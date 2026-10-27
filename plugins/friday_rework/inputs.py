"""Stage bytes only from a matched native admission's file receipts.

Native receive stamps the content digest; hashing a mutable cache later cannot
create that authority. Root selection and worker mount mapping are host inputs.
The adapter must verify the actual worker-visible bytes before submission.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from .admission import _snapshot
from .adapters.contract import VerifiedInput
from .artifacts import ArtifactError, stage_file


def stage_inputs(*, matched_ingress, admitted_reference, cache_roots,
                 staging_root, worker_input_root, max_file_bytes, max_total_bytes):
    """Return a complete input mapping or refuse the whole dependent task.

    A zero-file message returns no inputs; deciding whether the brief required
    a missing reply/file belongs to the host, never a substitute-file fallback.
    Old receipts lacking content remain readable, but cannot authorize bytes.
    """
    ingress = _snapshot(matched_ingress)
    if ingress['platform'] == 'cli':
        from hermes_cli.friday_cli_work import check_owner, owner_from_receipt
        check_owner(owner_from_receipt(ingress), ingress)
        if ingress['input']['attachments'] != []:
            raise ArtifactError('cli_file_receive_unsupported')
        return ()
    if (type(max_file_bytes) is not int or max_file_bytes <= 0
            or type(max_total_bytes) is not int or max_total_bytes <= 0):
        raise ArtifactError("invalid_input_limits")
    if (not isinstance(admitted_reference, str) or not admitted_reference.strip()
            or "\x00" in admitted_reference or len(admitted_reference.encode("utf-8")) > 2048):
        raise ArtifactError("invalid_input_receipt")
    if not isinstance(worker_input_root, str) or "\x00" in worker_input_root:
        raise ArtifactError("invalid_worker_input_mapping")
    worker_root = PurePosixPath(worker_input_root)
    if (not worker_root.is_absolute() or worker_root == PurePosixPath("/")
            or ".." in worker_root.parts or worker_input_root.startswith("//")
            or str(worker_root) != worker_input_root):
        raise ArtifactError("invalid_worker_input_mapping")
    roots = tuple(Path(root) for root in cache_roots)
    if not roots or any(not root.is_absolute() or root.resolve() != root for root in roots):
        raise ArtifactError("invalid_native_cache_roots")
    selected, total = [], 0
    for media in ingress["message"]["media"]:
        origin, content = media["origin"], media.get("content")
        if origin is None or content is None:
            raise ArtifactError("unproved_input_bytes")
        message = ingress["message"]
        if origin["message_id"] not in {message["message_id"], message["reply_to_message_id"]}:
            raise ArtifactError("input_outside_admitted_message")
        source = Path(media["local_reference"])
        matches = [root for root in roots if source.is_relative_to(root)]
        if not source.is_absolute() or len(matches) != 1:
            raise ArtifactError("input_outside_native_cache")
        count = content["size_bytes"]
        total += count
        if count > max_file_bytes or total > max_total_bytes:
            raise ArtifactError("input_too_large")
        selected.append((media, source, matches[0]))
    result = []
    for media, source, root in selected:
        staged = stage_file(source_root=root, relative_path=source.relative_to(root).as_posix(),
                            staging_root=staging_root, logical_name=source.name,
                            media_type=media["mime_type"], origin_reference=admitted_reference,
                            max_bytes=max_file_bytes)
        if (staged.size_bytes != media["content"]["size_bytes"]
                or staged.sha256 != media["content"]["sha256"]):
            # No mapping is returned and no worker is launched. The private
            # retained copy is evidence of changed cache bytes, not a grant.
            raise ArtifactError("input_bytes_changed_since_receive")
        result.append(VerifiedInput(str(Path(staging_root) / staged.reference),
                                    str(worker_root / staged.reference), staged.size_bytes,
                                    staged.sha256, admitted_reference))
    return tuple(result)


def stage_retained_outputs(*, store, retained_row, retained_paths,
                           retained_expectations, required_input, current_owner,
                           matched_ingress, admitted_reference, cache_roots,
                           staging_root, worker_input_root, max_file_bytes,
                           max_total_bytes):
    """Stage one admitted original plus explicitly bound, quiescent DSH outputs.

    The trusted host supplies canonical owners and expected hashes. First use
    may freeze the old output manifest through collect_outputs; this is a
    bounded file/store effect, not a read-only inspection. No worker is launched.
    """
    import os
    import re
    from .artifacts import StagedArtifact, read_staged
    from .associations import AssociationError, _owner
    from .host_record import owner_from_ingress
    from hermes_constants import get_hermes_home
    from hermes_cli.friday_user_scope import check_retained_job
    from .results import (_dsh_result_secrets, collect_outputs, output_root,
                          require_result_quiescence, selection_names)

    ingress = _snapshot(matched_ingress)
    if ingress["platform"] != "telegram":
        raise AssociationError("retained_input_platform_unsupported")
    row = store.get(retained_row["existing_task_id"], retained_row["owner"])
    original = _owner(row["owner"])
    current_owner = _owner(current_owner)
    binding = row["host"]["binding"]
    old_ingress = _snapshot(binding["ingress"])
    owner_fields = ("bot_id", "user_id", "chat_id", "thread_id",
                    "session_key", "session_id", "profile")
    if (row["worker_kind"] != "dsh"
            or old_ingress["platform"] != "telegram"
            or original != owner_from_ingress(binding["correlation"], old_ingress)
            or current_owner != owner_from_ingress(
                {"session_id": current_owner["session_id"]}, ingress)
            or any(original[k] != current_owner[k] for k in owner_fields)
            or any(old_ingress.get(k) != ingress.get(k) for k in
                   ("source_profile", "transport_profile", "runtime_profile", "chat_type"))
            or Path(binding["runtime"]["runtime_home"]) != get_hermes_home()):
        raise AssociationError("foreign_retained_output_owner")
    # Current native authority rechecks principal, generation and protected home;
    # matching serialized owners alone cannot authorize a retained job.
    check_retained_job(row)
    require_result_quiescence(row)
    if (not isinstance(required_input, dict)
            or set(required_input) != {"size_bytes", "sha256"}
            or type(required_input["size_bytes"]) is not int
            or required_input["size_bytes"] < 0
            or not isinstance(required_input["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", required_input["sha256"])):
        raise AssociationError("invalid_required_input")
    media = ingress["message"]["media"]
    if len(media) != 1 or media[0].get("content") != required_input:
        raise AssociationError("required_original_input_missing")
    if (type(max_file_bytes) is not int or max_file_bytes <= 0
            or type(max_total_bytes) is not int or max_total_bytes <= 0):
        raise ArtifactError("invalid_input_limits")
    labels = selection_names(retained_paths)
    if Path(media[0]["local_reference"]).name in labels:
        raise AssociationError("duplicate_input_name")
    if not isinstance(retained_expectations, dict) or set(retained_expectations) != set(retained_paths):
        raise AssociationError("retained_expectation_selection_mismatch")
    expected = {}
    for path in retained_paths:
        value = retained_expectations[path]
        if (not isinstance(value, dict) or set(value) != {"size_bytes", "sha256"}
                or type(value["size_bytes"]) is not int or value["size_bytes"] < 0
                or not isinstance(value["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
            raise AssociationError("invalid_retained_expectation")
        expected[path] = value
    if (1 + len(retained_paths) > 64
            or any(v["size_bytes"] > max_file_bytes for v in expected.values())
            or required_input["size_bytes"]
            + sum(v["size_bytes"] for v in expected.values()) > max_total_bytes):
        raise ArtifactError("input_too_large")

    fd = os.open(staging_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with os.scandir(fd) as entries:
            if next(entries, None) is not None:
                raise AssociationError("retained_input_replay_or_nonempty_staging")
    finally:
        os.close(fd)
    ordinary = stage_inputs(
        matched_ingress=ingress, admitted_reference=admitted_reference,
        cache_roots=cache_roots, staging_root=staging_root,
        worker_input_root=worker_input_root, max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes)
    if (len(ordinary) != 1 or ordinary[0].size_bytes != required_input["size_bytes"]
            or ordinary[0].sha256 != required_input["sha256"]):
        raise AssociationError("required_original_input_missing")
    check_retained_job(row)
    retained = collect_outputs(store, row, retained_paths)
    check_retained_job(retained)
    require_result_quiescence(retained)
    if retained["result"]["source_paths"] != retained_paths:
        raise AssociationError("retained_result_selection_mismatch")
    artifacts = retained["result"]["artifacts"]
    if len(artifacts) != len(retained_paths):
        raise AssociationError("retained_result_selection_mismatch")
    secrets = _dsh_result_secrets(retained)
    worker_root = PurePosixPath(worker_input_root)
    result = list(ordinary)
    for path, label, value in zip(retained_paths, labels, artifacts):
        artifact = StagedArtifact(**value)
        if (artifact.logical_name != label
                or artifact.origin_reference != row["existing_task_id"]
                or artifact.size_bytes != expected[path]["size_bytes"]
                or artifact.sha256 != expected[path]["sha256"]):
            raise AssociationError("retained_output_changed")
        original_bytes = read_staged(
            staging_root=output_root(retained), artifact=artifact,
            max_bytes=max_file_bytes, reject_bytes=secrets)
        staged = stage_file(
            source_root=output_root(retained), relative_path=artifact.reference,
            staging_root=staging_root, logical_name=label,
            media_type=artifact.media_type, origin_reference=admitted_reference,
            max_bytes=max_file_bytes, reject_bytes=secrets)
        if staged.size_bytes != artifact.size_bytes or staged.sha256 != artifact.sha256:
            raise AssociationError("retained_output_changed")
        item = VerifiedInput(str(Path(staging_root) / staged.reference),
                             str(worker_root / staged.reference), staged.size_bytes,
                             staged.sha256, admitted_reference)
        if any(v.host_path == item.host_path or v.worker_path == item.worker_path
               for v in result):
            raise AssociationError("duplicate_input_mapping")
        checked = read_staged(staging_root=staging_root, artifact=staged,
                              max_bytes=max_file_bytes, reject_bytes=secrets)
        if checked != original_bytes:
            raise AssociationError("retained_output_changed")
        result.append(item)
    return tuple(result)
