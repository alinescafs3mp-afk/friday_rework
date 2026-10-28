"""Optional small bridge for the existing Friday turn/aux/worker boundaries.

Root installs call sites; importing this file alone instruments nothing. No
network or server control. Reservations live in the existing baseline admission
file, not in protected Friday receipts. Missing/faulty coordination never raises
into Friday. A worker is released only after its existing quiescence evidence.
"""
import hashlib
import json
import os
import uuid
import functools
import inspect
from urllib.parse import urlsplit

from qpb.idle import Coordinator

ENV = "FRIDAY_BASELINE_COORDINATOR_DIR"


def coordinator():
    directory = os.environ.get(ENV)
    return Coordinator(directory) if directory else None


def begin(client, task_id):
    try:
        c = coordinator()
        return c.foreground_begin(client, str(task_id), resource="spark-whole-task") if c else None
    except Exception:
        return None  # The native bridge independently marks the canonical fault.


def end(token, *, outcome_known=True):
    try:
        c = coordinator()
        if c:
            c.foreground_end(token, outcome_known=outcome_known)
        return True
    except Exception:
        return False


def tracked(client):
    """Whole synchronous operation, including every intervening tool call."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            token = begin(client, uuid.uuid4().hex)
            try:
                result = function(*args, **kwargs)
            except BaseException:
                end(token, outcome_known=False)
                raise
            end(token)
            return result
        return wrapped
    return decorate


def atracked(client):
    """Async equivalent; foreground never waits for background cancellation."""
    def decorate(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            token = begin(client, uuid.uuid4().hex)
            try:
                result = await function(*args, **kwargs)
            except BaseException:
                end(token, outcome_known=False)
                raise
            end(token)
            return result
        return wrapped
    return decorate


def _worker_key(row):
    # Use the already admitted owner/task identity, never text supplied by a
    # model, and retain it across async controller calls and process restarts.
    data = json.dumps({"owner": row["owner"], "task": row["existing_task_id"],
                       "admission_hash": row["admission_hash"]}, sort_keys=True, separators=(",", ":"))
    return "friday-worker-" + hashlib.sha256(data.encode()).hexdigest()


def observe_worker(row, *, start=False):
    """Observe only a row already validated by the existing Host consumer.

    A completed NativeObservation alone is insufficient. Host._retain_settlement
    already verifies and persists terminal AND quiescence before release.
    """
    c = coordinator()
    if c is None:
        return
    try:
        key = _worker_key(row)
        quiet = row.get("host", {}).get("quiescence") is not None
        terminal = row.get("host", {}).get("terminal") is not None
        with c.transaction() as state:
            if quiet and terminal:
                if key in state["foreground"]:
                    del state["foreground"][key]
                    state["last_activity"] = c.clock()
                return
            if key in state["foreground"] or not start:
                return
            state["foreground"][key] = {"client": "friday-worker", "task_id": row["existing_task_id"],
                "resource": "spark-worker-model-and-embedding", "worker_kind": row["worker_kind"], "at": c.clock()}
            state["last_activity"] = c.clock()
            if state["inflight"]:
                state["inflight"].setdefault("foreground_at", c.clock())
    except Exception as exc:
        c.fault("worker_adapter:" + type(exc).__name__)


def start_worker(row):
    """Only current admitted prepare/start/schedule boundaries create a reserve.

    Historical UNKNOWN rows are never promoted into resource claims by reads.
    On startup Root separately reconciles real resources before admission.
    """
    observe_worker(row, start=True)


def session_guard_change(group, old_guard, new_guard, pending):
    """Mirror the existing native session guard/queue atomically; no TTL."""
    c = coordinator()
    if c is None:
        return
    try:
        key = "friday-session-" + group
        with c.transaction() as state:
            item = state["foreground"].get(key)
            guards = set((item or {}).get("guards", []))
            if old_guard:
                guards.discard(old_guard)
            if new_guard:
                guards.add(new_guard)
            if not guards and not pending:
                if item is not None:
                    del state["foreground"][key]
                    state["last_activity"] = c.clock()
                return
            state["foreground"][key] = {"client": "friday-native-session-queue", "task_id": group,
                "resource": "spark-pending-and-active-task", "guards": sorted(guards),
                "pending": bool(pending), "at": (item or {}).get("at", c.clock())}
            state["last_activity"] = c.clock()
            if state["inflight"]:
                state["inflight"].setdefault("foreground_at", c.clock())
    except Exception as exc:
        c.fault("session_adapter:" + type(exc).__name__)


_TERMINAL = {"stop", "length", "tool_calls", "function_call", "abort", "content_filter"}


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


class _PhysicalReservation:
    def __init__(self, token, count):
        self.token, self.count, self.finished, self.released = token, count, set(), False

    def accept(self, response):
        try:
            for choice in _get(response, "choices", []) or []:
                if _get(choice, "finish_reason") in _TERMINAL:
                    self.finished.add(int(_get(choice, "index", 0)))
        except Exception:
            pass  # No terminal proof is more conservative than guessing one.

    def release(self):
        if not self.released:
            self.released = True
            end(self.token, outcome_known=all(i in self.finished for i in range(self.count)))


class _SyncStream:
    def __init__(self, stream, reservation):
        self._stream, self._reservation = stream, reservation
        self._iterator = iter(stream)

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._iterator)
        except BaseException:
            self._reservation.release()
            raise
        self._reservation.accept(chunk)
        return chunk

    def close(self):
        try:
            return self._stream.close()
        finally:
            self._reservation.release()

    def __enter__(self):
        if hasattr(self._stream, "__enter__"):
            self._stream.__enter__()
        return self

    def __exit__(self, *args):
        try:
            return self._stream.__exit__(*args)
        finally:
            self._reservation.release()


class _AsyncStream:
    def __init__(self, stream, reservation):
        self._stream, self._reservation = stream, reservation
        self._iterator = stream.__aiter__()

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            chunk = await self._iterator.__anext__()
        except BaseException:
            self._reservation.release()
            raise
        self._reservation.accept(chunk)
        return chunk

    async def close(self):
        try:
            result = self._stream.close()
            if inspect.isawaitable(result):
                return await result
            return result
        finally:
            self._reservation.release()

    aclose = close

    async def __aenter__(self):
        if hasattr(self._stream, "__aenter__"):
            await self._stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        try:
            return await self._stream.__aexit__(*args)
        finally:
            self._reservation.release()


def physical_create(client, request):
    """One exact native SDK create; swallowed outer errors cannot clear this.

    No request mutation or retry. The native client already has max_retries=0.
    Hold streaming calls through consumption, not merely HTTP headers.
    """
    def fault(phase):
        try:
            c = coordinator()
            if c:
                c.fault("physical_adapter:" + phase)
        except Exception:
            pass
    try:
        parts = urlsplit(str(getattr(client, "base_url", "")))
        competing = parts.hostname == "192.0.2.195" and parts.port == 30000
        reservation = _PhysicalReservation(begin("friday-physical-http", uuid.uuid4().hex), int(request.get("n") or 1)) if competing else None
    except (Exception, SystemExit):
        fault("before_create")
        return client.chat.completions.create(**request)
    if reservation is None:
        return client.chat.completions.create(**request)
    def bind(response):
        if request.get("stream"):
            return _AsyncStream(response, reservation) if hasattr(response, "__aiter__") else _SyncStream(response, reservation)
        reservation.accept(response)
        reservation.release()
        return response
    def safe_bind(response):
        try:
            return bind(response)
        except (Exception, SystemExit):
            # A valid model result must survive a broken optional adapter.
            # Keep the same object; never call create again after acceptance.
            reservation.release()
            fault("after_create")
            return response
    try:
        response = client.chat.completions.create(**request)
    except BaseException:
        reservation.release()
        raise
    if inspect.isawaitable(response):
        async def await_response():
            try:
                original = await response
            except BaseException:
                reservation.release()
                raise
            return safe_bind(original)
        return await_response()
    return safe_bind(response)
