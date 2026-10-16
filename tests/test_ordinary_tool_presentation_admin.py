import copy,json,asyncio,importlib.util,sys
from pathlib import Path
import pytest,httpx
from test_user_onboarding import env,complete,home,row,admitted,sha,save
from hermes_cli import config,friday_user_scope as scope
import test_admin_foundation as foundation


@pytest.fixture(autouse=True)
def configured(env):
    env.template['config'].setdefault('tools',{})['tool_search']={'enabled':'auto','defer':['write_file','read_file','memory','session_search']}
    save(env,env.cfg)

def body(env,value='off'):
    return {'kind':'operational','expected_sha256':sha(home(env)/'config.yaml'),'values':{'key':'tools.tool_search.enabled','value':value}}

def snapshot(env):return {n:(home(env)/n).read_bytes() for n in ['config.yaml',scope.ONBOARDING,scope.MARKER,'.env','SOUL.md']}

def test_exact_profile_native_transaction_and_admission(env):
    complete(env);complete(env,'2');before=snapshot(env);old=config.require_readable_config_before_write(home(env)/'config.yaml');other=(home(env,'2')/'config.yaml').read_bytes();generation=row(env)['generation']
    answer=env.admin.write_settings('user-1',body(env),env.operator)
    now=config.require_readable_config_before_write(home(env)/'config.yaml');expected=copy.deepcopy(old);expected['tools']['tool_search']['enabled']='off'
    assert now==expected and answer['changed']==['tools.tool_search.enabled']
    assert answer['runtime_application']=='PERSISTED_NEXT_NATIVE_SESSION_OR_RELOAD' and answer['observed_live_reload'] is False
    assert (home(env,'2')/'config.yaml').read_bytes()==other and row(env)['generation']==generation
    assert all((home(env)/n).read_bytes()==before[n] for n in ['.env','SOUL.md'])
    assert json.loads((home(env)/scope.ONBOARDING).read_text())==dict(json.loads(before[scope.ONBOARDING]),config_sha256=sha(home(env)/'config.yaml'))
    assert admitted(env)[0]
    from tools.tool_search import ToolSearchConfig
    assert ToolSearchConfig.from_raw(now['tools']['tool_search']).enabled=='off'

@pytest.mark.parametrize('value',['on','auto',False,True,0,None,{},[],['off'],'OFF'])
def test_other_values_refused_without_write(env,value):
    complete(env);before=snapshot(env)
    with pytest.raises(ValueError,match='invalid_operational_value'):env.admin.write_settings('user-1',body(env,value),env.operator)
    assert snapshot(env)==before

@pytest.mark.parametrize('fault',['stale','managed','proof_missing','foreign','expired'])
def test_cas_managed_proof_and_authority_refused(env,monkeypatch,fault):
    complete(env);request=body(env);actor=env.operator
    if fault=='stale':request['expected_sha256']='0'*64
    if fault=='managed':
        from hermes_cli import managed_scope
        monkeypatch.setattr(managed_scope,'is_key_managed',lambda key:key=='tools.tool_search.enabled')
    if fault=='proof_missing':(home(env)/scope.ONBOARDING).unlink()
    if fault in ('foreign','expired'):
        from dataclasses import replace
        actor=replace(actor,user_id='foreign') if fault=='foreign' else replace(actor,expires_at=1)
    before={n:(home(env)/n).read_bytes() for n in ['config.yaml',scope.MARKER,'.env']}
    with pytest.raises((ValueError,PermissionError)):env.admin.write_settings('user-1',request,actor)
    assert all((home(env)/n).read_bytes()==v for n,v in before.items())

def test_authenticated_http_route_selects_profile_and_refuses_bad_auth(env,monkeypatch):
    complete(env);complete(env,'2')
    from hermes_cli.dashboard_auth import middleware,request_utils
    monkeypatch.setattr(middleware,'list_session_providers',lambda:[env.provider]);monkeypatch.setattr(request_utils,'list_session_providers',lambda:[env.provider])
    app=foundation.mounted_app(env)
    @app.middleware('http')
    async def gate(req,next_call):return await middleware.gated_auth_middleware(req,next_call)
    owner=env.provider._mint_session('owner').access_token;ordinary=env.provider._mint_session('ordinary').access_token
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic') as c:
            old=(home(env)/'config.yaml').read_bytes();other=(home(env,'2')/'config.yaml').read_bytes()
            for token,status in [('bad-signature',401),(ordinary,403)]:
                r=await c.put('/api/plugins/friday_rework/settings?profile=user-1',json=body(env),headers={'Authorization':'Bearer '+token});assert r.status_code==status
            assert (home(env)/'config.yaml').read_bytes()==old
            r=await c.put('/api/plugins/friday_rework/settings?profile=foreign',json=body(env),headers={'Authorization':'Bearer '+owner});assert r.status_code==403
            r=await c.put('/api/plugins/friday_rework/settings?profile=user-1',json=body(env),headers={'Authorization':'Bearer '+owner});assert r.status_code==200,r.text
            assert r.json()['profile']=='user-1' and (home(env,'2')/'config.yaml').read_bytes()==other
    asyncio.run(scenario());assert admitted(env)[0]


def test_final_source81_tool_search_edit_busts_native_cached_agent():
    import ast
    from gateway.run_agent_cache import GatewayAgentCacheMixin
    source=Path(__import__('gateway').__path__[-1])/'run.py'
    tree=ast.parse(source.read_text())
    keynode=next(n.value for n in ast.walk(tree) if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='_CACHE_BUSTING_CONFIG_KEYS')
    class NativeKeys(GatewayAgentCacheMixin):
        _CACHE_BUSTING_CONFIG_KEYS=ast.literal_eval(keynode)
    old={'tools':{'tool_search':{'enabled':'auto','defer':['write_file']}}}
    new=copy.deepcopy(old);new['tools']['tool_search']['enabled']='off'
    before=NativeKeys._extract_cache_busting_config(old);after=NativeKeys._extract_cache_busting_config(new)
    assert before!=after and before['tools.tool_search']==old['tools']['tool_search']
    assert NativeKeys._agent_config_signature('unchanged',{},['file'],'',cache_keys=before)!=NativeKeys._agent_config_signature('unchanged',{},['file'],'',cache_keys=after)
