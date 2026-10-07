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

from .dsh import PinnedFile, _private, _regular, _sync, _directory
from .a0_profile import checked_profile, endpoint_urls, legacy_profile, local_endpoint, profile_templates, ProfileError


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
    deployment: dict | None = None

    def checked(self):
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", self.name)
                and self.name not in {"host", "bridge", "default"}, "unsafe_network")
        if self.name == "none":
            require(not self.endpoints and self.policy is None and self.deployment is None, "network_none_mismatch")
        else:
            require(isinstance(self.endpoints, tuple) and 2 <= len(self.endpoints) <= 3
                    and len(set(self.endpoints)) == len(self.endpoints)
                    and isinstance(self.policy, PinnedFile), "local_policy_required")
            try:
                for endpoint in self.endpoints:
                    local_endpoint(endpoint)
                if self.deployment is None:
                    from urllib.parse import urlsplit
                    require(len(self.endpoints) == 2
                            and {urlsplit(x).port for x in self.endpoints} == {8001, 8002}, 'local_slots_required')
                    require(all(x.startswith('http://') for x in self.endpoints), 'local_slots_required')
                else:
                    profile = checked_profile(self.deployment)
                    require(set(self.endpoints) == set(endpoint_urls(profile)), 'local_profile_routes_mismatch')
            except ProfileError as exc:
                raise A0Error(str(exc)) from None
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
    web: dict | None = None

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
        if self.web is not None:
            from .a0_web import checked_web
            checked_web(self.web)
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
        if self.web is not None:
            args += ['--mount',f'type=bind,src={self.state_dir}/web/settings.yml,dst=/etc/searxng/settings.yml,readonly,bind-propagation=rprivate']
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
    if network.deployment is None:
        endpoints = {urlsplit(x).port: x for x in network.endpoints}
        profile = legacy_profile(endpoints[8001], endpoints[8002])
    else:
        profile = network.deployment
    try:
        return profile_templates(profile)
    except ProfileError as exc:
        raise A0Error(str(exc)) from None


KEY_REFERENCES = {"API_KEY_OPENAI": "FRIDAY_LLM_API_KEY",
                  "API_KEY_OTHER": "FRIDAY_EMBEDDINGS_API_KEY"}


def key_assignments(content):
    """Use the same parser as A0's python-dotenv, including quoted/export keys.

    Values stay private. A syntax error cannot hide an overriding assignment.
    """
    import io
    from dotenv.parser import parse_stream
    try:
        bindings = list(parse_stream(io.StringIO(content.decode("utf-8"))))
    except (ValueError, UnicodeError):
        raise A0Error("invalid_key_file") from None
    require(not any(v.error for v in bindings), "invalid_key_file")
    return {name: [v.value for v in bindings if v.key == name] for name in KEY_REFERENCES}


def _key_bytes(path):
    path = _regular(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
                and before.st_size <= 1024**2, "unsafe_key_file")
        chunks, size = [], 0
        while part := os.read(fd, min(65536, 1024**2 - size + 1)):
            size += len(part); require(size <= 1024**2, "unsafe_key_file"); chunks.append(part)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                              s.st_ctime_ns, s.st_nlink, s.st_mode)
        require(identity(before) == identity(os.fstat(fd)) == identity(path.stat(follow_symlinks=False)),
                "key_file_changed")
        return b"".join(chunks)
    finally:
        os.close(fd)


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

    def admitted(self):
        """Original admitted values, in memory/stdin only; never retain/log."""
        require(len(self.introduced) == 2, "introduced_key_changed")
        values = key_assignments(b"".join(self.introduced))
        require(all(len(values[name]) == 1 and isinstance(values[name][0], str)
                    and re.fullmatch(r"[A-Za-z0-9._:/+=@-]{1,4096}", values[name][0])
                    for name in KEY_REFERENCES), "introduced_key_changed")
        return {name: values[name][0] for name in KEY_REFERENCES}

    def ready(self):
        before = _key_bytes(self.path)
        expected = self.admitted()
        require(key_assignments(before) == {name: [value] for name, value in expected.items()}
                and all(before.splitlines(keepends=True).count(line) == 1 for line in self.introduced),
                'introduced_key_changed')

    def remove(self, *, cessation_confirmed):
        require(cessation_confirmed is True, "keys_require_confirmed_cessation")
        before = _key_bytes(self.path)
        lines = before.splitlines(keepends=True)
        expected = self.admitted()
        assignments = key_assignments(before)
        if all(not assignments[name] for name in expected):
            return  # Already removed after the same confirmed cessation.
        require(assignments == {name: [value] for name, value in expected.items()}, "introduced_key_changed")
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
    before = _key_bytes(path)
    require(not before or before.endswith(b"\n"), "noncanonical_key_file")
    require(all(not values for values in key_assignments(before).values()), "existing_key_owned_elsewhere")
    lines = []
    for name, reference in KEY_REFERENCES.items():
        value = resolve(reference)
        require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:/+=@-]{1,4096}", value),
                "invalid_scoped_key")
        lines.append(name.encode() + b"=" + value.encode() + b"\n")
    _replace_env(path, before, before + b"".join(lines))
    return KeyMaterial(path, tuple(lines), time.monotonic())


class WebKeyMaterial:
    """Existing job keys plus one private native-service secret; never serialize."""
    def __init__(self, base, path, content):
        self.base, self.path, self.secret_path = base, base.path, path
        self.content = content
        self.prepared_monotonic = base.prepared_monotonic

    def admitted(self):
        return self.base.admitted()

    def ready(self):
        self.base.ready()
        require(_key_bytes(self.secret_path) == self.content, 'native_web_secret_changed')

    def remove(self, *, cessation_confirmed):
        require(cessation_confirmed is True, 'keys_require_confirmed_cessation')
        if self.secret_path.exists():
            before = _key_bytes(self.secret_path)
            require(before in (b'',self.content), 'native_web_secret_changed')
            if before: _replace_env(self.secret_path, self.content, b'')
        self.base.remove(cessation_confirmed=True)


def prepare_web_keys(base, state_dir, resolve):
    """Previously absent job-owned secret. No source/config/argv/receipt value."""
    base.ready()
    value = resolve('SEARXNG_SECRET')
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{32,256}',value)
            and value.lower() not in {'ultrasecretkey','changeme','change_me','default','secret'},
            'native_web_secret_missing_or_default')
    path = state_dir / 'web/secret.env'
    _directory(path.parent)
    require(path.parent.stat().st_uid == os.getuid() and not path.parent.stat().st_mode & 0o022,
            'unsafe_web_secret_root')
    content = b'SEARXNG_SECRET=' + value.encode() + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        _sync(path.parent)
    except BaseException:
        # Own freshly created file only; no native execution can have started.
        path.unlink(missing_ok=True)
        raise
    return WebKeyMaterial(base,path,content)
