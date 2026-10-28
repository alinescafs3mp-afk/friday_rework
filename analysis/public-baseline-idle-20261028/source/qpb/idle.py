"""Small local admission state shared by Friday clients and this runner.

No network, service, heartbeat or automatic removal of reservations. A failed
foreground registration never stops Friday; a durable fault closes background.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid

from qpb.atomic import atomic_write_json

POLICY = {
    "version": "idle-v1", "selection": "pinned-pilot-first-then-order-skip-completed-defer-after-3",
    "idle_grace_seconds": 60, "max_background_inflight": 1,
    "cancel_confirm_timeout_seconds": 10,
    "max_foreground_interruptions_per_task": 3,
    "max_interrupted_attempt_wall_seconds": 7200, "authorization_window_days": 7,
}


class IdleBlocked(RuntimeError):
    pass


def endpoint_key(base_url):
    parts = urlsplit(base_url)
    # Model aliases and run IDs must never create a second admission slot.
    origin = f"{parts.scheme}://{parts.hostname}:{parts.port or (443 if parts.scheme == 'https' else 80)}"
    return hashlib.sha256(origin.encode()).hexdigest()[:24]


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


class Coordinator:
    def __init__(self, directory, *, clock=time.time):
        self.dir = Path(directory)
        self.clock = clock

    def _safe_dir(self):
        if self.dir.is_symlink():
            raise IdleBlocked("coordinator directory is a symlink")
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        st = self.dir.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise IdleBlocked("coordinator must be owner-only")

    @contextmanager
    def transaction(self):
        self._safe_dir()
        fd = os.open(self.dir / "state.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        until = time.monotonic() + 0.2
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= until:
                        raise IdleBlocked("coordinator lock unavailable")
                    time.sleep(0.005)
            path = self.dir / "state.json"
            if path.is_symlink():
                raise IdleBlocked("coordinator state is a symlink")
            if path.exists():
                state = json.loads(path.read_text())
            else:
                state = {"version": 1, "boot_id": boot_id(), "foreground": {},
                         "inflight": None, "last_activity": self.clock(),
                         "blocks": ["COVERAGE_UNVERIFIED", "CANCEL_UNVERIFIED"],
                         "coverage": None, "cancellation": None}
            before = json.dumps(state, sort_keys=True) if path.exists() else None
            if state["boot_id"] != boot_id():
                if "RECOVERY_REQUIRED" not in state["blocks"]:
                    state["blocks"].append("RECOVERY_REQUIRED")
            try:
                yield state
            finally:
                if before != json.dumps(state, sort_keys=True):
                    atomic_write_json(path, state)
                    os.chmod(path, 0o600)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def fault(self, reason):
        # Independent of the state lock. Never erase automatically.
        try:
            self._safe_dir()
            fd = os.open(self.dir / "FAULT", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, (str(reason)[:160] + "\n").encode())
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    def foreground_begin(self, client, task_id, *, resource="qwen", parent=None):
        token = uuid.uuid4().hex
        try:
            with self.transaction() as state:
                state["foreground"][token] = {"client": client, "task_id": task_id,
                    "resource": resource, "parent": parent, "at": self.clock()}
                state["last_activity"] = self.clock()
                if state["inflight"]:
                    state["inflight"].setdefault("foreground_at", self.clock())
            return token
        except Exception as exc:
            self.fault(type(exc).__name__)
            return None  # Friday remains available.

    def foreground_end(self, token, *, outcome_known=True):
        if token is None:
            return
        try:
            with self.transaction() as state:
                if token not in state["foreground"]:
                    raise IdleBlocked("unknown foreground reservation")
                if outcome_known:
                    del state["foreground"][token]
                else:
                    state["foreground"][token]["outcome"] = "OUTCOME_UNKNOWN"
                state["last_activity"] = self.clock()
        except Exception as exc:
            self.fault(type(exc).__name__)

    def certify(self, *, coverage, cancellation):
        """Integrator only, after checking actual clients and live handoff.

        This records evidence; it is not user authorization or a live test.
        """
        if not coverage.get("all_clients") or not coverage.get("whole_tasks") or not coverage.get("embeddings"):
            raise IdleBlocked("AUTOMATIC_MODE_BLOCKED: incomplete consumer coverage")
        if not all(cancellation.get(k) for k in ("installed_source", "rid_before_prefill", "terminal_evidence", "live_handoff")):
            raise IdleBlocked("AUTOMATIC_MODE_BLOCKED: cancellation unverified")
        with self.transaction() as state:
            if state["inflight"] or state["foreground"]:
                raise IdleBlocked("cannot certify with existing reservations")
            state["coverage"], state["cancellation"] = coverage, cancellation
            state["blocks"] = [b for b in state["blocks"] if b not in {"COVERAGE_UNVERIFIED", "CANCEL_UNVERIFIED"}]
            state["last_activity"] = self.clock()

    def snapshot(self):
        with self.transaction() as state:
            result = json.loads(json.dumps(state))
        result["observation_age_s"] = max(0, self.clock() - result["last_activity"])
        if (self.dir / "FAULT").exists():
            result["blocks"].append("COORDINATOR_FAULT")
        return result

    def reserve(self, run_id, attempt_id, request_hash, fingerprint, *, policy=POLICY, manual=False):
        with self.transaction() as state:
            reasons = [b for b in state["blocks"] if not manual or b not in {"COVERAGE_UNVERIFIED", "CANCEL_UNVERIFIED"}]
            if (self.dir / "FAULT").exists():
                reasons.append("COORDINATOR_FAULT")
            if state["foreground"]:
                reasons.append("FOREGROUND")
            if state["inflight"]:
                reasons.append("INFLIGHT_OR_RECOVERY_REQUIRED")
            if not manual and self.clock() - state["last_activity"] < policy["idle_grace_seconds"]:
                reasons.append("COOLDOWN")
            if reasons:
                raise IdleBlocked(",".join(reasons))
            permit = {"run_id": run_id, "attempt_id": attempt_id, "rid": "qpb-" + uuid.uuid4().hex,
                      "owner": uuid.uuid4().hex, "request_hash": request_hash,
                      "generation_fingerprint": fingerprint, "state": "RESERVED", "reserved_at": self.clock()}
            state["inflight"] = permit
            return dict(permit)

    def dispatch(self, permit, *, manual=False):
        with self.transaction() as state:
            current = self._owned(state, permit)
            if current["state"] != "RESERVED":
                raise IdleBlocked("permit already crossed the dispatch boundary")
            blocks = [b for b in state["blocks"] if not manual or b not in {"COVERAGE_UNVERIFIED", "CANCEL_UNVERIFIED"}]
            if state["foreground"] or blocks or (self.dir / "FAULT").exists():
                state["inflight"] = None  # RESERVED has never crossed send boundary.
                raise IdleBlocked("foreground or fault before dispatch")
            current["state"] = "DISPATCHING"
            current["dispatch_at"] = self.clock()

    @staticmethod
    def _owned(state, permit):
        item = state["inflight"]
        if not item or any(item.get(k) != permit.get(k) for k in ("owner", "rid", "attempt_id", "run_id")):
            raise IdleBlocked("request is not owned by this benchmark attempt")
        return item

    def cancellation(self, permit):
        with self.transaction() as state:
            item = self._owned(state, permit)
            if item["state"] not in {"DISPATCHING", "CANCEL_REQUESTED"}:
                raise IdleBlocked("cancel requires an owned dispatched request")
            if item.get("cancel_at") is not None:
                return False
            item["state"] = "CANCEL_REQUESTED"
            item["cancel_at"] = self.clock()
            return True

    def terminal(self, permit, outcome, *, evidence):
        if outcome not in {"complete", "INTERRUPTED_BY_FOREGROUND", "CANCELLED_BY_STOP", "NOT_SENT"} or not evidence:
            raise IdleBlocked("terminal confirmation required; cancel HTTP 200 is insufficient")
        with self.transaction() as state:
            item = self._owned(state, permit)
            if outcome == "NOT_SENT" and item["state"] != "RESERVED":
                raise IdleBlocked("dispatched request cannot be declared unsent")
            state["last_terminal"] = dict(item, outcome=outcome, evidence=evidence, terminal_at=self.clock())
            state["inflight"] = None
            state["last_activity"] = self.clock()

    def unknown(self, permit, reason):
        with self.transaction() as state:
            item = self._owned(state, permit)
            item["state"] = "OUTCOME_UNKNOWN"
            item["reason"] = str(reason)[:200]


@contextmanager
def foreground(directory, client, task_id, *, resource="qwen", parent=None):
    """Wrap the whole agent task; child HTTP calls may have child reserves.

    Exceptions preserve the reserve: a lost HTTP response is not server idle.
    Explicit caller reconciliation may release it later.
    """
    coordinator = Coordinator(directory)
    token = coordinator.foreground_begin(client, task_id, resource=resource, parent=parent)
    try:
        yield token
    except BaseException:
        coordinator.foreground_end(token, outcome_known=False)
        raise
    else:
        coordinator.foreground_end(token)
