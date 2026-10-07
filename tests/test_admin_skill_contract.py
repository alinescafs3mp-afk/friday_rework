"""Typed enable and actual native catalog agree, including legacy skill policy."""
import copy
import json

import pytest

from test_admin_foundation import env, session
from test_admin_controls import body, local_config


def install(env, *, duplicate=False, declared="fixture"):
    for directory in ("one", "two") if duplicate else ("fixture",):
        path = env.home / "skills" / directory
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            f"---\nname: {declared}\ndescription: Synthetic fixture\n---\nInstructions.\n")


def configure(env, skills):
    from hermes_cli import config
    cfg = config.require_readable_config_before_write()
    cfg["skills"] = skills
    # Deliberately replace the whole skills section, including malformed legacy
    # values; ordinary partial writes must retain the native omission guard.
    config.atomic_config_replace(env.home / "config.yaml", cfg)


def managed(env, monkeypatch, skills):
    from hermes_cli import managed_scope
    directory = env.home / "managed"
    directory.mkdir(exist_ok=True)
    (directory / "config.yaml").write_text(json.dumps({"skills": skills}))
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(directory))
    managed_scope.invalidate_managed_cache()


def visible():
    from tools.skills_tool import _find_all_skills
    return {row["name"] for row in _find_all_skills()}


@pytest.mark.parametrize("padding", [" {} ", "\t{}\t", "\r\n{}\v\f", "\u2003{}\u2003"])
@pytest.mark.parametrize("target", ["fixture", "one"])
@pytest.mark.parametrize("scope", ["global", "telegram", "discord"])
def test_managed_normalized_deny_refuses_enable_without_write(env, monkeypatch, padding, target, scope):
    from agent.skill_utils import get_disabled_skill_names
    local_config(env)
    install(env, duplicate=True)
    names = [padding.format(target)]
    policy = {"disabled": names} if scope == "global" else {"platform_disabled": {scope: names}}
    managed(env, monkeypatch, policy)
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert target in get_disabled_skill_names(platform="telegram" if scope == "global" else scope)
    assert ("one" in visible()) is (scope == "discord")
    before = (env.home / "config.yaml").read_bytes()
    refusal = "administrator_managed_key" if scope == "global" else "effective_native_skill_denied"
    with pytest.raises(PermissionError, match=refusal):
        env.admin.write_settings("default", body(env, "skill", name="one", enabled=True), session())
    assert (env.home / "config.yaml").read_bytes() == before
    monkeypatch.setenv("HERMES_PLATFORM", "telegram" if scope == "global" else scope)
    assert "one" not in visible()
    assert ("two" in visible()) is (target == "one")


@pytest.mark.parametrize("padding", ["{}", " {} ", "\t{}\r\n", "\u2003{}\u2003"])
@pytest.mark.parametrize("target", ["fixture", "one"])
def test_raw_normalized_enable_preserves_duplicate_peer(env, monkeypatch, padding, target):
    from hermes_cli import config
    local_config(env)
    install(env, duplicate=True)
    names = [padding.format(target), " unrelated "]
    if target == "one":
        names.append(" two ")
    configure(env, {"disabled": names, "platform_disabled": {"telegram": names[:]}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert visible() == set()
    answer = env.admin.write_settings("default", body(env, "skill", name="one", enabled=True), session())
    assert answer["recorded"] is True
    assert visible() == {"one"}
    cfg = config.require_readable_config_before_write()
    assert " unrelated " in cfg["skills"]["disabled"]
    monkeypatch.setenv("HERMES_PLATFORM", "discord")
    assert visible() == {"one"}


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("layer", ["raw", "managed"])
@pytest.mark.parametrize("padding", ["{}", "\t{}\n"])
def test_enable_keeps_native_essential_exemption_without_disabling_peers(env, monkeypatch, duplicate, layer, padding):
    local_config(env)
    install(env, duplicate=duplicate, declared="hermes-agent")
    policy = {"disabled": [padding.format("hermes-agent")], "platform_disabled": {"telegram": [padding.format("hermes-agent")]}}
    if layer == "managed":
        managed(env, monkeypatch, {"platform_disabled": policy["platform_disabled"]})
    else:
        configure(env, policy)
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    expected = {"one", "two"} if duplicate else {"hermes-agent"}
    assert visible() == expected
    answer = env.admin.write_settings("default", body(env, "skill", name="one" if duplicate else "hermes-agent", enabled=True), session())
    assert answer["recorded"] is True
    assert visible() == expected


@pytest.mark.parametrize("name", ["fix\tture", "fixture\u200b", "FIXTURE", "unrelated"])
def test_native_nonmatching_names_do_not_false_deny_enable(env, monkeypatch, name):
    local_config(env)
    install(env)
    managed(env, monkeypatch, {"platform_disabled": {"telegram": [name, "", " \t "]}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert visible() == {"fixture"}
    answer = env.admin.write_settings("default", body(env, "skill", name="fixture", enabled=True), session())
    assert answer["recorded"] is True
    assert visible() == {"fixture"}


def test_essential_declared_name_does_not_exempt_specific_duplicate_load_deny(env, monkeypatch):
    local_config(env)
    install(env, duplicate=True, declared="hermes-agent")
    managed(env, monkeypatch, {"platform_disabled": {"telegram": [" one ", " hermes-agent "]}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert visible() == {"two"}
    before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(PermissionError, match="effective_native_skill_denied"):
        env.admin.write_settings("default", body(env, "skill", name="one", enabled=True), session())
    assert (env.home / "config.yaml").read_bytes() == before
    assert visible() == {"two"}


@pytest.mark.parametrize("malformed", [[], "", False, None, 0, "invalid"])
@pytest.mark.parametrize("scope", [None, "global", "telegram"])
def test_nonmapping_native_skills_tolerated_with_managed_overlay(env, monkeypatch, malformed, scope):
    from agent import skill_utils
    local_config(env)
    install(env)
    configure(env, malformed)
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    raw = skill_utils._load_raw_config()
    before = copy.deepcopy(raw)
    if scope:
        policy = {"disabled": [" fixture "]} if scope == "global" else {"platform_disabled": {scope: ["\tfixture\n"]}}
        managed(env, monkeypatch, policy)
    assert skill_utils.get_disabled_skill_names() == ({"fixture"} if scope else set())
    assert visible() == (set() if scope else {"fixture"})
    assert raw == before
    assert skill_utils._load_raw_config() is raw
    if scope:
        managed(env, monkeypatch, {})
        assert visible() == {"fixture"}
