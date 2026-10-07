"""Finite installer process custody using the OS bubblewrap PID namespace.

This wraps each complete preparer/PM/build family, including detached sessions.
No process discovery, service manager, weaker fallback or background monitor.
"""
from __future__ import annotations
import hashlib
import math
import os
from pathlib import Path
import stat
import time


class Budget:
    def __init__(self, seconds, *, started=None, deadline=None):
        start = time.monotonic() if started is None else started
        if type(seconds) is not int or not 30 <= seconds <= 7200:
            raise ValueError('finite_install_budget_required')
        self.deadline = start + seconds if deadline is None else deadline
        if not math.isfinite(self.deadline) or self.deadline > start + seconds:
            raise ValueError('original_install_deadline_required')
        self.check()

    def check(self, *, reserve=0):
        remaining = self.deadline - time.monotonic() - reserve
        if remaining <= 0:
            raise ValueError('original_install_budget_exhausted')
        return remaining

    def call(self, function, *args, **kwargs):
        self.check()
        result = function(*args, **kwargs)
        self.check()
        return result


def checked_binary(pin):
    if not isinstance(pin, dict) or set(pin) != {'path', 'sha256'} or pin['path'] != '/usr/bin/bwrap':
        raise ValueError('explicit_system_bubblewrap_pin_required')
    path = Path(pin['path'])
    if path.resolve() != path:
        raise ValueError('system_bubblewrap_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_mode & 0o022:
            raise ValueError('protected_system_bubblewrap_required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(4 * 1024**2 + 1)
        after = os.fstat(fd)
        if any(getattr(before, key) != getattr(after, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')) or len(data) > 4 * 1024**2 or hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise ValueError('system_bubblewrap_pin_changed')
    finally:
        os.close(fd)
    return str(path)


def argv(binary, command):
    # Keep current installation filesystem/network semantics. This boundary
    # supplies process lifetime custody, not a new filesystem or network grant.
    return [binary, '--unshare-pid', '--die-with-parent', '--new-session',
            '--bind', '/', '/', '--proc', '/proc', '--', *command]


class Containment:
    def __init__(self, pin, budget, env):
        self.pin, self.budget, self.env = pin, budget, env
        self.binary = budget.call(checked_binary, pin)

    def run(self, command, cwd, *, timeout=1800):
        from scripts.dsh_prepare import run
        self.budget.call(checked_binary, self.pin)
        # Reserve cleanup *inside* the original deadline; no fresh grace clock.
        limit = min(timeout, self.budget.check(reserve=1))
        result = run(argv(self.binary, command), cwd, timeout=limit, env=self.env,
                     deadline=self.budget.deadline)
        self.budget.check()
        return result

    def probe(self, python, cwd):
        outer = os.readlink('/proc/self/ns/pid')
        code = ('import os; assert os.readlink("/proc/self/ns/pid") != ' + repr(outer)
                + '; print("FRIDAY_PID_NAMESPACE_OK")')
        result = self.run([python, '-B', '-c', code], cwd, timeout=5)[0]
        if result != 'FRIDAY_PID_NAMESPACE_OK':
            raise ValueError('required_pid_namespace_unavailable')
