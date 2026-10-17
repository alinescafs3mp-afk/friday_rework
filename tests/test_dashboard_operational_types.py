"""Shipped controls/events -> exact native SDK JSON -> mounted API/native writer.

Offline boundary: finite React hook/element driver and intercepted fetch; requests
are replayed unchanged through in-process ASGI with native signed authentication.
No browser, listening socket, model, live account or runtime reload is claimed.
"""
import asyncio
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from test_admin_controls import basic, local_config
from test_admin_foundation import ROOT, mounted_app

pytest_plugins = ["test_admin_foundation"]


@pytest.fixture
def authenticated(env, monkeypatch):
    from hermes_cli.dashboard_auth import middleware, request_utils
    local_config(env)
    provider = basic()
    monkeypatch.setattr(middleware, "list_session_providers", lambda: [provider])
    monkeypatch.setattr(request_utils, "list_session_providers", lambda: [provider])
    app = mounted_app(env)

    @app.middleware("http")
    async def gate(request, next_call):
        return await middleware.gated_auth_middleware(request, next_call)

    return app, provider._mint_session("owner").access_token


def ui(effective, token, fields, *, force=False, plugin=None):
    import hermes_cli
    native = Path(hermes_cli.__path__[-1]).parent
    payload = {"action": "settings", "kind": "operational", "fields": fields,
               "effective": effective, "token": token, "force_disabled_save": force}
    out = subprocess.run([
        "/home/jericho/.local/bin/node", "--disable-wasm-trap-handler", "--max-old-space-size=256",
        str(ROOT.parents[1] / "tests/admin_ui_controls.cjs"),
        str(plugin or ROOT / "dashboard/index.js"), str(native / "web/src/lib/api.ts"),
    ], input=json.dumps(payload), capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout)
    writes = [r for r in result["requests"] if r["method"] == "PUT"]
    return result, writes


def run(authenticated, scenario):
    app, token = authenticated

    async def execute():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://offline.invalid",
                                     cookies={"hermes_session_at": token, "hermes_session_provider": "basic"}) as client:
            response = await client.get("/api/plugins/friday_rework/effective?profile=default",
                                        headers={"X-Hermes-Session-Token": token})
            assert response.status_code == 200, response.text
            return await scenario(client, token, response.json())

    return asyncio.run(execute())


@pytest.mark.parametrize("key,value,expected", [
    ("tools.tool_search.enabled", None, "off"),
    ("tools.tool_search.defer", None, None),
    ("streaming.enabled", True, True),
    ("streaming.enabled", False, False),
    ("agent.max_turns", "1", 1),
    ("agent.max_turns", "17", 17),
    ("agent.max_turns", "200", 200),
])
def test_rendered_control_native_sdk_exact_json_accepted_by_real_api(env, authenticated, key, value, expected):
    from hermes_cli import config
    from tools.tool_search import ToolSearchConfig

    async def scenario(client, token, effective):
        before = (env.home / "config.yaml").read_bytes()
        fields = {"key": key}
        if value is not None:
            fields["enabled" if key == "streaming.enabled" else "value"] = value
        result, writes = ui(effective, token, fields)
        assert len(writes) == 1
        assert (env.home / "config.yaml").read_bytes() == before
        actual = expected
        if key == "tools.tool_search.defer":
            raw = config.require_readable_config_before_write()
            actual = sorted(ToolSearchConfig.from_raw(raw.get("tools", {}).get("tool_search")).effective_defer_tools
                            | {"session_search", "read_file"})
            control = next(c for c in result["controls"] if c.get("label") == "Native required deferred tools")
            assert control["tag"] == "textarea" and control["readOnly"] is True
            assert control["value"].splitlines() == actual
        if key == "tools.tool_search.enabled":
            control = next(c for c in result["controls"] if c.get("label") == "Operational string value")
            assert control["tag"] == "select" and control["disabled"] is True and control["value"] == "off"
        write = writes[0]
        assert write["headers"]["x-hermes-session-token"] == token
        assert write["credentials"] == "include"
        assert json.loads(write["body"]) == {"kind": "operational", "expected_sha256": effective["config_sha256"],
                                             "values": {"key": key, "value": actual}}
        response = await client.put(write["url"], content=write["body"], headers=write["headers"])
        assert response.status_code == 200, response.text
        assert response.json()["recorded"] is True and response.json()["observed_live_reload"] is False
        current = config.require_readable_config_before_write()
        for part in key.split("."):
            current = current[part]
        assert current == actual and type(current) is type(actual)
        # A replay of this UI CAS must not overwrite a subsequent native change.
        response = await client.put(write["url"], content=write["body"], headers=write["headers"])
        assert response.status_code == 400

    run(authenticated, scenario)


@pytest.mark.parametrize("native_list", [[], ["todo_list"], ["synthetic_existing_tool", "read_file"]])
def test_defer_metadata_is_derived_from_existing_native_effective_semantics(env, authenticated, native_list):
    from hermes_cli import config
    from tools.tool_search import ToolSearchConfig
    raw = config.require_readable_config_before_write()
    raw.setdefault("tools", {}).setdefault("tool_search", {})["defer"] = native_list
    config.atomic_config_write(env.home / "config.yaml", raw)

    async def scenario(client, token, effective):
        expected = sorted(ToolSearchConfig.from_raw({"defer": native_list}).effective_defer_tools
                          | {"session_search", "read_file"})
        assert effective["typed_options"]["operational_specs"]["tools.tool_search.defer"]["const"] == expected
        _, writes = ui(effective, token, {"key": "tools.tool_search.defer"})
        assert json.loads(writes[0]["body"])["values"]["value"] == expected
        result = await client.put(writes[0]["url"], content=writes[0]["body"], headers=writes[0]["headers"])
        assert result.status_code == 200

    run(authenticated, scenario)


@pytest.mark.parametrize("key,spec", [
    ("agent.max_turns", None),
    ("agent.max_turns", {"type": "integer", "minimum": 0, "maximum": 200}),
    ("streaming.enabled", {"type": "string"}),
    ("tools.tool_search.enabled", {"type": "string", "enum": ["off", "on"]}),
    ("tools.tool_search.defer", {"type": "array", "const": "read_file"}),
    ("tools.tool_search.defer", {"type": "array", "const": ["read_file"]}),
    ("tools.tool_search.defer", {"type": "array", "const": ["read_file", "session_search", 1]}),
    ("tools.tool_search.defer", {"type": "array", "const": ["read_file", "session_search", "read_file"]}),
    ("unknown.setting", {"type": "integer", "minimum": 1, "maximum": 200}),
])
def test_invalid_unavailable_or_unknown_metadata_blocks_even_forced_save(env, authenticated, key, spec):
    async def scenario(client, token, effective):
        before = (env.home / "config.yaml").read_bytes()
        effective["typed_options"]["operational_specs"][key] = spec
        if key == "unknown.setting":
            effective["typed_options"]["operational"].append(key)
        result, writes = ui(effective, token, {"key": key}, force=True)
        assert writes == [] and "Native typed setting unavailable" in result["rendered_text"]
        assert (env.home / "config.yaml").read_bytes() == before

    run(authenticated, scenario)


@pytest.mark.parametrize("fault", ["missing_specs", "null_specs", "missing_keys", "null_keys", "invalid_keys",
                                  "missing_sha", "null_sha", "invalid_sha"])
def test_missing_metadata_or_cas_never_sends_mutation(env, authenticated, fault):
    async def scenario(client, token, effective):
        before = (env.home / "config.yaml").read_bytes()
        force = fault.endswith(("specs", "keys"))
        if fault == "missing_specs":
            effective["typed_options"].pop("operational_specs")
        elif fault == "null_specs":
            effective["typed_options"]["operational_specs"] = None
        elif fault == "missing_keys":
            effective["typed_options"].pop("operational")
        elif fault in ("null_keys", "invalid_keys"):
            effective["typed_options"]["operational"] = None if fault == "null_keys" else "wrong"
        elif fault == "missing_sha":
            effective.pop("config_sha256")
        else:
            effective["config_sha256"] = None if fault == "null_sha" else "wrong"
        _, writes = ui(effective, token, {"key": "tools.tool_search.enabled"}, force=force)
        assert writes == [] and (env.home / "config.yaml").read_bytes() == before

    run(authenticated, scenario)


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "1.5", "1e2", "0", "201", "-1", "9007199254740993"])
def test_integer_invalid_input_fails_before_request(env, authenticated, value):
    async def scenario(client, token, effective):
        before = (env.home / "config.yaml").read_bytes()
        _, writes = ui(effective, token, {"key": "agent.max_turns", "value": value})
        assert writes == [] and (env.home / "config.yaml").read_bytes() == before

    run(authenticated, scenario)


@pytest.mark.parametrize("key,value", [
    ("tools.tool_search.enabled", None), ("tools.tool_search.enabled", 0),
    ("tools.tool_search.enabled", "on"), ("tools.tool_search.defer", "read_file,session_search"),
    ("tools.tool_search.defer", ["read_file"]),
    ("tools.tool_search.defer", ["read_file", "session_search", "session_search"]),
    ("tools.tool_search.defer", ["read_file", "session_search", "arbitrary_new_tool"]),
    ("streaming.enabled", "false"), ("agent.max_turns", 1.5),
    ("agent.max_turns", True), ("unknown.setting", 3),
])
def test_native_api_rejects_tampered_operational_value_without_write(env, authenticated, key, value):
    async def scenario(client, token, effective):
        before = (env.home / "config.yaml").read_bytes()
        response = await client.put("/api/plugins/friday_rework/settings?profile=default",
            json={"kind": "operational", "expected_sha256": effective["config_sha256"],
                  "values": {"key": key, "value": value}}, headers={"X-Hermes-Session-Token": token})
        assert response.status_code == 400
        assert (env.home / "config.yaml").read_bytes() == before

    run(authenticated, scenario)


def test_api_cas_mandatory_retrieval_and_ownership_still_enforced(env, authenticated):
    async def scenario(client, token, effective):
        before = (env.home / "config.yaml").read_bytes()
        body = {"kind": "operational", "values": {"key": "tools.tool_search.enabled", "value": "off"}}
        response = await client.put("/api/plugins/friday_rework/settings?profile=default", json=body,
                                    headers={"X-Hermes-Session-Token": token})
        assert response.status_code == 422
        body["expected_sha256"] = "a" * 64
        response = await client.put("/api/plugins/friday_rework/settings?profile=default", json=body,
                                    headers={"X-Hermes-Session-Token": token})
        assert response.status_code == 400
        body.update(kind="toolset", expected_sha256=effective["config_sha256"], values={"name": "web", "enabled": False})
        response = await client.put("/api/plugins/friday_rework/settings?profile=default", json=body,
                                    headers={"X-Hermes-Session-Token": token})
        assert response.status_code == 400
        body.update(kind="operational", values={"key": "tools.tool_search.enabled", "value": "off"})
        response = await client.put("/api/plugins/friday_rework/settings?profile=foreign", json=body,
                                    headers={"X-Hermes-Session-Token": token})
        assert response.status_code == 403
        assert (env.home / "config.yaml").read_bytes() == before

    run(authenticated, scenario)
