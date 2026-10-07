"""Resolved linked-file identity at the native registry/model_tools boundary."""
import json
import os
from pathlib import Path

import pytest

from test_skill_cache_identity import env, local_config, plugin_fixture, put, raw, reg, reset


def support_fixture(env, monkeypatch, kind):
    local_config(env)
    reset()
    if kind == "plugin":
        manager = plugin_fixture(env, monkeypatch)
        name = "fixtureplug:one"
        root = manager.find_plugin_skill(name).parent
    else:
        root = put(env, "category/one", "unique", "MAIN").parent
        name = "unique"
    a, b, link = [root / "references" / part for part in ("a.md", "b.md", "alias.md")]
    a.write_text("AAAA")
    b.write_text("BBBB")
    for target in (a, b):
        os.utime(target, ns=(1700000000000000000, 1700000000000000000))
    assert (a.stat().st_mtime_ns, a.stat().st_size) == (b.stat().st_mtime_ns, b.stat().st_size)
    link.symlink_to(a.name)
    return name, root, a, b, link


def call(name, boundary="registry"):
    if boundary == "registry":
        return reg(name, file="references/alias.md")
    from model_tools import handle_function_call
    result = handle_function_call(
        "skill_view", {"name": name, "file_path": "references/alias.md"},
        task_id="support-identity", session_id="synthetic-only")
    return json.loads(result) if isinstance(result, str) else result


@pytest.mark.parametrize("kind", ["local", "plugin"])
@pytest.mark.parametrize("boundary", ["registry", "model_tools"])
def test_support_retarget_equal_stat_returns_new_content(env, monkeypatch, kind, boundary):
    name, root, a, b, link = support_fixture(env, monkeypatch, kind)
    from tools import skills_tool_plugin
    original = skills_tool_plugin._read_skill_text
    support_reads = []

    def read(path):
        if Path(path).name != "SKILL.md":
            support_reads.append(str(Path(path).resolve()))
        return original(path)

    monkeypatch.setattr(skills_tool_plugin, "_read_skill_text", read)
    assert call(name, boundary)["content"] == "AAAA"
    assert call(name, boundary)["dedup"]
    assert support_reads == [str(a)]  # Identity/check never reads a support body.
    link.unlink()
    link.symlink_to(b.name)
    from tools.skills_tool import skill_view
    direct = json.loads(skill_view(name, file_path="references/alias.md", preprocess=False))
    assert direct["content"] == "BBBB"
    result = call(name, boundary)
    assert result.get("content") == "BBBB" and not result.get("dedup")
    assert result["_skill_identity"][-1] == str(b.resolve())
    assert call(name, boundary)["dedup"]
    assert support_reads == [str(a), str(b), str(b)]


@pytest.mark.parametrize("kind", ["local", "plugin"])
@pytest.mark.parametrize("denial", ["outside", "foreign", "missing", "directory", "disabled"])
def test_warm_support_refusal_precedes_body_read(env, monkeypatch, kind, denial):
    name, root, a, b, link = support_fixture(env, monkeypatch, kind)
    assert call(name)["content"] == "AAAA"
    assert call(name)["dedup"]
    if denial == "disabled":
        raw(env, {"disabled": ["\t " + name + " \n"]})
    else:
        link.unlink()
        if denial == "outside":
            target = env.home / "outside.md"
            target.write_text("DENIED_BODY")
        elif denial == "foreign":
            target = put(env, "foreign", "foreign", "FOREIGN_MAIN").parent / "references/detail.md"
        elif denial == "directory":
            target = root / "references"
        else:
            target = root / "references/missing.md"
        link.symlink_to(target)
    from tools import skills_tool_plugin
    original = skills_tool_plugin._read_skill_text
    reads = []

    def read(path):
        if Path(path).name != "SKILL.md":
            reads.append(str(path))
            raise AssertionError("Refused support body must not be read")
        return original(path)

    monkeypatch.setattr(skills_tool_plugin, "_read_skill_text", read)
    result = call(name)
    assert result["success"] is False and "content" not in result and not result.get("dedup")
    assert reads == []


@pytest.mark.parametrize("alias", ["unique", "one", "category/one", "category:one"])
def test_skill_aliases_still_dedup_the_same_support_source(env, monkeypatch, alias):
    name, root, a, b, link = support_fixture(env, monkeypatch, "local")
    assert call(name)["content"] == "AAAA"
    assert call(alias)["dedup"]
    link.unlink()
    link.symlink_to(b.name)
    assert call(alias)["content"] == "BBBB"
    assert call(name)["dedup"]
