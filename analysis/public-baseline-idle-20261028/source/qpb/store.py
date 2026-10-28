"""One run directory, one lock, atomic attempt records."""

from __future__ import annotations

import fcntl
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
