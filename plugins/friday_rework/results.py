"""Stable result bytes and delivery attempts in the existing association.

There is no worker launch or implicit retry here. A persisted UNKNOWN precedes
each native send; a crash or missing acknowledgement cannot authorize another.
File integrity and execution completion never certify the user's goal.
"""
from __future__ import annotations

import copy
import asyncio
import os
import fcntl
import stat
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import re

from .artifacts import StagedArtifact, read_staged, stage_file
from .associations import AssociationError, _number, _text

MAX_ARTIFACTS = 16
MAX_DELIVERY_ATTEMPTS = 16


def delivery_state(deliveries):
    states = [attempts[-1]["state"] if attempts else "NOT_RUN" for attempts in deliveries.values()]
    if states and all(s == "DELIVERED" for s in states):
        return "DELIVERED"
    if "UNKNOWN" in states:
        return "UNKNOWN"
    if "DELIVERED" in states:
        return "PARTIAL"
    return "FAILED" if "FAILED" in states else "NOT_RUN"


def _file_name(value):
    _text(value, 255)
    if value in {".", ".."} or any(ord(c) < 32 or c in "/\\" for c in value):
        raise AssociationError("invalid_result_name")
    return value


def _expected_receipt(row, artifact):
    message = row["host"]["binding"]["ingress"]["message"]
    return {"kind": "document", "sha256": artifact["sha256"],
            "bytes": artifact["size_bytes"], "file_name": artifact["logical_name"],
            "bot_id": message["bot_id"], "chat_id": message["chat_id"],
            "thread_id": message["thread_id"] or None, "reply_to": message["message_id"]}


def _receipt(row, artifact, value):
    """Retain only checked native acknowledgement fields, never SDK raw errors."""
    if not isinstance(value, dict) or value.get("state") not in {"FAILED", "UNKNOWN", "DELIVERED"}:
        return {"state": "UNKNOWN"}
    if value["state"] == "FAILED":
        # Only these native pre-send refusals establish that no send happened.
        if value.get("error") in {"gateway_delivery_preflight_rejected", "gateway_document_route_rejected",
                                  "invalid_document", "document_bytes_unsupported"}:
            return {"state": "FAILED", "error": value["error"]}
        return {"state": "UNKNOWN"}
    expected = _expected_receipt(row, artifact)
    if value["state"] == "DELIVERED" and all(value.get(k) == v for k, v in expected.items()):
        message = value.get("message_id")
        if isinstance(message, str) and message.isascii() and message.isdecimal() and int(message) > 0:
            return {"state": "DELIVERED", **expected, "message_id": message}
    return {"state": "UNKNOWN"}


def validate_result(row):
    try:
        _validate_result(row)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise AssociationError("invalid_result_record") from error


def _validate_result(row):
    result = row["result"]
    if (not isinstance(result, dict) or set(result) != {"artifacts", "source_paths", "deliveries", "observations", "assessment"}
            or row["host"]["quiescence"] is None
            or not isinstance(result["artifacts"], list)
            or not 1 <= len(result["artifacts"]) <= MAX_ARTIFACTS
            or not isinstance(result["deliveries"], dict)):
        raise AssociationError("invalid_result_record")
    labels = selection_names(result["source_paths"])
    if labels != [a.get("logical_name") for a in result["artifacts"]]:
        raise AssociationError("result_selection_mismatch")
    runtime = row["host"]["binding"]["runtime"]
    references, names, total = set(), set(), 0
    for item in result["artifacts"]:
        try:
            artifact = StagedArtifact(**item)
        except (TypeError, ValueError):
            raise AssociationError("invalid_result_artifact") from None
        _file_name(artifact.logical_name)
        _text(artifact.media_type, 256)
        if (not re.fullmatch(r"[0-9a-f]{32}\.[A-Za-z0-9]{1,12}", artifact.reference)
                or artifact.reference in references or artifact.logical_name in names
                or artifact.origin_reference != row["existing_task_id"]
                or artifact.complete is not True or artifact.verification != "verified"
                or type(artifact.size_bytes) is not int or not 0 <= artifact.size_bytes <= runtime["max_file_bytes"]
                or not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)):
            raise AssociationError("invalid_result_artifact")
        references.add(artifact.reference)
        names.add(artifact.logical_name)
        total += artifact.size_bytes
        attempts = result["deliveries"].get(artifact.reference)
        if not isinstance(attempts, list) or len(attempts) > MAX_DELIVERY_ATTEMPTS:
            raise AssociationError("invalid_delivery_attempts")
        for number, attempt in enumerate(attempts, 1):
            if (not isinstance(attempt, dict) or set(attempt) != {"number", "state", "at_unix", "receipt"}
                    or type(attempt["number"]) is not int or attempt["number"] != number
                    or attempt["state"] not in {"UNKNOWN", "FAILED", "DELIVERED"}
                    or number < len(attempts) and attempt["state"] != "FAILED"):
                raise AssociationError("invalid_delivery_attempt")
            _number(attempt["at_unix"])
            proof = attempt["receipt"]
            if proof is None:
                if attempt["state"] != "UNKNOWN":
                    raise AssociationError("missing_delivery_receipt")
            elif _receipt(row, item, proof) != proof or proof["state"] != attempt["state"]:
                raise AssociationError("invalid_delivery_receipt")
    if (set(result["deliveries"]) != references or total > runtime["max_total_bytes"]
            or row["delivery"] != delivery_state(result["deliveries"])):
        raise AssociationError("invalid_result_record")
    validate_assessment(row)


def validate_assessment(row):
    from .admission import CALL_FIELDS
    from .host_record import digest
    result = row["result"]
    observations = result["observations"]
    if not isinstance(observations, dict) or len(observations) > 64:
        raise AssociationError("invalid_result_observations")
    expected = {a["reference"]: a for a in result["artifacts"]}
    for reference, observed in observations.items():
        if (not isinstance(observed, dict) or set(observed) != {"call", "kind", "files", "at_unix"}
                or observed["kind"] != "file_inspection" or not isinstance(observed["call"], dict)
                or set(observed["call"]) != set(CALL_FIELDS)
                or reference != digest(observed["call"])
                or observed["call"]["task_id"] != row["owner"]["session_id"]
                or observed["call"]["session_id"] != row["owner"]["session_id"]
                or not isinstance(observed["files"], list) or len(observed["files"]) != len(expected)):
            raise AssociationError("invalid_result_observation")
        for value in observed["call"].values():
            _text(value)
        _number(observed["at_unix"])
        found = set()
        for seen in observed["files"]:
            if (not isinstance(seen, dict) or set(seen) != {"reference", "sha256", "bytes_seen", "preview_complete"}
                    or seen["reference"] not in expected or seen["reference"] in found
                    or seen["sha256"] != expected[seen["reference"]]["sha256"]
                    or type(seen["bytes_seen"]) is not int
                    or not 0 <= seen["bytes_seen"] <= min(4096, expected[seen["reference"]]["size_bytes"])
                    or type(seen["preview_complete"]) is not bool
                    or seen["preview_complete"] and seen["bytes_seen"] != expected[seen["reference"]]["size_bytes"]):
                raise AssociationError("invalid_inspection_extent")
            found.add(seen["reference"])
    assessment = result["assessment"]
    if assessment is None:
        if row["goal_verification"] != "NOT_RUN":
            raise AssociationError("missing_goal_assessment")
        return
    if (not isinstance(assessment, dict)
            or set(assessment) != {"state", "method", "observations", "rationale", "at_unix"}
            or assessment["method"] != "parent_file_review"
            or assessment["state"] not in {"PASS", "FAIL", "UNKNOWN"}
            or row["goal_verification"] != assessment["state"]
            or not isinstance(assessment["observations"], list) or not assessment["observations"]
            or len(set(assessment["observations"])) != len(assessment["observations"])
            or any(ref not in observations for ref in assessment["observations"])):
        raise AssociationError("invalid_goal_assessment")
    _text(assessment["rationale"], 2048)
    _number(assessment["at_unix"])
    if assessment["state"] == "PASS":
        terminal = row["host"]["terminal"]
        if terminal is None or terminal["state"] != "completed":
            raise AssociationError("unfinished_goal_cannot_pass")
        if not any(all(f["preview_complete"] for f in observations[ref]["files"])
                   for ref in assessment["observations"]):
            raise AssociationError("incomplete_file_review")


def record_inspection(store, row, call, previews):
    from .host_record import digest
    value = {"call": copy.deepcopy(call), "kind": "file_inspection", "at_unix": store.clock(),
             "files": [{"reference": a["reference"], "sha256": a["sha256"],
                        "bytes_seen": len(a["preview"].encode("utf-8")) if a["preview"] is not None else 0,
                        "preview_complete": a["preview_complete"]} for a in previews]}
    reference = digest(call)
    with store._locked() as data:
        current = store._owned(data, row["existing_task_id"], row["owner"])
        if current["result"]["artifacts"] != row["result"]["artifacts"]:
            raise AssociationError("inspection_candidate_changed")
        old = current["result"]["observations"].get(reference)
        if old is not None:
            if old["call"] != value["call"] or old["files"] != value["files"]:
                raise AssociationError("inspection_conflict")
        else:
            current["result"]["observations"][reference] = value
        if "notification" in current:
            current["notification"]["state"] = "OBSERVED"
        store._save(data)
    return reference


def assess_result(store, row, verdict, rationale, observations):
    """Record the original parent's judgement of actual independent observations.

    Method remains file review, never an executed-test claim. The caller must
    use UNKNOWN for goals requiring a check it has not actually observed.
    """
    with store._locked() as data:
        current = store._owned(data, row["existing_task_id"], row["owner"])
        if verdict == "PASS" and current["stop_intent"] is not None:
            raise AssociationError("stopped_goal_cannot_pass")
        assessment = {"state": verdict, "method": "parent_file_review", "observations": copy.deepcopy(observations),
                      "rationale": rationale, "at_unix": store.clock()}
        if current["result"]["assessment"] is not None:
            raise AssociationError("assessment_already_retained")
        if any(current["result"]["deliveries"].values()):
            raise AssociationError("assessment_after_delivery")
        current["result"]["assessment"] = assessment
        current["goal_verification"] = verdict
        store._save(data)
        return copy.deepcopy(current)


def output_root(row):
    # Same protected task staging tree as ingress, distinct from worker writes.
    return Path(row["host"]["binding"]["runtime"]["staging_root"]) / row["existing_task_id"] / "outputs"


def collect_outputs(store, row, paths):
    """Freeze explicitly selected job-relative files; paths are content, not authority.

    Failed copies preserve earlier staged bytes. A corrected file selection can
    retry harmless copying within the same bounded directory, never the worker.
    It cannot overwrite an earlier manifest.
    This does not execute returned code or assert that a task succeeded.
    """
    # Separate per-job filesystem ownership, never the control metadata lock.
    # A competing call refuses immediately. Kernel close/crash releases it.
    row = store.get(row["existing_task_id"], row["owner"])
    with output_copy_lock(row):
        return _collect_outputs(store, row, paths)


@contextmanager
def output_copy_lock(row):
    from .host_runtime import private_directory
    directory = private_directory(output_root(row).parent)
    fd = os.open(directory / ".outputs-copy.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise AssociationError("unsafe_output_copy_lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AssociationError("output_copy_busy") from exc
        yield
    finally:
        os.close(fd)


def _collect_outputs(store, row, paths):
    from .host_runtime import private_directory
    # Recheck the durable selection only after gaining exclusive copy ownership.
    row = store.get(row["existing_task_id"], row["owner"])
    if "result" in row:
        if paths is not None and paths != row["result"]["source_paths"]:
            raise AssociationError("result_selection_already_retained")
        return row
    require_result_quiescence(row)
    labels = selection_names(paths)
    retained = None
    if row["worker_kind"] == "a0":
        retained = {item.logical_name: item for item in a0_retained_outputs(store, row)}
        if any(path not in retained for path in paths):
            raise AssociationError("unknown_a0_output")
        source = private_directory(output_root(row).parent / "a0-outputs")
    else:
        source = private_directory(Path(row["workspace_reference"]) / "workspace")
    destination = output_root(row)
    private_directory(destination.parent)
    destination.mkdir(mode=0o700, exist_ok=True)
    private_directory(destination)
    # Include orphan bytes from failed copies in the per-task bound. Never erase
    # unresolved evidence to create capacity. This count stays stable under lock.
    runtime = row["host"]["binding"]["runtime"]
    remaining = 2 * runtime["max_total_bytes"]
    count = 0
    with os.scandir(destination) as entries:
        for entry in entries:
            count += 1
            info = entry.stat(follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()):
                raise AssociationError("unsafe_retained_output")
            remaining -= info.st_size
            if count + len(paths) > 2 * MAX_ARTIFACTS or remaining <= 0:
                raise AssociationError("staging_reconciliation_required")
    from .associations import _sync_directory
    _sync_directory(destination.parent)
    artifacts, remaining = [], min(remaining, runtime["max_total_bytes"])
    for path, label in zip(paths, labels):
        if remaining <= 0:
            raise AssociationError("result_total_limit")
        original = retained[path] if retained is not None else None
        item = stage_file(source_root=source, relative_path=original.reference if original else path,
                          staging_root=destination, logical_name=label,
                          media_type=original.media_type if original else "application/octet-stream",
                          origin_reference=row["existing_task_id"], max_bytes=min(runtime["max_file_bytes"], remaining))
        if original and (item.sha256 != original.sha256 or item.size_bytes != original.size_bytes):
            raise AssociationError("a0_output_changed_during_copy")
        remaining -= item.size_bytes
        artifacts.append(item)
    return retain_artifacts(store, row["existing_task_id"], row["owner"], artifacts, paths)


def require_result_quiescence(row):
    from .supervision import NativeSupervisor
    quiet = row["host"]["quiescence"]
    if (row["worker_kind"] not in {"dsh", "a0"} or quiet is None
            or row["native"] is None
            or row["worker_kind"] == "a0" and quiet["kind"] != "a0"
            or not NativeSupervisor().observe(row).quiescent):
        raise AssociationError("result_not_quiescent")


def a0_retained_outputs(store, row):
    """Read the original durable preparation and checked A0 artifacts only.

    No runtime binding, keys, container API or recovery launch is needed. The
    existing verifier checks the grant, context, input and response receipts,
    bounded artifact bytes and the separately retained A0 cessation evidence.
    """
    from .adapters.a0 import ExpectedFile, job_prefix, read_retained_result
    from .adapters.a0_native import NativeGrant
    from .controller import Controller
    row = store.get(row["existing_task_id"], row["owner"])
    if row["worker_kind"] != "a0":
        raise AssociationError("foreign_a0_result")
    require_result_quiescence(row)
    prepared = Controller(store, {})._load(row)
    a0 = row["host"]["a0"]
    prefix = job_prefix(row)
    expected = tuple(ExpectedFile('/a0/usr/workdir/' + prefix + '/' + prefix + '-' + item['logical_name'],
                                  **item) for item in a0['expected_files'])
    runtime = row["host"]["binding"]["runtime"]
    return read_retained_result(row, prepared, NativeGrant(**a0['grant']), expected,
                                output_root(row).parent / "a0-outputs",
                                min(runtime['max_file_bytes'], runtime['max_total_bytes']))


def selection_names(paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_ARTIFACTS:
        raise AssociationError("invalid_result_selection")
    labels = []
    for value in paths:
        _text(value, 2048)
        p = Path(value)
        if (p.is_absolute() or str(p) != value or any(part.startswith(".") for part in p.parts)
                or not p.parts):
            raise AssociationError("invalid_result_selection")
        labels.append(_file_name(p.name))
    if len(set(paths)) != len(paths) or len(set(labels)) != len(labels):
        raise AssociationError("duplicate_result_name")
    return labels


def inspect_outputs(row):
    """Only stable checked bytes reach the parent; limited preview is untrusted data."""
    if "result" not in row:
        raise AssociationError("result_not_collected")
    result = []
    for value in row["result"]["artifacts"]:
        data = read_staged(staging_root=output_root(row), artifact=StagedArtifact(**value),
                           max_bytes=row["host"]["binding"]["runtime"]["max_file_bytes"])
        try:
            preview = data[:4096].decode("utf-8")
        except UnicodeError:
            preview = None
        result.append({**value, "preview": preview, "preview_complete": preview is not None and len(data) <= 4096})
    return result


def retain_artifacts(store, task_id, owner, artifacts, source_paths):
    """Caller proves quiescence and stages bytes before retaining the manifest."""
    values = [asdict(a) for a in artifacts]
    with store._locked() as data:
        row = store._owned(data, task_id, owner)
        if "result" in row:
            if row["result"]["artifacts"] != values or row["result"]["source_paths"] != source_paths:
                raise AssociationError("result_already_retained")
            return copy.deepcopy(row)
        row["result"] = {"artifacts": values, "source_paths": copy.deepcopy(source_paths),
                         "deliveries": {a["reference"]: [] for a in values},
                         "observations": {}, "assessment": None}
        store._save(data)
        return copy.deepcopy(row)


def begin_delivery(store, task_id, owner, reference, *, retry=False):
    """Reserve the attempt and return its current presentation snapshot."""
    with store._locked() as data:
        row = store._owned(data, task_id, owner)
        if "result" not in row or reference not in row["result"]["deliveries"]:
            raise AssociationError("unknown_result_artifact")
        attempts = row["result"]["deliveries"][reference]
        if attempts and (attempts[-1]["state"] != "FAILED" or retry is not True):
            raise AssociationError("delivery_requires_reconciliation")
        if len(attempts) >= MAX_DELIVERY_ATTEMPTS:
            raise AssociationError("delivery_attempt_limit")
        attempt = {"number": len(attempts) + 1, "state": "UNKNOWN", "at_unix": store.clock(), "receipt": None}
        attempts.append(attempt)
        row["delivery"] = delivery_state(row["result"]["deliveries"])
        store._save(data)
        return copy.deepcopy(attempt), copy.deepcopy(row)


def finish_delivery(store, task_id, owner, reference, number, receipt):
    with store._locked() as data:
        row = store._owned(data, task_id, owner)
        result = row.get("result", {})
        attempts = result.get("deliveries", {}).get(reference, [])
        if not attempts or type(number) is not int or number != attempts[-1]["number"]:
            raise AssociationError("foreign_delivery_attempt")
        artifact = next(a for a in result["artifacts"] if a["reference"] == reference)
        checked = _receipt(row, artifact, receipt)
        attempt = attempts[-1]
        if attempt["receipt"] is not None and attempt["receipt"] != checked:
            raise AssociationError("delivery_receipt_conflict")
        attempt.update(state=checked["state"], receipt=checked)
        row["delivery"] = delivery_state(result["deliveries"])
        store._save(data)
        return copy.deepcopy(row)


async def deliver_artifact(ctx, store, row, reference, *, retry=False):
    """One explicit send of retained bytes to the retained original destination."""
    from .admission import delivery_route
    row = store.get(row["existing_task_id"], row["owner"])
    artifact = next((a for a in row.get("result", {}).get("artifacts", []) if a["reference"] == reference), None)
    if artifact is None:
        raise AssociationError("unknown_result_artifact")
    # Recheck bytes BEFORE reserving a send. A changed staging file never sends.
    payload = await asyncio.to_thread(read_staged, staging_root=output_root(row), artifact=StagedArtifact(**artifact),
                                      max_bytes=row["host"]["binding"]["runtime"]["max_file_bytes"])
    attempt, row = begin_delivery(store, row["existing_task_id"], row["owner"], reference, retry=retry)
    terminal = row["host"]["terminal"]
    partial = row["stop_intent"] is not None or terminal is None or terminal["state"] != "completed"
    check = {"NOT_RUN": "Проверка цели не выполнена.", "UNKNOWN": "Проверка цели не завершена.",
             "FAIL": "Проверка цели не пройдена.", "PASS": "Проверено чтением файлов; запуск тестов этим не подтверждается."}[row["goal_verification"]]
    caption = ("Частичный результат. " if partial else "Результат исполнителя. ") + check
    try:
        receipt = await ctx.deliver_gateway_document(route=delivery_route(row["host"]["binding"]["ingress"]),
                    data=payload, file_name=artifact["logical_name"], caption=caption, timeout=30)
    except Exception:
        receipt = {"state": "UNKNOWN"}
    # Cancellation/BaseException leaves durable UNKNOWN; no false FAILED/retry.
    return finish_delivery(store, row["existing_task_id"], row["owner"], reference, attempt["number"], receipt)
