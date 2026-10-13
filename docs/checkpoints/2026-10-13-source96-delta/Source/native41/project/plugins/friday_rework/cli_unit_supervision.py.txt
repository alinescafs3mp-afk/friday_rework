"""External observation/stop seam for an exclusively owned original CLI unit.

Uses the existing NativeSupervisor. It launches/reloads no unit or frontend.
Construction is NOT an authority grant. Root must supply a fresh durably owned
original-CLI association distinct from any worker, a separate existing owner
outside that unit, and whole native resource qualification. No such current
composition is supplied by the pinned inputs.
"""
from dataclasses import dataclass
import copy
import os
from pathlib import Path
import time

from .supervision import NativeSupervisor, SupervisorError


@dataclass(frozen=True)
class OriginalProcessBirth:
    boot_id: str
    pid: int
    start_ticks: int


def _birth(pid):
    if type(pid) is not int or pid <= 0:
        raise SupervisorError("invalid_original_cli_pid")
    raw = Path(f"/proc/{pid}/stat").read_text()
    # comm may contain spaces or ')'; parse after its final closing parenthesis.
    fields = raw.rsplit(")", 1)[1].split()
    return OriginalProcessBirth(
        Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        pid, int(fields[19]))


def _group(pid):
    rows = [line.split(":", 2) for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()]
    unified = [row[2] for row in rows if len(row) == 3 and row[:2] == ["0", ""]]
    if len(unified) != 1 or not unified[0].startswith("/"):
        raise SupervisorError("original_cli_unified_group_unconfirmed")
    return unified[0]


class ExternalOriginalCLIUnit:
    def __init__(self, association, *, expected_birth, expected_invocation):
        if type(expected_birth) is not OriginalProcessBirth:
            raise SupervisorError("original_cli_birth_not_retained")
        if association.get("native", {}).get("invocation_id") != expected_invocation:
            raise SupervisorError("original_cli_invocation_not_retained")
        self.supervisor = NativeSupervisor()
        self.association = copy.deepcopy(association)
        self.birth = expected_birth
        self.invocation = expected_invocation
        self.owner_birth = _birth(os.getpid())
        self.entry = None
        self.deadline = None
        self.stop_started = False
        self.stop_result = None
        self.last_error = None

    def _outside_owned_unit(self, observed):
        owner_group = _group(self.owner_birth.pid)
        owned = observed.control_group
        if (self.owner_birth.pid == self.birth.pid
                or owner_group == owned or owner_group.startswith(owned + "/")):
            raise SupervisorError("original_cli_unit_owner_would_stop_itself")

    def bind_original_clock(self, *, entry, deadline):
        # This only narrows an already supplied original caller clock.
        # It does not create the caller, claim a unit or authorize a runtime.
        now = time.monotonic()
        if (self.entry is not None or type(entry) not in (int, float)
                or type(deadline) not in (int, float)
                or not 0 < entry <= now < deadline <= entry + 30.0):
            raise SupervisorError("original_cli_clock_not_retained")
        observed = self.supervisor.observe(self.association, deadline=deadline)
        if (observed.quiescent or observed.invocation_id != self.invocation
                or observed.main_pid != self.birth.pid or _birth(self.birth.pid) != self.birth
                or _group(self.birth.pid) != observed.control_group
                or _birth(self.owner_birth.pid) != self.owner_birth):
            raise SupervisorError("original_cli_unit_birth_or_owner_changed")
        self._outside_owned_unit(observed)
        self.entry = entry
        self.deadline = deadline

    def narrow(self, deadline):
        if self.deadline is None or not self.entry < deadline <= self.deadline:
            raise SupervisorError("original_cli_unit_deadline_widened_or_missing")
        self.deadline = deadline

    def stop(self):
        if self.deadline is None or self.stop_started:
            raise SupervisorError("original_cli_stop_missing_clock_or_duplicate")
        self.stop_started = True
        try:
            before = self.supervisor.observe(self.association, deadline=self.deadline)
            self._outside_owned_unit(before)
            if before.invocation_id != self.invocation:
                raise SupervisorError("original_cli_invocation_replaced_before_stop")
            if not before.quiescent and _birth(self.birth.pid) != self.birth:
                raise SupervisorError("original_cli_process_recycled_before_stop")
            after = self.supervisor.stop(self.association, deadline=self.deadline)
            if (not after.quiescent or time.monotonic() >= self.deadline
                    or after.invocation_id not in ("", self.invocation)):
                raise SupervisorError("original_cli_unit_stop_unconfirmed")
            self.stop_result = after
            return after
        except BaseException as exc:
            self.last_error = type(exc).__name__
            # The exact association remains retained; no retry, new unit or
            # 'stopped' bool is minted after command/observe uncertainty.
            raise
