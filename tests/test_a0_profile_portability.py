"""Real profile producers/consumers, synthetic future routes; no live readiness."""

import ast
import copy
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace as NS

import pytest
import test_native_installer as installer_fixtures
import test_user_worker_provision as worker_fixtures
from plugins.friday_rework.adapters import a0_profile as profile
from plugins.friday_rework.adapters.a0_config import LocalNetwork, local_profile
from plugins.friday_rework.adapters.dsh import PinnedFile
from scripts import a0_runtime as runtime
from scripts import friday_install as installer
from test_product_profile import inputs as product_inputs
from test_product_profile import template
from test_user_worker_provision import cas, home, ident, prepare, raw, row, save, worker_prepare
from test_user_worker_provision import inputs as worker_inputs
from tools.configure_product import compose_product

env = worker_fixtures.env
install_input = installer_fixtures.install_input

Q = Path(__file__).resolve().parents[1]


def future():
    # Explicitly synthetic: no assertion that these endpoints/models exist.
    return dict(
        name="synthetic-future-local",
        preset="Default",
        chat=dict(
            endpoint="http://10.55.0.10:18001/v1",
            model="synthetic-chat-large",
            context_length=262144,
            max_output_tokens=16384,
            timeout=60,
        ),
        utility=dict(
            endpoint="http://10.55.0.11:18003/v1",
            model="synthetic-utility-large",
            context_length=131072,
            max_output_tokens=8192,
            timeout=45,
        ),
        embedding=dict(
            endpoint="https://10.55.0.12:18002/v1",
            model="synthetic-embedding-large",
            context_length=32768,
            timeout=30,
        ),
    )


def network(p, tmp_path):
    policy = tmp_path / "policy"
    policy.write_bytes(b"EXPLICIT SYNTHETIC POLICY; NO ROUTE AUTHORITY")
    return LocalNetwork(
        "synthetic-private-network",
        profile.endpoint_urls(p),
        PinnedFile(policy, hashlib.sha256(policy.read_bytes()).hexdigest()),
        p,
    )


def product(p):
    spec = product_inputs()
    c = p["chat"]
    spec["inference"].update(
        base_url=c["endpoint"],
        model=c["model"],
        key_env="FRIDAY_LLM_API_KEY",
        context=c["context_length"],
        max_input=c["context_length"] - 10000,
        main_output=c["max_output_tokens"],
        summary_output=4096,
    )
    spec["a0_deployment"] = p
    return spec


def test_legacy_presets_are_exactly_compatible_with_old_native_source(tmp_path):
    old = os.environ["FRW_A0_LEGACY_RUNTIME"]
    ns = {"__file__": old, "__name__": "synthetic_legacy"}
    exec(compile(Path(old).read_text(), old, "exec"), ns)
    original = ns["templates"]()
    assert runtime.templates() == original
    p = profile.legacy_profile()
    assert p["name"] == "legacy-local-test"
    assert profile.profile_templates(p) == original
    assert local_profile(network(p, tmp_path)) == original
    assert profile.network_endpoints(p) == runtime.LOCAL_ENDPOINTS


def test_future_whole_profile_native_materialization_and_network(tmp_path):
    p = future()
    n = network(p, tmp_path)
    native = local_profile(n)
    assert runtime.templates(p) == native
    usr = tmp_path / "usr"
    runtime.materialize(usr, p)
    for name, expected in native.items():
        assert json.loads((usr / name).read_text()) == expected
    slots = native["plugins/_model_config/presets.yaml"][0]
    assert slots["chat"]["ctx_length"] == 262144 and slots["chat"]["kwargs"]["max_tokens"] == 16384
    assert slots["utility"]["api_base"] != slots["chat"]["api_base"]
    assert slots["embedding"]["ctx_length"] == 32768
    assert slots["embedding"]["provider"] == "other" and slots["embedding"]["kwargs"] == {"timeout": 30}
    assert n.arguments() == ["--network=synthetic-private-network"]
    assert runtime.templates() != native


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com:443/v1",
        "http://8.8.8.8:8001/v1",
        "http://127.0.0.1:8001/v1",
        "http://169.254.169.254:8001/v1",
        "http://0.0.0.0:8001/v1",
        "http://224.0.0.1:8001/v1",
        "http://192.0.2.1:8001/v1",
        "http://user:secret@10.55.0.10:18001/v1",
        "http://10.55.0.10:18001/v1?key=secret",
        "http://10.55.0.10:18001/v1#fragment",
        "http://10.55.0.10:18001/v1/",
        "http://10.55.0.10:18001/v1?",
        "http://10.55.0.10:18001/v1#",
        "http://10.55.0.10/v1",
        "http://10.55.0.10:0/v1",
        "http://10.55.0.10:65536/v1",
        "http://010.055.000.010:18001/v1",
        "HTTP://10.55.0.10:18001/v1",
        "http://10.55.0.10:18001/%76%31",
        "http://10.55.0.10:18001/v1\n",
        "http://10.55.0.10\\@8.8.8.8:18001/v1",
        "http://[fe80::1]:18001/v1",
        "http://[::1]:18001/v1",
        "${LOCAL_ENDPOINT}",
    ],
)
def test_invalid_nonlocal_or_credential_bearing_endpoints_refuse(url):
    p = future()
    p["chat"]["endpoint"] = url
    with pytest.raises(ValueError):
        profile.checked_profile(p)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "${PROFILE}"),
        ("preset", "Future"),
        ("chat.model", "auto"),
        ("chat.model", "a model"),
        ("chat.context_length", True),
        ("chat.context_length", 4096),
        ("chat.context_length", 2**31),
        ("chat.max_output_tokens", 0),
        ("chat.max_output_tokens", 262144),
        ("chat.timeout", True),
        ("chat.timeout", 121),
        ("embedding.context_length", -1),
        ("embedding.model", "${MODEL}"),
    ],
)
def test_wrong_profile_models_and_capacities_refuse(field, value):
    p = future()
    node = p
    parts = field.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    with pytest.raises(ValueError):
        profile.checked_profile(p)


@pytest.mark.parametrize(
    "bad",
    [
        "duplicate-embedding",
        "duplicate-scheme-origin",
        "inline-key",
        "missing-slot",
        "reserved-preset-change",
    ],
)
def test_no_duplicate_origin_or_ambiguous_schema(bad):
    p = future()
    if bad == "duplicate-embedding":
        p["embedding"]["endpoint"] = p["chat"]["endpoint"]
    elif bad == "duplicate-scheme-origin":
        p["utility"]["endpoint"] = p["chat"]["endpoint"].replace("http:", "https:")
    elif bad == "inline-key":
        p["chat"]["api_key"] = "NEVER_REAL"
    elif bad == "missing-slot":
        del p["embedding"]
    else:
        p["name"] = "legacy-local-test"
    with pytest.raises(ValueError):
        profile.checked_profile(p)


def test_private_ipv6_canonical_profile_and_distinct_future_capacities():
    p = future()
    p["chat"]["endpoint"] = "https://[fd12::5]:18001/v1"
    p["utility"]["endpoint"] = p["chat"]["endpoint"]
    assert profile.checked_profile(p) == p
    assert profile.network_endpoints(p)[0] == dict(ip="fd12::5", port=18001, transport="tcp")
    assert (
        profile.profile_templates(p)["plugins/_model_config/presets.yaml"][0]["chat"]["ctx_length"] == 262144
    )


def test_profile_routes_cannot_change_network_authority(tmp_path):
    p = future()
    n = network(p, tmp_path)
    from dataclasses import replace

    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        replace(n, endpoints=profile.endpoint_urls(profile.legacy_profile())).checked()
    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        replace(n, policy=None).checked()
    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        replace(n, name="host").checked()
    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        replace(n, deployment=None).checked()


def test_product_template_selects_future_profile_without_runtime_readiness():
    p = future()
    b = compose_product(product(p))
    assert b["config"]["a0_deployment"] == p and template(b)["config"]["a0_deployment"] == p
    assert template(b)["config"]["plugins"]["entries"]["friday_rework"]["settings"]["runtime"] == {
        "enabled": False
    }
    assert b["contract"]["ready"] is False
    assert b["config"]["web"]["backend"] == "exa"
    assert b["config"]["fallback_providers"] == []


@pytest.mark.parametrize("bad", ["endpoint", "model", "context", "output", "key"])
def test_product_profile_mismatch_refuses(bad):
    spec = product(future())
    field = dict(endpoint="base_url", model="model", context="context", output="main_output", key="key_env")[
        bad
    ]
    spec["inference"][field] = {
        "endpoint": "http://10.55.0.99:18001/v1",
        "model": "foreign-model",
        "context": 131072,
        "output": 4096,
        "key": "OTHER_KEY",
    }[bad]
    with pytest.raises(ValueError):
        compose_product(spec)


def test_installer_actual_pure_input_reader_preserves_explicit_profile(install_input):
    install_input["product"] = product(future())
    installer.spec_checked(install_input)
    assert install_input["product"]["a0_deployment"] == future()
    bad = copy.deepcopy(install_input)
    bad["product"]["a0_deployment"]["chat"]["endpoint"] = "http://8.8.8.8:18001/v1"
    with pytest.raises(ValueError):
        installer.spec_checked(bad)


def prepare_future_user(env):
    p = future()
    b = compose_product(product(p))
    old = copy.deepcopy(env.template["config"])
    new = template(b)["config"]
    new["providers"]["friday-local"]["models"].update(old["providers"]["friday-local"]["models"])
    if "curator" in old:
        new["curator"] = old["curator"]
    env.template["config"].clear()
    env.template["config"].update(new)
    env.template["required_secrets"] = template(b)["required_secrets"]
    cfg = raw(env)
    cfg["plugins"]["entries"]["friday_rework"]["settings"]["onboarding"]["templates"][
        "approved-local"
    ].update(env.template)
    save(env, cfg)
    prepare(env)
    c, n = worker_inputs(env, worker="a0")
    c["a0"]["deployment"] = p
    n["endpoints"] = list(profile.endpoint_urls(p))
    return c, n


def test_real_operator_onboarding_prepares_future_native_inputs_stays_disabled(env):
    c, n = prepare_future_user(env)
    result = worker_prepare(env, worker="a0", runtime=c, network=n)
    assert result["state"] == "PREPARED_RUNTIME_UNOBSERVED" and not row(env)["enabled"]
    assert not Path(c["runtime_receipt"]["path"]).exists()
    actual = json.loads((home(env) / "workers/a0/inputs/a0-native-files.json").read_text())
    for k, v in profile.profile_templates(future()).items():
        assert actual[k] == v
    assert actual["/etc/searxng/settings.yml"]["use_default_settings"]["engines"]["keep_only"] == ["google"]
    assert {"FRIDAY_LLM_API_KEY", "FRIDAY_EMBEDDINGS_API_KEY", "EXA_API_KEY"} <= set(result["required_names"])
    configured = env.admin.onboarding_worker_configure(
        "default",
        session=env.operator,
        expected_config_sha256=cas(env),
        generation=row(env)["generation"],
        **ident(),
        worker="a0",
        preparation=result["preparation"],
        runtime_receipt=c["runtime_receipt"],
    )
    assert configured["state"] == "DISABLED_A0_RECONCILIATION_REQUIRED" and not row(env)["enabled"]


@pytest.mark.parametrize("bad", ["profile", "model", "capacity", "network", "key", "generation", "source"])
def test_operator_future_mismatch_fails_before_owned_worker_write(env, bad):
    c, n = prepare_future_user(env)
    changes = {}
    if bad == "profile":
        c["a0"]["deployment"]["name"] = "foreign-profile"
    elif bad == "model":
        c["a0"]["deployment"]["chat"]["model"] = "foreign-model"
    elif bad == "capacity":
        c["a0"]["deployment"]["chat"]["context_length"] += 1024
    elif bad == "network":
        n["endpoints"][0] = "http://10.55.0.99:18001/v1"
    elif bad == "key":
        c["a0"]["deployment"]["chat"]["api_key"] = "FORBIDDEN_INLINE_KEY"
    elif bad == "generation":
        changes["generation"] = row(env)["generation"] + 1
    else:
        c["a0"]["runtime"]["sha256"] = "0" * 64
    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        worker_prepare(env, worker="a0", runtime=c, network=n, **changes)
    assert not (home(env) / "workers/a0").exists() and not row(env)["enabled"]


def route(p, owner):
    nonce = "a" * 32
    return dict(
        schema="friday.a0.local-network.v1",
        name="frw-a0-local-" + nonce[:12],
        id="b" * 64,
        owner=owner,
        nonce=nonce,
        labels={"friday.rework.owner": owner, "friday.rework.route": nonce},
        bridge="br-frwa0local",
        endpoints=profile.network_endpoints(p),
        launcher_sha256="c" * 64,
        policy_sha256="d" * 64,
        request_sha256="e" * 64,
        guard_receipt_sha256="f" * 64,
        invocation_id="1" * 32,
        namespaces={"user": [1, 2], "mnt": [3, 4], "net": [5, 6]},
    )


def test_future_plan_hashes_original_budget_generation_network_and_renderer(tmp_path, monkeypatch):
    p = future()
    monkeypatch.setattr(runtime, "RUNTIME", tmp_path)
    params = dict(
        assignment="synthetic-portability",
        generation=1,
        owner_slot="sol",
        original_budget_seconds=300,
        network=route(p, "sol:synthetic-portability#1"),
        deployment=p,
        pins={"code_sha256": "a" * 64, "docker_sha256": "b" * 64, "daemon_unit_sha256": "c" * 64},
    )
    plan = runtime.plan(10000, 10300, **params)
    assert runtime.validate(plan, check_files=False) == plan
    assert plan["original_budget_seconds"] == 300 and plan["templates_sha256"] == runtime.digest(
        runtime.templates(p)
    )
    assert plan["profile_source_sha256"] == runtime.sha(runtime.PROFILE_SOURCE)
    other = copy.deepcopy(p)
    other["chat"]["context_length"] += 1024
    assert runtime.plan(10000, 10300, **(params | {"deployment": other}))["identity"] != plan["identity"]
    for plan_field in ("deployment", "network", "profile_source_sha256", "generation", "deadline_unix"):
        bad = copy.deepcopy(plan)
        if plan_field == "deployment":
            bad[plan_field]["chat"]["context_length"] += 1024
        elif plan_field == "network":
            bad[plan_field]["endpoints"] = runtime.LOCAL_ENDPOINTS
        elif plan_field == "profile_source_sha256":
            bad[plan_field] = "0" * 64
        else:
            bad[plan_field] += 1
        with pytest.raises((ValueError, RuntimeError, PermissionError)):
            runtime.validate(bad, check_files=False)


def test_native_actual_donor_reader_model_config_preserves_future_without_cloud(tmp_path, monkeypatch):
    """Whole original config reader; only private file/provider/import seams fake.

    Actual preset loader, validation, resolution and ModelConfig constructors run.
    Neither a client nor a model wrapper is instantiated; no key is inspected.
    """
    donor = Path(os.environ["FRW_A0_DONOR"])
    p = future()
    usr = tmp_path / "usr"
    runtime.materialize(usr, p)
    models_source = donor / "models.py"
    tree = ast.parse(models_source.read_text())
    models = ModuleType("models")
    models.__dict__.update(dataclass=dataclass, field=field, Enum=Enum)
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ("ModelType", "ModelConfig")]
    assert len(nodes) == 2
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(models_source), "exec"), models.__dict__)
    monkeypatch.setitem(sys.modules, "models", models)
    helper = ModuleType("helpers")
    helper.__path__ = []
    memory = {}
    helper.cache = NS(
        get=lambda area, sig: memory.get((area, sig)),
        add=lambda area, sig, v: memory.update({(area, sig): v}),
    )
    helper.defer = NS()

    def path(*parts):
        return str(Path(*parts))

    helper.files = NS(
        USER_DIR=str(usr),
        PLUGINS_DIR="plugins",
        get_abs_path=path,
        exists=lambda p: Path(p).is_file(),
        read_file=lambda p: Path(p).read_text(),
        read_file_json=lambda p: json.loads(Path(p).read_text()),
    )
    helper.plugins = NS(
        CONFIG_FILE_NAME="config.json",
        find_plugin_dir=lambda name: str(donor / "plugins" / name),
        determine_plugin_asset_path=lambda name, *args: str(
            usr / "plugins" / name / (args[-1] or "config.json")
        ),
        get_plugin_config=lambda *args, **kwargs: json.loads(
            (usr / "plugins/_model_config/config.json").read_text()
        ),
    )
    monkeypatch.setitem(sys.modules, "helpers", helper)
    extension = ModuleType("helpers.extension")
    extension.call_extensions_async = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, extension.__name__, extension)
    providers = ModuleType("helpers.providers")
    providers.get_provider_config = lambda *a: None
    providers.get_providers = lambda *a: []
    monkeypatch.setitem(sys.modules, providers.__name__, providers)
    yamlmod = ModuleType("helpers.yaml")
    exec(
        compile((donor / "helpers/yaml.py").read_text(), str(donor / "helpers/yaml.py"), "exec"),
        yamlmod.__dict__,
    )
    helper.yaml = yamlmod
    monkeypatch.setitem(sys.modules, yamlmod.__name__, yamlmod)
    reader = ModuleType("synthetic_native_a0_reader")
    source = donor / "plugins/_model_config/helpers/model_config.py"
    exec(compile(source.read_text(), str(source), "exec"), reader.__dict__)
    configured = reader.get_configured_preset_name(agent_profile="agent0", project_name=None)
    cfg = reader.get_config(agent_profile="agent0", project_name=None)
    preset = runtime.templates(p)["plugins/_model_config/presets.yaml"][0]
    runtime.probe_config_checked(cfg, configured, preset, preset["name"])
    for k in ("chat", "utility", "embedding"):
        mc = reader.build_model_config(
            cfg[k + "_model"], models.ModelType.EMBEDDING if k == "embedding" else models.ModelType.CHAT
        )
        assert (
            mc.name == p[k]["model"]
            and mc.api_base == p[k]["endpoint"]
            and mc.ctx_length == p[k]["context_length"]
        )
        assert mc.api_key == "" and mc.provider == ("other" if k == "embedding" else "openai")
    assert cfg["vision_model"] == {} and configured == "Default"


@pytest.mark.parametrize("bad", [None, "model", "endpoint", "context", "output", "key", "scope"])
def test_future_probe_reports_exact_selection_and_refuses_stale_observations(bad):
    from test_a0_runtime import NativeProbeControls, a0

    case = NativeProbeControls()
    case.setUp()
    try:
        p = future()
        native = runtime.templates(p)
        for name, value in native.items():
            (case.usr / name).write_text(json.dumps(value))
        preset = native["plugins/_model_config/presets.yaml"][0]
        case.cfg.update({s + "_model": copy.deepcopy(preset[s]) for s in ("chat", "utility", "embedding")})
        report = a0.native_probe(p)
        assert a0.probe_report_checked(report, p) == report and report["temporary_test"] is False
        assert report["hard_total_prompt_bound"] is False
        if bad is None:
            script = a0.probe_script(p)
            compile(script, "synthetic_future_probe", "exec")
            assert "synthetic-future-local" in script and "262144" in script
            with pytest.raises((ValueError, RuntimeError, PermissionError)):
                a0.probe_report_checked(report)
        else:
            stale = copy.deepcopy(report)
            if bad in ("model", "endpoint", "context", "output"):
                key = {
                    "model": "name",
                    "endpoint": "api_base",
                    "context": "ctx_length",
                    "output": "max_tokens",
                }[bad]
                stale["slots"]["chat"][key] = "foreign" if bad in ("model", "endpoint") else 1
            elif bad == "key":
                stale["key_ready"]["other"] = False
            else:
                stale["scope"] = "foreign/project"
            with pytest.raises((ValueError, RuntimeError, PermissionError)):
                a0.probe_report_checked(stale, p)
    finally:
        case.doCleanups()


def test_future_scoped_key_reference_mismatch_is_categorical_before_write(env):
    c, n = prepare_future_user(env)
    config = copy.deepcopy(env.template["config"])
    config["providers"]["friday-local"]["key_env"] = "FOREIGN_KEY"
    for route in config["auxiliary"].values():
        if isinstance(route, dict) and route.get("enabled") is not False:
            route["key_env"] = "FOREIGN_KEY"
    config["delegation"]["key_env"] = "FOREIGN_KEY"
    from friday_admin_controls.worker_provision import prepare_inputs

    with pytest.raises((ValueError, RuntimeError, PermissionError), match="a0_scoped_profile_key_mismatch"):
        prepare_inputs(home(env), "user-1", "a0", c, config, a0_network=n)
    assert not (home(env) / "workers/a0").exists()


def test_runtime_cannot_load_a_foreign_profile_renderer(tmp_path):
    from plugins.friday_rework.host_runtime import A0HostSession, HostUnavailable

    script = tmp_path / "scripts/a0_runtime.py"
    script.parent.mkdir()
    script.write_bytes((Q / "scripts/a0_runtime.py").read_bytes())
    helper = tmp_path / "plugins/friday_rework/adapters/a0_profile.py"
    helper.parent.mkdir(parents=True)
    helper.write_text('raise AssertionError("foreign helper must never execute")')
    session = object.__new__(A0HostSession)
    session.config = {
        "a0": {"runtime": {"path": str(script), "sha256": hashlib.sha256(script.read_bytes()).hexdigest()}}
    }
    with pytest.raises(HostUnavailable, match="a0_runtime_profile_source_mismatch"):
        session._module()
