#!/usr/bin/env python3
"""Render an explicit temporary local Harness patch; never resolve credentials."""

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit

try:
    from tools.web_profile import dsh_web_patch
except ModuleNotFoundError:  # Direct script invocation from outside the repository.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from web_profile import dsh_web_patch


DISABLED_ROWS = (
    "llm-deepseek", "llm-deepseek-account", "deepseek-account",
    "session-title-llm", "web-search-deepseek", "tool-web", "tool-goal",
    "command-goal", "goal-round-driver", "tool-workflow",
)


def build_patch(*, purpose, api, base_url, model, context_window, max_tokens,
                summary_max_tokens, headroom_tokens,
                api_key_env=None, request_timeout_ms=30000, web_profile="disabled",
                web_search_max_results=None, web_search_max_queries=None, web_timeout_ms=None,
                web_fetch_max_chars=None, web_fetch_max_bytes=None):
    web = dsh_web_patch(web_profile, search_max_results=web_search_max_results,
                        search_max_queries=web_search_max_queries, timeout_ms=web_timeout_ms,
                        fetch_max_chars=web_fetch_max_chars, fetch_max_bytes=web_fetch_max_bytes)
    if purpose != "temporary-local-test":
        raise ValueError("An explicit temporary-local-test purpose is required")
    if api != "openai-completions":
        raise ValueError("Only the audited OpenAI chat completions protocol is admitted")
    if (not isinstance(base_url, str) or not base_url
            or any(ord(c) <= 32 or ord(c) == 127 for c in base_url)
            or "\\" in base_url or "%" in base_url):
        raise ValueError("Endpoint contains ambiguous characters")
    try:
        url = urlsplit(base_url)
        address = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except ValueError:
        raise ValueError("Endpoint must use an explicit local IP address") from None
    networks = tuple(ipaddress.ip_network(n) for n in
                     ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))
    local = address.is_loopback or any(address.version == n.version and address in n
                                      for n in networks)
    if (not local or url.scheme not in ("http", "https") or not port
            or url.username is not None or url.password is not None
            or url.query or url.fragment or url.path not in ("/v1", "/v1/")):
        raise ValueError("Expected a credential-free local /v1 endpoint with explicit port")
    if (not isinstance(model, str) or not model or len(model) > 256
            or model != model.strip() or model.lower() == "auto"
            or "REPLACE" in model or "${" in model
            or any(ord(c) < 32 or ord(c) == 127 for c in model)):
        raise ValueError("An exact explicit served model ID is required")
    for value in (context_window, max_tokens, summary_max_tokens, headroom_tokens, request_timeout_ms):
        if type(value) is not int or not 0 < value <= 2**31 - 1:
            raise ValueError("Capacities and request timeout must be positive integers")
    if max_tokens >= context_window:
        raise ValueError("Output reservation must leave input space in the context")
    if summary_max_tokens > max_tokens or max_tokens + headroom_tokens >= context_window:
        raise ValueError("Summary and headroom must fit the explicitly declared model capacities")
    # Match compaction-basic/config.ts with its unchanged native defaults.
    # Positive pressure alone is insufficient: the retained tail must fit below it.
    message_budget = context_window - max_tokens
    threshold = int(min(context_window * 0.8, message_budget - headroom_tokens))
    retained_tail = int(message_budget * 0.16)
    if retained_tail >= threshold:
        raise ValueError("Native compaction retention must fit below its pressure threshold")
    if api_key_env is not None and (
            not isinstance(api_key_env, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", api_key_env)
            or api_key_env in ("HOME", "PATH", "DSH_HOME")):
        raise ValueError("Credential input must be an environment variable name")
    route = {
        "api": api, "baseURL": base_url.rstrip("/"),
        "timeoutMs": request_timeout_ms,
        "models": [{"id": model, "contextWindow": context_window,
                    "maxTokens": max_tokens, "input": ["text"]}],
    }
    if api_key_env is not None:
        route["apiKeyEnv"] = api_key_env
    # Cordis replaces this entire row config, including the provider dictionary.
    return [
        {"id": "llm-pi-ai", "config": {"providers": {"friday-local": route}}},
        {"id": "agent-default-model", "config": {"provider": "friday-local", "model": model}},
        {"id": "compaction-basic", "config": {
            "summarizationProvider": "friday-local", "summarizationModel": model,
            "maxTokens": summary_max_tokens, "headroomTokens": headroom_tokens,
        }},
        *({"id": row, "disabled": True} for row in DISABLED_ROWS
          if not (web and row == "tool-web")),
        *web,
    ]


def publish_private(path, patch):
    """Publish a new private file atomically; preserve every existing destination."""
    path = Path(path).absolute()
    parent = path.parent
    if parent != parent.resolve(strict=True):
        raise ValueError("Output parent must not contain symlinks")
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("Output requires an owned private directory")
    data = (json.dumps(patch, ensure_ascii=False, indent=2) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=".dsh-profile-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # A link operation admits a destination only if it does not exist.
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return hashlib.sha256(data).hexdigest()


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # Do not repeat possibly sensitive argv values in validation errors.
        self.exit(2, "Invalid explicit profile inputs; see --help\n")


class Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("Repeated input")
        setattr(namespace, self.dest, values)


def main():
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    for name in ("purpose", "api", "base-url", "model", "context-window", "max-tokens",
                 "summary-max-tokens", "headroom-tokens", "output"):
        parser.add_argument("--" + name, required=True, action=Once)
    parser.add_argument("--api-key-env", action=Once)
    parser.add_argument("--request-timeout-ms", action=Once)
    parser.add_argument("--web-profile", action=Once,
                        help="disabled (default) or exa-paid; retrieval only")
    for name in ("web-search-max-results", "web-search-max-queries", "web-timeout-ms",
                 "web-fetch-max-chars", "web-fetch-max-bytes"):
        parser.add_argument("--" + name, action=Once)
    args = parser.parse_args()
    try:
        integer = {}
        for name in ("context_window", "max_tokens", "summary_max_tokens", "headroom_tokens",
                     "request_timeout_ms"):
            value = getattr(args, name) or "30000"
            if not re.fullmatch(r"[1-9][0-9]*", value):
                raise ValueError("An explicit positive decimal integer is required")
            integer[name] = int(value)
        for name in ("web_search_max_results", "web_search_max_queries", "web_timeout_ms",
                     "web_fetch_max_chars", "web_fetch_max_bytes"):
            value = getattr(args, name)
            if value is not None:
                if not re.fullmatch(r"[1-9][0-9]*", value):
                    raise ValueError("An explicit positive decimal integer is required")
                integer[name] = int(value)
        patch = build_patch(purpose=args.purpose, api=args.api, base_url=args.base_url,
                            model=args.model, api_key_env=args.api_key_env,
                            web_profile="disabled" if args.web_profile is None else args.web_profile,
                            **integer)
        sha = publish_private(args.output, patch)
    except (OSError, ValueError):
        parser.exit(2, "Profile rendering refused; inputs/output must satisfy the documented contract\n")
    print(json.dumps({"sha256": sha, "purpose": "temporary-local-test",
                      "credentials": "reference-only", "inference": "NOT_RUN"}))


if __name__ == "__main__":
    main()
