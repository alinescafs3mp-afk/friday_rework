"""Actual native auth/stores and executable UI/client seams, entirely offline."""
import asyncio
import copy
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi import FastAPI
from starlette.websockets import WebSocket

from test_admin_foundation import (
    env, user, source, gateway, session, native_sessions, mounted_app,
    ProductAccess, PluginState, ROOT,
)
from hermes_cli.friday_product_access import ProductDashboardBoundary, session_allowed
from hermes_state import SessionDB


def ws(env, query="", path="/api/ws"):
    app = FastAPI(); app.state.auth_required = True
    web = ModuleType("hermes_cli.web_server"); web.app = app; web._SESSION_TOKEN = "synthetic-legacy"
    env.monkeypatch.setitem(sys.modules, "hermes_cli.web_server", web)
    async def unused(*args):
        raise AssertionError("Socket effects prohibited")
    return WebSocket(dict(type="websocket", path=path, root_path="", query_string=query.encode(),
        headers=[], scheme="ws", server=("synthetic", 80), client=("synthetic", 1), app=app), unused, unused)


@pytest.mark.parametrize("path", ["/api/ws", "/api/console", "/api/pty", "/api/pub", "/api/events",
    "/api/display/ws", "/api/audio/speak-stream", "/p/satellite/api/ws", "/future/ws"])
@pytest.mark.parametrize("profile", ["", "default", "satellite", "foreign"])
def test_product_asgi_refuses_every_ws_before_any_native_dispatch(env, path, profile):
    received = []
    async def forbidden(*args):
        raise AssertionError("Native RPC, PTY, display, audio must remain unreachable")
    async def scenario():
        await ProductDashboardBoundary(forbidden)(dict(type="websocket", path=path,
            query_string=("profile=" + profile).encode()), forbidden, lambda_send)
    async def lambda_send(message): received.append(message)
    asyncio.run(scenario())
    assert received == [{"type": "websocket.close", "code": 1008,
                         "reason": "product_websocket_surface_unaudited"}]


@pytest.mark.parametrize("config", [{}, {"admin": {"enabled": False}}])
def test_non_product_ws_asgi_keeps_native_behavior(env, config):
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"] = config; env.save()
    calls = []
    async def native(scope, receive, send): calls.append(scope)
    asyncio.run(ProductDashboardBoundary(native)({"type": "websocket"}, None, None))
    assert calls == [{"type": "websocket"}]


def test_product_asgi_http_uses_original_native_router(env):
    calls = []
    async def native(scope, receive, send): calls.append(scope)
    asyncio.run(ProductDashboardBoundary(native)({"type": "http"}, None, None))
    assert calls == [{"type": "http"}]


def test_actual_native_app_mount_refuses_ws_before_router(env):
    import importlib
    previous = sys.stdout
    try:
        native = importlib.import_module("hermes_cli.web_server")
    finally:
        sys.stdout = previous
    assert any(m.cls is ProductDashboardBoundary for m in native.app.user_middleware)
    messages = []
    async def no_receive(): raise AssertionError("Unaudited WS must refuse before reading commands")
    async def send(msg): messages.append(msg)
    async def scenario():
        for path in ["/api/ws", "/api/pty", "/api/console", "/api/display/ws", "/api/audio/speak-stream"]:
            await native.app(dict(type="websocket", asgi={"version": "3.0"}, path=path, root_path="",
                query_string=b"", headers=[], scheme="ws", server=("synthetic", 80), client=("synthetic", 1)), no_receive, send)
    asyncio.run(scenario())
    assert len(messages) == 5 and all(m["type"] == "websocket.close" and m["code"] == 1008 for m in messages)


def test_corrupt_admin_policy_ws_fails_closed(env):
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"]["admin"]["enabled"] = 0; env.save()
    messages = []
    async def deny(*args): raise AssertionError("Corrupt policy cannot admit WS")
    async def send(msg): messages.append(msg)
    asyncio.run(ProductDashboardBoundary(deny)({"type": "websocket"}, deny, send))
    assert messages[0]["code"] == 1008


@pytest.mark.parametrize("method,params", [("session.list", {"profile": "satellite"}),
    ("session.list", {}), ("config.get", {"key": "full", "profile": "default"}),
    ("session.create", {"profile": "satellite"})])
@pytest.mark.parametrize("transport_kind", ["verified", "legacy"])
def test_actual_native_rpc_cannot_bypass_product_policy_after_upgrade(env, method, params, transport_kind):
    from types import SimpleNamespace
    from hermes_cli import banner
    env.monkeypatch.setattr(banner, "prefetch_update_check", lambda: None)
    previous = sys.stdout
    try:
        from tui_gateway import server
    finally:
        sys.stdout = previous
    from tui_gateway.transport import bind_transport, reset_transport
    from tui_gateway.ws import WSTransport
    transport = (SimpleNamespace(auth_identity={"provider": "basic", "user_id": "owner", "org_id": ""})
                 if transport_kind == "verified" else object.__new__(WSTransport))
    request = {"jsonrpc": "2.0", "id": 7, "method": method, "params": params}
    context = bind_transport(transport)
    try:
        result = server.handle_request(request)
    finally:
        reset_transport(context)
    assert result["error"]["code"] == 403 and result["error"]["message"] == "product_rpc_surface_unaudited"
    # Dispatch must reject before long-handler queueing or any transport write.
    assert server.dispatch(request, transport) == result


def test_local_stdio_and_non_product_rpc_not_restricted(env):
    from hermes_cli.friday_product_access import product_rpc_allowed
    from types import SimpleNamespace
    assert product_rpc_allowed(None)
    assert product_rpc_allowed(SimpleNamespace())
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"] = {}; env.save()
    assert product_rpc_allowed(SimpleNamespace(auth_identity={"user_id": "ordinary"}))


@pytest.mark.parametrize("org,expected", [(None, "product_dashboard_forbidden"),
    ("", "product_websocket_surface_unaudited"), ("foreign", "product_dashboard_forbidden")])
def test_ticket_org_never_invented_and_once_only(env, org, expected):
    from hermes_cli import web_server_chat as chat
    from hermes_cli.dashboard_auth.ws_tickets import mint_ticket
    extra = {} if org is None else {"org_id": org}
    value = ws(env, "ticket=" + mint_ticket(user_id="owner", provider="basic", extra=extra))
    assert chat._ws_auth_reason(value)[0] == expected
    identity = value._hermes_auth_identity
    assert ("org_id" in identity) == (org is not None)
    if org is not None: assert identity["org_id"] == org
    assert chat._ws_auth_reason(value)[0] == "ticket_invalid"


@pytest.mark.parametrize("org", ["", "foreign-organization"])
def test_actual_rs256_oidc_preserves_verified_org_and_refuses_ws(env, org):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from hermes_cli import web_server_chat as chat
    from hermes_cli.dashboard_auth import middleware, request_utils
    H = Path(__import__("hermes_cli").__path__[-1]).parent
    spec = importlib.util.spec_from_file_location("repair_oidc", H / "plugins/dashboard_auth/self_hosted/__init__.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    issuer = "https://synthetic-oidc.invalid"
    provider = mod.SelfHostedOIDCProvider(issuer=issuer, client_id="repair-client")
    provider._discovery = {"issuer": issuer, "jwks_uri": issuer + "/jwks"}; provider._discovery_fetched_at = time.time()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="synthetic-only", use="sig", alg="RS256")
    provider._jwks_client = jwt.PyJWKClient(issuer + "/jwks")
    provider._jwks_client.jwk_set_cache.put({"keys": [public]})
    claims = dict(sub="owner", iss=issuer, aud="repair-client", iat=int(time.time()), exp=int(time.time()) + 600, org_id=org)
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "synthetic-only"})
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"]["admin"]["operators"][0]["provider"] = "self-hosted"
    env.save()
    env.monkeypatch.setattr(middleware, "list_session_providers", lambda: [provider])
    env.monkeypatch.setattr(request_utils, "list_session_providers", lambda: [provider])
    verified = provider.verify_session(access_token=token)
    assert verified.org_id == org and session_allowed(verified) == (org == "")
    value = ws(env, "token=" + token + "&profile=default")
    assert chat._ws_auth_reason(value)[0] == ("product_websocket_surface_unaudited" if not org else "product_dashboard_forbidden")
    assert value._hermes_auth_identity["org_id"] == org
    expired = jwt.encode(claims | {"exp": int(time.time()) - 120}, key, algorithm="RS256", headers={"kid": "synthetic-only"})
    assert provider.verify_session(access_token=expired) is None


def test_actual_ticket_route_keeps_authenticated_org(env):
    from hermes_cli.dashboard_auth.routes import api_auth_ws_ticket
    from hermes_cli.dashboard_auth.ws_tickets import consume_ticket
    from test_admin_foundation import request
    value = session(org_id="verified-org")
    req = request(value); result = asyncio.run(api_auth_ws_ticket(req))
    assert consume_ticket(result["ticket"])["org_id"] == "verified-org"


def test_native_created_history_keeps_account_after_rotation_and_peer_refresh(env):
    native_sessions(env)
    before = env.admin.conversation("default", "session-1")["identity"]
    env.cfg["plugins"]["entries"]["friday_rework"]["settings"]["product_access"]["accounts"][0]["account_id"] = "bot-new"
    env.save()
    from gateway.session_recovery import SessionRecoveryMixin
    value = source(env); value.chat_id = "shared-chat"; value.thread_id = "topic-A"
    proposed = SessionRecoveryMixin._session_create_kwargs(session_id="unused", session_key="key-1", origin=value,
        source_value="telegram", display_name=None, parent_session_id=None)
    assert json.loads(proposed["origin_json"])["friday_account_origin"]["account_id"] == "bot-new"
    db = SessionDB(env.home / "state.db")
    db.record_gateway_session_peer("session-1", session_key="key-1", source="telegram", user_id="1", chat_id="shared-chat",
        thread_id="topic-A", origin_json=proposed["origin_json"], transport_profile="default")
    db.close()
    after = env.admin.conversation("default", "session-1")["identity"]
    assert before == after and after["account_id"] == "bot-A"


@pytest.mark.parametrize("legacy", [None, {"platform": "telegram", "user_id": "1", "chat_id": "chat", "thread_id": None}])
def test_old_unproven_history_never_backfilled_from_current_policy(env, legacy):
    db = SessionDB(env.home / "state.db")
    db.create_session("legacy", "telegram", user_id="1", chat_id="chat", session_key="legacy-key", transport_profile="default",
        origin_json=json.dumps(legacy))
    from gateway.session_recovery import SessionRecoveryMixin
    value = source(env)
    new = SessionRecoveryMixin._session_create_kwargs(session_id="new", session_key="legacy-key", origin=value,
        source_value="telegram", display_name=None, parent_session_id=None)
    db.record_gateway_session_peer("legacy", session_key="legacy-key", source="telegram", user_id="1", chat_id="chat",
        transport_profile="default", origin_json=new["origin_json"])
    db.close()
    assert env.admin.conversation("default", "legacy")["identity"]["evidence"] == "UNKNOWN"


def test_unknown_native_transport_does_not_stamp_account(env):
    from gateway.session_recovery import SessionRecoveryMixin
    value = source(env); del value._identity
    kwargs = SessionRecoveryMixin._session_create_kwargs(session_id="unknown", session_key="key", origin=value,
        source_value="telegram", display_name=None, parent_session_id=None)
    assert "friday_account_origin" not in json.loads(kwargs["origin_json"])


def test_compression_peer_refresh_keeps_each_original_account_in_same_native_transaction(env):
    native_sessions(env); db = SessionDB(env.home / "state.db")
    old = json.loads(db.get_session("session-1")["origin_json"])
    tip = copy.deepcopy(old); tip["friday_account_origin"]["account_id"] = "tip-account"
    db.end_session("session-1", "compression")
    db.create_session("tip", "telegram", parent_session_id="session-1", user_id="1", chat_id="shared-chat",
        thread_id="topic-A", session_key="key-1", transport_profile="default", origin_json=json.dumps(tip))
    proposed = copy.deepcopy(tip); proposed["friday_account_origin"]["account_id"] = "current-replacement"
    db.record_gateway_session_peer("tip", session_key="key-1", source="telegram", user_id="1", chat_id="shared-chat",
        thread_id="topic-A", transport_profile="default", origin_json=json.dumps(proposed), include_compression_ancestors=True)
    assert json.loads(db.get_session("session-1")["origin_json"])["friday_account_origin"]["account_id"] == "bot-A"
    assert json.loads(db.get_session("tip")["origin_json"])["friday_account_origin"]["account_id"] == "tip-account"
    db.close()


@pytest.mark.parametrize("operation", ["users", "pairing", "set_user", "approve"])
def test_runtime_profile_cannot_read_or_write_inert_access_authority(env, operation):
    env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*"); user(env)
    values = dict(platform="telegram", transport_profile="default", account_id="bot-A")
    with pytest.raises(PermissionError, match="receiving_transport_authority"):
        if operation in {"users", "pairing"}: getattr(env.admin, operation)("satellite")
        elif operation == "set_user": env.admin.set_user("satellite", **values, user_id="1", enabled=False, role="user")
        else: env.admin.approve("satellite", **values, request_id="not-looked-up")
    assert gateway(env)._is_user_authorized(source(env, profile="satellite"))
    env.admin.set_user("default", **values, user_id="1", enabled=False, role="user")
    assert not gateway(env)._is_user_authorized(source(env, profile="satellite"))


@pytest.mark.parametrize("messages", [1, 100, 101, 121, 200, 201])
def test_real_message_pages_cover_entire_history_without_overlap(env, messages):
    native_sessions(env); db = SessionDB(env.home / "state.db")
    for i in range(messages - 1): db.append_message("session-1", "user", "message-" + str(i))
    db.close()
    result = []; offset = 0
    while True:
        page = env.admin.conversation("default", "session-1", offset=offset)
        assert page["page"]["offset"] == offset and page["page"]["count"] == len(page["messages"])
        result += page["messages"]
        if page["page"]["next_offset"] is None:
            assert page["page"]["end"] and page["page"]["state"] == "END"; break
        assert page["page"]["has_more"] and not page["page"]["end"]
        offset = page["page"]["next_offset"]
    assert len(result) == messages and len({m["id"] for m in result}) == messages


@pytest.mark.parametrize("limit,offset", [(0, 0), (201, 0), (True, 0), (100, -1), (100, 100001), (100, False)])
def test_message_pagination_rejects_unbounded_or_ambiguous_input(env, limit, offset):
    with pytest.raises(ValueError, match="invalid_admin_session"):
        env.admin.conversation("default", "session-1", limit=limit, offset=offset)


def test_maximum_message_page_and_bounded_navigation_state(env):
    native_sessions(env); db = SessionDB(env.home / "state.db")
    for i in range(200): db.append_message("session-1", "user", "bounded-" + str(i))
    db.close()
    page = env.admin.conversation("default", "session-1", limit=200)
    assert len(page["messages"]) == 200 and page["page"]["next_offset"] == 200
    end = env.admin.conversation("default", "session-1", offset=100000)
    assert end["page"]["next_offset"] is None and end["page"]["state"] == "END"


def run_ui(scenario):
    H = Path(__import__("hermes_cli").__path__[-1]).parent
    response = subprocess.run(["/home/jericho/.local/bin/node", "--disable-wasm-trap-handler", "--max-old-space-size=128", str(Path(__file__).with_name("admin_ui_controls.cjs")),
        str(ROOT / "dashboard/index.js"), str(H / "web/src/lib/api.ts")], input=json.dumps(scenario),
        text=True, capture_output=True, timeout=25, check=False)
    assert response.returncode == 0, response.stderr
    return json.loads(response.stdout)


def basic_app(env):
    from hermes_cli.dashboard_auth import middleware, request_utils
    H = Path(__import__("hermes_cli").__path__[-1]).parent
    spec = importlib.util.spec_from_file_location("repair_basic", H / "plugins/dashboard_auth/basic/__init__.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    provider = mod.BasicAuthProvider(username="owner", password_hash="unused-synthetic-only", secret=b"synthetic-repair-key-at-least-32bytes")
    env.monkeypatch.setattr(middleware, "list_session_providers", lambda: [provider])
    env.monkeypatch.setattr(request_utils, "list_session_providers", lambda: [provider])
    app = mounted_app(env)
    @app.middleware("http")
    async def gate(req, next_call): return await middleware.gated_auth_middleware(req, next_call)
    return app, provider._mint_session("owner").access_token


@pytest.mark.parametrize("action", ["disable", "enable", "role", "approve"])
def test_executed_ui_native_fetchjson_bytes_succeed_at_actual_signed_router(env, action):
    app, token = basic_app(env); user(env)
    from gateway.pairing import PairingStore
    store = PairingStore(); store.generate_code("telegram", "new-user", "synthetic-only")
    pending = store.list_pending()[0]
    users = env.admin.users("default")
    if action == "enable": env.admin.set_user("default", **{k: v for k, v in users["users"][0].items() if k != "principal_id"} | {"enabled": False}); users = env.admin.users("default")
    # Gated browsers authenticate with native cookies; fetchJSON must keep include.
    result = run_ui(dict(action=action, users=users, pending=env.admin.pairing("default")))
    writes = [r for r in result["requests"] if r["method"] in {"PUT", "POST"}]
    assert len(writes) == 1
    request = writes[0]
    assert request["headers"]["content-type"] == "application/json" and request["credentials"] == "include"
    assert "authorization" not in request["headers"]
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic",
            cookies={"hermes_session_at": token, "hermes_session_provider": "basic"}) as client:
            bad = await client.request(request["method"], request["url"], content=request["body"],
                headers=request["headers"] | {"content-type": "text/plain;charset=UTF-8"})
            assert bad.status_code == 422
            good = await client.request(request["method"], request["url"], content=request["body"], headers=request["headers"])
            assert good.status_code == 200, good.text
    asyncio.run(scenario())
    if action == "disable":
        env.monkeypatch.setenv("GATEWAY_ALLOWED_USERS", "*"); assert not gateway(env)._is_user_authorized(source(env))
    if action == "approve": assert store.is_approved("telegram", pending["user_id"])


def test_executed_ui_next_previous_messages_follow_actual_native_pages(env):
    native_sessions(env); db = SessionDB(env.home / "state.db")
    for i in range(120): db.append_message("session-1", "user", "message-" + str(i))
    db.close()
    first = env.admin.conversation("default", "session-1")
    second = env.admin.conversation("default", "session-1", offset=100)
    result = run_ui(dict(action="messages", token="synthetic-only", conversations=env.admin.conversations("default"),
        pages={"0": first, "100": second}))
    requests = [r for r in result["requests"] if "/conversations/session-1?" in r["url"]]
    assert [r["url"].split("offset=")[1] for r in requests] == ["0", "100", "0"]
    assert result["page_states"] == ["MORE", "END", "MORE"]
    assert result["message_counts"] == [100, 21, 100]
    app, token = basic_app(env)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://synthetic") as client:
            for request, count in zip(requests, result["message_counts"]):
                got = await client.get(request["url"], headers={"Authorization": "Bearer " + token})
                assert got.status_code == 200 and len(got.json()["messages"]) == count
    asyncio.run(scenario())
