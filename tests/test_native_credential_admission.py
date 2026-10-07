"""Actual scoped native consumers; protected synthetic keys, no network or model."""
import copy
import contextvars
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_native_dashboard_owner import installation
from test_native_installer import native_home
from test_product_profile import inputs, template
from test_user_onboarding import env, complete, admitted, home as user_home
from tools.configure_product import compose_product
from hermes_cli import friday_credential_admission as admission


def publish(p, value):
    p.write_text(json.dumps(value)); p.chmod(0o600)


def dotenv(home, **values):
    p = home / '.env'; p.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));p.chmod(0o600)


@pytest.fixture
def operator(installation, monkeypatch):
    home, source, config, verified = installation
    monkeypatch.setattr(admission, 'SOURCE', source)
    from hermes_cli import friday_dashboard_owner as boundary
    monkeypatch.setattr(boundary, 'SOURCE', source)
    cfg=copy.deepcopy(config);cfg['auth']={'adopt_external_logins':False}
    publish(home/'config.yaml',cfg)
    (home/'auth.json').unlink(missing_ok=True)
    values={'FRIDAY_LOCAL_KEY':'SYNTHETIC_LOCAL_INFERENCE', 'EXA_API_KEY':'SYNTHETIC_EXA_WEB',
            'TELEGRAM_BOT_TOKEN':'123456:synthetic-channel-token-for-fixture'}
    dotenv(home,**values)
    monkeypatch.setenv('HERMES_HOME',str(home))
    import hermes_constants
    monkeypatch.setattr(hermes_constants,'_PINNED_PROCESS_HERMES_HOME',str(home))
    with native_home(home), admission.scoped(home):
        yield SimpleNamespace(home=home,source=source,cfg=cfg,values=values,verified=verified)


def runtime():
    from hermes_cli.runtime_provider import resolve_runtime_provider
    return resolve_runtime_provider(requested='custom:friday-local',target_model=inputs()['inference']['model'])


def test_actual_named_resolver_own_key_and_auxiliary(operator,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','FOREIGN_CLOUD_SECRET')
    monkeypatch.setenv('FRIDAY_LOCAL_KEY','FOREIGN_LOCAL_SECRET')
    r=runtime();assert r['api_key']==operator.values['FRIDAY_LOCAL_KEY'];assert r['base_url']==inputs()['inference']['base_url']
    from agent.auxiliary_client import _resolve_task_provider_model
    for name,row in operator.cfg['auxiliary'].items():
        if isinstance(row,dict):
            p,m,u,k,mode=_resolve_task_provider_model(task=name)
            assert (p,m,u,k,mode)==('custom:friday-local',inputs()['inference']['model'],inputs()['inference']['base_url'],operator.values['FRIDAY_LOCAL_KEY'],'chat_completions')


@pytest.mark.parametrize('name',['FRIDAY_LOCAL_KEY','EXA_API_KEY'])
def test_missing_owned_key_never_borrows_ambient(operator,monkeypatch,name):
    values=dict(operator.values);values.pop(name);dotenv(operator.home,**values)
    monkeypatch.setenv(name,'FOREIGN_AMBIENT_MUST_NOT_FILL')
    with admission.scoped(operator.home),pytest.raises(admission.CredentialDenied):runtime()


def test_actual_native_global_pool_is_not_read(operator,monkeypatch):
    from hermes_cli import auth
    def foreign():raise AssertionError('foreign root auth store read')
    monkeypatch.setattr(auth,'_load_global_auth_store',foreign)
    assert auth.read_credential_pool('custom:friday-local')==[]
    assert runtime()['api_key']==operator.values['FRIDAY_LOCAL_KEY']


def test_actual_own_native_pool_precedes_configured_reference(operator):
    publish(operator.home/'auth.json',{'credential_pool':{'custom:friday-local':[{
        'id':'owned-local','source':'manual','auth_type':'api_key','access_token':'OWNED_POOL_SECRET',
        'base_url':inputs()['inference']['base_url'],'priority':0}]}})
    r=runtime();assert r['api_key']=='OWNED_POOL_SECRET' and r['source'].startswith('pool:')


def test_missing_dotenv_inference_can_use_actual_own_native_pool(operator):
    values=dict(operator.values);values.pop('FRIDAY_LOCAL_KEY');dotenv(operator.home,**values)
    publish(operator.home/'auth.json',{'credential_pool':{'custom:friday-local':[{
        'id':'owned-local','source':'manual','auth_type':'api_key','access_token':'OWNED_POOL_SECRET',
        'base_url':inputs()['inference']['base_url'],'priority':0}]}})
    with admission.scoped(operator.home):assert runtime()['api_key']=='OWNED_POOL_SECRET'


@pytest.mark.parametrize('change',[{'base_url':'https://foreign.example/v1'}, {'base_url':None},
    {'refresh_token':'FOREIGN_REFRESH_SECRET'}, {'auth_type':'oauth'}, {'access_token':'no-key-required'}])
def test_own_pool_invalid_route_or_placeholder_refused(operator,change):
    row={'id':'owned-local','source':'manual','auth_type':'api_key','access_token':'OWNED_POOL_SECRET',
         'base_url':inputs()['inference']['base_url'],'priority':0};row.update(change)
    publish(operator.home/'auth.json',{'credential_pool':{'custom:friday-local':[row]}})
    with pytest.raises(admission.CredentialDenied):runtime()


@pytest.mark.parametrize('kwargs',[{'requested':'openrouter'},{'explicit_base_url':'https://foreign.example/v1'},
    {'explicit_api_key':'FOREIGN_EXPLICIT_SECRET'},{'target_model':'foreign-model'}])
def test_real_named_resolver_overrides_refuse_before_native_ladder(operator,monkeypatch,kwargs):
    from hermes_cli import runtime_provider as rp
    monkeypatch.setattr(rp,'_ladder_rungs',lambda *a:(_ for _ in ()).throw(AssertionError('ladder reached')))
    with pytest.raises(admission.CredentialDenied):rp.resolve_runtime_provider(**kwargs)


@pytest.mark.parametrize('kwargs',[{'provider':'openrouter'},{'base_url':'https://foreign.example/v1'},
    {'api_key':'FOREIGN_EXPLICIT_SECRET'},{'model':'foreign-model'}])
def test_actual_auxiliary_overrides_refuse(operator,kwargs):
    from agent.auxiliary_client import _resolve_task_provider_model
    with pytest.raises(admission.CredentialDenied):_resolve_task_provider_model(task='compression',**kwargs)


@pytest.mark.parametrize('mutation',['fallback','auxiliary','delegation','operator','enable','model','key_cmd'])
def test_cold_config_drift_refused(operator,mutation):
    cfg=copy.deepcopy(operator.cfg)
    if mutation=='fallback':cfg['fallback_providers']=['openrouter']
    elif mutation=='auxiliary':cfg['auxiliary']['compression']['provider']='openrouter'
    elif mutation=='delegation':cfg['delegation']['model']='foreign'
    elif mutation=='operator':cfg['dashboard']['basic_auth']['username']='foreign'
    elif mutation=='enable':cfg['platforms']['discord']['enabled']=True
    elif mutation=='model':cfg['model']['base_url']='https://foreign.example/v1'
    else:cfg['providers']['friday-local']['key_cmd']='foreign-command'
    publish(operator.home/'config.yaml',cfg)
    with pytest.raises(admission.CredentialDenied):runtime()


@pytest.mark.parametrize('kind',['public','hardlink','symlink','interpolation','missing'])
def test_protected_dotenv_negative_before_secret_resolution(operator,kind):
    p=operator.home/'.env'
    if kind=='public':p.chmod(0o644)
    elif kind=='hardlink':os.link(p,operator.home/'linked.env')
    elif kind=='symlink':p.rename(operator.home/'original.env');p.symlink_to(operator.home/'original.env')
    elif kind=='interpolation':p.write_text('FRIDAY_LOCAL_KEY=${OPENAI_API_KEY}\nEXA_API_KEY=SYNTHETIC_EXA\n')
    else:p.unlink()
    with pytest.raises((ValueError,OSError)):runtime()
    for n in ('linked.env','original.env'):(operator.home/n).unlink(missing_ok=True)
    p.unlink(missing_ok=True)


def test_boot_actual_env_loader_excludes_ambient_and_project(operator,monkeypatch):
    from hermes_cli.env_loader import load_hermes_dotenv
    monkeypatch.setenv('FRIDAY_LOCAL_KEY','FOREIGN_AMBIENT')
    monkeypatch.setenv('OPENROUTER_API_KEY','FOREIGN_CLOUD')
    project=operator.home/'project.env';project.write_text('FRIDAY_LOCAL_KEY=FOREIGN_PROJECT\n');project.chmod(0o600)
    with monkeypatch.context() as patch:
        patch.setattr(os,'environ',dict(os.environ))
        assert load_hermes_dotenv(hermes_home=operator.home,project_env=project)==[operator.home/'.env']
        assert os.environ['FRIDAY_LOCAL_KEY']==operator.values['FRIDAY_LOCAL_KEY']
        assert 'OPENROUTER_API_KEY' not in os.environ
        assert runtime()['api_key']==operator.values['FRIDAY_LOCAL_KEY']
    project.unlink()


@pytest.mark.parametrize('kind',['wrong_home','source_drift','ambient_operator'])
def test_normal_cold_boot_refuses_unproved_source_home_or_operator(operator,monkeypatch,kind):
    from hermes_cli.env_loader import load_hermes_dotenv
    target=operator.home;changed=None
    if kind=='wrong_home':
        target=operator.home/'foreign';target.mkdir(mode=0o700)
    elif kind=='ambient_operator':monkeypatch.setenv('HERMES_DASHBOARD_BASIC_AUTH_SECRET','FOREIGN_OPERATOR_SECRET')
    else:
        changed=operator.source/'hermes_cli/friday_credential_admission.py';before=changed.read_bytes();changed.write_bytes(before+b'\n')
    try:
        with pytest.raises((ValueError,OSError)):load_hermes_dotenv(hermes_home=target)
    finally:
        if changed:changed.write_bytes(before)
        if kind=='wrong_home':target.rmdir()


def test_actual_native_scoped_channel_config_ignores_foreign_token(operator,monkeypatch):
    from gateway.config import load_gateway_config,Platform
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','FOREIGN_TOKEN')
    monkeypatch.setenv('DISCORD_BOT_TOKEN','FOREIGN_DISCORD')
    cfg=load_gateway_config()
    assert cfg.platforms[Platform.TELEGRAM].token==operator.values['TELEGRAM_BOT_TOKEN']
    assert not cfg.platforms[Platform.DISCORD].enabled


def test_actual_channel_config_foreign_token_refused(operator):
    from gateway.config import load_gateway_config,Platform
    cfg=load_gateway_config();cfg.platforms[Platform.TELEGRAM].token='FOREIGN_TOKEN'
    with pytest.raises(admission.CredentialDenied):admission.channel_config(cfg)


def test_native_initialized_account_before_consumption(operator):
    admission.channel_identity('telegram','bot-A')
    with pytest.raises(admission.CredentialDenied):admission.channel_identity('telegram','foreign-bot')


def test_wrong_secret_scope_home_refused(operator):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    t=set_secret_scope(operator.values,profile_home=str(operator.home/'foreign'))
    try:
        with pytest.raises(admission.CredentialDenied):runtime()
    finally:reset_secret_scope(t)


def test_failure_messages_and_metadata_do_not_include_values(operator):
    try:admission.route_inputs(api_key='FOREIGN_CANARY_SECRET')
    except admission.CredentialDenied as e:
        assert 'FOREIGN_CANARY_SECRET' not in str(e) and not any(v in str(e) for v in operator.values.values())
    else:pytest.fail('expected refusal')


def test_two_actual_native_onboarded_user_scopes_do_not_borrow_operator(env,monkeypatch):
    spec=inputs();spec['inference']['key_env']='LOCAL_KEY';env.template=template(compose_product(spec))
    env.cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local']=env.template
    publish(env.home/'config.yaml',env.cfg)
    complete(env,'1');complete(env,'2')
    monkeypatch.setenv('LOCAL_KEY','FOREIGN_OWNER_LOCAL');monkeypatch.setenv('EXA_API_KEY','FOREIGN_OWNER_EXA')
    from hermes_cli import friday_user_scope as user
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    from agent.secret_scope import build_profile_secret_scope,get_secret
    from hermes_cli.runtime_provider import resolve_runtime_provider
    for uid in ('1','2'):
        ok,s=admitted(env,uid);assert ok
        h=user_home(env,uid);t=set_hermes_home_override(str(h))
        try:
            with user.scoped_source(s), admission.scoped(h):
                v=build_profile_secret_scope(h)
                assert v['LOCAL_KEY']=='synthetic-'+uid+'-LOCAL_KEY'
                assert get_secret('LOCAL_KEY')==v['LOCAL_KEY']
                r=resolve_runtime_provider(requested='custom:friday-local')
                assert r['api_key']==v['LOCAL_KEY'] and r['base_url']==spec['inference']['base_url']
                from plugins.web import _common as shared
                assert shared.provider_env('EXA_API_KEY')==v['EXA_API_KEY']
                with pytest.raises(admission.CredentialDenied):admission.channel_identity('telegram','bot-A')
        finally:reset_hermes_home_override(t)


def test_unmarked_native_scope_keeps_normal_donor_semantics(tmp_path,monkeypatch):
    from agent.secret_scope import build_profile_secret_scope
    h=tmp_path/'unmarked';h.mkdir(mode=0o700);publish(h/'config.yaml',{})
    monkeypatch.setattr(admission,'SOURCE',tmp_path/'ordinary-source')
    dotenv(h,OWN_KEY='UNMARKED_OWN_VALUE')
    assert not admission.managed(h)
    assert build_profile_secret_scope(h)['OWN_KEY']=='UNMARKED_OWN_VALUE'


@pytest.mark.parametrize('field,value',[('keyless_rescue',True),('search_backend','brave')])
def test_native_web_connection_remains_exa_separate_from_inference(operator,field,value):
    cfg=copy.deepcopy(operator.cfg);cfg['web'][field]=value;publish(operator.home/'config.yaml',cfg)
    with pytest.raises(admission.CredentialDenied):runtime()


def test_native_exa_consumer_uses_own_key_and_missing_is_unavailable(operator,monkeypatch):
    from plugins.web.exa.provider import ExaWebSearchProvider
    from plugins.web import _common
    from tools import web_tools
    seen=[]
    monkeypatch.setattr(_common,'lazy_ensure',lambda name:None)
    monkeypatch.setattr(web_tools,'_credential_admission_fixture_cache',None,raising=False)
    client=_common.cached_sdk_client('_credential_admission_fixture_cache','EXA_API_KEY','missing','exa',lambda k:seen.append(k) or object())
    assert ExaWebSearchProvider().is_available() and seen==[operator.values['EXA_API_KEY']]
    assert client is _common.cached_sdk_client('_credential_admission_fixture_cache','EXA_API_KEY','missing','exa',lambda k:pytest.fail('unexpected rebuild'))
    values=dict(operator.values);values.pop('EXA_API_KEY');dotenv(operator.home,**values)
    monkeypatch.setenv('EXA_API_KEY','FOREIGN_EXA_KEY')
    with admission.scoped(operator.home):
        assert not ExaWebSearchProvider().is_available()
        with pytest.raises(ValueError):_common.cached_sdk_client('_credential_admission_fixture_cache','EXA_API_KEY','missing','exa',lambda k:pytest.fail('borrowed'))


def test_actual_native_resolved_key_must_belong_to_declared_pool(operator):
    r=runtime();r['api_key']='UNDECLARED_POOL_CANARY'
    with pytest.raises(admission.CredentialDenied):admission.runtime_checked(r,admission.route_inputs())


def test_native_pool_not_in_receiving_scope_cannot_enable_missing_key(operator,monkeypatch):
    from hermes_cli import auth
    values=dict(operator.values);values.pop('FRIDAY_LOCAL_KEY');dotenv(operator.home,**values)
    monkeypatch.setattr(auth,'_load_global_auth_store',lambda:{'credential_pool':{'custom:friday-local':[{
        'id':'owner','source':'manual','access_token':'FOREIGN_OWNER_POOL_SECRET','base_url':inputs()['inference']['base_url']}]}})
    with admission.scoped(operator.home),pytest.raises(admission.CredentialDenied):runtime()


@pytest.mark.parametrize('which',['config.yaml','auth.json'])
def test_private_native_config_and_pool_links_refused(operator,which):
    p=operator.home/which
    if which=='auth.json':publish(p,{'credential_pool':{}})
    alias=operator.home/(which+'.alias');os.link(p,alias)
    try:
        with pytest.raises(ValueError):runtime()
    finally:alias.unlink()


def test_native_config_cannot_interpolate_ambient_endpoint(operator,monkeypatch):
    cfg=copy.deepcopy(operator.cfg);cfg['model']['base_url']='${FOREIGN_ENDPOINT}'
    monkeypatch.setenv('FOREIGN_ENDPOINT',inputs()['inference']['base_url']);publish(operator.home/'config.yaml',cfg)
    with pytest.raises(admission.CredentialDenied):runtime()


@pytest.mark.parametrize('account',['123456','999999'])
def test_actual_telegram_sdk_getme_checked_before_consumption(operator,monkeypatch,account):
    import asyncio
    from telegram.request import BaseRequest
    from telegram.ext import Application
    from plugins.platforms.telegram.adapter import TelegramAdapter
    from gateway.config import PlatformConfig
    from gateway import status
    seen=[]
    class SyntheticRequest(BaseRequest):
        @property
        def read_timeout(self):return 2
        async def initialize(self):pass
        async def shutdown(self):seen.append('closed')
        async def do_request(self,url,method,request_data=None,**kwargs):
            assert url.endswith('/getMe');seen.append('actual_sdk_getMe')
            return 200,json.dumps({'ok':True,'result':{'id':int(account),'is_bot':True,
                'first_name':'Synthetic','username':'synthetic_fixture_bot'}}).encode()
    class BeforeConsumption(BaseException):pass
    async def before_consumption(app):
        seen.append('admitted_before_consumption');raise BeforeConsumption()
    async def requests(adapter):return SyntheticRequest(),SyntheticRequest()
    monkeypatch.setattr(TelegramAdapter,'_build_ptb_requests',requests)
    monkeypatch.setattr(Application,'start',before_consumption)
    monkeypatch.setattr(status,'_get_lock_dir',lambda:operator.home/'telegram-locks')
    operator.cfg['plugins']['entries']['friday_rework']['settings']['product_access']['accounts'][0]['account_id']='123456'
    publish(operator.home/'config.yaml',operator.cfg)
    adapter=TelegramAdapter(PlatformConfig(enabled=True,token=operator.values['TELEGRAM_BOT_TOKEN']))
    async def exercise():
        try:
            if account=='123456':
                with pytest.raises(BeforeConsumption):await adapter.connect()
                assert 'admitted_before_consumption' in seen
            else:
                assert await adapter.connect() is False
                assert adapter.fatal_error_code=='friday_account_refused' and not adapter.fatal_error_retryable
                assert 'admitted_before_consumption' not in seen
        finally:await adapter.disconnect()
        assert adapter._app is None and not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    asyncio.run(exercise());assert 'actual_sdk_getMe' in seen and 'closed' in seen


def test_same_launch_home_native_scope_miss_never_borrows_even_without_multiplex(operator,monkeypatch):
    from agent import secret_scope as native
    monkeypatch.setattr(native,'_MULTIPLEX_ACTIVE',False)
    m=native.set_multiplex_context(False)
    s=native.set_secret_scope({},profile_home=str(operator.home))
    monkeypatch.setenv('EXA_API_KEY','FOREIGN_OWNER_EXA_KEY')
    values=dict(operator.values);values.pop('EXA_API_KEY');dotenv(operator.home,**values)
    try:
        assert native.get_secret('EXA_API_KEY') is None
        from plugins.web.exa.provider import ExaWebSearchProvider
        assert not ExaWebSearchProvider().is_available()
        empty=native.set_secret_scope(None)
        try:
            with pytest.raises(native.UnscopedSecretError):native.get_secret('EXA_API_KEY')
        finally:native.reset_secret_scope(empty)
    finally:native.reset_secret_scope(s);native.reset_multiplex_context(m)


def test_actual_native_web_foreign_bound_home_refused(operator):
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    from plugins.web.exa.provider import ExaWebSearchProvider
    t=set_secret_scope({'EXA_API_KEY':'FOREIGN_SCOPE_KEY'},profile_home=str(operator.home/'foreign'))
    try:
        assert ExaWebSearchProvider().is_available() is False
    finally:reset_secret_scope(t)


@pytest.mark.parametrize('which',['public','symlink'])
def test_actual_native_web_cannot_read_unprotected_dotenv(operator,which):
    from plugins.web.exa.provider import ExaWebSearchProvider
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    p=operator.home/'.env'
    if which=='public':p.chmod(0o644)
    else:p.rename(operator.home/'original.env');p.symlink_to(operator.home/'original.env')
    t=set_secret_scope({},profile_home=str(operator.home))
    try:assert ExaWebSearchProvider().is_available() is False
    finally:
        reset_secret_scope(t);p.unlink(missing_ok=True);(operator.home/'original.env').unlink(missing_ok=True)


def test_actual_gateway_invalid_yaml_is_masked_before_permissive_loader(operator,monkeypatch,caplog):
    from gateway.config import load_gateway_config
    (operator.home/'config.yaml').write_text('secret: [INVALID_CANARY_SECRET: broken: syntax')
    (operator.home/'config.yaml').chmod(0o600)
    with pytest.raises(admission.CredentialDenied):load_gateway_config()
    assert 'INVALID_CANARY_SECRET' not in caplog.text


def test_actual_gateway_weak_key_is_masked_before_native_token_diagnostic(operator,caplog):
    from gateway.config import load_gateway_config
    values=dict(operator.values);values['TELEGRAM_BOT_TOKEN']='YOUR_TOKEN_HERE';dotenv(operator.home,**values)
    with admission.scoped(operator.home),pytest.raises(admission.CredentialDenied):load_gateway_config()
    assert 'YOUR_T' not in caplog.text


@pytest.mark.parametrize('kwargs',[{'provider':'openrouter'},{'provider':'auto'},
    {'provider':'custom:friday-local','explicit_base_url':'https://foreign.example/v1'},
    {'provider':'custom:friday-local','explicit_api_key':'FOREIGN_DIRECT_CLIENT_KEY'},
    {'provider':'custom:friday-local','api_mode':'codex_app_server'}])
def test_actual_auxiliary_client_router_blocks_bypass_before_sdk(operator,monkeypatch,kwargs):
    from agent import auxiliary_client as aux
    monkeypatch.setattr(aux,'_validate_proxy_env_urls',lambda:pytest.fail('router reached sdk preparation'))
    with pytest.raises(admission.CredentialDenied):aux.resolve_provider_client(**kwargs)


def test_actual_auxiliary_client_router_constructs_only_declared_local_sdk(operator,monkeypatch):
    from agent import auxiliary_client as aux
    seen=[]
    def client(**kwargs):seen.append(kwargs);return SimpleNamespace(**kwargs)
    monkeypatch.setattr(aux,'_create_openai_client',client)
    client,model=aux.resolve_provider_client(provider='custom:friday-local')
    assert model==inputs()['inference']['model'] and client is not None
    assert seen and seen[-1]['base_url']==inputs()['inference']['base_url']
    assert seen[-1]['api_key']==operator.values['FRIDAY_LOCAL_KEY']


def test_actual_auxiliary_client_keeps_owned_pool_priority(operator,monkeypatch):
    from agent import auxiliary_client as aux
    publish(operator.home/'auth.json',{'credential_pool':{'custom:friday-local':[{
        'id':'owned-local','source':'manual','auth_type':'api_key','access_token':'OWNED_POOL_SECRET',
        'base_url':inputs()['inference']['base_url'],'priority':0}]}})
    def client(**kwargs):return SimpleNamespace(**kwargs)
    monkeypatch.setattr(aux,'_create_openai_client',client)
    p,m,u,k,mode=aux._resolve_task_provider_model(task='compression')
    c,selected=aux.resolve_provider_client(provider=p,model=m,explicit_base_url=u,explicit_api_key=k,api_mode=mode)
    assert c.api_key=='OWNED_POOL_SECRET' and selected==m


def test_declared_local_inference_cannot_silently_use_ambient_proxy(operator,monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY','http://foreign-proxy.invalid:8080')
    with pytest.raises(admission.CredentialDenied):runtime()
