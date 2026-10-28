"""One run directory, one lock, atomic attempt records."""

from __future__ import annotations

import fcntl
import hashlib
import json
import stat
import os
import re
from pathlib import Path

from qpb.atomic import (
    append_jsonl,
    atomic_write_json,
    load_json_result,
    read_json,
    recover_jsonl_tail,
)

_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}\Z")
COMPLETE_OUTCOMES = {"complete"}
TECHNICAL_LOSS = "technical_loss"


def technical_loss_retry_authorized(record: dict) -> bool:
    """Accept only a protected, hash-bound reconciliation for this exact loss.

    This does not discover or clear unknown requests. The one-off Root recovery
    must first confirm the old request is no longer active and explicitly permit
    its next attempt. The lost result and its cost remain unknown.
    """
    try:
        recovery = record["recovery"]
        if not isinstance(recovery, dict):
            return False
        if (record.get("outcome") != TECHNICAL_LOSS
                or record.get("state") != "LOST_RESPONSE_AFTER_CLIENT_REBOOT"
                or record.get("sent") is not True
                or recovery.get("result_unknown") is not True
                or recovery.get("request_no_longer_active") is not True
                or recovery.get("repeat_authorized") is not True
                or recovery.get("authorized_next_attempt_n") != record["attempt_n"] + 1):
            return False
        path = Path(recovery["evidence_ref"])
        if not path.is_absolute():
            return False
        for parent in path.parents:
            st = parent.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid not in (0, os.getuid()) or st.st_mode & 0o022:
                return False
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 1 or st.st_mode & 0o077 or st.st_size > 1048576:
                return False
            with os.fdopen(os.dup(fd), "rb") as stream:
                raw = stream.read(1048577)
            after = os.fstat(fd)
            named = path.lstat()
            fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(st, k) != getattr(after, k) or getattr(st, k) != getattr(named, k) for k in fields):
                return False
        finally:
            os.close(fd)
        if hashlib.sha256(raw).hexdigest() != recovery["evidence_sha256"]:
            return False
        evidence = json.loads(raw)
        if not isinstance(evidence, dict) or evidence.get("schema") != "frw.baseline.orphan-reconciliation.v1":
            return False
        expected = {"attempt_id": record["attempt_id"], "run_id": record["permit"]["run_id"],
                    "rid": record["server_request_id"], "request_hash": record["request_hash"],
                    "generation_fingerprint": record["generation_fingerprint"],
                    "original_request_sha256": recovery["original_request_sha256"],
                    "authorized_next_attempt_n": record["attempt_n"] + 1}
        return (all(evidence.get(k) == v for k, v in expected.items())
                and evidence.get("repeat_authorized") is True
                and evidence.get("result_unknown") is True
                and evidence.get("request_no_longer_active") is True
                and evidence.get("empty_backend_verified") is True
                and evidence.get("same_serving_verified") is True)
    except (OSError, ValueError, TypeError, KeyError):
        return False


class RunIdError(ValueError):
    pass


class RunBusy(RuntimeError):
    pass


class FingerprintMismatch(RuntimeError):
    pass


def check_run_id(run_id: str) -> str:
    if not _RUN_ID.fullmatch(run_id or ""):
        raise RunIdError(f"bad run id: {run_id!r}")
    return run_id


def safe_name(text: str) -> str:
    return text.replace(":", "__").replace("/", "_")


class RunStore:
    def __init__(self, runs_root: Path, run_id: str):
        self.run_id = check_run_id(run_id)
        self.dir = runs_root / self.run_id
        self.requests = self.dir / "requests"
        self.predictions = self.dir / "predictions"
        self.reviews = self.dir / "reviews"
        self._lock_fd = None

    def exists(self) -> bool:
        return (self.dir / "manifest.json").exists()

    def ensure_dirs(self) -> None:
        for path in (self.requests, self.predictions, self.reviews):
            path.mkdir(parents=True, exist_ok=True)

    def lock(self) -> None:
        self.ensure_dirs()
        fd = os.open(self.dir / "runner.lock", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise RunBusy(f"run {self.run_id} уже держит другой исполнитель") from exc
        self._lock_fd = fd

    def unlock(self) -> None:
        if self._lock_fd is None:
            return
        fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        os.close(self._lock_fd)
        self._lock_fd = None

    def write_manifest(self, obj: dict) -> None:
        atomic_write_json(self.dir / "manifest.json", obj)

    def manifest(self) -> dict:
        return read_json(self.dir / "manifest.json")

    def write_resolved(self, obj: dict) -> None:
        atomic_write_json(self.dir / "profile-resolved.json", obj)

    def event(self, obj: dict) -> None:
        append_jsonl(self.dir / "events.jsonl", obj)

    def write_progress(self, obj: dict) -> None:
        atomic_write_json(self.dir / "progress.json", obj)

    def progress(self) -> dict:
        path = self.dir / "progress.json"
        if not path.exists():
            return {}
        loaded = load_json_result(path)
        if not loaded["ok"]:
            return {"state": "INCOMPLETE", "progress_record": "partial"}
        return loaded["value"]

    def write_control(self, pause: bool = False, stop: bool = False) -> None:
        current = self.control()
        current["pause"] = bool(pause) or current.get("pause", False) if pause else current.get("pause", False)
        if stop:
            current["stop"] = True
        if pause:
            current["pause"] = True
        if not pause and not stop:
            pass
        atomic_write_json(self.dir / "control.json", current)

    def set_control(self, *, pause: bool, stop: bool) -> None:
        atomic_write_json(self.dir / "control.json", {"pause": pause, "stop": stop})

    def control(self) -> dict:
        path = self.dir / "control.json"
        if not path.exists():
            return {"pause": False, "stop": False}
        loaded = load_json_result(path)
        if not loaded["ok"]:
            return {"pause": True, "stop": False, "control_record": "partial"}
        return loaded["value"]

    def request_path(self, attempt_id: str) -> Path:
        return self.requests / f"{safe_name(attempt_id)}.json"

    def prediction_path(self, benchmark: str, task_id: str) -> Path:
        return self.predictions / f"{benchmark}__{safe_name(task_id)}.json"

    def review_path(self, benchmark: str, task_id: str) -> Path:
        return self.reviews / f"{benchmark}__{safe_name(task_id)}.json"

    def save_request(self, record: dict) -> None:
        atomic_write_json(self.request_path(record["attempt_id"]), record)

    def save_prediction(self, record: dict) -> None:
        atomic_write_json(self.prediction_path(record["benchmark"], record["task_id"]), record)

    def read_prediction(self, benchmark: str, task_id: str) -> dict:
        return load_json_result(self.prediction_path(benchmark, task_id))

    def prediction_complete(self, benchmark: str, task_id: str) -> bool:
        loaded = self.read_prediction(benchmark, task_id)
        if not loaded["ok"]:
            return False
        value = loaded["value"]
        return value.get("outcome") in COMPLETE_OUTCOMES and bool(value.get("finish_reason"))

    def iter_request_files(self):
        if not self.requests.exists():
            return
        for path in sorted(self.requests.glob("*.json")):
            yield path

    def reconcile(self) -> dict:
        """Mark partial and unknown records. Do not turn them into success."""
        notes = {"partial": [], "outcome_unknown": [], "events_tail": None}
        notes["events_tail"] = recover_jsonl_tail(self.dir / "events.jsonl")
        if notes["events_tail"].get("dropped"):
            self.event({"event": "journal_tail_recovered", "success": False})
        for path in self.iter_request_files():
            loaded = load_json_result(path)
            if not loaded["ok"]:
                marker = {
                    "attempt_id": path.stem,
                    "state": "PARTIAL_RECORD",
                    "outcome": "PARTIAL_RECORD",
                    "success": False,
                    "sent": True,
                    "detail": loaded.get("error"),
                }
                partial_path = path.with_suffix(".partial.json")
                path.replace(partial_path)
                atomic_write_json(path, marker)
                notes["partial"].append(path.name)
                continue
            record = loaded["value"]
            if record.get("state") == "SENDING":
                benchmark = record.get("benchmark")
                task_id = record.get("task_id")
                complete = False
                if benchmark and task_id:
                    complete = self.prediction_complete(benchmark, task_id)
                if not complete:
                    record["state"] = "OUTCOME_UNKNOWN"
                    record["outcome"] = "OUTCOME_UNKNOWN"
                    record["success"] = False
                    record["note"] = "Запрос мог остаться активным на сервере. Повторный POST не делается."
                    self.save_request(record)
                    notes["outcome_unknown"].append(record.get("attempt_id"))
        if self.predictions.exists():
            for path in self.predictions.glob("*.json"):
                loaded = load_json_result(path)
                if loaded["ok"]:
                    continue
                marker = {
                    "outcome": "PARTIAL_RECORD",
                    "success": False,
                    "finish_reason": None,
                    "detail": loaded.get("error"),
                    "task_id": path.stem,
                }
                path.with_suffix(".partial.json").write_bytes(path.read_bytes())
                atomic_write_json(path, marker)
                notes["partial"].append(path.name)
        return notes

    def latest_attempt(self, benchmark: str, task_id: str) -> dict | None:
        found = []
        prefix = f"{benchmark}__{safe_name(task_id)}__"
        for path in self.iter_request_files():
            if path.name.startswith(prefix):
                loaded = load_json_result(path)
                if loaded["ok"]:
                    found.append(loaded["value"])
        if not found:
            return None
        return max(found, key=lambda record: int(record.get("attempt_n") or 0))

    def attempt_blocks_send(self, record: dict | None) -> str | None:
        """Return a reason when another POST of this task is forbidden."""
        if record is None:
            return None
        outcome = record.get("outcome") or record.get("state")
        if outcome == TECHNICAL_LOSS:
            return None if technical_loss_retry_authorized(record) else "technical_loss_not_authorized"
        if outcome in {"OUTCOME_UNKNOWN", "PARTIAL_RECORD"}:
            return outcome
        if record.get("state") == "SENDING":
            return "SENDING"
        if outcome == "complete":
            return "complete"
        if record.get("sent") is True and outcome == "transport_error":
            return "transport_error_sent"
        if outcome == "protocol_diagnostic":
            return "protocol_diagnostic"
        return None
