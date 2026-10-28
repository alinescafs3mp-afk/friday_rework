"""Load an endpoint description. The file holds an env var name, not a secret."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from qpb.atomic import read_json


class EndpointError(RuntimeError):
    pass


class MissingAPIKey(EndpointError):
    pass


def load_endpoint(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, dict):
        raise EndpointError("endpoint file must be an object")
    for banned in ("api_key", "authorization", "bearer", "token"):
        if banned in data:
            raise EndpointError(f"endpoint file must not contain {banned}")
    for key in ("base_url", "model", "api_key_env"):
        if not data.get(key):
            raise EndpointError(f"endpoint missing {key}")
    base = str(data["base_url"]).strip()
    if not base.rstrip("/").endswith("/v1"):
        raise EndpointError("base_url must be the API root ending in /v1")
    data["base_url"] = base.rstrip("/")
    data["live_checked"] = bool(data.get("live_checked", False))
    data.setdefault("kind", "model")
    if data["kind"] not in {"model", "fixture"}:
        raise EndpointError("endpoint kind must be model or fixture")
    return data


def alias(endpoint: dict) -> str:
    parts = urlsplit(endpoint["base_url"])
    host = parts.hostname or ""
    port = parts.port or ""
    return f"{host}:{port}{parts.path} model={endpoint['model']}"


def api_key(endpoint: dict) -> str:
    name = endpoint["api_key_env"]
    value = os.environ.get(name, "")
    if not value:
        raise MissingAPIKey(name)
    return value


def redact_headers(headers: dict) -> dict:
    cleaned = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            cleaned[key] = "REDACTED"
        else:
            cleaned[key] = value
    return cleaned
