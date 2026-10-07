"""A0 REST/file calls inside an already admitted dedicated native environment.

No launch, scheduler, retry or network admission. Whole-environment stop uses
the existing NativeSupervisor and exact Docker identity, including descendants.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from ..supervision import NativeSupervisor
from .a0_config import A0Deployment, A0Error, require, local_profile


def strict_json(data):
    def pairs(items):
        result = dict(items)
        require(len(result) == len(items), "duplicate_json_field")
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(A0Error("invalid_number")))
    except (ValueError, UnicodeError, TypeError):
        raise A0Error("invalid_native_json") from None


def decode_file(value, limit):
    require(isinstance(value, str) and len(value) <= 4 * ((limit + 2) // 3), "oversized_file")
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise A0Error("invalid_base64") from None
    require(len(data) <= limit and base64.b64encode(data).decode() == value, "noncanonical_base64")
    return data


# Body and effective native key never enter argv or a transport error. Only
# bounded successful raw JSON crosses stdout; the host rejects duplicate fields.
API_SCRIPT = '''import base64,contextlib,io,json,sys,urllib.request
try:
 v=json.load(sys.stdin)
 assert v['path'] in ('/api/api_message','/api/api_log_get','/api/api_files_get')
 assert v['method'] in ('GET','POST')
 with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
  from helpers import dotenv,runtime,settings
  runtime.initialize();dotenv.load_dotenv()
  key=settings.get_settings()['mcp_server_token']
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs): raise ValueError('redirect_refused')
 body=json.dumps(v['payload']).encode() if v['method']=='POST' else None
 url='http://127.0.0.1:5000'+v['path']
 if v['method']=='GET':
  import urllib.parse
  url+='?'+urllib.parse.urlencode(v['payload'])
 request=urllib.request.Request(url,data=body,method=v['method'],headers={'X-API-KEY':key,'Content-Type':'application/json'})
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 with opener.open(request,timeout=v['timeout']) as response:
  assert response.status==200
  raw=response.read(v['max_bytes']+1)
  assert len(raw)<=v['max_bytes']
 # Redact actual private keys if a worker echoed them in its response.
 import os
 for secret in (key,os.getenv('API_KEY_OPENAI'),os.getenv('API_KEY_OTHER')):
  if secret: raw=raw.replace(secret.encode(),b'[redacted]')
 print(json.dumps({'ok':True,'body':base64.b64encode(raw).decode()}))
except BaseException:
 print('{"ok":false}')
 raise SystemExit(1)
'''


def native_file(root, relative, limit):
    """Walk with dirfds/no-follow; reject changed files and hard links."""
    import stat
    parts = relative.split("/")
    require(parts and all(p not in {"", ".", ".."} for p in parts), "unsafe_native_file")
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_size <= limit, "unsafe_native_file")
        chunks, size = [], 0
        while data := os.read(fd, min(65536, limit - size + 1)):
            size += len(data); require(size <= limit, "oversized_file"); chunks.append(data)
        identity = lambda s: [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                              s.st_ctime_ns, s.st_nlink, s.st_mode]
        require(identity(before) == identity(os.fstat(fd)) == identity(
            os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)), "mutable_native_file")
        data = b"".join(chunks)
        return {"identity": identity(before), "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "base64": base64.b64encode(data).decode()}
    finally:
        if fd is not None: os.close(fd)
        os.close(parent)


def file_script():
    import inspect
    return ("import os,json,base64,hashlib,sys\nclass A0Error(RuntimeError): pass\n"
            + inspect.getsource(require) + inspect.getsource(native_file)
            + "try:\n v=json.load(sys.stdin);value=native_file('/a0',v['relative'],v['limit'])\n"
            + " import contextlib,io\n with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):\n"
            + "  from helpers import dotenv,runtime,settings\n  runtime.initialize();dotenv.load_dotenv()\n"
            + "  secrets=(settings.get_settings()['mcp_server_token'],os.getenv('API_KEY_OPENAI'),os.getenv('API_KEY_OTHER'))\n"
            + " data=base64.b64decode(value['base64'],validate=True)\n"
            + " require(not any(s and s.encode() in data for s in secrets),'runtime_secret_in_file')\n"
            + " print(json.dumps(value))\n"
            + "except BaseException:\n print('{}');raise SystemExit(1)\n")


@dataclass(frozen=True)
class NativeGrant:
    """Actual launch identity from the trusted owner, never tool/model input."""
    container_id: str
    container_name: str
    invocation_id: str
    labels: dict
    accepted_unix: float
    deadline_unix: float
    container_cgroup: str
    boot_id: str
    # Current independently reviewed egress evidence; not a file-presence gate.
    network_verified: bool = False
    keys_prepared_monotonic: float = 0
    daemon_invocation_id: str = ""
    accepted_monotonic: float = 0


def _duration(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]+)?(?:us|ms|s|min|h) ?)+", value):
        raise A0Error("unbounded_native_deadline")
    scales = {"us": 1e-6, "ms": .001, "s": 1, "min": 60, "h": 3600}
    return sum(float(n) * scales[u] for n, u in re.findall(r"([0-9]+(?:\.[0-9]+)?)(us|ms|min|s|h)", value))


class A0NativeBoundary:
    def __init__(self, deployment: A0Deployment, grant: NativeGrant, *, supervisor=None,
                 runner=None, clock=time.time, monotonic=time.monotonic):
        self.config, self.grant = deployment.checked(), grant
        self.supervisor = supervisor or NativeSupervisor()
        self.runner = runner or self._run
        self.clock, self.monotonic = clock, monotonic
        self.samples = []
        self.stop_requested = False
        require(re.fullmatch(r"[0-9a-f]{64}", grant.container_id)
                and re.fullmatch(r"[0-9a-f]{32}", grant.invocation_id)
                and re.fullmatch(r"[0-9a-f]{32}", grant.daemon_invocation_id)
                and re.fullmatch(r"frw-a0-[0-9a-f]{32}", grant.container_name), "invalid_native_identity")
        require(grant.boot_id == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                and grant.container_cgroup.startswith('/user.slice/')
                and str(Path(grant.container_cgroup)) == grant.container_cgroup
                and '..' not in Path(grant.container_cgroup).parts
                and grant.container_cgroup.endswith('/docker-' + grant.container_id + '.scope'),
                "foreign_native_cgroup_or_boot")
        require(type(grant.accepted_monotonic) in (int,float) and math.isfinite(grant.accepted_monotonic)
                and 0 < grant.accepted_monotonic <= grant.keys_prepared_monotonic, 'original_monotonic_budget_missing')

    @staticmethod
    def _run(argv, data, timeout):
        try:
            result = subprocess.run(argv, input=data, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
            require(result.returncode == 0, "native_call_unknown")
            return result.stdout
        except (OSError, subprocess.SubprocessError):
            raise A0Error("native_call_unknown") from None

    def _docker(self, args, *, data=None, timeout=5):
        self.config.docker.read()
        return self.runner([str(self.config.docker.path), "--host", self.config.socket, *args], data, timeout)

    def _association(self, row):
        require(row["worker_kind"] == "a0" and self.grant.deadline_unix == row["deadline_unix"]
                and self.grant.accepted_unix == row["created_at_unix"]
                and row["existing_task_id"] == self.grant.labels.get("friday.rework.assignment")
                and row["admission_hash"] == self.grant.labels.get("friday.rework.plan"), "foreign_native_grant")
        prior = row.get('native')
        require(prior is None or (prior['invocation_id'] == self.grant.invocation_id
                and prior['worker_reference'].startswith('a0:' + self.grant.container_id + ':')),
                'native_invocation_changed')
        return {**row, "native": {"invocation_id": self.grant.invocation_id,
                                  "worker_reference": self.grant.container_id}}

    def inspect(self, row, *, stopping=False):
        self._association(row)
        xs = strict_json(self._docker(["inspect", self.grant.container_id]))
        require(isinstance(xs, list) and len(xs) == 1, "native_identity_unknown")
        obj = xs[0]; c, h, s = obj["Config"], obj["HostConfig"], obj["State"]
        require(obj["Id"] == self.grant.container_id and obj["Name"] == "/" + self.grant.container_name
                and obj["Image"] == c["Image"] == self.config.image
                and {k: v for k, v in (c.get("Labels") or {}).items() if k.startswith("friday.rework.")}
                    == self.grant.labels, "container_owner_or_image_changed")
        require(h.get("NetworkMode") == self.config.network.name and not h.get("Privileged")
                and not h.get("PortBindings") and not h.get("PublishAllPorts") and not h.get("Binds")
                and not h.get("Devices") and not h.get("DeviceRequests") and not h.get("CapAdd")
                and h.get("CapDrop") == ["ALL"] and h.get("SecurityOpt") == ["no-new-privileges"]
                and h.get("PidMode", "") == "" and h.get("IpcMode") in {"", "private"}
                and h.get("RestartPolicy") == {"Name": "no", "MaximumRetryCount": 0}, "native_exposure_changed")
        mounts = obj.get("Mounts", [])
        require(len(mounts) == 2 and len({m.get("Destination") for m in mounts}) == 2,
                "native_mounts_changed")
        for target, source, rw in [("/a0/usr", self.config.state_dir, True), ("/a0/.git", self.config.git_dir, False)]:
            m = next((m for m in mounts if m.get("Destination") == target), {})
            require(m.get("Type") == "bind" and m.get("Source") == str(source)
                    and m.get("RW") is rw and m.get("Propagation") == "rprivate", "native_mounts_changed")
        require(c.get("Entrypoint") == ["/bin/bash"] and c.get("Cmd") == list(self.config.command)
                and c.get("WorkingDir") == "/a0", "native_command_changed")
        require(type(s.get("Running")) is bool and type(s.get("Pid")) is int and s["Pid"] >= 0
                and (s["Running"] or s["Pid"] == 0), "native_state_unknown")
        if not stopping:
            require(h.get("Memory") == h.get("MemorySwap") == 2147483648
                    and h.get("NanoCpus") == 2000000000 and h.get("PidsLimit") == 256,
                    "native_resource_changed")
        return obj

    def _sample(self, obj, *, caps):
        pid = obj["State"]["Pid"]
        line = Path(f"/proc/{pid}/cgroup").read_text().strip()
        require(line.startswith("0::/") and "\n" not in line, "native_cgroup_unknown")
        group = line[3:]
        require(group == self.grant.container_cgroup, "native_cgroup_changed")
        root = Path("/sys/fs/cgroup") / group.lstrip("/")
        if caps:
            q, period = (root / "cpu.max").read_text().split()
            require(q != "max" and int(q) == 2 * int(period)
                    and (root / "memory.max").read_text().strip() == "2147483648"
                    and (root / "memory.swap.max").read_text().strip() == "0"
                    and (root / "pids.max").read_text().strip() == "256", "native_kernel_caps_changed")
        processes = []
        for p in [root, *root.rglob("*")]:
            if p.is_dir():
                for n in (p / "cgroup.procs").read_text().split():
                    try:
                        start = Path(f"/proc/{n}/stat").read_text().rsplit(")", 1)[1].split()[19]
                        processes.append((int(n), start))
                    except FileNotFoundError:
                        pass
        require(processes, "native_descendants_unknown")
        self.samples.append((root, processes))

    def _daemon_caps(self, group):
        require(isinstance(group, str) and group.startswith('/user.slice/')
                and '..' not in Path(group).parts
                and group.endswith('/' + self.config.daemon_unit.path.name), 'daemon_cgroup_changed')
        root = Path('/sys/fs/cgroup') / group.lstrip('/')
        q, period = (root/'cpu.max').read_text().split()
        require(q != 'max' and int(q) == 8*int(period)
                and (root/'memory.max').read_text().strip() == '21474836480'
                and (root/'pids.max').read_text().strip() == '2048', 'daemon_kernel_caps_changed')

    def admit(self, row):
        require(row["stop_intent"] is None and self.clock() < row["deadline_unix"]
                and row["elapsed_seconds"] < row["budget_seconds"], "stopped_or_expired")
        require(self.config.network.name != "none" and self.grant.network_verified is True,
                "local_network_not_admitted")
        # Check actual consumed preset bytes, not a parallel settings dialect.
        for name, expected in local_profile(self.config.network).items():
            from .dsh import _regular
            require(strict_json(_regular(self.config.state_dir/name).read_bytes()) == expected,
                    'effective_local_profile_changed')
        self.config.daemon_unit.read()
        daemon_names = 'ActiveState,InvocationID,MemoryMax,CPUQuotaPerSecUSec,TasksMax,ControlGroup,MainPID'
        result = self.supervisor._command(['show', self.config.daemon_unit.path.name,
                    '--property=' + daemon_names], 3)
        require(result.returncode == 0, 'daemon_observation_unknown')
        pairs = [line.split('=', 1) for line in result.stdout.splitlines()]
        daemon = dict(pairs)
        require(len(daemon) == len(pairs) and set(daemon) == set(daemon_names.split(','))
                and daemon['ActiveState'] == 'active'
                and daemon['InvocationID'] == self.grant.daemon_invocation_id
                and daemon['MemoryMax'] == '21474836480'
                and _duration(daemon['CPUQuotaPerSecUSec']) == 8 and daemon['TasksMax'] == '2048'
                and re.fullmatch('[1-9][0-9]*', daemon['MainPID']), 'daemon_identity_or_caps_changed')
        self._daemon_caps(daemon['ControlGroup'])
        obj = self.inspect(row)
        require(obj["State"]["Running"], "native_not_running")
        unit = self.supervisor.observe(self._association(row))
        require(not unit.quiescent and unit.invocation_id == self.grant.invocation_id,
                "native_unit_changed")
        names = "RuntimeMaxUSec,ActiveEnterTimestampMonotonic,TimeoutStopUSec,ExecStopPost,Restart,MemoryMax,CPUQuotaPerSecUSec,TasksMax"
        result = self.supervisor._command(["show", unit.unit, "--property=" + names], 3)
        require(result.returncode == 0, "native_deadline_unknown")
        pairs = [line.split("=", 1) for line in result.stdout.splitlines()]
        fields = dict(pairs)
        require(len(fields) == len(pairs), 'duplicate_native_property')
        require(set(fields) == set(names.split(",")) and fields.get("Restart") == "no"
                and fields['MemoryMax'] == '268435456' and _duration(fields['CPUQuotaPerSecUSec']) == 1
                and fields['TasksMax'] == '64', "native_deadline_or_helper_caps_unknown")
        remaining = int(fields["ActiveEnterTimestampMonotonic"]) / 1e6 + _duration(fields["RuntimeMaxUSec"]) - self.monotonic()
        started = int(fields['ActiveEnterTimestampMonotonic']) / 1e6
        require(started >= self.grant.accepted_monotonic and started + _duration(fields['RuntimeMaxUSec'])
                + _duration(fields['TimeoutStopUSec']) <= self.grant.accepted_monotonic
                + row['deadline_unix'] - row['created_at_unix'], 'original_native_budget_extended')
        # Native stop plus grace must complete inside the ORIGINAL job deadline.
        require(0 < remaining and remaining + _duration(fields["TimeoutStopUSec"])
                <= row["deadline_unix"] - self.clock(), "native_deadline_not_bounded")
        stop = [str(self.config.docker.path), "--host", self.config.socket, "stop", "--time", "2", self.grant.container_id]
        require("argv[]=" + shlex.join(stop) + " ;" in fields["ExecStopPost"]
                and 'path=' + str(self.config.docker.path) + ' ;' in fields['ExecStopPost']
                and fields["ExecStopPost"].count("argv[]=") == 1
                and "ignore_errors=no" in fields["ExecStopPost"], "native_cleanup_changed")
        # Same-boot monotonic time avoids wall-clock formatting/rounding. The
        # trusted owner must reconstruct this grant after reboot, never reuse it.
        require(0 < self.grant.keys_prepared_monotonic
                <= int(fields["ActiveEnterTimestampMonotonic"]) / 1e6,
                "keys_not_prepared_before_ui")
        self.native_left = remaining
        self._sample(obj, caps=True)
        return unit

    def _exec(self, row, script, payload, timeout):
        self.admit(row)
        timeout = min(timeout, self.native_left - 1, row["deadline_unix"] - self.clock() - 5)
        require(timeout > 1, "budget_exhausted")
        if "timeout" in payload:
            payload = {**payload, "timeout": min(payload["timeout"], timeout - .5)}
        data = json.dumps(payload, allow_nan=False).encode()
        try:
            return self._docker(["exec", "-i", "--workdir=/a0", self.grant.container_id,
                                 self.config.python, "-B", "-c", script], data=data, timeout=timeout)
        except BaseException:
            raise A0Error("native_call_unknown") from None

    def request(self, row, method, path, payload, timeout, max_bytes):
        value = strict_json(self._exec(row, API_SCRIPT, {"method": method, "path": path,
                            "payload": payload, "timeout": timeout, "max_bytes": max_bytes}, timeout + 1))
        require(isinstance(value, dict) and value.get("ok") is True and set(value) == {"ok", "body"}, "api_outcome_unknown")
        return strict_json(decode_file(value["body"], max_bytes))

    def file(self, row, path, limit, timeout):
        require(path.startswith("/a0/") and "\x00" not in path, "unsafe_native_file")
        return strict_json(self._exec(row, file_script(), {"relative": path[4:], "limit": limit}, timeout))

    def stop(self, row):
        errors = []
        repeated = self.stop_requested
        self.stop_requested = True
        try:
            obj = self.inspect(row, stopping=True)
            if obj["State"]["Running"]:
                require(not repeated, 'stop_requires_reconciliation')
                try: self._sample(obj, caps=False)
                except BaseException: errors.append("descendants_not_observed")
                self._docker(["stop", "--time", "2", self.grant.container_id], timeout=8)
        except BaseException:
            errors.append("container_stop_unknown")
        # Auxiliary I/O, caps drift or Docker error never prevents native stop.
        try:
            unit = (self.supervisor.observe(self._association(row)) if repeated
                    else self.supervisor.stop(self._association(row)))
        except BaseException:
            unit = None; errors.append("native_stop_unknown")
        try:
            obj = self.inspect(row, stopping=True)
            require(not obj["State"]["Running"] and obj["State"]["Pid"] == 0, "container_still_running")
            original = (Path('/sys/fs/cgroup') / self.grant.container_cgroup.lstrip('/'), [])
            for root, processes in [original, *self.samples]:
                if root.exists():
                    require("populated 0" in (root / "cgroup.events").read_text()
                            and all(not p.read_text().strip() for p in root.rglob("cgroup.procs")), "cgroup_still_populated")
                for pid, start in processes:
                    try: current = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
                    except FileNotFoundError: continue
                    require(current != start, "descendant_still_running")
            require(unit is not None and unit.quiescent and not errors, "STOP_UNCONFIRMED")
        except BaseException:
            raise A0Error("STOP_UNCONFIRMED") from None
        return unit
