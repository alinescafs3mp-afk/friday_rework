"""Actual Hermes PluginManager, PluginState, middleware and gateway work API.

The accepted DSH adapter performs real preparation/receipt/event reduction.
Only its native systemd boundary is an offline fixture. No native worker,
inference, network or Telegram send is executed or claimed as acceptance.
Run with Hermes's canonical per-file runner and an isolated HERMES_HOME.
"""
from __future__ import annotations

import asyncio
import copy
from contextvars import Context, ContextVar
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from hermes_cli import plugins
from hermes_cli.middleware import run_tool_execution_middleware
from hermes_cli.plugin_command_context import _command_context
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from tools.registry import registry
from tests.gateway.test_admitted_ingress import native, offline_boundary

SOURCE = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
ARGS = dict(worker="dsh", brief="Read the supplied fixture only.", goal_check="Host independently checks the fixture bytes.")
CALL = dict(task_id="native-session", session_id="native-session", turn_id="native-turn",
            api_request_id="native-api-request", tool_call_id="native-call")
SESSION = "session-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
INV = "a" * 32


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(plugins, "get_bundled_plugins_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(plugins.PluginManager, "_scan_entry_points", lambda self: [])
    token = set_hermes_home_override(home)
    plugins._reset_plugin_managers_for_tests()
    yield home
    plugins._reset_plugin_managers_for_tests()
    reset_hermes_home_override(token)


@pytest.fixture
def setup(isolated, native, tmp_path, monkeypatch):
    import hermes_yaml as yaml
    destination = isolated / "plugins/friday_rework"
    shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__"))
    config = {"plugins": {"enabled": ["friday_rework"], "entries": {"friday_rework": {
        "allow_gateway_work": True, "allow_gateway_control": True, "settings": {}}}}}
    def configure(runtime=None, **flags):
        entry = config["plugins"]["entries"]["friday_rework"]
        entry["settings"] = {} if runtime is None else {"runtime": runtime}
        entry.update(flags)
        (isolated / "config.yaml").write_text(yaml.safe_dump(config))
    configure()
    manager = plugins.get_plugin_manager()
    manager.discover_and_load()
    assert manager._plugins["friday_rework"].enabled, manager._plugins["friday_rework"].error
    entry = registry.get_entry("friday_work", scope=manager.scope_key)
    host = entry.handler.__self__
    package = manager._plugins["friday_rework"].module.__name__
    host_module = sys.modules[package + ".host"]
    runtime_module = sys.modules[package + ".host_runtime"]
    record_module = sys.modules[package + ".host_record"]
    supervisor_module = sys.modules[package + ".supervision"]
    jobs, staging, cache, payload, tools = [tmp_path / name for name in ("jobs", "staged", "cache", "payload", "toolchain")]
    for directory in (jobs, staging, cache, payload, tools):
        directory.mkdir(mode=0o700)
    (payload / "apps/cli/lib").mkdir(parents=True)
    node, cli, patchfile, nativefile = tools / "node", payload / "apps/cli/lib/bin.js", tmp_path / "profile.yml", payload / "native.js"
    for p in (node, cli, patchfile, nativefile):
        p.write_bytes(b"OFFLINE FIXTURE BYTES; NOT A DEPLOYMENT\n")
    runtime = dict(enabled=True, runtime_profile="default", runtime_home=str(isolated), workspace_root=str(jobs), staging_root=str(staging),
                   cache_roots=[str(cache)], budget_seconds=60, max_file_bytes=1024, max_total_bytes=4096,
                   dsh=dict(payload_root=str(payload), toolchain_root=str(tools), node=pin(node), cli=pin(cli),
                            patch=pin(patchfile), native_files=[pin(nativefile)], key_name="OFFLINE_DSH_KEY",
                            profile="headless", memory_bytes=2*1024**3, cpu_percent=200, tasks=64,
                            shutdown_seconds=2, tmp_bytes=64*1024**2))
    evidence = tmp_path / "fixture-evidence.json"
    evidence.write_text('{"scope":"offline native boundary fixture only"}')
    receipt = tmp_path / "runtime-receipt.json"
    receipt.write_text(json.dumps(dict(schema="friday-rework.dsh-runtime.v1", ready=True,
        runtime_sha256=record_module.digest(runtime), adapter_sha256=pin(destination / "adapters/dsh.py")["sha256"],
        evidence=[pin(evidence)])))
    runtime["runtime_receipt"] = pin(receipt)
    configure(runtime)
    monkeypatch.setenv("OFFLINE_DSH_KEY", "offline-value-not-a-secret")
    (isolated / ".env").write_text("OFFLINE_DSH_KEY=offline-profile-value\n")

    boundary = SimpleNamespace(units={}, launches=[], stops=[], completed=True, fail_launch=False)
    class Supervisor:
        description = staticmethod(supervisor_module.NativeSupervisor.description)
        def observe(self, row):
            unit = boundary.units.get(row["supervisor"]["unit"])
            if unit and row["native"] and row["native"]["invocation_id"] != INV:
                raise RuntimeError("foreign_invocation")
            running = bool(unit and unit["running"])
            return supervisor_module.UnitObservation(row["supervisor"]["unit"], INV if unit else "",
                "active" if running else "inactive", "running" if running else "dead", "success",
                42 if running else 0, "/offline/unit" if running else "", running, unit is None)
        def stop(self, row):
            self.observe(row)
            boundary.stops.append(row["supervisor"]["unit"])
            if row["supervisor"]["unit"] in boundary.units:
                boundary.units[row["supervisor"]["unit"]]["running"] = False
            return self.observe(row)
    monkeypatch.setattr(host_module, "NativeSupervisor", Supervisor)
    monkeypatch.setattr(runtime_module, "NativeSupervisor", Supervisor)
    started = threading.Event()
    start = host._start
    def start_observed(row):
        try:
            return start(row)
        finally:
            started.set()
    monkeypatch.setattr(host, "_start", start_observed)

    def launch(argv, **kwargs):
        assert argv[0] == "/usr/bin/systemd-run", "No other subprocess permitted"
        assert kwargs["env"]["OFFLINE_DSH_KEY"] == "offline-profile-value"
        assert not boundary.fail_launch, "injected unavailable launch"
        unit = next(arg.split("=", 1)[1] for arg in argv if arg.startswith("--unit="))
        row = next(row for row in host.store.snapshot().values() if row["supervisor"]["unit"] == unit)
        assert row["submission_observation"] == "UNKNOWN"
        assert row["host"]["inputs"] is not None
        boundary.launches.append(argv)
        boundary.units[unit] = {"running": not boundary.completed}
        control = Path(row["workspace_reference"]) / ".dsh-adapter"
        events = [dict(type="session", sessionId=SESSION, cwd="/workspace")]
        if boundary.completed:
            events += [dict(type="status", phase="turn_start", turn=1),
                       dict(type="status", phase="turn_end", turn=1, reason={"kind": "completed"}),
                       dict(type="final", text="UNTRUSTED WORKER CLAIM: all goals delivered")]
            (control / "terminal.json").write_text(json.dumps(dict(INVOCATION_ID=INV, SERVICE_RESULT="success",
                                                                  EXIT_CODE="exited", EXIT_STATUS="0")))
        (control / "events.ndjson").write_text("".join(json.dumps(v) + "\n" for v in events))
        return subprocess.CompletedProcess(argv, 0, b"", ("invocation ID: " + INV + "\n").encode())
    monkeypatch.setattr(subprocess, "run", launch)
    native.runner._primary_profile_name = "default"
    native.runner._profile_adapters = {}
    native.runner._running, native.runner._draining = True, False
    native.runner._background_tasks = set()
    native.adapter._running = True
    value = SimpleNamespace(home=isolated, native=native, manager=manager, host=host, ctx=host.ctx,
                            configure=configure, runtime=runtime, boundary=boundary, cache=cache,
                            module=host_module, record=record_module, started=started)
    yield value
    native.runner._clear_plugin_message_injector()
    manager.unload()
    native.runner._shutdown_executor(drain_timeout=2)


async def ingress(setup, *, file=False, stamp=True):
    setup.native.runner._gateway_loop = asyncio.get_running_loop()
    setup.native.runner._install_plugin_message_injector()
    _, event = setup.native.make(document=file)
    if file:
        from plugins.platforms.telegram.telegram_file_boundary import stamp_media
        path = setup.cache / "fixture.txt"
        data = b"fixture input\n"
        path.write_bytes(data)
        event.media_urls = [str(path)]
        event.media_types = ["text/plain"]
        if stamp:
            stamp_media(event, event.raw_message, str(path), data)
    assert await setup.native.runner._handle_message(event) == "ordinary-agent"
    assert len(setup.host.admission._read()["receipts"]) == 1
    proof = next(iter(setup.host.admission._read()["receipts"].values()))
    return proof


def invoke(setup, proof, *, call=None, args=None):
    call = CALL if call is None else call
    def bound():
        fields = dict(PLATFORM="telegram", CHAT_ID=proof["message"]["chat_id"], CHAT_TYPE=proof["chat_type"],
                      THREAD_ID=proof["message"]["thread_id"], USER_ID=proof["message"]["user_id"],
                      KEY=proof["session_key"], ID=call["session_id"], MESSAGE_ID=proof["message"]["message_id"],
                      PROFILE=proof["source_profile"])
        for k, v in fields.items():
            ContextVar("HERMES_SESSION_" + k).set(v)
        token = set_hermes_home_override(setup.home)
        try:
            return json.loads(run_tool_execution_middleware("friday_work", args or ARGS,
                lambda supplied: registry.dispatch("friday_work", supplied, scope=setup.manager.scope_key, **call), **call))
        finally:
            reset_hermes_home_override(token)
    return Context().run(bound)


async def settle(setup):
    # A finite test rendezvous with native owned tasks; no production polling.
    for _ in range(100):
        await asyncio.sleep(.01)
        tasks = tuple(setup.native.runner._background_tasks)
        if tasks:
            return await asyncio.wait_for(asyncio.gather(*tasks), 3)
        rows = setup.host.store.snapshot()
        if rows and all(row["host"]["quiescence"] for row in rows.values()):
            return
    raise AssertionError("native scheduling did not start")


async def control(setup, verb, reference="", **event_fields):
    _, event = setup.native.make(text="/friday-" + verb + (" " + reference if reference else ""),
                                 update_id=702, message_id=502, **event_fields)
    answer = await setup.native.runner._handle_message(event)
    return json.loads(answer) if answer is not None else {"accepted": False, "native_refused": True}


@pytest.mark.asyncio
async def test_public_manager_default_no_effects_then_exact_adapter_dispatch(setup):
    proof = await ingress(setup)
    setup.configure(None)
    assert not (await asyncio.to_thread(invoke, setup, proof))["accepted"]
    assert not setup.host.store.snapshot()
    assert not setup.boundary.launches
    setup.configure(setup.runtime)
    result = await asyncio.to_thread(invoke, setup, proof)
    assert result["accepted"] and result["submission"] == "NOT_SUBMITTED"
    await settle(setup)
    row = setup.host.store.snapshot()[result["reference"]]
    assert len(setup.boundary.launches) == 1
    assert row["host"]["binding"]["correlation"] == CALL
    assert row["host"]["binding"]["ingress"] == proof
    assert row["host"]["terminal"]["state"] == "completed"
    assert row["host"]["quiescence"]["kind"] == "native"
    assert row["goal_verification"] == row["delivery"] == "NOT_RUN"
    assert row["native"] == {"invocation_id": INV, "worker_reference": SESSION}
    original = copy.deepcopy(row)
    assert (await asyncio.to_thread(invoke, setup, proof))["execution"] == "completed"
    assert setup.host.store.snapshot()[result["reference"]] == original
    assert len(setup.boundary.launches) == 1
    old_host = setup.host
    setup.manager.discover_and_load(force=True)
    setup.host = registry.get_entry("friday_work", scope=setup.manager.scope_key).handler.__self__
    assert setup.host is not old_host
    assert (await asyncio.to_thread(invoke, setup, proof))["execution"] == "completed"
    assert setup.host.store.snapshot()[result["reference"]] == original
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_native_call_batch_address_and_serialized_capacity(setup):
    proof = await ingress(setup)
    # Keep the public scheduled coroutine pending on this loop while both sync
    # admissions run: the first persisted association already owns capacity.
    first = invoke(setup, proof)
    second_call = {**CALL, "api_request_id": "second-native-request"}
    assert setup.record.association_address(CALL, proof) != setup.record.association_address(second_call, proof)
    second = invoke(setup, proof, call=second_call)
    assert first["accepted"] and not second["accepted"]
    assert len(setup.host.store.snapshot()) == 1
    await settle(setup)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["workspace", "deadline", "owner", "runtime", "unit"])
async def test_model_cannot_supply_host_authority(setup, field):
    proof = await ingress(setup)
    assert not (await asyncio.to_thread(invoke, setup, proof, args={**ARGS, field: "forged"}))["accepted"]
    assert not setup.host.store.snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["a0", "pins", "receipt", "profile", "gateway_optout", "missing_call", "missing_api"])
async def test_unready_or_unproved_runtime_fails_closed(setup, monkeypatch, mutation):
    proof = await ingress(setup)
    args, call = ARGS, CALL
    if mutation == "a0":
        args = {**ARGS, "worker": "a0"}
    elif mutation in {"pins", "receipt"}:
        value = setup.runtime["dsh"]["node"] if mutation == "pins" else setup.runtime["runtime_receipt"]
        Path(value["path"]).write_bytes(b"changed")
    elif mutation == "profile":
        runtime = copy.deepcopy(setup.runtime)
        runtime["runtime_profile"] = "foreign"
        setup.configure(runtime)
    elif mutation == "gateway_optout":
        setup.configure(setup.runtime, allow_gateway_work=False)
    elif mutation == "missing_api":
        monkeypatch.setattr(setup.ctx, "get_command_context", None)
    else:
        call = {**CALL, "turn_id": None}
    result = await asyncio.to_thread(invoke, setup, proof, args=args, call=call)
    assert not result["accepted"]
    assert not setup.boundary.launches


@pytest.mark.asyncio
async def test_pending_cancel_survives_restart_without_prepare_or_budget_reset(setup):
    proof = await ingress(setup)
    result = invoke(setup, proof)
    row = setup.host.store.snapshot()[result["reference"]]
    # Direct native producer scope while the scheduler is still pending.
    receipt = {"command": "friday-stop", "session_key": proof["session_key"], "admitted_ingress": proof,
               "source": {"platform": "telegram", "profile": "default", "user_id": "111", "chat_id": "-100123", "thread_id": "17"}}
    with _command_context(setup.ctx, receipt):
        stopped = json.loads(setup.host.control("friday-stop", result["reference"]))
    assert stopped["execution"] == "stopped" and stopped["quiescent"]
    await settle(setup)
    reopened = setup.module.WorkerHost(setup.ctx, type(setup.host.admission)(
        PluginState(setup.ctx.plugin_id, setup.ctx.manifest.skill_namespace)))
    recovered = reopened._reconcile(row)
    assert recovered["stop_intent"] == "cancel" and not recovered["preparation_reserved"]
    assert recovered["deadline_unix"] == row["deadline_unix"]
    assert not setup.boundary.launches


@pytest.mark.asyncio
@pytest.mark.parametrize("busy", [False, True])
async def test_actual_idle_control_ownership_original_route_and_native_stop(setup, monkeypatch, busy):
    proof = await ingress(setup)
    setup.boundary.completed = False
    result = await asyncio.to_thread(invoke, setup, proof)
    assert await asyncio.to_thread(setup.started.wait, 3)
    row = setup.host.store.snapshot()[result["reference"]]
    assert row["native"]
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "111,222")
    if busy:
        setup.native.runner._session_state(proof["session_key"]).turn.agent = object()
    for foreign in ({"thread_id": 99}, {"sender_id": 222}):
        response = await control(setup, "stop", result["reference"], **foreign)
        assert not response["accepted"]
        assert setup.host.store.snapshot()[result["reference"]]["stop_intent"] is None
    assert (await control(setup, "status", result["reference"]))["submission"] == "OBSERVED"
    assert (await control(setup, "pause", result["reference"]))["stop_intent"] == "pause"
    assert (await control(setup, "stop", result["reference"]))["stop_intent"] == "cancel"
    await settle(setup)
    row = setup.host.store.snapshot()[result["reference"]]
    assert row["owner"]["message_id"] == proof["message"]["message_id"]
    assert row["host"]["binding"]["ingress"] == proof
    assert setup.boundary.stops


@pytest.mark.asyncio
async def test_restart_status_never_prepares_or_launches_and_expired_pending_stops(setup):
    proof = await ingress(setup)
    # Scheduler rejection deliberately leaves a durable unstarted reservation.
    setup.native.runner._draining = True
    result = await asyncio.to_thread(invoke, setup, proof)
    assert not result["accepted"]
    row = setup.host.store.snapshot()[result["reference"]]
    reopened = setup.module.WorkerHost(setup.ctx, type(setup.host.admission)(
        PluginState(setup.ctx.plugin_id, setup.ctx.manifest.skill_namespace)))
    assert reopened._reconcile(row)["submission_observation"] == "NOT_SUBMITTED"
    reopened.store.clock = lambda: row["deadline_unix"] + 1
    assert reopened._reconcile(row)["stop_intent"] == "cancel"
    assert not setup.boundary.launches
    assert not (Path(row["workspace_reference"]) / ".dsh-adapter").exists()


@pytest.mark.asyncio
async def test_lost_preparation_corruption_and_unknown_hold_capacity_no_replay(setup):
    proof = await ingress(setup)
    setup.native.runner._draining = True
    result = await asyncio.to_thread(invoke, setup, proof)
    row = setup.host.store.snapshot()[result["reference"]]
    controller = setup.host._controller(row)
    brief = sys.modules[type(controller).__module__].parse_brief(ARGS)
    controller.prepare(row["existing_task_id"], row["owner"], brief, ())
    setup.host.store.begin_submission(row["existing_task_id"], row["owner"])
    setup.ctx.state.set("worker_preparation.v1", {"schema_version": 1, "jobs": {}})
    with pytest.raises(RuntimeError):
        setup.host._reconcile(row)
    retained = setup.host.store.snapshot()[result["reference"]]
    assert retained["submission_observation"] == "UNKNOWN" and retained["host"]["quiescence"] is None
    assert not invoke(setup, proof, call={**CALL, "tool_call_id": "another"})["accepted"]
    assert not setup.boundary.launches
    document = setup.ctx.state.get("associations.v1")
    document["jobs"][result["reference"]]["host"]["binding"]["correlation"]["turn_id"] = "corrupt"
    setup.ctx.state.set("associations.v1", document)
    assert not invoke(setup, proof)["accepted"]


@pytest.mark.asyncio
async def test_worker_text_cannot_change_frozen_terminal_or_claim_delivery(setup):
    proof = await ingress(setup)
    result = await asyncio.to_thread(invoke, setup, proof)
    await settle(setup)
    row = setup.host.store.snapshot()[result["reference"]]
    terminal = row["host"]["terminal"]
    (Path(row["workspace_reference"]) / ".dsh-adapter/events.ndjson").write_bytes(b"worker changed later")
    recovered = setup.host._reconcile(row)
    assert recovered["host"]["terminal"] == terminal
    assert recovered["goal_verification"] == recovered["delivery"] == "NOT_RUN"


@pytest.mark.asyncio
@pytest.mark.parametrize("off_loop", [False, True])
async def test_unload_stops_owned_worker_with_native_quiescence(setup, off_loop):
    proof = await ingress(setup)
    setup.boundary.completed = False
    result = await asyncio.to_thread(invoke, setup, proof)
    assert await asyncio.to_thread(setup.started.wait, 3)
    row = setup.host.store.snapshot()[result["reference"]]
    assert row["native"]
    tasks = tuple(setup.native.runner._background_tasks)
    if off_loop:
        await asyncio.to_thread(setup.manager.unload)
    else:
        setup.manager.unload()
        if setup.host._cleanup_future is not None:
            await asyncio.wait_for(asyncio.shield(setup.host._cleanup_future), 3)
    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 3)
    row = setup.host.store.snapshot()[result["reference"]]
    assert row["stop_intent"] == "cancel"
    assert row["host"]["quiescence"] is not None
    assert all(not v["running"] for v in setup.boundary.units.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "unstamped", "changed", "missing"])
async def test_received_bytes_staged_and_copied_by_exact_adapter_or_refused(setup, failure):
    proof = await ingress(setup, file=True, stamp=failure != "unstamped")
    path = setup.cache / "fixture.txt"
    if failure == "changed":
        path.write_bytes(b"different bytes")
    elif failure == "missing":
        path.unlink()
    result = await asyncio.to_thread(invoke, setup, proof)
    if failure:
        assert not result["accepted"]
        assert not setup.boundary.launches
        return
    assert result["accepted"]
    await settle(setup)
    row = setup.host.store.snapshot()[result["reference"]]
    mapping, = row["host"]["inputs"]
    assert Path(mapping["host_path"]).read_bytes() == b"fixture input\n"
    assert (Path(row["workspace_reference"]) / "inputs/verified" / Path(mapping["worker_path"]).name).read_bytes() == b"fixture input\n"
    assert mapping["sha256"] == hashlib.sha256(b"fixture input\n").hexdigest()
    assert row["host"]["binding"]["ingress"]["message"]["media"][0]["content"]["sha256"] == mapping["sha256"]


@pytest.mark.asyncio
async def test_retained_deadline_stops_running_worker_without_new_grant(setup):
    proof = await ingress(setup)
    setup.boundary.completed = False
    result = await asyncio.to_thread(invoke, setup, proof)
    assert await asyncio.to_thread(setup.started.wait, 3)
    row = setup.host.store.snapshot()[result["reference"]]
    setup.host.store.clock = lambda: row["deadline_unix"] + 1
    outcome = await control(setup, "status", result["reference"])
    assert outcome["execution"] == "stopped" and outcome["quiescent"]
    assert outcome["deadline_unix"] == row["deadline_unix"]
    await settle(setup)
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_missing_scoped_key_never_borrows_ambient_process_key(setup):
    proof = await ingress(setup)
    (setup.home / ".env").unlink()
    result = await asyncio.to_thread(invoke, setup, proof)
    assert result["accepted"]
    assert await asyncio.to_thread(setup.started.wait, 3)
    tasks = tuple(setup.native.runner._background_tasks)
    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 3)
    assert not setup.boundary.launches
    row = setup.host.store.snapshot()[result["reference"]]
    assert row["submission_observation"] == "UNKNOWN"
    assert row["host"]["quiescence"] is None


@pytest.mark.asyncio
async def test_factory_refuses_foreign_or_missing_secret_scope_even_with_ambient_key(setup):
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    proof = await ingress(setup)
    setup.native.runner._draining = True
    result = await asyncio.to_thread(invoke, setup, proof)
    row = setup.host.store.snapshot()[result["reference"]]
    factory = setup.host._controller(row).bindings["dsh"].adapter.config.environment
    for mapping, home in ((None, None), ({}, str(setup.home)),
                          ({"OFFLINE_DSH_KEY": "foreign"}, str(setup.home / "foreign"))):
        token = set_secret_scope(mapping, profile_home=home)
        try:
            with pytest.raises(RuntimeError, match="runtime_key_unavailable"):
                factory()
        finally:
            reset_secret_scope(token)
    token = set_secret_scope({"OFFLINE_DSH_KEY": "own-profile-value"}, profile_home=str(setup.home))
    try:
        assert factory() == {"OFFLINE_DSH_KEY": "own-profile-value"}
    finally:
        reset_secret_scope(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["absent", "bot", "transport", "profile"])
async def test_control_needs_fresh_native_proof_and_original_principal(setup, foreign):
    proof = await ingress(setup)
    result = invoke(setup, proof)
    before = setup.host.store.snapshot()[result["reference"]]
    receipt = {"command": "friday-stop", "session_key": proof["session_key"], "admitted_ingress": copy.deepcopy(proof),
               "source": {"platform": "telegram", "profile": "default", "user_id": "111", "chat_id": "-100123", "thread_id": "17"}}
    if foreign == "bot":
        receipt["admitted_ingress"]["message"]["bot_id"] = "another-bot"
    elif foreign == "transport":
        receipt["admitted_ingress"]["transport_profile"] = "another-profile"
    elif foreign == "profile":
        receipt["source"]["profile"] = receipt["admitted_ingress"]["runtime_profile"] = "another-profile"
    if foreign == "absent":
        answer = setup.host.control("friday-stop", result["reference"])
    else:
        with _command_context(setup.ctx, receipt):
            answer = setup.host.control("friday-stop", result["reference"])
    assert not json.loads(answer)["accepted"]
    assert setup.host.store.snapshot()[result["reference"]] == before
    await settle(setup)


# Regression controls for recovered cleanup and same-owner metadata contention.
def _pending_running(setup, proof):
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    setup.native.runner._draining = True
    answer = invoke(setup, proof)
    assert not answer["accepted"] and answer.get("reference")
    row = setup.host.store.snapshot()[answer["reference"]]
    setup.boundary.completed = False
    token = set_secret_scope({"OFFLINE_DSH_KEY": "offline-profile-value"}, profile_home=str(setup.home))
    try:
        return setup.host._start(row)
    finally:
        reset_secret_scope(token)


def _control_receipt(proof, command):
    return dict(command=command, session_key=proof["session_key"], admitted_ingress=proof,
                source=dict(platform="telegram", profile="default", user_id="111", chat_id="-100123", thread_id="17"))


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("storage", ["outcome", "read"])
async def test_recovered_status_storage_failure_attempts_exact_cleanup(setup, monkeypatch, cleanup_fails, storage):
    proof = await ingress(setup)
    row = _pending_running(setup, proof)
    recovered = setup.module.WorkerHost(setup.ctx, setup.host.admission)
    original = OSError("outcome ENOSPC")
    method = "retain_outcome" if storage == "outcome" else "get"
    retain, stop = getattr(recovered.store, method), setup.module.NativeSupervisor.stop
    seen = []
    def emergency(self, checked):
        seen.append(copy.deepcopy(checked))
        if cleanup_fails:
            raise RuntimeError("offline stop failure")
        return stop(self, checked)
    monkeypatch.setattr(recovered.store, method, lambda *a, **kw: (_ for _ in ()).throw(original))
    monkeypatch.setattr(setup.module.NativeSupervisor, "stop", emergency)
    try:
        with _command_context(setup.ctx, _control_receipt(proof, "friday-status")):
            answer = json.loads(recovered.control("friday-status", row["existing_task_id"]))
        assert not answer["accepted"]
        assert len(seen) == 1 and seen[0]["native"] == row["native"]
        assert not setup.native.runner._background_tasks
        assert any(("STOP_UNCONFIRMED" if cleanup_fails else "STOP_CONFIRMED") in note
                   for note in getattr(original, "__notes__", ()))
        if cleanup_fails:
            assert answer["cleanup"] == "STOP_UNCONFIRMED"
        else:
            assert all(not v["running"] for v in setup.boundary.units.values())
        retained = recovered.store.snapshot()[row["existing_task_id"]]
        assert retained["host"]["quiescence"] is None  # Failed commit cannot release capacity.
        assert retained["deadline_unix"] == row["deadline_unix"]
    finally:
        monkeypatch.setattr(recovered.store, method, retain)
        monkeypatch.setattr(setup.module.NativeSupervisor, "stop", stop)
        setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_initiating_storage_exception(setup, monkeypatch):
    row = _pending_running(setup, await ingress(setup))
    original = OSError("retained stop ENOSPC")
    request, stop = setup.host.store.request_stop, setup.module.NativeSupervisor.stop
    monkeypatch.setattr(setup.host.store, "request_stop", lambda *a, **kw: (_ for _ in ()).throw(original))
    monkeypatch.setattr(setup.module.NativeSupervisor, "stop", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline cleanup failure")))
    try:
        with pytest.raises(OSError) as caught:
            setup.host._stop(row, "cancel")
        assert caught.value is original
        assert any("STOP_UNCONFIRMED" in note for note in original.__notes__)
    finally:
        monkeypatch.setattr(setup.host.store, "request_stop", request)
        monkeypatch.setattr(setup.module.NativeSupervisor, "stop", stop)
        setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_unload_serializes_owned_metadata_contention_without_retry(setup, monkeypatch):
    row = _pending_running(setup, await ingress(setup))
    entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
    request = setup.host.store.request_stop
    def held_metadata():
        with setup.host.store._locked():
            entered.set()
            assert release.wait(3), "test must release the owned metadata lock"
    def stop_requested(*args, **kwargs):
        attempted.set()
        return request(*args, **kwargs)
    holder = asyncio.create_task(asyncio.to_thread(held_metadata))
    assert await asyncio.to_thread(entered.wait, 3)
    monkeypatch.setattr(setup.host.store, "request_stop", stop_requested)
    try:
        setup.manager.unload()
        assert await asyncio.to_thread(attempted.wait, 3)
        assert not setup.host._cleanup_future.done()
    finally:
        release.set()
        await holder
    await asyncio.wait_for(asyncio.shield(setup.host._cleanup_future), 3)
    retained = setup.host.store.snapshot()[row["existing_task_id"]]
    assert retained["stop_intent"] == "cancel" and retained["host"]["quiescence"] is not None
    assert all(not v["running"] for v in setup.boundary.units.values())
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_other_store_writer_still_refused_by_nonblocking_flock(setup):
    row = _pending_running(setup, await ingress(setup))
    other = type(setup.host.store)(setup.host.store.state)
    with setup.host.store._locked():
        with pytest.raises(RuntimeError, match="admission_busy"):
            other.get(row["existing_task_id"], row["owner"])
    setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_owned_coroutine_cleanup_failure_preserves_original_exception(setup, monkeypatch):
    proof = await ingress(setup)
    setup.native.runner._draining = True
    answer = invoke(setup, proof)
    row = setup.host.store.snapshot()[answer["reference"]]
    original = OSError("executor storage failure")
    start, stop = setup.host._start, setup.host._stop
    monkeypatch.setattr(setup.host, "_start", lambda *a: (_ for _ in ()).throw(original))
    monkeypatch.setattr(setup.host, "_stop", lambda *a: (_ for _ in ()).throw(RuntimeError("cleanup failure")))
    try:
        with pytest.raises(OSError) as caught:
            await setup.host._run(row)
        assert caught.value is original
        assert any("STOP_UNCONFIRMED" in note for note in original.__notes__)
    finally:
        monkeypatch.setattr(setup.host, "_start", start)
        monkeypatch.setattr(setup.host, "_stop", stop)
        stop(row, "cancel")
