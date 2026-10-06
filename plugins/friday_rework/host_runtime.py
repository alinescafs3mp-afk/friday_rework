"""Explicit operator configuration -> exact accepted DSH adapter.

No deployment defaults, environment routing, dynamic imports or model grants.
An operator's pinned readiness receipt binds this config to actual reviewed
runtime evidence. This code cannot manufacture that evidence or enable A0.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .adapters.dsh import DshAdapter, DshHostConfig, PinnedFile
from .controller import WorkerBinding
from .supervision import NativeSupervisor


class HostUnavailable(RuntimeError):
    pass


def _path(value):
    if (not isinstance(value, str) or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value)
            or str(Path(value)) != value or ".." in Path(value).parts or value == "/"):
        raise HostUnavailable("invalid_runtime_path")
    return value


def _pin(value):
    if (not isinstance(value, dict) or set(value) != {"path", "sha256"}
            or not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise HostUnavailable("invalid_runtime_pin")
    return PinnedFile(Path(_path(value["path"])), value["sha256"])


def validate_runtime(value):
    required = {"enabled", "runtime_profile", "runtime_home", "workspace_root", "staging_root", "cache_roots",
                "budget_seconds", "max_file_bytes", "max_total_bytes", "dsh", "runtime_receipt"}
    if (not isinstance(value, dict) or set(value) != required or value["enabled"] is not True
            or not isinstance(value["runtime_profile"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value["runtime_profile"])):
        raise HostUnavailable("worker_not_configured")
    for key in ("runtime_home", "workspace_root", "staging_root"):
        _path(value[key])
    if not isinstance(value["cache_roots"], list) or not value["cache_roots"]:
        raise HostUnavailable("missing_cache_roots")
    for root in value["cache_roots"]:
        _path(root)
    for key, ceiling in (("budget_seconds", 86400), ("max_file_bytes", 16*1024**2),
                         ("max_total_bytes", 64*16*1024**2)):
        if type(value[key]) is not int or not 0 < value[key] <= ceiling:
            raise HostUnavailable("invalid_runtime_limits")
    dsh = value["dsh"]
    required_dsh = {"payload_root", "toolchain_root", "node", "cli", "patch", "native_files", "key_name",
                    "profile", "memory_bytes", "cpu_percent", "tasks", "shutdown_seconds", "tmp_bytes"}
    if not isinstance(dsh, dict) or set(dsh) != required_dsh or dsh["profile"] != "headless":
        raise HostUnavailable("invalid_dsh_config")
    for key in ("payload_root", "toolchain_root"):
        _path(dsh[key])
    for key in ("node", "cli", "patch"):
        _pin(dsh[key])
    if not isinstance(dsh["native_files"], list) or not dsh["native_files"]:
        raise HostUnavailable("missing_native_pins")
    for pin in dsh["native_files"]:
        _pin(pin)
    for key, maximum in (("memory_bytes", 2*1024**3), ("cpu_percent", 400), ("tasks", 64),
                         ("shutdown_seconds", 2), ("tmp_bytes", 64*1024**2)):
        if type(dsh[key]) is not int or not 0 < dsh[key] <= maximum:
            raise HostUnavailable("invalid_resource_grant")
    if not isinstance(dsh["key_name"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", dsh["key_name"]):
        raise HostUnavailable("invalid_key_reference")
    _pin(value["runtime_receipt"])
    return copy.deepcopy(value)


def private_directory(path):
    path = Path(path)
    info = path.stat()
    if (not path.is_absolute() or path.resolve() != path or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise HostUnavailable("nonprivate_runtime_root")
    return path


def check_runtime(value, associations):
    from .host_record import digest
    from hermes_constants import get_hermes_home
    config = validate_runtime(value)
    if Path(config["runtime_home"]) != get_hermes_home():
        raise HostUnavailable("foreign_runtime_home")
    workspace = private_directory(config["workspace_root"])
    staging = private_directory(config["staging_root"])
    # No worker writable mount contains the store or staged originals.
    protected = [staging, Path(associations.state.data_dir),
                 Path(config["dsh"]["payload_root"]), Path(config["dsh"]["toolchain_root"])]
    if any(p.is_relative_to(workspace) or workspace.is_relative_to(p) for p in protected):
        raise HostUnavailable("overlapping_runtime_roots")
    for root in config["cache_roots"]:
        p = Path(root)
        if not p.is_dir() or p.resolve() != p:
            raise HostUnavailable("unsafe_cache_root")
    dsh = config["dsh"]
    for pin in (dsh["node"], dsh["cli"], dsh["patch"], *dsh["native_files"]):
        _pin(pin).read()
    receipt = json.loads(_pin(config["runtime_receipt"]).read())
    adapter_hash = hashlib.sha256(Path(__file__).with_name("adapters").joinpath("dsh.py").read_bytes()).hexdigest()
    if (not isinstance(receipt, dict) or set(receipt) != {"schema", "ready", "runtime_sha256", "adapter_sha256", "evidence"}
            or receipt["schema"] != "friday-rework.dsh-runtime.v1" or receipt["ready"] is not True
            or receipt["adapter_sha256"] != adapter_hash
            or receipt["runtime_sha256"] != digest({k: v for k, v in config.items() if k != "runtime_receipt"})
            or not isinstance(receipt["evidence"], list) or not receipt["evidence"]):
        raise HostUnavailable("runtime_not_verified")
    for pin in receipt["evidence"]:
        _pin(pin).read()
    return config


def dsh_binding(value, associations):
    """Concrete config factory; recovery preserves retained config and budgets.

    Stop does not re-read readiness or launch pins. DSH's own stop and emergency
    native supervisor remain authoritative when those launch files drift.
    """
    config = validate_runtime(value)
    dsh = config["dsh"]
    def environment():
        from agent.secret_scope import current_secret_scope, current_secret_scope_home
        from gateway.platforms._shared import get_scoped_secret
        from hermes_constants import get_hermes_home
        scope = current_secret_scope()
        if (scope is None or current_secret_scope_home() != config["runtime_home"]
                or get_hermes_home() != Path(config["runtime_home"]) or dsh["key_name"] not in scope):
            raise HostUnavailable("runtime_key_unavailable")
        value = get_scoped_secret(dsh["key_name"])
        if (not isinstance(value, str) or not value or "\x00" in value
                or value != scope[dsh["key_name"]]):
            raise HostUnavailable("runtime_key_unavailable")
        return {dsh["key_name"]: value}
    supervisor = NativeSupervisor()
    native = DshHostConfig(
        workspace_root=Path(config["workspace_root"]), payload_root=Path(dsh["payload_root"]),
        toolchain_root=Path(dsh["toolchain_root"]), node=_pin(dsh["node"]), cli=_pin(dsh["cli"]),
        patch=_pin(dsh["patch"]), native_files=tuple(_pin(p) for p in dsh["native_files"]),
        environment=environment, key_name=dsh["key_name"],
        current_association=lambda row: associations.get(row["existing_task_id"], row["owner"]),
        **{k: dsh[k] for k in ("profile", "memory_bytes", "cpu_percent", "tasks", "shutdown_seconds", "tmp_bytes")})
    return WorkerBinding(DshAdapter(native, supervisor=supervisor, clock=associations.clock), supervisor.stop)
