"""Native52 causal tests: production modules, in-memory provider stubs only."""
import copy
import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest



@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("network forbidden"))
    from tools import web_tools as wt, web_result_cache as cache
    from plugins.web import keyless_mcp as keyless
    from plugins.web import _common
    monkeypatch.setattr(wt, "_get_search_backend", lambda: "exa")
    monkeypatch.setattr(wt, "_load_web_config", lambda: {"backend": "exa", "keyless_rescue": False})
    monkeypatch.setattr(_common, "provider_env", lambda name: "")
    monkeypatch.setattr(keyless, "provider_tier", lambda name: "auto")
    monkeypatch.setattr(keyless, "keyless_enabled", lambda: True)
    monkeypatch.setattr(cache, "_web_config", lambda: {"cache_enabled": True})
    monkeypatch.setattr(wt, "_managed_search_fallback", lambda *a: None)
    monkeypatch.setattr(wt, "_rescue_eligible", lambda *a: False)
    cache.search_memo.clear()
    return wt


def provider(seen, name="exa", error=None):
    def search(query, limit):
        seen.append(limit)
        if error:
            return {"success": False, "error": error}
        if name == "exa" and limit > 20:
            return {"success": False, "error": "keyless search bounds refused"}
        return {"success": True, "data": {"web": [{"url": f"https://example.com/{n}"} for n in range(limit)]}}
    return SimpleNamespace(name=name, search=search)


def test_dynamic_advertisement_matches_selected_keyless_and_does_not_mutate_global():
    import model_tools as mt
    from tools.web_tools import WEB_SEARCH_SCHEMA
    raw = {"type": "function", "function": copy.deepcopy(WEB_SEARCH_SCHEMA)}
    result = mt._apply_dynamic_schemas([raw])[0]
    assert result["function"]["parameters"]["properties"]["limit"]["maximum"] == 20
    assert WEB_SEARCH_SCHEMA["parameters"]["properties"]["limit"]["maximum"] == 100
    assert raw["function"]["parameters"]["properties"]["limit"]["maximum"] == 100


@pytest.mark.parametrize("limit,expected", [(1,10),(5,10),(10,10),(11,20),(19,20),(20,20)])
def test_valid_exa_keyless_limits_are_never_inflated_past_endpoint(setup, limit, expected):
    seen = []
    result = setup._memoized_search(provider(seen), "same", limit)
    assert result["success"], result
    assert len(result["data"]["web"]) == limit
    assert seen == [expected]


@pytest.mark.parametrize("limit", [21,49,50,100])
def test_out_of_range_is_explicit_before_provider_cache_or_rescue(setup, monkeypatch, limit):
    from tools.web_result_cache import search_memo
    seen = []
    monkeypatch.setattr(search_memo, "lookup", lambda *a: pytest.fail("unsupported request reached cache"))
    monkeypatch.setattr(setup, "_managed_search_fallback", lambda *a: pytest.fail("unsupported request reached fallback"))
    result = setup._memoized_search(provider(seen), "same", limit)
    assert result["success"] is False
    assert result["state"] == "limit_exceeded"
    assert result["requested_limit"] == limit
    assert result["limit_max"] == 20
    assert seen == []


@pytest.mark.parametrize("error", ["HTTP 401 denied", "HTTP 403 denied", "HTTP 429 quota exceeded", "terminal provider failure"])
def test_provider_denial_is_preserved_and_not_cached(setup, error):
    seen = []
    p = provider(seen, error=error)
    for _ in range(2):
        assert setup._memoized_search(p, "same", 5) == {"success": False, "error": error}
    assert seen == [10,10]


@pytest.mark.parametrize("tier,key", [("paid", ""),("paid", "secret"),("auto", "secret")])
def test_keyed_or_paid_exa_retains_original_bound(setup, monkeypatch, tier, key):
    from plugins.web import keyless_mcp as keyless, _common
    import model_tools as mt
    monkeypatch.setattr(keyless, "provider_tier", lambda name: tier)
    monkeypatch.setattr(_common, "provider_env", lambda name: key)
    raw = {"type": "function", "function": copy.deepcopy(setup.WEB_SEARCH_SCHEMA)}
    assert mt._apply_dynamic_schemas([raw])[0]["function"]["parameters"]["properties"]["limit"]["maximum"] == 100
    seen=[]
    p = SimpleNamespace(name="exa", search=lambda q,n: (seen.append(n) or {"success": True, "data": {"web": []}}))
    assert setup._memoized_search(p, "same", 21)["success"]
    assert seen == [50]


def test_free_tier_with_key_is_still_keyless(setup, monkeypatch):
    from plugins.web import keyless_mcp as keyless, _common
    monkeypatch.setattr(keyless, "provider_tier", lambda name: "free")
    monkeypatch.setattr(_common, "provider_env", lambda name: "secret")
    import model_tools as mt
    raw = {"type": "function", "function": copy.deepcopy(setup.WEB_SEARCH_SCHEMA)}
    assert mt._apply_dynamic_schemas([raw])[0]["function"]["parameters"]["properties"]["limit"]["maximum"] == 20


def test_other_provider_keeps_original_cache_bucket(setup):
    seen=[]
    assert setup._memoized_search(provider(seen, "other"), "same", 21)["success"]
    assert seen == [50]


def test_disabled_cache_preserves_exact_request(setup, monkeypatch):
    from tools import web_result_cache as cache
    monkeypatch.setattr(cache, "_web_config", lambda: {"cache_enabled": False})
    seen=[]
    assert setup._memoized_search(provider(seen), "same", 5)["success"]
    assert seen == [5]


def test_dynamic_schema_cache_key_changes_when_key_mode_changes(setup, monkeypatch):
    import model_tools as mt
    from plugins.web import _common
    monkeypatch.setattr(mt, "check_fn_cache_scope", lambda: "test")
    a = mt._tool_defs_cache_key(["web"], [], True)
    monkeypatch.setattr(_common, "provider_env", lambda name: "secret")
    b = mt._tool_defs_cache_key(["web"], [], True)
    assert a != b


def test_excess_21_never_inflates_to_50_on_actual_provider_call(setup):
    seen=[]
    result=setup._memoized_search(provider(seen), "same", 21)
    assert seen == [], f"unsupported21 reached provider with cache bucket {seen}"
    assert result["state"] == "limit_exceeded"


def test_real_exa_provider_chain_default5_fetches10(setup, monkeypatch):
    from plugins.web import keyless_mcp as keyless
    from plugins.web.exa.provider import ExaWebSearchProvider
    calls=[]
    def mcp(url, tool, args, **kwargs):
        calls.append((tool,args))
        return "\n---\n".join(f"Title: item {i}\nURL: https://example.com/{i}\nHighlights: text" for i in range(args["numResults"]))
    monkeypatch.setattr(keyless, "mcp_call", mcp)
    result=setup._memoized_search(ExaWebSearchProvider(), "real chain", 5)
    assert result["success"], result
    assert len(result["data"]["web"]) == 5
    assert calls == [("web_search_exa", {"query":"real chain", "numResults":10})]


def test_deferred_tool_describe_advertises_current_keyless20(setup, monkeypatch):
    import model_tools as mt
    from tools import tool_search as search
    cfg=search.ToolSearchConfig.from_raw({"enabled":"on", "defer":["web_search"]})
    monkeypatch.setattr(search, "load_config_readonly", lambda: cfg)
    raw = {"type":"function", "function":copy.deepcopy(setup.WEB_SEARCH_SCHEMA)}
    definitions=mt._apply_dynamic_schemas([raw])
    result=json.loads(search.dispatch_tool_describe({"names":["web_search"]}, current_tool_defs=definitions, config=cfg))
    assert result["tools"]["web_search"]["parameters"]["properties"]["limit"]["maximum"] == 20


@pytest.mark.parametrize("enabled,disabled", [(["file"], []), (["file", "web"], ["web"])])
def test_file_only_native_definitions_ignore_malformed_unselected_web(setup, monkeypatch, enabled, disabled):
    import model_tools as mt
    monkeypatch.setattr(mt, "check_fn_cache_scope", lambda: "fixture-file-only")
    monkeypatch.setattr(setup, "_load_web_config", lambda: {"backend": ["malformed"]})
    # Exercise actual native backend parsing, not the fixture's selected-backend lambda.
    monkeypatch.setattr(setup, "_get_search_backend", lambda: setup._get_backend())
    mt._clear_tool_defs_cache()
    rows = mt.get_tool_definitions(enabled_toolsets=enabled, disabled_toolsets=disabled,
                                  quiet_mode=True, skip_tool_search_assembly=True)
    names = {row["function"]["name"] for row in rows}
    assert {"read_file", "write_file"} <= names
    assert "web_search" not in names
