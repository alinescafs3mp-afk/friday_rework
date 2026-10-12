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


def _check_memory_methods(stream):
    # StringIO instances have a __dict__: exact type alone does not prevent a
    # caller from overriding write/tell/getvalue. Refuse shadowed methods before
    # acquisition and each slice; direct immutable descriptors also close the
    # check-to-call race. No user callback is invoked even if a concurrent thread
    # replaces an instance attribute immediately after this check.
    if type(stream) is not io.StringIO:
        raise ValueError('unsupported_cli_memory_method_override')
    attributes = vars(stream)
    if type(attributes) is not dict or any(
            name in attributes for name in ('write', 'tell', 'getvalue', 'seek')):
        raise ValueError('unsupported_cli_memory_method_override')


def _memory_bounds(stream):
    # C seek/tell inspect the existing length without getvalue() copying a
    # potentially large old transcript. Restore the exact original cursor.
    position = io.StringIO.tell(stream)
    if not 0 <= position <= 2 * MAX_ENVELOPE:
        raise ValueError('unsupported_cli_memory_output')
    end = io.StringIO.seek(stream, 0, 2)
    io.StringIO.seek(stream, position)
    return position, end


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
        self.renderer_output = None
        self.renderer_app = None
        self.renderer_requests = set()
        self.renderer_guard = threading.Lock()

    def check_lifetime(self):
        if (self.closed.is_set() or getattr(self.cli, '_friday_cli_output', None) is not self
                or self.cli.console is not self.console
                or getattr(self.console, '_lock', None) is not self.console_lock
                or getattr(self.cli, '_friday_cli_scope', None) is not self.cap
                or (self.renderer_app is not None and getattr(self.cli, '_app', None) is not self.renderer_app)):
            raise RuntimeError('original_cli_output_lifetime_lost')

    def check(self):
        self.check_lifetime()
        if not self.matches_stream(self.console.file):
            raise RuntimeError('original_cli_output_stream_changed')

    def matches_stream(self, stream):
        if stream is self.stream:
            return True
        if self.renderer_output is None or self.renderer_app is None:
            return False
        from prompt_toolkit.patch_stdout import StdoutProxy
        return (type(stream) is StdoutProxy and not stream.closed
                and stream.original_stdout is self.stream
                and stream._output is self.renderer_output
                and stream.app_session.app is self.renderer_app
                and self.renderer_app.output is self.renderer_output
                and self.renderer_app.renderer.output is self.renderer_output)

    def check_effect(self):
        # Final non-callback check after descriptor/capability observations.
        # A queued stop cannot turn a slow observation into a new write.
        if self.closed.is_set(): raise RuntimeError('original_cli_output_closed')
        request = getattr(self.renderer_output, 'request', None)
        if request is not None: request.check_effect()

    def close(self):
        # The existing task/ledger remains the sole FD custodian. Closing the
        # frontend prevents its next write; cancellation/finally joins cleanup.
        # Do not close/reuse a coroutine's descriptor from another thread.
        self.closed.set()
        with self.renderer_guard:
            requests = tuple(self.renderer_requests)
        for request in requests:
            request.stop.set()

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
            _check_memory_methods(stream)
            position, end = _memory_bounds(stream)
            if stream.closed or position != end or position > MAX_ENVELOPE:
                raise ValueError('unsupported_cli_memory_output')
            self.memory_position = position
            self.kind = 'bounded-memory'
            return
        if (sys.platform != 'linux' or type(stream) is not io.TextIOWrapper
                or stream.closed or stream.encoding.lower().replace('_', '-') not in {'utf-8', 'ascii'}):
            raise ValueError('unsupported_cli_output_stream')
        buffer = stream.buffer
        raw = buffer.raw if type(buffer) is io.BufferedWriter else buffer
        if type(raw) is not io.FileIO or raw.closed:
            raise ValueError('unsupported_cli_output_buffer')
        self.original_fd = io.FileIO.fileno(raw)
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
            if fd == self.original_fd:
                owner.close()
                raise RuntimeError('cli_output_reopen_reused_original_descriptor')
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
            if (raw.closed or io.FileIO.fileno(raw) != self.original_fd
                    or _identity(os.fstat(self.original_fd)) != self.original_identity
                    or fcntl.fcntl(self.original_fd, fcntl.F_GETFL) != self.original_flags
                    or _identity(os.fstat(self.fd)) != self.original_identity
                    or not fcntl.fcntl(self.fd, fcntl.F_GETFL) & os.O_NONBLOCK):
                raise RuntimeError('original_cli_output_descriptor_changed')
        else:
            stream = self.owner.stream
            _check_memory_methods(stream)
            position, end = _memory_bounds(stream)
            if (stream.closed or position != self.memory_position
                    or end != self.memory_position
                    or self.memory_position > 2 * MAX_ENVELOPE):
                raise RuntimeError('original_cli_memory_output_changed')

    def write(self, chunk):
        self.check()
        self.owner.check_effect()
        if self.fd is None:
            # Call the immutable C descriptor directly, never an instance hook.
            count = io.StringIO.write(self.owner.stream, chunk.decode('ascii'))
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
            or owner.console is not turn['console'] or not owner.matches_stream(turn['stream'])
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


class _RendererRequest:
    """One native Application task, joined by its original ledger caller.

    Completion is published only by the native task's done callback, after all
    finally blocks. Cancelling a concurrent Future is never a cleanup receipt.
    """
    def __init__(self, owner, deadline, check, stop):
        from concurrent.futures import Future
        self.owner = owner
        self.deadline = deadline
        self.check = check
        self.caller_stop = stop
        self.stop = threading.Event()
        self.done = Future()
        self.task = None
        self.started = False
        self.terminal_entered = False
        self.terminal_restored = False
        self.effects = 0
        self.outcome = None

    def check_effect(self):
        if (self.owner.closed.is_set() or self.stop.is_set()
                or asyncio.get_running_loop().time() >= self.deadline):
            raise RuntimeError('original_cli_renderer_effect_stopped')

    def guard(self):
        self.owner.check()
        app = self.owner.renderer_app
        if (self.stop.is_set() or self.caller_stop()
                or asyncio.get_running_loop().time() >= self.deadline
                or not app.is_running or app.output is not self.owner.renderer_output
                or app.renderer.output is not self.owner.renderer_output):
            raise RuntimeError('original_cli_renderer_stopped')
        self.check()
        self.check_effect()


def _bounded_vt100(owner, original):
    # Native supported Output injection; inherit actual VT100 encoding/control
    # sequences. Replace only its buffered flush. No native flush_stdout call,
    # original stream flush, F_SETFL, proxy queue or writer thread is used here.
    from prompt_toolkit.output.vt100 import Vt100_Output
    if type(original) is not Vt100_Output or original.stdout is not owner.stream:
        raise OutputRejected('unsupported_native_renderer_output')
    import types
    getter = original._get_size
    codes = [c for c in Vt100_Output.from_pty.__func__.__code__.co_consts
             if isinstance(c, types.CodeType) and c.co_name == 'get_size']
    if (type(getter) is not types.FunctionType or not any(getter.__code__ is c for c in codes)
            or getter.__globals__ is not Vt100_Output.from_pty.__func__.__globals__
            or getter.__closure__ is None or len(getter.__closure__) != 1
            or getter.__closure__[0].cell_contents is not owner.stream):
        raise OutputRejected('unsupported_native_renderer_geometry_callback')
    class BoundedVt100Output(Vt100_Output):
        def __init__(self):
            super().__init__(owner.stream, original._get_size, term=original.term,
                             default_color_depth=original.default_color_depth,
                             enable_bell=original.enable_bell, enable_cpr=False)
            self.request = None
            self._friday_owner = owner
            self.buffer_bytes = 0

        def write_raw(self, text):
            if type(text) is not str:
                raise ValueError('native_renderer_text_required')
            size = len(text.encode('utf-8'))
            if self.buffer_bytes + size > MAX_ENVELOPE:
                self._buffer.clear(); self.buffer_bytes = 0
                owner.close()
                raise OutputCleanupUnconfirmed('native_renderer_buffer_limit')
            owner.check()
            if self.request is not None:
                self.request.guard()
            self._buffer.append(text); self.buffer_bytes += size

        def write(self, text):
            self.write_raw(text.replace('\x1b', '?'))

        def flush(self):
            # Detach before any effect: failed/partial flush cannot replay.
            text = ''.join(self._buffer)
            self._buffer.clear(); self.buffer_bytes = 0
            if not text:
                return
            request = self.request
            if request is not None:
                request.guard()
            lease = None
            try:
                lease = owner.acquire()
                data = text.encode('utf-8')
                if lease.fd is None:
                    lease.check()
                    owner.check_effect()
                    io.StringIO.write(owner.stream, text)
                    lease.memory_position += len(text)
                    lease.accepted += len(data)
                    if request is not None: request.effects += len(data)
                else:
                    offset = 0
                    flush_end = __import__('time').monotonic() + .02
                    calls = 0
                    # Finite CPU loop, no sleeping/retry on EAGAIN. A native
                    # renderer error stops this frontend; no queued bytes remain.
                    while offset < len(data):
                        calls += 1
                        if calls > 128 or __import__('time').monotonic() >= flush_end:
                            raise RuntimeError('native_renderer_flush_budget')
                        if request is not None: request.guard()
                        count = lease.write(data[offset:offset + WRITE_SLICE])
                        offset += count
                        if request is not None: request.effects += count
                if request is not None: request.guard()
            except BaseException:
                owner.close()
                raise
            finally:
                if lease is not None: lease.close()

    return BoundedVt100Output()


class _RendererSession:
    def __init__(self, cli):
        self.owner = getattr(cli, '_friday_cli_output', None)
        self.session = None

    def __enter__(self):
        if self.owner is None or self.owner.cap is None:
            return self
        from prompt_toolkit.application.current import create_app_session, get_app_session
        self.owner.check()
        bounded = _bounded_vt100(self.owner, get_app_session().output)
        self.owner.renderer_output = bounded
        self.session = create_app_session(output=bounded)
        self.session.__enter__()
        return self

    def __exit__(self, *args):
        if self.session is None: return
        self.owner.close()
        # Application.run() awaits its native background tasks before returning.
        with self.owner.renderer_guard:
            unfinished = [r for r in self.owner.renderer_requests if not r.done.done()]
        try:
            if unfinished:
                raise OutputCleanupUnconfirmed('native_renderer_join_unconfirmed')
        finally:
            self.session.__exit__(*args)


def renderer_session(cli):
    return _RendererSession(cli)


def bind_renderer_application(cli, app):
    owner = getattr(cli, '_friday_cli_output', None)
    if owner is None or owner.renderer_output is None: return
    owner.check()
    if (owner.renderer_app is not None or app.output is not owner.renderer_output
            or app.renderer.output is not owner.renderer_output):
        raise RuntimeError('native_renderer_injection_lost')
    owner.renderer_app = app


async def write_renderer_envelope(owner, payload, *, deadline, check, stop):
    """Dispatch once into the existing owner loop and join the native task.

    A stop token guards queued start and every renderer/document effect. No
    callback can write after an unconfirmed join: the token remains revoked.
    Native Application owns/cancels the task at exit; original ledger waits for
    actual done. Context/capability is copied, never reconstructed from records.
    """
    from contextvars import copy_context
    from prompt_toolkit.application.current import set_app
    from prompt_toolkit.application.run_in_terminal import in_terminal
    loop = asyncio.get_running_loop()
    app = owner.renderer_app
    if (app is None or app.loop is None or not app.is_running
            or app.loop.is_closed() or owner.renderer_output is None):
        raise OutputRejected('original_cli_renderer_not_running')
    if type(payload) is not bytes or len(payload) > MAX_ENVELOPE:
        raise OutputRejected('cli_output_envelope_limit')
    request = _RendererRequest(owner, deadline, check, stop)
    with owner.renderer_guard:
        owner.check(); owner.renderer_requests.add(request)
    context = copy_context()

    async def run():
        request.started = True
        with set_app(app):
            request.guard()
            # Pre-entry wait is shielded. Native in_terminal otherwise cancels
            # its predecessor Future and can strand its newly published chain.
            while app._running_in_terminal_f is not None and not app._running_in_terminal_f.done():
                request.guard()
                await asyncio.shield(app._running_in_terminal_f)
            request.guard()
            sink = owner.renderer_output
            if sink.request is not None:
                raise RuntimeError('native_renderer_request_busy')
            sink.request = request
            previous_chain = app._running_in_terminal_f
            own_chain = None
            try:
                # Entry can erase the UI before native input cleanup is armed.
                # A native context-manager failure leaves its frontend unsafe
                # even if the chain Future is completed by its finally block.
                request.terminal_entered = True
                async with in_terminal():
                    own_chain = app._running_in_terminal_f
                    request.guard()
                    # Reuse the original finite writer on this same owner loop.
                    await write_console_envelope(owner, payload, deadline=deadline,
                              check=request.guard, stop=request.stop.is_set)
                request.terminal_restored = True
                request.guard()  # Native reset/redraw/close precede acknowledgement.
                return 'bounded-owner-renderer-write'
            finally:
                # Native in_terminal's erase happens before its try/finally.
                # With CPR disabled and a completed predecessor, that entry
                # has no await; retire only our own pre-entry failed chain.
                if own_chain is None and app._running_in_terminal_f is not previous_chain:
                    own_chain = app._running_in_terminal_f
                if own_chain is not None and not own_chain.done():
                    own_chain.set_result(None)
                sink._buffer.clear(); sink.buffer_bytes = 0
                sink.request = None

    async def owned_run():
        try:
            request.outcome = (True, await run())
        except BaseException as exc:
            if request.terminal_entered and not request.terminal_restored:
                # Revoke subsequent effects; this is not a cleanup receipt or
                # a substitute for the native task's actual joined completion.
                owner.close()
            request.outcome = (False, exc)

    def completed(task):
        try:
            if request.outcome is None:
                request.done.set_result((False, OutputCleanupUnconfirmed('native_renderer_outcome_missing')))
            elif request.outcome[0]:
                request.done.set_result(request.outcome)
            else:
                request.done.set_result(request.outcome)
        finally:
            with owner.renderer_guard: owner.renderer_requests.discard(request)

    def start():
        if request.stop.is_set() or owner.closed.is_set():
            request.done.set_result((False, OutputRejected('native_renderer_cancelled_before_start')))
            with owner.renderer_guard: owner.renderer_requests.discard(request)
            return
        coro = owned_run()
        try:
            request.task = app.create_background_task(coro)
            request.task.add_done_callback(completed)
        except BaseException as exc:
            coro.close(); request.done.set_result((False, exc))
            with owner.renderer_guard: owner.renderer_requests.discard(request)

    wrapped = asyncio.wrap_future(request.done)
    try:
        app.loop.call_soon_threadsafe(start, context=context)
        # Reserve final join within the same supplied deadline, never +30 anew.
        remaining = deadline - loop.time()
        if remaining <= 0: raise TimeoutError('native_renderer_deadline')
        async with asyncio.timeout(max(0, remaining - min(.25, remaining / 4))):
            success, value = await asyncio.shield(wrapped)
            if not success: raise value
            return value
    except BaseException:
        request.stop.set()
        def cancel():
            if request.task is not None and not request.task.done(): request.task.cancel()
        try: app.loop.call_soon_threadsafe(cancel)
        except RuntimeError: pass
        try:
            async with asyncio.timeout(max(0, deadline - loop.time())):
                await asyncio.shield(wrapped)
        except (asyncio.CancelledError, Exception):
            if not request.done.done():
                owner.close()
                raise OutputCleanupUnconfirmed('native_renderer_join_unconfirmed') from None
        raise
