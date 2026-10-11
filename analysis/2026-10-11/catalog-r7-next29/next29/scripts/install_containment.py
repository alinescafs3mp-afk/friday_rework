"""Finite installer process custody using the OS bubblewrap PID namespace.

This wraps each complete preparer/PM/build family, including detached sessions.
No process discovery, service manager, weaker fallback or background monitor.
"""
from __future__ import annotations
import hashlib
import json
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


def argv(binary, command, *, read_only=False):
    # Keep current installation filesystem/network semantics. This boundary
    # supplies process lifetime custody, not a new filesystem or network grant.
    # The finite command is namespace PID 1. Bubblewrap therefore waits for
    # namespace-init exit, after the kernel has drained its descendants, rather
    # than returning the application-status event while its reaper still exits.
    if type(read_only) is not bool:
        raise ValueError('explicit_read_only_boolean_required')
    # Mount protection belongs to this same native boundary. Nesting another
    # bwrap would request another user namespace and can be refused by the OS.
    return [binary, '--unshare-pid', '--die-with-parent', '--new-session', '--as-pid-1',
            '--ro-bind' if read_only else '--bind', '/', '/',
            '--dev', '/dev', '--proc', '/proc', '--', *command]


def namespace_exit(data, observation):
    """Only bwrap's monitor owns this pipe; sandbox commands never inherit it."""
    try:
        if (type(data) is not bytes or len(data) > 4096
                or type(observation) is not dict
                or type(observation.get('returncode')) is not int):
            return False
        rows = [json.loads(line) for line in data.splitlines() if line.strip()]
        return (len(data) <= 4096 and len(rows) == 2
                and isinstance(rows[0], dict) and type(rows[0].get('child-pid')) is int
                and rows[0]['child-pid'] > 0
                and rows[1] == {'exit-code': observation['returncode']}
                and type(rows[1]['exit-code']) is int
                and observation['returncode'] >= 0
                and observation['timeout'] is False and observation['reaped'] is True)
    except (ValueError, KeyError, TypeError):
        return False


class Containment:
    def __init__(self, pin, budget, env):
        self.pin, self.budget, self.env = pin, budget, env
        self.binary = budget.call(checked_binary, pin)

    def run(self, command, cwd, *, timeout=1800, read_only=False, log=None):
        from scripts.dsh_prepare import run, CommandFailed, StopUnconfirmed, safe_observation
        self.budget.call(checked_binary, self.pin)
        # Reserve cleanup *inside* the original deadline; no fresh grace clock.
        limit = min(timeout, self.budget.check(reserve=1))
        reader, writer = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        failure = None; secondary = []; result = None; observation = {}; data = b''
        # A later diagnostic/pipe error must never replace the invocation cause.
        # This is a finite list: each setup/run/read/close/witness stage runs once.
        def failed(exc):
            nonlocal failure
            if failure is None:
                failure = exc
            else:
                secondary.append(exc)
        try:
            args = argv(self.binary, command, read_only=read_only)
            args[1:1] = ['--json-status-fd', str(writer)]
            try:
                logging = {'log': log} if log is not None else {}
                result = run(args, cwd, timeout=limit, env=self.env,
                             deadline=self.budget.deadline, pass_fds=(writer,), **logging)
                observation = result[1]
            except BaseException as exc:
                failed(exc)
                if isinstance(exc, CommandFailed):
                    try:
                        observation = exc.observation
                    except BaseException as observation_failure:
                        failed(observation_failure)
            closing = writer; writer = None  # never retry an ambiguous close
            try:
                os.close(closing)
            except BaseException as close_failure:
                failed(close_failure)
            # Exactly two small native records fit in the pipe. Never wait for
            # EOF from an uncertain monitor or use its stdout as proof.
            try:
                data = os.read(reader, 4097)
            except BlockingIOError:
                pass
            except BaseException as read_failure:
                failed(read_failure)
        except BaseException as exc:
            failed(exc)
        finally:
            if writer is not None:
                closing = writer; writer = None
                try:
                    os.close(closing)
                except BaseException as close_failure:
                    failed(close_failure)
            try:
                os.close(reader)
            except BaseException as close_failure:
                failed(close_failure)
        try:
            known = namespace_exit(data, observation) is True
        except BaseException as witness_failure:
            failed(witness_failure)
            known = False
        if (known and not secondary
                and (failure is None or isinstance(failure, CommandFailed))
                and observation.get('returncode') != 3):
            try:
                observation['namespace_init_exit_verified'] = True
            except BaseException as observation_failure:
                failed(observation_failure)
                known = False
        # A cleanup/observation failure is conservatively unknown even when a
        # record happened to look complete. Exit 3 also propagates inner custody.
        if (not known or secondary or isinstance(failure, StopUnconfirmed)
                or (type(observation) is dict and observation.get('returncode') == 3)
                or (failure is not None and not isinstance(failure, CommandFailed))):
            stopped = (failure if isinstance(failure, StopUnconfirmed) else
                       StopUnconfirmed('STOP_UNCONFIRMED: namespace init exit not established'))
            stopped.friday_custody_primary = failure
            if type(observation) is dict and observation:
                try:
                    stopped.observation = safe_observation(observation)
                except BaseException as observation_failure:
                    secondary.append(observation_failure)
            stopped.friday_custody_secondary = tuple(secondary)
            stopped.friday_custody_state = 'UNCONFIRMED'
            if stopped is failure:
                raise stopped
            raise stopped from failure
        if failure is not None: raise failure
        self.budget.check()
        return result

    def probe(self, python, cwd):
        outer = os.readlink('/proc/self/ns/pid')
        code = ('import os; assert os.readlink("/proc/self/ns/pid") != ' + repr(outer)
                + '; fd=os.open("/dev/null",os.O_RDWR); '
                  'assert os.read(fd,1)==b""; assert os.write(fd,b"probe")==5; '
                  'os.close(fd); print("FRIDAY_PID_NAMESPACE_OK")')
        result = self.run([python, '-B', '-c', code], cwd, timeout=5)[0]
        if result != 'FRIDAY_PID_NAMESPACE_OK':
            raise ValueError('required_pid_namespace_unavailable')
