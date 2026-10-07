"""Real typed enable and explicit native load for essential-name policy."""
import json
from pathlib import Path
import pytest
from test_admin_skill_loader import env, session, body, local_config, install, raw, managed, visible, load


@pytest.mark.parametrize("layer", ["raw", "managed"])
def test_recorded_essential_enable_must_leave_the_selected_native_skill_loadable(env, monkeypatch, layer):
    local_config(env); install(env, declared="hermes-agent")
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    raw(env, {"disabled": ["category/two", "other"], "platform_disabled": {}})
    policy = {"platform_disabled": {"telegram": ["hermes-agent"]}}
    if layer == "raw":
        raw(env, {"disabled": ["category/two", "other"], **policy})
    else:
        managed(env, monkeypatch, policy)
    before = visible()
    answer = env.admin.write_settings("default", body(env, "skill", name="category/one", enabled=True), session())
    loaded = load("category/one")
    with (Path(__import__("os").environ.get("FRIDAY_FIXTURE_EVIDENCE", env.home.parent)) / "essential-enable-observations.jsonl").open("a") as f:
        f.write(json.dumps({"layer": layer, "visible_before": sorted(before), "visible_after": sorted(visible()), "typed_edit": answer, "native_load": loaded}) + "\n")
    assert before == {"category/one"} and visible() == before and answer["recorded"]
    assert loaded["success"] is True, "Recorded enable and essential catalog exemption must agree with explicit native load"
