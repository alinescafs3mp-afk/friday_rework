"""Explicit local A0 model data. Pure rendering is never network admission."""

from __future__ import annotations

import copy
import ipaddress
import re
from urllib.parse import urlsplit


class ProfileError(ValueError):
    pass


def require_profile(ok, code):
    if not ok:
        raise ProfileError(code)


def local_endpoint(value):
    require_profile(
        isinstance(value, str)
        and len(value) <= 256
        and not any(c.isspace() or ord(c) < 32 or c in "\\%" for c in value),
        "invalid_a0_endpoint",
    )
    try:
        u = urlsplit(value)
        ip = ipaddress.ip_address(u.hostname or "")
        # RFC1918/ULA only; ip.is_private also includes special-use addresses.
        ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
        allowed = any(ip in ipaddress.ip_network(n) for n in ranges)
        canonical_host = "[" + str(ip) + "]" if ip.version == 6 else str(ip)
        valid = (
            allowed
            and not ip.is_loopback
            and not ip.is_link_local
            and not ip.is_multicast
            and not ip.is_unspecified
            and u.scheme in ("http", "https")
            and u.port is not None
            and 1 <= u.port <= 65535
            and u.path == "/v1"
            and u.username is None
            and u.password is None
            and not u.query
            and not u.fragment
            and value == f"{u.scheme}://{canonical_host}:{u.port}/v1"
        )
    except ValueError:
        valid = False
    require_profile(valid, "nonlocal_a0_endpoint")
    return value


def legacy_profile(chat="http://192.168.1.78:8001/v1", embedding="http://192.168.1.78:8002/v1"):
    """Named temporary test preset; preserves original native Default bytes."""
    slot = dict(endpoint=chat, model="dispatcher", context_length=40960, max_output_tokens=4096, timeout=60)
    return dict(
        name="legacy-local-test",
        preset="Default",
        chat=slot,
        utility=copy.deepcopy(slot),
        embedding=dict(endpoint=embedding, model="qwen3-embedding-0.6b", context_length=0, timeout=30),
    )


def checked_profile(value):
    require_profile(
        isinstance(value, dict) and set(value) == {"name", "preset", "chat", "utility", "embedding"},
        "explicit_a0_profile_required",
    )
    for k in ("name", "preset"):
        require_profile(
            isinstance(value[k], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value[k]),
            "invalid_a0_profile_name",
        )
    require_profile(value["preset"] == "Default", "native_default_a0_preset_required")
    for kind in ("chat", "utility", "embedding"):
        slot = value[kind]
        fields = {"endpoint", "model", "context_length", "timeout"}
        if kind != "embedding":
            fields.add("max_output_tokens")
        require_profile(isinstance(slot, dict) and set(slot) == fields, "invalid_a0_model_slot")
        local_endpoint(slot["endpoint"])
        require_profile(
            isinstance(slot["model"], str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}", slot["model"])
            and slot["model"] != "auto",
            "explicit_a0_model_required",
        )
        require_profile(
            type(slot["timeout"]) is int and 1 <= slot["timeout"] <= 120, "invalid_a0_model_timeout"
        )
        minimum = 0 if kind == "embedding" else 1
        require_profile(
            type(slot["context_length"]) is int and minimum <= slot["context_length"] <= 2**31 - 1,
            "invalid_a0_context",
        )
        if kind != "embedding":
            require_profile(
                type(slot["max_output_tokens"]) is int
                and 0 < slot["max_output_tokens"] < slot["context_length"],
                "invalid_a0_output",
            )
    # Chat and utility may share an inference server. Embedding is a distinct
    # original credential/route slot, never a duplicate or a web-access route.
    inference = {value[k]["endpoint"] for k in ("chat", "utility")}
    require_profile(value["embedding"]["endpoint"] not in inference, "duplicate_a0_origin")
    origins = [(urlsplit(v).hostname, urlsplit(v).port) for v in inference | {value["embedding"]["endpoint"]}]
    require_profile(len(origins) == len(set(origins)), "duplicate_a0_origin")
    if value["name"] == "legacy-local-test":
        require_profile(
            value == legacy_profile(value["chat"]["endpoint"], value["embedding"]["endpoint"])
            and urlsplit(value["chat"]["endpoint"]).port == 8001
            and urlsplit(value["embedding"]["endpoint"]).port == 8002
            and value["chat"]["endpoint"].startswith("http://")
            and value["embedding"]["endpoint"].startswith("http://"),
            "legacy_a0_preset_changed",
        )
    return copy.deepcopy(value)


def endpoint_urls(profile):
    p = checked_profile(profile)
    return tuple(dict.fromkeys(p[k]["endpoint"] for k in ("chat", "utility", "embedding")))


def network_endpoints(profile):
    return [
        {"ip": urlsplit(url).hostname, "port": urlsplit(url).port, "transport": "tcp"}
        for url in endpoint_urls(profile)
    ]


def profile_templates(profile=None):
    p = checked_profile(legacy_profile() if profile is None else profile)
    models = {}
    for kind in ("chat", "utility"):
        s = p[kind]
        models[kind] = dict(
            provider="openai",
            name=s["model"],
            api_base=s["endpoint"],
            ctx_length=s["context_length"],
            vision=False,
            rl_requests=0,
            rl_input=0,
            rl_output=0,
            kwargs={"max_tokens": s["max_output_tokens"], "timeout": s["timeout"], "a0_api_mode": "chat"},
        )
        models[kind]["ctx_history" if kind == "chat" else "ctx_input"] = 0.7
    s = p["embedding"]
    models["embedding"] = dict(
        provider="other",
        name=s["model"],
        api_base=s["endpoint"],
        kwargs={"timeout": s["timeout"]},
        rl_requests=0,
        rl_input=0,
    )
    if s["context_length"]:
        models["embedding"]["ctx_length"] = s["context_length"]
    return {
        "plugins/_model_config/presets.yaml": [{"name": p["preset"], **models}],
        "plugins/_model_config/config.json": {"model_preset": p["preset"]},
        "plugins/_code_execution/config.json": {"ssh_enabled": "false"},
        "settings.json": {
            "agent_profile": "agent0",
            "workdir_path": "/a0/usr/workdir",
            "uvicorn_access_logs_enabled": False,
        },
    }
