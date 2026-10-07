"""Finite native Hermes research driver, prepared source only.

The trusted parent must already own the original task, an exclusive lease and
the existing supervised process. This module neither launches nor grants one.
Call it in that dedicated process, never inside a concurrent gateway. Importing
the file is inert. There is deliberately no command that can self-authorize.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
from collections import deque
import copy
from dataclasses import dataclass
import hashlib
import ipaddress
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import runpy
import stat
import sys
import time
import threading
from urllib.parse import urlsplit


class Refused(RuntimeError):
    """Categorical only: never include native exception text or credentials."""


def _require(ok, reason):
    if not ok:
        raise Refused(reason)


def _read(pin):
    _require(isinstance(pin, dict) and set(pin) == {"path", "sha256"}, "invalid_pin")
    p = Path(pin["path"])
    _require(p.is_absolute() and p.resolve() == p, "unsafe_pin_path")
    _require(isinstance(pin["sha256"], str) and re.fullmatch("[0-9a-f]{64}", pin["sha256"]), "invalid_pin_hash")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid(), "unsafe_pin_file")
        data = handle.read(16 * 1024**2 + 1)
        after = os.fstat(handle.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")
    _require(len(data) <= 16 * 1024**2 and all(getattr(before, k) == getattr(after, k) for k in fields), "pin_read_race")
    _require(hashlib.sha256(data).hexdigest() == pin["sha256"], "pin_changed")
    return data


def _local(url):
    _require(isinstance(url, str) and not any(ord(c) <= 32 or ord(c) == 127 for c in url), "invalid_endpoint")
    value = urlsplit(url)
    try:
        address = ipaddress.ip_address(value.hostname or "")
        port = value.port
    except ValueError:
        raise Refused("literal_local_endpoint_required") from None
    private = (address.is_loopback or any(address in ipaddress.ip_network(n) for n in
               (("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16") if address.version == 4 else ())))
    _require(private and value.scheme in {"http", "https"} and port and value.path.rstrip("/") == "/v1"
             and not value.username and not value.password and not value.query and not value.fragment,
             "literal_local_endpoint_required")


def _emitted_options(expected, actual):
    """Native load_config merges defaults; compare every emitted option exactly.

    Native defaults such as cache TTL and unserved platform rows need not be
    falsely reported as drift. Explicit selection/toolsets/tier/rescue remain
    pinned, including their full list values.
    """
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _emitted_options(v, actual[k]) for k,v in expected.items())
    return type(expected) is type(actual) and expected == actual


def validation_profile(config, native_defaults):
    """Source-only delta over the published temporary renderer.

    Native load_config adds other auto auxiliary tasks. In this bounded research
    fixture every model-capable auxiliary row must explicitly use the same local
    route, rather than depending on the absence of cloud credentials. The parent
    writes this returned value via the existing atomic_config_replace into a NEW
    private validation home, then pins the actual bytes. No write happens here.
    Native task names come from the pinned donor defaults; models/capacities do
    not become permanent values. Whole product startup remains separate.
    """
    result = copy.deepcopy(config)
    model = result["model"]
    _local(model["base_url"])
    _require(model["provider"] == "custom:friday-local", "explicit_local_provider_required")
    key = result["providers"]["friday-local"]["key_env"]
    _require(isinstance(key,str) and re.fullmatch("[A-Z][A-Z0-9_]*",key), "invalid_local_credential_reference")
    route = {"provider":model["provider"], "model":model["default"], "base_url":model["base_url"],
             "key_env":key, "api_key":"", "api_mode":"chat_completions", "fallback_chain":[]}
    for name,row in native_defaults["auxiliary"].items():
        if isinstance(row,dict) and "provider" in row:
            result["auxiliary"].setdefault(name,{}).update(copy.deepcopy(route))
    result["auxiliary"]["transient_retries"] = 0
    return result


PROMPTS = {
    "ordinary": 'Подготовь конфигурацию urllib3 Retry для текущего стабильного API: максимум два повтора, '
                'только GET: HTTP 503, а HTTP 413/429 только при наличии Retry-After; учитывать Retry-After. '
                'Не повторять POST или другие статусы. Верни JSON с полями total, allowed_methods, '
                'status_forcelist, respect_retry_after_header, sources (URL). '
                'Если текущий API подтвердить нельзя, явно укажи неопределённость вместо догадки.',
    "explicit": 'Исследуй текущую официальную документацию urllib3 Retry, найди и прочитай первичные источники. '
                'Подготовь конфигурацию: максимум два повтора, только GET: HTTP 503, а HTTP 413/429 только '
                'при наличии Retry-After; учитывать Retry-After. Не повторять POST или другие статусы. '
                'Верни JSON с полями total, allowed_methods, status_forcelist, respect_retry_after_header, '
                'sources (URL). Если источник недоступен, сообщи об этом честно.',
}


@dataclass(frozen=True)
class OriginalTask:
    """Constructed by the trusted parent from original admission, never model input."""
    task_id: str
    accepted_monotonic: float
    accepted_wall: float
    budget_seconds: float
    boot_id: str
    plan_sha256: str

    def remaining(self, *, mono=time.monotonic, wall=time.time, boot=None):
        boot = boot or Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        _require(boot == self.boot_id, "original_boot_changed")
        values = (self.accepted_monotonic, self.accepted_wall, self.budget_seconds)
        _require(all(type(v) in (int, float) and math.isfinite(v) for v in values)
                 and self.budget_seconds > 0, "invalid_original_clock")
        now_m, now_w = mono(), wall()
        _require(now_m >= self.accepted_monotonic and now_w >= self.accepted_wall, "original_clock_reversed")
        remaining = min(self.accepted_monotonic + self.budget_seconds - now_m,
                        self.accepted_wall + self.budget_seconds - now_w)
        _require(remaining > 5, "original_deadline_exhausted")
        return remaining - 5  # native cleanup reservation; never reset on continuation


def verify_plan(plan, task):
    """Nonsecret finite validation recipe, not another task/authorization store."""
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    _require(hashlib.sha256(encoded).hexdigest() == task.plan_sha256, "original_plan_mismatch")
    required = {"task_id", "mode", "source", "source_files", "profile", "soul", "policy", "driver", "web_profile_source",
                "inference_endpoint", "web_profile", "max_iterations", "workspace", "output"}
    _require(set(plan) == required and plan["task_id"] == task.task_id and plan["mode"] in PROMPTS,
             "invalid_original_plan")
    _require(plan["web_profile"] in {"exa-paid", "exa-keyless"}, "explicit_web_profile_required")
    _require(type(plan["max_iterations"]) is int and 1 <= plan["max_iterations"] <= 8, "invalid_iterations")
    _local(plan["inference_endpoint"])
    root = Path(plan["source"])
    _require(root.is_absolute() and root.resolve() == root and root.is_dir(), "unsafe_source")
    _require(isinstance(plan["source_files"], dict) and plan["source_files"], "candidate_pins_required")
    mandatory = {"run_agent.py", "agent/agent_init.py", "agent/prompt_builder.py", "agent/system_prompt.py",
                 "agent/secret_scope.py", "hermes_cli/runtime_provider.py", "tools/web_tools.py",
                 "tools/web_result_cache.py", "plugins/web/exa/provider.py", "plugins/web/keyless_mcp.py",
                 "hermes_cli/config_defaults.py", "agent/session_persistence.py", "agent/tool_executor.py",
                 "tools/web_tools_truncate.py", "tools/tool_result_storage.py", "hermes_logging.py",
                 "agent/redact.py", "agent/agent_runtime_helpers.py", "agent/stream_delivery.py", "agent/chat_completion_helpers.py", "agent/conversation_loop.py", "agent/turn_context.py", "agent/turn_finalizer.py", "agent/turn_facade.py", "agent/turn_tool_round.py",
                 "agent/message_sanitization.py", "agent/turn_recovery.py", "agent/turn_api_error.py",
                 "agent/client_lifecycle.py", "agent/credential_pool.py", "hermes_cli/runtime_provider_custom.py"}
    _require(mandatory <= set(plan["source_files"]), "native_candidate_pins_incomplete")
    for rel, digest in plan["source_files"].items():
        p = root / rel
        _require(p.resolve().is_relative_to(root), "candidate_path_escape")
        _read({"path": str(p), "sha256": digest})
    for name in ("profile", "soul", "policy", "driver", "web_profile_source"):
        _read(plan[name])
    _require(Path(plan["soul"]["path"]) == Path(plan["profile"]["path"]).parent / "SOUL.md", "wrong_profile_soul")
    _require(Path(plan["profile"]["path"]).name == "config.yaml", "wrong_profile_file")
    _require(Path(plan["driver"]["path"]).resolve() == Path(__file__).resolve(), "wrong_driver")
    _require(Path(plan["web_profile_source"]["path"]) == Path(__file__).resolve().parents[1] / "tools/web_profile.py", "wrong_profile_renderer")
    for name in ("workspace", "output"):
        p = Path(plan[name]); _require(p.is_absolute() and p.resolve() == p and p.is_dir(), "unsafe_private_directory")
        _require(p.stat().st_uid == os.getuid() and not p.stat().st_mode & 0o077, "private_directory_required")
    home = Path(plan["profile"]["path"]).parent
    _require(not home.stat().st_mode & 0o077 and home.stat().st_uid == os.getuid(), "private_profile_required")
    _require(not any(os.path.lexists(home / name) for name in (".env", "auth.json")),
             "fresh_credential_profile_required")
    _require(not (Path(plan["output"]) / "observation.json").exists(), "observation_already_exists_no_replay")


@contextmanager
def _clean_environment(home):
    old = dict(os.environ)
    # Native scoped resolver owns credentials. No ambient provider/proxy/policy
    # overrides, cloud routes, other home's dotenv or telemetry flags survive.
    os.environ.clear()
    os.environ.update(PATH="/usr/bin:/bin", LANG="C.UTF-8", HOME=str(home.parent), HERMES_HOME=str(home),
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        yield
    finally:
        os.environ.clear(); os.environ.update(old)


class Native:
    """Pinned Hermes mechanisms, lazy imports after environment admission."""
    def observe(self, callback):
        self.observer = callback

    def _tool_complete(self, call_id, name, args, result):
        try:
            self.observer({"messages": [
                {"role": "assistant", "tool_calls": [{"id": call_id, "function": {
                    "name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]},
                {"role": "tool", "tool_call_id": call_id, "name": name, "content": result}]})
        except Exception:
            # Native callbacks swallow Exception. Retain the failure and ask
            # its existing interrupt mechanism to stop; never report success.
            self.observation_failed = True
            self.agent.interrupt("observation_persistence_failed")
            raise

    def _stream_delta(self, text):
        # Native calls this AFTER its thinking/context scrubbers and writer fence.
        # Its own per-response text resets on retry; this bounded consumer does not.
        if getattr(self, "observation_failed", False):
            raise Refused("native_observation_already_failed")
        try:
            with self.stream_lock:
                _require(time.monotonic() < self.stream_deadline, "stream_observation_deadline")
                self.stream_callbacks += 1
                _require(self.stream_callbacks <= 4096 and isinstance(text, str)
                         and self.stream_input + len(text) <= 65536, "stream_observation_limit")
                self.stream_input += len(text)
                addition = self.stream_redactor.feed(text)
                _require(len(self.stream_text) + len(addition) <= 16384, "stream_observation_limit")
                self.stream_text += addition
                now = time.monotonic()
                # First delivery is durable immediately; further snapshots are
                # coalesced, with a hard lifetime I/O cap and no timer/thread.
                if (self._stream_snapshot().strip() and
                        (self.stream_publications == 0 or self.stream_input - self.stream_published_input >= 512
                         or now - self.stream_published_at >= 0.25)):
                    _require(self.stream_publications < 256, "stream_observation_limit")
                    self.observer({"partial_response": self._stream_snapshot()})
                    self.stream_publications += 1
                    self.stream_published_input = self.stream_input
                    self.stream_published_at = now
                _require(time.monotonic() < self.stream_deadline, "stream_observation_deadline")
        except Exception:
            self.observation_failed = True
            self.agent.interrupt("observation_persistence_failed")
            raise

    def _stream_snapshot(self):
        return self.stream_text + self.stream_redactor.tail()

    def partial(self):
        # Never reconstruct from a native buffer that resets/retries or contains
        # raw partial credentials. Preserve the last consumer snapshot instead.
        text = ""
        if hasattr(self, "stream_lock"):
            with self.stream_lock:
                text = self._stream_snapshot()
        return {"messages": getattr(getattr(self, "agent", None), "_session_messages", []),
                "partial_response": text}

    def open(self, plan, secrets, remaining):
        # remaining derives from the original task; construction and callbacks
        # share this deadline. No fresh per-token/per-retry allocation.
        self.stream_deadline = time.monotonic() + remaining
        self.stream_lock = threading.RLock()
        self.stream_text = ""
        self.stream_input = self.stream_callbacks = self.stream_publications = 0
        self.stream_published_input = 0
        self.stream_published_at = 0.0
        source = Path(plan["source"])
        self.old_path = list(sys.path)
        # A dedicated supervised process is required; never mix another
        # already-imported donor with this pinned candidate.
        for name in ("run_agent", "hermes_cli", "agent", "tools", "plugins"):
            existing = sys.modules.get(name)
            path = getattr(existing, "__file__", None)
            _require(not path or Path(path).resolve().is_relative_to(source), "foreign_native_module_loaded")
        sys.path.insert(0, str(source))
        from agent.secret_scope import set_secret_scope, set_multiplex_context
        self.tokens = []
        home = str(Path(plan["profile"]["path"]).parent)
        self.tokens.append(("multiplex", set_multiplex_context(True)))
        self.tokens.append(("scope", set_secret_scope(secrets, profile_home=home)))
        from hermes_constants import get_hermes_home
        _require(str(get_hermes_home().resolve()) == home, "native_profile_home_mismatch")
        from hermes_cli.config import load_config
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from run_agent import AIAgent
        config = load_config()
        model = config["model"]
        _require(model["provider"] == "custom:friday-local" and model["base_url"].rstrip("/") == plan["inference_endpoint"].rstrip("/"), "profile_inference_route_mismatch")
        _require(not config.get("fallback_providers") and not config.get("fallback_model")
                 and config.get("agent", {}).get("auto_recovery_cycles") == 0, "inference_fallback_refused")
        hermes_web_config = runpy.run_path(plan["web_profile_source"]["path"])["hermes_web_config"]
        expected = hermes_web_config(plan["web_profile"],
                        extract_char_limit=config["web"].get("extract_char_limit"),
                        extract_timeout=config["web"].get("extract_timeout"))
        _require(_emitted_options(expected, config), "native_web_configuration_mismatch")
        policy = _read(plan["policy"]).decode().strip()
        _require(config["agent"].get("environment_hint") == policy, "research_policy_mismatch")
        for name, row in config["auxiliary"].items():
            if isinstance(row, dict):
                _require(row.get("provider") == model["provider"] and row.get("base_url") == model["base_url"]
                         and row.get("model") == model["default"] and not row.get("fallback_chain"), "auxiliary_cloud_route_refused")
        key_name = config["providers"]["friday-local"]["key_env"]
        provider = config["providers"]["friday-local"]
        _require(not provider.get("key_cmd") and not provider.get("api_key"), "static_scoped_credential_required")
        required_keys = {key_name} | ({"EXA_API_KEY"} if plan["web_profile"] == "exa-paid" else set())
        _require(set(secrets) == required_keys, "wrong_scoped_credential_set")
        runtime = resolve_runtime_provider(requested=model["provider"], target_model=model["default"])
        _require(runtime["base_url"].rstrip("/") == plan["inference_endpoint"].rstrip("/")
                 and runtime["api_mode"] == "chat_completions" and runtime["provider"] == "custom",
                 "native_runtime_route_mismatch")
        _require(isinstance(runtime["api_key"], str), "static_scoped_credential_required")
        # Pin and use the native transformation itself. This private key_env
        # profile has no dotenv/pool/fallback/dynamic credential source. Refresh
        # resolves the scoped stripped value, Unicode repair removes non-ASCII,
        # and primary recovery restores the constructor snapshot. Both operations
        # are idempotent; retain every original as well as this finite closure.
        from agent.message_sanitization import _strip_non_ascii
        self.secrets = tuple(secrets.values())
        runtime_values = (runtime["api_key"], secrets[key_name].strip())
        self.credential_policy = _CredentialPolicy.create(self.secrets,
            (*runtime_values, *(_strip_non_ascii(value) for value in runtime_values)))
        # Supported native no-store mode: no SQLite, WAL, transcript divert or
        # trajectory. The driver retains only bounded redacted observations.
        # Long web_extract pages still spill with cache_enabled=False. Scrub at
        # that actual native persistence seam BEFORE it sees content or URL.
        from tools import web_tools_truncate
        self.spill_module = web_tools_truncate
        self.old_spill = web_tools_truncate._store_full_text
        self.stream_redactor = _SecretPrefixRedactor(self.credential_policy)
        # Native 4xx request dumps invoke redact_sensitive_text(force=True)
        # even when verbose logging and trajectories are disabled. Use its
        # supported profile-scoped exact-value registry for arbitrary secrets,
        # including their JSON-escaped representations, before any SDK call.
        from agent.redact import register_vault_redaction_value, clear_vault_redaction_values
        self.clear_redactions = clear_vault_redaction_values
        # The native exact registry uses sequential replacement. A full match
        # can consume the beginning of an overlapping credential before the
        # later JSON sink sees it. Conceal their union at that earlier boundary.
        # The supervised donor process is dedicated, and the hook applies only
        # to this authenticated profile; native policy for other homes remains.
        from agent import redact as native_redact
        self.redact_module = native_redact
        self.old_registered_redact = native_redact.redact_registered_vault_values
        original_registered_redact = self.old_registered_redact
        def redact_before_native_registry(text):
            if isinstance(text, str) and str(get_hermes_home().resolve()) == home:
                text = _redact(text, self.credential_policy)
            return original_registered_redact(text)
        self.registered_redactor = redact_before_native_registry
        native_redact.redact_registered_vault_values = self.registered_redactor
        # Exa's native keyless parser normalizes lines and later truncates
        # content. Conceal the complete decoded envelope before either loss,
        # including HTTP/MCP errors, rather than guessing normalized secrets.
        from plugins.web import keyless_mcp
        self.keyless_module = keyless_mcp
        self.old_response_text = keyless_mcp._response_text
        original_response_text = self.old_response_text
        def redact_web_response(response):
            text = original_response_text(response)
            if str(get_hermes_home().resolve()) == home:
                text = _redact(text, self.credential_policy)
            return text
        self.response_redactor = redact_web_response
        keyless_mcp._response_text = self.response_redactor
        for form in _secret_forms(self.credential_policy):
            register_vault_redaction_value(form)
        web_tools_truncate._store_full_text = lambda url, content: self.old_spill(
            _redact(url, self.credential_policy), _redact(content, self.credential_policy))
        from tools import tool_result_storage
        self.result_storage = tool_result_storage
        self.old_result_spill = tool_result_storage._write_to_spillover
        tool_result_storage._write_to_spillover = lambda content, filename: self.old_result_spill(
            _redact(content, self.credential_policy), _redact(filename, self.credential_policy))
        # A partial-delivery stub may enter a later 4xx request dump. Its
        # incomplete prefixes are absent from the native exact-value registry.
        # Scrub the actual native JSON persistence seam too, restoring on close.
        from agent import agent_runtime_helpers
        self.runtime_helpers = agent_runtime_helpers
        self.old_debug_write = agent_runtime_helpers.atomic_json_write
        agent_runtime_helpers.atomic_json_write = lambda path, value, **kw: self.old_debug_write(
            path, _bounded_public(value, self.credential_policy), **kw)
        self.agent = AIAgent(model=model["default"], base_url=runtime["base_url"], api_key=runtime["api_key"],
            provider=runtime["provider"], api_mode=runtime["api_mode"], requested_provider=model["provider"],
            max_iterations=plan["max_iterations"], enabled_toolsets=["web"], skip_context_files=True,
            load_soul_identity=True, skip_memory=True, skip_background_review=True, quiet_mode=True,
            session_db=None, save_trajectories=False, verbose_logging=False,
            tool_complete_callback=self._tool_complete,
            session_id=plan["task_id"], run_budget_seconds=remaining,
            fallback_model={}, cwd=plan["workspace"])
        # Native Unicode recovery may replace the live client key. Diagnostic
        # authorization needs no credential prefix/suffix, original or changed.
        # Scope this to the owned agent and never invoke callable credentials.
        self.had_debug_mask = "_mask_api_key_for_logs" in vars(self.agent)
        self.old_debug_mask = vars(self.agent).get("_mask_api_key_for_logs")
        self.debug_mask = lambda key: ("<entra-id-bearer>" if callable(key) and not isinstance(key, str)
                                      else "[REDACTED]" if key else None)
        self.agent._mask_api_key_for_logs = self.debug_mask
        self.rendered_prompt = self.agent._build_system_prompt()
        _require(policy in self.rendered_prompt, "native_rendered_research_policy_missing")
        _require(_read(plan["soul"]).decode().strip() in self.rendered_prompt, "native_rendered_soul_missing")
        _require(set(self.agent.valid_tool_names) == {"web_search","web_extract"}, "native_effective_tools_mismatch")
        self.observation_metadata = {"model":model["default"], "inference_endpoint":runtime["base_url"],
             "profile_sha256":plan["profile"]["sha256"], "soul_sha256":plan["soul"]["sha256"],
             "research_sha256":plan["policy"]["sha256"], "native_tools":sorted(self.agent.valid_tool_names),
             "rendered_prompt_sha256":hashlib.sha256(self.rendered_prompt.encode()).hexdigest()}
        return self

    def run(self, prompt):
        previous = self.agent._stream_callback
        try:
            result = self.agent.run_conversation(prompt, stream_callback=self._stream_delta)
            return {**result, "partial_response": self.partial()["partial_response"]}
        finally:
            # Native early-error exits can bypass its normal finalizer reset.
            self.agent._stream_callback = previous

    def close(self):
        # Close every acquired native object even after partial construction.
        errors = []
        for name in ("agent", "db"):
            value = getattr(self, name, None)
            if value is not None:
                try: value.close()
                except Exception: errors.append(name)
        if hasattr(self, "old_debug_mask"):
            if vars(self.agent).get("_mask_api_key_for_logs") is self.debug_mask:
                if self.had_debug_mask:
                    self.agent._mask_api_key_for_logs = self.old_debug_mask
                else:
                    del self.agent._mask_api_key_for_logs
                del self.old_debug_mask
            else:
                errors.append("native_debug_mask_ownership")
        if hasattr(self, "old_response_text"):
            if self.keyless_module._response_text is self.response_redactor:
                self.keyless_module._response_text = self.old_response_text
                del self.old_response_text
            else:
                errors.append("native_web_response_hook_ownership")
        if hasattr(self, "old_registered_redact"):
            if self.redact_module.redact_registered_vault_values is self.registered_redactor:
                self.redact_module.redact_registered_vault_values = self.old_registered_redact
                del self.old_registered_redact
            else:
                errors.append("native_redaction_hook_ownership")
        if hasattr(self, "clear_redactions"):
            try: self.clear_redactions()
            except Exception: errors.append("redaction_scope")
        if getattr(self, "tokens", []):
            from agent.secret_scope import reset_secret_scope, reset_multiplex_context
            for name, token in reversed(self.tokens):
                try: (reset_secret_scope if name == "scope" else reset_multiplex_context)(token)
                except Exception: errors.append("secret_scope")
        if hasattr(self, "old_path"):
            sys.path[:] = self.old_path
        if hasattr(self, "old_spill"):
            self.spill_module._store_full_text = self.old_spill
        if hasattr(self, "old_result_spill"):
            self.result_storage._write_to_spillover = self.old_result_spill
        if hasattr(self, "old_debug_write"):
            self.runtime_helpers.atomic_json_write = self.old_debug_write
        _require(not errors, "native_cleanup_unconfirmed")


def _repr_string_body(value, quote, ascii_only):
    # SDK status errors render a dict using Python repr, which chooses either
    # quote style from the whole surrounding message. Generate both styles:
    # a partial echo can choose a different quote than the complete credential.
    render = ascii if ascii_only else repr
    return "".join(("\\" + ch if ch == quote else ch) if ch in "\"'"
                   else render(ch)[1:-1] for ch in value)


def _secret_form_prefixes(secret_values):
    # Thresholds count eight ORIGINAL characters, not escaping characters.
    # Preserve raw + three JSON layers; also cover the actual SDK dict repr
    # at any one of those boundaries before the subsequent debug JSON dump.
    # Repeated arbitrary encodings are not unboundedly enumerated.
    states = {(value, False): len(value[:8]) for value in secret_values if value}
    forms = {value: length for (value, _), length in states.items()}
    for _ in range(3):
        for (value, has_repr), length in tuple(states.items()):
            for ascii_only in (False, True):
                pairs = [(json.dumps(value, ensure_ascii=ascii_only)[1:-1],
                          json.dumps(value[:length], ensure_ascii=ascii_only)[1:-1],
                          has_repr)]
                if not has_repr:
                    pairs += [(_repr_string_body(value, quote, ascii_only),
                               _repr_string_body(value[:length], quote, ascii_only), True)
                              for quote in ("'", '\"')]
                for escaped, prefix, repr_done in pairs:
                    states[escaped, repr_done] = min(
                        states.get((escaped, repr_done), len(prefix)), len(prefix))
                    forms[escaped] = min(forms.get(escaped, len(prefix)), len(prefix))
    return forms


@dataclass(frozen=True)
class _CredentialPolicy:
    """Original admission limits and a finite native runtime value closure.

    Derived credentials count against the existing form/character budget, not
    as additional user-supplied originals. No observer discovers keys lazily.
    """
    originals: tuple
    values: tuple

    @classmethod
    def create(cls, originals, reachable):
        originals = tuple(dict.fromkeys(originals))
        _require(all(isinstance(value, str) and value for value in originals),
                 "native_scoped_credentials_required")
        _require(len(originals) <= 8 and sum(map(len, originals)) <= 8192, "secret_redaction_limit")
        values = tuple(dict.fromkeys((*originals, *(value for value in reachable if value))))
        forms = _secret_form_prefixes(values)
        _require(len(forms) <= 64 and sum(map(len, forms)) <= 65536, "secret_redaction_limit")
        return cls(originals, values)


def _secret_forms(secret_values):
    values = secret_values.values if isinstance(secret_values, _CredentialPolicy) else secret_values
    return sorted(_secret_form_prefixes(values), key=len, reverse=True)


class _SecretPrefixRedactor:
    """Conceal the union of matches while retaining every overlapping start.

    Failure links retain suffix matches across full/meaningful matches, without
    rescanning or retaining their raw secret text. Only undecided short prefixes
    are buffered. A connected masked span becomes one marker; any complete
    credential in it upgrades that marker. Snapshots are non-destructive, so a
    mismatch, callback split or native retry cannot forget an overlapping start.
    """
    def __init__(self, secret_values):
        policy = secret_values if isinstance(secret_values, _CredentialPolicy) else None
        values = policy.values if policy else tuple(set(secret_values))
        originals = policy.originals if policy else values
        _require(len(originals) <= 8 and sum(map(len, originals)) <= 8192, "secret_redaction_limit")
        forms = _secret_form_prefixes(values)
        _require(len(forms) <= 64 and sum(map(len, forms)) <= 65536, "secret_redaction_limit")
        self.edges, self.fail, self.depth = [{}], [0], [0]
        self.mark, self.full = [0], [False]
        self.pending_limit = max(forms.values(), default=0)
        for form, threshold in forms.items():
            node = 0
            for index, ch in enumerate(form, 1):
                if ch not in self.edges[node]:
                    self.edges[node][ch] = len(self.edges)
                    self.edges.append({}); self.fail.append(0)
                    self.depth.append(index); self.mark.append(0); self.full.append(False)
                node = self.edges[node][ch]
                if index >= threshold:
                    self.mark[node] = index
            self.full[node] = True
        queue = deque(self.edges[0].values())
        while queue:
            parent = queue.popleft()
            suffix = self.fail[parent]
            self.mark[parent] = max(self.mark[parent], self.mark[suffix])
            self.full[parent] = self.full[parent] or self.full[suffix]
            for ch, child in self.edges[parent].items():
                fallback = suffix
                while fallback and ch not in self.edges[fallback]:
                    fallback = self.fail[fallback]
                self.fail[child] = self.edges[fallback].get(ch, 0)
                queue.append(child)
        self.node = 0
        self.pending = []
        self.masked = self.complete = False

    @staticmethod
    def _marker(complete):
        return "[REDACTED]" if complete else "[REDACTED_PARTIAL]"

    def tail(self, *, truncated=False):
        # Integer entries are masked positions, never raw credential tails.
        # Keep terminal flags in the pending span until its literals resolve.
        result = []
        masked, complete = self.masked, self.complete
        for item in self.pending:
            if not isinstance(item, str) or truncated:
                masked = True
                complete = complete or item == 1
            else:
                if masked:
                    result.append(self._marker(complete)); masked = complete = False
                result.append(item)
        if masked:
            result.append(self._marker(complete))
        return "".join(result)

    def feed(self, text):
        result = []
        for ch in text:
            while self.node and ch not in self.edges[self.node]:
                self.node = self.fail[self.node]
            self.node = self.edges[self.node].get(ch, 0)
            self.pending.append(ch)
            length = self.mark[self.node]
            if length:
                for index in range(max(0, len(self.pending) - length), len(self.pending)):
                    if isinstance(self.pending[index], str):
                        self.pending[index] = 0
                if self.full[self.node]:
                    self.pending[-1] = 1
            # Literals in the longest active prefix are still undecided. Masked
            # positions can be consumed immediately while automaton state alone
            # retains all starts, including starts inside the concealed span.
            safe = len(self.pending) - self.depth[self.node]
            consumed = 0
            for item in self.pending:
                if isinstance(item, str):
                    if consumed >= safe:
                        break
                    if self.masked:
                        result.append(self._marker(self.complete))
                        self.masked = self.complete = False
                    result.append(item)
                else:
                    self.masked = True
                    self.complete = self.complete or item == 1
                consumed += 1
            del self.pending[:consumed]
            _require(len(self.pending) < max(1, self.pending_limit), "secret_redaction_limit")
        return "".join(result)


def _redact(text, secret_values, *, truncated=False):
    scrubber = _SecretPrefixRedactor(secret_values)
    return scrubber.feed(text) + scrubber.tail(truncated=truncated)


@contextmanager
def _native_output_policy():
    """Dedicated-process policy: native logs/console have no persistence grant.

    Disable before imports/construction, including exception logs and close.
    Observations have their own redacted sink. Avoid buffering raw output.
    """
    class Discard(io.TextIOBase):
        def write(self, text): return len(text)
    previous = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        with redirect_stdout(Discard()), redirect_stderr(Discard()):
            yield
    finally:
        logging.disable(previous)


def _bounded_public(value, secret_values):
    """Bound input scanning, conceal cut prefixes, then cap public output."""
    def public(value):
        budget = 64 * 1024
        nodes = 1024
        truncated = False
        def clean(item, depth=0):
            nonlocal budget, nodes, truncated
            nodes -= 1
            if depth > 8 or nodes < 0:
                truncated = True
                return "[TRUNCATED]"
            if isinstance(item, str):
                allowed = min(16384, budget)
                if len(item) > allowed:
                    truncated = True
                item = _redact(item[:allowed], secret_values, truncated=len(item) > allowed)
                if len(item) > allowed:
                    item = item[:allowed] + "[TRUNCATED]"; truncated = True
                budget = max(0, budget - len(item))
                return item
            if isinstance(item, dict):
                truncated = truncated or len(item) > 32
                result = {}
                for k, v in list(item.items())[:32]:
                    truncated = truncated or len(k) > 256
                    key = _redact(k[:256], secret_values, truncated=len(k) > 256)
                    # Concealing secret-bearing keys must not silently discard
                    # their values when distinct keys map to the same marker.
                    unique = key
                    suffix = 2
                    while unique in result:
                        unique = key + f"[KEY_{suffix}]"
                        suffix += 1
                    result[unique] = clean(v, depth+1)
                return result
            if isinstance(item, list):
                truncated = truncated or len(item) > 32
                return [clean(v, depth+1) for v in item[:32]]
            return item
        value = clean(value)
        value["observation_truncated"] = truncated
        return value
    return public(value)


def _observation(result, secret_values):
    """Bounded public observations only. No thinking, raw prompt or exceptions."""
    messages = result.get("messages", [])
    tool_calls = [m.get("tool_calls") for m in messages if m.get("tool_calls")]
    # Tool messages are observed source data; no inference that the model used
    # them correctly. The independent verifier must join call IDs/URLs/text.
    tool_sources = [m for m in messages if m.get("role") == "tool"]
    _require(all(c.get("function", {}).get("name") in {"web_search", "web_extract"}
                 for batch in tool_calls for c in batch), "unexpected_tool_in_observation")
    value = _bounded_public({"final_response": result.get("final_response", ""),
                             "partial_response": result.get("partial_response", ""),
                             "tool_calls": tool_calls, "tool_source_observations": tool_sources}, secret_values)
    value.update(model_completed=result.get("completed") if type(result.get("completed")) is bool else None,
                 api_calls=result.get("api_calls") if type(result.get("api_calls")) is int else None,
                 uncertainty="Interpret source availability, accuracy and application independently",
                 status="OBSERVED_REQUIRES_INDEPENDENT_CHECK", journey_acceptance="NOT_CLAIMED")
    return value


class ExistingBoundary:
    """Read/settle the already owned systemd boundary; never launch a service.

    Only the trusted parent supplies current_association, scoped_credentials,
    confirm_remote_quiescence and the inherited exclusive FD. Current live
    production of this complete admission is NOT IMPLEMENTED/NOT ACCEPTED.
    The existing offline card permits testing these seams with synthetic state.
    """
    def __init__(self, *, current_association, associations, association_owner, supervisor, lock_fd, lock_pin,
                 scoped_credentials, verify_network_admission, confirm_remote_quiescence):
        self.current_association = current_association
        self.associations = associations
        self.association_owner = association_owner
        self.supervisor = supervisor
        self.lock_fd = lock_fd
        self.lock_pin = lock_pin
        self.scoped_credentials = scoped_credentials
        self.verify_network_admission = verify_network_admission
        self.confirm_remote_quiescence = confirm_remote_quiescence

    def admit(self, plan, task, remaining):
        import fcntl
        row = self.current_association()
        _require(row["existing_task_id"] == task.task_id and row["stop_intent"] is None
                 and row["budget_seconds"] == task.budget_seconds
                 and row["created_at_unix"] == task.accepted_wall
                 and row["deadline_unix"] == task.accepted_wall + task.budget_seconds,
                 "original_association_mismatch_or_stopped")
        observation = self.supervisor.observe(row)
        _require(not observation.quiescent and observation.main_pid == os.getpid()
                 and observation.active_state == "active" and observation.invocation_id,
                 "existing_owned_supervised_process_required")
        # NativeSupervisor already checks admission hash, invocation continuity,
        # transient status, foreign cgroup and whole-cgroup kill policy.
        group = Path("/proc/self/cgroup").read_text().strip()
        _require(group == "0::" + observation.control_group, "driver_outside_owned_cgroup")
        result = self.supervisor._command(["show", observation.unit,
                  "--property=RuntimeMaxUSec,ActiveEnterTimestampMonotonic"], 3)
        entries = [line.split("=", 1) for line in result.stdout.splitlines()]
        _require(all(len(x) == 2 for x in entries), "native_deadline_observation_required")
        fields = dict(entries)
        _require(result.returncode == 0 and len(entries) == len(fields) and set(fields) == {"RuntimeMaxUSec", "ActiveEnterTimestampMonotonic"},
                 "native_deadline_observation_required")
        # systemctl emits RuntimeMaxUSec as a timespan (e.g. 1min 30s), not a
        # guaranteed bare integer. Refuse unsupported forms without guessing.
        duration = fields["RuntimeMaxUSec"]
        parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(us|ms|min|h|s)", duration)
        _require(parts and " ".join(a+b for a,b in parts) == duration, "unsupported_native_deadline_format")
        scale = {"us":1e-6, "ms":1e-3, "s":1, "min":60, "h":3600}
        seconds = sum(float(a)*scale[b] for a,b in parts)
        start = fields["ActiveEnterTimestampMonotonic"]
        _require(start.isdigit() and int(start) > 0 and 0 < seconds <= task.budget_seconds
                 and int(start)/1e6 + seconds <= task.accepted_monotonic + task.budget_seconds,
                 "native_supervisor_extends_original_deadline")
        fd = self.lock_fd; value = os.fstat(fd); pin = self.lock_pin
        _require(stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid()
                 and (value.st_dev, value.st_ino) == (pin["device"], pin["inode"])
                 and Path(pin["path"]).resolve() == Path(pin["path"])
                 and (Path(pin["path"]).stat().st_dev,Path(pin["path"]).stat().st_ino) == (value.st_dev,value.st_ino),
                 "inherited_exclusive_lease_mismatch")
        # An inherited open-file description holds the parent's existing lock.
        # Never create a second lock or release it here.
        # fdinfo reports locks held by THIS open-file description. Observing a
        # busy path alone could belong to somebody else; acquiring a free lock
        # here would invent admission. Do neither.
        info = Path(f"/proc/self/fdinfo/{fd}").read_text()
        _require(any("FLOCK  ADVISORY  WRITE" in line and line.split()[-3].endswith(":" + str(value.st_ino))
                     for line in info.splitlines() if line.startswith("lock:")), "inherited_exclusive_lock_not_held")
        other = os.open(pin["path"], os.O_RDONLY | os.O_NOFOLLOW)
        try:
            try: fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: pass
            else: raise Refused("exclusive_lease_not_retained")
        finally: os.close(other)
        _require(self.verify_network_admission(plan,task), "current_original_network_admission_required")
        _require(self.current_association() == row, "association_changed_during_admission")
        self.row = row
        return self.scoped_credentials(plan)

    def consume(self, plan, task):
        """Use the original Association's one-way submission transition.

        The supervised wrapper is already active; the original research
        submission must still be NOT_SUBMITTED. No other worker's submitted row
        can authorize this run. An uncertain save/ack never permits execution.
        """
        _require(self.current_association() == self.row
                 and self.associations.get(task.task_id, self.association_owner) == self.row,
                 "original_association_changed_before_consume")
        consumed = self.associations.begin_submission(task.task_id, self.association_owner)
        expected = {**self.row, "submission_observation": "UNKNOWN"}
        _require(self.row.get("submission_observation") == "NOT_SUBMITTED"
                 and consumed == expected and self.current_association() == consumed,
                 "original_admission_consumption_unconfirmed")
        self.row = consumed

    def settle(self, plan, task):
        # The driver is still the supervised MainPID while this runs, so it
        # cannot attest its own terminal cgroup. Native object close plus remote
        # inference settlement is recorded; after process exit the parent MUST
        # observe the entire cgroup quiescent before releasing its own lease.
        return bool(self.confirm_remote_quiescence(plan, task))


def execute(plan, task, boundary, *, native=None, mono=time.monotonic, wall=time.time, boot=None):
    """One original task, no replay. Boundary is the trusted existing host seam.

    boundary.admit must independently prove the exact supervised current process,
    original durable admission/deadline, retained exclusive lock, clean runtime
    and reviewed web/model egress. It must return only native scoped credentials.
    boundary.consume MUST durably consume the original admission before effects,
    using the existing association's begin_submission transition. No live
    admission producer is claimed in this package.
    boundary.settle must reconcile remote inference. After this driver exits,
    the parent must observe the entire cgroup quiescent before releasing its
    lease. Neither agent.close nor an in-process callback proves cgroup stop.
    """
    verify_plan(plan, task)
    remaining = task.remaining(mono=mono, wall=wall, boot=boot)
    secrets = boundary.admit(plan, task, remaining)
    # A failed write/ack remains consumed or unknown; never guess it is unused.
    boundary.consume(plan, task)
    obj = native if native is not None else Native()
    record = {"task_id": task.task_id, "mode": plan["mode"], "input": PROMPTS[plan["mode"]],
              "plan_sha256": task.plan_sha256, "status": "RUNNING_OR_UNCERTAIN", "journey_acceptance": "NOT_CLAIMED",
              "original_admission":{"accepted_monotonic":task.accepted_monotonic,"accepted_wall":task.accepted_wall,
                  "budget_seconds":task.budget_seconds,"boot_id":task.boot_id}}
    failure = None
    capture_lock = threading.RLock()
    def capture(result, *, partial=False):
        with capture_lock:
            # The same precompiled value closure covers stream, callbacks,
            # retained/error results and all native persistence boundaries.
            policy = getattr(obj, "credential_policy", None)
            if policy is None:
                policy = (*secrets.values(), *getattr(obj, "secrets", ()))
            observed = _observation(result, policy)
            if partial:
                for key in ("tool_calls", "tool_source_observations"):
                    observed[key] = (record.get(key, []) + observed[key])[:32]
                if not observed['final_response']:
                    observed['final_response'] = record.get('final_response', '')
            else:
                for key in ("tool_calls", "tool_source_observations"):
                    if not observed[key]:observed[key] = record.get(key, [])
            if not observed['partial_response']:
                observed['partial_response'] = record.get('partial_response', '')
            bounded = _bounded_public({key: observed[key] for key in (
                'final_response', 'partial_response', 'tool_calls', 'tool_source_observations')},
                policy)
            bounded['observation_truncated'] |= observed['observation_truncated'] or record.get('observation_truncated', False)
            observed.update(bounded)
            observed["status"] = "RUNNING_OR_UNCERTAIN"
            record.update(observed)
            _publish(Path(plan["output"]) / "partial-observation.json", record, replace=True)
    with _clean_environment(Path(plan["profile"]["path"]).parent), _native_output_policy():
        try:
            _require(isinstance(secrets, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in secrets.items()), "native_scoped_credentials_required")
            _publish(Path(plan["output"]) / "partial-observation.json", record, replace=True)
            verify_plan(plan, task)  # recheck after bounded native admission I/O
            if hasattr(obj, "observe"):
                obj.observe(lambda result: capture(result, partial=True))
            obj.open(plan, secrets, task.remaining(mono=mono, wall=wall, boot=boot))
            record["native_input_observation"] = getattr(obj,"observation_metadata",{})
            _publish(Path(plan["output"]) / "partial-observation.json", record, replace=True)
            result = obj.run(PROMPTS[plan["mode"]])
            # Store returned evidence BEFORE deadline/stop classification.
            capture(result)
            _require(not getattr(obj, "observation_failed", False), "native_observation_persistence_failed")
            task.remaining(mono=mono, wall=wall, boot=boot)
            _require(result.get("completed") is True, "native_run_not_completed")
        except BaseException as exc:
            failure = exc
            if hasattr(obj, "partial") and not record.get("final_response"):
                try: capture(obj.partial(), partial=True)
                except Exception: pass  # retain the last durable partial, no retry
            record.update(status="FAILED_OR_UNCERTAIN", error=type(exc).__name__)
        finally:
            try: obj.close()
            except Exception as exc:
                failure = failure or exc;record.update(status="CLEANUP_UNCONFIRMED", cleanup="NATIVE_CLOSE_UNCONFIRMED")
            try:
                _require(boundary.settle(plan, task), "whole_job_stop_unconfirmed")
                record["owned_boundary"] = "REMOTE_SETTLED_PARENT_CGROUP_OBSERVATION_REQUIRED"
            except Exception as exc:
                failure = failure or exc;record.update(status="STOP_UNCONFIRMED", owned_boundary="UNCONFIRMED")
    # Recovery can return the stored final/partial evidence even if final
    # publication fails. It has no execution, admission or fresh budget path.
    if failure is None:
        record['status'] = 'OBSERVED_REQUIRES_INDEPENDENT_CHECK'
    _publish(Path(plan["output"]) / "partial-observation.json", record, replace=True)
    _publish(Path(plan["output"]) / "observation.json", record)
    if failure is not None:
        raise Refused(record["status"]) from None
    return record


def _publish(path, record, *, replace=False):
    # Includes metadata/escaping overhead; no oversized partial or final file.
    data = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode()
    _require(len(data) <= 1024 * 1024, "observation_file_limit")
    destination = path
    if replace:
        path = path.with_suffix(".pending")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data);handle.flush();os.fsync(handle.fileno())
        if replace:
            os.replace(path, destination)
    finally:
        if replace and path.exists():
            path.unlink()
    fd = os.open(path.parent, os.O_DIRECTORY);os.fsync(fd);os.close(fd)


def recover(plan, task):
    """Read-only redelivery of stored evidence, including after deadline/reboot.

    The trusted caller still owns delivery/identity. This is not admission,
    remote settlement, cgroup cleanup or a renewed original clock.
    """
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    _require(hashlib.sha256(encoded).hexdigest() == task.plan_sha256
             and plan["task_id"] == task.task_id, "original_plan_mismatch")
    directory = Path(plan["output"])
    _require(directory.is_absolute() and directory.resolve() == directory
             and directory.stat().st_uid == os.getuid() and not directory.stat().st_mode & 0o077,
             "unsafe_recovery_directory")
    for name in ("observation.json", "partial-observation.json"):
        try:
            fd = os.open(directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as handle:
                st = os.fstat(handle.fileno())
                _require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
                         and not st.st_mode & 0o077, "unsafe_recovery_file")
                data = handle.read(1024 * 1024 + 1)
                _require(len(data) <= 1024 * 1024, "recovery_record_too_large")
                record = json.loads(data)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        _require(record["task_id"] == task.task_id and record["plan_sha256"] == task.plan_sha256
                 and record["original_admission"] == {
                     "accepted_monotonic": task.accepted_monotonic, "accepted_wall": task.accepted_wall,
                     "budget_seconds": task.budget_seconds, "boot_id": task.boot_id}, "recovery_identity_mismatch")
        return record
    raise Refused("no_stored_observation_admission_remains_consumed_or_unknown")
