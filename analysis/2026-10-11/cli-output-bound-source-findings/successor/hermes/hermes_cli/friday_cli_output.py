"""Finite output owned by the original classic frontend and its calling task.

No executor, writer thread, buffered document, or detached pump. On Linux a
terminal/pipe is reopened through its retained /proc/self/fd entry: this creates
a separate nonblocking open file description, NOT dup() or a shared flag change.
The original stream/FD/flags stay intact; the temporary description belongs to
the existing PluginContext coroutine and closes before it returns or cancels.
Installed console/renderer qualification remains required before activation.
"""
import asyncio
import fcntl
import io
import math
import os
import stat
import sys
import threading

MAX_ENVELOPE = 384 * 1024
WRITE_SLICE = 4096


class OutputRejected(ValueError):
    """Proven refusal before any document write; safe FAILED acknowledgement."""


class OutputCleanupUnconfirmed(RuntimeError):
    """Retain custody and stop this frontend; never acknowledge a clean close."""


def output_deadline(timeout, deadline=None):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError('invalid_cli_output_timeout')
    now = asyncio.get_running_loop().time()
    end = now + timeout
    if deadline is not None:
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= now:
            raise ValueError('invalid_cli_output_deadline')
        end = min(end, deadline)
    return end


def _identity(value):
    return value.st_dev, value.st_ino, value.st_mode, value.st_rdev


class ClassicConsoleOutput:
    """Opaque frontend lifetime, created once by HermesCLI.__init__.

    Capturing this object never opens, flushes, replaces, or reconfigures output.
    Only exact standard streams are supported; user supplied async/write hooks
    cannot acquire a capability. The console's existing lock protects its output.
    """
    def __init__(self, cli):
        self.cli = cli
        self.console = cli.console
        self.stream = self.console.file
        self.console_lock = getattr(self.console, '_lock', None)
        self.cap = getattr(cli, '_friday_cli_scope', None)
        self.closed = threading.Event()
        self.busy = threading.Lock()
        self.uncertain_descriptor = None

    def check_lifetime(self):
        if (self.closed.is_set() or getattr(self.cli, '_friday_cli_output', None) is not self
                or self.cli.console is not self.console
                or getattr(self.console, '_lock', None) is not self.console_lock
                or getattr(self.cli, '_friday_cli_scope', None) is not self.cap):
            raise RuntimeError('original_cli_output_lifetime_lost')

    def check(self):
        self.check_lifetime()
        if self.console.file is not self.stream:
            raise RuntimeError('original_cli_output_stream_changed')

    def close(self):
        # The existing task/ledger remains the sole FD custodian. Closing the
        # frontend prevents its next write; cancellation/finally joins cleanup.
        # Do not close/reuse a coroutine's descriptor from another thread.
        self.closed.set()

    def acquire(self):
        self.check()
        if not self.busy.acquire(blocking=False):
            raise RuntimeError('original_cli_output_busy')
        locked = False
        try:
            if self.console_lock is None or not self.console_lock.acquire(blocking=False):
                raise RuntimeError('original_cli_console_busy')
            locked = True
            self.check()
            return _ConsoleWrite(self)
        except BaseException:
            if locked:
                self.console_lock.release()
            self.busy.release()
            raise


class _ConsoleWrite:
    def __init__(self, owner):
        self.owner = owner
        self.fd = None
        self.original_fd = None
        self.original_identity = None
        self.original_flags = None
        self.accepted = 0
        self.active = True
        stream = owner.stream
        if type(stream) is io.StringIO:
            # Exact C implementation only; no custom slow write/flush method.
            # A bounded append avoids copying an unbounded old transcript.
            if stream.closed or stream.tell() != len(stream.getvalue()) or stream.tell() > MAX_ENVELOPE:
                raise ValueError('unsupported_cli_memory_output')
            self.memory_position = stream.tell()
            self.kind = 'bounded-memory'
            return
        if (sys.platform != 'linux' or type(stream) is not io.TextIOWrapper
                or stream.closed or stream.encoding.lower().replace('_', '-') not in {'utf-8', 'ascii'}):
            raise ValueError('unsupported_cli_output_stream')
        buffer = stream.buffer
        raw = buffer.raw if type(buffer) is io.BufferedWriter else buffer
        if type(raw) is not io.FileIO or raw.closed:
            raise ValueError('unsupported_cli_output_buffer')
        self.original_fd = raw.fileno()
        original = os.fstat(self.original_fd)
        # Regular files/devices/sockets have no proved finite console contract.
        if not ((stat.S_ISCHR(original.st_mode) and os.isatty(self.original_fd))
                or stat.S_ISFIFO(original.st_mode)):
            raise ValueError('unsupported_cli_output_descriptor')
        self.original_identity = _identity(original)
        self.original_flags = fcntl.fcntl(self.original_fd, fcntl.F_GETFL)
        if self.original_flags & os.O_ACCMODE == os.O_RDONLY:
            raise ValueError('readonly_cli_output')
        fd = os.open('/proc/self/fd/' + str(self.original_fd),
                     os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY)
        try:
            if (_identity(os.fstat(fd)) != self.original_identity
                    or not fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK
                    or not fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
                    or _identity(os.fstat(self.original_fd)) != self.original_identity
                    or fcntl.fcntl(self.original_fd, fcntl.F_GETFL) != self.original_flags):
                raise RuntimeError('original_cli_output_descriptor_changed')
            owner.check()
            self.fd = fd
            self.kind = 'native-nonblocking-fd'
        except BaseException:
            try:
                os.close(fd)
            except Exception as exc:
                owner.uncertain_descriptor = {'fd':fd,'identity':self.original_identity}
                owner.closed.set()
                raise OutputCleanupUnconfirmed('cli_output_close_unconfirmed') from exc
            raise

    def check(self):
        self.owner.check()
        if not self.active:
            raise RuntimeError('cli_output_write_closed')
        if self.fd is not None:
            stream = self.owner.stream
            raw = stream.buffer.raw if type(stream.buffer) is io.BufferedWriter else stream.buffer
            if (raw.closed or raw.fileno() != self.original_fd
                    or _identity(os.fstat(self.original_fd)) != self.original_identity
                    or fcntl.fcntl(self.original_fd, fcntl.F_GETFL) != self.original_flags
                    or _identity(os.fstat(self.fd)) != self.original_identity
                    or not fcntl.fcntl(self.fd, fcntl.F_GETFL) & os.O_NONBLOCK):
                raise RuntimeError('original_cli_output_descriptor_changed')
        elif (self.owner.stream.closed or self.owner.stream.tell() != self.memory_position
                or len(self.owner.stream.getvalue()) != self.memory_position
                or self.memory_position > 2 * MAX_ENVELOPE):
            raise RuntimeError('original_cli_memory_output_changed')

    def write(self, chunk):
        self.check()
        if self.fd is None:
            count = self.owner.stream.write(chunk.decode('ascii'))
        else:
            count = os.write(self.fd, chunk)
        if type(count) is not int or not 0 < count <= len(chunk):
            raise RuntimeError('uncertain_cli_output_write')
        self.accepted += count
        if self.fd is None:
            self.memory_position += count
        return count

    def close(self):
        if not self.active:
            return
        self.active = False
        try:
            if self.fd is not None:
                fd, self.fd = self.fd, None
                try:
                    os.close(fd)
                except Exception as exc:
                    self.owner.uncertain_descriptor = {'fd':fd,'identity':self.original_identity}
                    self.owner.closed.set()
                    raise OutputCleanupUnconfirmed('cli_output_close_unconfirmed') from exc
        finally:
            try:
                self.owner.console_lock.release()
            finally:
                self.owner.busy.release()


def initialize_console_output(cli):
    if getattr(cli, '_friday_cli_output', None) is not None:
        raise RuntimeError('cli_output_already_initialized')
    cli._friday_cli_output = ClassicConsoleOutput(cli)


def retained_console_output(turn):
    owner = getattr(turn['cli'], '_friday_cli_output', None)
    if (type(owner) is not ClassicConsoleOutput or owner is not turn.get('output')
            or owner.console is not turn['console'] or owner.stream is not turn['stream']
            or owner.cap is not turn['cap']):
        raise RuntimeError('original_cli_output_missing')
    owner.check()
    return owner


def retained_console_lifetime(turn):
    # Native patch_stdout can wrap the console between input turns. Its
    # existing intake/status/stop contracts remain usable. Such a wrapped sink
    # cannot silently replace the captured output producer or receive bytes.
    owner = getattr(turn['cli'], '_friday_cli_output', None)
    if (type(owner) is not ClassicConsoleOutput or owner is not turn.get('output')
            or owner.cli is not turn['cli'] or owner.cap is not turn['cap']):
        raise RuntimeError('original_cli_output_missing')
    owner.check_lifetime()
    return owner


async def write_console_envelope(owner, payload, *, deadline, check, stop):
    """Run inside the caller's existing native ledger task; no hidden child.

    No generic synchronous stream flush is called. Completed raw nonblocking
    writes mean kernel acceptance of every byte. Partial/error/expiry stays
    uncertain; closing drops no user-space document buffer for a later replay.
    """
    if type(payload) is not bytes or len(payload) > MAX_ENVELOPE:
        raise ValueError('cli_output_envelope_limit')
    loop = asyncio.get_running_loop()
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= loop.time():
        raise ValueError('cli_output_expired_before_write')
    await asyncio.sleep(0)  # cancellation can win before descriptor acquisition
    check()
    if stop() or loop.time() >= deadline:
        raise ValueError('cli_output_stopped_before_write')
    try:
        lease = owner.acquire()
    except OutputCleanupUnconfirmed:
        raise
    except Exception:
        raise OutputRejected('unsupported_or_unavailable_original_cli_output') from None
    try:
        await asyncio.sleep(0)  # queued cancellation also wins after acquisition
        offset = 0
        while offset < len(payload):
            check()
            lease.check()
            if stop() or loop.time() >= deadline:
                raise TimeoutError('cli_output_deadline_or_stop')
            try:
                offset += lease.write(payload[offset:offset + WRITE_SLICE])
            except BlockingIOError:
                # Only raw nonblocking EAGAIN is retryable. No buffered writer
                # callback is invoked and no document is submitted twice.
                if lease.fd is None:
                    raise
            except InterruptedError:
                pass
            if offset < len(payload):
                await asyncio.sleep(min(.001, max(0, deadline - loop.time())))
        check()
        lease.check()
        if stop() or loop.time() >= deadline:
            raise TimeoutError('cli_output_deadline_or_stop')
        return lease.kind
    finally:
        lease.close()
