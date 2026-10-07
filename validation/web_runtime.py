"""Finite native Hermes research driver, prepared source only.

The trusted parent must already own the original task, an exclusive lease and
the existing supervised process. This module neither launches nor grants one.
Call it in that dedicated process, never inside a concurrent gateway. Importing
the file is inert. There is deliberately no command that can self-authorize.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import runpy
import stat
import sys
import time
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
                'повторять только GET при HTTP 503, учитывать Retry-After. Верни JSON с полями total, '
                'allowed_methods, status_forcelist, respect_retry_after_header, sources (URL). '
                'Если текущий API подтвердить нельзя, явно укажи неопределённость вместо догадки.',
    "explicit": 'Исследуй текущую официальную документацию urllib3 Retry, найди и прочитай первичные источники. '
                'Подготовь конфигурацию: максимум два повтора, только GET при HTTP 503, учитывать Retry-After. '
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
                 "hermes_cli/config_defaults.py"}
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
    def open(self, plan, secrets, remaining):
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
        from hermes_state import SessionDB
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
        required_keys = {key_name} | ({"EXA_API_KEY"} if plan["web_profile"] == "exa-paid" else set())
        _require(set(secrets) == required_keys, "wrong_scoped_credential_set")
        runtime = resolve_runtime_provider(requested=model["provider"], target_model=model["default"])
        _require(runtime["base_url"].rstrip("/") == plan["inference_endpoint"].rstrip("/")
                 and runtime["api_mode"] == "chat_completions", "native_runtime_route_mismatch")
        self.db = SessionDB(Path(home) / "state.db")
        self.agent = AIAgent(model=model["default"], base_url=runtime["base_url"], api_key=runtime["api_key"],
            provider=runtime["provider"], api_mode=runtime["api_mode"], requested_provider=model["provider"],
            max_iterations=plan["max_iterations"], enabled_toolsets=["web"], skip_context_files=True,
            load_soul_identity=True, skip_memory=True, skip_background_review=True, quiet_mode=True,
            session_db=self.db, session_id=plan["task_id"], run_budget_seconds=remaining,
            fallback_model={}, cwd=plan["workspace"])
        self.secrets = tuple(secrets.values()) + (runtime["api_key"],)
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
        return self.agent.run_conversation(prompt)

    def close(self):
        # Close every acquired native object even after partial construction.
        errors = []
        for name in ("agent", "db"):
            value = getattr(self, name, None)
            if value is not None:
                try: value.close()
                except Exception: errors.append(name)
        if getattr(self, "tokens", []):
            from agent.secret_scope import reset_secret_scope, reset_multiplex_context
            for name, token in reversed(self.tokens):
                (reset_secret_scope if name == "scope" else reset_multiplex_context)(token)
        if hasattr(self, "old_path"):
            sys.path[:] = self.old_path
        _require(not errors, "native_cleanup_unconfirmed")


def _observation(result, secret_values):
    """Bounded public observations only. No thinking, raw prompt or exceptions."""
    def public(value):
        _require(len(json.dumps(value, ensure_ascii=False).encode()) <= 1024 * 1024, "native_observation_too_large")
        def clean(item):
            if isinstance(item, str):
                for secret in secret_values:
                    if secret:
                        for form in (secret, json.dumps(secret, ensure_ascii=False)[1:-1]):
                            item = item.replace(form, "[REDACTED]")
                return item
            if isinstance(item, dict):return {clean(k):clean(v) for k,v in item.items()}
            if isinstance(item, list):return [clean(v) for v in item]
            return item
        return clean(value)
    messages = result.get("messages", [])
    tool_calls = [m.get("tool_calls") for m in messages if m.get("tool_calls")]
    # Tool messages are observed source data; no inference that the model used
    # them correctly. The independent verifier must join call IDs/URLs/text.
    tool_sources = [m for m in messages if m.get("role") == "tool"]
    _require(all(c.get("function", {}).get("name") in {"web_search", "web_extract"}
                 for batch in tool_calls for c in batch), "unexpected_tool_in_observation")
    return public({"model_completed": result.get("completed"), "api_calls": result.get("api_calls"),
                   "tool_calls": tool_calls, "tool_source_observations": tool_sources,
                   "final_response": result.get("final_response", ""),
                   "uncertainty": "Interpret source availability, accuracy and application independently",
                   "status": "OBSERVED_REQUIRES_INDEPENDENT_CHECK", "journey_acceptance": "NOT_CLAIMED"})


class ExistingBoundary:
    """Read/settle the already owned systemd boundary; never launch a service.

    Only the trusted parent supplies current_association, scoped_credentials,
    confirm_remote_quiescence and the inherited exclusive FD. Current live
    production of this complete admission is NOT IMPLEMENTED/NOT ACCEPTED.
    The existing offline card permits testing these seams with synthetic state.
    """
    def __init__(self, *, current_association, supervisor, lock_fd, lock_pin,
                 scoped_credentials, verify_network_admission, confirm_remote_quiescence):
        self.current_association = current_association
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
    No implementation of that live admission producer is claimed in this package.
    boundary.settle must reconcile remote inference. After this driver exits,
    the parent must observe the entire cgroup quiescent before releasing its
    lease. Neither agent.close nor an in-process callback proves cgroup stop.
    """
    verify_plan(plan, task)
    remaining = task.remaining(mono=mono, wall=wall, boot=boot)
    secrets = boundary.admit(plan, task, remaining)
    obj = native if native is not None else Native()
    record = {"task_id": task.task_id, "mode": plan["mode"], "input": PROMPTS[plan["mode"]],
              "plan_sha256": task.plan_sha256, "status": "STARTED", "journey_acceptance": "NOT_CLAIMED",
              "original_admission":{"accepted_monotonic":task.accepted_monotonic,"accepted_wall":task.accepted_wall,
                  "budget_seconds":task.budget_seconds,"boot_id":task.boot_id}}
    failure = None
    with _clean_environment(Path(plan["profile"]["path"]).parent):
        try:
            _require(isinstance(secrets, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in secrets.items()), "native_scoped_credentials_required")
            verify_plan(plan, task)  # recheck after bounded native admission I/O
            obj.open(plan, secrets, task.remaining(mono=mono, wall=wall, boot=boot))
            record["native_input_observation"] = getattr(obj,"observation_metadata",{})
            result = obj.run(PROMPTS[plan["mode"]])
            task.remaining(mono=mono, wall=wall, boot=boot)
            record.update(_observation(result, (*secrets.values(), *getattr(obj, "secrets", ()))))
        except Exception as exc:
            failure = exc
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
    path = Path(plan["output"]) / "observation.json"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2);handle.write("\n");handle.flush();os.fsync(handle.fileno())
    fd = os.open(path.parent, os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    if failure is not None:
        raise Refused(record["status"]) from None
    return record
