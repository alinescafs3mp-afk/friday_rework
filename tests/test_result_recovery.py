"""Real file/state concurrency controls, with offline native worker/transport."""
import asyncio
import threading
import time

import pytest

from test_host_native import isolated, setup, native, offline_boundary
from test_result_delivery import completed


@pytest.mark.asyncio
async def test_copy_owner_serializes_staging_without_blocking_stop(setup, monkeypatch):
    module, row, workspace = await completed(setup, monkeypatch)
    paths = [f"file-{i}.txt" for i in range(16)]
    for path in paths:
        (workspace / path).write_text("x")
    entered, release = threading.Event(), threading.Event()
    original = module.stage_file
    def held(**kwargs):
        entered.set()
        assert release.wait(3)
        return original(**kwargs)
    monkeypatch.setattr(module, "stage_file", held)
    first = asyncio.create_task(asyncio.to_thread(module.collect_outputs, setup.host.store, row, paths))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        # Separate store instances cannot become a second copy owner.
        for _ in range(3):
            store = type(setup.host.store)(setup.ctx.state)
            began = time.monotonic()
            with pytest.raises(RuntimeError, match="output_copy_busy"):
                await asyncio.to_thread(module.collect_outputs, store, row, paths)
            assert time.monotonic() - began < .5
        # The copy lock is separate from the existing control metadata lock.
        stopped = setup.host.store.request_stop(row["existing_task_id"], row["owner"], "cancel")
        assert stopped["stop_intent"] == "cancel"
    finally:
        release.set()
        retained = await first
    assert len(list(module.output_root(row).iterdir())) == 16
    assert retained["stop_intent"] == "cancel"
    # Same selection reuses exact files after ownership has been released.
    assert module.collect_outputs(setup.host.store, row, paths) == retained
    assert len(list(module.output_root(row).iterdir())) == 16
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["count", "bytes"])
async def test_failed_copy_evidence_consumes_bounded_capacity(setup, monkeypatch, limit):
    module, row, workspace = await completed(setup, monkeypatch)
    if limit == "count":
        paths = [f"file-{i}.txt" for i in range(15)]
        for path in paths:
            (workspace / path).write_text("x")
        for _ in range(2):
            with pytest.raises(FileNotFoundError):
                module.collect_outputs(setup.host.store, row, [*paths, "missing.txt"])
        expected = 30
    else:
        paths = [f"file-{i}.txt" for i in range(3)]
        for path in paths:
            (workspace / path).write_bytes(b"x" * 1024)
        for _ in range(2):
            with pytest.raises(FileNotFoundError):
                module.collect_outputs(setup.host.store, row, [*paths, "missing.txt"])
        # Only 2KiB of the 8KiB directory allowance remains; third file refuses.
        with pytest.raises(RuntimeError, match="result_total_limit"):
            module.collect_outputs(setup.host.store, row, paths)
        expected = 8
    with pytest.raises(RuntimeError, match="staging_reconciliation_required"):
        module.collect_outputs(setup.host.store, row, [*paths, "missing.txt"])
    files = list(module.output_root(row).iterdir())
    assert len(files) == expected <= 2 * module.MAX_ARTIFACTS
    assert sum(path.stat().st_size for path in files) <= 2 * setup.runtime["max_total_bytes"]
    assert "result" not in setup.host.store.get(row["existing_task_id"], row["owner"])


@pytest.mark.asyncio
async def test_delivery_uses_stop_snapshot_after_actual_staging_read(setup, monkeypatch):
    from gateway.platforms.base import SendResult
    module, row, _ = await completed(setup, monkeypatch)
    setup.configure(setup.runtime, allow_gateway_delivery=True)
    row = module.collect_outputs(setup.host.store, row, ["answer.txt"])
    artifact = row["result"]["artifacts"][0]
    original, sent = module.read_staged, []
    def cancel_after_read(**kwargs):
        payload = original(**kwargs)
        setup.host.store.request_stop(row["existing_task_id"], row["owner"], "cancel")
        return payload
    async def native_document(chat_id, data, **kwargs):
        sent.append(kwargs)
        return SendResult(success=True, message_id="601", raw_response={
            **module._expected_receipt(row, artifact), "message_id": "601"})
    monkeypatch.setattr(module, "read_staged", cancel_after_read)
    monkeypatch.setattr(setup.native.adapter, "send_document_bytes", native_document)
    final = await module.deliver_artifact(setup.ctx, setup.host.store, row, artifact["reference"])
    assert len(sent) == 1 and sent[0]["caption"].startswith("Частичный результат.")
    assert final["stop_intent"] == "cancel" and final["delivery"] == "DELIVERED"
    assert final["goal_verification"] == "NOT_RUN" and len(setup.boundary.launches) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "mode"])
async def test_copy_lock_cannot_alias_another_file(setup, monkeypatch, unsafe):
    module, row, _ = await completed(setup, monkeypatch)
    lock = module.output_root(row).parent / ".outputs-copy.lock"
    foreign = setup.cache / "unrelated"
    foreign.write_bytes(b"PRIVATE_UNRELATED")
    if unsafe == "symlink":
        lock.symlink_to(foreign)
    elif unsafe == "hardlink":
        lock.hardlink_to(foreign)
    else:
        lock.write_bytes(b"")
        lock.chmod(0o644)
    with pytest.raises((RuntimeError, OSError)):
        module.collect_outputs(setup.host.store, row, ["answer.txt"])
    assert foreign.read_bytes() == b"PRIVATE_UNRELATED"
    assert "result" not in setup.host.store.get(row["existing_task_id"], row["owner"])
