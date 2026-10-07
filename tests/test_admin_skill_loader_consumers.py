"""Actual aliases, linked files and native plugin registration honor skill policy."""
import json
from pathlib import Path

import pytest
from test_admin_skill_loader import env, local_config, install, raw, managed, visible, load


@pytest.mark.parametrize("layer", ["raw", "managed"])
@pytest.mark.parametrize("scope", ["global", "telegram"])
@pytest.mark.parametrize("target", ["shared", "category/one"])
@pytest.mark.parametrize("alias", ["category/one", "category:one", "one"])
def test_denied_alias_never_serves_linked_content_or_preprocesses(env, monkeypatch, layer, scope, target, alias):
    from tools import skills_tool, skills_tool_plugin
    local_config(env); install(env)
    p = env.home / "skills/category/one/references/private.md"
    p.parent.mkdir(); p.write_text("DO_NOT_SERVE_SYNTHETIC_CONTENT")
    policy = {"disabled": [f"\t {target} \n"]} if scope == "global" else {"platform_disabled": {scope: [f"\t {target} \n"]}}
    (raw(env, policy) if layer == "raw" else managed(env, monkeypatch, policy))
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    original = skills_tool_plugin._read_skill_text
    reads = []
    def read(path):
        reads.append(str(path))
        assert Path(path) != p, "Denied support file was opened"
        return original(path)
    monkeypatch.setattr(skills_tool_plugin, "_read_skill_text", read)
    # The local lookup reads SKILL.md metadata to identify a copy. It must never
    # serve support bytes or run activation/preprocessing after a denied match.
    calls = []
    monkeypatch.setattr(skills_tool, "_preprocess_skill", lambda *a: calls.append(a) or "UNEXPECTED")
    for file_path in [None, "references/private.md"]:
        result = json.loads(skills_tool.skill_view(alias, file_path=file_path, preprocess=True))
        assert result["success"] is False and "disabled" in result["error"].lower()
        assert "content" not in result and "DO_NOT_SERVE" not in json.dumps(result)
    assert not calls and str(p) not in reads
    assert ("category/two" in visible()) is (target != "shared")
    assert load("other")["success"]


def plugin_fixture(env, monkeypatch):
    from hermes_cli import plugins
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    pm = PluginManager()
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: pm)
    monkeypatch.setattr(plugins, "discover_plugins", lambda: None)
    ctx = PluginContext(PluginManifest(name="fixtureplug", version="1.0", source="user", description="Synthetic plugin"), pm)
    for name in ["one", "two"]:
        p = env.home / "plugin-fixture" / name / "SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text(f"---\nname: shared\ndescription: Fixture plugin\n---\nPLUGIN_USEFUL:{name}\n")
        support = p.parent / "references/note.md"; support.parent.mkdir(); support.write_text(f"PLUGIN_SUPPORT:{name}")
        ctx.register_skill(name, p, description="Fixture plugin", frontmatter={"name": "shared"})
    assert pm.find_plugin_skill("fixtureplug:one") is not None
    return pm


@pytest.mark.parametrize("layer", ["raw", "managed"])
@pytest.mark.parametrize("scope", ["global", "telegram"])
@pytest.mark.parametrize("value", [["\t fixtureplug:one \n"], '[" fixtureplug:one "]'])
def test_actual_registry_deny_precedes_plugin_content_reads(env, monkeypatch, layer, scope, value):
    from tools import skills_tool, skills_tool_plugin
    local_config(env); pm = plugin_fixture(env, monkeypatch)
    policy = {"disabled": value} if scope == "global" else {"platform_disabled": {scope: value}}
    (raw(env, policy) if layer == "raw" else managed(env, monkeypatch, policy))
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    denied_root = pm.find_plugin_skill("fixtureplug:one").parent
    original = skills_tool_plugin._read_skill_text
    def read(path):
        assert not Path(path).is_relative_to(denied_root), "Disabled registered plugin content was read"
        return original(path)
    monkeypatch.setattr(skills_tool_plugin, "_read_skill_text", read)
    listed = json.loads(skills_tool.skills_list())
    assert "fixtureplug:one" not in {s["name"] for s in listed["skills"]}
    assert "fixtureplug:two" in {s["name"] for s in listed["skills"]}
    for file_path in [None, "references/note.md"]:
        result = json.loads(skills_tool.skill_view("fixtureplug:one", file_path=file_path, preprocess=False))
        assert result["success"] is False and "disabled" in result["error"].lower() and "content" not in result
    assert "PLUGIN_USEFUL:two" in load("fixtureplug:two")["content"]
    assert "PLUGIN_SUPPORT:two" in json.loads(skills_tool.skill_view("fixtureplug:two", file_path="references/note.md", preprocess=False))["content"]


@pytest.mark.parametrize("entry", ["*", "fixtureplug:*", "one", "shared", "hermes-agent"])
def test_plugin_qualified_names_keep_literal_namespace_semantics(env, monkeypatch, entry):
    local_config(env); plugin_fixture(env, monkeypatch)
    managed(env, monkeypatch, {"platform_disabled": {"telegram": [entry]}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    answer = load("fixtureplug:one")
    assert answer["success"] and "PLUGIN_USEFUL:one" in answer["content"]


def test_unique_skill_directory_alias_is_not_a_duplicate_load_deny(env, monkeypatch):
    local_config(env)
    p = env.home / "skills/category/one/SKILL.md"; p.parent.mkdir(parents=True)
    p.write_text("---\nname: unique\ndescription: Fixture\n---\nUNIQUE_USEFUL\n")
    raw(env, {"disabled": [" category/one "]})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    assert visible() == {"unique"}
    for alias in ["unique", "one", "category/one", "category:one"]:
        assert "UNIQUE_USEFUL" in load(alias)["content"]
    raw(env, {"disabled": [" unique "]})
    for alias in ["unique", "one", "category/one", "category:one"]:
        assert load(alias)["success"] is False


@pytest.mark.parametrize("platform", ["telegram", "discord"])
def test_effective_platform_precedence_and_other_platform_grant(env, monkeypatch, platform):
    from tools.skills_tool import _is_skill_disabled
    local_config(env); install(env)
    raw(env, {"platform_disabled": {"telegram": [" shared "], "discord": [" other "]}})
    monkeypatch.setenv("HERMES_PLATFORM", platform)
    assert _is_skill_disabled("shared", platform="telegram")
    assert not _is_skill_disabled("shared", platform="discord")
    assert load("category/one")["success"] is (platform == "discord")
    assert load("other")["success"] is (platform == "telegram")


def test_reader_failure_cannot_fail_open_on_actual_content(env, monkeypatch):
    local_config(env); install(env)
    raw(env, {"platform_disabled": "invalid mapping"})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    answer = load("category/one")
    assert answer["success"] is False and "content" not in answer


@pytest.mark.parametrize("kind", ["local", "plugin"])
@pytest.mark.parametrize("layer", ["raw", "managed"])
@pytest.mark.parametrize("scope", ["global", "telegram"])
def test_registered_repeat_view_rechecks_current_effective_deny(env, monkeypatch, kind, layer, scope):
    from tools import skills_tool
    from tools.registry import registry
    local_config(env); monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    skills_tool.reset_skill_view_dedup()
    if kind == "plugin":
        plugin_fixture(env, monkeypatch); name = "fixtureplug:one"
    else:
        p = env.home / "skills/unique/SKILL.md"; p.parent.mkdir(parents=True)
        p.write_text("---\nname: unique\ndescription: Fixture\n---\nUNIQUE_USEFUL\n"); name = "unique"
    def view():
        answer = registry.dispatch("skill_view", {"name": name}, task_id="synthetic-retained-view")
        return json.loads(answer) if isinstance(answer, str) else answer
    first = view(); second = view()
    assert first["success"] and first["content"] and second["dedup"]
    policy = {"disabled": [f" {name} "]} if scope == "global" else {"platform_disabled": {scope: [f" {name} "]}}
    (raw(env, policy) if layer == "raw" else managed(env, monkeypatch, policy))
    denied = view()
    with (Path(__import__("os").environ.get("FRIDAY_FIXTURE_EVIDENCE", env.home.parent)) / "retained-registry-observations.jsonl").open("a") as f:
        f.write(json.dumps({"kind": kind, "layer": layer, "scope": scope, "first": first, "second": second, "after_deny": denied}) + "\n")
    assert denied["success"] is False and "disabled" in denied["error"].lower() and "content" not in denied
    (raw(env, {}) if layer == "raw" else managed(env, monkeypatch, {}))
    restored = view()
    assert restored["success"] and restored["content"]
