"""Real native consumers with synthetic protected inputs; no runtime grants."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from tools.configure_product import compose_product, materialize_product, ROOT


def inputs():
    return {'profile': 'default', 'inference': {
        'base_url': 'http://127.0.0.1:9000/v1', 'model': 'explicit-local-fixture',
        'key_env': 'FRIDAY_LOCAL_KEY', 'context': 32768, 'max_input': 30000,
        'main_output': 4096, 'summary_output': 2048, 'margin': 1024, 'template_overhead': 512},
        'web': {'profile': 'exa-paid', 'extract_char_limit': 20000, 'extract_timeout': 30},
        'dashboard': {'host': '127.0.0.1', 'port': 9119, 'public_url': 'https://friday.example:9119',
            'operator': {'provider': 'basic', 'user_id': 'explicit-operator', 'org_id': ''}},
        'accounts': [{'platform': 'telegram', 'transport_profile': 'default', 'account_id': 'bot-A'}],
        'runtime': {'enabled': False}}


def template(bundle):
    return bundle['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']


def test_composition_preserves_native_capabilities_and_routes():
    from hermes_cli.config import DEFAULT_CONFIG
    bundle = compose_product(inputs()); config = bundle['config']
    assert config['toolsets'] == ['hermes-cli', 'web', 'friday_rework']
    assert config['memory'] == DEFAULT_CONFIG['memory']
    assert config['skills'] == DEFAULT_CONFIG['skills']
    assert config['approvals'] == DEFAULT_CONFIG['approvals']
    assert config['agent'] == dict(DEFAULT_CONFIG['agent'],environment_hint=config['agent']['environment_hint'])
    assert config['tools'] == DEFAULT_CONFIG['tools']
    assert config['web']['cache_enabled'] == DEFAULT_CONFIG['web']['cache_enabled']
    assert config['fallback_providers'] == [] and config['fallback_model'] == {}
    expected = {k for k, v in DEFAULT_CONFIG['auxiliary'].items() if isinstance(v, dict) and 'provider' in v}
    assert expected == {k for k, v in config['auxiliary'].items() if isinstance(v, dict)}
    for name in expected:
        route = config['auxiliary'][name]
        assert route['provider'] == 'custom:friday-local'
        assert route['base_url'] == inputs()['inference']['base_url']
        assert route['key_env'] == 'FRIDAY_LOCAL_KEY'
        assert route['model'] == inputs()['inference']['model'] and route['fallback_chain'] == []
        assert 'api_key' not in route
    assert config['auxiliary']['title_generation']['enabled'] is True
    assert config['auxiliary']['background_review']['enabled'] is True
    assert config['delegation']['base_url'] == config['model']['base_url']
    assert config['delegation']['fallback_providers'] == []
    assert not bundle['contract']['ready'] and bundle['contract']['state'] == 'TEMPLATE_INCOMPLETE'
    assert bundle['soul'] == (ROOT / 'config/SOUL.md').read_text()


@pytest.mark.parametrize('context,max_input,main,summary', [(32768,30000,4096,2048),(131072,120000,8192,4096),(65536,60000,6000,3000)])
def test_explicit_capacity_variants(context, max_input, main, summary):
    spec = inputs(); spec['inference'].update(context=context,max_input=max_input,main_output=main,summary_output=summary)
    config = compose_product(spec)['config']; row = config['providers']['friday-local']['models'][spec['inference']['model']]
    assert row['context_length'] == context
    assert row['bounded_context']['main_max_output_tokens'] == main
    assert config['auxiliary']['compression']['extra_body']['max_tokens'] == summary
    assert config['compression']['threshold_tokens'] == (min(max_input,context-max(main,summary))-1536)*3//4
    from agent.bounded_context import policy_from_config
    policy=policy_from_config(config)
    assert policy.context_length==context and policy.main_max_output_tokens==main
    assert policy.compression_output_tokens==summary
    assert policy.input_budget(main)==min(max_input,context-main)-1024
    assert policy.trigger_tokens==config['compression']['threshold_tokens']
    request={'model':spec['inference']['model'],'max_tokens':main,'messages':[{'role':'user','content':'synthetic text'}]}
    assert policy.check_request(request)
    from agent.bounded_context import BoundedContextError
    with pytest.raises(BoundedContextError):policy.check_request(dict(request,max_tokens=main+1))
    with pytest.raises(BoundedContextError):policy.check_request(dict(request,messages=[{'role':'user','content':[{'type':'image_url','image_url':'data:synthetic'}]}]))


@pytest.mark.parametrize('path,value', [
    ('web.profile','disabled'),('web.profile','foreign-web'),('web.extract_timeout',None),
    ('dashboard.operator.provider','auto'),('dashboard.operator.user_id',''),('dashboard.operator.org_id',None),
    ('dashboard.public_url','https://user:secret@friday.example:9119'),
    ('dashboard.public_url','https://friday.example:9119/path'),('dashboard.public_url','http://friday.example:9119'),
    ('dashboard.public_url','https://*:9119'),('dashboard.public_url','https://bad_host:9119'),
    ('inference.base_url','https://api.openai.com/v1'),('inference.model','auto'),
    ('inference.key_env','EXA_API_KEY'),('inference.key_env','PATH'),('inference.max_input',True),
    ('inference.main_output',32768),('inference.model','${MODEL}'),('runtime.enabled',True)])
def test_missing_unsafe_or_ambiguous_input_refused(path, value):
    spec = inputs(); node = spec
    parts = path.split('.')
    for part in parts[:-1]: node = node[part]
    node[parts[-1]] = value
    with pytest.raises((ValueError,KeyError,TypeError)): compose_product(spec)


@pytest.mark.parametrize('field', ['inference','dashboard','web','accounts','runtime'])
def test_required_input_not_silently_defaulted(field):
    spec = inputs(); del spec[field]
    with pytest.raises(ValueError): compose_product(spec)


def test_ambient_keys_and_input_data_never_adopted(monkeypatch):
    spec = inputs(); before = copy.deepcopy(spec)
    for key in ('OPENAI_API_KEY','OPENROUTER_API_KEY','LOCAL_KEY','EXA_API_KEY',
                'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD','HERMES_DASHBOARD_BASIC_AUTH_USERNAME'):
        monkeypatch.setenv(key,'AMBIENT_OWNER_CANARY')
    bundle = compose_product(spec)
    assert spec == before and 'AMBIENT_OWNER_CANARY' not in json.dumps(bundle)
    ordinary = template(bundle)
    assert set(ordinary) == {'config','tools','required_secrets'}
    assert not any(k in ordinary['config'] for k in ('dashboard','gateway','secrets'))
    assert ordinary['config']['plugins']['entries']['friday_rework']['settings'] == {
        'runtime': {'enabled': False}, 'results': {'enabled': True}}
    assert ordinary['config']['skills']['external_dirs'] == []
    assert not ordinary['config']['skills']['project_discovery']
    assert 'dashboard_auth/basic' not in ordinary['config']['plugins']['enabled']
    assert 'dashboard_auth/basic' in ordinary['config']['plugins']['disabled']


@pytest.mark.parametrize('path,value', [
    (('compression','proactive_prune_tokens'),'secret-canary'),
    (('compression','proactive_prune_tokens'),True),
    (('compression','proactive_prune_tokens'),-1),
    (('tools','listing_max_tokens'),'${OWNER_SECRET}'),
    (('tools','other_token'),4000),
    (('memory','listing_max_tokens'),4000)])
def test_native_numeric_metadata_exception_cannot_embed_credentials(path,value):
    from plugins.friday_rework.onboarding import validate_template
    ordinary=template(compose_product(inputs()))
    ordinary['config'].setdefault(path[0],{})[path[1]]=value
    with pytest.raises(ValueError):validate_template(ordinary)


def test_multiple_configured_surfaces_and_profile_authority():
    spec = inputs(); spec['profile'] = 'operator-local'; spec['accounts'] = [
        {'platform': 'telegram','transport_profile':'operator-local','account_id':'bot-A'},
        {'platform': 'discord','transport_profile':'operator-local','account_id':'bot-B'}]
    bundle = compose_product(spec); config = bundle['config']
    assert set(config['platform_toolsets']) == {'cli','telegram','discord'}
    assert len({tuple(v) for v in config['platform_toolsets'].values()}) == 1
    assert config['plugins']['entries']['friday_rework']['settings']['admin']['profiles'] == ['operator-local']
    for bad in ([spec['accounts'][0],spec['accounts'][0]], [dict(spec['accounts'][0],transport_profile='foreign')]):
        spec['accounts'] = bad
        with pytest.raises(ValueError): compose_product(spec)


def test_fresh_atomic_native_materialization_and_readonly_load(tmp_path):
    from hermes_cli.config import load_config_readonly
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    parent = tmp_path/'private'; parent.mkdir(mode=0o700); home = parent/'new-profile'
    spec = inputs(); before = copy.deepcopy(spec)
    result = materialize_product(home,spec)
    assert result['state'] == 'TEMPLATE_INCOMPLETE' and not result['ready']
    assert spec == before and not (home/'.env').exists()
    assert not any((home/name).exists() for name in ('USER.md','MEMORY.md','state.db','skills','.friday-user-scope.json'))
    token = set_hermes_home_override(str(home))
    try:
        config = load_config_readonly()
        assert config['model']['default'] == spec['inference']['model']
        assert config['memory']['memory_enabled'] and config['skills']['project_discovery']
        assert config['plugins']['entries']['friday_rework']['settings']['admin']['operators'] == [spec['dashboard']['operator']]
    finally: reset_hermes_home_override(token)
    assert result['soul_sha256'] == hashlib.sha256((home/'SOUL.md').read_bytes()).hexdigest()
    for p in home.iterdir(): assert p.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError): materialize_product(home,spec)


@pytest.mark.parametrize('kind',['public_parent','symlink_parent','preexisting_home','symlink_home','invalid_spec'])
def test_ownership_and_conflict_refusal(tmp_path, kind):
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new';spec=inputs()
    if kind=='public_parent':parent.chmod(0o755)
    elif kind=='symlink_parent':alias=tmp_path/'alias';alias.symlink_to(parent);home=alias/'new'
    elif kind=='preexisting_home':home.mkdir(mode=0o700);(home/'keep').write_text('KEEP')
    elif kind=='symlink_home':home.symlink_to(parent)
    else:spec['web']['profile']='disabled'
    before={str(p):p.read_bytes() for p in parent.rglob('*') if p.is_file()}
    with pytest.raises((PermissionError,ValueError,FileExistsError)):materialize_product(home,spec)
    assert before=={str(p):p.read_bytes() for p in parent.rglob('*') if p.is_file()}


def test_native_auxiliary_resolver_reads_only_named_scoped_keys(tmp_path, monkeypatch):
    from hermes_cli.config import load_config_readonly
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    from agent import auxiliary_client as aux
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new'
    materialize_product(home,inputs());token=set_hermes_home_override(str(home))
    values={'FRIDAY_LOCAL_KEY':'synthetic-local-scoped','EXA_API_KEY':'synthetic-exa-scoped'}
    protected_profile_keys(home, values)
    secret=set_secret_scope(values,profile_home=str(home))
    try:
        cfg=load_config_readonly()
        from hermes_cli import plugins
        # Native config getter/resolver remain real. No unrelated plugin
        # discovery/SDK activation is part of this source/offline fixture.
        monkeypatch.setattr(plugins,'get_plugin_auxiliary_tasks',lambda:[])
        for name,row in cfg['auxiliary'].items():
            if isinstance(row,dict):
                provider,model,url,key,mode=aux._resolve_task_provider_model(task=name)
                assert provider=='custom:friday-local' and model==inputs()['inference']['model']
                assert url==inputs()['inference']['base_url'] and key=='synthetic-local-scoped'
                assert mode=='chat_completions'
    finally:reset_secret_scope(secret);reset_hermes_home_override(token)


def test_actual_native_dashboard_gate_and_signed_operator_identity(tmp_path,monkeypatch):
    from hermes_cli import web_server as native
    from hermes_cli.friday_product_access import session_allowed
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new';spec=inputs()
    materialize_product(home,spec);token=set_hermes_home_override(str(home))
    monkeypatch.setenv('HERMES_HOME',str(home))
    import hermes_constants
    monkeypatch.setattr(hermes_constants,'_PINNED_PROCESS_HERMES_HOME',str(home))
    monkeypatch.setattr(native.app.state,'auth_required',False,raising=False)
    from hermes_cli import dashboard_auth
    monkeypatch.setattr(dashboard_auth,'list_providers',lambda:[])
    try:
        with pytest.raises(SystemExit):native._configure_auth_gate('127.0.0.1',False,None,None)
        assert native.app.state.auth_required is True
        from plugins.dashboard_auth.basic import BasicAuthProvider
        provider=BasicAuthProvider(username='explicit-operator',password_hash='synthetic-unused',secret=b'synthetic-signing-secret-32bytes')
        mint=provider._mint_session('explicit-operator');session=provider.verify_session(access_token=mint.access_token)
        assert session_allowed(session)
        assert not session_allowed(provider.verify_session(access_token=provider._mint_session('display-name').access_token))
        from dataclasses import replace
        assert not session_allowed(replace(session,org_id='foreign-org'))
    finally:reset_hermes_home_override(token)


def test_real_native_manifest_keys_and_protected_plugin_gate():
    from hermes_cli.plugins_manifest import parse_manifest_file,manifest_key
    from hermes_cli.plugins_discovery import gate_manifest
    import hermes_cli
    source=Path(hermes_cli.__file__).parent.parent
    bundle=compose_product(inputs());cfg=bundle['config']['plugins']
    for name in ('basic','nous','self_hosted','drain'):
        directory=source/'plugins/dashboard_auth'/name
        manifest=parse_manifest_file(directory/'plugin.yaml',directory,'bundled','dashboard_auth')
        assert manifest_key(manifest)=='dashboard_auth/'+name
        decision=gate_manifest(manifest,set(cfg['disabled']),set(cfg['enabled']))
        assert decision.action == ('load_now' if name=='basic' else 'placeholder')
    directory=ROOT/'plugins/friday_rework'
    manifest=parse_manifest_file(directory/'plugin.yaml',directory,'user','')
    assert manifest_key(manifest)=='friday_rework'
    assert gate_manifest(manifest,set(cfg['disabled']),set(cfg['enabled'])).action=='load'


def test_native_auth_requires_owned_launch_environment_not_context_scope(tmp_path,monkeypatch):
    from plugins.dashboard_auth.basic import _settings,SkipRegistration
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new'
    materialize_product(home,inputs());token=set_hermes_home_override(str(home))
    for key in ('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD','HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH',
                'HERMES_DASHBOARD_BASIC_AUTH_USERNAME','HERMES_DASHBOARD_BASIC_AUTH_SECRET'):
        monkeypatch.delenv(key,raising=False)
    secret=set_secret_scope({},profile_home=str(home))
    try:
        with pytest.raises(SkipRegistration):_settings()
    finally:reset_secret_scope(secret)
    secret=set_secret_scope({'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH':'synthetic-hash-fixture',
        'HERMES_DASHBOARD_BASIC_AUTH_SECRET':'synthetic-private-signing-key-32bytes',
        'HERMES_DASHBOARD_BASIC_AUTH_USERNAME':'explicit-operator'},profile_home=str(home))
    try:
        # Native auth does not consume context-local model credential scopes.
        # The renderer exposes this launcher prerequisite, never invents one.
        with pytest.raises(SkipRegistration):_settings()
        monkeypatch.setenv('HERMES_DASHBOARD_BASIC_AUTH_USERNAME','explicit-operator')
        monkeypatch.setenv('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH','synthetic-hash-fixture')
        monkeypatch.setenv('HERMES_DASHBOARD_BASIC_AUTH_SECRET','synthetic-private-signing-key-32bytes')
        resolved=_settings()
        assert resolved['username']=='explicit-operator'
        assert resolved['password_hash']=='synthetic-hash-fixture'
        assert resolved['secret']==b'synthetic-private-signing-key-32bytes'
    finally:reset_secret_scope(secret);reset_hermes_home_override(token)


def test_native_gateway_load_enables_only_declared_channels(tmp_path,monkeypatch):
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    from gateway.config import load_gateway_config,Platform
    from hermes_cli import plugins
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new'
    materialize_product(home,inputs());token=set_hermes_home_override(str(home))
    monkeypatch.setattr(plugins,'discover_plugins',lambda:None)
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    values={'TELEGRAM_BOT_TOKEN':'synthetic-telegram-token'}
    protected_profile_keys(home,values)
    secret=set_secret_scope(values,profile_home=str(home))
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','synthetic-telegram-token')
    monkeypatch.setenv('DISCORD_BOT_TOKEN','AMBIENT_UNDECLARED_DISCORD_CANARY')
    try:
        config=load_gateway_config()
        assert config.platforms[Platform.TELEGRAM].enabled is True
        assert config.platforms[Platform.DISCORD].enabled is False
        assert all(not p.enabled for name,p in config.platforms.items() if name!=Platform.TELEGRAM)
        assert config.multiplex_profiles is True
    finally:reset_secret_scope(secret);reset_hermes_home_override(token)


def test_partial_native_write_is_retained_and_cannot_be_adopted(tmp_path,monkeypatch):
    from hermes_cli import config
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new'
    monkeypatch.setattr(config,'atomic_config_replace',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic-write-failure')))
    with pytest.raises(OSError,match='synthetic-write'):materialize_product(home,inputs())
    assert home.exists() and not (home/'FRIDAY-PROFILE.json').exists()
    with pytest.raises(FileExistsError):materialize_product(home,inputs())


def worker_contract(home):
    pin={'path':str(home.parent/'synthetic-pin'),'sha256':'a'*64}
    return {'enabled':True,'runtime_profile':'default','runtime_home':str(home),
        'workspace_root':str(home.parent/'workspace'),'staging_root':str(home.parent/'staging'),
        'cache_roots':[str(home.parent/'cache')],'budget_seconds':60,'max_file_bytes':1024,'max_total_bytes':4096,
        'runtime_receipt':copy.deepcopy(pin),'dsh':{'payload_root':str(home.parent/'payload'),
        'toolchain_root':str(home.parent/'toolchain'),'node':copy.deepcopy(pin),'cli':copy.deepcopy(pin),
        'patch':copy.deepcopy(pin),'native_files':[copy.deepcopy(pin)],'key_name':'FRIDAY_DSH_KEY',
        'profile':'headless','memory_bytes':2*1024**3,'cpu_percent':200,'tasks':64,'shutdown_seconds':2,'tmp_bytes':64*1024**2,
        'web':{'profile':'exa-paid',**{k:copy.deepcopy(pin) for k in ('resolver','trust_bundle','egress_evidence','research_policy')}}}}


def test_explicit_worker_receipt_source_pins_preserved_without_ready_grant(tmp_path):
    spec=inputs();spec['runtime']=worker_contract(tmp_path/'new');before=copy.deepcopy(spec)
    bundle=compose_product(spec)
    assert bundle['config']['plugins']['entries']['friday_rework']['settings']['runtime']==before['runtime']
    assert spec==before and not bundle['contract']['ready']
    assert template(bundle)['config']['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}
    assert not (tmp_path/'synthetic-pin').exists()


@pytest.mark.parametrize('change',['missing_web','foreign_profile','foreign_home','tampered_pin'])
def test_worker_contract_and_ownership_missing_readiness_refuse(tmp_path,change):
    parent=tmp_path/'private';parent.mkdir(mode=0o700);home=parent/'new';spec=inputs();spec['runtime']=worker_contract(home)
    if change=='missing_web':del spec['runtime']['dsh']['web']
    elif change=='foreign_profile':spec['runtime']['runtime_profile']='foreign'
    elif change=='foreign_home':spec['runtime']['runtime_home']=str(parent/'foreign')
    else:spec['runtime']['runtime_receipt']['sha256']='invalid'
    with pytest.raises(ValueError):materialize_product(home,spec)
    assert not home.exists()


def test_two_actual_native_provider_resolutions_do_not_borrow_credentials(tmp_path,monkeypatch):
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    from hermes_cli.runtime_provider import resolve_runtime_with_fallback
    from hermes_cli.config import load_config_readonly
    parent=tmp_path/'private';parent.mkdir(mode=0o700)
    monkeypatch.setenv('OPENROUTER_API_KEY','AMBIENT_UNRELATED_CLOUD_CANARY')
    for number in (1,2):
        spec=inputs();spec['inference'].update(model='fixture-'+str(number),base_url='http://127.0.0.1:'+str(9000+number)+'/v1')
        home=parent/('profile-'+str(number));materialize_product(home,spec)
        values={'FRIDAY_LOCAL_KEY':'synthetic-local-'+str(number),'EXA_API_KEY':'synthetic-exa-'+str(number)}
        protected_profile_keys(home,values)
        token=set_hermes_home_override(str(home));secret=set_secret_scope(values,profile_home=str(home))
        try:
            config=load_config_readonly()
            runtime,fallback=resolve_runtime_with_fallback(config,requested='custom:friday-local',target_model=spec['inference']['model'])
            assert fallback is None and runtime['provider']=='custom'
            assert runtime['base_url']==spec['inference']['base_url']
            assert runtime['api_key']=='synthetic-local-'+str(number)
            assert runtime['model']==spec['inference']['model']
        finally:reset_secret_scope(secret);reset_hermes_home_override(token)


def test_cli_private_json_render_and_fresh_materialization(tmp_path,monkeypatch,capsys):
    from tools.configure_product import main
    parent=tmp_path/'private';parent.mkdir(mode=0o700);p=parent/'input.json'
    p.write_text(json.dumps(inputs()));p.chmod(0o600)
    before=p.read_bytes();monkeypatch.setattr('sys.argv',['configure_product.py','--input',str(p)])
    main();out=json.loads(capsys.readouterr().out)
    assert out['contract']['state']=='TEMPLATE_INCOMPLETE' and p.read_bytes()==before
    monkeypatch.setattr('sys.argv',['configure_product.py','--input',str(p),'--home',str(parent/'new')])
    main();out=json.loads(capsys.readouterr().out)
    assert out['runtime_acceptance']=='NOT_RUN' and p.read_bytes()==before


@pytest.mark.parametrize('kind',['duplicate_field','callable_yaml','public_input','symlink_input','hardlink_input'])
def test_cli_ambiguous_or_foreign_input_refuses_before_home(tmp_path,monkeypatch,capsys,kind):
    from tools.configure_product import main
    parent=tmp_path/'private';parent.mkdir(mode=0o700);p=parent/'input.json';p.write_text(json.dumps(inputs()));p.chmod(0o600)
    if kind=='duplicate_field':p.write_text('{"profile":"default","profile":"foreign"}')
    elif kind=='callable_yaml':p.write_text('!!python/object/apply:os.system ["SECRET_CANARY"]')
    elif kind=='public_input':p.chmod(0o644)
    elif kind=='symlink_input':p.rename(parent/'original');p.symlink_to(parent/'original')
    else:os.link(p,parent/'alias')
    monkeypatch.setattr('sys.argv',['configure_product.py','--input',str(p),'--home',str(parent/'new')])
    with pytest.raises(SystemExit) as result:main()
    assert result.value.code==2 and not (parent/'new').exists()
    assert 'SECRET_CANARY' not in capsys.readouterr().err


def test_actual_protected_onboarding_two_users_remain_unready_without_keys(env):
    # Existing exact native fixture; replace only installation-owned nonsecret
    # template/config. Native CAS, grant, scope and activation remain unchanged.
    from test_user_onboarding import prepare,activate,grant,home,cas,row,admitted
    spec=inputs();spec['dashboard']['operator']['user_id']='owner'  # Exact existing fixture operator.
    bundle=compose_product(spec);cfg=bundle['config'];env.cfg=cfg
    cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local']=template(bundle)
    (env.home/'config.yaml').write_text(json.dumps(cfg));(env.home/'config.yaml').chmod(0o600)
    for uid in ('1','2'):
        result=prepare(env,uid);assert result['enabled'] is False
        grant(env,uid)
        assert activate(env,uid)['state']=='DISABLED_SCOPED_KEYS_MISSING'
        assert not row(env,uid)['enabled'] and not admitted(env,uid)[0]
        assert not (home(env,uid)/'.env').exists()
    assert home(env,'1') != home(env,'2')
    assert (home(env,'1')/'SOUL.md').read_bytes() == (home(env,'2')/'SOUL.md').read_bytes()
    assert all(not (home(env,uid)/'skills').exists() or not list((home(env,uid)/'skills').iterdir()) for uid in ('1','2'))


# Import the exact protected native fixture, not a new consumer implementation.
from test_user_onboarding import env


def protected_profile_keys(home, values):
    # Admission now consumes the actual protected native dotenv, not an
    # unproved mapping that exists only in the test caller.
    p=home/'.env';p.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));p.chmod(0o600)
