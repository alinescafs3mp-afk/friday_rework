"""Intact Harness adapter. The trusted controller owns admission and threads.

Run these synchronous calls in the host's existing off-event-loop boundary.
No scheduler, retry, route discovery, new task/session identity or goal check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import suppress
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from typing import Callable, Mapping

from ..associations import _validate_store
from ..boundary import WorkBrief, parse_brief
from ..supervision import NativeSupervisor
from .contract import NativeObservation, PreparedNative, VerifiedInput
from ..worker_web import DshWebInputs, WorkerWebError, DSH_NETWORK_PROBE


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class PinnedFile:
    path: Path
    sha256: str

    def read(self):
        p = _regular(self.path)
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.sha256:
            raise AdapterError("host_input_changed")
        return data


@dataclass(frozen=True)
class DshHostConfig:
    """Only host code constructs this grant. Never deserialize model arguments.

    workspace_root contains private checked per-job association workspaces.
    payload/toolchain remain read-only mounts; patch is the reviewed native
    profile with environment references, not a secret or model-chosen route.
    environment supplies only the explicitly named local inference key.
    current_association must re-read the controller's checked durable row.
    """
    workspace_root: Path
    payload_root: Path
    toolchain_root: Path
    node: PinnedFile
    cli: PinnedFile
    patch: PinnedFile
    native_files: tuple[PinnedFile, ...]
    environment: Callable[[], Mapping[str, str]]
    current_association: Callable[[Mapping], Mapping]
    key_name: str
    profile: str = "headless"
    memory_bytes: int = 2 * 1024**3
    cpu_percent: int = 400
    tasks: int = 64
    shutdown_seconds: int = 2
    tmp_bytes: int = 64 * 1024**2
    web: DshWebInputs | None = None
    # Existing trusted controller's current check. No default producer/grant.
    verify_web_network: Callable | None = None


def _directory(p):
    p = Path(p)
    if (not p.is_absolute() or p.resolve() != p or not p.is_dir()
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(p))):
        raise AdapterError("unsafe_host_directory")
    return p


def _regular(p):
    p = Path(p)
    if not p.is_absolute() or p.resolve() != p:
        raise AdapterError("unsafe_host_file")
    s = p.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        raise AdapterError("unsafe_host_file")
    return p


def _private(p):
    p = _directory(p)
    if p.stat().st_uid != os.getuid() or stat.S_IMODE(p.stat().st_mode) != 0o700:
        raise AdapterError("job_directory_not_private")
    return p


def _sync(p):
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(p, data):
    """Atomically publish complete fsynced bytes without replacing an owner.

    The hard link is a no-clobber publication. Failure after publication stays
    uncertain; a partial temporary file is never exposed as a receipt.
    """
    if not isinstance(data, bytes):
        data = (json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix="." + p.name + ".", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            if f.write(data) != len(data):
                raise OSError("short_receipt_write")
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, p, follow_symlinks=False)
    finally:
        with suppress(OSError):
            os.unlink(temporary)
    _sync(p.parent)


def _json(p):
    def pairs(items):
        d = dict(items)
        if len(d) != len(items):
            raise AdapterError("duplicate_json_field")
        return d
    return json.loads(_regular(p).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(AdapterError("invalid_number")))


def _identity(row):
    return {k: row[k] for k in ("existing_task_id", "admission_hash", "owner",
                              "worker_kind", "brief_sha256", "workspace_reference",
                              "supervisor", "created_at_unix", "budget_seconds", "deadline_unix")}


class NativeEvents:
    """Strict finite native NDJSON reducer; exit zero alone proves nothing."""
    def __init__(self):
        self.session = None
        self.turn = None
        self.step = None
        self.completed = False
        self.final = False
        self.failed = False
        self.calls = set()
        self.results = set()
        self.rows = 0

    def feed(self, line):
        try:
            if len(line) > 4 * 1024**2 or not line.endswith(b"\n"):
                raise ValueError()
            def pairs(items):
                d = dict(items)
                if len(d) != len(items):
                    raise ValueError()
                return d
            v = json.loads(line, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(v, dict):
                raise ValueError()
            kind = v.get("type")
            if self.rows == 0:
                if (kind != "session" or set(v) != {"type", "sessionId", "cwd"}
                        or v["cwd"] != "/workspace"
                        or not re.fullmatch(r"session-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", v["sessionId"])):
                    raise ValueError()
                self.session = v["sessionId"]
            elif kind == "status":
                phase = v.get("phase")
                if type(v.get("turn")) is not int or v["turn"] != 1:
                    raise ValueError()
                if phase == "turn_start" and self.turn is None and not self.completed:
                    self.turn = 1
                elif phase == "step_start" and self.turn == 1 and self.step is None:
                    if type(v.get("step")) is not int or v["step"] <= 0:
                        raise ValueError()
                    self.step = v["step"]
                elif phase == "step_end" and self.step is not None and v.get("step") == self.step:
                    self.step = None
                elif phase == "turn_end" and self.turn == 1 and self.step is None:
                    self.completed = v.get("reason", {}).get("kind") == "completed"
                    self.failed |= not self.completed
                    self.turn = None
                else:
                    raise ValueError()
            elif kind == "tool_call" and self.turn == 1 and self.step is not None:
                call = v.get("callId")
                if not isinstance(call, str) or not call or call in self.calls:
                    raise ValueError()
                self.calls.add(call)
            elif kind == "tool_result" and self.turn == 1:
                call = v.get("callId")
                if call not in self.calls or call in self.results or v.get("status") not in {"completed", "failed"}:
                    raise ValueError()
                self.results.add(call)
            elif kind in {"thinking", "text"} and self.turn == 1:
                if not isinstance(v.get("text"), str):
                    raise ValueError()
            elif kind == "final" and self.completed and not self.final:
                if not isinstance(v.get("text"), str) or self.calls != self.results:
                    raise ValueError()
                self.final = True
            elif kind == "error":
                self.failed = True
            else:
                raise ValueError()
            self.rows += 1
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
            raise AdapterError("malformed_native_events") from exc


# Host-only teardown receipt survives successful unit collection and crashes
# before the opening session event. systemd supplies these actual fields.
_FINALIZE = b'''import os,sys,json,tempfile\nfrom pathlib import Path\nfrom contextlib import suppress\np=Path(sys.argv[1]); d={k:os.environ.get(k,"") for k in ("INVOCATION_ID","SERVICE_RESULT","EXIT_CODE","EXIT_STATUS")}\nf,t=tempfile.mkstemp(prefix=".terminal.",dir=p.parent)\ntry:\n with os.fdopen(f,"wb") as s:\n  b=(json.dumps(d)+"\\n").encode()\n  if s.write(b)!=len(b): raise OSError("short_terminal_write")\n  s.flush(); os.fsync(s.fileno())\n os.link(t,p,follow_symlinks=False)\nfinally:\n with suppress(OSError): os.unlink(t)\nf=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\ntry: os.fsync(f)\nfinally: os.close(f)\n'''


class DshAdapter:
    def __init__(self, config: DshHostConfig, *, supervisor=None, clock=time.time):
        self.config = config
        self.supervisor = supervisor or NativeSupervisor()
        self.clock = clock
        self._invocations = {}
        for p in (config.workspace_root, config.payload_root, config.toolchain_root):
            _directory(p)
        for value, maximum in ((config.memory_bytes, 2*1024**3), (config.cpu_percent, 400),
                               (config.tasks, 64), (config.shutdown_seconds, 2),
                               (config.tmp_bytes, 64*1024**2)):
            if type(value) is not int or not 0 < value <= maximum:
                raise AdapterError("invalid_resource_grant")
        if config.profile != "headless" or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", config.key_name):
            raise AdapterError("invalid_host_profile")
        if (not config.node.path.is_relative_to(config.toolchain_root)
                or config.cli.path != config.payload_root / "apps/cli/lib/bin.js"):
            raise AdapterError("invalid_native_payload_mapping")

    def _row(self, association):
        _validate_store({"schema_version": 1, "jobs": {association["existing_task_id"]: dict(association)}})
        row = dict(self.config.current_association(association))
        _validate_store({"schema_version": 1, "jobs": {row["existing_task_id"]: row}})
        if _identity(row) != _identity(association) or row["worker_kind"] != "dsh":
            raise AdapterError("foreign_or_changed_association")
        root = _private(row["workspace_reference"])
        if root == self.config.workspace_root or not root.is_relative_to(self.config.workspace_root):
            raise AdapterError("foreign_workspace")
        return row, root

    def _admit(self, row):
        if self._retained_stop(row):
            raise AdapterError("stopped_or_expired")

    def _retained_stop(self, row):
        return (row["stop_intent"] is not None or self.clock() >= row["deadline_unix"]
                or row["elapsed_seconds"] >= row["budget_seconds"])

    def _remaining(self, row):
        return min(row["deadline_unix"] - self.clock(),
                   row["budget_seconds"] - row["elapsed_seconds"]) - self.config.shutdown_seconds - 5

    def _pins(self):
        c = self.config
        if c.web is not None:
            c.web.checked_patch(c.patch.read())
        else:
            try:
                rows = json.loads(c.patch.read())
            except (ValueError, UnicodeError):
                rows = []  # Existing reviewed non-JSON native profiles.
            if isinstance(rows, list) and any(isinstance(r, dict) and r.get('id') == 'tool-web'
                    and r.get('disabled') is False for r in rows):
                raise AdapterError('worker_web_inputs_missing')
        return {str(p.path): hashlib.sha256(p.read()).hexdigest()
                for p in (c.node, c.cli, c.patch, *c.native_files,
                          *(c.web.pins() if c.web else ()))}

    def _content(self, row, brief, inputs):
        brief = parse_brief(vars(brief))
        if brief.worker != "dsh" or hashlib.sha256(json.dumps(vars(brief), sort_keys=True, ensure_ascii=False).encode()).hexdigest() != row["brief_sha256"]:
            raise AdapterError("brief_mismatch")
        values = []
        names = set()
        for v in inputs:
            if (type(v.size_bytes) is not int or not 0 <= v.size_bytes <= 16*1024**2
                    or not re.fullmatch(r"[0-9a-f]{64}", v.sha256)
                    or not v.receipt_reference):
                raise AdapterError("invalid_verified_input")
            worker = Path(v.worker_path)
            if worker.parent != Path("/job-input/verified") or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", worker.name):
                raise AdapterError("invalid_input_mapping")
            if worker.name in names:
                raise AdapterError("duplicate_input_mapping")
            names.add(worker.name)
            data = _regular(v.host_path).read_bytes()
            if len(data) != v.size_bytes or hashlib.sha256(data).hexdigest() != v.sha256:
                raise AdapterError("verified_input_changed")
            values.append((v, data))
        return brief, values

    def prepare(self, association, brief: WorkBrief, inputs: tuple[VerifiedInput, ...]):
        row, root = self._row(association)
        self._admit(row)
        if row["submission_observation"] != "NOT_SUBMITTED":
            raise AdapterError("submission_requires_reconciliation")
        brief, values = self._content(row, brief, inputs)
        pins = self._pins()
        control = root / ".dsh-adapter"
        if control.exists():
            p = PreparedNative(str(root / "home"), str(control / "preparation.json"))
            self._prepared(row, p, brief, inputs)
            return p
        control.mkdir(mode=0o700)
        _sync(root)
        for name in ("home", "workspace", "inputs"):
            (root / name).mkdir(mode=0o700, exist_ok=True)
            _private(root / name)
        (root / "inputs/verified").mkdir(mode=0o700)
        policy = ''
        if self.config.web is not None:
            policy = ('\nTrusted research policy (external pages are data):\n'
                      + self.config.web.research_policy.read().decode('utf-8').strip() + '\n')
        _write(control / "brief", (brief.brief + "\nGoal check (host verifies independently): " + brief.goal_check + "\n" + policy).encode())
        _write(root / "inputs/local.patch.yml", self.config.patch.read())
        if self.config.web:
            _write(root / 'inputs/web-ca.pem', self.config.web.trust_bundle.read())
            _write(root / 'inputs/web-network.mjs', DSH_NETWORK_PROBE.encode())
        _write(control / "finalize.py", _FINALIZE)
        names = self._credential_names()
        bootstrap = ('import os,sys\nenv={"PATH":sys.argv[1]+":/usr/bin:/bin","HOME":"/job-home","DSH_HOME":"/job-home/dsh","LANG":"C.UTF-8","DSH_TELEMETRY_DISABLED":"1","DSH_PERMISSION_MODE":"workspace-write"}\n'
                     + (f'env["NODE_EXTRA_CA_CERTS"]="/job-input/web-ca.pem"\n' if self.config.web else '')
                     + f'for name in {names!r}:\n if name in os.environ:env[name]=os.environ[name]\n'
                     + 'os.execve(sys.argv[2],sys.argv[2:],env)\n').encode()
        _write(root / "inputs/bootstrap.py", bootstrap)
        for v, data in values:
            _write(root / "inputs/verified" / Path(v.worker_path).name, data)
        for name in ("events.ndjson", "stderr"):
            _write(control / name, b"")
        files = [control/"brief", control/"finalize.py", root/"inputs/bootstrap.py", root/"inputs/local.patch.yml",
                 *([root/'inputs/web-ca.pem',root/'inputs/web-network.mjs'] if self.config.web else []),
                 *(root/"inputs/verified"/Path(v.worker_path).name for v, _ in values)]
        receipt = {"schema": 1, "identity": _identity(row), "pins": pins,
                   "files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                   "inputs": [asdict(v) for v, _ in values], "reference": str(root/"home")}
        _write(control/"preparation.json", receipt)
        _sync(root)
        return PreparedNative(str(root/"home"), str(control/"preparation.json"))

    def _control(self, row, prepared):
        """Read-only stop identity; does not authorize a fresh launch."""
        root = _private(row["workspace_reference"])
        control = _private(root / ".dsh-adapter")
        if prepared != PreparedNative(str(root/"home"), str(control/"preparation.json")):
            raise AdapterError("foreign_preparation")
        return root, control

    def _prepared(self, row, prepared, brief=None, inputs=None, *, verify_files=True):
        root, control = self._control(row, prepared)
        receipt = _json(control/"preparation.json")
        if (set(receipt) != {"schema", "identity", "pins", "files", "inputs", "reference"}
                or receipt["schema"] != 1 or receipt["identity"] != _identity(row)
                or receipt["reference"] != prepared.reference):
            raise AdapterError("preparation_changed")
        if verify_files:
            if receipt["pins"] != self._pins():
                raise AdapterError("preparation_changed")
            for path, digest in receipt["files"].items():
                p = _regular(path)
                if not p.is_relative_to(root) or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                    raise AdapterError("preparation_changed")
        if verify_files:
            for name in ("home", "workspace"):
                _directory(root/name)
            for name in ("inputs", "inputs/verified"):
                _private(root/name)
        if brief is not None:
            _, values = self._content(row, brief, inputs)
            if receipt["inputs"] != [asdict(v) for v, _ in values]:
                raise AdapterError("input_receipt_changed")
        return root, control

    def _boundary(self, root, command):
        c = self.config
        return ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--ro-bind", "/usr", "/usr",
                "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                "--proc", "/proc", "--dev", "/dev", "--size", str(c.tmp_bytes), "--tmpfs", "/tmp",
                "--ro-bind", str(c.toolchain_root), str(c.toolchain_root),
                "--ro-bind", str(c.payload_root), str(c.payload_root),
                "--ro-bind", str(root/"inputs"), "/job-input", "--bind", str(root/"workspace"), "/workspace",
                "--bind", str(root/"home"), "/job-home",
                *(c.web.mounts() if c.web else ()),
                "--chdir", "/workspace", "--remount-ro", "/",
                "--", "/usr/bin/python3", "-I", "/job-input/bootstrap.py", str(c.node.path.parent), *command]

    @staticmethod
    def _environment():
        runtime = f"/run/user/{os.getuid()}"
        return {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": runtime,
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime}/bus", "LC_ALL": "C"}

    @staticmethod
    def _key(row):
        return json.dumps(_identity(row), sort_keys=True)

    @staticmethod
    def _auxiliary_invocation(control, name, *, strict=False):
        try:
            value = _json(control / name)
            fields = ({"invocation_id"} if name == "invocation.json" else
                      {"INVOCATION_ID", "SERVICE_RESULT", "EXIT_CODE", "EXIT_STATUS"})
            key = "invocation_id" if name == "invocation.json" else "INVOCATION_ID"
            if (not isinstance(value, dict) or set(value) != fields
                    or not isinstance(value[key], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", value[key])):
                raise AdapterError("invalid_invocation_receipt")
            return value[key]
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, AdapterError, RecursionError):
            if strict:
                raise
            # Auxiliary corruption cannot prevent exact-owned supervision.
            # Valid but contradictory identities are still refused below.
            return None

    def _known(self, row, control, *, strict=False):
        """Read checked identity without writing or trusting partial JSON."""
        native = dict(row)
        candidates = [(row["native"] or {}).get("invocation_id"),
                      self._invocations.get(self._key(row)),
                      *(self._auxiliary_invocation(control, name, strict=strict)
                        for name in ("invocation.json", "terminal.json"))]
        identities = {v for v in candidates if v}
        if len(identities) > 1:
            raise AdapterError("native_invocation_changed")
        if identities:
            native["native"] = {"invocation_id": identities.pop(),
                                "worker_reference": (row["native"] or {}).get("worker_reference", "")}
        return native

    def _remember(self, row, control, invocation):
        if not re.fullmatch(r"[0-9a-f]{32}", invocation):
            raise AdapterError("invalid_native_invocation")
        known = self._known(row, control)
        if known["native"] is not None and known["native"]["invocation_id"] != invocation:
            raise AdapterError("native_invocation_changed")
        self._invocations[self._key(row)] = invocation

    def _persist_invocation(self, row, control):
        known = self._known(row, control, strict=True)
        if known["native"] is not None and not (control/"invocation.json").exists():
            _write(control/"invocation.json", {"invocation_id": known["native"]["invocation_id"]})

    def _stop_owned(self, row, control):
        known = self._known(row, control)
        before = self.supervisor.observe(known)
        if before.invocation_id:
            self._remember(row, control, before.invocation_id)
            known = self._known(row, control)
        unit = self.supervisor.stop(known)
        if not unit.quiescent:
            raise AdapterError("native_stop_unconfirmed")
        if unit.invocation_id:
            self._remember(row, control, unit.invocation_id)
        return unit

    def _cleanup(self, row, control, error):
        """Keep the initiating error even when exact-owned stop fails."""
        try:
            unit = self._stop_owned(row, control)
        except BaseException as stop_error:
            error.stop_confirmed = False
            error.stop_error = stop_error
            error.add_note("STOP_UNCONFIRMED: " + type(stop_error).__name__)
        else:
            error.stop_confirmed = True
            error.stop_observation = unit
            error.add_note("Owned native boundary quiescence confirmed")

    def _reference(self, row, session):
        prior = (row["native"] or {}).get("worker_reference")
        if prior and not re.fullmatch(r"session-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", prior):
            raise AdapterError("invalid_native_session")
        if prior and session and prior != session:
            raise AdapterError("native_session_changed")
        return session or prior or ""

    def _events(self, control, *, terminal=False):
        p = _regular(control / "events.ndjson")
        if p.stat().st_size > 16*1024**2:
            raise AdapterError("native_events_too_large")
        data = p.read_bytes()
        state = NativeEvents()
        lines = data.splitlines(keepends=True)
        for line in lines:
            if not line.endswith(b"\n") and not terminal:
                break
            state.feed(line)
        return state

    def _launch_argv(self, row, root, control, remaining, grant, command):
        c = self.config
        argv = ["/usr/bin/systemd-run", "--user", "--no-ask-password", "--expand-environment=no",
                "--unit="+row["supervisor"]["unit"], "--description="+self.supervisor.description(row),
                "--property=Type=exec", "--property=Restart=no", "--property=KillMode=control-group",
                "--property=SendSIGKILL=yes", "--property=NoNewPrivileges=yes", "--property=UMask=0077",
                f"--property=RuntimeMaxSec={remaining:.6f}s", f"--property=TimeoutStopSec={c.shutdown_seconds}s",
                f"--property=MemoryMax={c.memory_bytes}", f"--property=CPUQuota={c.cpu_percent}%",
                f"--property=TasksMax={c.tasks}", "--property=StandardInput=file:"+str(control/"brief"),
                "--property=StandardOutput=append:"+str(control/"events.ndjson"),
                "--property=StandardError=append:"+str(control/"stderr"),
                "--property=ExecStopPost=/usr/bin/python3 -I "+str(control/"finalize.py")+" "+str(control/"terminal.json")]
        argv += ['--setenv='+name for name in sorted(grant)]
        # --clearenv leaves only the explicit local key; bootstrap replaces all
        # worker environment with the minimal reviewed native environment.
        boundary = self._boundary(root, command)
        if not grant:
            boundary.insert(1, "--clearenv")
        argv += boundary
        return argv

    def submit(self, association, brief, inputs, prepared, on_native_observed):
        row, root = self._row(association)
        self._admit(row)
        if row["submission_observation"] != "UNKNOWN" or row["native"] is not None:
            raise AdapterError("durable_unknown_required")
        root, control = self._prepared(row, prepared, brief, inputs)
        if not self.supervisor.observe(row).missing:
            raise AdapterError("planned_unit_already_exists")
        # O_EXCL is durable per-job handoff, not a second admission store. A
        # crash anywhere after it requires reconciliation and never replay.
        # Reserve both the bounded launch RPC and native shutdown. RPC time
        # never becomes a hidden deadline extension or a fresh task budget.
        remaining = self._remaining(row)
        if not math.isfinite(remaining) or remaining <= 0:
            raise AdapterError("stopped_or_expired")
        env = self._environment()
        if self.config.web:
            if not callable(self.config.verify_web_network):
                raise AdapterError('worker_web_network_admission_missing')
            self.config.verify_web_network(row, self.config.web)
            current, _ = self._row(row)
            self._admit(current)
        grant = dict(self.config.environment())
        allowed = set(self._credential_names())
        if (set(grant) not in ((allowed,) if self.config.web else (set(), allowed))
                or any(not isinstance(v,str) or not v or len(v)>4096
                       or any(ord(c)<32 or ord(c)==127 for c in v) for v in grant.values())):
            raise AdapterError("invalid_scoped_environment")
        env.update(grant)
        c = self.config
        command = [str(c.node.path), str(c.cli.path), "--profile", c.profile,
                   "--patch", "/job-input/local.patch.yml", "--json", "-"]
        argv = self._launch_argv(row, root, control, remaining, grant, command)
        _write(control/"submission.json", {"identity": _identity(row), "argv": argv,
                                            "remaining_seconds": remaining, "at_unix": self.clock(), "state": "UNKNOWN"})
        try:
            current, _ = self._row(row)
            self._admit(current)
            if self.config.web:
                self.config.verify_web_network(current, self.config.web)
                self._prepared(current, prepared, brief, inputs)
                current, _ = self._row(row)
                self._admit(current)
                if dict(self.config.environment()) != grant:
                    raise AdapterError('scoped_environment_changed_before_launch')
            remaining = self._remaining(current)
            if remaining <= 0:
                raise AdapterError("stopped_or_expired")
            argv = self._launch_argv(current, root, control, remaining, grant, command)
            _write(control/"launch-grant.json", {"argv": argv, "remaining_seconds": remaining,
                                                "deadline_unix": current["deadline_unix"], "at_unix": self.clock()})
            # One bounded native launch. Timeout is uncertain, never retry.
            r = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False)
            ids = re.findall(rb"invocation ID: ([0-9a-f]{32})", r.stderr)
            if len(ids) == 1:
                self._remember(row, control, ids[0].decode())
            observed = self.supervisor.observe(self._known(row, control))
            if observed.invocation_id:
                self._remember(row, control, observed.invocation_id)
            _write(control/"launch.json", {"returncode": r.returncode, "stdout": r.stdout.decode(errors="replace"),
                                           "stderr": r.stderr.decode(errors="replace")})
            if self._known(row, control)["native"] is None:
                raise AdapterError("submission_unknown")
            self._persist_invocation(row, control)
            if r.returncode != 0:
                raise AdapterError("native_launch_failed")
            while True:
                current, _ = self._row(row)
                known = self._known(current, control)
                unit = self.supervisor.observe(known)
                if self._retained_stop(current):
                    self._stop_owned(current, control)
                    raise AdapterError("stopped_or_expired")
                events = self._events(control, terminal=unit.quiescent)
                if events.session:
                    value = self.observe(current, prepared)
                    on_native_observed(value)
                    # Re-read retained intent immediately after durable callback.
                    current, _ = self._row(row)
                    if self._retained_stop(current):
                        return self.stop(current, prepared, current["stop_intent"] or "deadline")
                    return value
                if unit.quiescent:
                    raise AdapterError("native_session_not_observed")
                # Finite local opening-event read, bounded by original native
                # timer. No mailbox, peer, model or service-health polling.
                time.sleep(.02)
        except BaseException as error:
            self._cleanup(row, control, error)
            raise

    def _credential_names(self):
        if self.config.web and self.config.key_name == 'EXA_API_KEY':
            raise AdapterError('web_and_inference_credentials_overlap')
        return (self.config.key_name, 'EXA_API_KEY') if self.config.web else (self.config.key_name,)

    def observe(self, association, prepared):
        row, _ = self._row(association)
        _, control = self._control(row, prepared)
        known = self._known(row, control)
        unit = self.supervisor.observe(known)
        if unit.invocation_id:
            self._remember(row, control, unit.invocation_id)
        if self._retained_stop(row):
            return self.stop(row, prepared, row["stop_intent"] or "deadline")
        try:
            self._prepared(row, prepared)
            self._persist_invocation(row, control)
            events = self._events(control, terminal=unit.quiescent)
            return self._observation(row, control, unit, events)
        except BaseException as error:
            self._cleanup(row, control, error)
            raise

    def _observation(self, row, control, unit, events):
        known = self._known(row, control)
        inv = unit.invocation_id or (known.get("native") or {}).get("invocation_id", "")
        reference = self._reference(row, events.session)
        state = "running" if not unit.quiescent and events.session else "unknown"
        terminal = control/"terminal.json"
        if unit.quiescent and terminal.exists():
            end = _json(terminal)
            if (set(end) != {"INVOCATION_ID", "SERVICE_RESULT", "EXIT_CODE", "EXIT_STATUS"}
                    or end["INVOCATION_ID"] != inv):
                raise AdapterError("foreign_terminal_receipt")
            state = "failed"
            if end["SERVICE_RESULT"] == "success" and end["EXIT_CODE"] == "exited" and end["EXIT_STATUS"] == "0" and events.completed and events.final and not events.failed:
                state = "completed"
        if self._retained_stop(row):
            state = "stopped" if unit.quiescent else "unknown"
        value = NativeObservation(inv, reference, str(control/"events.ndjson"),
                                  max(row["elapsed_seconds"], self.clock()-row["created_at_unix"]), state)
        return value

    def stop(self, association, prepared, intent):
        if intent not in {"cancel", "pause", "deadline"}:
            raise AdapterError("invalid_stop_intent")
        row, _ = self._row(association)
        _, control = self._control(row, prepared)
        if intent == "deadline":
            if self.clock() < row["deadline_unix"] and row["elapsed_seconds"] < row["budget_seconds"]:
                raise AdapterError("deadline_not_reached")
        elif row["stop_intent"] not in ({"pause", "cancel"} if intent == "pause" else {"cancel"}):
            raise AdapterError("durable_stop_required")
        unit = self._stop_owned(row, control)
        known = self._known(row, control)
        inv = unit.invocation_id or (known.get("native") or {}).get("invocation_id", "")
        # Malformed output cannot prevent a confirmed owned native stop.
        try:
            session = self._events(control, terminal=True).session
        except (AdapterError, OSError, ValueError, RecursionError):
            session = None
        reference = self._reference(row, session)
        return NativeObservation(inv, reference, str(control/"events.ndjson"),
                                 max(row["elapsed_seconds"], self.clock()-row["created_at_unix"]), "stopped")
