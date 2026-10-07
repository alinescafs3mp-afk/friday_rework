"""Host-only, portable A0 deployment inputs. Rendering is never admission.

The intact image, existing Docker daemon and NativeSupervisor remain owners of
execution. No service, network, key source or container is created here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Callable

from .dsh import PinnedFile, _private, _regular, _sync


class A0Error(RuntimeError):
    """Categorical errors only; native errors and credentials stay private."""


def require(condition, code):
    if not condition:
        raise A0Error(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class LocalNetwork:
    # A pre-existing bridge plus separately verified deny-by-default egress.
    # Docker --network alone does NOT enforce the endpoint allowlist.
    name: str = "none"
    endpoints: tuple[str, ...] = ()
    policy: PinnedFile | None = None

    def checked(self):
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", self.name)
                and self.name not in {"host", "bridge", "default"}, "unsafe_network")
        if self.name == "none":
            require(not self.endpoints and self.policy is None, "network_none_mismatch")
        else:
            require(len(self.endpoints) == 2 and len(set(self.endpoints)) == 2
                    and isinstance(self.policy, PinnedFile), "local_policy_required")
            from urllib.parse import urlsplit
            for endpoint in self.endpoints:
                u = urlsplit(endpoint)
                try:
                    ip = ipaddress.ip_address(u.hostname or "")
                    valid = (ip.is_private and not ip.is_loopback and not ip.is_link_local
                             and u.scheme == "http" and u.port in {8001, 8002}
                             and u.path == "/v1" and not u.query and not u.fragment
                             and not u.username and not u.password)
                except ValueError:
                    valid = False
                require(valid, "nonlocal_endpoint")
            require({urlsplit(x).port for x in self.endpoints} == {8001, 8002}, 'local_slots_required')
            self.policy.read()
        return self

    def arguments(self):
        self.checked()
        return ["--network=" + self.name]


@dataclass(frozen=True)
class A0Deployment:
    docker: PinnedFile
    daemon_unit: PinnedFile
    socket: str
    image: str
    state_dir: Path
    git_dir: Path
    # Exact reviewed intact startup command, not a model/tool argument.
    command: tuple[str, ...]
    network: LocalNetwork = field(default_factory=LocalNetwork)
    python: str = "/opt/venv-a0/bin/python"
    port: int = 5000

    def checked(self):
        self.docker.read(); self.daemon_unit.read(); self.network.checked()
        require(self.socket.startswith("unix:///") and not any(
            c in self.socket for c in "\n\r\x00 ,"), "unsafe_daemon_socket")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", self.image), "unpinned_image")
        _private(self.state_dir)
        require(self.git_dir.is_absolute() and self.git_dir.resolve() == self.git_dir
                and self.git_dir.is_dir(), "unsafe_git_mount")
        require(not any(c in str(p) for p in (self.state_dir, self.git_dir, self.docker.path, self.daemon_unit.path)
                        for c in '\n\r\x00,'), 'unsafe_deployment_path')
        require(isinstance(self.command, tuple) and len(self.command) == 2
                and self.command[0] == "-ceu" and isinstance(self.command[1], str)
                and 0 < len(self.command[1]) < 2048 and "\x00" not in self.command[1],
                "unchecked_start_command")
        require(self.python == "/opt/venv-a0/bin/python" and self.port == 5000,
                "unreviewed_native_api")
        return self

    def container_arguments(self, *, name, labels):
        """PREPARED argv for the existing launcher; no execution or grant."""
        self.checked()
        require(re.fullmatch(r"frw-a0-[0-9a-f]{32}", name), "invalid_container_name")
        require(set(labels) == {"friday.rework.owner", "friday.rework.assignment",
                               "friday.rework.generation", "friday.rework.plan"},
                "invalid_native_labels")
        args = [str(self.docker.path), "--host", self.socket, "create", "--name", name,
                "--pull=never", *self.network.arguments(), "--restart=no", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--memory=2147483648",
                "--memory-swap=2147483648", "--cpus=2", "--pids-limit=256",
                "--stop-timeout=2", "--log-driver=none", "--ulimit=nofile=65535:65535"]
        for key, value in sorted(labels.items()):
            require(isinstance(value, str) and value and not any(c in value for c in "\n\r\x00"),
                    "invalid_native_labels")
            args += ["--label", key + "=" + value]
        args += ["--mount", f"type=bind,src={self.state_dir},dst=/a0/usr",
                 "--mount", f"type=bind,src={self.git_dir},dst=/a0/.git,readonly,bind-propagation=rprivate",
                 "--env=HF_HUB_OFFLINE=1", "--env=TRANSFORMERS_OFFLINE=1", "--workdir=/a0",
                 "--entrypoint=/bin/bash", self.image, *self.command]
        return args


def local_profile(network: LocalNetwork):
    """Actual intact plugin collection schema; same accepted TEST capacities.

    Returns data only. Parent must retain the effective no-project/agent0 scope
    and independently prove startup/local routes before any model admission.
    """
    network.checked()
    require(network.name != 'none', 'local_profile_needs_explicit_routes')
    from urllib.parse import urlsplit
    endpoints = {urlsplit(x).port: x for x in network.endpoints}
    chat = dict(provider='openai', name='dispatcher', api_base=endpoints[8001], ctx_length=40960,
                ctx_history=.7, vision=False, rl_requests=0, rl_input=0, rl_output=0,
                kwargs={'max_tokens':4096,'timeout':60,'a0_api_mode':'chat'})
    utility = dict(chat); utility.pop('ctx_history'); utility['ctx_input'] = .7
    return {'plugins/_model_config/presets.yaml': [{'name':'Default','chat':chat,'utility':utility,
                'embedding': {'provider':'other','name':'qwen3-embedding-0.6b','api_base':endpoints[8002],
                              'kwargs':{'timeout':30},'rl_requests':0,'rl_input':0}}],
            'plugins/_model_config/config.json': {'model_preset':'Default'},
            'plugins/_code_execution/config.json': {'ssh_enabled':'false'},
            'settings.json': {'agent_profile':'agent0','workdir_path':'/a0/usr/workdir',
                              'uvicorn_access_logs_enabled':False}}


KEY_REFERENCES = {"API_KEY_OPENAI": "FRIDAY_LLM_API_KEY",
                  "API_KEY_OTHER": "FRIDAY_EMBEDDINGS_API_KEY"}


def _replace_env(path, before, content):
    """Existing owned 0600 regular file; atomic, mode-preserving replacement."""
    path = _regular(path)
    st = path.stat()
    require(stat.S_IMODE(st.st_mode) == 0o600 and st.st_uid == os.getuid(), "unsafe_key_file")
    require(path.read_bytes() == before, "key_file_changed")
    fd, temp = tempfile.mkstemp(prefix=".a0-keys-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        require(path.stat().st_ino == st.st_ino and path.read_bytes() == before, "key_file_changed")
        os.replace(temp, path); _sync(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@dataclass(frozen=True)
class KeyMaterial:
    path: Path
    # In-memory only, never serialize/hash/log this object or its values.
    introduced: tuple[bytes, ...] = field(repr=False)
    prepared_monotonic: float = 0

    def ready(self):
        before = _regular(self.path).read_bytes()
        require(stat.S_IMODE(self.path.stat().st_mode) == 0o600 and self.path.stat().st_uid == os.getuid(),
                'unsafe_key_file')
        require(len(self.introduced) == 2 and all(before.splitlines(keepends=True).count(line) == 1
                for line in self.introduced), 'introduced_key_changed')

    def remove(self, *, cessation_confirmed):
        require(cessation_confirmed is True, "keys_require_confirmed_cessation")
        before = _regular(self.path).read_bytes()
        require(stat.S_IMODE(self.path.stat().st_mode) == 0o600 and self.path.stat().st_uid == os.getuid(),
                'unsafe_key_file')
        lines = before.splitlines(keepends=True)
        names = [line.split(b"=", 1)[0] for line in self.introduced]
        if not any(re.search(rb"(?m)^\s*(?:export\s+)?" + name + rb"\s*=", before) for name in names):
            return  # Already removed after the same confirmed cessation.
        for line in self.introduced:
            require(lines.count(line) == 1, "introduced_key_changed")
            lines.remove(line)
        _replace_env(self.path, before, b"".join(lines))


def prepare_keys(state_dir: Path, resolve: Callable[[str], str]):
    """Call before the native launcher starts UI, under its existing owner.

    A0 run_ui/initialize load usr/.env. No key value enters Docker Env, argv,
    receipt or body. Only two previously absent fields are introduced.
    """
    _private(state_dir)
    path = state_dir / ".env"
    before = _regular(path).read_bytes()
    require(not before or before.endswith(b"\n"), "noncanonical_key_file")
    for name in KEY_REFERENCES:
        require(not re.search(rb"(?m)^\s*(?:export\s+)?" + name.encode() + rb"\s*=", before),
                "existing_key_owned_elsewhere")
    lines = []
    for name, reference in KEY_REFERENCES.items():
        value = resolve(reference)
        require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:/+=@-]{1,4096}", value),
                "invalid_scoped_key")
        lines.append(name.encode() + b"=" + value.encode() + b"\n")
    _replace_env(path, before, before + b"".join(lines))
    return KeyMaterial(path, tuple(lines), time.monotonic())
