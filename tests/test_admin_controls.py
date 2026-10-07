"""Actual native config/auth/API and loaded host; synthetic transport only."""
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from test_admin_foundation import env, session, mounted_app, ROOT, package
from test_host_native import setup, isolated, native, offline_boundary, ingress, invoke, settle
from friday_admin_controls.admin_settings import local_endpoint


def basic():
    root = Path(__import__("hermes_cli").__path__[-1]).parent
    spec = importlib.util.spec_from_file_location("synthetic_admin_basic", root / "plugins/dashboard_auth/basic/__init__.py")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module.BasicAuthProvider(username="owner", password_hash="unused-synthetic", secret=b"SYNTHETIC-ONLY-shared-signing-key-32")


def local_config(env):
    from tools.configure_local_test import build_config
    config = build_config(base_url="http://127.0.0.1:8001/v1", model="fixture-local", key_env="SYNTHETIC_LOCAL_KEY",
        context=8000, max_input=7000, main_output=512, summary_output=512, margin=128, template_overhead=128,
        web_profile="exa-paid")
    policy = copy.deepcopy(env.cfg["plugins"])
    web_plugins = config.pop("plugins", {})
    policy["enabled"] = list(dict.fromkeys([*policy["enabled"], *web_plugins.get("enabled", [])]))
    policy.setdefault("entries", {}).update(web_plugins.get("entries", {}))
    config["plugins"] = policy
    env.cfg.update(config); env.save()
    return config


def body(env, kind, **values):
    return {"kind": kind, "values": values, "expected_sha256": hashlib.sha256((env.home / "config.yaml").read_bytes()).hexdigest()}


@pytest.mark.parametrize("kind,values,path,expected", [
    ("operational", {"key": "agent.max_turns", "value": 17}, ("agent", "max_turns"), 17),
    ("operational", {"key": "streaming.enabled", "value": True}, ("streaming", "enabled"), True),
    ("web", {"profile": "exa-keyless", "extract_timeout": 8, "extract_char_limit": 7000}, ("web", "extract_timeout"), 8),
    ("toolset", {"name": "terminal", "enabled": True}, ("platform_toolsets", "telegram"), ["web", "terminal"]),
    ("model", {"slot": "main", "provider": "custom:friday-local", "model": "fixture-local", "base_url": "http://127.0.0.1:8001/v1"}, ("model", "default"), "fixture-local"),
    ("model", {"slot": "compression", "provider": "custom:friday-local", "model": "fixture-local", "base_url": "http://127.0.0.1:8001/v1"}, ("auxiliary", "compression", "model"), "fixture-local"),
])
def test_typed_native_write_actual_raw_and_runtime_readers(env, kind, values, path, expected):
    from hermes_cli.config import load_config_readonly, require_readable_config_before_write
    local_config(env)
    raw = require_readable_config_before_write()
    raw["plugins"]["entries"]["friday_rework"]["settings"]["synthetic_secret"] = "PRIVATE-SYNTHETIC-CANARY"
    from hermes_cli.config import atomic_config_write
    atomic_config_write(env.home / "config.yaml", raw)
    answer = env.admin.write_settings("default", body(env, kind, **values), session())
    assert answer["recorded"] and answer["observed_live_reload"] is False
    current = load_config_readonly()
    for key in path: current = current[key]
    assert current == expected
    reread = require_readable_config_before_write()
    assert reread["plugins"] == raw["plugins"]  # original host/runtime remains unchanged
    assert reread["providers"]["friday-local"]["models"] == raw["providers"]["friday-local"]["models"]
    from friday_admin_controls.admin import masked
    assert "PRIVATE-SYNTHETIC-CANARY" not in json.dumps(masked(env.admin.effective("default")))
    if kind == "model":
        from hermes_cli.providers import resolve_custom_provider
        from hermes_cli.config import get_compatible_custom_providers
        provider = resolve_custom_provider("custom:friday-local", get_compatible_custom_providers(reread))
        assert provider and provider.base_url == "http://127.0.0.1:8001/v1"


@pytest.mark.parametrize("value", ["https://api.openai.com/v1", "http://100.100.100.100:80/v1", "http://127.0.0.1:80/v1?key=secret",
    "http://user:secret@127.0.0.1:80/v1", "http://localhost:80/v1", "http://169.254.169.254:80/v1", "http://127.0.0.1:80/v1\n"])
def test_public_or_unproved_model_endpoint_refused(value):
    with pytest.raises((ValueError, TypeError)): local_endpoint(value)


@pytest.mark.parametrize("kind,values", [
    ("operational", {"key": "env.ANY_KEY", "value": "LEAK"}),
    ("operational", {"key": "agent.max_turns", "value": True}),
    ("operational", {"key": "streaming.enabled", "value": "false"}),
    ("web", {"profile": "disabled", "extract_timeout": 30, "extract_char_limit": 15000}),
    ("web", {"profile": "exa-paid", "extract_timeout": 0, "extract_char_limit": 15000}),
    ("toolset", {"name": "web", "enabled": False}),
    ("skill", {"name": "../../FOREIGN", "enabled": True}),
    ("model", {"slot": "main", "provider": "openrouter", "model": "cloud", "base_url": "https://cloud.invalid/v1"}),
    ("model", {"slot": "main", "provider": "custom:friday-local", "model": "unobserved", "base_url": "http://127.0.0.1:8001/v1"}),
])
def test_arbitrary_secret_path_cloud_or_capability_change_refused(env, kind, values):
    local_config(env); before = (env.home / "config.yaml").read_bytes()
    with pytest.raises((ValueError, PermissionError)): env.admin.write_settings("default", body(env, kind, **values), session())
    assert (env.home / "config.yaml").read_bytes() == before


def test_skill_native_toggle_cas_and_managed_leaf_refusal(env):
    from hermes_cli import managed_scope
    from hermes_cli.config import load_config_readonly
    local_config(env)
    skill = env.home / "skills/fixture"; skill.mkdir(parents=True); (skill / "SKILL.md").write_text("synthetic installed skill")
    stale = body(env, "skill", name="fixture", enabled=False)
    env.admin.write_settings("default", stale, session())
    assert load_config_readonly()["skills"]["disabled"] == ["fixture"]
    with pytest.raises(ValueError, match="changed_reload"): env.admin.write_settings("default", stale, session())
    env.admin.write_settings("default", body(env, "skill", name="fixture", enabled=True), session())
    assert load_config_readonly()["skills"]["disabled"] == []
    env.monkeypatch.setattr(managed_scope, "is_key_managed", lambda key: key == "web.extract_timeout")
    before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(PermissionError): env.admin.write_settings("default", body(env, "web", profile="exa-paid", extract_timeout=10, extract_char_limit=5000), session())
    assert (env.home / "config.yaml").read_bytes() == before


def test_enabled_cloud_fallback_config_is_not_written(env):
    local_config(env)
    env.cfg["auxiliary"]["compression"]["provider"] = "openrouter"; env.save()
    before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(ValueError, match="explicit_local"):
        env.admin.write_settings("default", body(env, "operational", key="agent.max_turns", value=20), session())
    assert (env.home / "config.yaml").read_bytes() == before


def test_private_config_symlink_or_permissions_refused(env):
    local_config(env); path = env.home / "config.yaml"
    path.chmod(0o644)
    with pytest.raises(PermissionError): env.admin.write_settings("default", body(env, "operational", key="agent.max_turns", value=20), session())
    path.chmod(0o600)
    alternate = env.home / "config-copy.yaml"; alternate.write_bytes(path.read_bytes()); alternate.chmod(0o600)
    path.unlink(); path.symlink_to(alternate)
    with pytest.raises(PermissionError): env.admin.write_settings("default", body(env, "operational", key="agent.max_turns", value=20), session())


def test_native_remote_context_refuses_owning_gateway_callback():
    from hermes_cli.plugin_host_child import RemotePluginContext
    from hermes_cli.plugin_host_wire import PluginHostUnsupported
    remote = object.__new__(RemotePluginContext)
    with pytest.raises(PluginHostUnsupported, match="cannot run in the plugin host"):
        remote.register_gateway_control("not-admitted", lambda raw: {})


@pytest.mark.parametrize("who", [session(uid="ordinary"), session(org_id="foreign"), session(expires_at=1), None])
def test_foreign_ordinary_expired_operator_cannot_write(env, who):
    local_config(env); before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(PermissionError): env.admin.write_settings("default", body(env, "operational", key="agent.max_turns", value=12), who)
    assert (env.home / "config.yaml").read_bytes() == before


def test_native_signed_auth_actual_asgi_settings_and_task_unknown(env):
    from hermes_cli.dashboard_auth import middleware, request_utils
    provider = basic(); local_config(env)
    env.monkeypatch.setattr(middleware, "list_session_providers", lambda: [provider])
    env.monkeypatch.setattr(request_utils, "list_session_providers", lambda: [provider])
    app = mounted_app(env)
    @app.middleware("http")
    async def gate(request, next_call): return await middleware.gated_auth_middleware(request, next_call)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline.invalid") as client:
            root = "/api/plugins/friday_rework"
            owner = {"Authorization": "Bearer " + provider._mint_session("owner").access_token}
            ordinary = {"Authorization": "Bearer " + provider._mint_session("ordinary").access_token}
            b = body(env, "operational", key="agent.max_turns", value=15)
            assert (await client.put(root + "/settings?profile=default", json=b, headers=ordinary)).status_code == 403
            assert (await client.put(root + "/settings?profile=foreign", json=b, headers=owner)).status_code == 403
            result = await client.put(root + "/settings?profile=default", json=b, headers=owner)
            assert result.status_code == 200 and result.json()["recorded"]
            current = await client.get(root + "/effective?profile=default", headers=owner)
            assert current.json()["settings"]["model"]["base_url"] == "http://127.0.0.1:8001/v1"
            unavailable = await client.post(root + "/tasks/native-" + "a" * 64 + "/control?profile=default", json={"action": "cancel"}, headers=owner)
            assert unavailable.status_code == 200 and unavailable.json()["execution"] == "UNKNOWN"
            assert "access_token" not in unavailable.text
            assert (await client.post(root + "/tasks/native-" + "a" * 64 + "/control?profile=default", json={"action": "cancel", "owner": "forged"}, headers=owner)).status_code == 422
    asyncio.run(scenario())


def test_native_schedule_pause_resume_retains_job_original_scope(env):
    from cron.jobs import create_job, get_job
    job = create_job(prompt="Synthetic not executed", schedule="every 1h", name="admin-fixture", paused=True)
    original = get_job(job["id"])
    assert env.admin.schedules("default", "resume", job["id"], session())["recorded"]
    assert get_job(job["id"])["enabled"]
    assert env.admin.schedules("default", "pause", job["id"], session())["recorded"]
    assert get_job(job["id"])["enabled"] is False
    assert get_job(job["id"])["prompt"] == original["prompt"]
    with pytest.raises(ValueError): env.admin.schedules("default", "resume", "admin-fixture", session())
    with pytest.raises(PermissionError): env.admin.schedules("default", "resume", job["id"], session("ordinary"))


@pytest.mark.parametrize("action,kind,fields,expected", [
    ("cancel_task", "", {}, {"action": "cancel"}),
    ("pause_task", "", {}, {"action": "pause"}),
    ("check_task", "", {}, {"action": "status"}),
    ("settings", "operational", {"value": "19"}, {"key": "agent.max_turns", "value": 19}),
    ("settings", "web", {"web": "exa-keyless", "timeout": "7", "chars": "9000"}, {"profile": "exa-keyless", "extract_timeout": 7, "extract_char_limit": 9000}),
    ("settings", "model", {}, {"slot": "main", "provider": "custom:friday-local", "model": "fixture-local", "base_url": "http://127.0.0.1:8001/v1"}),
    ("schedule", "", {}, {"action": "pause"}),
])
def test_shipped_ui_actual_native_sdk_generates_real_api_contract(env, action, kind, fields, expected):
    import subprocess
    from friday_admin_controls.admin import masked
    local_config(env)
    root = Path(__import__("hermes_cli").__path__[-1]).parent
    payload = {"action": action, "kind": kind, "fields": fields, "token": "SYNTHETIC-SDK-TOKEN",
        "tasks": [{"existing_task_id": "native-" + "a" * 64, "quiescent": False}],
        "effective": masked(env.admin.effective("default")), "schedules": [{"id": "fixture-job", "enabled": True}],
        "control": {"accepted": False, "execution": "UNKNOWN"}}
    out = subprocess.run(["/home/jericho/.local/bin/node", "--disable-wasm-trap-handler", "--max-old-space-size=256",
        str(ROOT.parents[1] / "tests/admin_ui_controls.cjs"), str(ROOT / "dashboard/index.js"),
        str(root / "web/src/lib/api.ts")], input=json.dumps(payload), text=True, capture_output=True, timeout=20)
    assert out.returncode == 0, out.stderr
    requests = json.loads(out.stdout)["requests"]
    writes = [r for r in requests if r["method"] in ("POST", "PUT")]
    assert len(writes) == 1  # no automatic retry on UNKNOWN
    write = writes[0]; values = json.loads(write["body"])
    assert values == expected if kind == "" else values["values"] == expected
    assert "profile=default" in write["url"]
    assert write["headers"]["content-type"] == "application/json"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "cancel"])
@pytest.mark.parametrize("api_boundary", [False, True])
@pytest.mark.parametrize("metadata_failure", [False, True])
async def test_actual_native_gateway_verb_existing_host_controller_stop(setup, action, api_boundary, metadata_failure, monkeypatch):
    from hermes_cli.dashboard_auth.registry import register_provider, restore_registration
    from hermes_cli.config import require_readable_config_before_write, atomic_config_write
    from hermes_cli.plugins_gateway_control import plugin_control_verb
    from gateway.control_socket import GatewayControlServer
    cfg = require_readable_config_before_write()
    cfg["plugins"]["entries"]["friday_rework"]["settings"]["admin"] = {"enabled": True,
        "operators": [{"provider": "basic", "user_id": "owner", "org_id": ""}], "profiles": ["default"]}
    atomic_config_write(setup.ctx.state.data_dir.parents[1] / "config.yaml", cfg)
    provider = basic(); register_provider(provider, scope=str(setup.home))
    try:
        setup.boundary.completed = False
        proof = await ingress(setup)
        submitted = await asyncio.to_thread(invoke, setup, proof)
        assert await asyncio.to_thread(setup.started.wait, 3)
        ref = submitted["reference"]; row = setup.host.store.snapshot()[ref]
        original = copy.deepcopy(row)
        assert "friday-admin-control" not in setup.manager._plugin_commands
        assert "friday_rework:friday-admin-control" in setup.manager._gateway_verb_handlers
        runner = SimpleNamespace(served_profile_names=lambda: ["default"])
        server = GatewayControlServer(verb_handlers={"plugin-control": plugin_control_verb(runner, asyncio.get_running_loop())})
        async def control(token, selected=action, profile="default"):
            raw = json.dumps({"verb": "plugin-control", "params": {"profile": profile, "plugin": "friday_rework", "control": "friday-admin-control",
                "arguments": {"provider": "basic", "access_token": token, "task_id": ref, "action": selected}}}).encode()
            return json.loads(await asyncio.to_thread(server.handle_request_line, raw))["result"]
        ordinary = await control(provider._mint_session("ordinary").access_token)
        assert not ordinary["accepted"] and not setup.boundary.stops
        assert not (await control("expired-invalid-synthetic"))["accepted"]
        assert not (await control(provider._mint_session("owner").access_token, profile="foreign"))["accepted"]
        denied = cfg["plugins"]["entries"]["friday_rework"]
        denied["allow_gateway_control"] = False
        atomic_config_write(setup.home / "config.yaml", cfg)
        assert not (await control(provider._mint_session("owner").access_token))["accepted"]
        assert not setup.boundary.stops
        denied["allow_gateway_control"] = True
        atomic_config_write(setup.home / "config.yaml", cfg)
        if metadata_failure:
            snapshot = setup.host.store.snapshot
            monkeypatch.setattr(setup.host.store, "snapshot", lambda: (_ for _ in ()).throw(OSError("SYNTHETIC_METADATA_UNAVAILABLE")))
            unknown = await control(provider._mint_session("owner").access_token)
            assert unknown["accepted"] is False and unknown["execution"] == "UNKNOWN"
            assert setup.boundary.stops  # exact owned native boundary, no false terminal row
            assert len(setup.boundary.launches) == 1
            monkeypatch.setattr(setup.host.store, "snapshot", snapshot)
            await settle(setup)
            return
        if api_boundary:
            from hermes_cli.dashboard_auth import middleware, request_utils
            from gateway import control_socket
            import stat, os
            monkeypatch.setattr(middleware, "list_session_providers", lambda: [provider])
            monkeypatch.setattr(request_utils, "list_session_providers", lambda: [provider])
            app = mounted_app(SimpleNamespace(monkeypatch=monkeypatch))
            @app.middleware("http")
            async def gate(request, next_call): return await middleware.gated_auth_middleware(request, next_call)
            # Only the socket byte transport/ACL observation is synthetic. The
            # actual ASGI/native auth, native protocol, loop, loaded host and
            # original controller all execute on this exact source composition.
            endpoint = SimpleNamespace(lstat=lambda: SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.getuid()))
            monkeypatch.setattr(control_socket, "resolve_client_socket_path", lambda home: endpoint)
            calls = []
            def query(home, verb, *, params, timeout):
                calls.append({"verb": verb, "task_id": params["arguments"]["task_id"], "action": params["arguments"]["action"]})
                result = json.loads(server.handle_request_line(json.dumps({"verb": verb, "params": params}).encode()))["result"]
                return result if action == "pause" else None  # observed stop, lost IPC response
            monkeypatch.setattr(control_socket, "query_gateway_control", query)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline.invalid") as client:
                answer = await client.post("/api/plugins/friday_rework/tasks/" + ref + "/control?profile=default",
                    json={"action": action}, headers={"Authorization": "Bearer " + provider._mint_session("owner").access_token})
            assert answer.status_code == 200
            stopped = answer.json()
            assert len(calls) == 1
            if action == "cancel":
                assert stopped == {"accepted": False, "execution": "UNKNOWN", "error": "owning_control_response_lost"}
                stopped = setup.module.status(setup.host.store.snapshot()[ref])  # independent retained observation only
        else:
            stopped = await control(provider._mint_session("owner").access_token)
        assert stopped["accepted"] and stopped["quiescent"] and stopped["stop_intent"] == action
        retained = setup.host.store.snapshot()[ref]
        assert retained["deadline_unix"] == original["deadline_unix"] and retained["budget_seconds"] == original["budget_seconds"]
        assert retained["owner"] == original["owner"] and retained["native"] == original["native"]
        assert retained["host"]["binding"]["ingress"] == original["host"]["binding"]["ingress"]
        count = len(setup.boundary.launches)
        again = await control(provider._mint_session("owner").access_token, "status")
        assert again["stop_intent"] == action and len(setup.boundary.launches) == count
        await settle(setup)
        assert provider._mint_session("owner").access_token not in json.dumps(setup.host.store.snapshot())
        assert setup.manager.unload("friday_rework")
        assert "friday_rework:friday-admin-control" not in setup.manager._gateway_verb_handlers
        unavailable = await control(provider._mint_session("owner").access_token)
        assert unavailable["accepted"] is False and unavailable["error"] == "owning_host_not_loaded"
    finally:
        restore_registration("basic", provider, None, scope=str(__import__("hermes_constants").get_hermes_home()))
