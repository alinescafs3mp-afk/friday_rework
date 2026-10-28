"""Live generation loop. Refuses before any HTTP client exists without --allow-live."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from qpb.corpus import get_corpus
from qpb.endpoint import MissingAPIKey, alias, api_key, redact_headers
from qpb.estimate import eta_for_remaining, window_blocks
from qpb.extract import split_final
from qpb.fingerprints import generation_fingerprint
from qpb.errors import OutcomeUnknownError, ProtocolDiagnostic, TransportError
from qpb.pins import CORE_TOTAL, ESTIMATE_PRIOR_S, PROFILE_ID
from qpb.profile import generation_body
from qpb.store import FingerprintMismatch, RunBusy, RunStore

CONTINUABLE = {"PAUSED", "STOPPED", "INCOMPLETE", "PILOT_DONE", "RUNNING"}


class RunRefused(RuntimeError):
    pass


def live_permitted(allow_live: bool, authorization: dict | None = None) -> bool:
    """authorization.json is ignored. Only an explicit flag passes this check."""
    del authorization
    return bool(allow_live)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _scope(corpus, pilot_only: bool):
    tasks = []
    for benchmark in ("ifbench", "gpqa", "lcb"):
        chosen = set(corpus.pilot[benchmark]) if pilot_only else None
        for task_id in corpus.order[benchmark]:
            if chosen is not None and task_id not in chosen:
                continue
            tasks.append((benchmark, task_id))
    return tasks


def _idle_scope(corpus, pilot_only):
    pilot = _scope(corpus, True)
    if pilot_only:
        return pilot
    chosen = set(pilot)
    return pilot + [task for task in _scope(corpus, False) if task not in chosen]


def _summarize(store: RunStore, corpus, pilot_only: bool) -> dict:
    attempts = 0
    errors = 0
    truncations = 0
    active = 0.0
    walls = {"ifbench": [], "gpqa": [], "lcb": []}
    for path in store.iter_request_files():
        from qpb.atomic import load_json_result

        loaded = load_json_result(path)
        if not loaded["ok"]:
            errors += 1
            continue
        record = loaded["value"]
        attempts += 1
        wall = record.get("wall_s")
        if isinstance(wall, (int, float)):
            active += float(wall)
            bench = record.get("benchmark")
            if bench in walls:
                walls[bench].append(float(wall))
        if record.get("truncated"):
            truncations += 1
        if record.get("outcome") in {"transport_error", "OUTCOME_UNKNOWN", "protocol_diagnostic", "PARTIAL_RECORD"}:
            errors += 1
    completed = 0
    for benchmark in ("ifbench", "gpqa", "lcb"):
        for task_id in corpus.order[benchmark]:
            if store.prediction_complete(benchmark, task_id):
                completed += 1
    return {
        "attempts": attempts,
        "errors": errors,
        "truncations": truncations,
        "active_s": active,
        "completed": completed,
        "walls": walls,
        "pilot_only": pilot_only,
    }


def _progress_line(progress: dict) -> str:
    return (
        f"run={progress['run_id']} profile={progress['profile']} bench={progress.get('benchmark') or '-'} "
        f"{progress['completed']}/{progress['expected']} attempts={progress['attempts']} "
        f"errors={progress['errors']} trunc={progress['truncations']} "
        f"current={progress.get('current') or '-'} active_s={progress['active_s']:.1f} "
        f"window={progress.get('window') or '-'} eta={progress.get('eta') or '-'} "
        f"state={progress['state']}"
    )


def _per_task(walls: list[float]) -> float:
    estimate = eta_for_remaining(1, walls)
    return float(estimate.get("per_task_s") or ESTIMATE_PRIOR_S)


def _format_eta(corpus, store: RunStore, walls: dict, pilot_only: bool) -> str:
    parts = []
    for benchmark in ("ifbench", "gpqa", "lcb"):
        ids = corpus.pilot[benchmark] if pilot_only else corpus.order[benchmark]
        left = sum(1 for task_id in ids if not store.prediction_complete(benchmark, task_id))
        estimate = eta_for_remaining(left, walls.get(benchmark) or [])
        weak = " weak" if estimate["weak"] else ""
        parts.append(
            f"{benchmark}:{left} n={estimate['n']} {estimate['low_s']:.0f}-{estimate['high_s']:.0f}s{weak}"
        )
    return " ".join(parts)


class Runner:
    def __init__(self, root, runs_root, run_id, profile, endpoint, identity, *, allow_live, pilot_only, window_hours, transport_factory, command):
        if not live_permitted(allow_live):
            raise RunRefused("нет --allow-live. HTTP-клиент не создаётся. Замер не начат.")
        self.root = root
        self.store = RunStore(runs_root, run_id)
        self.profile = profile
        self.endpoint = endpoint
        self.identity = identity
        self.pilot_only = pilot_only
        self.window_hours = window_hours
        self.transport_factory = transport_factory
        self.command = command
        self.fingerprint = generation_fingerprint(endpoint, profile, identity)
        self.corpus = None
        self.transport = None
        # The idle subclass uses the same generation loop, store and scorers.
        from qpb.idle import Coordinator, endpoint_key
        admission_root = self.store.dir.parent if endpoint.get("kind") == "fixture" else self.root / "runs"
        self.coordinator = Coordinator(admission_root / ".admission" / endpoint_key(endpoint["base_url"]))

    def execute(self) -> int:
        import fcntl
        import os
        if type(self) is not Runner:
            return self._execute()
        self.coordinator._safe_dir()
        fd = os.open(self.coordinator.dir / "worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("BLOCKED: endpoint already has a worker")
                return 2
            snapshot = self.coordinator.snapshot()
            if snapshot["inflight"] or any(b not in {"COVERAGE_UNVERIFIED", "CANCEL_UNVERIFIED"} for b in snapshot["blocks"]):
                print("RECOVERY_REQUIRED: endpoint outcome retained; no new POST")
                return 2
            return self._execute()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _execute(self) -> int:
        self.corpus = get_corpus(self.root)
        exists = self.store.exists()
        if self.command == "resume" and not exists:
            print(f"run {self.store.run_id} не найден. resume ничего не создаёт.", flush=True)
            return 2
        if exists:
            current = self.store.manifest()
            if type(self) is Runner and current.get("mode") == "idle":
                print("Use --mode idle for this run; priority policy cannot be bypassed")
                return 2
            if current.get("generation_fingerprint") != self.fingerprint:
                raise FingerprintMismatch(
                    "generation fingerprint не совпал. Этот run не смешивается с другим протоколом или другим endpoint."
                )
            decision = self._continue_decision(current)
            if decision.get("noop"):
                print(decision["noop"], flush=True)
                return 0
            if decision.get("error"):
                print(decision["error"], flush=True)
                return 2
            self.pilot_only = decision["pilot_only"]
        try:
            self.store.lock()
        except RunBusy as exc:
            print(str(exc), flush=True)
            return 2
        try:
            if not exists:
                self._create()
            else:
                self.store.reconcile()
                manifest = self.store.manifest()
                manifest["pilot_only"] = self.pilot_only
                manifest["state"] = "RUNNING"
                self.store.write_manifest(manifest)
            # Client is created only after the flag, the fingerprint, and the lock.
            factory = self.transport_factory
            if factory is None:
                from qpb.httpclient import UrllibTransport

                self.transport = UrllibTransport()
            else:
                self.transport = factory()
            # This invocation was asked to continue. A pause or stop left by
            # the previous process must not cancel the first task of this one.
            # A flag set while this loop is running still stops the next task.
            self.store.set_control(pause=False, stop=False)
            return self._loop()
        finally:
            self.store.unlock()

    def _continue_decision(self, current: dict) -> dict:
        state = current.get("state")
        if state == "COMPLETE":
            return {"error": "run уже COMPLETE. Новый протокол — новый run id."}
        if self.command == "resume" and state == "PILOT_DONE":
            return {
                "noop": (
                    "Пилот закончен. Полный прогон сам не продолжается. "
                    "Команда полного baseline: baseline run --profile public-core-v1 "
                    f"--run {self.store.run_id} --allow-live"
                )
            }
        if self.command == "resume" and state not in CONTINUABLE:
            return {"error": f"resume не принимает состояние {state}"}
        if self.command == "run" and self.pilot_only and current.get("pilot_only") is False:
            return {"error": "полный run уже начат. Повтор с --pilot-only его не сужает."}
        if state not in CONTINUABLE and state != "PILOT_DONE":
            return {"error": f"run в состоянии {state} не продолжается"}
        if self.command == "resume":
            return {"pilot_only": bool(current.get("pilot_only"))}
        return {"pilot_only": bool(self.pilot_only)}

    def _create(self) -> None:
        self.store.ensure_dirs()
        self.store.set_control(pause=False, stop=False)
        manifest = {
            "run_id": self.store.run_id,
            "kind": self.endpoint.get("kind", "model"),
            "profile": PROFILE_ID,
            "created_at": _now(),
            "generation_fingerprint": self.fingerprint,
            "endpoint_alias": alias(self.endpoint),
            "live_checked": False,
            "model": self.endpoint["model"],
            "base_url": self.endpoint["base_url"],
            "api_key_env": self.endpoint["api_key_env"],
            "state": "RUNNING",
            "pilot_only": self.pilot_only,
            "datasets": self.identity["datasets"],
        }
        self.store.write_manifest(manifest)
        self.store.write_resolved(
            {
                "profile": self.profile,
                "endpoint_alias": manifest["endpoint_alias"],
                "generation_fingerprint": self.fingerprint,
                "live_checked": False,
            }
        )
        self.store.event({"event": "run_created", "at": _now(), "pilot_only": self.pilot_only})

    def _emit(self, state: str, benchmark: str | None, current: str | None, summary: dict, deadline, started) -> dict:
        window = "-"
        if self.window_hours is not None and deadline is not None:
            elapsed = time.monotonic() - started
            left = max(0.0, deadline - time.monotonic())
            window = f"{self.window_hours}h elapsed={elapsed:.0f}s left={left:.0f}s"
        progress = {
            "run_id": self.store.run_id,
            "profile": PROFILE_ID,
            "benchmark": benchmark,
            "completed": summary["completed"],
            "expected": CORE_TOTAL,
            "attempts": summary["attempts"],
            "errors": summary["errors"],
            "truncations": summary["truncations"],
            "current": current,
            "active_s": summary["active_s"],
            "window": window,
            "eta": _format_eta(self.corpus, self.store, summary["walls"], self.pilot_only),
            "state": state,
        }
        if summary.get("tail"):
            progress["tail"] = summary["tail"]
        self.store.write_progress(progress)
        print(_progress_line(progress), flush=True)
        return progress

    def _set_state(self, state: str, **extra) -> None:
        manifest = self.store.manifest()
        manifest["state"] = state
        manifest["pilot_only"] = self.pilot_only
        manifest.update(extra)
        self.store.write_manifest(manifest)

    def _loop(self) -> int:
        started = time.monotonic()
        deadline = None if self.window_hours is None else started + float(self.window_hours) * 3600
        consecutive = 0
        limit = int(self.profile["generation"]["consecutive_transport_stop"])
        self._set_state("RUNNING")
        summary = _summarize(self.store, self.corpus, self.pilot_only)
        self._emit("RUNNING", None, None, summary, deadline, started)
        for benchmark, task_id in _scope(self.corpus, self.pilot_only):
            summary = _summarize(self.store, self.corpus, self.pilot_only)
            control = self.store.control()
            if control.get("stop"):
                self._set_state("STOPPED")
                summary = _summarize(self.store, self.corpus, self.pilot_only)
                self._emit("STOPPED", benchmark, None, summary, deadline, started)
                return 0
            if control.get("pause"):
                self._set_state("PAUSED")
                summary = _summarize(self.store, self.corpus, self.pilot_only)
                self._emit("PAUSED", benchmark, None, summary, deadline, started)
                return 0
            walls = summary["walls"].get(benchmark) or []
            per_task = _per_task(walls)
            if window_blocks(time.monotonic(), deadline, per_task):
                tail = (
                    f"возможный хвост одной задачи около {per_task:.0f}s. "
                    "Освобождение к дедлайну не обещано: cancel не вызывается."
                )
                summary = _summarize(self.store, self.corpus, self.pilot_only)
                summary["tail"] = tail
                self._set_state("PAUSED", window_tail=tail)
                self._emit("PAUSED", benchmark, None, summary, deadline, started)
                print(tail, flush=True)
                return 0
            if self.store.prediction_complete(benchmark, task_id):
                continue
            previous = self.store.latest_attempt(benchmark, task_id)
            blocked = self.store.attempt_blocks_send(previous)
            if blocked:
                continue
            attempt_n = int((previous or {}).get("attempt_n") or 0) + 1
            attempt_id = f"{benchmark}__{task_id}__a{attempt_n}"
            task = self.corpus.tasks[benchmark][task_id]
            body = generation_body(self.endpoint, self.profile, benchmark, task["messages"], attempt_id)
            try:
                key = api_key(self.endpoint)
            except MissingAPIKey as exc:
                self._set_state("INCOMPLETE", stop_reason=f"missing_api_key:{exc}")
                print(f"Нет значения env {exc}. Запрос не отправлен.", flush=True)
                return 2
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
            record = {
                "attempt_id": attempt_id,
                "attempt_n": attempt_n,
                "benchmark": benchmark,
                "task_id": task_id,
                "state": "PREPARED",
                "sent": False,
                "outcome": None,
                "body": body,
                "headers": redact_headers(headers),
                "started_at": _now(),
                "success": False,
            }
            self.store.save_request(record)
            from qpb.fingerprints import sha256_obj
            from qpb.idle import IdleBlocked
            try:
                permit = self.coordinator.reserve(self.store.run_id, attempt_id, sha256_obj(body), self.fingerprint, manual=True)
            except IdleBlocked as exc:
                self._set_state("INCOMPLETE", stop_reason=str(exc))
                return 2
            record["permit"] = permit
            sent = {"value": False}

            def mark_sending(record=record, sent=sent):
                control = self.store.control()
                if control.get("pause") or control.get("stop"):
                    self.coordinator.terminal(permit, "NOT_SENT", evidence="manual control before dispatch")
                    self._set_state("STOPPED" if control.get("stop") else "PAUSED")
                    raise IdleBlocked("manual control before dispatch")
                self.coordinator.dispatch(permit, manual=True)
                record["state"] = "SENDING"
                record["sent"] = True
                record["sending_at"] = _now()
                self.store.save_request(record)
                sent["value"] = True

            summary = _summarize(self.store, self.corpus, self.pilot_only)
            self._set_state("RUNNING")
            self._emit("RUNNING", benchmark, attempt_id, summary, deadline, started)
            try:
                outcome = self.transport.post(
                    self.endpoint["base_url"],
                    headers,
                    body,
                    float(self.profile["generation"]["request_timeout_s"]),
                    mark_sending,
                )
            except KeyboardInterrupt:
                self._interrupt(record, sent["value"])
                if sent["value"]:
                    self.coordinator.unknown(permit, "SIGINT after send")
                else:
                    self.coordinator.terminal(permit, "NOT_SENT", evidence="interrupted before dispatch")
                return 130
            except OutcomeUnknownError as exc:
                record["partial_raw_response"] = exc.partial_raw
                record["partial_response_timing"] = exc.timing
                record["server_request_id"] = exc.request_id or body.get("rid")
                self._unknown(record, str(exc))
                self.coordinator.unknown(permit, "response unknown")
                return 2
            except IdleBlocked:
                return 2
            except ProtocolDiagnostic as exc:
                self.coordinator.unknown(permit, "protocol diagnostic requires reconciliation")
                record["state"] = "PROTOCOL"
                record["outcome"] = "protocol_diagnostic"
                record["sent"] = True
                record["error"] = str(exc)[:2000]
                record["finished_at"] = _now()
                self.store.save_request(record)
                self._set_state("INCOMPLETE", stop_reason="protocol_diagnostic")
                summary = _summarize(self.store, self.corpus, self.pilot_only)
                self._emit("INCOMPLETE", benchmark, attempt_id, summary, deadline, started)
                print("Протокол отклонён сервером. Поля не вырезаются и запрос не повторяется.", flush=True)
                return 2
            except TransportError as exc:
                if exc.sent:
                    self.coordinator.unknown(permit, "transport response after possible acceptance")
                else:
                    self.coordinator.terminal(permit, "NOT_SENT", evidence="connection failed before dispatch")
                record["state"] = "TRANSPORT_ERROR"
                record["outcome"] = "transport_error"
                record["sent"] = bool(exc.sent)
                record["http_status"] = exc.status
                record["error"] = str(exc)[:1000]
                record["finished_at"] = _now()
                self.store.save_request(record)
                consecutive += 1
                if exc.status in {401, 403} or consecutive >= limit:
                    self._set_state("INCOMPLETE", stop_reason="transport")
                    summary = _summarize(self.store, self.corpus, self.pilot_only)
                    self._emit("INCOMPLETE", benchmark, attempt_id, summary, deadline, started)
                    return 2
                if exc.sent:
                    return 2
                continue
            self._save_complete(record, outcome)
            self.coordinator.terminal(permit, "complete", evidence="durable prediction from original response")
            consecutive = 0
        summary = _summarize(self.store, self.corpus, self.pilot_only)
        pending = self._pending()
        if pending:
            # Blocked unknowns or transport errors left work unfinished.
            self._set_state("INCOMPLETE")
            self._emit("INCOMPLETE", None, None, summary, deadline, started)
            return 2
        state = "PILOT_DONE" if self.pilot_only else "COMPLETE"
        self._set_state(state)
        self._emit(state, None, None, summary, deadline, started)
        return 0

    def _pending(self) -> int:
        left = 0
        for benchmark, task_id in _scope(self.corpus, self.pilot_only):
            if self.store.prediction_complete(benchmark, task_id):
                continue
            blocked = self.store.attempt_blocks_send(self.store.latest_attempt(benchmark, task_id))
            if blocked:
                continue
            left += 1
        blocked_left = 0
        for benchmark, task_id in _scope(self.corpus, self.pilot_only):
            if self.store.prediction_complete(benchmark, task_id):
                continue
            if self.store.attempt_blocks_send(self.store.latest_attempt(benchmark, task_id)):
                blocked_left += 1
        return left + blocked_left

    def _save_complete(self, record: dict, outcome: dict) -> None:
        final, reasoning = split_final(outcome.get("content"), outcome.get("reasoning"))
        usage = outcome.get("usage") if isinstance(outcome.get("usage"), dict) else None
        usage_out = None
        if usage is not None:
            usage_out = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": outcome.get("reasoning_tokens"),
            }
        prediction = {
            "attempt_id": record["attempt_id"],
            "benchmark": record["benchmark"],
            "task_id": record["task_id"],
            "outcome": "complete",
            "record_complete": True,
            "finish_reason": outcome.get("finish_reason"),
            "truncated": bool(outcome.get("truncated")),
            "content": outcome.get("content") or "",
            "reasoning": reasoning,
            "final_answer": final,
            "raw": outcome.get("raw"),
            "usage": usage_out,
            "ttft_s": outcome.get("ttft_s"),
            "first_final_content_s": outcome.get("first_final_content_s"),
            "wall_s": outcome.get("wall_s"),
            "seed_echoed": outcome.get("seed_echoed"),
            "reasoning_delta_field": outcome.get("reasoning_delta_field"),
            "handoff": outcome.get("handoff"),
            "server_response_ids": outcome.get("server_response_ids"),
            "sse_done_received": outcome.get("sse_done_received"),
            "trailing_stream_error": outcome.get("trailing_stream_error"),
            "usage_complete": outcome.get("usage_complete"),
            "http_status": outcome.get("http_status", 200),
            "finished_at": _now(),
        }
        self.store.save_prediction(prediction)
        record["state"] = "COMPLETE"
        record["outcome"] = "complete"
        record["sent"] = True
        record["finish_reason"] = prediction["finish_reason"]
        record["truncated"] = prediction["truncated"]
        record["wall_s"] = prediction["wall_s"]
        record["usage"] = usage_out
        record["ttft_s"] = prediction["ttft_s"]
        record["handoff"] = prediction["handoff"]
        record["finished_at"] = prediction["finished_at"]
        record["success"] = False
        record["record_complete"] = True
        self.store.save_request(record)
        self.store.event({"event": "saved", "attempt_id": record["attempt_id"], "at": record["finished_at"]})

    def _unknown(self, record: dict, message: str) -> None:
        record["state"] = "OUTCOME_UNKNOWN"
        record["outcome"] = "OUTCOME_UNKNOWN"
        record["sent"] = True
        record["success"] = False
        record["error"] = message
        record["finished_at"] = _now()
        record["note"] = "Запрос мог остаться активным на сервере. Повторный POST не делается."
        self.store.save_request(record)
        self._set_state("INCOMPLETE", stop_reason="OUTCOME_UNKNOWN")
        self.store.event({"event": "outcome_unknown", "attempt_id": record["attempt_id"], "at": record["finished_at"]})
        print(record["note"], flush=True)

    def _interrupt(self, record: dict, sent: bool) -> None:
        if sent:
            self._unknown(record, "SIGINT after send")
            return
        record["state"] = "PREPARED"
        record["sent"] = False
        record["outcome"] = "interrupted_before_send"
        record["finished_at"] = _now()
        self.store.save_request(record)
        self._set_state("PAUSED", stop_reason="SIGINT")
        print("Остановлено до отправки. Повтор сам не стартует.", flush=True)


class IdleRunner(Runner):
    """One finite public-core run, waiting only on local admission state."""
    def __init__(self, *args, coordinator_dir=None, policy=None, **kwargs):
        super().__init__(*args, **kwargs)
        from qpb.idle import Coordinator, POLICY, endpoint_key
        self.policy = dict(POLICY if policy is None else policy)
        canonical_directory = self.coordinator.dir.resolve()
        if coordinator_dir is not None and self.endpoint.get("kind") != "fixture" and Path(coordinator_dir).resolve() != canonical_directory:
            raise RunRefused("production endpoint uses its canonical admission directory regardless of runs-root")
        self.coordinator = Coordinator(coordinator_dir or canonical_directory)

    def execute(self):
        import fcntl
        import os
        from qpb.idle import IdleBlocked
        self.coordinator._safe_dir()
        fd = os.open(self.coordinator.dir / "worker.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("BLOCKED: endpoint already has a worker", flush=True)
                return 2
            snapshot = self.coordinator.snapshot()
            if snapshot["blocks"] or snapshot["inflight"]:
                print("AUTOMATIC_MODE_BLOCKED: " + ",".join(snapshot["blocks"] or ["RECOVERY_REQUIRED: inflight retained"]), flush=True)
                return 2
            # Historical possibly sent attempts also block the endpoint even
            # when this admission state was only just prepared.
            for manifest_path in self.store.dir.parent.glob("*/manifest.json"):
                other = RunStore(self.store.dir.parent, manifest_path.parent.name)
                manifest = other.manifest()
                if manifest.get("base_url") != self.endpoint["base_url"]:
                    continue
                for path in other.iter_request_files():
                    from qpb.atomic import load_json_result
                    loaded = load_json_result(path)
                    if not loaded["ok"]:
                        raise IdleBlocked("RECOVERY_REQUIRED: partial historical request")
                    record = loaded["value"]
                    if other.attempt_blocks_send(record) in {"SENDING", "OUTCOME_UNKNOWN", "PARTIAL_RECORD", "transport_error_sent"}:
                        if not other.prediction_complete(record.get("benchmark", ""), record.get("task_id", "")):
                            raise IdleBlocked("RECOVERY_REQUIRED: historical possibly accepted POST")
            return super().execute()
        except KeyboardInterrupt:
            if self.store.exists():
                self.store.set_control(pause=True, stop=True)
                self._set_state("STOPPED", stop_reason="SIGINT; inspect retained endpoint inflight")
            return 130
        except IdleBlocked as exc:
            print(str(exc), flush=True)
            return 2
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _create(self):
        super()._create()
        from qpb.fingerprints import sha256_obj
        manifest = self.store.manifest()
        manifest.update(mode="idle", idle_policy=self.policy,
                        idle_policy_fingerprint=sha256_obj(self.policy),
                        authorized_start_epoch=time.time(),
                        authorization_expires_epoch=time.time() + self.policy["authorization_window_days"] * 86400,
                        coordinator_dir=str(self.coordinator.dir.resolve()))
        self.store.write_manifest(manifest)

    def _continue_decision(self, current):
        from qpb.fingerprints import sha256_obj
        if current.get("mode") != "idle" or current.get("idle_policy_fingerprint") != sha256_obj(self.policy):
            return {"error": "idle policy identity mismatch; no generation"}
        # Explicit resume cannot renew the original authorization or erase an
        # unresolved attempt. Parent checks the shared endpoint before here.
        if time.time() >= current.get("authorization_expires_epoch", 0):
            return {"error": "AUTHORIZATION_EXPIRED; original window is retained"}
        allowed = {"MANUAL_PAUSED", "WAITING_IDLE", "COOLDOWN", "YIELDED_FOR_FOREGROUND", "NEEDS_QUIET_WINDOW", "RECOVERY_REQUIRED"}
        if current.get("state") in allowed:
            current = dict(current, state="PAUSED")
        return super()._continue_decision(current)

    def _loop(self):
        import uuid
        from qpb.errors import TransportError
        from qpb.fingerprints import sha256_obj
        from qpb.idle import IdleBlocked
        from qpb.idle_transport import monitored_post, InterruptedByForeground
        started = time.monotonic()
        deadline = None if self.window_hours is None else started + self.window_hours * 3600
        last_state = None
        while True:
            summary = _summarize(self.store, self.corpus, self.pilot_only)
            manifest = self.store.manifest()
            control = self.store.control()
            state = None
            if control.get("stop"):
                state = "STOPPED"
            elif control.get("pause"):
                state = "MANUAL_PAUSED"
            elif time.time() >= manifest["authorization_expires_epoch"]:
                state = "AUTHORIZATION_EXPIRED"
            elif deadline is not None and time.monotonic() >= deadline:
                state = "MANUAL_PAUSED"
            interruptions, interrupted_wall = {}, 0.0
            for path in self.store.iter_request_files():
                from qpb.atomic import read_json
                record = read_json(path)
                if record.get("outcome") == "INTERRUPTED_BY_FOREGROUND":
                    key = (record["benchmark"], record["task_id"])
                    interruptions[key] = interruptions.get(key, 0) + 1
                if record.get("outcome") in {"INTERRUPTED_BY_FOREGROUND", "CANCELLED_BY_STOP"}:
                    interrupted_wall += float(record.get("wall_s") or 0)
            if interrupted_wall >= self.policy["max_interrupted_attempt_wall_seconds"]:
                state = state or "PAUSED_POLICY"
            if state:
                self._set_state(state, interrupted_wall_s=interrupted_wall)
                self._emit(state, None, None, summary, deadline, started)
                return 0
            pending, deferred = [], []
            for benchmark, task_id in _idle_scope(self.corpus, self.pilot_only):
                if self.store.prediction_complete(benchmark, task_id):
                    continue
                previous = self.store.latest_attempt(benchmark, task_id)
                if self.store.attempt_blocks_send(previous):
                    self._set_state("RECOVERY_REQUIRED")
                    return 2
                if interruptions.get((benchmark, task_id), 0) >= self.policy["max_foreground_interruptions_per_task"]:
                    deferred.append(f"{benchmark}:{task_id}")
                else:
                    pending.append((benchmark, task_id, previous))
            if not pending:
                state = "NEEDS_QUIET_WINDOW" if deferred else ("PILOT_DONE" if self.pilot_only else "COMPLETE")
                self._set_state(state, deferred_ids=deferred)
                self._emit(state, None, None, summary, deadline, started)
                return 0
            benchmark, task_id, previous = pending[0]
            task = self.corpus.tasks[benchmark][task_id]
            attempt_n = int((previous or {}).get("attempt_n") or 0) + 1
            attempt_id = f"{benchmark}__{task_id}__a{attempt_n}"
            body = generation_body(self.endpoint, self.profile, benchmark, task["messages"], attempt_id)
            try:
                key = api_key(self.endpoint)
            except MissingAPIKey:
                self._set_state("INCOMPLETE", stop_reason="missing_api_key")
                return 2
            try:
                permit = self.coordinator.reserve(self.store.run_id, attempt_id, sha256_obj(body), self.fingerprint, policy=self.policy)
            except IdleBlocked as exc:
                reason = str(exc)
                if any(token in reason for token in ("UNVERIFIED", "FAULT", "RECOVERY", "INFLIGHT")):
                    self._set_state("RECOVERY_REQUIRED", idle_blockers=[reason])
                    return 2
                state = "YIELDED_FOR_FOREGROUND" if "FOREGROUND" in reason else "COOLDOWN"
                if state != last_state:
                    self._set_state(state, deferred_ids=deferred, idle_blockers=[reason])
                    self._emit(state, benchmark, None, summary, deadline, started)
                    last_state = state
                time.sleep(1)
                continue
            body["rid"] = permit["rid"]
            # Hash the actual body including the preassigned server ID.
            with self.coordinator.transaction() as shared:
                self.coordinator._owned(shared, permit)["request_hash"] = sha256_obj(body)
            record = {"attempt_id": attempt_id, "attempt_n": attempt_n, "benchmark": benchmark,
                      "task_id": task_id, "state": "PREPARED", "sent": False, "outcome": None,
                      "body": body, "request_hash": sha256_obj(body), "generation_fingerprint": self.fingerprint,
                      "server_request_id": permit["rid"], "permit": permit, "started_at": _now(),
                      "started_epoch": time.time(), "success": False}
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream"}
            record["headers"] = redact_headers(headers)
            self.store.save_request(record)
            def mark_sending():
                control = self.store.control()
                if control.get("pause") or control.get("stop"):
                    self.coordinator.terminal(permit, "NOT_SENT", evidence="manual control before dispatch")
                    raise IdleBlocked("manual control before dispatch")
                self.coordinator.dispatch(permit)
                record.update(state="SENDING", sent=True, sending_at=_now())
                self.store.save_request(record)
            self._set_state("RUNNING", idle_blockers=[], deferred_ids=deferred)
            self._emit("RUNNING", benchmark, attempt_id, summary, deadline, started)
            last_state = "RUNNING"
            try:
                outcome = monitored_post(self.transport, self.coordinator, permit, self.store,
                    self.endpoint["base_url"], headers, body, self.profile["generation"]["request_timeout_s"],
                    mark_sending, self.policy)
                # Prediction commit precedes release; crash in between is
                # recoverable without ever regenerating the completed task.
                self._save_complete(record, outcome)
                self.coordinator.terminal(permit, "complete", evidence="original SSE stop/length and durable prediction")
            except InterruptedByForeground as exc:
                record.update(state=exc.reason, outcome=exc.reason, finished_at=_now(),
                              wall_s=exc.result.get("wall_s"), partial_response=exc.result,
                              handoff=exc.result.get("handoff"),
                              record_complete=False)
                self.store.save_request(record)
                self.coordinator.terminal(permit, exc.reason, evidence="owned original SSE finish_reason=abort")
            except IdleBlocked as exc:
                # Admission revoked before the HTTP send boundary.
                record.update(state="PREPARED", outcome="interrupted_before_send", sent=False, error=str(exc))
                self.store.save_request(record)
                snapshot = self.coordinator.snapshot()
                if snapshot["inflight"]:
                    self.coordinator.terminal(permit, "NOT_SENT", evidence="dispatch was not entered")
            except (OutcomeUnknownError, ProtocolDiagnostic, TransportError, KeyboardInterrupt) as exc:
                if isinstance(exc, TransportError) and not exc.sent:
                    self.coordinator.terminal(permit, "NOT_SENT", evidence="connection failed before dispatch")
                    record.update(state="TRANSPORT_ERROR", outcome="transport_error", sent=False)
                    self.store.save_request(record)
                    self._set_state("INCOMPLETE", stop_reason="connection_failed_before_send")
                else:
                    if isinstance(exc, OutcomeUnknownError):
                        record["partial_raw_response"] = exc.partial_raw
                        record["partial_response_timing"] = exc.timing
                        record["server_request_id"] = exc.request_id or permit["rid"]
                    if isinstance(exc, KeyboardInterrupt):
                        self.store.set_control(pause=True, stop=True)
                    self.coordinator.unknown(permit, type(exc).__name__)
                    self._unknown(record, type(exc).__name__)
                    self._set_state("RECOVERY_REQUIRED", stop_reason="OUTCOME_UNKNOWN")
                return 2
