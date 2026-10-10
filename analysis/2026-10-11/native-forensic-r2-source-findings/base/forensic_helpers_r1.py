import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import selectors
import stat
import time

FORENSIC_LIMIT = 65536
STREAM_LIMIT = 4096
QUEUE_TIMEOUT = 20


class EvidencePersistenceError(RuntimeError):
    pass


def _safe_text(value):
    text = str(value)
    text = re.sub(r'(?i)(bearer\s+)[^\s"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|password|secret)["\']?\s*[=:]\s*["\']?)[^\s,"\']+', r'\1[REDACTED]', text)
    return text


def _atomic_json(path, value, initial=False):
    """Owner-only bounded replacement; old UNKNOWN survives every write failure."""
    data = (json.dumps(value, ensure_ascii=True, sort_keys=True) + '\n').encode()
    if len(data) > FORENSIC_LIMIT:
        raise ValueError('Bounded forensic record exceeded')
    if not initial:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise PermissionError('Evidence target is not an owned private regular file')
    temporary = path if initial else path.with_name('.' + path.name + '.write-' + str(os.getpid()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        if not initial:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # Never unlink an original reservation or old receipt.
        if not initial:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise


def _commit_receipt(path, receipt, forensic_path, evidence):
    try:
        _atomic_json(path, receipt)
    except BaseException as exc:
        evidence['bookkeeping_exception'] = _exception(exc, 'receipt_commit')
        evidence['receipt_commit'] = 'UNKNOWN_DURABILITY'
        _checkpoint(forensic_path, evidence, 'receipt_commit_failed')
        raise
    evidence['receipt_commit'] = 'DURABLE'
    evidence['canonical_receipt_state'] = receipt['state']
    _checkpoint(forensic_path, evidence, 'receipt_committed')


def _exception(exc, phase):
    result = {'class': type(exc).__module__ + '.' + type(exc).__qualname__,
              'phase': phase, 'message': _safe_text(str(exc))[:1024]}
    chain = []; cause = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    seen = {id(exc)}
    while cause is not None and id(cause) not in seen and len(chain) < 4:
        seen.add(id(cause))
        item = {'class': type(cause).__module__ + '.' + type(cause).__qualname__,
                'message': _safe_text(str(cause))[:256]}
        if isinstance(getattr(cause, 'errno', None), int):
            item['errno'] = cause.errno
        chain.append(item)
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    if chain:
        result['cause_chain'] = chain
    for key in ('errno', 'timeout', 'returncode'):
        value = getattr(exc, key, None)
        if isinstance(value, (int, float)):
            result[key] = value
    for key, attribute in (('stdout', 'output'), ('stderr', 'stderr')):
        value = getattr(exc, attribute, None)
        if value is not None:
            stream = _Stream(); stream.add(value)
            result[key] = stream.record()
    return result


class _Stream:
    def __init__(self, limit=STREAM_LIMIT):
        self.limit = limit
        self.head = b''; self.tail = b''; self.total = 0
        self.digest = hashlib.sha256(); self.types = set()

    def add(self, value):
        self.types.add('bytes' if isinstance(value, bytes) else 'text')
        data = value if isinstance(value, bytes) else str(value).encode('utf-8', 'surrogatepass')
        self.digest.update(data); self.total += len(data)
        remaining = self.limit // 2 - len(self.head)
        if remaining > 0:
            self.head += data[:remaining]
            data = data[remaining:]
        self.tail = (self.tail + data)[-self.limit // 2:]

    def data(self):
        return self.head + self.tail

    def record(self):
        # Exact byte excerpts where safe; redact before either base64 or text storage.
        raw = self.data()
        text = raw.decode('utf-8', 'backslashreplace')
        safe = _safe_text(text)
        redacted = safe != text
        retained = safe.encode() if redacted else raw
        return {'observed_types': sorted(self.types), 'total_bytes': self.total,
                'captured_bytes': len(raw), 'truncated': self.total > len(raw),
                'raw_sha256': self.digest.hexdigest(), 'redacted': redacted,
                'encoding': 'base64', 'bytes': base64.b64encode(retained).decode(),
                'text': safe[:1024], 'text_truncated': len(safe) > 1024, 'partial': True}


def _checkpoint(path, evidence, phase=None, initial=False):
    if phase is not None and evidence.get('phase') != phase:
        evidence['phase'] = phase
        history = evidence.setdefault('phase_history', [])
        history.append({'phase': phase, 'monotonic_ns': time.monotonic_ns()})
        if len(history) > 16:
            del history[1]
    evidence['observed_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    evidence['observed_monotonic_ns'] = time.monotonic_ns()
    try:
        _atomic_json(path, evidence, initial=initial)
    except Exception as exc:
        # No alternate queue call. The canonical durable reservation still suppresses resend.
        causal = evidence.get('exception', {}).get('class', 'UNKNOWN')
        raise EvidencePersistenceError('Private evidence persistence failed; phase=' + evidence.get('phase', 'UNKNOWN') + '; causal=' + causal + '; no retry') from exc


def _lifecycle_run(command, phase, path, evidence):
    evidence['queue_call'] = 'NOT_CALLED'
    _checkpoint(path, evidence, phase + '_before_call')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except BaseException as exc:
        evidence['exception'] = _exception(exc, phase)
        _checkpoint(path, evidence, phase + '_exception')
        raise
    evidence['lifecycle_result'] = {'phase': phase, 'returncode': result.returncode}
    for name in ('stdout', 'stderr'):
        stream = _Stream(limit=512); stream.add(getattr(result, name))
        evidence['lifecycle_result'][name] = stream.record()
    _checkpoint(path, evidence, phase + '_returned')
    return result


def _observed_rpc_ids(evidence, streams):
    """Only actual structured CLI diagnostics, never manufacture a client identity."""
    observations = []
    for name, stream in streams.items():
        # Truncated output cannot provide a complete structured diagnostic.
        if stream.total > STREAM_LIMIT:
            continue
        for line in stream.data().decode('utf-8', 'replace').splitlines()[:64]:
            try:
                value = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(value, dict) or value.get('method') != 'thread/queue/add':
                continue
            params = value.get('params')
            if not isinstance(params, dict) or params.get('threadId') != evidence.get('recipient_thread'):
                continue
            rpc = value.get('id'); client = params.get('clientUserMessageId')
            if not isinstance(rpc, (str, int)) or isinstance(rpc, bool):
                continue
            if not isinstance(client, str) or not client or len(client) > 128 or len(str(rpc)) > 128:
                continue
            # Keep the same-request pairing, source, and diagnostic-only authority.
            safe_rpc = rpc if isinstance(rpc, int) else _safe_text(rpc)
            safe_client = _safe_text(client)
            if safe_rpc != rpc or safe_client != client:
                continue
            observations.append({'rpc_request_id': rpc, 'rpc_request_id_type': type(rpc).__name__,
                                 'client_user_message_id': client,
                                 'source': name + ':JSON:thread/queue/add', 'authority': 'CLI_DIAGNOSTIC_ONLY_NOT_SETTLEMENT'})
            if len(observations) == 4:
                break
        if len(observations) == 4:
            break
    evidence['identities']['observed_request_pairs'] = observations
    evidence['identities']['rpc_request_id'] = 'UNKNOWN'
    evidence['identities']['client_user_message_id'] = 'UNKNOWN'
    if observations and len({(item['rpc_request_id'], item['client_user_message_id']) for item in observations}) == 1:
        evidence['identities']['rpc_request_id'] = observations[0]['rpc_request_id']
        evidence['identities']['client_user_message_id'] = observations[0]['client_user_message_id']


def _queue_run(command, path, evidence):
    """Same single CLI call and 20s transport; own local process cleanup only."""
    started = time.monotonic()
    deadline = started + QUEUE_TIMEOUT
    evidence['transport_started_monotonic_ns'] = time.monotonic_ns()
    evidence['transport_timeout_seconds'] = QUEUE_TIMEOUT
    evidence['queue_call'] = 'UNKNOWN_SPAWN_BOUNDARY'
    # Must be durable BEFORE Popen. A crash at this boundary cannot prove no call.
    _checkpoint(path, evidence, 'queue_spawn_boundary')
    process = None
    persistence_failed = False
    selector = None
    streams = {'stdout': _Stream(), 'stderr': _Stream()}
    phase = 'selector_prepare'
    try:
        selector = selectors.DefaultSelector()
        phase = 'queue_spawn'
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        evidence['queue_call'] = 'CLI_STARTED_REMOTE_EFFECT_UNKNOWN'
        evidence['identities']['cli_pid'] = process.pid
        evidence['identities']['cli_spawn_return_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        evidence['identities']['cli_exe_path'] = 'UNKNOWN'
        try:
            evidence['identities']['cli_exe_path'] = os.readlink('/proc/' + str(process.pid) + '/exe')
        except OSError:
            pass
        evidence['identities']['cli_executable_stat'] = 'UNKNOWN'
        try:
            executable_stat = Path('/proc/' + str(process.pid) + '/exe').stat()
            evidence['identities']['cli_executable_stat'] = {'device': executable_stat.st_dev, 'inode': executable_stat.st_ino,
                                                          'size': executable_stat.st_size, 'mtime_ns': executable_stat.st_mtime_ns}
        except OSError:
            pass
        try:
            fields = Path('/proc/' + str(process.pid) + '/stat').read_text().rsplit(')', 1)[1].split()
            evidence['identities']['cli_start_ticks'] = int(fields[19])
        except (OSError, ValueError, IndexError):
            evidence['identities']['cli_start_ticks'] = 'UNKNOWN'
        _checkpoint(path, evidence, 'queue_cli_started')
        for name in streams:
            pipe = getattr(process, name)
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        phase = 'queue_capture'
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, QUEUE_TIMEOUT,
                                                output=streams['stdout'].data(), stderr=streams['stderr'].data())
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                streams[key.data].add(chunk)
                evidence['streams'] = {name: stream.record() for name, stream in streams.items()}
                _observed_rpc_ids(evidence, streams)
                _checkpoint(path, evidence)
        phase = 'queue_wait'
        returncode = process.wait(timeout=max(0, deadline - time.monotonic()))
        evidence['returncode'] = returncode
        evidence['streams'] = {name: stream.record() for name, stream in streams.items()}
        _observed_rpc_ids(evidence, streams)
        _checkpoint(path, evidence, 'queue_returned')
        # Exact original success grammar; oversized stdout cannot be admitted by an excerpt.
        phase = 'queue_decode_stdout'
        stdout = streams['stdout'].data().decode('utf-8') if streams['stdout'].total <= STREAM_LIMIT else ''
        return subprocess.CompletedProcess(command, returncode, stdout, '')
    except BaseException as exc:
        evidence['exception'] = _exception(exc, phase)
        if process is None and isinstance(exc, OSError):
            evidence['queue_call'] = 'NOT_CALLED_EXEC_FAILED' if phase == 'queue_spawn' else 'NOT_CALLED_LOCAL_PREPARATION_FAILED'
        evidence['streams'] = {name: stream.record() for name, stream in streams.items()}
        _observed_rpc_ids(evidence, streams)
        if isinstance(exc, EvidencePersistenceError):
            persistence_failed = True
        else:
            try:
                _checkpoint(path, evidence, 'queue_exception')
            except EvidencePersistenceError:
                persistence_failed = True
                raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit, EvidencePersistenceError)):
            raise
        return None
    finally:
        cleanup_errors = []
        if selector is not None:
            try:
                selector.close()
            except BaseException as exc:
                cleanup_errors.append((exc, 'queue_selector_cleanup'))
        if process is not None:
            # Matches subprocess.run timeout cleanup: kill/reap only this owned CLI.
            try:
                if process.poll() is None:
                    process.kill()
                process.wait()
                evidence['local_process_closed'] = True
                evidence['local_returncode'] = process.returncode
            except BaseException as exc:
                evidence['local_process_closed'] = 'UNKNOWN'
                cleanup_errors.append((exc, 'queue_local_process_cleanup'))
            finally:
                for name in streams:
                    try:
                        getattr(process, name).close()
                    except BaseException as exc:
                        cleanup_errors.append((exc, 'queue_' + name + '_cleanup'))
        else:
            evidence['local_process_closed'] = True
        evidence['local_handles_closed'] = not cleanup_errors
        if cleanup_errors:
            evidence['cleanup_exceptions'] = [_exception(exc, cleanup_phase) for exc, cleanup_phase in cleanup_errors]
        evidence['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        # Remote settlement remains UNKNOWN even after local process closure.
        if not persistence_failed:
            _checkpoint(path, evidence)
        if cleanup_errors:
            raise cleanup_errors[0][0]

