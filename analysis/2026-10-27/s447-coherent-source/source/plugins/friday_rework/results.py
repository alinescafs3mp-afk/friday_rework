"""Stable result bytes and delivery attempts in the existing association.

There is no worker launch or implicit retry here. A persisted UNKNOWN precedes
each native send; a crash or missing acknowledgement cannot authorize another.
File integrity and execution completion never certify the user's goal.
"""
from __future__ import annotations

import copy
import asyncio
from contextvars import copy_context
import os
import fcntl
import stat
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import re
import threading
import time

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
    ingress=row['host']['binding']['ingress']
    if ingress['platform'] == 'cli':
        from .admission import delivery_route
        return {'kind':'local-output','sha256':artifact['sha256'],'bytes':artifact['size_bytes'],
                'file_name':artifact['logical_name'],'route':delivery_route(ingress)}
    message = ingress["message"]
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
        allowed = {'cli_document_preflight_rejected'} if row['owner'].get('platform') == 'cli' else {
            'gateway_delivery_preflight_rejected','gateway_document_route_rejected','invalid_document','document_bytes_unsupported'}
        if value.get('error') in allowed:
            return {'state':'FAILED','error':value['error']}
        return {'state':'UNKNOWN'}
    expected = _expected_receipt(row, artifact)
    if row['owner'].get('platform') == 'cli':
        from hermes_cli.friday_cli_work import validate_route
        try:
            validate_route(value.get('route'))
        except Exception:
            return {'state':'UNKNOWN'}
        if type(value.get('bytes')) is not int:
            return {'state':'UNKNOWN'}
        if (value['state']=='DELIVERED' and all(value.get(k)==v for k,v in expected.items())
                and value.get('native_output')=='bounded-original-console-write' and value.get('human_read')=='UNCONFIRMED'):
            return {'state':'DELIVERED',**expected,'native_output':'bounded-original-console-write','human_read':'UNCONFIRMED'}
        return {'state':'UNKNOWN'}
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


def _dsh_result_secrets(row):
    if row["worker_kind"] != "dsh":
        return ()
    # Use the same trusted receiving scope as admission, and bind its values to
    # the original launch receipt. Never use arbitrary ambient environment.
    from .worker_web import scoped_environment
    from .adapters.dsh import checked_output_credentials
    try:
        runtime = row["host"]["binding"]["runtime"]
        dsh = runtime["dsh"]
        names = (dsh["key_name"], "EXA_API_KEY") if dsh.get("web", {}).get("profile") == "exa-paid" else (dsh["key_name"],)
        return checked_output_credentials(row, scoped_environment(runtime["runtime_home"], names))
    except Exception:
        raise AssociationError("dsh_output_credentials_unconfirmed") from None


def _collect_outputs(store, row, paths):
    from .host_runtime import private_directory
    # Recheck the durable selection only after gaining exclusive copy ownership.
    row = store.get(row["existing_task_id"], row["owner"])
    secrets = _dsh_result_secrets(row)
    if "result" in row:
        import json
        from .artifacts import _reject_secrets
        _reject_secrets(json.dumps(row["result"], ensure_ascii=False).encode("utf-8"), secrets)
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
                          origin_reference=row["existing_task_id"], max_bytes=min(runtime["max_file_bytes"], remaining),
                          reject_bytes=secrets)
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
    from .adapters.contract import VerifiedInput
    from .controller import Controller
    row = store.get(row["existing_task_id"], row["owner"])
    if row["worker_kind"] != "a0":
        raise AssociationError("foreign_a0_result")
    require_result_quiescence(row)
    inputs = tuple(VerifiedInput(**item) for item in row["host"]["inputs"])
    prepared = Controller(store, {})._load(row, inputs)
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
    secrets = _dsh_result_secrets(row)
    result = []
    for value in row["result"]["artifacts"]:
        data = read_staged(staging_root=output_root(row), artifact=StagedArtifact(**value),
                           max_bytes=row["host"]["binding"]["runtime"]["max_file_bytes"], reject_bytes=secrets)
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
            return store.consumer_copy(row)
        row["result"] = {"artifacts": values, "source_paths": copy.deepcopy(source_paths),
                         "deliveries": {a["reference"]: [] for a in values},
                         "observations": {}, "assessment": None}
        store._save(data)
        return store.consumer_copy(row)


def _check_gateway_snapshot(row, saved):
    from hermes_cli.friday_user_scope import check_retained_job
    check_retained_job(row)
    fields = ("existing_task_id", "admission_hash", "owner", "worker_kind",
              "brief_sha256", "workspace_reference", "native")
    if (row["owner"].get("platform") == "cli"
            or any(row[k] != saved[k] for k in fields)
            or row["host"]["binding"] != saved["host"]["binding"]
            or row["result"]["artifacts"] != saved["result"]["artifacts"]
            or row["result"]["source_paths"] != saved["result"]["source_paths"]):
        raise AssociationError("foreign_gateway_result_snapshot")


def begin_delivery(store, task_id, owner, reference, *, retry=False,
                   gateway_snapshot=None, completion_check=None):
    """Reserve the attempt and return its current presentation snapshot."""
    with store._locked() as data:
        row = store._owned(data, task_id, owner)
        if "result" not in row or reference not in row["result"]["deliveries"]:
            raise AssociationError("unknown_result_artifact")
        if gateway_snapshot is not None:
            if not callable(completion_check):
                raise AssociationError("invalid_gateway_receipt_context")
            completion_check()
            _check_gateway_snapshot(row, gateway_snapshot)
        attempts = row["result"]["deliveries"][reference]
        if attempts and row["owner"].get("platform") == "cli" and retry is True:
            # Only current ACTUALLY accepted pre-send refusal can resolve a
            # prior UNKNOWN to FAILED for canonical explicit retry. Its original
            # immutable UNKNOWN journal remains forever; no uncertain send is retried.
            view = store.consumer_copy(row)
            prior = view["result"]["deliveries"][reference][-1]
            if attempts[-1]["state"] == "UNKNOWN" and prior["state"] == "FAILED":
                attempts[-1].update(state="FAILED", receipt=copy.deepcopy(prior["receipt"]))
        if attempts and (attempts[-1]["state"] != "FAILED" or retry is not True):
            raise AssociationError("delivery_requires_reconciliation")
        if len(attempts) >= MAX_DELIVERY_ATTEMPTS:
            raise AssociationError("delivery_attempt_limit")
        attempt = {"number": len(attempts) + 1, "state": "UNKNOWN", "at_unix": store.clock(), "receipt": None}
        attempts.append(attempt)
        row["delivery"] = delivery_state(row["result"]["deliveries"])
        selection = None
        if row["owner"].get("platform") == "cli":
            from hermes_cli.friday_cli_caller import current
            from .cli_receipt_selection import OriginalReceiptSelection
            span = current(required=True)
            selection = OriginalReceiptSelection(store, span, row, reference, attempt["number"])
            key = (id(store), task_id, reference, attempt["number"])
            if key in span.receipt_selections:
                raise AssociationError("duplicate_original_receipt_selection")
            span.receipt_selections[key] = selection
        if gateway_snapshot is not None:
            completion_check()
        returned = store._save(data, journals=(("unknown", selection.unknown_history),) if selection is not None else ())
        if selection is not None:
            selection.unknown_save_returned(returned)
        return copy.deepcopy(attempt), copy.deepcopy(row)


def finish_delivery(store, task_id, owner, reference, number, receipt, selection=None,
                    *, gateway_snapshot=None, completion_check=None):
    with store._locked() as data:
        row = store._owned(data, task_id, owner)
        result = row.get("result", {})
        attempts = result.get("deliveries", {}).get(reference, [])
        if not attempts or type(number) is not int or number != attempts[-1]["number"]:
            raise AssociationError("foreign_delivery_attempt")
        artifact = next(a for a in result["artifacts"] if a["reference"] == reference)
        if gateway_snapshot is not None:
            # A receipt cannot adopt a replaced owner, source, manifest, native
            # execution or same-number attempt. Check while holding the CURRENT
            # store locks, immediately before its one permitted metadata save.
            if row["owner"].get("platform") == "cli" or not callable(completion_check):
                raise AssociationError("invalid_gateway_receipt_context")
            completion_check()
            saved = gateway_snapshot
            _check_gateway_snapshot(row, saved)
            if (attempts[-1] != saved["result"]["deliveries"][reference][-1]
                    or attempts[-1]["state"] != "UNKNOWN" or attempts[-1]["receipt"] is not None):
                raise AssociationError("foreign_gateway_receipt_attempt")
        if row["owner"].get("platform") == "cli":
            from hermes_cli.friday_cli_caller import current
            from .cli_receipt_selection import OriginalReceiptSelection
            span = current(required=True)
            if type(selection) is not OriginalReceiptSelection:
                raise AssociationError("original_receipt_selection_missing")
            span.check("receipt_selection_before_commit", cleanup=True)
            selection.begin_commit(store, span, row, reference, number)
        checked = _receipt(row, artifact, receipt)
        attempt = attempts[-1]
        if row["owner"].get("platform") == "cli":
            # Actual UNKNOWN is NEVER overwritten, including native rename,
            # fsync, close, outer caller or supervision acknowledgement failure.
            candidate = selection.prepare_candidate(checked)
            returned = store._save(data, journals=(("candidate", candidate),))
            selection.save_returned(returned)
            return copy.deepcopy(row)
        if attempt["receipt"] is not None and attempt["receipt"] != checked:
            raise AssociationError("delivery_receipt_conflict")
        attempt.update(state=checked["state"], receipt=checked)
        row["delivery"] = delivery_state(result["deliveries"])
        if gateway_snapshot is not None:
            completion_check()
        store._save(data)
        return store.consumer_copy(row)


async def _gateway_result_call(operation, *, deadline):
    """Owned, joined metadata/read work on the existing asyncio executor.

    Shield the actual worker future. Cancellation stops publication at its next
    check and joins the finite in-flight operation; it never detaches a writer.
    The callback receives a checkpoint for the locked pre-publication boundary.
    """
    _number(deadline)
    stopped = threading.Event()
    def check():
        if stopped.is_set():
            raise asyncio.CancelledError()
        if time.monotonic() >= deadline:
            raise TimeoutError("gateway_result_deadline")
    def work():
        # Python 3.14 shield logs exceptions from a cancelled inner Future even
        # when the owner later retrieves them. Keep that executor Future normal;
        # only the owning coroutine may raise the operation's captured error.
        try:
            check()
            return True, operation(check)
        except BaseException as error:
            return False, error
    execution = asyncio.get_running_loop().run_in_executor(None, copy_context().run, work)
    try:
        succeeded, value = await asyncio.shield(execution)
    except asyncio.CancelledError:
        stopped.set()
        # Repeated cancellation must not discard custody of the same worker.
        while not execution.done():
            try:
                await asyncio.shield(execution)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if execution.done() and not execution.cancelled():
            execution.result()  # Consume the ordinary envelope; propagate cancellation.
        raise
    if not succeeded:
        raise value
    return value


async def _deliver_gateway_artifact(ctx, store, row, reference, *, retry=False, deadline=None):
    """One document: original 30-second useful window plus two-second tail.

    Both cutoffs are anchored before reads/reservation/send, never reminted on
    acknowledgement or contention. A blocked receipt save does not resend. Any
    I/O failure or ambiguous transport stays UNKNOWN without an automatic retry.
    """
    from .admission import delivery_route
    from hermes_cli.friday_user_scope import check_retained_job
    started = time.monotonic()
    end = started + 32.0
    if deadline is not None:
        end = min(end, _number(deadline))
    send_end = min(started + 30.0, end - 2.0)
    def current(check):
        actual = store.get(row["existing_task_id"], row["owner"])
        check_retained_job(actual)
        check()
        return actual
    row = await _gateway_result_call(current, deadline=send_end)
    artifact = next((a for a in row.get("result", {}).get("artifacts", [])
                     if a["reference"] == reference), None)
    if artifact is None:
        raise AssociationError("unknown_result_artifact")
    def staged(check):
        payload = read_staged(staging_root=output_root(row), artifact=StagedArtifact(**artifact),
                              max_bytes=row["host"]["binding"]["runtime"]["max_file_bytes"],
                              reject_bytes=_dsh_result_secrets(row))
        check_retained_job(row)
        check()
        return payload
    payload = await _gateway_result_call(staged, deadline=send_end)
    def reserve(check):
        check_retained_job(row)
        check()
        return begin_delivery(store, row["existing_task_id"], row["owner"], reference, retry=retry,
                              gateway_snapshot=row, completion_check=check)
    attempt, row = await _gateway_result_call(reserve, deadline=send_end)
    terminal = row["host"]["terminal"]
    partial = row["stop_intent"] is not None or terminal is None or terminal["state"] != "completed"
    check = {"NOT_RUN": "Проверка цели не выполнена.", "UNKNOWN": "Проверка цели не завершена.",
             "FAIL": "Проверка цели не пройдена.", "PASS": "Проверено чтением файлов; запуск тестов этим не подтверждается."}[row["goal_verification"]]
    caption = ("Частичный результат. " if partial else "Результат исполнителя. ") + check
    remaining = send_end - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("gateway_result_send_deadline")
    # Only the original owned gateway coroutine calls the native transport.
    # Cancellation/BaseException keeps the already durable UNKNOWN fence.
    try:
        async with asyncio.timeout(remaining):
            receipt = await ctx.deliver_gateway_document(
                route=delivery_route(row["host"]["binding"]["ingress"]), data=payload,
                file_name=artifact["logical_name"], caption=caption, timeout=remaining)
    except Exception:
        receipt = {"state": "UNKNOWN"}
    # Detach only the validated native fields. No SDK object, message or mutable
    # acknowledgement can cross into the metadata worker or change its identity.
    checked = _receipt(row, artifact, receipt)
    saved = copy.deepcopy(row)
    def complete(check):
        check()
        with store.delivery_receipt_budget(end):
            return finish_delivery(store, row["existing_task_id"], row["owner"], reference,
                                   attempt["number"], checked, gateway_snapshot=saved,
                                   completion_check=check)
    return await _gateway_result_call(complete, deadline=end)


async def deliver_artifact(ctx, store, row, reference, *, retry=False, deadline=None):
    if row["owner"].get("platform") == "cli":
        return await _deliver_cli_artifact(ctx, store, row, reference, retry=retry, deadline=deadline)
    return await _deliver_gateway_artifact(ctx, store, row, reference, retry=retry, deadline=deadline)


async def _deliver_cli_artifact(ctx, store, row, reference, *, retry=False, deadline=None):
    """One explicit send of retained bytes to the retained original destination."""
    from .admission import delivery_route
    from hermes_cli.friday_cli_caller import current as current_original_caller
    span = current_original_caller()
    local = row["owner"].get("platform") == "cli"
    if local:
        span = current_original_caller(required=True)
        span.check("artifact_entry")
        row = span.sync("artifact_store_get", store.get, row["existing_task_id"], row["owner"])
    else:
        row = store.get(row["existing_task_id"], row["owner"])
    from hermes_cli.friday_user_scope import check_retained_job
    check_retained_job(row)
    local = row['owner'].get('platform') == 'cli'
    if local:
        from hermes_cli.friday_cli_output import output_deadline
        remaining = row['deadline_unix'] - store.clock()
        if remaining <= 0:
            raise AssociationError('original_delivery_budget_exhausted')
        deadline = output_deadline(min(30, remaining), deadline)
    artifact = next((a for a in row.get("result", {}).get("artifacts", []) if a["reference"] == reference), None)
    if artifact is None:
        raise AssociationError("unknown_result_artifact")
    secrets = _dsh_result_secrets(row)
    # Recheck bytes BEFORE reserving a send. A changed staging file never sends.
    if local:
        # Refuse oversize before even opening a staged payload. The ORIGINAL
        # caller owns this read; no cancelled to_thread reader can survive it.
        if type(artifact["size_bytes"]) is not int or artifact["size_bytes"] > 256 * 1024:
            raise AssociationError("cli_staged_document_limit")
        payload = span.sync("staged_original_read", read_staged,
                            staging_root=output_root(row), artifact=StagedArtifact(**artifact),
                            max_bytes=min(256 * 1024, row["host"]["binding"]["runtime"]["max_file_bytes"]), reject_bytes=secrets)
    else:
        payload = await asyncio.to_thread(read_staged, staging_root=output_root(row), artifact=StagedArtifact(**artifact),
                                        max_bytes=row["host"]["binding"]["runtime"]["max_file_bytes"], reject_bytes=secrets)
    check_retained_job(row)
    attempt, row = (begin_delivery(store, row["existing_task_id"], row["owner"], reference, retry=retry) if not local else
                    span.sync("begin_durable_UNKNOWN", begin_delivery, store, row["existing_task_id"],
                              row["owner"], reference, retry=retry))
    if local:
        span.receipt_selections[(id(store), row["existing_task_id"], reference,
                                 attempt["number"])].observe_unknown_boundary_return()
    terminal = row["host"]["terminal"]
    partial = row["stop_intent"] is not None or terminal is None or terminal["state"] != "completed"
    check = {"NOT_RUN": "Проверка цели не выполнена.", "UNKNOWN": "Проверка цели не завершена.",
             "FAIL": "Проверка цели не пройдена.", "PASS": "Проверено чтением файлов; запуск тестов этим не подтверждается."}[row["goal_verification"]]
    caption = ("Частичный результат. " if partial else "Результат исполнителя. ") + check
    try:
        check_retained_job(row)
        send = ctx.deliver_cli_document if row['owner'].get('platform') == 'cli' else ctx.deliver_gateway_document
        kwargs = {'deadline':deadline} if local else {}
        receipt = await send(route=delivery_route(row["host"]["binding"]["ingress"]),
                    data=payload, file_name=artifact["logical_name"], caption=caption, timeout=30, **kwargs)
    except Exception:
        receipt = {"state": "UNKNOWN"}
    # Cancellation/BaseException leaves durable UNKNOWN; no false FAILED/retry.
    check_retained_job(row)
    if local:
        span.check("artifact_observed_before_native_tail")
        span.defer_receipt(finish_delivery, store, row["existing_task_id"], row["owner"],
                           reference, attempt["number"], receipt,
                           span.receipt_selections[(id(store), row["existing_task_id"],
                                                    reference, attempt["number"])])
        return row  # persisted UNKNOWN; never early DELIVERED/false FAILED
    return finish_delivery(store, row["existing_task_id"], row["owner"], reference, attempt["number"], receipt)
