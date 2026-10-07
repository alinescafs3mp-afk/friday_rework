"""Render an explicit temporary local profile through Hermes' native writer.

Run with the PM-owned Hermes interpreter. The bounded_context extension must
be applied and accepted before this profile can construct an agent.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit

try:
    from tools.web_profile import hermes_web_config, research_policy
except ModuleNotFoundError:  # Direct script invocation from outside the repository.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from web_profile import hermes_web_config, research_policy

ROOT = Path(__file__).resolve().parents[1]


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Profile rendering refused; see --help for explicit inputs and private output rules\n")


class Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("Repeated input")
        setattr(namespace, self.dest, values)


def build_config(*, base_url, model, key_env, context, max_input,
                 main_output, summary_output, margin, template_overhead,
                 web_profile="disabled", web_extract_char_limit=None, web_extract_timeout=None):
    web = hermes_web_config(web_profile, extract_char_limit=web_extract_char_limit,
                            extract_timeout=web_extract_timeout)
    values = (context, max_input, main_output, summary_output, margin, template_overhead)
    if any(type(v) is not int or v <= 0 for v in values):
        raise ValueError("Every capacity/reservation must be an explicit positive integer")
    if max_input > context:
        raise ValueError("Input ceiling cannot exceed the real context")
    budget = min(max_input, context - max(main_output, summary_output)) - margin - template_overhead
    if budget <= 0:
        raise ValueError("Output and overhead reservations leave no usable input")
    if not isinstance(base_url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in base_url):
        raise ValueError("URL must not contain whitespace or control characters")
    url = urlsplit(base_url)
    try:
        address = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except ValueError as exc:
        raise ValueError("Use a verified literal local server address") from exc
    networks = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    local = address.is_loopback or any(address.version == n.version and address in n for n in networks)
    if (not local or url.scheme not in ("http", "https") or not port
            or url.username is not None or url.password is not None or url.query or url.fragment
            or url.path.rstrip("/") != "/v1"):
        raise ValueError("Expected a credential-free local OpenAI-compatible /v1 URL")
    if (not isinstance(model, str) or not model.strip() or model != model.strip()
            or model.lower() == "auto" or "${" in model
            or any(ord(c) < 32 or ord(c) == 127 for c in model)):
        raise ValueError("An exact observed served model ID is required")
    if not isinstance(key_env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key_env):
        raise ValueError("Provide the name of an existing credential environment variable")
    base_url = base_url.rstrip("/")
    provider = "custom:friday-local"
    route = {"provider": provider, "model": model, "base_url": base_url,
             "key_env": key_env, "api_mode": "chat_completions", "fallback_chain": []}
    auxiliary = {name: {**route, "fallback_chain": []} for name in (
        "compression", "vision", "approval", "skills_hub", "mcp", "title_generation",
        "background_review", "review")}
    auxiliary["compression"].update(context_length=context, extra_body={"max_tokens": summary_output})
    auxiliary["title_generation"].update(enabled=False, model_upgrade_enabled=False)
    auxiliary["background_review"]["enabled"] = False
    auxiliary["transient_retries"] = 0
    config = {
        "model": {"provider": provider, "default": model, "base_url": base_url,
                  "api_mode": "chat_completions", "context_length": context},
        "providers": {"friday-local": {
            "api": base_url, "key_env": key_env, "transport": "chat_completions",
            "default_model": model, "discover_models": False,
            "request_timeout_seconds": 30,
            "models": {model: {"context_length": context, "bounded_context": {
                "mode": "local_test", "server_max_input_tokens": max_input,
                "main_max_output_tokens": main_output,
                "compression_max_output_tokens": summary_output,
                "safety_margin_tokens": margin, "template_overhead_tokens": template_overhead,
            }}},
        }},
        "fallback_providers": [], "fallback_model": {},
        "agent": {"api_max_retries": 1, "auto_recovery_cycles": 0},
        "compression": {"enabled": True, "threshold_tokens": max(1, budget * 3 // 4)},
        "auxiliary": auxiliary,
        "approvals": {"mode": "manual", "single_query_mode": "deny", "unattended_mode": "deny"},
        "memory": {"memory_enabled": False, "user_profile_enabled": False, "provider": ""},
        "curator": {"enabled": False},
        "skills": {"external_dirs": [], "project_discovery": False, "trusted_project_dirs": [],
                   "auto_load": [], "inline_shell": False},
        "mcp_servers": {}, "mcp": {"auto_reload_on_config_change": False},
        "toolsets": [], "tools": {"tool_search": {"enabled": "off"}},
        "delegation": {"provider": provider, "model": model, "api_mode": "chat_completions",
                       "fallback_providers": []},
    }
    if web:
        config.update(web)
        # Native additive environment prose survives personality selection.
        # Leave SOUL, display.personality and agent.system_prompt untouched.
        config["agent"]["environment_hint"] = research_policy()
    return config


def read_owned_file(path, *, private=False):
    """Read without following links; backups must be independent private files."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or (private and (before.st_mode & 0o077 or before.st_nlink != 1))):
            raise ValueError("Expected an owned regular file with safe backup permissions")
        data = handle.read(16 * 1024 * 1024 + 1)
        after = os.fstat(handle.fileno())
        stable = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(data) > 16 * 1024 * 1024 or any(getattr(before, k) != getattr(after, k) for k in stable):
            raise ValueError("Config file changed during read or exceeds the size bound")
        return data


def main():
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--hermes-source", type=Path, default=ROOT / ".donors/hermes")
    for name in ("base-url", "model", "key-env"):
        parser.add_argument("--" + name, required=True)
    for name in ("context", "max-input", "main-output", "summary-output", "margin", "template-overhead"):
        parser.add_argument("--" + name, required=True, type=int)
    parser.add_argument("--expected-config-sha256", help="Required to replace an existing owned config")
    parser.add_argument("--web-profile", action=Once,
                        help="disabled (default), exa-paid, or exa-keyless; retrieval only")
    parser.add_argument("--web-extract-char-limit", type=int, action=Once)
    parser.add_argument("--web-extract-timeout", type=int, action=Once)
    args = parser.parse_args()
    home = args.home.absolute()
    if home.resolve() != home or not home.is_relative_to(ROOT / ".runtime"):
        parser.error("Test home must be a real path beneath this workspace's .runtime")
    args.web_profile = "disabled" if args.web_profile is None else args.web_profile
    try:
        config = build_config(**{k: getattr(args, k) for k in (
            "base_url", "model", "key_env", "context", "max_input", "main_output",
            "summary_output", "margin", "template_overhead", "web_profile",
            "web_extract_char_limit", "web_extract_timeout")})
    except ValueError:
        parser.error("Invalid explicit profile")
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    if home.stat().st_uid != os.getuid() or home.stat().st_mode & 0o077:
        parser.error("Test home must be owner-private")
    path = home / "config.yaml"
    before = None
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
            parser.error("Existing config must be an owned regular file")
        before = read_owned_file(path)
        digest = hashlib.sha256(before).hexdigest()
        if digest != args.expected_config_sha256:
            parser.error("Existing config changed or no expected hash was supplied")
        backup = home / ("config.before." + digest + ".yaml")
        if not backup.exists() and not backup.is_symlink():
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(before)
                handle.flush()
                os.fsync(handle.fileno())
        try:
            if read_owned_file(backup, private=True) != before:
                parser.error("Existing backup does not match")
        except (OSError, ValueError) as exc:
            parser.error("Existing backup is unsafe: " + str(exc))
    os.environ["HERMES_HOME"] = str(home)
    os.environ["HERMES_SAFE_MODE"] = "1"
    sys.path.insert(0, str(args.hermes_source.resolve(strict=True)))
    from hermes_cli.config import atomic_config_replace
    if before is not None and read_owned_file(path) != before:
        parser.error("Concurrent config edit; replacement refused")
    atomic_config_replace(path, config)
    print(json.dumps({"config": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "profile": "temporary_local_test", "runtime_acceptance": "NOT_RUN"}))


if __name__ == "__main__":
    main()
