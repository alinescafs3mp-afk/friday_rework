import json
from types import SimpleNamespace
import pytest
from test_admin_foundation import env,session
from test_admin_controls import local_config,body

@pytest.mark.parametrize('layer',['raw','managed'])
@pytest.mark.parametrize('escape',['endpoint','fallback'])
def test_enabled_delegation_uses_only_local_inference(env,monkeypatch,layer,escape):
    from hermes_cli import config,managed_scope
    from tools.delegate_tool_config import _load_config,_resolve_delegation_credentials,_resolve_child_fallback_chain
    from model_tools import _select_tool_names
    local_config(env);cfg=config.require_readable_config_before_write()
    cfg['platform_toolsets']['telegram']=['web','delegation']
    delta={'provider':'','base_url':'https://synthetic-inference.invalid/v1','model':'synthetic-cloud','api_mode':'chat_completions'} if escape=='endpoint' else {'fallback_providers':[{'provider':'openrouter','model':'synthetic-cloud'}]}
    if layer=='raw':cfg['delegation'].update(delta)
    else:
        directory=env.home/'managed';directory.mkdir();(directory/'config.yaml').write_text(json.dumps({'delegation':delta}))
        monkeypatch.setenv('HERMES_MANAGED_DIR',str(directory));managed_scope.invalidate_managed_cache()
    config.atomic_config_write(env.home/'config.yaml',cfg)
    before=(env.home/'config.yaml').read_bytes()
    try:answer=env.admin.write_settings('default',body(env,'web',profile='exa-paid',extract_timeout=12,extract_char_limit=6000),session())
    except (ValueError,PermissionError):
        assert (env.home/'config.yaml').read_bytes()==before;return
    effective=config.load_config_readonly()
    assert 'delegate_task' in _select_tool_names(effective['platform_toolsets']['telegram'],effective['agent'].get('disabled_toolsets'),True)
    route=_load_config()
    if escape=='endpoint':
        actual=_resolve_delegation_credentials(route,SimpleNamespace())
        assert actual['base_url']!='https://synthetic-inference.invalid/v1', 'Successful local-only edit retains an enabled native cloud delegation endpoint; response='+repr(answer)
    else:
        actual=_resolve_child_fallback_chain(SimpleNamespace(_fallback_chain=[]),route,pinned=True)
        assert not actual, 'Successful local-only edit retains enabled native cloud delegation fallback '+repr(actual)


@pytest.mark.parametrize('delta',[{}, {'base_url':'http://127.0.0.1:8000/v1','model':'test-local','api_mode':'chat_completions'}])
def test_delegation_inherited_or_declared_local_remains_usable(env,delta):
    from hermes_cli import config
    from tools.delegate_tool_config import _load_config,_resolve_delegation_credentials,_resolve_child_fallback_chain
    local_config(env);cfg=config.require_readable_config_before_write()
    if delta:
        delta=dict(delta,base_url=cfg['providers']['friday-local']['api'],model=cfg['model']['default'])
    cfg['delegation'].update(provider='',base_url='',model='',api_mode='')
    cfg['delegation'].update(delta);config.atomic_config_write(env.home/'config.yaml',cfg)
    answer=env.admin.write_settings('default',body(env,'web',profile='exa-paid',extract_timeout=12,extract_char_limit=6000),session())
    assert answer['recorded']
    route=_load_config();actual=_resolve_delegation_credentials(route,SimpleNamespace())
    assert actual['base_url'] in (None,cfg['providers']['friday-local']['api'])
    assert not _resolve_child_fallback_chain(SimpleNamespace(_fallback_chain=[]),route,pinned=bool(delta))

@pytest.mark.parametrize('delta',[{'provider':'openrouter'}, {'command':'unapproved-command'}, {'api_mode':'anthropic_messages'}, {'model':'undeclared-model'}])
def test_other_delegation_route_escape_is_refused_without_write(env,delta):
    from hermes_cli import config
    local_config(env);cfg=config.require_readable_config_before_write();cfg['delegation'].update(delta)
    config.atomic_config_write(env.home/'config.yaml',cfg);before=(env.home/'config.yaml').read_bytes()
    with pytest.raises(ValueError):env.admin.write_settings('default',body(env,'web',profile='exa-paid',extract_timeout=12,extract_char_limit=6000),session())
    assert (env.home/'config.yaml').read_bytes()==before
