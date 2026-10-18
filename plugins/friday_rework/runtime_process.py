"""Shared bounded process custody, extracted from the native preparer."""

import hashlib
import json
import locale
import math
import os
from pathlib import Path
import signal
import subprocess
import time


class StopUnconfirmed(RuntimeError):
    """An owned command was signalled but its cessation was not observed."""



SAFE_OBSERVATION_FIELDS = ('returncode', 'elapsed_seconds', 'timeout', 'stdout_sha256',
                           'stderr_sha256', 'stdout_bytes', 'stderr_bytes', 'pid',
                           'starttime_ticks', 'reaped', 'reason',
                           'namespace_init_exit_verified', 'custody_scope', 'exception_type')



def safe_observation(observation):
    return {key: observation[key] for key in SAFE_OBSERVATION_FIELDS if key in observation}



class CommandFailed(RuntimeError):
    """Reaped command failure; never carry argv, environment or raw output."""

    def __init__(self, observation):
        self.observation = safe_observation(observation)
        super().__init__('command_timeout' if observation['timeout'] else
                         'command_exception' if observation.get('reason') == 'command_exception'
                         else 'command_nonzero_exit')



def clean_environment(donor):
    # Build tools retain the user's actual home, but receive no model/Telegram keys.
    allowed = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM",
               "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               COREPACK_ENABLE_DOWNLOAD_PROMPT="0",
               COREPACK_HOME=str(donor / ".git/friday-corepack"),
               npm_config_cache=str(donor / ".git/friday-npm-cache"),
               npm_config_child_concurrency="4", npm_config_network_concurrency="8",
               NODE_OPTIONS="--disable-wasm-trap-handler",
               DSH_TELEMETRY_DISABLED="1", DSH_HOME=str(donor / ".git/friday-smoke-home"))
    return env



def _starttime(pid):
    return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19])


def _kill_exact_leader(process, starttime):
    """A pidfd binds this signal; never signal a possibly reused numeric PID/PGID."""
    if type(starttime) is not int or starttime <= 0:
        raise StopUnconfirmed('STOP_UNCONFIRMED: owned leader identity unavailable')
    fd = os.pidfd_open(process.pid)
    failure = None
    try:
        birth = _starttime(process.pid)
        info = dict(line.split(':', 1) for line in
                    Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines())
        if birth != starttime or int(info['Pid']) != process.pid:
            raise StopUnconfirmed('STOP_UNCONFIRMED: owned leader identity changed')
        signal.pidfd_send_signal(fd, signal.SIGKILL)
    except ProcessLookupError:
        # This exact pidfd no longer names a live process. Reaping is separate.
        pass
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            os.close(fd)
        except BaseException as exc:
            if failure is None:
                raise
            failure.friday_custody_secondary = (
                getattr(failure, 'friday_custody_secondary', ()) + (exc,))


def run(argv, donor, *, timeout=60, log=None, env=None, deadline=None, pass_fds=(),
        stop_on_timeout=None):
    """Bound owned leader/pipes; namespace callers alone prove detached-tree exit.

    The historical callback name also covers non-timeout failures after spawn.
    Without that boundary, interruption cannot prove process-group or detached
    descendant cessation: kill only an identity-bound leader and report unknown.
    """
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError('finite_command_timeout_required')
    if deadline is not None and (not isinstance(deadline, (int, float))
                                 or not math.isfinite(deadline)):
        raise ValueError('finite_original_deadline_required')
    if argv[0] == "git":
        argv = ["git", "-c", "core.hooksPath=" + os.devnull,
                "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
                "-c", "pack.threads=4", *argv[1:]]
    start = time.monotonic()
    if deadline is not None and deadline <= start:
        raise ValueError('original_command_budget_exhausted')
    # Preserve the historical maximum ten seconds of no-deadline cleanup, but
    # anchor it before spawn. Cleanup never receives a renewed grace clock.
    finish_by = deadline if deadline is not None else start + timeout + 10
    process = subprocess.Popen(argv, cwd=donor, env=env or clean_environment(donor),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=False, start_new_session=True, pass_fds=pass_fds)
    starttime = None
    out = err = b''
    failure = None
    secondary = []
    timed_out = False
    family_unknown = False
    observation = {'argv': argv, 'pid': process.pid, 'starttime_ticks': None, 'timeout': False,
                   'reaped': False, 'reason': 'command_exception',
                   'custody_scope': 'namespace_monitor' if stop_on_timeout is not None
                                    else 'leader_and_pipes_only'}

    def failed(exc):
        nonlocal failure
        if failure is None:
            failure = exc
        else:
            secondary.append(exc)
        secondary.extend(getattr(exc, 'friday_custody_secondary', ()))

    try:
        try:
            starttime = _starttime(process.pid)
        except (OSError, ValueError, IndexError):
            # A short-lived leader can disappear before this optional sample.
            pass
        out, err = process.communicate(timeout=min(timeout, max(0, finish_by - time.monotonic())))
    except BaseException as exc:
        failed(exc)
        timed_out = isinstance(exc, subprocess.TimeoutExpired)
        # Do not kill the native monitor: its two status records are the only
        # kernel-drained namespace witness. Stop the exact init via its callback.
        if process.returncode is None:
            try:
                if stop_on_timeout is not None:
                    if starttime is None:
                        starttime = _starttime(process.pid)
                    stop_on_timeout(process, starttime)
                else:
                    family_unknown = True
                    _kill_exact_leader(process, starttime)
            except BaseException as stop_failure:
                failed(stop_failure)
        remaining = finish_by - time.monotonic()
        if remaining > 0:
            try:
                # Binary pipes cannot raise a second text-decoding exception.
                out, err = process.communicate(timeout=remaining)
            except BaseException as drain_failure:
                failed(drain_failure)
                remaining = finish_by - time.monotonic()
                if remaining > 0:
                    try:
                        process.wait(timeout=remaining)
                    except BaseException as wait_failure:
                        failed(wait_failure)

    # Everything below is still owned custody: decoding, observation, diagnostics,
    # and closing pipes can all fail. Retain the first cause, redact public text.
    try:
        observation.update(returncode=process.returncode, starttime_ticks=starttime,
                           timeout=timed_out, reaped=process.returncode is not None,
                           elapsed_seconds=round(time.monotonic() - start, 3))
        raw_out = out.encode() if isinstance(out, str) else out
        raw_err = err.encode() if isinstance(err, str) else err
        observation.update(stdout_sha256=hashlib.sha256(raw_out).hexdigest(),
                           stderr_sha256=hashlib.sha256(raw_err).hexdigest(),
                           stdout_bytes=len(raw_out), stderr_bytes=len(raw_err))
        encoding = locale.getpreferredencoding(False)
        # Match text-mode universal newline handling, after binary draining/reap.
        out = out if isinstance(out, str) else out.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
        err = err if isinstance(err, str) else err.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
        # Existing hashes describe returned text, as in the prior text-mode API.
        observation.update(stdout_sha256=hashlib.sha256(out.encode()).hexdigest(),
                           stderr_sha256=hashlib.sha256(err.encode()).hexdigest(),
                           stdout_bytes=len(out.encode()), stderr_bytes=len(err.encode()))
        reason = ('device_null_unavailable' if
                  "fatal: could not open '/dev/null' for reading and writing: Permission denied" in err
                  else 'command_timeout' if timed_out else 'command_exception' if failure is not None
                  else 'command_nonzero_exit' if process.returncode else 'command_succeeded')
        source_reasons = {'git_source_operation_failed': 'source_git_operation_failed',
                          'source_preparation_deadline': 'source_preparation_deadline',
                          'source_input_or_io_failed': 'source_input_or_io_failed',
                          'fresh_destination_required': 'source_destination_exists',
                          'dirty_donor_refused': 'source_donor_changed',
                          'donor_identity_changed': 'source_donor_changed',
                          'overlay_hash_mismatch': 'source_overlay_changed'}
        for code, stable in source_reasons.items():
            if err.strip() == 'FRIDAY_SOURCE_REFUSED reason=' + code:
                reason = stable
                break
        observation['reason'] = reason
        if log:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.with_suffix('.stdout').write_text(out)
            log.with_suffix('.stderr').write_text(err)
            log.with_suffix('.json').write_text(json.dumps(dict(observation, argv=argv), indent=2) + '\n')
    except BaseException as diagnostic_failure:
        failed(diagnostic_failure)
    finally:
        for name in ('stdout', 'stderr'):
            try:
                stream = getattr(process, name, None)
                if stream is not None and not stream.closed:
                    stream.close()
            except BaseException as close_failure:
                failed(close_failure)

    # poll() is nonblocking; no final wait may reopen the exhausted budget.
    try:
        if process.returncode is None:
            process.poll()
        observation.update(returncode=process.returncode, reaped=process.returncode is not None,
                           starttime_ticks=starttime, timeout=timed_out,
                           elapsed_seconds=round(time.monotonic() - start, 3))
    except BaseException as poll_failure:
        failed(poll_failure)
    if failure is not None:
        if not timed_out:
            observation['reason'] = 'command_exception'
        observation['exception_type'] = type(failure).__name__
        unknown = family_unknown or secondary or not observation.get('reaped')
        wrapped = (StopUnconfirmed('STOP_UNCONFIRMED: owned command cessation not established')
                   if unknown else CommandFailed(observation))
        wrapped.observation = safe_observation(observation)
        wrapped.friday_custody_primary = failure
        wrapped.friday_custody_secondary = tuple(secondary)
        if unknown:
            wrapped.friday_custody_state = 'UNCONFIRMED'
        raise wrapped from None
    if not observation.get('reaped'):
        stopped = StopUnconfirmed('STOP_UNCONFIRMED: owned command not reaped')
        stopped.observation = safe_observation(observation)
        stopped.friday_custody_primary = None
        stopped.friday_custody_secondary = ()
        stopped.friday_custody_state = 'UNCONFIRMED'
        raise stopped from None
    if process.returncode:
        raise CommandFailed(observation)
    return out.strip(), observation
