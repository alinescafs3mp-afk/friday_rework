"""Real native stores and supported dashboard mount; synthetic identities only.

No model, daemon, HTTP socket, real credentials or live product acceptance.
"""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace, ModuleType

import httpx
import pytest
from fastapi import FastAPI
from hermes_cli.friday_product_access import (
    KEY, access_policy, admin_policy, gateway_allowed, operator_allowed,
    principal_id, request_allowed, session_allowed, validate_access,
)
from hermes_cli.plugins_state import PluginState
from hermes_cli.dashboard_auth.base import Session
from hermes_constants import set_hermes_home_override, reset_hermes_home_override

ROOT = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_admin_controls", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec); sys.modules[spec.name] = package; spec.loader.exec_module(package)
from friday_admin_controls.admin import Administration, masked
from friday_admin_controls.access import ProductAccess
from friday_admin_controls.associations import Associations, AssociationError
from friday_admin_controls.artifacts import ArtifactError
from friday_admin_controls.boundary import WorkBrief


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir(mode=0o700)
    satellite = home / "profiles/satellite"; satellite.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("HERMES_HOME", str(home))
    import hermes_constants
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(home))
    # Empty synthetic env; no real profile/environment is inherited by an auth test.
    for key in ("GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS", "TELEGRAM_ALLOWED_USERS",
                "TELEGRAM_ALLOW_ALL_USERS", "TELEGRAM_GROUP_ALLOWED_CHATS", "TELEGRAM_GROUP_ALLOWED_USERS"):
        monkeypatch.delenv(key, raising=False)
    policy = {"product_access": {"enabled": True, "accounts": [{"platform": "telegram", "transport_profile": "default",
        "account_id": "bot-A", "runtime_profiles": ["default", "satellite"]}, {"platform": "discord", "transport_profile": "default",
        "account_id": "bot-B", "runtime_profiles": ["default"]}]},
        "admin": {"enabled": True, "operators": [{"provider": "basic", "user_id": "owner", "org_id": ""}],
                  "profiles": ["default", "satellite"]}}
    cfg = {"plugins": {"enabled": ["friday_rework"], "entries": {"friday_rework": {"settings": policy}}}}
    def save(value=cfg, where=home):
        (where / "config.yaml").write_text(json.dumps(value)); (where / "config.yaml").chmod(0o600)
    save(); save(where=satellite)
    token = set_hermes_home_override(str(home))
    try:
        yield SimpleNamespace(home=home, satellite=satellite, cfg=cfg, save=save, monkeypatch=monkeypatch,
            state=PluginState("friday_rework"), admin=Administration())
    finally:
        reset_hermes_home_override(token)


def user(env, uid="1", enabled=True, role="user", **delta):
    return ProductAccess(env.state).set_user(**(dict(platform="telegram", transport_profile="default", account_id="bot-A",
        user_id=uid, enabled=enabled, role=role) | delta))


def source(env, uid="1", **kwargs):
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity
    value = SessionSource(Platform.TELEGRAM, "chat", user_id=uid, **kwargs)
    value._identity = RoutingIdentity("default", value.profile or "default", env.home, env.home, multiplexed=False)
    return value


def gateway(env):
    from gateway.authz_mixin import GatewayAuthorizationMixin
    from gateway.pairing import PairingStore
    value = GatewayAuthorizationMixin()
    value.pairing_store = PairingStore()
    return value


def session(uid="owner", **changes):
    return Session(**(dict(user_id=uid, email="", display_name="same name", org_id="", provider="basic",
        expires_at=int(time.time()) + 600, access_token="synthetic-only", refresh_token="") | changes))


def request(session_value, path="/api/plugins/friday_rework/users", profile="default", gated=True):
    from starlette.requests import Request
    app = FastAPI(); app.state.auth_required = gated
    result = Request(dict(type="http", method="GET", path=path, root_path="", query_string=("profile=" + profile).encode(),
        headers=[], app=app, scheme="http", server=("test", 80), client=("test", 1)))
    result.state.session = session_value
    return result


def test_native_wildcard_disable_reload_and_enable(env):
    env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*")
    g = gateway(env); one, two = source(env, "1"), source(env, "2")
    user(env, "1"); user(env, "2")
    assert g._is_user_authorized(one) and g._is_user_authorized(two)
    user(env, "1", enabled=False)
    assert not g._is_user_authorized(one) and g._is_user_authorized(two)
    # Newly constructed reader/gateway observes disk rather than old cached metadata.
    assert not gateway(env)._is_user_authorized(one)
    user(env, "1", enabled=True)
    assert gateway(env)._is_user_authorized(one)


@pytest.mark.parametrize("grant", ["pairing", "global_all", "platform_all", "role", "group", "relay"])
def test_native_grant_cannot_override_disabled_product_user(env, grant):
    g = gateway(env); value = source(env)
    if grant == "pairing":
        g.pairing_store._approve_user("telegram", "1")
    elif grant == "global_all":
        env.monkeypatch.setenv("GATEWAY_ALLOW_ALL_USERS", "1")
    elif grant == "platform_all":
        env.monkeypatch.setenv("TELEGRAM_ALLOW_ALL_USERS", "1")
    elif grant == "role":
        value.role_authorized = True
    elif grant == "group":
        value.chat_type = "group"; env.monkeypatch.setenv("TELEGRAM_GROUP_ALLOWED_CHATS", "chat")
    else:
        value.delivered_via_upstream_relay = True
    user(env); assert g._principal_authorized(value, allow_adapter_delegation=True)
    user(env, enabled=False)
    assert not g._principal_authorized(value, allow_adapter_delegation=True)


def test_product_enable_still_requires_native_grant(env):
    user(env)
    assert not gateway(env)._principal_authorized(source(env), allow_adapter_delegation=True)


def test_non_friday_gateway_keeps_native_wildcard_behavior(env):
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"] = {}; env.save()
    env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*")
    assert gateway(env)._is_user_authorized(source(env, "not-product-user"))


def test_routed_runtime_cannot_override_transport_disable(env):
    env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*")
    user(env, enabled=False)
    with pytest.raises(PermissionError, match="receiving_transport_authority"):
        env.admin.set_user("satellite", platform="telegram", transport_profile="default", account_id="bot-A", user_id="1", enabled=True, role="user")
    value = source(env, profile="satellite")
    token = set_hermes_home_override(str(env.satellite))
    try:
        assert not gateway(env)._is_user_authorized(value)
    finally: reset_hermes_home_override(token)


@pytest.mark.parametrize("key", ["admin", "product_access"])
@pytest.mark.parametrize("bad", [0, 0.0, 1, "true", None])
def test_policy_enabled_boolean_aliases_do_not_disable_protection(env, key, bad):
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"][key] = {"enabled": bad}
    env.save()
    with pytest.raises(ValueError):
        (admin_policy if key == "admin" else access_policy)()


@pytest.mark.parametrize("change", ["corrupt_config", "corrupt_state", "lost_state", "unknown_account", "foreign_runtime", "missing_user"])
def test_product_admission_fails_closed(env, change):
    env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*"); user(env)
    value = source(env)
    if change == "corrupt_config": (env.home / "config.yaml").write_text("[malformed")
    elif change == "corrupt_state": env.state.path.write_text("not-json")
    elif change == "lost_state": env.state.path.unlink()
    elif change == "unknown_account": value.platform = __import__("gateway.config", fromlist=["Platform"]).Platform.SLACK
    elif change == "foreign_runtime":
        from gateway.session_identity import RoutingIdentity
        value._identity = RoutingIdentity("default", "foreign", env.home, env.home)
    else: value.user_id = "unknown"
    assert not gateway(env)._principal_authorized(value, allow_adapter_delegation=True)


def test_equal_ids_names_and_platforms_never_merge(env):
    a = user(env)
    b = user(env, platform="discord", account_id="bot-B")
    assert a["principal_id"] != b["principal_id"]
    assert len(ProductAccess(env.state).users()) == 2
    with pytest.raises(ValueError): user(env, account_id="other-bot")


@pytest.mark.parametrize("delta", [{"enabled": 1}, {"role": "superuser"}, {"user_id": ""}, {"transport_profile": "../default"}])
def test_invalid_user_metadata_cannot_write(env, delta):
    with pytest.raises(ValueError): user(env, **delta)
    assert ProductAccess(env.state).users() == {}


def test_native_atomic_write_failure_preserves_disabled_state(env):
    user(env, enabled=False)
    import utils
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(utils, "atomic_json_write", lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic disk failure")))
        with pytest.raises(OSError): user(env, enabled=True)
    assert ProductAccess(PluginState("friday_rework")).users()[principal_id("telegram", "default", "bot-A", "1")]["enabled"] is False


def test_directory_barrier_failure_does_not_report_effective_success(env):
    import friday_admin_controls.access as access
    user(env, enabled=False)
    env.monkeypatch.setattr(access, "_sync_directory", lambda _: (_ for _ in ()).throw(OSError("synthetic fsync failure")))
    with pytest.raises(OSError): user(env, enabled=True)
    # It may already have committed: retained UNKNOWN, not rolled back or retried.
    assert ProductAccess(env.state).users()[principal_id("telegram", "default", "bot-A", "1")]["enabled"] is True


@pytest.mark.parametrize("identity", [None, "plain-object", session("ordinary"), session("owner", provider="foreign"),
    session("owner", org_id="foreign"), session("owner", expires_at=1)])
def test_admin_direct_route_identity_refusals(env, identity):
    import importlib.util
    s = importlib.util.spec_from_file_location("admin_api_test", ROOT / "dashboard/api.py")
    m = importlib.util.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e: m.require_admin(request(identity))
    assert e.value.status_code == 403


def test_native_operator_and_product_profile_scope(env):
    assert session_allowed(session()) and request_allowed(request(session()))
    assert not request_allowed(request(session(), profile="foreign"))
    assert not request_allowed(request(session(), gated=False))
    assert not request_allowed(request(session(), path="/api/env/reveal"))
    with pytest.raises(PermissionError): env.admin.users("foreign")
    with pytest.raises(ValueError): env.admin.users("../default")


def test_target_profile_cannot_replace_launch_auth_policy(env):
    altered = copy.deepcopy(env.cfg)
    altered["plugins"]["entries"]["friday_rework"]["settings"]["admin"]["operators"][0]["user_id"] = "ordinary"
    env.save(altered, env.satellite)
    token = set_hermes_home_override(str(env.satellite))
    try:
        assert session_allowed(session()) and not session_allowed(session("ordinary"))
    finally: reset_hermes_home_override(token)
    with pytest.raises(PermissionError, match="receiving_transport_authority"):
        env.admin.users("satellite")
    assert env.admin.effective("satellite")["profile"] == "satellite"


def native_sessions(env):
    from hermes_state import SessionDB
    db = SessionDB(env.home / "state.db")
    for uid, topic in [("1", "topic-A"), ("2", "topic-B")]:
        from gateway.session_recovery import SessionRecoveryMixin
        value = source(env, uid); value.chat_id = "shared-chat"; value.thread_id = topic
        db.create_session(**SessionRecoveryMixin._session_create_kwargs(session_id="session-" + uid,
            session_key="key-" + uid, origin=value, source_value="telegram", display_name=None, parent_session_id=None))
        db.append_message("session-" + uid, "user", "native-message-" + uid)
    db.create_session("unknown-history", "telegram")
    db.close()


def test_actual_sessiondb_users_topics_messages_unknown_and_no_lineage_merge(env):
    native_sessions(env)
    rows = {r["session_id"]: r for r in env.admin.conversations("default")}
    assert set(rows) == {"session-1", "session-2", "unknown-history"}
    assert rows["session-1"]["identity"]["principal_id"] != rows["session-2"]["identity"]["principal_id"]
    assert rows["session-1"]["identity"]["thread_id"] == "topic-A"
    assert rows["unknown-history"]["identity"]["evidence"] == "UNKNOWN"
    first = env.admin.conversation("default", "session-1")
    assert [m["content"] for m in first["messages"]] == ["native-message-1"]
    assert first["ancestor_history"] == "NOT_MERGED"
    assert len(env.admin.conversations("default", query="native-message-2")) == 1
    assert [r["session_id"] for r in env.admin.conversations("default", filters={"user_id": "2", "thread_id": "topic-B"})] == ["session-2"]
    assert env.admin.conversations("default", filters={"account_id": "bot-B"}) == []


def test_task_projection_uses_actual_native_association_and_no_cancel_mutation(env):
    store = Associations(env.state)
    owner = dict(bot_id="bot-A", user_id="1", chat_id="shared-chat", thread_id="topic-A", message_id="m",
                 session_id="session-1", session_key="key-1", profile="default")
    row, _ = store.claim(task_id="owned-task", admission_key="unique", owner=owner,
        brief=WorkBrief("dsh", "test", "check"), workspace_reference="synthetic-workspace",
        supervisor={"scope": "user", "unit": "friday-rework-worker-" + "a" * 32 + ".service"}, budget_seconds=30,
        deadline_unix=time.time() + 29)
    native_sessions(env)
    joined = env.admin.conversation("default", "session-1")["tasks"]
    assert len(joined) == 1 and joined[0]["existing_task_id"] == "owned-task"
    assert joined[0]["stop_available"] is True and joined[0]["goal_verification"] == "NOT_RUN"
    assert joined[0]["stop_reason"] == "VERIFY_CURRENT_ADMIN_AND_OWNING_GATEWAY_ON_ACTION"
    assert env.admin.conversation("default", "session-2")["tasks"] == []
    assert store.get("owned-task", owner) == row


@pytest.mark.parametrize("reference,index", [("unknown", 0), ("../../etc/passwd", 0), ("unknown", -1), ("unknown", 16)])
def test_attachment_arbitrary_reference_refused(env, reference, index):
    with pytest.raises((ValueError, PermissionError)): env.admin.attachment("default", reference, index)


def test_synthetic_secrets_are_structurally_and_text_masked(env):
    value = {"password_hash": "opaque-hash", "nested": [{"api_key": "synthetic-plain", "Authorization": "Bearer secret-value"}],
             "message": "Authorization: Bearer abcdefghijklmno1234567890", "token_count": 123}
    output = json.dumps(masked(value))
    for raw in ("opaque-hash", "synthetic-plain", "secret-value", "abcdefghijklmno1234567890"):
        assert raw not in output


def test_actual_native_pairing_request_approve_and_product_enable(env):
    from gateway.pairing import PairingStore
    store = PairingStore()
    # Actual native request creation/hashing/persistence, no outbound message.
    store.generate_code("telegram", "3", "same name")
    pending = env.admin.pairing("default")["pending"]
    assert len(pending) == 1 and "code" not in pending[0]
    result = env.admin.approve("default", platform="telegram", transport_profile="default", account_id="bot-A", request_id=pending[0]["request_id"])
    assert result["recorded"] and result["user"]["user_id"] == "3"
    assert PairingStore().is_approved("telegram", "3")
    assert gateway(env)._is_user_authorized(source(env, "3"))


def test_pairing_partial_persistence_reports_uncertainty(env):
    from gateway.pairing import PairingStore
    store = PairingStore(); store.generate_code("telegram", "4", "same name")
    ref = store.list_pending()[0]["request_id"]
    env.monkeypatch.setattr(ProductAccess, "set_user", lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic product failure")))
    with pytest.raises(RuntimeError, match="grant_may_exist"):
        env.admin.approve("default", platform="telegram", transport_profile="default", account_id="bot-A", request_id=ref)
    assert PairingStore().is_approved("telegram", "4")
    assert not gateway(env)._is_user_authorized(source(env, "4"))


def mounted_app(env, *, enabled=True, source_kind="user"):
    from hermes_cli import web_server_dashboard as dashboard, plugins_cmd
    app = FastAPI(); app.state.auth_required = True
    plugin = dashboard._dashboard_plugin_entry(json.loads((ROOT / "dashboard/manifest.json").read_text()), "friday_rework", ROOT / "dashboard", source_kind)
    web = ModuleType("hermes_cli.web_server"); web.app = app; web._get_dashboard_plugins = lambda: [plugin]
    env.monkeypatch.setitem(sys.modules, "hermes_cli.web_server", web)
    env.monkeypatch.setattr(plugins_cmd, "_get_enabled_set", lambda: {"friday_rework"} if enabled else set())
    env.monkeypatch.setattr(plugins_cmd, "_get_disabled_set", lambda: set())
    dashboard._mount_plugin_api_routes()
    return app


def test_native_trust_gates_actual_route_mount(env):
    for kind, enabled, expected in [("project", True, False), ("user", False, False), ("user", True, True)]:
        app = mounted_app(env, source_kind=kind, enabled=enabled)
        assert any(r.path == "/api/plugins/friday_rework/users" for r in app.routes) is expected


def test_native_basic_signed_auth_asgi_two_users_foreign_and_disable(env):
    import importlib.util
    from hermes_cli.dashboard_auth import middleware
    path = Path(__import__("hermes_cli").__path__[-1]).parent / "plugins/dashboard_auth/basic/__init__.py"
    s = importlib.util.spec_from_file_location("synthetic_native_basic", path); m = importlib.util.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m)
    provider = m.BasicAuthProvider(username="owner", password_hash="unused-synthetic-only", secret=b"synthetic-only-signing-key-32bytes")
    env.monkeypatch.setattr(middleware, "list_session_providers", lambda: [provider])
    from hermes_cli.dashboard_auth import request_utils
    env.monkeypatch.setattr(request_utils, "list_session_providers", lambda: [provider])
    # Signed by the actual native provider, verified by the actual native stack.
    owner_token = provider._mint_session("owner").access_token
    ordinary_token = provider._mint_session("ordinary").access_token
    app = mounted_app(env)
    @app.middleware("http")
    async def gate(req, next_call): return await middleware.gated_auth_middleware(req, next_call)
    native_sessions(env); user(env, "1"); user(env, "2")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic") as client:
            async def get(token, path="users", profile="default"):
                return await client.get("/api/plugins/friday_rework/" + path, params={"profile": profile}, headers={"Authorization": "Bearer " + token})
            assert (await get(ordinary_token)).status_code == 403
            assert (await get("bad-synthetic-signature")).status_code == 401
            assert (await get(owner_token, profile="foreign")).status_code == 403
            all_users = await get(owner_token); assert all_users.status_code == 200 and len(all_users.json()["users"]) == 2
            all_sessions = await get(owner_token, "conversations"); assert all_sessions.status_code == 200 and len(all_sessions.json()) == 3
            settings = env.cfg["plugins"]["entries"]["friday_rework"]["settings"]
            settings["synthetic_password_hash"] = "never-return-this-opaque-hash"
            env.save()
            effective = await get(owner_token, "effective")
            assert effective.status_code == 200 and "never-return-this-opaque-hash" not in effective.text
            body = {"platform": "telegram", "transport_profile": "default", "account_id": "bot-A", "user_id": "1", "enabled": False, "role": "user"}
            denied = await client.put("/api/plugins/friday_rework/users?profile=default", json=body, headers={"Authorization": "Bearer " + ordinary_token})
            assert denied.status_code == 403
            result = await client.put("/api/plugins/friday_rework/users?profile=default", json=body, headers={"Authorization": "Bearer " + owner_token})
            assert result.status_code == 200 and result.json()["recorded"] is True
            assert (await get(owner_token, profile="satellite")).status_code == 403
            bad = await client.put("/api/plugins/friday_rework/users?profile=default", json=body | {"enabled": 1, "admin": True}, headers={"Authorization": "Bearer " + owner_token})
            assert bad.status_code == 422
    asyncio.run(scenario())
    env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*")
    assert not gateway(env)._is_user_authorized(source(env, "1")) and gateway(env)._is_user_authorized(source(env, "2"))


def input_task(env):
    """Actual trusted association and staging from native ingress bytes; no worker."""
    import hashlib
    from dataclasses import asdict
    from friday_admin_controls.host_record import association_address, owner_from_ingress
    from friday_admin_controls.inputs import stage_inputs
    cache, staging, workspace = [env.home / p for p in ["cache", "stage", "workspace"]]
    for p in [cache, staging, workspace]: p.mkdir(mode=0o700)
    upload = cache / "user-file.txt"; upload.write_bytes(b"checked native input\n")
    payload_hash = hashlib.sha256(upload.read_bytes()).hexdigest()
    pinfile = env.home / "synthetic-source-pin"; pinfile.write_bytes(b"NOT AN EXECUTABLE; SOURCE FIXTURE ONLY")
    pin = {"path": str(pinfile), "sha256": hashlib.sha256(pinfile.read_bytes()).hexdigest()}
    runtime = dict(enabled=True, runtime_profile="default", runtime_home=str(env.home), workspace_root=str(workspace),
        staging_root=str(staging), cache_roots=[str(cache)], budget_seconds=60, max_file_bytes=1024, max_total_bytes=4096,
        dsh=dict(payload_root=str(env.home), toolchain_root=str(env.home), node=pin, cli=pin, patch=pin, native_files=[pin],
            key_name="SYNTHETIC_UNUSED_KEY", profile="headless", memory_bytes=2*1024**3, cpu_percent=200,
            tasks=64, shutdown_seconds=2, tmp_bytes=64*1024**2), runtime_receipt=pin)
    message = dict(bot_id="bot-A", user_id="1", chat_id="shared-chat", thread_id="topic-A", message_id="m",
        platform_update_id="u", reply_to_message_id="", media=[dict(local_reference=str(upload), mime_type="text/plain",
            origin=dict(bot_id="bot-A", chat_id="shared-chat", thread_id="topic-A", message_id="m", file_id="file-A", file_unique_id="unique-A", declared_bytes=upload.stat().st_size),
            content=dict(size_bytes=upload.stat().st_size, sha256=payload_hash))])
    ingress = dict(platform="telegram", source_profile="default", transport_profile="default", runtime_profile="default",
        session_key="key-1", chat_type="thread", message=message)
    call = dict(task_id="session-1", session_id="session-1", turn_id="turn", api_request_id="request", tool_call_id="tool")
    task_id = association_address(call, ingress); owner = owner_from_ingress(call, ingress)
    brief = WorkBrief("dsh", "read owned file", "parent checks bytes")
    store = Associations(env.state)
    row, _ = store.claim(task_id=task_id, admission_key=task_id, owner=owner, brief=brief,
        workspace_reference=str(workspace / task_id), supervisor={"scope": "user", "unit": "friday-rework-worker-" + task_id[7:39] + ".service"},
        budget_seconds=60, deadline_unix=time.time() + 59,
        host_binding={"correlation": call, "ingress": ingress, "brief": vars(brief), "runtime": runtime})
    stage = staging / task_id; stage.mkdir(mode=0o700)
    items = stage_inputs(matched_ingress=ingress, admitted_reference="association:" + task_id + "#ingress",
        cache_roots=[cache], staging_root=stage, worker_input_root="/job-input/verified", max_file_bytes=1024, max_total_bytes=4096)
    row = store.retain_inputs(task_id, owner, [asdict(item) for item in items])
    return row, store


def test_verified_native_received_attachment_actual_bytes(env):
    row, _ = input_task(env)
    assert env.admin.input_attachment("default", row["existing_task_id"], 0) == b"checked native input\n"
    with pytest.raises((ValueError, PermissionError)): env.admin.input_attachment("default", row["existing_task_id"], 1)
    with pytest.raises(PermissionError): env.admin.input_attachment("satellite", row["existing_task_id"], 0)


@pytest.mark.parametrize("mutation", ["bytes", "hardlink", "symlink", "origin", "missing_content", "ambiguous_mapping"])
def test_received_attachment_change_or_ambiguous_ownership_refused(env, mutation):
    row, _ = input_task(env); name = Path(row["host"]["inputs"][0]["host_path"])
    if mutation == "bytes": name.chmod(0o600); name.write_bytes(b"different\n"); name.chmod(0o400)
    elif mutation == "hardlink": os.link(name, env.home / "alias")
    elif mutation == "symlink": name.unlink(); name.symlink_to(env.home / "config.yaml")
    else:
        document = env.state.get("associations.v1")
        edited = document["jobs"][row["existing_task_id"]]
        if mutation == "origin": edited["host"]["binding"]["ingress"]["message"]["media"][0]["origin"]["message_id"] = "foreign-message"
        elif mutation == "missing_content": del edited["host"]["binding"]["ingress"]["message"]["media"][0]["content"]
        else: edited["host"]["inputs"].append(copy.deepcopy(edited["host"]["inputs"][0]))
        env.state.set("associations.v1", document)
    with pytest.raises((ValueError, PermissionError, OSError, ArtifactError, AssociationError)): env.admin.input_attachment("default", row["existing_task_id"], 0)


def test_ws_native_ticket_operator_and_ordinary_refusal_before_accept(env):
    from hermes_cli import web_server_chat as chat
    from hermes_cli.dashboard_auth.ws_tickets import mint_ticket
    app = FastAPI(); app.state.auth_required = True
    web = ModuleType("hermes_cli.web_server"); web.app = app; web._SESSION_TOKEN = "synthetic-legacy-token"
    env.monkeypatch.setitem(sys.modules, "hermes_cli.web_server", web)
    from starlette.websockets import WebSocket
    async def unused(*args): raise AssertionError("no WebSocket effects allowed")
    def ws(uid):
        ticket = mint_ticket(user_id=uid, provider="basic", extra={"org_id": ""})
        return WebSocket(dict(type="websocket", path="/api/ws", root_path="", query_string=("ticket=" + ticket).encode(),
            headers=[], scheme="ws", server=("synthetic", 80), client=("synthetic", 1), app=app), unused, unused)
    assert chat._ws_auth_reason(ws("owner")) == ("product_websocket_surface_unaudited", "ticket")
    assert chat._ws_auth_reason(ws("ordinary"))[0] == "product_dashboard_forbidden"
    value = ws("owner"); assert chat._ws_auth_reason(value)[0] == "product_websocket_surface_unaudited"
    assert chat._ws_auth_reason(value)[0] == "ticket_invalid"  # actual native once-only ticket
    value = ws("owner"); value.scope["query_string"] += b"&profile=foreign"
    assert chat._ws_auth_reason(value)[0] == "product_profile_forbidden"
