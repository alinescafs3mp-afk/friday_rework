"""Shared bounded process custody, extracted from the native preparer."""

import hashlib
import json
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
                           'namespace_init_exit_verified')



def safe_observation(observation):
    return {key: observation[key] for key in SAFE_OBSERVATION_FIELDS if key in observation}



class CommandFailed(RuntimeError):
    """Reaped command failure; never carry argv, environment or raw output."""

    def __init__(self, observation):
        self.observation = safe_observation(observation)
        super().__init__('command_timeout' if observation['timeout'] else 'command_nonzero_exit')



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



def run(argv, donor, *, timeout=60, log=None, env=None, deadline=None, pass_fds=(),
        stop_on_timeout=None):
    """Bound one group; callers needing detached-tree custody use a PID namespace."""
    if argv[0] == "git":
        argv = ["git", "-c", "core.hooksPath=" + os.devnull,
                "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
                "-c", "pack.threads=4", *argv[1:]]
    start = time.monotonic()
    process = subprocess.Popen(argv, cwd=donor, env=env or clean_environment(donor),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True, pass_fds=pass_fds)
    try:
        starttime = int(Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        starttime = None
    timed_out = False
    stop_errors = []
    def unconfirmed(message, observation, extra=()):
        secondary = list(stop_errors) + list(extra)
        # A retained exception also retains this frame/Popen. Release our pipe
        # handles now, and reap only if already exited: no renewed wait budget.
        for name in ('stdout', 'stderr'):
            try:
                stream = getattr(process, name, None)
                if stream is not None and not stream.closed:
                    stream.close()
            except BaseException as exc:
                secondary.append(exc)
        try:
            poll = getattr(process, 'poll', None)
            if poll is not None:
                poll()
                observation = dict(observation, returncode=process.returncode,
                                   reaped=process.returncode is not None)
        except BaseException as exc:
            secondary.append(exc)
        observation = dict(observation, elapsed_seconds=round(time.monotonic() - start, 3))
        primary = CommandFailed(observation)
        stopped = StopUnconfirmed(message)
        stopped.observation = primary.observation
        stopped.friday_custody_primary = primary
        stopped.friday_custody_secondary = tuple(secondary)
        return stopped, primary
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if deadline is not None:
            # Containment targets its exact namespace init while leaving the
            # native monitor alive to report kernel-drained namespace exit.
            # A process group alone provides no detached-session custody.
            try:
                if stop_on_timeout is not None:
                    stop_on_timeout(process, starttime)
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except BaseException as exc:
                stop_errors.append(exc)
                stop_errors.extend(getattr(exc, 'friday_custody_secondary', ()))
            remaining = deadline - time.monotonic()
            partial = dict(returncode=process.returncode, timeout=True,
                           pid=process.pid, starttime_ticks=starttime,
                           reaped=process.returncode is not None, reason='command_timeout',
                           elapsed_seconds=round(time.monotonic() - start, 3))
            if remaining <= 0:
                stopped, primary = unconfirmed('STOP_UNCONFIRMED: original cleanup budget exhausted', partial)
                raise stopped from primary
            try:
                out, err = process.communicate(timeout=remaining)
            except BaseException as exc:
                stopped, primary = unconfirmed('STOP_UNCONFIRMED: contained command not reaped', partial, (exc,))
                raise stopped from primary
        else:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                out, err = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                out, err = process.communicate(timeout=5)
    reason = ('device_null_unavailable' if
              "fatal: could not open '/dev/null' for reading and writing: Permission denied" in err
              else 'command_timeout' if timed_out else 'command_nonzero_exit' if process.returncode else 'command_succeeded')
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
    observation = {"argv": argv, "returncode": process.returncode,
                   "elapsed_seconds": round(time.monotonic() - start, 3),
                   "timeout": timed_out, "stdout_sha256": hashlib.sha256(out.encode()).hexdigest(),
                   "stderr_sha256": hashlib.sha256(err.encode()).hexdigest(),
                   "stdout_bytes": len(out.encode()), "stderr_bytes": len(err.encode()),
                   "pid": process.pid, "starttime_ticks": starttime,
                   "reaped": process.returncode is not None, "reason": reason}
    try:
        if log:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.with_suffix(".stdout").write_text(out)
            log.with_suffix(".stderr").write_text(err)
            log.with_suffix(".json").write_text(json.dumps(observation, indent=2) + "\n")
    except BaseException as exc:
        if timed_out or process.returncode:
            stopped, primary = unconfirmed('STOP_UNCONFIRMED: command diagnostics failed', observation, (exc,))
            raise stopped from primary
        raise
    if timed_out or process.returncode:
        if stop_errors:
            stopped, primary = unconfirmed('STOP_UNCONFIRMED: native init stop failed', observation)
            raise stopped from primary
        raise CommandFailed(observation)
    return out.strip(), observation

