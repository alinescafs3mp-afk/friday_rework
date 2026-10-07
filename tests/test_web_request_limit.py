"""Actual pinned native dispatch/provider/MCP, synthetic HTTP transport only."""
import asyncio
import json
import runpy
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from hermes_cli.config import atomic_config_replace
from tools import web_tools as wt, web_result_cache as cache
from agent import web_search_registry as registry
from plugins.web.exa import provider as exa
from plugins.web import keyless_mcp as mcp

Q = Path(__file__).resolve().parents[1]
build = runpy.run_path(str(Q / "tools/configure_local_test.py"))["build_config"]


@pytest.fixture
def native(monkeypatch, tmp_path):
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    config = build(base_url="http://127.0.0.1:8011/v1", model="offline-fixture", key_env="FRIDAY_FIXTURE_KEY",
                   context=40960, max_input=40954, main_output=4096, summary_output=2048,
                   margin=1024, template_overhead=2048, web_profile="exa-keyless")
    atomic_config_replace(home / "config.yaml", config)
    registry.register_provider(exa.ExaWebSearchProvider())
    # Full normal plugin discovery is NOT_RUN. The registered provider and all
    # native selection/ring/parsing/cache/error functions below are genuine.
    monkeypatch.setattr(wt, "_ensure_web_plugins_loaded", lambda: None)
    monkeypatch.setattr(cache, "search_memo", cache.SearchMemo())
    monkeypatch.setattr(exa, "_get_exa_client", lambda: pytest.fail("paid SDK rescue forbidden"))
    calls = []

    def post(url, **kw):
        calls.append((url, kw))
        assert url == mcp.EXA_MCP_URL and kw["timeout"] == 30
        assert not any(k.lower() == "authorization" for k in kw["headers"])
        args = kw["json"]["params"]["arguments"]
        if kw["json"]["params"]["name"] == "web_search_exa":
            text = "\n---\n".join(f"Title: Native fixture{i}\nURL: https://example.com/{i}\nHighlights:\nsource{i}"
                                    for i in range(args["numResults"]))
        else:
            text = "# Source\nDocument text read through native extraction"
        body = json.dumps({"jsonrpc":"2.0", "id":1, "result":{"content":[{"type":"text", "text":text}]}}).encode()
        return SimpleNamespace(status_code=200, headers={"Content-Type":"application/json"}, content=body)
    monkeypatch.setattr(requests, "post", post)
    return config, home, calls, post


def test_literal_one_use_native_receipt(native, monkeypatch):
    _, _, calls, post = native
    expected = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"web_search_exa","arguments":{"query":"Friday exact native limit","numResults":3}}}'
    consumed = []
    def once(url, **kw):
        actual = json.dumps(kw["json"], separators=(",", ":"), ensure_ascii=False).encode()
        assert actual == expected and not consumed
        consumed.append(actual)
        return post(url, **kw)
    monkeypatch.setattr(requests, "post", once)
    result = json.loads(wt.web_search_tool("Friday exact native limit", 3))
    assert result["success"] and len(result["data"]["web"]) == 3
    assert consumed == [expected] and len(calls) == 1


@pytest.mark.parametrize("value,want", [(1,1), (3,3), (5,5), (11,11), (100,100), (101,100),
                                         (0,1), (-3,1), (None,5), ("bad",5), ("3",3), (True,1), (3.9,3)])
def test_native_validation_stays_intact(native, value, want):
    _, _, calls, _ = native
    result = json.loads(wt.web_search_tool("validation", value))
    assert result["success"] and len(result["data"]["web"]) == want
    assert calls[0][1]["json"]["params"]["arguments"]["numResults"] == want


def test_disabled_cache_repeats_exact_request(native):
    _, _, calls, _ = native
    for _ in range(2): assert json.loads(wt.web_search_tool("same query", 3))["success"]
    assert [x[1]["json"]["params"]["arguments"]["numResults"] for x in calls] == [3,3]


@pytest.mark.parametrize("enabled", [True, None])
def test_cache_enabled_default_hit_bucket_and_slice(native, enabled):
    config, home, calls, _ = native
    if enabled is None: del config["web"]["cache_enabled"]
    else: config["web"]["cache_enabled"] = enabled
    atomic_config_replace(home / "config.yaml", config)
    first = json.loads(wt.web_search_tool("bucket query", 3))
    second = json.loads(wt.web_search_tool("  BUCKET   query ", 8))
    assert len(first["data"]["web"]) == 3 and len(second["data"]["web"]) == 8
    assert len(calls) == 1 and calls[0][1]["json"]["params"]["arguments"]["numResults"] == 10


def test_actual_singleflight_retained(native, monkeypatch):
    config, home, calls, post = native
    config["web"]["cache_enabled"] = True;atomic_config_replace(home / "config.yaml", config)
    entered, release = threading.Event(), threading.Event()
    def slow(url, **kw):
        entered.set();assert release.wait(2);return post(url, **kw)
    monkeypatch.setattr(requests, "post", slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(wt.web_search_tool, "flight", 3)
        assert entered.wait(2)
        two = pool.submit(wt.web_search_tool, "flight", 8)
        release.set()
        assert len(json.loads(one.result(2))["data"]["web"]) == 3
        assert len(json.loads(two.result(2))["data"]["web"]) == 8
    assert len(calls) == 1


def test_outage_exact_payload_once_no_rescue_or_error_cache(native, monkeypatch):
    _, _, calls, _ = native
    def fail(url, **kw):
        calls.append((url,kw));raise requests.ConnectionError("synthetic provider unavailable")
    monkeypatch.setattr(requests, "post", fail)
    result = json.loads(wt.web_search_tool("outage", 3))
    assert not result["success"] and "synthetic provider unavailable" in result["error"]
    assert len(calls) == 1 and calls[0][0] == mcp.EXA_MCP_URL
    assert calls[0][1]["json"]["params"]["arguments"]["numResults"] == 3
    assert cache.search_memo.lookup("exa", "outage", 3) is None


def test_paid_exact_limit_and_failure_remains_paid(native, monkeypatch):
    config, home, calls, _ = native
    config["web"].update(keyless_fallback=False, provider_tier={"exa":"paid"})
    atomic_config_replace(home / "config.yaml", config)
    seen = []
    class Client:
        def search(self, query, **kw):
            seen.append(kw)
            if query == "outage": raise RuntimeError("synthetic paid failure")
            return SimpleNamespace(results=[SimpleNamespace(url="https://example.com/source", title="Source", highlights=["native"])])
    monkeypatch.setattr(exa, "_get_exa_client", lambda: Client())
    assert json.loads(wt.web_search_tool("paid",3))["success"]
    assert not json.loads(wt.web_search_tool("outage",3))["success"]
    assert [x["num_results"] for x in seen] == [3,3] and calls == []


def test_native_extract_source_observation_is_separate(native, monkeypatch):
    _, _, calls, _ = native
    async def safe(url): return True  # synthetic public URL: no DNS in this offline fixture
    monkeypatch.setattr(wt, "async_is_safe_url", safe)
    value = json.loads(asyncio.run(wt.web_extract_tool(["https://example.com/source"])))
    assert "Document text read" in value["results"][0]["content"]
    assert calls[0][1]["json"]["params"]["name"] == "web_fetch_exa"
