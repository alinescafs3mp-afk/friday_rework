"""Actual plugin registration/middleware; transport remains offline."""
from contextvars import Context, ContextVar
import importlib
import json

import pytest

from test_host_native import isolated, setup, native, offline_boundary, CALL
from test_result_delivery import completed
from hermes_cli.middleware import run_tool_execution_middleware
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from tools.registry import registry


def enable_results(setup):
    import hermes_yaml as yaml
    path = setup.home / "config.yaml"
    value = yaml.safe_load(path.read_text())
    value["plugins"]["entries"]["friday_rework"]["settings"]["results"] = {"enabled": True}
    path.write_text(yaml.safe_dump(value))


def invoke_result(setup, row, args, *, fields=None, call=None, middleware=True):
    proof = row["host"]["binding"]["ingress"]
    call = call or {**CALL, "tool_call_id": "result-" + args["action"]}
    def bound():
        values = dict(PLATFORM="telegram", CHAT_ID=row["owner"]["chat_id"], CHAT_TYPE=proof["chat_type"],
                      THREAD_ID=row["owner"]["thread_id"], USER_ID=row["owner"]["user_id"],
                      KEY=row["owner"]["session_key"], ID=call["session_id"], MESSAGE_ID="new-parent-message",
                      PROFILE=proof["source_profile"])
        values.update(fields or {})
        for k, v in values.items():
            ContextVar("HERMES_SESSION_" + k).set(v)
        token = set_hermes_home_override(setup.home)
        try:
            def dispatch(supplied):
                return registry.dispatch("friday_result", supplied, scope=setup.manager.scope_key, **call)
            value = run_tool_execution_middleware("friday_result", args, dispatch, **call) if middleware else dispatch(args)
            return json.loads(value)
        finally:
            reset_hermes_home_override(token)
    return Context().run(bound)


@pytest.mark.asyncio
async def test_parent_inspection_and_assessment_use_actual_native_evidence(setup, monkeypatch):
    module, row, _ = await completed(setup, monkeypatch)
    enable_results(setup)
    common = {"reference": row["existing_task_id"]}
    listing = invoke_result(setup, row, {**common, "action": "list"})
    assert listing["files"] == [{"path": "answer.txt", "bytes": len("Проверенные байты\n".encode())}]
    inspected = invoke_result(setup, row, {**common, "action": "inspect", "paths": ["answer.txt"]})
    assert inspected["artifacts"][0]["preview"] == "Проверенные байты\n"
    assert inspected["goal_verification"] == "NOT_RUN"
    missing = {**common, "action": "assess", "verdict": "PASS", "rationale": "Claim without independent observation", "observations": ["not-an-observation"]}
    assert not invoke_result(setup, row, missing)["accepted"]
    assessed = invoke_result(setup, row, {**missing, "observations": [inspected["observation_reference"]],
                                       "rationale": "The full text content matches the requested text. No executed test claim."})
    assert assessed["goal_verification"] == "PASS"
    assert assessed["assessment"]["method"] == "parent_file_review"
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["USER_ID", "CHAT_ID", "THREAD_ID", "KEY", "PROFILE", "CHAT_TYPE", "ID"])
async def test_result_read_does_not_follow_foreign_or_replacement_session(setup, monkeypatch, field):
    _, row, _ = await completed(setup, monkeypatch)
    enable_results(setup)
    response = invoke_result(setup, row, {"action": "list", "reference": row["existing_task_id"]}, fields={field: "different"})
    assert response == {"accepted": False, "error": "result_unavailable"}
    assert "result" not in setup.host.store.get(row["existing_task_id"], row["owner"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["missing_scope", "wrong_task", "unknown_reference", "route_payload", "disabled"])
async def test_model_content_cannot_grant_result_authority(setup, monkeypatch, mutation):
    _, row, _ = await completed(setup, monkeypatch)
    if mutation != "disabled":
        enable_results(setup)
    args = {"action": "list", "reference": row["existing_task_id"]}
    if mutation == "unknown_reference":
        args["reference"] = "another-task"
    if mutation == "route_payload":
        args["route"] = {"chat_id": "-1"}
    call = {**CALL, "task_id": "foreign-task"} if mutation == "wrong_task" else None
    assert not invoke_result(setup, row, args, call=call, middleware=mutation != "missing_scope")["accepted"]


@pytest.mark.asyncio
async def test_notification_records_only_scheduled_and_parent_read_proves_consumption(setup, monkeypatch):
    _, row, _ = await completed(setup, monkeypatch)
    enable_results(setup)
    tool_module = importlib.import_module(setup.module.__package__ + ".result_tool")
    observed = []
    def schedule(content, **kwargs):
        observed.append((json.loads(content), kwargs))
        assert setup.host.store.get(row["existing_task_id"], row["owner"])["notification"]["state"] == "UNKNOWN"
        return True
    monkeypatch.setattr(setup.ctx, "inject_message", schedule)
    await tool_module.notify_finished(setup.host, row)
    await tool_module.notify_finished(setup.host, row)
    current = setup.host.store.get(row["existing_task_id"], row["owner"])
    assert current["notification"]["state"] == "SCHEDULED" and len(observed) == 1
    assert observed[0][1] == {"session_key": row["owner"]["session_key"], "expected_session_id": row["owner"]["session_id"]}
    assert "UNTRUSTED WORKER CLAIM" not in str(observed)
    result = invoke_result(setup, row, {"action": "inspect", "reference": row["existing_task_id"], "paths": ["answer.txt"]})
    assert result["accepted"]
    assert setup.host.store.get(row["existing_task_id"], row["owner"])["notification"]["state"] == "OBSERVED"


@pytest.mark.asyncio
async def test_partial_review_cannot_pass_or_hide_test_gap(setup, monkeypatch):
    module, row, workspace = await completed(setup, monkeypatch)
    enable_results(setup)
    # Invalid UTF-8 is still a valid file transfer, not a completed text review.
    (workspace / "answer.txt").write_bytes(b"\xff\x00")
    common = {"reference": row["existing_task_id"]}
    inspected = invoke_result(setup, row, {**common, "action": "inspect", "paths": ["answer.txt"]})
    assert inspected["artifacts"][0]["preview"] is None
    assessment = {**common, "action": "assess", "verdict": "PASS", "rationale": "Cannot inspect these bytes", "observations": [inspected["observation_reference"]]}
    assert not invoke_result(setup, row, assessment)["accepted"]
    unknown = invoke_result(setup, row, {**assessment, "verdict": "UNKNOWN"})
    assert unknown["goal_verification"] == "UNKNOWN" and unknown["execution"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("replaced", [False, True])
async def test_completion_through_real_context_and_gateway_pins_original_session(setup, monkeypatch, replaced):
    import asyncio
    from datetime import datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import hermes_yaml as yaml
    from gateway.session import SessionEntry
    from gateway.config import Platform

    _, row, _ = await completed(setup, monkeypatch)
    enable_results(setup)
    path = setup.home / "config.yaml"
    config = yaml.safe_load(path.read_text())
    config["plugins"]["entries"]["friday_rework"]["allow_gateway_injection"] = True
    path.write_text(yaml.safe_dump(config))
    _, event = setup.native.make()
    entry = SessionEntry(session_key=row["owner"]["session_key"],
                         session_id="replacement-session" if replaced else row["owner"]["session_id"],
                         created_at=datetime.now(), updated_at=datetime.now(),
                         origin=event.source, platform=Platform.TELEGRAM)
    runner = setup.native.runner
    lookup_gate = asyncio.Event()
    async def lookup(_key):
        await lookup_gate.wait()
        return entry
    runner._async_session_store = SimpleNamespace(
        _store=runner.session_store, lookup_by_session_key=lookup)
    handled = AsyncMock()
    monkeypatch.setattr(setup.native.adapter, "handle_message", handled)
    tool_module = importlib.import_module(setup.module.__package__ + ".result_tool")
    await tool_module.notify_finished(setup.host, row)
    tasks = tuple(runner._background_tasks)
    assert len(tasks) == 1
    lookup_gate.set()
    assert await asyncio.gather(*tasks) == [not replaced]
    current = setup.host.store.get(row["existing_task_id"], row["owner"])
    assert current["notification"]["state"] == "SCHEDULED"
    assert current["goal_verification"] == current["delivery"] == "NOT_RUN"
    if replaced:
        handled.assert_not_awaited()
    else:
        received = handled.await_args.args[0]
        assert received.metadata["gateway_session_id"] == row["owner"]["session_id"]
        assert received.metadata["gateway_session_strict"] is True
        assert not received.allow_gateway_control
        assert json.loads(received.text)["friday_worker_result"] == row["existing_task_id"]
    assert len(setup.boundary.launches) == 1
