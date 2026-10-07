"""Persist actual native observations before checking the assigned load contract."""
import json
from pathlib import Path

import pytest
from test_admin_skill_loader import env, session, body, local_config, install, raw, managed, visible, load

def record(env, name, **fields):
    root = Path(__import__("os").environ.get("FRIDAY_FIXTURE_EVIDENCE", env.home.parent))
    with (root / "load-observations.jsonl").open("a") as f:
        f.write(json.dumps({"case": name, **fields}, ensure_ascii=False) + "\n")


@pytest.mark.parametrize("layer", ["raw", "managed"])
@pytest.mark.parametrize("padding", ["{}", " {} ", "\t{}\n"])
def test_actual_catalog_and_explicit_load_agree_under_native_denial(env, monkeypatch, layer, padding):
    from agent import skill_utils
    from tools import skills_tool
    local_config(env); install(env)
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    policy = {"platform_disabled": {"telegram": [padding.format("shared")]}}
    (raw(env, policy) if layer == "raw" else managed(env, monkeypatch, policy))
    shown = visible(); answer = load("category/one")
    disabled_before = sorted(skill_utils.get_disabled_skill_names())
    predicate_before = skills_tool._is_skill_disabled("shared", "category/one")
    before = (env.home / "config.yaml").read_bytes()
    try:
        edited = env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=True), session())
    except (PermissionError, ValueError) as e:
        edited = {"refused": str(e)}
    record(env, f"{layer}:{padding!r}", visible=sorted(shown), disabled_before=disabled_before, native_load=answer, native_predicate_before=predicate_before, typed_edit=edited, raw_unchanged=(env.home / "config.yaml").read_bytes() == before,
           reader_file=skill_utils.__file__, loader_file=skills_tool.__file__)
    if layer == "managed":
        assert "refused" in edited and (env.home / "config.yaml").read_bytes() == before
    else:
        assert edited["recorded"] and load("category/one")["success"]
    assert "category/one" not in shown
    assert answer["success"] is False, "Explicit native load must enforce the catalog's native denial"


def test_actual_essential_catalog_and_explicit_load_agree(env, monkeypatch):
    local_config(env); install(env, declared="hermes-agent")
    raw(env, {"disabled": ["hermes-agent", "category/two", "other"], "platform_disabled": {}})
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    shown = visible(); answer = load("category/one")
    record(env, "essential", visible=sorted(shown), native_load=answer)
    assert shown == {"category/one"}
    assert answer["success"] is True, "The native essential exemption must also apply on explicit load"
