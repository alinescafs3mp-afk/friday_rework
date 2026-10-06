#!/usr/bin/env python3
"""Fail closed before running the installed upstream observer; never set up mounts."""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import runpy
import stat
import sys
import uuid

ROOT = Path("/usr/local/lib/friday-upstream-check-system")
STATE = Path("/var/lib/friday-upstream-check-system")
CONTROL = Path("/var/lib/friday-upstream-check-system-control")


class BoundaryError(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise BoundaryError(reason)


def readonly(path):
    require(os.statvfs(path).f_flag & os.ST_RDONLY, "required_mount_not_readonly")


def denied_write(path):
    """Open only: no creation, truncation, or write, even on a failed boundary."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        require(exc.errno == errno.EROFS, "outside_write_not_denied_by_readonly_mount")
        return
    os.close(fd)
    raise BoundaryError("outside_write_allowed")


def private_write():
    """Bounded positive control, using the same private cwd as the report writer."""
    directory = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = ".boundary-" + uuid.uuid4().hex
    try:
        s = os.fstat(directory)
        require(s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o700,
                "unsafe_state_directory")
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                     dir_fd=directory)
        try:
            s = os.fstat(fd)
            require(s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o600
                    and s.st_nlink == 1, "unsafe_control_file")
            data = b"friday-boundary-check\n"
            require(os.write(fd, data) == len(data), "short_control_write")
            os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            require(os.read(fd, len(data) + 1) == data, "control_readback_failed")
        finally:
            os.close(fd)
            os.unlink(name, dir_fd=directory)
    finally:
        os.close(directory)


def check_boundary():
    require(os.getuid() == os.geteuid() != 0, "privileged_identity")
    status = dict(line.split(":", 1) for line in
                  Path("/proc/self/status").read_text().splitlines() if ":" in line)
    require(status.get("NoNewPrivs", "").strip() == "1", "no_new_privileges_missing")
    for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
        require(key in status and int(status[key].strip(), 16) == 0,
                "capabilities_not_empty")
    require(Path.cwd() == STATE and not STATE.is_symlink(), "unexpected_state_directory")
    require(not os.statvfs(".").f_flag & os.ST_RDONLY, "state_mount_readonly")
    for path in (Path("/"), Path("/home"), Path("/home/jericho"), ROOT):
        readonly(path)
    for path in (ROOT / "scripts/check_upstream_system.py", ROOT / "scripts/check_upstream.py",
                 ROOT / "sources.lock.json"):
        for component in (path, *path.parents):
            s = component.lstat()
            require(not stat.S_ISLNK(s.st_mode) and s.st_uid == 0
                    and not s.st_mode & 0o022, "unsafe_installed_source")
        require(stat.S_ISREG(path.stat().st_mode), "source_not_regular")
        readonly(path)
    # Owner-writable by DAC on the host, outside the StateDirectory exception.
    # A root-owned 0644 source file could instead fail for an unrelated DAC reason.
    control = CONTROL.lstat()
    require(stat.S_ISREG(control.st_mode) and control.st_uid == os.geteuid()
            and stat.S_IMODE(control.st_mode) == 0o600 and control.st_nlink == 1,
            "unsafe_outside_control")
    readonly(CONTROL)
    denied_write(CONTROL)
    private_write()
    return {"sandbox_preflight": "ok", "uid": os.geteuid(),
            "outside_write": "EROFS", "state_directory": str(STATE)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="finite offline boundary check; no API calls")
    args = parser.parse_args()
    try:
        result = check_boundary()
    except (BoundaryError, OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, BoundaryError) else "boundary_inspection_failed"
        print("sandbox_boundary_refused:" + reason, file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True), flush=True)
    if args.verify_only:
        return 0
    # The checked process continues in the same namespace. No ExecStartPre gap.
    sys.argv = [str(ROOT / "scripts/check_upstream.py"), "--report-dir", "."]
    runpy.run_path(sys.argv[0], run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
