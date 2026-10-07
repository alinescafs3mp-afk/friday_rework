"""Native plugin store and document path, with offline worker/Telegram transport.

These tests prove result glue, not a real Telegram send or a successful goal.
"""
import asyncio
import copy
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_host_native import isolated, setup, native, offline_boundary, ingress, invoke, settle


async def completed(setup, monkeypatch):
    proof = await ingress(setup)
    result = invoke(setup, proof)
    await settle(setup)
    row = setup.host.store.snapshot()[result["reference"]]
    assert row["host"]["terminal"]["state"] == "completed"
    module = importlib.import_module(setup.module.__package__ + ".results")
    supervisor = importlib.import_module(setup.module.__package__ + ".supervision")
    monkeypatch.setattr(supervisor, "NativeSupervisor", setup.module.NativeSupervisor)
    workspace = Path(row["workspace_reference"]) / "workspace"
    (workspace / "answer.txt").write_text("Проверенные байты\n")
    return module, row, workspace


def receipt(module, row, artifact, **changes):
    return {"state": "DELIVERED", **module._expected_receipt(row, artifact), "message_id": "601", **changes}


@pytest.mark.asyncio
async def test_stable_result_survives_worker_file_changes_and_store_reload(setup, monkeypatch):
    module, row, workspace = await completed(setup, monkeypatch)
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    (workspace / "answer.txt").write_text("unrelated later workspace change")
    store = type(setup.host.store)(setup.ctx.state)
    retained = store.get(row["existing_task_id"], row["owner"])
    actual = module.inspect_outputs(retained)
    assert actual[0]["preview"] == "Проверенные байты\n"
    assert retained["goal_verification"] == retained["delivery"] == "NOT_RUN"
    assert module.collect_outputs(store, retained, ["answer.txt"]) == retained
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["escape", "symlink", "hardlink", "fifo", "oversize", "duplicate"])
async def test_untrusted_result_selection_cannot_export_foreign_or_unbounded_bytes(setup, monkeypatch, kind):
    module, row, workspace = await completed(setup, monkeypatch)
    outside = setup.cache / "unrelated.txt"
    outside.write_text("PRIVATE_UNRELATED")
    paths = ["answer.txt"]
    if kind == "escape":
        paths = ["../home/secret"]
    elif kind == "symlink":
        (workspace / "leak.txt").symlink_to(outside)
        paths = ["leak.txt"]
    elif kind == "hardlink":
        (workspace / "leak.txt").hardlink_to(outside)
        paths = ["leak.txt"]
    elif kind == "fifo":
        import os
        os.mkfifo(workspace / "pipe")
        paths = ["pipe"]
    elif kind == "oversize":
        (workspace / "answer.txt").write_bytes(b"x" * 1025)
    else:
        paths *= 2
    with pytest.raises((ValueError, RuntimeError, OSError)):
        module.collect_outputs(setup.host.store, row, paths)
    assert "result" not in setup.host.store.get(row["existing_task_id"], row["owner"])
    assert outside.read_text() == "PRIVATE_UNRELATED"


@pytest.mark.asyncio
async def test_failed_send_retries_same_bytes_without_execution_or_budget_reset(setup, monkeypatch):
    module, row, _ = await completed(setup, monkeypatch)
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    artifact = row["result"]["artifacts"][0]
    observed = []
    async def send(**kwargs):
        stored = setup.host.store.get(row["existing_task_id"], row["owner"])
        assert stored["delivery"] == "UNKNOWN"  # before external effect
        observed.append(kwargs)
        if len(observed) == 1:
            return {"state": "FAILED", "error": "gateway_delivery_preflight_rejected"}
        return receipt(module, row, artifact)
    ctx = SimpleNamespace(deliver_gateway_document=send)
    failed = await module.deliver_artifact(ctx, setup.host.store, row, artifact["reference"])
    assert failed["delivery"] == "FAILED"
    with pytest.raises(RuntimeError, match="reconciliation"):
        await module.deliver_artifact(ctx, setup.host.store, row, artifact["reference"])
    done = await module.deliver_artifact(ctx, setup.host.store, row, artifact["reference"], retry=True)
    assert done["delivery"] == "DELIVERED" and done["goal_verification"] == "NOT_RUN"
    assert len(observed) == 2 and observed[0] == observed[1]
    assert "не выполнена" in observed[0]["caption"]
    assert len(setup.boundary.launches) == 1
    for key in ("native", "deadline_unix", "budget_seconds", "elapsed_seconds", "owner", "stop_intent"):
        assert done[key] == row[key]
    assert observed[0]["route"]["source"]["message_id"] == row["owner"]["message_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "cancel", "wrong_chat", "wrong_hash", "raw_failure", "legacy_ambiguous_failure", "lost_store"])
async def test_unknown_or_lost_ack_stays_nonreplayable(setup, monkeypatch, failure):
    module, row, _ = await completed(setup, monkeypatch)
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    artifact = row["result"]["artifacts"][0]
    store = setup.host.store
    original_save = store._save
    calls = []
    async def send(**kwargs):
        calls.append(kwargs)
        if failure == "timeout":
            raise TimeoutError("SECRET SDK ERROR")
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure == "wrong_chat":
            return receipt(module, row, artifact, chat_id="-999")
        if failure == "wrong_hash":
            return receipt(module, row, artifact, sha256="0" * 64)
        if failure == "raw_failure":
            return {"state": "FAILED", "error": "timeout_after_send_SECRET"}
        if failure == "legacy_ambiguous_failure":
            return {"state": "FAILED", "error": "gateway_delivery_rejected"}
        def fail_write(data):
            raise OSError("injected disk failure")
        monkeypatch.setattr(store, "_save", fail_write)
        return receipt(module, row, artifact)
    try:
        await module.deliver_artifact(SimpleNamespace(deliver_gateway_document=send), store, row, artifact["reference"])
    except (asyncio.CancelledError, OSError):
        assert failure in {"cancel", "lost_store"}
    monkeypatch.setattr(store, "_save", original_save)
    retained = store.get(row["existing_task_id"], row["owner"])
    assert retained["delivery"] == "UNKNOWN" and "SECRET" not in str(retained)
    for retry in (False, True):
        with pytest.raises(RuntimeError, match="reconciliation"):
            module.begin_delivery(store, row["existing_task_id"], row["owner"], artifact["reference"], retry=retry)
    assert len(calls) == len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_changed_staged_bytes_never_reach_transport(setup, monkeypatch):
    module, row, _ = await completed(setup, monkeypatch)
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    artifact = row["result"]["artifacts"][0]
    path = module.output_root(row) / artifact["reference"]
    path.chmod(0o600)
    path.write_text("altered bytes")
    path.chmod(0o400)
    async def forbidden(**kwargs):
        raise AssertionError("transport must not be reached")
    with pytest.raises(RuntimeError, match="staged_artifact_changed"):
        await module.deliver_artifact(SimpleNamespace(deliver_gateway_document=forbidden), setup.host.store, row, artifact["reference"])
    assert setup.host.store.get(row["existing_task_id"], row["owner"])["delivery"] == "NOT_RUN"


@pytest.mark.asyncio
async def test_foreign_owner_and_late_receipt_cannot_change_result(setup, monkeypatch):
    module, row, _ = await completed(setup, monkeypatch)
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    artifact = row["result"]["artifacts"][0]
    with pytest.raises(RuntimeError, match="foreign"):
        module.begin_delivery(setup.host.store, row["existing_task_id"], {**row["owner"], "chat_id": "-999"}, artifact["reference"])
    attempt, snapshot = module.begin_delivery(setup.host.store, row["existing_task_id"], row["owner"], artifact["reference"])
    assert snapshot["delivery"] == "UNKNOWN"
    with pytest.raises(RuntimeError, match="foreign_delivery_attempt"):
        module.finish_delivery(setup.host.store, row["existing_task_id"], row["owner"], artifact["reference"], 999, receipt(module, row, artifact))
    done = module.finish_delivery(setup.host.store, row["existing_task_id"], row["owner"], artifact["reference"], attempt["number"], receipt(module, row, artifact))
    with pytest.raises(RuntimeError, match="conflict"):
        module.finish_delivery(setup.host.store, row["existing_task_id"], row["owner"], artifact["reference"], attempt["number"], {"state": "UNKNOWN"})
    assert setup.host.store.get(row["existing_task_id"], row["owner"]) == done


@pytest.mark.asyncio
async def test_incomplete_collection_can_retry_copy_without_worker_or_clobber(setup, monkeypatch):
    module, row, _ = await completed(setup, monkeypatch)
    with pytest.raises(FileNotFoundError):
        module.collect_outputs(setup.host.store, row, ["answer.txt", "missing.txt"])
    preserved = {p.name: p.read_bytes() for p in module.output_root(row).iterdir()}
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    assert module.inspect_outputs(row)[0]["preview"] == "Проверенные байты\n"
    for name, data in preserved.items():
        assert (module.output_root(row) / name).read_bytes() == data
    with pytest.raises(RuntimeError, match="selection_already_retained"):
        module.collect_outputs(setup.host.store, row, ["different.txt"])
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_multiple_files_keep_individual_receipts_and_never_duplicate_success(setup, monkeypatch):
    module, row, workspace = await completed(setup, monkeypatch)
    (workspace / "second.txt").write_text("second")
    row = module.collect_outputs(setup.host.store, row, ["answer.txt", "second.txt"])
    a, b = row["result"]["artifacts"]
    n = module.begin_delivery(setup.host.store, row["existing_task_id"], row["owner"], a["reference"])[0]["number"]
    row = module.finish_delivery(setup.host.store, row["existing_task_id"], row["owner"], a["reference"], n, receipt(module, row, a))
    assert row["delivery"] == "PARTIAL"
    n = module.begin_delivery(setup.host.store, row["existing_task_id"], row["owner"], b["reference"])[0]["number"]
    row = module.finish_delivery(setup.host.store, row["existing_task_id"], row["owner"], b["reference"], n, receipt(module, row, b))
    assert row["delivery"] == "DELIVERED"
    with pytest.raises(RuntimeError, match="reconciliation"):
        module.begin_delivery(setup.host.store, row["existing_task_id"], row["owner"], a["reference"], retry=True)
