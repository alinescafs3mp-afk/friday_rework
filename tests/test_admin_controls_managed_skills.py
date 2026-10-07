import json
from test_admin_foundation import env,session
from test_admin_controls import local_config,body


def test_enable_cannot_bypass_existing_managed_platform_skill_deny(env,monkeypatch):
    from hermes_cli import config,managed_scope
    from tools.skills_tool import _find_all_skills
    local_config(env);skill=env.home/'skills/fixture';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('Synthetic skill')
    cfg=config.require_readable_config_before_write();cfg['skills']['disabled']=['fixture'];config.atomic_config_write(env.home/'config.yaml',cfg)
    directory=env.home/'managed';directory.mkdir();(directory/'config.yaml').write_text(json.dumps({'skills':{'platform_disabled':{'telegram':['fixture']}}}))
    monkeypatch.setenv('HERMES_MANAGED_DIR',str(directory));monkeypatch.setenv('HERMES_PLATFORM','telegram');managed_scope.invalidate_managed_cache()
    assert 'fixture' not in [row['name'] for row in _find_all_skills()]
    before=(env.home/'config.yaml').read_bytes()
    try:answer=env.admin.write_settings('default',body(env,'skill',name='fixture',enabled=True),session())
    except (ValueError,PermissionError):
        assert (env.home/'config.yaml').read_bytes()==before;return
    effective=config.load_config_readonly();assert effective['skills']['platform_disabled']['telegram']==['fixture']
    assert 'fixture' not in [row['name'] for row in _find_all_skills()], 'Typed enable crossed managed Telegram skill deny; native skill previously absent now available, response='+repr(answer)


def test_native_catalog_enforces_managed_deny_without_raw_shadow(env,monkeypatch):
    from hermes_cli import managed_scope
    from tools.skills_tool import _find_all_skills
    local_config(env)
    skill=env.home/'skills/fixture';skill.mkdir(parents=True)
    (skill/'SKILL.md').write_text('Synthetic skill')
    assert 'fixture' in [row['name'] for row in _find_all_skills()]
    directory=env.home/'managed';directory.mkdir()
    (directory/'config.yaml').write_text(json.dumps({'skills':{'platform_disabled':{'telegram':['fixture']}}}))
    monkeypatch.setenv('HERMES_MANAGED_DIR',str(directory));monkeypatch.setenv('HERMES_PLATFORM','telegram')
    managed_scope.invalidate_managed_cache()
    assert 'fixture' not in [row['name'] for row in _find_all_skills()]
    monkeypatch.setenv('HERMES_PLATFORM','discord')
    assert 'fixture' in [row['name'] for row in _find_all_skills()]
