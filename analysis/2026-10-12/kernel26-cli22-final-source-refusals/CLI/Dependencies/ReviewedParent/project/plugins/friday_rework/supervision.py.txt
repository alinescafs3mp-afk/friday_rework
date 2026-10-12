"""Observe/stop an existing owned user-systemd boundary; never launch or retry.

Quiescence here describes this cgroup only. In particular, terminating an A0
HTTP client is not proof that its dedicated server/context or remote inference
stopped; the A0 adapter must reconcile those separate native boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess

from .associations import _supervisor


class SupervisorError(RuntimeError):
    pass


@dataclass(frozen=True)
class UnitObservation:
    unit: str
    invocation_id: str
    active_state: str
    sub_state: str
    result: str
    main_pid: int
    control_group: str
    populated: bool | None
    missing: bool = False

    @property
    def quiescent(self):
        return (self.missing or self.active_state in {"inactive", "failed"}) and self.main_pid == 0 and self.populated is False


class NativeSupervisor:
    """Only the controller may pass a checked, durably owned association.

    The launch must use Description=description(association), KillMode=control-group
    and SendSIGKILL=yes. An observed invocation may never silently be replaced.
    Stop intent is persisted by the controller first; persistence failure must
    still attempt stop using its last checked association, retaining uncertainty.
    """
    properties = ("LoadState", "Transient", "Description", "InvocationID",
                  "ActiveState", "SubState", "Result", "MainPID", "ControlGroup",
                  "KillMode", "SendSIGKILL")
    # Supported service observations. Future/unknown states require explicit
    # reconciliation, never a fabricated successful stop. Zero MainPID is valid
    # during pre/post commands, forking discovery and RemainAfterExit.
    substates = {
        "inactive": {"dead"},
        "failed": {"failed"},
        "active": {"running", "exited"},
        "activating": {"condition", "start-pre", "start", "start-post"},
        "reloading": {"reload", "reload-signal", "reload-notify"},
        "deactivating": {"stop", "stop-watchdog", "stop-sigterm", "stop-sigkill",
                         "stop-post", "final-watchdog", "final-sigterm", "final-sigkill"},
    }
    results = {"success", "resources", "protocol", "timeout", "exit-code", "signal",
               "core-dump", "watchdog", "start-limit-hit", "exec-condition", "oom-kill"}

    @staticmethod
    def description(association):
        digest = association.get("admission_hash")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SupervisorError("invalid_admission_identity")
        return "Friday rework " + digest

    @staticmethod
    def _unit(association):
        supervisor = _supervisor(association["supervisor"])
        if supervisor["scope"] != "user":
            raise SupervisorError("unsupported_supervisor_scope")
        return supervisor["unit"]

    @staticmethod
    def _command(arguments, timeout):
        runtime = f"/run/user/{os.getuid()}"
        try:
            return subprocess.run(
                ["/usr/bin/systemctl", "--user", "--no-pager", *arguments],
                env={"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": runtime,
                     "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime}/bus", "LC_ALL": "C"},
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SupervisorError("native_control_unavailable") from exc

    @staticmethod
    def _populated(group):
        if not group:
            return False
        root = Path("/sys/fs/cgroup")
        path = root / group.lstrip("/")
        if not group.startswith("/") or path.resolve() != path or not path.is_relative_to(root):
            raise SupervisorError("invalid_native_cgroup")
        try:
            entries = [line.split() for line in (path / "cgroup.events").read_text().splitlines()]
            if any(len(entry) != 2 for entry in entries):
                raise ValueError("malformed cgroup fields")
            rows = dict(entries)
            if len(rows) != len(entries):
                raise ValueError("duplicate cgroup fields")
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as exc:
            raise SupervisorError("native_cgroup_unreadable") from exc
        if rows.get("populated") not in {"0", "1"}:
            raise SupervisorError("invalid_native_cgroup_observation")
        return rows["populated"] == "1"

    def observe(self, association):
        unit = self._unit(association)
        expected = self.description(association)
        result = self._command(["show", unit, "--property=" + ",".join(self.properties)], 3)
        if result.returncode != 0:
            raise SupervisorError("native_unit_unreadable")
        try:
            entries = [line.split("=", 1) for line in result.stdout.splitlines()]
            fields = dict(entries)
            if len(fields) != len(entries) or set(fields) != set(self.properties):
                raise ValueError("incomplete or duplicate unit fields")
        except ValueError as exc:
            raise SupervisorError("invalid_native_unit_observation") from exc
        if fields["LoadState"] == "not-found":
            missing = {"LoadState": "not-found", "Transient": "no", "Description": unit,
                       "InvocationID": "", "ActiveState": "inactive", "SubState": "dead",
                       "Result": "success", "MainPID": "0", "ControlGroup": "",
                       "KillMode": "control-group", "SendSIGKILL": "yes"}
            if fields != missing:
                raise SupervisorError("inconsistent_missing_unit")
            return UnitObservation(unit, "", fields["ActiveState"], fields["SubState"],
                                   fields["Result"], 0, "", False, True)
        if fields["LoadState"] != "loaded":
            raise SupervisorError("invalid_native_load_state")
        if (fields["SubState"] not in self.substates.get(fields["ActiveState"], set())
                or fields["Result"] not in self.results):
            raise SupervisorError("inconsistent_native_service_state")
        if fields.get("Transient") != "yes" or fields.get("Description") != expected:
            raise SupervisorError("native_unit_owner_mismatch")
        invocation = fields.get("InvocationID", "")
        if not re.fullmatch(r"[0-9a-f]{32}", invocation):
            raise SupervisorError("invalid_native_invocation")
        prior = association.get("native")
        if prior is not None and prior["invocation_id"] != invocation:
            raise SupervisorError("native_invocation_changed")
        if fields.get("KillMode") != "control-group" or fields.get("SendSIGKILL") != "yes":
            raise SupervisorError("native_stop_boundary_changed")
        try:
            if not re.fullmatch(r"0|[1-9][0-9]{0,19}", fields["MainPID"]):
                raise ValueError("invalid pid")
            pid = int(fields["MainPID"])
            group = fields["ControlGroup"]
            if group and not group.endswith("/" + unit):
                raise SupervisorError("native_cgroup_owner_mismatch")
            populated = self._populated(group)
            if (pid and (not group or not populated)
                    or fields["SubState"] == "running" and (not group or not populated)
                    or pid and fields["ActiveState"] in {"inactive", "failed"}):
                raise SupervisorError("inconsistent_native_process_state")
            return UnitObservation(unit, invocation, fields["ActiveState"], fields["SubState"],
                                   fields["Result"], pid, group, populated)
        except (KeyError, ValueError) as exc:
            raise SupervisorError("invalid_native_unit_observation") from exc

    def stop(self, association):
        before = self.observe(association)
        if before.quiescent:
            return before
        # Reusing the observed invocation after this check is prevented by the
        # controller's sole-writer/ownership boundary; do not add --all or killall.
        result = self._command(["stop", before.unit], 15)
        if result.returncode != 0:
            raise SupervisorError("native_stop_unconfirmed")
        after = self.observe(association)
        if after.invocation_id and after.invocation_id != before.invocation_id:
            raise SupervisorError("native_invocation_changed")
        if not after.quiescent:
            raise SupervisorError("native_stop_unconfirmed")
        return after
