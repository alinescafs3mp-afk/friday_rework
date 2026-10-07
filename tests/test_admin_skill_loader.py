"""Independent native catalog/load and supported typed edit observations."""
import copy
import json

import pytest
from test_admin_foundation import env, session
from test_admin_controls import body, local_config


def install(env, declared="shared"):
    for rel, name in (("category/one", declared), ("category/two", declared), ("other", "other")):
        p = env.home / "skills" / rel
        p.mkdir(parents=True)
        (p / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Independent synthetic {rel}\n---\nUSEFUL:{rel}\n")


def raw(env, skills):
    from hermes_cli import config
    value = config.require_readable_config_before_write()
    value["skills"] = skills
    config.atomic_config_replace(env.home / "config.yaml", value)


def managed(env, monkeypatch, policy):
    from hermes_cli import managed_scope
    p = env.home / "managed"
    p.mkdir(exist_ok=True)
    (p / "config.yaml").write_text(json.dumps({"skills": policy}))
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(p))
    managed_scope.invalidate_managed_cache()


def visible():
    from tools.skills_tool import _find_all_skills
    return {r["name"] for r in _find_all_skills()}


def load(name):
    from tools.skills_tool import skill_view
    return json.loads(skill_view(name, preprocess=False))


@pytest.mark.parametrize("padding", ["\u00a0{}\u00a0", "\u2028{}\u2029", "\t {} \r\n"])
@pytest.mark.parametrize("target", ["shared", "category/one"])
@pytest.mark.parametrize("platform", ["telegram", "discord"])
def test_managed_denial_is_observed_by_actual_load_and_enable_is_honest(env, monkeypatch, padding, target, platform):
    local_config(env); install(env)
    managed(env, monkeypatch, {"platform_disabled": {platform: [padding.format(target)], "unrelated-platform": ["other"]}})
    monkeypatch.setenv("HERMES_PLATFORM", platform)
    assert "category/one" not in visible()
    assert load("category/one")["success"] is False
    before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(PermissionError, match="effective_native_skill_denied"):
        env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=True), session())
    assert (env.home / "config.yaml").read_bytes() == before
    assert load("category/one")["success"] is False
    assert ("category/two" in visible()) is (target != "shared")
    assert load("other")["success"] is True


@pytest.mark.parametrize("layer", ["global", "platform", "both"])
@pytest.mark.parametrize("target", [" shared ", "\tcategory/one\r\n"])
def test_normalized_enable_changes_actual_load_and_preserves_every_peer(env, monkeypatch, layer, target):
    from hermes_cli import config
    local_config(env); install(env)
    names = [target, " category/two ", " other ", "*", "shar*", "UNRELATED"]
    policy = {"disabled": names if layer != "platform" else [], "platform_disabled": {"telegram": names[:] if layer != "global" else []}}
    raw(env, policy); monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert visible() == set()
    answer = env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=True), session())
    assert answer["recorded"] and visible() == {"category/one"}
    selected = load("category/one")
    assert selected["success"] and "USEFUL:category/one" in selected["content"]
    assert load("category/two")["success"] is False and load("other")["success"] is False
    reread = config.require_readable_config_before_write()
    for names_after in [reread["skills"]["disabled"], reread["skills"]["platform_disabled"]["telegram"]]:
        if names_after:
            assert {"*", "shar*", "UNRELATED", " other "} <= set(names_after)
    before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(ValueError, match="native_config_changed"):
        env.admin.write_settings("default", {"kind": "skill", "values": {"name": "category/two", "enabled": True}, "expected_sha256": "0" * 64}, session())
    assert (env.home / "config.yaml").read_bytes() == before


@pytest.mark.parametrize("pattern", ["*", "shar*", "SHARED", "shared\u200b"])
def test_native_literal_nonmatching_names_do_not_invent_wildcard_denial(env, monkeypatch, pattern):
    local_config(env); install(env)
    managed(env, monkeypatch, {"platform_disabled": {"telegram": [pattern]}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    before = visible()
    assert before == {"category/one", "category/two", "other"}
    assert env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=True), session())["recorded"]
    assert visible() == before and load("category/one")["success"]


@pytest.mark.parametrize("malformed", [[], ["shared"], "", "malformed", False, True, None, 0, 3.5])
def test_legacy_nonmapping_reader_and_managed_reload_keep_cache_and_useful_load(env, monkeypatch, malformed):
    from agent import skill_utils
    local_config(env); install(env); raw(env, malformed)
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    cached = skill_utils._load_raw_config(); snapshot = copy.deepcopy(cached)
    assert visible() == {"category/one", "category/two", "other"}
    assert load("category/one")["success"]
    managed(env, monkeypatch, {"platform_disabled": {"telegram": [" shared "]}})
    assert visible() == {"other"} and load("category/one")["success"] is False
    assert cached == snapshot and skill_utils._load_raw_config() is cached
    managed(env, monkeypatch, {})
    assert visible() == {"category/one", "category/two", "other"} and load("category/one")["success"]
    assert cached == snapshot and skill_utils._load_raw_config() is cached


def test_essential_display_exemption_keeps_specific_duplicate_deny_and_other_policy(env, monkeypatch):
    local_config(env); install(env, declared="hermes-agent")
    raw(env, {"disabled": [" hermes-agent ", " category/two ", "other"], "platform_disabled": {}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert visible() == {"category/one"} and load("category/one")["success"]
    assert env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=True), session())["recorded"]
    assert visible() == {"category/one"}
    before = (env.home / "config.yaml").read_bytes()
    with pytest.raises(ValueError, match="native_required_skill"):
        env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=False), session())
    assert (env.home / "config.yaml").read_bytes() == before
    assert load("category/two")["success"] is False and load("other")["success"] is False
