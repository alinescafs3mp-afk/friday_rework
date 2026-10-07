"""Finite A0 bridge behind the existing WorkerAdapter/Controller seam.

Synchronous calls belong off the gateway loop. Bootstrap is model work under
the original native deadline. Neither a response nor staged files verifies the
goal/delivery. This candidate has no registration or implicit live admission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
from typing import Callable

from ..artifacts import StagedArtifact, stage_file, read_staged, _root, _source
from ..associations import _validate_store
from ..boundary import parse_brief
from ..controller import Controller
from .contract import NativeObservation, PreparedNative, VerifiedInput
from .dsh import _identity, _json, _private, _write
from .a0_config import A0Error, KeyMaterial, require, digest
from .a0_native import A0NativeBoundary, decode_file


@dataclass(frozen=True)
class ExpectedFile:
    worker_path: str
    logical_name: str
    media_type: str


@dataclass(frozen=True)
class A0HostConfig:
    workspace_root: Path
    input_root: Path
    staging_root: Path
    current_association: Callable
    expected_files: Callable
    key_material: KeyMaterial
    max_file_bytes: int = 16 * 1024**2
    max_response_bytes: int = 32 * 1024**2
    lifetime_hours: float = 24
    agent_profile: str = "agent0"
    project_name: str | None = None


def job_prefix(row):
    return hashlib.sha256((row["existing_task_id"] + ":" + row["admission_hash"]).encode()).hexdigest()[:24]


def input_path(row, index, suffix=".bin"):
    require(type(index) is int and 0 <= index < 64
            and re.fullmatch(r"\.[a-zA-Z0-9]{1,12}", suffix), "invalid_input_name")
    return f"/a0/usr/uploads/{job_prefix(row)}-input-{index}{suffix}"


class A0Adapter:
    def __init__(self, config: A0HostConfig, boundary: A0NativeBoundary, *, clock=time.time):
        self.config, self.boundary, self.clock = config, boundary, clock
        self.inflight = False
        for p in (config.workspace_root, config.input_root, config.staging_root): _private(p)
        require(type(config.max_file_bytes) is int and 0 < config.max_file_bytes <= 16 * 1024**2
                and type(config.max_response_bytes) is int
                and config.max_file_bytes * 4 / 3 < config.max_response_bytes <= 64 * 1024**2,
                "invalid_transfer_bound")
        require(0 < config.lifetime_hours <= 24 and config.agent_profile == "agent0"
                and config.project_name is None,
                "unreviewed_native_profile")
        require(config.key_material.path == boundary.config.state_dir / ".env"
                and config.key_material.prepared_monotonic == boundary.grant.keys_prepared_monotonic,
                "foreign_key_material")
        require(getattr(boundary, "key_material", None) in (None, config.key_material),
                "foreign_key_material")
        boundary.key_material = config.key_material

    def _row(self, association):
        _validate_store({"schema_version": 1, "jobs": {association["existing_task_id"]: dict(association)}})
        row = dict(self.config.current_association(association))
        _validate_store({"schema_version": 1, "jobs": {row["existing_task_id"]: row}})
        require(_identity(row) == _identity(association) and row["worker_kind"] == "a0", "foreign_association")
        root = _private(row["workspace_reference"])
        require(root != self.config.workspace_root and root.is_relative_to(self.config.workspace_root), "foreign_workspace")
        return row, root

    def _remaining(self, row):
        require(row["stop_intent"] is None and self.clock() >= row["created_at_unix"], "stopped_or_clock_rollback")
        seconds = min(row["deadline_unix"] - self.clock(), row["budget_seconds"] - row["elapsed_seconds"]) - 10
        require(seconds > 2, "stopped_or_expired")
        return seconds

    def _brief(self, row, brief):
        brief = parse_brief(vars(brief))
        require(brief.worker == "a0" and hashlib.sha256(json.dumps(vars(brief), sort_keys=True,
                ensure_ascii=False).encode()).hexdigest() == row["brief_sha256"], "brief_changed")
        return brief

    def _path(self, row, path, *, upload=False):
        require(isinstance(path, str) and "\x00" not in path and "\\" not in path, "unsafe_job_path")
        p = PurePosixPath(path)
        root = "/a0/usr/uploads/" if upload else f"/a0/usr/workdir/{job_prefix(row)}/"
        require(str(p) == path and path.startswith(root)
                and p.parent.as_posix() == root.rstrip("/")
                and re.fullmatch(job_prefix(row) + r"-[A-Za-z0-9_.-]{1,96}", p.name), "unsafe_job_path")
        return p.name

    def _inputs(self, row, inputs):
        require(isinstance(inputs, tuple) and len(inputs) <= 16, "invalid_inputs")
        result, names, size = [], set(), 0
        for v in inputs:
            require(isinstance(v, VerifiedInput) and type(v.size_bytes) is int
                    and 0 <= v.size_bytes <= self.config.max_file_bytes
                    and re.fullmatch(r"[0-9a-f]{64}", v.sha256) and v.receipt_reference, "invalid_inputs")
            name = self._path(row, v.worker_path, upload=True)
            require(name not in names, "duplicate_basename"); names.add(name)
            host = Path(v.host_path)
            require(host.is_absolute() and host.is_relative_to(self.config.input_root), "foreign_input")
            with _root(self.config.input_root) as root, _source(root, host.relative_to(self.config.input_root).as_posix()) as (fd, info):
                require(info.st_size == v.size_bytes, "input_changed")
                chunks, count = [], 0
                while data := os.read(fd, min(65536, self.config.max_file_bytes - count + 1)):
                    count += len(data); require(count <= self.config.max_file_bytes, "input_too_large"); chunks.append(data)
                data = b"".join(chunks)
            require(len(data) == v.size_bytes and hashlib.sha256(data).hexdigest() == v.sha256, "input_changed")
            size += len(data); require(size <= self.config.max_file_bytes, "inputs_too_large")
            result.append((v, {"filename": name, "base64": __import__("base64").b64encode(data).decode()}))
        return result

    def _outputs(self, row):
        values = self.config.expected_files(row)
        require(isinstance(values, tuple) and 0 < len(values) <= 16, "expected_files_required")
        names, labels = set(), set()
        for v in values:
            require(isinstance(v, ExpectedFile) and isinstance(v.logical_name, str)
                    and 0 < len(v.logical_name) <= 512 and isinstance(v.media_type, str)
                    and 0 < len(v.media_type) <= 256, "invalid_expected_file")
            name = self._path(row, v.worker_path)
            require(name not in names and v.logical_name not in labels, "duplicate_basename")
            names.add(name); labels.add(v.logical_name)
        return values

    def _request(self, association, method, path, payload):
        row, _ = self._row(association)
        self.config.key_material.ready()
        return self.boundary.request(row, method, path, payload, self._remaining(row), self.config.max_response_bytes)

    def _verified_files(self, association, paths):
        require(len(paths) <= 16 and len(set(paths)) == len(paths)
                and len({PurePosixPath(p).name for p in paths}) == len(paths), "duplicate_basename")
        row, _ = self._row(association)
        self.config.key_material.ready()
        before = {p: self.boundary.file(row, p, self.config.max_file_bytes, self._remaining(row)) for p in paths}
        values = self._request(row, "POST", "/api/api_files_get", {"paths": list(paths)})
        require(isinstance(values, dict) and set(values) == {PurePosixPath(p).name for p in paths}, "missing_or_extra_files")
        result, total = {}, 0
        for path in paths:
            data = decode_file(values[PurePosixPath(path).name], self.config.max_file_bytes)
            row, _ = self._row(row)
            after = self.boundary.file(row, path, self.config.max_file_bytes, self._remaining(row))
            require(before[path] == after and isinstance(after.get("identity"), list)
                    and len(after["identity"]) == 7 and after.get("size") == len(data)
                    and after.get("sha256") == hashlib.sha256(data).hexdigest()
                    and decode_file(after.get("base64"), self.config.max_file_bytes) == data, "mutable_or_mismatched_file")
            total += len(data); require(total <= self.config.max_file_bytes, "outputs_too_large")
            result[path] = data
        return result

    def _obs(self, row, context, reference, state):
        return NativeObservation(self.boundary.grant.invocation_id,
            "a0:" + self.boundary.grant.container_id + ":" + context, str(reference),
            max(row["elapsed_seconds"], self.clock() - row["created_at_unix"]), state)

    def emergency_stop(self, association):
        # Uses last checked identity; state/receipt corruption cannot block stop.
        unit = self.boundary.stop(association)
        self.config.key_material.remove(cessation_confirmed=unit.quiescent)
        return unit

    def _cleanup(self, row, error):
        try: self.emergency_stop(row)
        except BaseException: error.add_note("owned execution STOP_UNCONFIRMED")
        else: error.add_note("owned execution STOP_CONFIRMED; original error retained")

    def prepare(self, association, brief, inputs):
        row, root = self._row(association)
        try:
            self._remaining(row); self._brief(row, brief)
            require(row["preparation_reserved"] is True and row["submission_observation"] == "NOT_SUBMITTED", "preparation_not_reserved")
            values = self._inputs(row, inputs); outputs = self._outputs(row)
            self.boundary.admit(row)
            require(not (root / "bootstrap-intent.json").exists(), "bootstrap_requires_reconciliation")
            _write(root / "bootstrap-intent.json", {"identity": _identity(row),
                   "container_id": self.boundary.grant.container_id,
                   "invocation_id": self.boundary.grant.invocation_id,
                   "native_grant": asdict(self.boundary.grant),
                   "inputs": [asdict(v) for v, _ in values], "outputs": [asdict(v) for v in outputs],
                   "bootstrap_is_model_work": True})
            payload = {"message": "Initialize context for Friday_rework job " + row["existing_task_id"]
                       + ". Reply READY and wait. Do not use tools or change files.",
                       "attachments": [v for _, v in values], "lifetime_hours": self.config.lifetime_hours,
                       "agent_profile": self.config.agent_profile}
            response = self._request(row, "POST", "/api/api_message", payload)
            context = response.get("context_id") if isinstance(response, dict) else None
            require(isinstance(context, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", context)
                    and isinstance(response.get("response"), str), "bootstrap_outcome_unknown")
            # Actual context is durable BEFORE input checks or effectful task.
            receipt = root / "a0-prepared.json"
            _write(receipt, {"identity": _identity(row), "context_id": context,
                            "container_id": self.boundary.grant.container_id,
                            "invocation_id": self.boundary.grant.invocation_id,
                            "native_grant": asdict(self.boundary.grant),
                            "inputs": [asdict(v) for v, _ in values], "outputs": [asdict(v) for v in outputs]})
            receipt.chmod(0o400)
            if values:
                actual = self._verified_files(row, tuple(v.worker_path for v, _ in values))
                require(all(len(actual[v.worker_path]) == v.size_bytes
                            and hashlib.sha256(actual[v.worker_path]).hexdigest() == v.sha256
                            for v, _ in values), "uploaded_input_missing_or_changed")
            _write(root / "inputs-verified.json", {"receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()})
            current, _ = self._row(row); self._remaining(current)
            return PreparedNative(context, str(receipt))
        except BaseException as error:
            self._cleanup(row, error); raise

    def _prepared(self, association, prepared):
        row, root = self._row(association)
        require(isinstance(prepared, PreparedNative) and prepared.receipt_reference == str(root / "a0-prepared.json"), "foreign_preparation")
        receipt = _json(root / "a0-prepared.json")
        require(receipt["identity"] == _identity(row) and receipt["context_id"] == prepared.reference
                and receipt["container_id"] == self.boundary.grant.container_id
                and receipt["invocation_id"] == self.boundary.grant.invocation_id
                and receipt['native_grant'] == asdict(self.boundary.grant)
                and receipt["outputs"] == [asdict(v) for v in self._outputs(row)], "preparation_changed")
        verified = _json(root / "inputs-verified.json")
        require(verified == {"receipt_sha256": hashlib.sha256((root / "a0-prepared.json").read_bytes()).hexdigest()}, "inputs_not_verified")
        return row, root, receipt

    def submit(self, association, brief, inputs, prepared, on_native_observed):
        row, root = self._row(association)
        try:
            row, root, receipt = self._prepared(row, prepared)
            self._remaining(row); self._brief(row, brief)
            require(row["submission_observation"] in {"UNKNOWN", "OBSERVED"}, "submission_not_reserved")
            require(receipt["inputs"] == [asdict(v) for v, _ in self._inputs(row, inputs)], "inputs_changed")
            require(not (root / "task-post-intent.json").exists(), "task_requires_reconciliation")
            on_native_observed(self._obs(row, prepared.reference, root / "a0-prepared.json", "running"))
            # The bootstrap receipt proves past transfer only. Check the actual
            # worker-visible selected bytes again at the dependent handoff.
            if inputs:
                actual = self._verified_files(row, tuple(v.worker_path for v in inputs))
                require(all(len(actual[v.worker_path]) == v.size_bytes
                            and hashlib.sha256(actual[v.worker_path]).hexdigest() == v.sha256
                            for v in inputs), "uploaded_input_missing_or_changed")
            _write(root / "task-post-intent.json", {"context_id": prepared.reference,
                   "brief_sha256": row["brief_sha256"], "deadline_unix": row["deadline_unix"],
                   "container_id": self.boundary.grant.container_id, "invocation_id": self.boundary.grant.invocation_id})
            self.inflight = True
            message = ("Existing job: " + row["existing_task_id"] + "\nGoal: " + brief.brief
                       + "\nCheck: " + brief.goal_check + "\nOriginal deadline: " + str(row["deadline_unix"])
                       + "\nVerified inputs: " + json.dumps([v.worker_path for v in inputs])
                       + "\nWrite these exact output files: " + json.dumps([v["worker_path"] for v in receipt["outputs"]]))
            response = self._request(row, "POST", "/api/api_message", {"context_id": prepared.reference,
                       "message": message, "lifetime_hours": self.config.lifetime_hours})
            require(isinstance(response, dict) and response.get("context_id") == prepared.reference
                    and isinstance(response.get("response"), str), "task_outcome_unknown")
            _write(root / "worker-response.json", response)
            paths = tuple(v["worker_path"] for v in receipt["outputs"])
            data = self._verified_files(row, paths)
            received = root / "a0-received"; received.mkdir(mode=0o700)
            staged = []
            for output in receipt["outputs"]:
                name = PurePosixPath(output["worker_path"]).name
                _write(received / name, data[output["worker_path"]])
                staged.append(stage_file(source_root=received, relative_path=name,
                    staging_root=self.config.staging_root, logical_name=output["logical_name"],
                    media_type=output["media_type"], origin_reference=str(root / "worker-response.json"),
                    max_bytes=self.config.max_file_bytes))
            # Preserve bytes before stopping. Normal response does not release
            # warm capacity: this first candidate always stops its environment.
            self.emergency_stop(row)
            for artifact in staged: read_staged(staging_root=self.config.staging_root,
                                              artifact=artifact, max_bytes=self.config.max_file_bytes)
            _write(root / "a0-result.json", {"artifacts": [asdict(v) for v in staged],
                   "identity": _identity(row), "outputs": receipt["outputs"],
                   "context_id": prepared.reference, "stop_confirmed": True,
                   "goal_verification": "NOT_RUN", "delivery": "NOT_RUN"})
            return self._obs(row, prepared.reference, root / "a0-result.json", "completed")
        except BaseException as error:
            self._cleanup(row, error); raise
        finally:
            self.inflight = False

    def artifacts(self, association, prepared):
        row, root, receipt = self._prepared(association, prepared)
        result = _json(root / "a0-result.json")
        require(set(result) == {"artifacts", "identity", "outputs", "context_id", "stop_confirmed",
                                "goal_verification", "delivery"}
                and result.get("identity") == _identity(row)
                and result.get("outputs") == receipt["outputs"]
                and result.get("goal_verification") == result.get("delivery") == "NOT_RUN"
                and result.get("context_id") == prepared.reference and result.get("stop_confirmed") is True,
                "result_requires_reconciliation")
        values = result["artifacts"]
        fields = set(StagedArtifact.__dataclass_fields__)
        require(isinstance(values, list) and len(values) == len(receipt["outputs"])
                and all(isinstance(v, dict) and set(v) == fields for v in values), "incomplete_result_manifest")
        items = tuple(StagedArtifact(**v) for v in values)
        require(len({v.reference for v in items}) == len(items)
                and len({v.logical_name for v in items}) == len(items), "duplicate_result_artifact")
        total = 0
        for item, expected in zip(items, receipt["outputs"]):
            require(item.logical_name == expected["logical_name"] and item.media_type == expected["media_type"]
                    and item.origin_reference == str(root / "worker-response.json")
                    and item.complete is True and item.verification == "verified"
                    and type(item.size_bytes) is int and 0 <= item.size_bytes <= self.config.max_file_bytes,
                    "foreign_or_incomplete_result_artifact")
            total += item.size_bytes; require(total <= self.config.max_file_bytes, "outputs_too_large")
            read_staged(staging_root=self.config.staging_root, artifact=item, max_bytes=self.config.max_file_bytes)
        return items

    def observe(self, association, prepared):
        row, root, _ = self._prepared(association, prepared)
        if (root / "a0-result.json").exists():
            self.artifacts(row, prepared)
            unit = self.boundary.supervisor.observe(self.boundary._association(row))
            obj = self.boundary.inspect(row, stopping=True)
            require(unit.quiescent and not obj["State"]["Running"] and obj["State"]["Pid"] == 0, "STOP_UNCONFIRMED")
            return self._obs(row, prepared.reference, root / "a0-result.json", "completed")
        if not self.inflight:
            self.emergency_stop(row)
            return self._obs(row, prepared.reference, root / "task-post-intent.json", "unknown")
        response = self._request(row, "GET", "/api/api_log_get", {"context_id": prepared.reference, "length": 100})
        require(isinstance(response, dict) and response.get("context_id") == prepared.reference
                and isinstance(response.get("log"), dict), "progress_unknown")
        log = response["log"]
        require(isinstance(log.get("guid"), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',log['guid'])
                and type(log.get("progress_active")) is bool
                and type(log.get("total_items")) is int and log["total_items"] >= 0, "progress_unknown")
        guid_ref = root / 'log-guid.json'
        identity = {'context_id':prepared.reference,'guid':log['guid']}
        if guid_ref.exists():
            require(_json(guid_ref) == identity, 'log_guid_requires_reconciliation')
        else:
            _write(guid_ref, identity)
        # No thought/tool content streamed. Counts are factual progress only.
        value = {k: log[k] for k in ("guid", "total_items", "progress_active")}
        ref = root / ("progress-" + digest(value) + ".json")
        if not ref.exists(): _write(ref, value)
        return self._obs(row, prepared.reference, ref, "running")

    def stop(self, association, prepared, intent):
        require(intent in {"cancel", "pause", "deadline"}, "invalid_stop_intent")
        row, root, _ = self._prepared(association, prepared)
        self.emergency_stop(row)
        ref = root / ("stop-" + intent + ".json")
        if not ref.exists(): _write(ref, {"intent": intent, "stop_confirmed": True})
        return self._obs(row, prepared.reference, ref, "stopped")


class A0Controller(Controller):
    """Small A0 bootstrap correction using the SAME association/journal/lock.

    The shared Controller assumes prepare is harmless. Host integration must use
    this subclass for A0 until that assumption is corrected by its owner.
    """
    def _checked_row(self, task_id, owner):
        try:
            row = self.associations.get(task_id, owner)
        except BaseException as error:
            # A state read can fail after bootstrap, before shared start's try.
            # Only the same last verified task/principal is eligible for stop.
            prior = getattr(self, "_last_a0_row", None)
            if prior and prior["existing_task_id"] == task_id and prior["owner"] == owner:
                self._stop_on_error(prior, error)
            raise
        if row["worker_kind"] == "a0":
            import copy
            self._last_a0_row = copy.deepcopy(row)
        return row

    def start(self, task_id, owner, brief, inputs):
        row = self._checked_row(task_id, owner)
        try:
            return super().start(task_id, owner, brief, inputs)
        except BaseException as error:
            # Even NOT_SUBMITTED can own an effectful model bootstrap. Covers
            # brief/input/journal failures and a committed UNKNOWN whose write
            # acknowledgement failed, using this last checked association.
            if row["worker_kind"] == "a0": self._stop_on_error(row, error)
            raise

    def prepare(self, task_id, owner, brief, inputs):
        row = self._checked_row(task_id, owner)
        try:
            result = super().prepare(task_id, owner, brief, inputs)
            current = self.associations.get(task_id, owner)
            if current["worker_kind"] == "a0" and self._intent(current):
                raise A0Error("retained_stop_or_deadline")
            return result
        except BaseException as error:
            if row["worker_kind"] == "a0": self._stop_on_error(row, error)
            raise

    def reconcile(self, task_id, owner):
        row = self._checked_row(task_id, owner)
        try:
            return super().reconcile(task_id, owner)
        except BaseException as error:
            if row["worker_kind"] == "a0": self._stop_on_error(row, error)
            raise

    def stop(self, task_id, principal, intent):
        row = self.associations.get_for_control(task_id, principal)
        if row["worker_kind"] != "a0" or row["submission_observation"] != "NOT_SUBMITTED":
            return super().stop(task_id, principal, intent)
        require(intent in {"cancel", "pause"}, "invalid_stop_intent")
        try:
            row = self.associations.request_stop(task_id, row["owner"], intent)
            # Preparation can be blocked in a model request with no context ID.
            # No preparation read/persistence is a prerequisite to native stop.
            unit = self._binding(row).emergency_stop(row)
            require(unit.quiescent, "STOP_UNCONFIRMED")
            return NativeObservation("", "", "association:" + task_id + "#stop_intent",
                                     row["elapsed_seconds"], "stopped")
        except BaseException as error:
            self._stop_on_error(row, error)
            raise
