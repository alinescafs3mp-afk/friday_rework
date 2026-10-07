"""Typed operational edits through Hermes' protected native config/cron stores.

No raw YAML, environment, shell, path, credentials, runtime grants or active-job
bindings can be supplied. Existing model capabilities are selected, not invented.
"""
import copy
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


def local_endpoint(value):
    # Same literal /v1 boundary as tools/configure_local_test.py; avoid DNS
    # inference, ambient proxies, userinfo, interpolations and cloud fallback.
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError("invalid_local_endpoint")
    url = urlsplit(value)
    address = ipaddress.ip_address(url.hostname or "")
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    local = address.is_loopback or any(address in ipaddress.ip_network(n) for n in networks)
    if (not local or url.scheme not in ("http", "https") or not url.port
            or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1"):
        raise ValueError("invalid_local_endpoint")
    return value.rstrip("/")


def private_config(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o077):
        raise PermissionError("protected_native_config_required")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def options(cfg, home):
    from toolsets import get_toolset_names
    from tools.skills_tool import _find_all_skills
    from agent.skill_utils import ESSENTIAL_SKILLS
    routes = []
    for name, provider in (cfg.get("providers") or {}).items():
        if not isinstance(provider, dict) or provider.get("transport") != "chat_completions":
            continue
        try:
            endpoint = local_endpoint(provider.get("api"))
        except (ValueError, TypeError):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", provider.get("key_env", "")):
            continue
        for model in provider.get("models") or {}:
            if isinstance(model, str) and 0 < len(model) <= 256 and not any(ord(c) <= 32 for c in model):
                routes.append({"provider": "custom:" + name, "model": model, "base_url": endpoint})
    # Use the same resolved load names as skill_view, including categorized
    # skills and same-tier duplicate names. Directory names are not identities.
    skills = [row["name"] for row in _find_all_skills(skip_disabled=True)]
    return {"local_routes": routes, "toolsets": get_toolset_names(), "skills": skills,
            "required_skills": sorted(ESSENTIAL_SKILLS),
            "web_backends": ["exa-paid", "exa-keyless"],
            "operational": ["agent.max_turns", "streaming.enabled"],
            "model_slots": ["main", *[k for k, v in (cfg.get("auxiliary") or {}).items() if isinstance(v, dict)]]}


def _local_inference(cfg):
    """All enabled inference roles remain explicit, local, and without rescue."""
    if cfg.get("fallback_providers") or cfg.get("fallback_model"):
        raise ValueError("cloud_fallback_refused")
    slots = [(cfg.get("model") or {}, "default")]
    slots.extend((slot, "model") for slot in (cfg.get("auxiliary") or {}).values()
                 if isinstance(slot, dict) and slot.get("enabled", True) is not False)
    for slot, field in slots:
        if slot.get("fallback_chain") or not isinstance(slot.get("provider"), str) or not slot["provider"].startswith("custom:"):
            raise ValueError("explicit_local_inference_required")
        name = slot["provider"].split(":", 1)[1]
        provider = (cfg.get("providers") or {}).get(name)
        if not isinstance(provider, dict) or provider.get("transport") != "chat_completions" or provider.get("command"):
            raise ValueError("local_native_provider_required")
        endpoint = local_endpoint(provider.get("api"))
        if slot.get("base_url", endpoint).rstrip("/") != endpoint or slot.get(field) not in (provider.get("models") or {}):
            raise ValueError("declared_local_model_required")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", provider.get("key_env", "")):
            raise ValueError("protected_native_credential_reference_required")


    # Validate the native delegation bundle before a future toolset enable as
    # well as while enabled. Empty routing inherits the validated parent.
    delegation = cfg.get("delegation") or {}
    if not isinstance(delegation, dict):
        raise ValueError("invalid_native_delegation_config")
    if any(delegation.get(key) for key in ("fallback_providers", "fallback_chain", "fallback_model", "command", "args")):
        raise ValueError("delegation_fallback_or_command_refused")
    parent = cfg.get("model") or {}
    provider_name = delegation.get("provider") or parent.get("provider")
    if not isinstance(provider_name, str) or not provider_name.startswith("custom:"):
        raise ValueError("explicit_local_delegation_required")
    provider = (cfg.get("providers") or {}).get(provider_name.split(":", 1)[1])
    if not isinstance(provider, dict) or provider.get("transport") != "chat_completions" or provider.get("command"):
        raise ValueError("local_delegation_provider_required")
    endpoint = local_endpoint(provider.get("api"))
    if delegation.get("base_url") and local_endpoint(delegation["base_url"]) != endpoint:
        raise ValueError("declared_local_delegation_required")
    if delegation.get("api_mode") not in (None, "", "chat_completions"):
        raise ValueError("local_delegation_transport_required")
    if (delegation.get("model") or parent.get("default")) not in (provider.get("models") or {}):
        raise ValueError("declared_local_delegation_model_required")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", provider.get("key_env", "")):
        raise ValueError("protected_native_credential_reference_required")


def edit(profile, home, body, verify):
    from hermes_cli import config, managed_scope
    path = home / "config.yaml"
    if config.is_managed():
        raise PermissionError("managed_native_config")
    # The existing native cross-process config writer lock and cache lock cover
    # raw read/CAS/merge/write. Do not materialize expanded secrets or defaults.
    with config.config_write_transaction(path):
        verify()
        sha = private_config(path)
        if body["expected_sha256"] != sha:
            raise ValueError("native_config_changed_reload_required")
        cfg = config.require_readable_config_before_write(path)
        candidate = copy.deepcopy(cfg)
        allowed = options(cfg, home)
        kind, values = body["kind"], body["values"]
        changed = []
        if kind == "model":
            if set(values) != {"slot", "provider", "model", "base_url"} or values["slot"] not in allowed["model_slots"]:
                raise ValueError("invalid_model_selection")
            choice = {k: values[k] for k in ("provider", "model", "base_url")}
            if choice not in allowed["local_routes"]:
                raise ValueError("unobserved_local_model_route")
            slot = values["slot"]
            target = candidate.setdefault("model", {}) if slot == "main" else candidate.setdefault("auxiliary", {}).setdefault(slot, {})
            target.update(provider=choice["provider"], base_url=choice["base_url"], api_mode="chat_completions")
            target["default" if slot == "main" else "model"] = choice["model"]
            # Keep exact configured context/capacity; switching between unproved
            # capability budgets is refused rather than relabelling test caps.
            name = choice["provider"].split(":", 1)[1]
            declared = cfg["providers"][name]["models"][choice["model"]]
            if not isinstance(declared, dict) or declared.get("context_length") != target.get("context_length", (cfg.get("model") or {}).get("context_length")):
                raise ValueError("model_capacity_rebind_required")
            target["key_env"] = cfg["providers"][name]["key_env"]
            if any(k in target for k in ("api_key", "api_key_env", "fallback_model")):
                raise ValueError("protected_credential_rebind_required")
            if slot != "main": target["fallback_chain"] = []
            candidate["fallback_providers"] = []; candidate["fallback_model"] = {}
            changed = ["model" if slot == "main" else "auxiliary." + slot, "fallback_providers", "fallback_model"]
        elif kind == "web":
            if set(values) != {"profile", "extract_timeout", "extract_char_limit"} or values["profile"] not in allowed["web_backends"]:
                raise ValueError("invalid_web_profile")
            timeout, chars = values["extract_timeout"], values["extract_char_limit"]
            if type(timeout) is not int or not 1 <= timeout <= 120 or type(chars) is not int or not 2000 <= chars <= 500000:
                raise ValueError("invalid_web_bounds")
            # Exact existing Exa native profile; retrieval is separate from model
            # inference and remains mandatory. No keys or alternative providers.
            candidate.setdefault("web", {}).update(backend="exa", search_backend="exa", extract_backend="exa",
                keyless_fallback=values["profile"] == "exa-keyless", keyless_rescue=False,
                provider_tier={"exa": "free" if values["profile"] == "exa-keyless" else "paid",
                    "parallel": "paid", "firecrawl": "paid", "keenable": "paid"},
                extract_timeout=timeout, extract_char_limit=chars, cache_enabled=False)
            changed = ["web"]
        elif kind in ("toolset", "skill"):
            if set(values) != {"name", "enabled"} or type(values["enabled"]) is not bool:
                raise ValueError("invalid_capability_change")
            if values["name"] not in allowed["toolsets" if kind == "toolset" else "skills"]:
                raise ValueError("native_capability_not_installed")
            if kind == "toolset":
                from model_tools import _select_tool_names
                from toolsets import resolve_toolset
                if values == {"name": "web", "enabled": False}:
                    raise ValueError("mandatory_retrieval_required")
                # Native gateway reader uses platform_toolsets; change only
                # explicitly configured selected surfaces, never broaden all.
                sets = candidate.get("platform_toolsets")
                if not isinstance(sets, dict) or not sets:
                    raise ValueError("native_toolset_profiles_required")
                for platform, names in sets.items():
                    if not isinstance(names, list) or "web" not in names:
                        raise ValueError("mandatory_retrieval_required")
                    sets[platform] = list(dict.fromkeys([*names, values["name"]])) if values["enabled"] else [n for n in names if n != values["name"]]
                disabled = candidate.setdefault("agent", {}).get("disabled_toolsets", [])
                if not isinstance(disabled, list): raise ValueError("invalid_native_toolset_policy")
                disabled = [name for name in disabled if name != values["name"]] if values["enabled"] else list(dict.fromkeys([*disabled, values["name"]]))
                target_tools = set(resolve_toolset(values["name"]))
                for names in sets.values():
                    selected = _select_tool_names(names, disabled, True)
                    if not {"web_search", "web_extract"} <= selected:
                        raise ValueError("mandatory_retrieval_required")
                    if (values["enabled"] and not target_tools <= selected
                            or not values["enabled"] and target_tools & selected):
                        raise ValueError("conflicting_native_toolset_policy")
                candidate["agent"]["disabled_toolsets"] = disabled
                changed = ["platform_toolsets", "agent.disabled_toolsets"]
            else:
                from agent.skill_utils import ESSENTIAL_SKILLS, _normalize_string_set, is_disabled_entry
                from tools.skills_tool import _skill_catalog
                catalog = _skill_catalog(skip_disabled=True)
                selected = next(row for row in catalog if row.get("load_name") == values["name"])
                if not values["enabled"] and selected["name"] in ESSENTIAL_SKILLS:
                    raise ValueError("native_required_skill_cannot_be_disabled")
                disabled = candidate.setdefault("skills", {}).get("disabled", [])
                if not isinstance(disabled, list): raise ValueError("invalid_native_skill_policy")
                def enable_one(names):
                    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
                        raise ValueError("invalid_native_skill_policy")
                    result = [n for n in names if not is_disabled_entry(selected, _normalize_string_set([n]))]
                    # Expand a broad declared-name disable before enabling one
                    # duplicate, so its peers retain their prior policy.
                    if selected["name"] in _normalize_string_set(names) - ESSENTIAL_SKILLS:
                        result.extend(row["load_name"] for row in catalog
                            if row["name"] == selected["name"] and row.get("load_name")
                            and row["load_name"] != values["name"])
                    return list(dict.fromkeys(result))
                candidate["skills"]["disabled"] = enable_one(disabled) if values["enabled"] else list(dict.fromkeys([*disabled, values["name"]]))
                changed = ["skills.disabled"]
                if values["enabled"]:
                    platform_disabled = candidate["skills"].get("platform_disabled", {})
                    if not isinstance(platform_disabled, dict): raise ValueError("invalid_native_skill_policy")
                    for platform, names in platform_disabled.items():
                        platform_disabled[platform] = enable_one(names)
                    if platform_disabled: changed.append("skills.platform_disabled")
        elif kind == "operational":
            if set(values) != {"key", "value"} or values["key"] not in allowed["operational"]:
                raise ValueError("invalid_operational_setting")
            key, value = values["key"], values["value"]
            if (key == "agent.max_turns" and (type(value) is not int or not 1 <= value <= 200)
                    or key == "streaming.enabled" and type(value) is not bool):
                raise ValueError("invalid_operational_value")
            target = candidate
            segments = key.split(".")
            for group in segments[:-1]:
                if group in target and not isinstance(target[group], dict):
                    raise ValueError("invalid_native_operational_mapping")
                target = target.setdefault(group, {})
            target[segments[-1]] = value; changed = [key]
        else:
            raise ValueError("unsupported_typed_setting")
        def leaves(value, prefix):
            if isinstance(value, dict):
                return [path for key, item in value.items() for path in leaves(item, prefix + "." + key)]
            return [prefix]
        managed_paths = []
        for key in changed:
            value = candidate
            for segment in key.split("."): value = value[segment]
            managed_paths.extend(leaves(value, key))
        if any(managed_scope.is_key_managed(key) for key in managed_paths):
            raise PermissionError("administrator_managed_key")
        _local_inference(candidate)
        # Validate the complete native effective candidate, including default
        # auxiliary roles and managed precedence, without persisting expansion.
        effective, _ = config._merge_managed_overlay(config._expand_env_vars(
            config._canonicalize_config(config._deep_merge(copy.deepcopy(config.DEFAULT_CONFIG), candidate))))
        _local_inference(effective)
        if kind == "skill" and values["enabled"]:
            # Match the catalog's normalized display/load names and essential
            # exemptions, including managed denials outside this edit's keys.
            skill_policy = effective.get("skills") or {}
            denials = [skill_policy.get("disabled", [])]
            platforms = skill_policy.get("platform_disabled", {})
            if not isinstance(platforms, dict):
                raise ValueError("invalid_native_skill_policy")
            denials.extend(platforms.values())
            for names in denials:
                if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                    raise ValueError("invalid_native_skill_policy")
                if is_disabled_entry(selected, _normalize_string_set(names) - ESSENTIAL_SKILLS):
                    raise PermissionError("effective_native_skill_denied")
        verify()
        if private_config(path) != sha:
            raise ValueError("native_config_changed_reload_required")
        config.atomic_config_write(path, candidate)
        reread = config.require_readable_config_before_write(path)
        if reread != candidate:
            raise RuntimeError("native_config_write_unconfirmed")
        return {"recorded": True, "profile": profile, "config_sha256": private_config(path),
            "changed": changed, "runtime_application": "PERSISTED_NEXT_NATIVE_SESSION_OR_RELOAD",
            "active_worker_binding": "UNCHANGED_ORIGINAL_BUDGET", "observed_live_reload": False}


def schedules(action=None, job_id=None, verify=None):
    from cron.jobs import get_job, list_jobs, pause_job, resume_job
    if action is None:
        return [{k: row.get(k) for k in ("id", "name", "schedule", "enabled", "state", "next_run_at", "paused_reason")}
                for row in list_jobs(include_disabled=True)][:200]
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id) or get_job(job_id) is None:
        raise ValueError("exact_native_schedule_required")
    if action not in ("pause", "resume"):
        raise ValueError("invalid_schedule_control")
    if not callable(verify):
        raise PermissionError("verified_admin_required")
    verify()
    row = pause_job(job_id, reason="Verified Friday Dashboard administrator", before_write=verify, strict_lock=True) if action == "pause" else resume_job(job_id, before_write=verify, strict_lock=True)
    current = get_job(job_id)
    if row is None or current is None or bool(current.get("enabled")) != (action == "resume"):
        raise RuntimeError("native_schedule_write_unconfirmed")
    return {"recorded": True, "job_id": job_id, "action": action,
            "running_execution": "UNCHANGED_USE_TASK_CONTROL", "state": current.get("state")}
