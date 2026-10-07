"""Source-only normal-start consumers. Every effect boundary is synthetic.

The positive service/exec observations are synthetic donor-boundary contracts,
not product admission. Real prerequisites still refuse this pinned TLS-only base.
"""

import contextlib
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from plugins.friday_rework import startup_health as health
from scripts import friday_install as entry
from scripts import friday_start as start
from scripts.dsh_prepare import StopUnconfirmed
from scripts.install_containment import Budget

pytest_plugins = ["test_native_installer", "test_native_dashboard_owner", "test_admin_foundation"]


def pin(path, private=True):
    return {str(path): {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "private": private}}


@pytest.fixture
def native_home(tmp_path, monkeypatch):
    from gateway import host_rendezvous as hr
    from hermes_cli import gateway as gw
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    tmp_path.chmod(0o700)
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    source = home / "hermes-agent"
    source.mkdir()
    receipt = home / "hermes-agent.source.json"
    receipt.write_text(json.dumps({"commit": "781334eea4b9225a3e194faf0c241d9afe218634"}))
    receipt.chmod(0o600)
    launcher = source / ".hermes/bin/hermes"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("synthetic intercepted native launcher")
    launcher.chmod(0o700)
    unit = tmp_path / "user/sol-fixture.service"
    unit.parent.mkdir()
    expected = (
        '[Service]\nEnvironment="HERMES_HOME='
        + str(home)
        + '"\nExecStart=/synthetic-native -p default gateway run\n'
    )
    token = set_hermes_home_override(str(home))
    monkeypatch.setattr(gw, "supports_systemd_services", lambda: True)
    monkeypatch.setattr(gw, "has_legacy_hermes_units", lambda: False)
    monkeypatch.setattr(gw, "has_conflicting_systemd_units", lambda: False)
    monkeypatch.setattr(
        gw, "get_systemd_unit_path", lambda system=False: tmp_path / "system.service" if system else unit
    )
    monkeypatch.setattr(gw, "generate_systemd_unit", lambda system=False: expected)
    monkeypatch.setattr(hr, "read_record", lambda *a, **kw: None)
    monkeypatch.setattr(
        gw, "_read_systemd_unit_properties", lambda **kw: {"ActiveState": "inactive", "MainPID": "0"}
    )
    monkeypatch.setattr(gw, "find_gateway_pids", lambda: [])
    monkeypatch.setattr(start, "load_required_plugins", lambda b: None)
    monkeypatch.setattr(start, "dashboard_admission", lambda v, b: None)
    record = hr.HostRecord(
        role="gateway",
        pid=45678,
        create_time=1.0,
        home=str(home),
        profiles=("default",),
        host="127.0.0.1",
        port=9119,
        start_time=5678,
        protocol_version=1,
        updated_at="synthetic",
        token_fingerprint="synthetic",
    )
    env = SimpleNamespace(home=home, source=source, unit=unit, expected=expected, gw=gw, hr=hr, record=record)
    try:
        yield env
    finally:
        reset_hermes_home_override(token)


def observe(env, monkeypatch, *, state="running", mainpid="45678", invocation="a" * 32):
    from gateway import control_socket
    from hermes_cli import friday_gateway_owner

    generation = {"home": str(env.home), "source": {"receipt": "synthetic-source"},
                  "configuration": "synthetic-configuration"}
    monkeypatch.setattr(friday_gateway_owner, "expected", lambda home: generation)
    monkeypatch.setattr(control_socket, "identify_gateway", lambda home, **kw: {
        "protocol": control_socket.CONTROL_PROTOCOL_VERSION, "kind": "hermes-gateway",
        "pid": env.record.pid, "start_time": env.record.start_time,
        "hermes_home": str(env.home), "friday_owner": generation,
        "code_sha": "781334eea4b9225a3e194faf0c241d9afe218634",
    })
    monkeypatch.setattr(env.hr, "read_record", lambda *a, **kw: env.record)
    monkeypatch.setattr(env.hr, "liveness_is_proven", lambda r: True)
    monkeypatch.setattr(env.hr, "record_token_is_consistent", lambda r: True)
    monkeypatch.setattr(
        env.gw,
        "_read_systemd_unit_properties",
        lambda **kw: {
            "ActiveState": "active",
            "SubState": "running",
            "MainPID": mainpid,
            "InvocationID": invocation,
        },
    )
    monkeypatch.setattr(
        env.gw, "_read_gateway_runtime_status", lambda: {
            "pid": 45678, "gateway_state": state, "kind": "hermes-gateway",
            "start_time": env.record.start_time, "hermes_home": str(env.home),
            "code_sha": "781334eea4b9225a3e194faf0c241d9afe218634",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def test_native_gateway_empty_unit_preflight_is_read_only(native_home):
    unit, old = start.gateway_preflight(native_home.home, "default", Budget(30))
    assert unit == native_home.unit and old is None and not unit.exists()


def test_actual_native_unit_parser_and_exact_definition(native_home):
    native_home.unit.write_text(native_home.expected)
    assert start.gateway_preflight(native_home.home, "default", Budget(30))[0] == native_home.unit


@pytest.mark.parametrize(
    "change",
    [
        "home",
        "definition",
        "public",
        "symlink",
        "hardlink",
        "system",
        "dropin",
        "legacy",
        "conflicting",
        "backend",
    ],
)
def test_foreign_duplicate_or_changed_gateway_refuses_before_effect(native_home, monkeypatch, change):
    env = native_home
    env.unit.write_text(env.expected)
    if change == "home":
        env.unit.write_text(env.expected.replace(str(env.home), "/synthetic-foreign"))
    elif change == "definition":
        env.unit.write_text(env.expected + "Environment=FOREIGN=1\n")
    elif change == "public":
        env.unit.chmod(0o666)
    elif change == "symlink":
        env.unit.rename(env.unit.with_suffix(".other"))
        env.unit.symlink_to(env.unit.with_suffix(".other"))
    elif change == "hardlink":
        os.link(env.unit, env.unit.with_suffix(".other"))
    elif change == "system":
        (env.unit.parent.parent / "system.service").write_text(env.expected)
    elif change == "dropin":
        d = env.unit.parent / (env.unit.name + ".d")
        d.mkdir()
        (d / "20-change.conf").write_text("change")
    elif change == "legacy":
        monkeypatch.setattr(env.gw, "has_legacy_hermes_units", lambda: True)
    elif change == "conflicting":
        monkeypatch.setattr(env.gw, "has_conflicting_systemd_units", lambda: True)
    elif change == "backend":
        monkeypatch.setattr(env.gw, "supports_systemd_services", lambda: False)
    before = {str(p): p.read_bytes() for p in env.unit.parent.rglob("*") if p.is_file()}
    with pytest.raises((ValueError, OSError)):
        start.gateway_preflight(env.home, "default", Budget(30))
    assert {str(p): p.read_bytes() for p in env.unit.parent.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("change", ["foreign", "profile", "unknown-start", "stale", "token"])
def test_existing_gateway_incarnation_must_be_proven(native_home, monkeypatch, change):
    env = native_home
    observe(env, monkeypatch)
    data = env.record.to_dict() if hasattr(env.record, "to_dict") else vars(env.record).copy()
    if change == "foreign":
        data["home"] = "/synthetic-foreign"
    elif change == "profile":
        data["profiles"] = ("foreign",)
    elif change == "unknown-start":
        data["start_time"] = None
    elif change == "stale":
        monkeypatch.setattr(env.hr, "liveness_is_proven", lambda r: False)
    elif change == "token":
        monkeypatch.setattr(env.hr, "record_token_is_consistent", lambda r: False)
    record = env.hr.HostRecord(**data)
    monkeypatch.setattr(env.hr, "read_record", lambda *a, **kw: record)
    with pytest.raises(ValueError):
        start.gateway_preflight(env.home, "default", Budget(30))


@pytest.mark.parametrize(
    "state,pid,invocation",
    [
        ("running", "45678", "a" * 32),
        ("degraded", "45678", "a" * 32),
        ("startup_failed", "45678", "a" * 32),
        ("running", "99999", "a" * 32),
        ("running", "45678", ""),
    ],
)
def test_actual_native_runtime_observation_never_equals_command_exit(
    native_home, monkeypatch, state, pid, invocation
):
    observe(native_home, monkeypatch, state=state, mainpid=pid, invocation=invocation)
    if state == "running" and pid == "45678" and invocation:
        assert start.gateway_observation(native_home.home, Budget(30)) == native_home.record
    else:
        with pytest.raises(ValueError):
            start.gateway_observation(native_home.home, Budget(30))


def test_snapshot_drift_and_expired_original_clock_refuse(tmp_path):
    p = tmp_path / "input.json"
    p.write_text("synthetic-pinned")
    p.chmod(0o600)
    pins = pin(p)
    start.unchanged(pins, Budget(30))
    p.write_text("changed")
    with pytest.raises(ValueError, match="native_start_input_changed"):
        start.unchanged(pins, Budget(30))
    with pytest.raises(ValueError, match="budget_exhausted"):
        Budget(30, started=0)


@pytest.fixture
def launch_fixture(native_home, monkeypatch):
    from scripts import install_containment as containment

    env = native_home
    calls = []
    marker = env.home / "synthetic-input.json"
    marker.write_text("original-source-config-marker-key snapshot")
    marker.chmod(0o600)
    argv = {
        "gateway_install": [
            "/synthetic-native",
            "-p",
            "default",
            "gateway",
            "install",
            "--no-start-now",
            "--no-start-on-login",
        ],
        "gateway_start": ["/synthetic-native", "-p", "default", "gateway", "start"],
        "dashboard": [
            str(env.source / ".hermes/bin/hermes"),
            "-p",
            "default",
            "dashboard",
            "--host",
            "192.168.12.128",
            "--port",
            "9119",
            "--no-open",
        ],
    }
    monkeypatch.setattr(entry, "commands", lambda v: argv)

    class Custody:
        def __init__(self, pin, budget, environment):
            self.budget = budget

        def probe(self, python, cwd):
            calls.append("namespace-probe")

        def run(self, command, cwd, *, timeout):
            assert timeout == 30 and cwd == env.source
            assert self.budget.deadline == budget.deadline
            calls.append(list(command))
            effect(command)
            return "", {"synthetic": True}

    def effect(command):
        if "install" in command:
            env.unit.write_text(env.expected)
        else:
            observe(env, monkeypatch)

    monkeypatch.setattr(containment, "Containment", Custody)

    # Raises only at the intercepted OS ownership-transfer boundary.
    def transfer(executable, command, environment):
        calls.append(("exec", executable, command, environment))
        raise SystemExit("synthetic-transfer")

    monkeypatch.setattr(os, "execve", transfer)
    budget = Budget(1800)
    value = {
        "home": str(env.home),
        "bootstrap_python": {"path": "/synthetic-python"},
        "containment": {"path": "/synthetic-bwrap"},
        "product": {"dashboard": {"host": "192.168.12.128", "port": 9119}},
    }
    return SimpleNamespace(
        env=env,
        calls=calls,
        argv=argv,
        budget=budget,
        value=value,
        pins=pin(marker),
        marker=marker,
        effect=effect,
    )


def test_supported_native_service_then_dashboard_argv_and_original_clock(launch_fixture):
    f = launch_fixture
    # Interception returns control rather than transferring the actual process;
    # even SystemExit must preserve the already-owned gateway's unknown stop.
    with pytest.raises(StopUnconfirmed) as caught:
        start.launch(f.value, f.budget, pins=f.pins)
    assert isinstance(caught.value.__cause__, SystemExit)
    assert f.calls[:3] == ["namespace-probe", f.argv["gateway_install"], f.argv["gateway_start"]]
    assert f.calls[-1][2] == f.argv["dashboard"]
    assert f.calls[-1][3]["HERMES_HOME"] == str(f.env.home)
    assert f.calls[-1][3].get("HERMES_GATEWAY_LOCK_DIR") is None
    assert "HERMeS_HOME" not in f.calls[-1][3]


def test_valid_owned_service_reattaches_without_second_start(launch_fixture, monkeypatch):
    f = launch_fixture
    f.env.unit.write_text(f.env.expected)
    observe(f.env, monkeypatch)
    with pytest.raises(StopUnconfirmed) as caught:
        start.launch(f.value, f.budget, pins=f.pins)
    assert isinstance(caught.value.__cause__, SystemExit)
    assert all("gateway" not in call for call in f.calls if isinstance(call, list))


@pytest.mark.parametrize("boundary", ["install", "start", "observation"])
def test_uncertain_native_service_keeps_typed_stop_and_never_retries(launch_fixture, monkeypatch, boundary):
    f = launch_fixture

    def effect(command):
        if boundary in command:
            raise RuntimeError("synthetic unknown effect")
        f.effect(command)

    from scripts import install_containment as containment

    def run(self, command, cwd, *, timeout):
        if boundary == "observation" and "start" in command:
            f.calls.append(list(command))
            return "", {"synthetic": True}
        effect(command)
        f.calls.append(list(command))
        return "", {"synthetic": True}

    monkeypatch.setattr(containment.Containment, "run", run)
    with pytest.raises(StopUnconfirmed):
        start.launch(f.value, f.budget, pins=f.pins)
    assert not any(isinstance(c, tuple) and c[0] == "exec" for c in f.calls)


def test_key_source_or_config_drift_prevents_service_effect(launch_fixture):
    f = launch_fixture
    f.marker.write_text("drift")
    with pytest.raises(ValueError, match="native_start_input_changed"):
        start.launch(f.value, f.budget, pins=f.pins)
    assert f.calls == []


def test_running_unit_without_host_record_is_unresolved_not_absent(launch_fixture, monkeypatch):
    f = launch_fixture
    monkeypatch.setattr(
        f.env.gw, "_read_systemd_unit_properties", lambda **kw: {"ActiveState": "active", "MainPID": "99"}
    )
    with pytest.raises(ValueError, match="requires_reconciliation"):
        start.launch(f.value, f.budget, pins=f.pins)
    assert not any(isinstance(c, list) for c in f.calls)


def test_dashboard_foreign_or_unproven_attachment_precedes_all_service_effects(launch_fixture, monkeypatch):
    f = launch_fixture
    monkeypatch.setattr(
        f.env.hr, "read_record", lambda role, **kw: f.env.record if role == f.env.hr.ROLE_SERVE else None
    )
    from hermes_cli import friday_dashboard_owner as owner

    def refuse(record):
        raise ValueError("synthetic auth/nonce/foreign identity denied")

    monkeypatch.setattr(owner, "check_attachment", refuse)
    with pytest.raises(ValueError):
        start.launch(f.value, f.budget, pins=f.pins)
    assert f.calls == []


def test_rendered_ready_or_disabled_workers_never_reexec(install_input, monkeypatch):
    monkeypatch.setattr(entry, "inspect", lambda *a: {"state": "READY", "ready": True})
    calls = []
    monkeypatch.setattr(os, "execve", lambda *a: calls.append(a))
    with pytest.raises(ValueError, match="mandatory_a0_web_kernel"):
        entry.start(install_input, "synthetic")
    assert calls == []


@pytest.mark.parametrize(
    "configured,check_result", [(False, "not-run"), (True, "pass"), (True, "stale"), (True, "cancelled")]
)
def test_worker_health_uses_original_native_receipt_checker_without_effects(
    tmp_path, monkeypatch, configured, check_result
):
    from hermes_cli import config_effective as config
    from plugins.friday_rework import admin, host_runtime

    runtime = {
        "enabled": configured,
        "dsh": {"web": {"profile": "exa-paid"}},
        "runtime_receipt": {"path": "synthetic", "sha256": "0" * 64},
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}")
    config_path.chmod(0o600)

    class Administrator:
        def profiles(self):
            return ["default"]

        @contextlib.contextmanager
        def scope(self, p):
            yield tmp_path

    monkeypatch.setattr(admin, "Administration", Administrator)
    monkeypatch.setattr(
        config,
        "read_user_config_effective_readonly",
        lambda *args, **kwargs: {
            "plugins": {"entries": {"friday_rework": {"settings": {"runtime": runtime}}}}
        },
    )
    calls = []

    def check(r, associations):
        calls.append(r)
        if check_result in ("stale", "cancelled"):
            raise host_runtime.HostUnavailable("synthetic-closed-receipt")
        return r

    monkeypatch.setattr(host_runtime, "check_runtime", check)
    report = health.worker_health()
    assert report["runtime_ready"] is False and report["live_journeys"] == "NOT_RUN"
    assert bool(calls) == configured
    assert report["workers"][0]["deployment_verified"] == (configured and check_result == "pass")
    assert report["workers"][0]["execution"] == "NOT_OBSERVED"


def test_a0_original_web_and_kernel_dependency_is_not_turned_into_grant(tmp_path, monkeypatch):
    from hermes_cli import config_effective as config
    from plugins.friday_rework import admin, host_runtime

    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}")
    config_path.chmod(0o600)

    class Administrator:
        def profiles(self):
            return ["default"]

        @contextlib.contextmanager
        def scope(self, p):
            yield tmp_path

    monkeypatch.setattr(admin, "Administration", Administrator)
    r = {"enabled": True, "a0": {}, "ready": True}
    monkeypatch.setattr(
        config,
        "read_user_config_effective_readonly",
        lambda *args, **kwargs: {"plugins": {"entries": {"friday_rework": {"settings": {"runtime": r}}}}},
    )
    monkeypatch.setattr(host_runtime, "check_runtime", lambda value, store: value)
    out = health.worker_health()
    assert out["missing_workers"] == ["a0", "dsh"] and not out["workers"][0]["deployment_verified"]


def test_native_admin_health_uses_existing_authority_and_installed_plugin_module():
    from plugins.friday_rework.admin import Administration

    # No root/operator policy: no state/worker availability can create authority.
    with pytest.raises(PermissionError):
        Administration().health()


def test_absent_auth_pool_cannot_be_added_after_admission(tmp_path):
    p = tmp_path / "auth.json"
    pins = {str(p): {"private": True, "sha256": None}}
    start.unchanged(pins, Budget(30))
    p.write_text('{"synthetic":"new-pool"}')
    p.chmod(0o600)
    with pytest.raises(ValueError, match="native_start_input_changed"):
        start.unchanged(pins, Budget(30))


@pytest.mark.parametrize(
    "mutation", ["none", "receipt-not-ready", "source", "runtime", "receipt-byte", "foreign-home"]
)
def test_real_original_runtime_receipt_check_is_not_a_start_grant(tmp_path, monkeypatch, mutation):
    from hermes_cli.plugins_state import PluginState
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from plugins.friday_rework import host_record, host_runtime
    from plugins.friday_rework.associations import Associations

    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    directories = {n: tmp_path / n for n in ["work", "stage", "cache", "payload", "toolchain"]}
    for p in directories.values():
        p.mkdir(mode=0o700)
    nativefile = directories["payload"] / "native.js"
    node = directories["toolchain"] / "node"
    patch = tmp_path / "dsh-profile.yml"
    for p in [nativefile, node, patch]:
        p.write_text("explicit synthetic bytes; no executable")
        p.chmod(0o600)

    def pinned(p):
        return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

    runtime = {
        "enabled": True,
        "runtime_profile": "default",
        "runtime_home": str(home),
        "workspace_root": str(directories["work"]),
        "staging_root": str(directories["stage"]),
        "cache_roots": [str(directories["cache"])],
        "budget_seconds": 60,
        "max_file_bytes": 1024,
        "max_total_bytes": 4096,
        "dsh": {
            "payload_root": str(directories["payload"]),
            "toolchain_root": str(directories["toolchain"]),
            "node": pinned(node),
            "cli": pinned(nativefile),
            "patch": pinned(patch),
            "native_files": [pinned(nativefile)],
            "key_name": "SYNTHETIC_LOCAL_KEY",
            "profile": "headless",
            "memory_bytes": 2 * 1024**3,
            "cpu_percent": 200,
            "tasks": 64,
            "shutdown_seconds": 2,
            "tmp_bytes": 64 * 1024**2,
        },
    }
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"scope":"SYNTHETIC_FIXTURE_NOT_LIVE"}')
    evidence.chmod(0o600)
    receipt = {
        "schema": "friday-rework.dsh-runtime.v1",
        "ready": True,
        "runtime_sha256": host_record.digest(runtime),
        "adapter_sha256": hashlib.sha256(
            Path(host_runtime.__file__).with_name("adapters").joinpath("dsh.py").read_bytes()
        ).hexdigest(),
        "evidence": [pinned(evidence)],
    }
    if mutation == "receipt-not-ready":
        receipt["ready"] = False
    if mutation == "source":
        receipt["adapter_sha256"] = "0" * 64
    if mutation == "runtime":
        receipt["runtime_sha256"] = "0" * 64
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    runtime["runtime_receipt"] = pinned(path)
    if mutation == "receipt-byte":
        path.write_text("{}")
    if mutation == "foreign-home":
        runtime["runtime_home"] = str(tmp_path / "foreign")
    token = set_hermes_home_override(str(home))
    state = PluginState("friday_rework")
    state.data_dir.mkdir(parents=True, mode=0o700)
    retained = state.data_dir / "state.json"
    retained.write_text('{"owner_pause":true,"cancelled_generation":4,"original_budget":60}')
    retained.chmod(0o600)
    before = retained.read_bytes()
    try:
        if mutation == "none":
            assert host_runtime.check_runtime(runtime, Associations(state)) == runtime
        else:
            with pytest.raises((ValueError, RuntimeError, OSError)):
                host_runtime.check_runtime(runtime, Associations(state))
        assert retained.read_bytes() == before
    finally:
        reset_hermes_home_override(token)


def test_failed_dashboard_exec_retains_native_gateway_ownership(launch_fixture, monkeypatch):
    f = launch_fixture

    def failed(*a):
        raise OSError("SYNTHETIC EXEC FAILURE; no service cessation observed")

    monkeypatch.setattr(os, "execve", failed)
    with pytest.raises(StopUnconfirmed):
        start.launch(f.value, f.budget, pins=f.pins)
    assert f.env.unit.exists()
    assert sum("start" in c for c in f.calls if isinstance(c, list)) == 1


def test_normal_native_discovery_loads_installed_plugin_without_http_activation(tmp_path, monkeypatch):
    import shutil

    import hermes_constants
    import hermes_yaml as yaml
    from hermes_cli import plugins
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    home = tmp_path / "native"
    home.mkdir(mode=0o700)
    shutil.copytree(entry.ROOT / "plugins/friday_rework", home / "plugins/friday_rework")
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "plugins": {
                    "enabled": ["friday_rework", "dashboard_auth/basic", "web/exa"],
                    "entries": {
                        "friday_rework": {
                            "allow_gateway_work": True,
                            "allow_gateway_control": True,
                            "settings": {"runtime": {"enabled": False}},
                        }
                    },
                },
                "dashboard": {
                    "basic_auth": {
                        "username": "synthetic-operator",
                        "password": "SYNTHETIC-ONLY",
                        "secret": "SYNTHETIC SIGNING SECRET FOR FIXTURE ONLY",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(hermes_constants, "_PINNED_PROCESS_HERMES_HOME", None)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(plugins.PluginManager, "_scan_entry_points", lambda self: [])
    token = set_hermes_home_override(str(home))
    plugins._reset_plugin_managers_for_tests()
    try:
        start.load_required_plugins(Budget(30))
        from hermes_cli.plugins_activation import activation_summaries

        summaries = activation_summaries(plugins.get_plugin_manager())
        friday = next(r for r in summaries if r["name"] == "friday_rework")
        assert "post_gateway_admission" in friday["activated_now"]["hooks"]
        assert "friday_work" in friday["deferred"]["tools"]
    finally:
        plugins._reset_plugin_managers_for_tests()
        reset_hermes_home_override(token)


def test_prerequisites_refuses_absent_credential_join(native_home, monkeypatch):
    from hermes_cli import source_build
    from pm import environments, paths

    f = native_home
    monkeypatch.setattr(paths, "repo_root", lambda: f.source)
    monkeypatch.setattr(environments, "project_python", lambda source: Path(os.sys.executable))
    monkeypatch.setattr(environments, "owning_home_root", lambda source: None)
    monkeypatch.setattr(source_build, "source_product_current", lambda *a: True)
    monkeypatch.setattr(start, "snapshot", lambda home, budget: {})
    # The complete composition contains this dependency; remove it explicitly
    # to retain the missing-overlay negative control after integration.
    monkeypatch.setitem(os.sys.modules, "hermes_cli.friday_credential_admission", None)
    with pytest.raises(ValueError, match="native_credential_admission_join_required"):
        start.prerequisites({"home": str(f.home)}, Budget(30))
    assert not f.unit.exists()


def test_actual_native_dashboard_provider_gate_before_service_effects(owner):
    value = {
        "product": {
            "dashboard": {
                "host": "127.0.0.1",
                "port": 9119,
            }
        }
    }
    result = start.dashboard_admission(value, Budget(30))
    assert result["operator"]["user_id"] == "explicit-operator"
    assert owner.ws.app.state.auth_required is True


@pytest.mark.parametrize("identity", ["owner", "ordinary", "missing", "foreign"])
def test_installed_dashboard_health_route_retains_native_operator_authority(env, identity):
    import asyncio
    import importlib.util

    import httpx
    from fastapi import FastAPI
    from hermes_cli.dashboard_auth.base import Session

    path = entry.ROOT / "plugins/friday_rework/dashboard/api.py"
    spec = importlib.util.spec_from_file_location("_synthetic_start_health_api", path)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/friday_rework")
    app.state.auth_required = True

    @app.middleware("http")
    async def principal(request, call_next):
        request.state.session = (
            None
            if identity == "missing"
            else Session(
                provider="foreign" if identity == "foreign" else "basic",
                user_id="owner" if identity == "owner" else "ordinary",
                org_id="",
                expires_at=9999999999,
                email="",
                display_name="synthetic",
                access_token="synthetic",
                refresh_token="",
            )
        )
        return await call_next(request)

    async def call():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://synthetic"
        ) as client:
            return await client.get("/api/plugins/friday_rework/health")

    from hermes_cli.config import load_config_readonly

    load_config_readonly()  # Normal native startup initializes its home before serving.
    before = {str(p): p.read_bytes() for p in env.home.rglob("*") if p.is_file()}
    response = asyncio.run(call())
    if identity == "owner":
        assert response.status_code == 200
        assert response.json()["runtime_ready"] is False
        assert response.json()["missing_workers"] == ["a0", "dsh"]
    else:
        assert response.status_code == 403
    assert {str(p): p.read_bytes() for p in env.home.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("raw", ["model:\n  default: synthetic-local\n", "- not-a-mapping\n", "broken: [\n"])
def test_native_readonly_effective_config_is_current_and_never_seeds_backup(tmp_path, raw):
    from hermes_cli.config_effective import read_user_config_effective_readonly
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    home = tmp_path / "cold-profile"
    home.mkdir(mode=0o700)
    p = home / "config.yaml"
    p.write_text(raw)
    p.chmod(0o600)
    token = set_hermes_home_override(str(home))
    before = {str(f): f.read_bytes() for f in home.rglob("*") if f.is_file()}
    try:
        if raw.startswith("model:"):
            assert read_user_config_effective_readonly(p)["model"]["default"] == "synthetic-local"
            p.write_text("model:\n  default: changed-current\n")
            assert read_user_config_effective_readonly(p)["model"]["default"] == "changed-current"
            p.write_text(raw)
        else:
            with pytest.raises((ValueError, __import__("hermes_yaml").YAMLError)):
                read_user_config_effective_readonly(p)
        assert {str(f): f.read_bytes() for f in home.rglob("*") if f.is_file()} == before
    finally:
        reset_hermes_home_override(token)


@pytest.mark.parametrize("drift", ["foreign-unit", "appeared-owner"])
def test_native_unit_and_owner_are_rechecked_after_probe_before_start(launch_fixture, monkeypatch, drift):
    from scripts import install_containment

    f = launch_fixture
    original = install_containment.Containment.probe

    def changed(self, python, cwd):
        original(self, python, cwd)
        if drift == "foreign-unit":
            f.env.unit.write_text("[Service]\nEnvironment=HERMES_HOME=/synthetic-foreign\n")
        else:
            f.env.unit.write_text(f.env.expected)
            observe(f.env, monkeypatch)

    monkeypatch.setattr(install_containment.Containment, "probe", changed)
    with pytest.raises(
        ValueError,
        match="foreign_or_changed_gateway_unit|gateway_owner_changed_before_handoff|gateway_start_requires_reconciliation",
    ):
        start.launch(f.value, f.budget, pins=f.pins)
    assert f.calls == ["namespace-probe"]
