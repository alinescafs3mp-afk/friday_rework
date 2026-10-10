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
