"""Explicit native retrieval profiles; no credential or environment resolution.

These configure tools, not worker connectivity. Inference belongs to the caller.
Only options actually consumed by the pinned donors are emitted.
"""
from pathlib import Path


HERMES_PROFILES = ("disabled", "exa-paid", "exa-keyless")
DSH_PROFILES = ("disabled", "exa-paid", "exa-keyless")


def _profile(value, supported, options):
    if not isinstance(value, str) or value not in supported:
        raise ValueError("Unsupported explicit native web profile")
    if value == "disabled" and any(v is not None for v in options):
        raise ValueError("Web options require an explicitly enabled web profile")
    return value != "disabled"


def _bound(value, default, low, high):
    value = default if value is None else value
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Web option is outside the supported integer bounds")
    return value


def research_policy():
    """Trusted shipped policy; no user-selected file or interpolated content."""
    return (Path(__file__).resolve().parents[1] / "config/RESEARCH.md").read_text().strip()


def hermes_web_config(profile="disabled", *, extract_char_limit=None, extract_timeout=None):
    if not _profile(profile, HERMES_PROFILES, (extract_char_limit, extract_timeout)):
        return {}
    chars = _bound(extract_char_limit, 15000, 2000, 500000)
    timeout = _bound(extract_timeout, 30, 1, 120)
    # Even explicit free Exa normally walks a four-vendor ring. Pin every other
    # rung to paid so this profile attempts only Exa, once, with no rescue.
    keyless = profile == "exa-keyless"
    return {
        "toolsets": ["web"],
        # Gateway selection reads platform_toolsets, not the top-level CLI list.
        "platform_toolsets": {"cli": ["web"], "telegram": ["web"]},
        "web": {
            "backend": "exa", "search_backend": "exa", "extract_backend": "exa",
            "keyless_fallback": keyless, "keyless_rescue": False,
            "provider_tier": {"exa": "free" if keyless else "paid",
                              "parallel": "paid", "firecrawl": "paid", "keenable": "paid"},
            "extract_char_limit": chars, "extract_timeout": timeout,
            "cache_enabled": False,
        },
        "plugins": {"enabled": ["web/exa"],
                    "disabled": ["web/xai", "web/openai_native", "web/perplexity"]},
    }


def dsh_web_patch(profile="disabled", *, search_max_results=None, search_max_queries=None,
                  timeout_ms=None, fetch_max_chars=None, fetch_max_bytes=None):
    options = (search_max_results, search_max_queries, timeout_ms, fetch_max_chars, fetch_max_bytes)
    if not _profile(profile, DSH_PROFILES, options):
        return []
    results = _bound(search_max_results, 5, 1, 20)
    queries = _bound(search_max_queries, 2, 1, 4)
    timeout = _bound(timeout_ms, 30000, 1, 120000)
    chars = _bound(fetch_max_chars, 15000, 2000, 200000)
    size = _bound(fetch_max_bytes, 1000000, 1, 5000000)
    provider = ({"id": "web-search-exa", "name": "@deepseek-ai/dsh-web-search-exa",
                     "config": {"baseURL": "https://api.exa.ai", "searchType": "auto",
                                "numResults": results, "highlightsPerResult": 1}}
                if profile == "exa-paid" else
                {"id": "web-search-exa-keyless", "name": "/payload/friday-web-keyless.mjs",
                 "config": {"endpoint": "https://mcp.exa.ai/mcp?tools=web_search_exa",
                            "maxResults": results, "timeoutMs": min(timeout, 30000),
                            "maxResponseBytes": min(size, 1000000), "maxOutputChars": min(chars, 15000)}})
    return [
        {"id": "web", "config": {"searchProvider": "exa", "fetchProvider": "http"}},
        # Exa is absent from the base. A plain id/config patch would be skipped.
        {"insert": [provider]},
        {"id": "web-fetch-http", "disabled": False, "config": {
            "maxResponseBytes": size, "maxBodyChars": chars, "timeoutMs": timeout,
            "maxRedirects": 3,
        }},
        {"id": "tool-web", "disabled": False, "config": {
            "search": True, "fetch": True, "searchMaxResults": results,
            "searchMaxQueries": queries, "searchTimeoutMs": timeout,
            "fetchTimeoutMs": timeout, "fetchMaxOutputChars": chars,
        }},
    ]
