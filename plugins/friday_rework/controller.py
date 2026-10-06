"""Synchronous glue around the existing association, adapter and native stop.

The host calls these methods outside its event loop. This module creates no
executor, queue, timer, task identity or workspace. Admission, verified input
staging and a ready adapter are prerequisites supplied by the trusted host.
Preparation references share Hermes PluginState and the association lock.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Callable, Mapping

from .adapters.contract import NativeObservation, PreparedNative, VerifiedInput, WorkerAdapter
from .associations import Associations, _native, _sync_directory, _text
from .boundary import WorkBrief, parse_brief
from .supervision import UnitObservation

KEY = "worker_preparation.v1"


class ControllerError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerBinding:
    adapter: WorkerAdapter
    # Must stop the entire owned execution even if PluginState, auxiliary
    # receipts or pinned launch files are unreadable. DSH uses its reviewed
    # NativeSupervisor.stop; an A0 HTTP-client-only stop cannot qualify.
    emergency_stop: Callable[[Mapping], UnitObservation]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def _prepared(value):
    if not isinstance(value, dict) or set(value) != {"reference", "receipt_reference"}:
        raise ControllerError("invalid_preparation")
    return PreparedNative(**{k: _text(v, 2048) for k, v in value.items()})


def _inputs_digest(inputs):
    if not isinstance(inputs, tuple) or len(inputs) > 64:
        raise ControllerError("invalid_verified_inputs")
    names = set()
    for item in inputs:
        if not isinstance(item, VerifiedInput):
            raise ControllerError("invalid_verified_inputs")
        for value in (item.host_path, item.worker_path, item.receipt_reference):
            _text(value, 2048)
        if (type(item.size_bytes) is not int or item.size_bytes < 0
                or not isinstance(item.sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", item.sha256)
                or item.worker_path in names):
            raise ControllerError("invalid_verified_inputs")
        names.add(item.worker_path)
    return _digest([asdict(item) for item in inputs])


class Controller:
    def __init__(self, associations: Associations, bindings: Mapping[str, WorkerBinding]):
        if any(k not in {"dsh", "a0"} or not isinstance(v, WorkerBinding)
               or not callable(v.emergency_stop) for k, v in bindings.items()):
            raise ControllerError("invalid_worker_binding")
        self.associations = associations
        self.bindings = dict(bindings)

    def _binding(self, row):
        try:
            return self.bindings[row["worker_kind"]]
        except KeyError as exc:
            raise ControllerError("worker_not_admitted") from exc

    def _journal(self):
        value = self.associations.state.get(KEY, {"schema_version": 1, "jobs": {}})
        if (not isinstance(value, dict) or set(value) != {"schema_version", "jobs"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or not isinstance(value["jobs"], dict)):
            raise ControllerError("invalid_preparation_store")
        for task, entry in value["jobs"].items():
            _text(task, 128)
            if not isinstance(entry, dict) or set(entry) != {
                    "admission_hash", "brief_sha256", "inputs_sha256", "prepared"}:
                raise ControllerError("invalid_preparation_store")
            for name in ("admission_hash", "brief_sha256", "inputs_sha256"):
                if not isinstance(entry[name], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[name]):
                    raise ControllerError("invalid_preparation_store")
            if entry["prepared"] is not None:
                _prepared(entry["prepared"])
        return value

    def _save(self, value):
        self.associations.state.set(KEY, value)
        _sync_directory(Path(self.associations.state.data_dir))

    @staticmethod
    def _entry(journal, row):
        entry = journal["jobs"].get(row["existing_task_id"])
        if (row["preparation_reserved"] is not True or entry is None
                or entry["admission_hash"] != row["admission_hash"]
                or entry["brief_sha256"] != row["brief_sha256"]):
            raise ControllerError("missing_or_foreign_preparation")
        return entry

    def _load(self, row, inputs=None):
        with self.associations._locked() as data:
            current = self.associations._owned(data, row["existing_task_id"], row["owner"])
            entry = self._entry(self._journal(), current)
            if entry["prepared"] is None:
                raise ControllerError("preparation_requires_reconciliation")
            if inputs is not None and entry["inputs_sha256"] != _inputs_digest(inputs):
                raise ControllerError("prepared_inputs_changed")
            return _prepared(entry["prepared"])

    def _intent(self, row):
        if row["stop_intent"] is not None:
            return row["stop_intent"]
        if (self.associations.clock() >= row["deadline_unix"]
                or row["elapsed_seconds"] >= row["budget_seconds"]):
            return "deadline"
        return None

    def _stop_on_error(self, row, error):
        # No fresh state read or receipt write may prevent this attempt.
        try:
            observed = self._binding(row).emergency_stop(copy.deepcopy(row))
            if not isinstance(observed, UnitObservation) or not observed.quiescent:
                raise ControllerError("STOP_UNCONFIRMED")
        except BaseException as stop_error:
            error.add_note("owned execution STOP_UNCONFIRMED: " + type(stop_error).__name__)
        else:
            error.add_note("owned execution STOP_CONFIRMED; original failure retained")

    def prepare(self, task_id, owner, brief: WorkBrief, inputs: tuple[VerifiedInput, ...]):
        brief = parse_brief(vars(brief))
        input_hash = _inputs_digest(inputs)
        with self.associations._locked() as data:
            row = copy.deepcopy(self.associations._owned(data, task_id, owner))
            binding = self._binding(row)
            if _digest(vars(brief)) != row["brief_sha256"]:
                raise ControllerError("brief_changed")
            journal = self._journal()
            if task_id in journal["jobs"]:
                entry = self._entry(journal, row)
                if entry["inputs_sha256"] != input_hash:
                    raise ControllerError("prepared_inputs_changed")
                if entry["prepared"] is None:
                    raise ControllerError("preparation_requires_reconciliation")
                return _prepared(entry["prepared"])
            if row["preparation_reserved"]:
                raise ControllerError("preparation_requires_reconciliation")
            if row["submission_observation"] != "NOT_SUBMITTED" or self._intent(row):
                raise ControllerError("preparation_stopped_or_uncertain")
            # A lost auxiliary document must not look like a first prepare.
            # Commit the one-way marker in the authoritative association
            # before publishing its auxiliary reservation or calling adapter.
            data["jobs"][task_id]["preparation_reserved"] = True
            self.associations._save(data)
            row["preparation_reserved"] = True
            journal["jobs"][task_id] = {
                "admission_hash": row["admission_hash"], "brief_sha256": row["brief_sha256"],
                "inputs_sha256": input_hash, "prepared": None,
            }
            self._save(journal)
        # Do not hold the profile-wide metadata lock across native preparation.
        # A crash/failure retains None and cannot silently repeat preparation.
        prepared = binding.adapter.prepare(row, brief, inputs)
        value = asdict(prepared) if isinstance(prepared, PreparedNative) else None
        prepared = _prepared(value)
        with self.associations._locked() as data:
            current = self.associations._owned(data, task_id, owner)
            journal = self._journal()
            entry = self._entry(journal, current)
            if entry["prepared"] is not None or entry["inputs_sha256"] != input_hash:
                raise ControllerError("preparation_conflict")
            entry["prepared"] = value
            self._save(journal)
        return prepared

    def _record(self, row, observation):
        if (not isinstance(observation, NativeObservation)
                or observation.state not in {"running", "completed", "failed", "stopped", "unknown"}
                or isinstance(observation.elapsed_seconds, bool)
                or not isinstance(observation.elapsed_seconds, (int, float))
                or not math.isfinite(observation.elapsed_seconds) or observation.elapsed_seconds < 0):
            raise ControllerError("invalid_native_observation")
        _text(observation.evidence_reference, 2048)
        _text(observation.invocation_id, 64, empty=True)
        _text(observation.worker_reference, 2048, empty=True)
        # Empty identity means no actual opening event/context observation.
        # A preparation path is never a substitute worker/session identity.
        if not observation.invocation_id or not observation.worker_reference:
            current = self.associations.get(row["existing_task_id"], row["owner"])
            if (row["native"] is not None or current["native"] is not None
                    or observation.state in {"running", "completed"}):
                raise ControllerError("native_identity_missing")
            return current
        native = _native({"invocation_id": observation.invocation_id,
                          "worker_reference": observation.worker_reference})
        if row["native"] is None:
            # Retain checked actual identity locally BEFORE the state write.
            # If persistence fails, the caller can still stop this invocation.
            row["native"] = native
            row["submission_observation"] = "OBSERVED"
            current = self.associations.attach_native(row["existing_task_id"], row["owner"], native)
        else:
            if row["native"] != native:
                raise ControllerError("native_identity_changed")
            current = self.associations.get(row["existing_task_id"], row["owner"])
        row.update(current)
        return self.associations.observe(row["existing_task_id"], row["owner"], native=native,
                                         evidence_reference=observation.evidence_reference,
                                         elapsed_seconds=observation.elapsed_seconds)

    def start(self, task_id, owner, brief: WorkBrief, inputs: tuple[VerifiedInput, ...]):
        row = self.associations.get(task_id, owner)
        if _digest(vars(parse_brief(vars(brief)))) != row["brief_sha256"]:
            raise ControllerError("brief_changed")
        binding = self._binding(row)
        try:
            prepared = self._load(row, inputs)
        except BaseException as exc:
            if row["submission_observation"] != "NOT_SUBMITTED":
                self._stop_on_error(row, exc)
            raise
        if row["submission_observation"] != "NOT_SUBMITTED":
            return self.reconcile(task_id, owner)
        row = self.associations.begin_submission(task_id, owner)
        # No external launch has occurred if begin_submission fails. Its
        # potentially committed UNKNOWN is preserved for reconciliation.
        try:
            def native_observed(value):
                row.update(self._record(row, value))
                if self._intent(row):
                    raise ControllerError("retained_stop_or_deadline")

            row.update(self.associations.get(task_id, owner))
            if self._intent(row):
                raise ControllerError("retained_stop_or_deadline")
            value = binding.adapter.submit(row, brief, inputs, prepared, native_observed)
            row.update(self._record(row, value))
            if self._intent(row):
                return self._stop(row, prepared, self._intent(row))
            return value
        except BaseException as exc:
            self._stop_on_error(row, exc)
            raise

    def _stop(self, row, prepared, intent):
        value = self._binding(row).adapter.stop(row, prepared, intent)
        if not isinstance(value, NativeObservation) or value.state != "stopped":
            raise ControllerError("STOP_UNCONFIRMED")
        self._record(row, value)
        return value

    def reconcile(self, task_id, owner):
        row = self.associations.get(task_id, owner)
        try:
            prepared = self._load(row)
            intent = self._intent(row)
            if intent:
                return self._stop(row, prepared, intent)
            value = self._binding(row).adapter.observe(row, prepared)
            row.update(self._record(row, value))
            if self._intent(row):
                return self._stop(row, prepared, self._intent(row))
            return value
        except BaseException as exc:
            self._stop_on_error(row, exc)
            raise

    def stop(self, task_id, principal, intent):
        if intent not in {"cancel", "pause"}:
            raise ControllerError("invalid_stop_intent")
        row = self.associations.get_for_control(task_id, principal)
        try:
            row = self.associations.request_stop(task_id, row["owner"], intent)
            prepared = self._load(row)
            return self._stop(row, prepared, row["stop_intent"])
        except BaseException as exc:
            self._stop_on_error(row, exc)
            raise
