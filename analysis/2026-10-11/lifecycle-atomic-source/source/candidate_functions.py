"""Exact source function excerpts for analysis; no installed/native/profile bindings.

Whole guard compatibility remains NOT_RUN. Namespace dependencies are intentionally
unbound: these excerpts are not a complete installed guard or a runtime grant.
"""
from __future__ import annotations
from contextlib import contextmanager
import os,json,resource,tempfile,fcntl,stat
from pathlib import Path
from typing import Any,Iterator

def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    mode = path.stat().st_mode
    if path.stat().st_uid != os.getuid() or mode & 0o077:
        raise RuntimeError(f"unsafe lifecycle directory: {path}")


def _write_all(fd: int, body: bytes) -> None:
    view = memoryview(body)
    offset = 0
    while offset < len(view):
        try:
            written = os.write(fd, view[offset:])
        except InterruptedError:
            continue
        if type(written) is not int or written <= 0 or written > len(view) - offset:
            raise RuntimeError("lifecycle write did not make valid progress")
        offset += written


def _check_file_size_bound(length: int, *, offset: int = 0) -> None:
    limit, _hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    if limit != resource.RLIM_INFINITY and offset + length > limit:
        raise RuntimeError("lifecycle write exceeds inherited file size limit")


def _atomic_json(path: Path, value: object) -> None:
    body = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
    _check_file_size_bound(len(body))
    _secure_dir(path.parent)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, body)
        if os.fstat(fd).st_size != len(body):
            raise RuntimeError("lifecycle temporary file size mismatch")
        os.fsync(fd)
        closing, fd = fd, -1
        os.close(closing)
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _load_registry(profile: str) -> dict[str, Any]:
    spec = profile_spec(profile)
    path = STATE / profile / "registry.json"
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except FileNotFoundError:
        return empty_registry(profile, "unix://" + str(spec["endpoint"]), spec["root"])
    if not isinstance(value, dict) or value.get("profile") != profile or value.get("version") != 1:
        raise RuntimeError(f"invalid lifecycle registry: {path}")
    if value.get("designated_root_thread_id") != spec["root"]:
        raise RuntimeError("registry root binding mismatch")
    value.setdefault("pending_continuations", {})
    return value


def _event_path(profile: str) -> Path:
    return STATE / profile / "events.jsonl"


def _append_event(profile: str, event: dict[str, Any]) -> None:
    body = (json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n").encode("ascii")
    path = _event_path(profile)
    _secure_dir(path.parent)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _check_file_size_bound(len(body), offset=os.fstat(fd).st_size)
        _write_all(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def registry_txn(profile: str, *, write: bool = True) -> Iterator[dict[str, Any]]:
    directory = STATE / profile
    if write:
        _secure_dir(directory)
    else:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError(f"unsafe lifecycle directory: {directory}")
        if not (directory / "registry.json").is_file():
            raise RuntimeError("read-only lifecycle registry missing")
    lock_path = directory / "registry.lock"
    flags = os.O_CREAT | os.O_RDWR if write else os.O_RDONLY
    fd = os.open(lock_path, flags | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        registry = _load_registry(profile)
        yield registry
        if write:
            registry["updated_at"] = utc_now()
            _atomic_json(directory / "registry.json", registry)
    finally:
        os.close(fd)


def command_peer_check(args: argparse.Namespace) -> int:
    with registry_txn(args.profile, write=False) as registry:
        row = peer_state(registry, args.assignment, args.generation)
        probe = json.loads(json.dumps(registry))
        try:
            register_peer(probe, assignment_id=args.assignment, generation=args.generation,
                          kind="PREFLIGHT", event_id=args.event, action=args.action)
            blocked = False
            reason = None
        except LifecycleError as exc:
            blocked = True
            reason = str(exc)
    print(json.dumps({"profile": args.profile, "assignment": assignment_key(args.assignment, args.generation),
                      "state": row.get("state") if row else None, "blocked": blocked,
                      "reason": reason}))
    return 2 if blocked else 0
