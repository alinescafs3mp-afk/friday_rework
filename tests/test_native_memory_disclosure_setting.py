"""Existing native admin transaction and tool discovery, synthetic signed users only."""
import copy,json,hashlib
import pytest
from test_user_onboarding import env,complete,home,row,admitted,sha
from hermes_cli import config,friday_user_scope as scope
from hermes_constants import set_hermes_home_override,reset_hermes_home_override
from tools.tool_search import ToolSearchConfig


@pytest.fixture(autouse=True)
def declared_fixture_provider_key(env):
    # The existing producer fixture predates the explicit model key reference.
    # Declare its already-owned synthetic key before prepare/sign/activate.
    env.template['config']['model']['key_env']='LOCAL_KEY'
    env.template['config']['auth']={'adopt_external_logins':False}
    env.template['config']['delegation'].update(base_url='http://127.0.0.1:9000/v1',key_env='LOCAL_KEY')
    env.template['config'].setdefault('tools',{}).setdefault('tool_search',{})['enabled']='auto'
    from test_user_onboarding import save
    save(env,env.cfg)


def current(env):
    return config.require_readable_config_before_write(home(env)/'config.yaml')


def target(cfg):
    return sorted(ToolSearchConfig.from_raw((cfg.get('tools')or{}).get('tool_search')).effective_defer_tools|{'session_search','read_file'})


def edit(env,value=None,body=None,operator=None):
    cfg=current(env)
    request=body or {'kind':'operational','expected_sha256':sha(home(env)/'config.yaml'),
       'values':{'key':'tools.tool_search.defer','value':target(cfg) if value is None else value}}
    return env.admin.write_settings('user-1',request,operator or env.operator)


def setup_explicit(env,names):
    raw=env.template['config'].setdefault('tools',{}).setdefault('tool_search',{})
    raw['defer']=names
    # Template is configured before native prepare/sign/activate, not an active config mutation.
    cfg=copy.deepcopy(env.cfg);cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local']=env.template
    from test_user_onboarding import save
    save(env,cfg)


@pytest.mark.parametrize('names',[[],['write_file','web_search','web_extract','memory'],['session_search','write_file']])
def test_real_admin_edit_preserves_signed_admission_generation_other_tools_and_idempotence(env,names):
    setup_explicit(env,names);complete(env);complete(env,'2')
    old=current(env);generation=row(env)['generation'];other=(home(env,'2')/'config.yaml').read_bytes()
    beforeproof=json.loads((home(env)/scope.ONBOARDING).read_text())
    assert 'tools.tool_search.defer'in env.admin.effective('user-1')['typed_options']['operational']
    answer=edit(env);assert answer['recorded'] and answer['changed']==['tools.tool_search.defer']
    now=current(env);expected=copy.deepcopy(old);expected.setdefault('tools',{}).setdefault('tool_search',{})['defer']=target(old)
    assert now==expected and row(env)['generation']==generation and (home(env,'2')/'config.yaml').read_bytes()==other
    assert json.loads((home(env)/scope.ONBOARDING).read_text())==dict(beforeproof,config_sha256=sha(home(env)/'config.yaml'))
    assert edit(env)['recorded'] and current(env)==now
    assert admitted(env)[0]


@pytest.mark.parametrize('value',[[],['session_search'],['session_search','write_file','web_search','web_extract','memory','terminal'],['session_search','session_search'],['session_search',1],'session_search'])
def test_arbitrary_drop_add_duplicate_scalar_refused_without_config_or_proof_change(env,value):
    setup_explicit(env,['write_file','web_search','web_extract','memory']);complete(env)
    before={n:(home(env)/n).read_bytes() for n in ['config.yaml',scope.ONBOARDING,scope.MARKER]}
    with pytest.raises(ValueError):edit(env,value)
    assert all((home(env)/n).read_bytes()==data for n,data in before.items()) and admitted(env)[0]


def test_default_native_defer_preserved_when_explicit_list_absent(env):
    complete(env);old=current(env);answer=edit(env);assert answer['recorded']
    assert set(current(env)['tools']['tool_search']['defer'])==set(target(old))
    assert admitted(env)[0]


def test_managed_leaf_and_stale_CAS_refused(env,monkeypatch):
    complete(env);request={'kind':'operational','expected_sha256':'0'*64,'values':{'key':'tools.tool_search.defer','value':target(current(env))}}
    before=(home(env)/'config.yaml').read_bytes()
    with pytest.raises(ValueError,match='native_config_changed'):edit(env,body=request)
    from hermes_cli import managed_scope
    monkeypatch.setattr(managed_scope,'is_key_managed',lambda key:key=='tools.tool_search.defer')
    with pytest.raises(PermissionError,match='administrator_managed'):edit(env)
    assert (home(env)/'config.yaml').read_bytes()==before


@pytest.mark.parametrize('kind',['foreign','expired','revoked'])
def test_admin_authority_rechecked(env,kind):
    complete(env);before=(home(env)/'config.yaml').read_bytes();from dataclasses import replace
    actor=replace(env.operator,user_id='foreign') if kind=='foreign' else replace(env.operator,expires_at=1) if kind=='expired' else env.operator
    if kind=='revoked':
        cfg=config.require_readable_config_before_write(env.home/'config.yaml');cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators']=[{'provider':'basic','user_id':'replacement','org_id':''}];config.atomic_config_write(env.home/'config.yaml',cfg)
    with pytest.raises(PermissionError):edit(env,operator=actor)
    assert (home(env)/'config.yaml').read_bytes()==before


def test_deferred_search_describe_real_scoped_dispatch_and_file_web_discovery(env):
    setup_explicit(env,['write_file','web_search','web_extract','memory']);complete(env);complete(env,'2');edit(env)
    ok,source=admitted(env);assert ok
    from tools import tool_search as ts,session_search_tool,file_tools,web_tools,memory_tool
    from tools.registry import registry
    import model_tools
    token=set_hermes_home_override(str(home(env)))
    from agent.secret_scope import load_env_file,set_secret_scope,reset_secret_scope
    secret_token=set_secret_scope(load_env_file(home(env)/'.env'),profile_home=str(home(env)))
    try:
        with scope.scoped_source(source) as cap:
            cap.check();grant=copy.deepcopy(cap.binding)
            definitions=model_tools.get_tool_definitions(enabled_toolsets=['file','web','session_search','memory'],quiet_mode=True,skip_tool_search_assembly=True)
            names={d['function']['name'] for d in definitions};assert {'read_file','write_file','session_search','web_search','web_extract','memory'}<=names
            cfg=ts.load_config_readonly();before=ts.ToolSearchConfig.from_raw(dict(enabled='auto',defer=[n for n in cfg.effective_defer_tools if n not in {'session_search','read_file'}]))
            old=ts.assemble_tool_defs(definitions,context_length=40960,config=before);new=ts.assemble_tool_defs(definitions,context_length=40960,config=cfg)
            out={d['function']['name'] for d in new.tool_defs};assert 'session_search'not in out and 'read_file'not in out and {'tool_search','tool_describe','tool_call'}<=out
            assert not ts.is_deferrable_tool_name('clarify',cfg.effective_defer_tools)
            found=json.loads(ts.dispatch_tool_search({'queries':['recall past conversation session_search','read_file','write_file','web_search'],'limit':10},current_tool_defs=definitions,config=cfg));assert all(n in json.dumps(found) for n in ['session_search','read_file','write_file','web_search'])
            assert 'session_search'in json.loads(ts.dispatch_tool_describe({'names':['session_search']},current_tool_defs=definitions,config=cfg))['tools']
            from hermes_state import SessionDB
            db=SessionDB(home(env)/'state.db');db.create_session('own-session','telegram',user_id='1',profile_name='user-1',origin_json=json.dumps({'friday_account_origin':{'schema':'friday.account_origin.v1','platform':'telegram','transport_profile':'default','account_id':'bot-A'}}));db.append_message('own-session','user','OWN_RECALL_SENTINEL');db.close()
            direct=json.loads(registry.dispatch('session_search',{'query':'OWN_RECALL_SENTINEL'}))
            from agent.tool_executor import _unwrap_tool_search_call
            from types import SimpleNamespace
            name,args,error=_unwrap_tool_search_call(SimpleNamespace(enabled_toolsets=['file','web','session_search','memory'],disabled_toolsets=[]),'tool_call',{'calls':[{'name':'session_search','arguments':{'query':'OWN_RECALL_SENTINEL'}}]})
            assert name=='session_search' and error is None
            bridged=json.loads(registry.dispatch(name,args))
            assert direct==bridged and 'OWN_RECALL_SENTINEL'in json.dumps(bridged) and 'product_user_scope_refused'not in json.dumps(bridged)
            own=home(env)/'workspace/own.txt';own.write_text('OWN_FILE_SENTINEL');own.chmod(0o600)
            foreign=home(env,'2')/'workspace/foreign.txt';foreign.write_text('FOREIGN_FILE_SENTINEL');foreign.chmod(0o600)
            read=lambda path:json.loads(model_tools.handle_function_call('tool_call',{'calls':[{'name':'read_file','arguments':{'path':str(path)}}]},enabled_toolsets=['file','web','session_search','memory']))
            assert 'OWN_FILE_SENTINEL'in json.dumps(read(own))
            denied=read(foreign);assert 'FOREIGN_FILE_SENTINEL'not in json.dumps(denied) and 'product_user_scope_refused'in json.dumps(denied)
            assert cap.binding==grant and cap.check() is cap
            size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode())
            print('DISCLOSURE_BYTES',json.dumps({'before':size(old.tool_defs),'after':size(new.tool_defs),'saving':size(old.tool_defs)-size(new.tool_defs),'own_only_dispatch':True,'names_preserved':sorted(names)}))
    finally:reset_secret_scope(secret_token);reset_hermes_home_override(token)
