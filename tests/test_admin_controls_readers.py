import copy,json,time
from dataclasses import replace
import pytest
from test_admin_foundation import env,session
from test_admin_controls import local_config,body,basic


def test_operational_streaming_reaches_real_native_reader(env):
    local_config(env)
    result=env.admin.write_settings('default',body(env,'operational',key='streaming.enabled',value=True),session())
    from gateway.config_loader import read_yaml_layers,bridge_toplevel_keys
    from gateway.config import GatewayConfig
    raw=read_yaml_layers(env.home);gateway={};bridge_toplevel_keys(raw,raw.get('gateway'),gateway)
    assert result['recorded']
    assert GatewayConfig.from_dict(gateway).streaming.globally_enabled, 'recorded=True but native streaming reader ignores boolean gateway.streaming'


def test_operational_iterations_reaches_real_native_reader(env):
    local_config(env)
    env.admin.write_settings('default',body(env,'operational',key='agent.max_turns',value=17),session())
    from hermes_cli.config import load_config_readonly,resolve_turn_limit
    cfg=load_config_readonly()
    from gateway.run import _current_max_iterations
    actual=_current_max_iterations()
    assert actual==17, 'recorded=True but actual gateway reader uses agent.max_turns, not agent.max_turns; observed '+str(actual)


def test_installed_native_nested_skill_is_offered(env):
    local_config(env)
    skill=env.home/'skills/category/nested';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('---\nname: declared-nested\ndescription: Synthetic fixture\n---\nFixture instructions.\n')
    from tools.skills_tool import _find_all_skills
    native=[s['name'] for s in _find_all_skills(skip_disabled=True)]
    assert 'declared-nested' in native
    assert 'declared-nested' in env.admin.effective('default')['typed_options']['skills'], 'native installed categorized skills omitted by first-level directory scan'


def test_installed_skill_frontmatter_name_controls_real_reader(env):
    local_config(env)
    skill=env.home/'skills/directory-alias';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('---\nname: declared-name\ndescription: Synthetic fixture\n---\nFixture instructions.\n')
    from tools.skills_tool import _find_all_skills
    assert 'declared-name' in [s['name'] for s in _find_all_skills(skip_disabled=True)]
    env.admin.write_settings('default',body(env,'skill',name='declared-name',enabled=False),session())
    assert 'declared-name' not in [s['name'] for s in _find_all_skills()], 'recorded=True disables directory name but native catalog indexes declared name'


def test_essential_skill_cannot_be_reported_disabled(env):
    local_config(env)
    skill=env.home/'skills/hermes-agent';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('---\nname: hermes-agent\ndescription: Synthetic fixture\n---\nFixture instructions.\n')
    from tools.skills_tool import _find_all_skills
    try: result=env.admin.write_settings('default',body(env,'skill',name='hermes-agent',enabled=False),session())
    except (ValueError,PermissionError):return
    assert 'hermes-agent' not in [s['name'] for s in _find_all_skills()], 'recorded=True though native ESSENTIAL_SKILLS refuses disabling hermes-agent'


def test_schedule_operator_revoked_during_store_read_is_refused(env,monkeypatch):
    from cron import jobs
    local_config(env);job=jobs.create_job(prompt='Synthetic never executed',schedule='every 1h',name='revocation',paused=True)
    old_get=jobs.get_job;called=[]
    def revoke(job_id):
        result=old_get(job_id)
        if not called:
            called.append(True)
            from hermes_cli.config import require_readable_config_before_write,atomic_config_write
            cfg=require_readable_config_before_write();cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators']=[{'provider':'basic','user_id':'replacement-owner','org_id':''}]
            atomic_config_write(env.home/'config.yaml',cfg)
        return result
    monkeypatch.setattr(jobs,'get_job',revoke)
    try:env.admin.schedules('default','resume',job['id'],session())
    except PermissionError:pass
    assert not old_get(job['id'])['enabled'], 'revoked operator resumed schedule after authorization and before native mutation'


def test_settings_rechecks_revocation_before_atomic_write(env,monkeypatch):
    from hermes_cli import managed_scope,config
    local_config(env);original=config.require_readable_config_before_write()
    called=[]
    def revoke(key):
        if not called:
            called.append(True);cfg=copy.deepcopy(original);cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators']=[{'provider':'basic','user_id':'replacement-owner','org_id':''}];config.atomic_config_write(env.home/'config.yaml',cfg)
        return False
    monkeypatch.setattr(managed_scope,'is_key_managed',revoke)
    with pytest.raises(PermissionError):env.admin.write_settings('default',body(env,'operational',key='agent.max_turns',value=17),session())
    assert config.require_readable_config_before_write().get('agent',{})==original.get('agent',{})


@pytest.mark.parametrize('case',['provider-missing','wrong-key','expired-signed','foreign-org','provider-mismatch','operator-revoked','profile-revoked'])
def test_prove_native_operator_negative(env,monkeypatch,case):
    from friday_admin_controls.admin_controls import prove_operator
    from hermes_cli.dashboard_auth import registry
    p=basic();owner=p._mint_session('owner');verifier=p
    if case=='provider-missing':verifier=None
    elif case=='wrong-key':
        verifier=basic();verifier._secret=b'OTHER-SYNTHETIC-key-32-bytes-long'
    elif case=='expired-signed':
        import sys
        signer=sys.modules[p.__module__]._sign
        owner=replace(owner,access_token=signer({'sub':'owner','kind':'access','exp':int(time.time())-1},p._secret))
    elif case in ('foreign-org','provider-mismatch'):
        signed=p.verify_session(access_token=owner.access_token)
        if case=='foreign-org':signed=replace(signed,org_id='other-org')
        else:signed=replace(signed,provider='other-provider')
        monkeypatch.setattr(p,'verify_session',lambda **kw:signed)
    elif case=='operator-revoked':env.cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators']=[{'provider':'basic','user_id':'replacement-owner','org_id':''}];env.save()
    elif case=='profile-revoked':env.cfg['plugins']['entries']['friday_rework']['settings']['admin']['profiles']=['satellite'];env.save()
    monkeypatch.setattr(registry,'get_provider',lambda *a,**kw:verifier)
    with pytest.raises(PermissionError):prove_operator('basic',owner.access_token,env.home,'default')

import copy,json,os,stat
from types import SimpleNamespace
import pytest
from test_admin_foundation import env,session
from test_admin_controls import local_config,body

@pytest.mark.parametrize('override',[{'model':{'provider':'openrouter','default':'synthetic-cloud'}},{'fallback_providers':[{'provider':'openrouter','model':'synthetic-cloud'}]}])
def test_local_only_invariant_uses_native_effective_managed_config(env,monkeypatch,override):
    from hermes_cli import config,managed_scope
    local_config(env);managed=env.home/'managed-fixture';managed.mkdir();(managed/'config.yaml').write_text(json.dumps(override))
    monkeypatch.setenv('HERMES_MANAGED_DIR',str(managed));managed_scope.invalidate_managed_cache()
    before=(env.home/'config.yaml').read_bytes()
    try:env.admin.write_settings('default',body(env,'web',profile='exa-paid',extract_timeout=12,extract_char_limit=6000),session())
    except (ValueError,PermissionError):return
    effective=config.load_config_readonly()
    assert not effective.get('fallback_providers') and effective['model']['provider'].startswith('custom:'), 'typed write succeeds though effective managed inference contains cloud provider/fallback'


def test_cas_does_not_clobber_intervening_native_raw_write(env,monkeypatch):
    from hermes_cli import config,managed_scope
    local_config(env);called=[]
    def native_writer(key):
        if not called:
            called.append(True);fresh=config.require_readable_config_before_write();fresh['web']['extract_timeout']=99;config.atomic_config_write(env.home/'config.yaml',fresh)
        return False
    monkeypatch.setattr(managed_scope,'is_key_managed',native_writer)
    try:env.admin.write_settings('default',body(env,'operational',key='agent.max_turns',value=17),session())
    except (ValueError,PermissionError):pass
    assert config.require_readable_config_before_write()['web']['extract_timeout']==99, 'initial-only CAS silently clobbers native raw write before final commit'


def test_schedule_revocation_at_native_locked_mutation(env, monkeypatch):
    from cron import jobs
    from hermes_cli import config
    local_config(env)
    job = jobs.create_job(prompt='Synthetic never executed', schedule='every 1h', paused=True)
    original = jobs._fill_missing_next_run
    def revoke(updated):
        original(updated)
        cfg = config.require_readable_config_before_write()
        cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators'] = [
            {'provider': 'basic', 'user_id': 'replacement-owner', 'org_id': ''}]
        config.atomic_config_write(env.home/'config.yaml', cfg)
    monkeypatch.setattr(jobs, '_fill_missing_next_run', revoke)
    with pytest.raises(PermissionError):
        env.admin.schedules('default', 'resume', job['id'], session())
    assert not jobs.get_job(job['id'])['enabled']


def test_skill_enable_preserves_disabled_duplicate_and_observes_platform(env, monkeypatch):
    from tools.skills_tool import _find_all_skills, clear_skills_cache
    from agent.skill_utils import get_disabled_skill_names
    from hermes_cli import config
    local_config(env)
    for name in ('one', 'two'):
        directory = env.home/'skills'/name
        directory.mkdir(parents=True)
        (directory/'SKILL.md').write_text('---\nname: duplicate\ndescription: Synthetic fixture\n---\nFixture instructions.\n')
    cfg = config.require_readable_config_before_write()
    cfg['skills'].update(disabled=['duplicate'], platform_disabled={'telegram': ['duplicate']})
    config.atomic_config_write(env.home/'config.yaml', cfg)
    clear_skills_cache()
    names = sorted(row['name'] for row in _find_all_skills(skip_disabled=True))
    assert names == ['one', 'two']
    env.admin.write_settings('default', body(env, 'skill', name='one', enabled=True), session())
    monkeypatch.setenv('HERMES_PLATFORM', 'telegram')
    assert get_disabled_skill_names() == {'two'}
    assert [row['name'] for row in _find_all_skills()] == ['one']

@pytest.mark.parametrize('mode',[stat.S_IFSOCK|0o666,stat.S_IFREG|0o600,stat.S_IFLNK|0o600])
def test_unprotected_native_endpoint_refuses_before_token_transport(env,monkeypatch,mode):
    from gateway import control_socket
    from friday_admin_controls.admin_controls import request_control
    monkeypatch.setattr(control_socket,'resolve_client_socket_path',lambda home:SimpleNamespace(lstat=lambda:SimpleNamespace(st_mode=mode,st_uid=os.getuid())))
    called=[];monkeypatch.setattr(control_socket,'query_gateway_control',lambda *a,**kw:called.append(kw))
    with pytest.raises(PermissionError):request_control(env.home,'default',session(),'native-'+'a'*64,'cancel')
    assert not called

@pytest.mark.parametrize('response',[None,b'broken',b'{"ok":false}',b'{"ok":true,"result":{"accepted":"yes"}}'])
def test_actual_native_query_unknown_serialization_never_retries(env,monkeypatch,response):
    from gateway import control_socket
    from friday_admin_controls.admin_controls import request_control
    monkeypatch.setattr(control_socket,'resolve_client_socket_path',lambda home:SimpleNamespace(lstat=lambda:SimpleNamespace(st_mode=stat.S_IFSOCK|0o600,st_uid=os.getuid())))
    calls=[]
    def query(home,request,timeout):calls.append(json.loads(request));return response
    monkeypatch.setattr(control_socket,'_query_unix_socket',query)
    result=request_control(env.home,'default',session(),'native-'+'a'*64,'cancel')
    assert result=={'accepted':False,'execution':'UNKNOWN','error':'owning_control_response_lost'}
    assert len(calls)==1
    assert set(calls[0]['params']['arguments'])=={'provider','access_token','task_id','action'}
    assert 'access_token' not in json.dumps(result)

@pytest.mark.parametrize('case',['disable-included-terminal','enable-natively-disabled-terminal','mandatory-web-natively-disabled'])
def test_toolset_edit_matches_effective_native_selection(env,case):
    from hermes_cli import config
    from model_tools import _select_tool_names
    local_config(env)
    raw=config.require_readable_config_before_write()
    if case=='disable-included-terminal':raw['platform_toolsets']['telegram']=['web','debugging']
    else:raw.setdefault('agent',{})['disabled_toolsets']=['terminal' if case=='enable-natively-disabled-terminal' else 'web']
    config.atomic_config_write(env.home/'config.yaml',raw)
    try:env.admin.write_settings('default',body(env,'toolset',name='terminal',enabled=case!='disable-included-terminal'),session())
    except (PermissionError,ValueError):return
    current=config.load_config_readonly()
    effective=_select_tool_names(current['platform_toolsets']['telegram'],current.get('agent',{}).get('disabled_toolsets'),True)
    if case=='disable-included-terminal':assert 'terminal' not in effective, 'recorded disable leaves terminal enabled through native composite debugging'
    elif case=='enable-natively-disabled-terminal':assert 'terminal' in effective, 'recorded enable leaves terminal disabled by native agent.disabled_toolsets'
    else:assert 'web_search' in effective, 'mandatory web check uses only listed names and misses native disabled_toolsets subtraction'


def test_streaming_retains_native_top_level_precedence_and_options(env):
    from hermes_cli import config
    from gateway.config_loader import read_yaml_layers, bridge_toplevel_keys
    from gateway.config import GatewayConfig
    local_config(env)
    cfg = config.require_readable_config_before_write()
    cfg['streaming'] = {'enabled': False, 'transport': 'edit', 'edit_interval': 1.2}
    cfg['gateway'] = {'streaming': {'enabled': False, 'transport': 'auto'}}
    config.atomic_config_write(env.home/'config.yaml', cfg)
    env.admin.write_settings('default', body(env, 'operational', key='streaming.enabled', value=True), session())
    raw = read_yaml_layers(env.home); gateway = {}
    bridge_toplevel_keys(raw, raw.get('gateway'), gateway)
    value = GatewayConfig.from_dict(gateway).streaming
    assert value.globally_enabled and value.transport == 'edit' and value.edit_interval == 1.2


def test_profile_covers_every_native_auxiliary_route(env):
    from hermes_cli import config
    local_config(env)
    for role, route in config.load_config_readonly()['auxiliary'].items():
        if isinstance(route, dict) and route.get('enabled', True):
            assert route['provider'] == 'custom:friday-local', role
            assert route['fallback_chain'] == [] and route['base_url'] == 'http://127.0.0.1:8001/v1'


def test_native_config_transaction_serializes_competing_writer(env, monkeypatch):
    import threading
    from hermes_cli import config, managed_scope
    local_config(env)
    attempted, committed = threading.Event(), threading.Event()
    failures, observed, threads = [], [], []
    def writer():
        try:
            attempted.set()
            with config.config_write_transaction(env.home/'config.yaml'):
                cfg = config.require_readable_config_before_write(env.home/'config.yaml')
                observed.append(cfg['agent']['max_turns'])
                cfg['web']['extract_timeout'] = 99
                config.atomic_config_write(env.home/'config.yaml', cfg)
            committed.set()
        except BaseException as error:
            failures.append(type(error).__name__)
    def interleave(key):
        if not threads:
            thread = threading.Thread(target=writer)
            threads.append(thread); thread.start()
            assert attempted.wait(1)
            assert not committed.wait(.03)
        return False
    monkeypatch.setattr(managed_scope, 'is_key_managed', interleave)
    try:
        env.admin.write_settings('default', body(env, 'operational', key='agent.max_turns', value=17), session())
    finally:
        for thread in threads:
            thread.join(3)
            assert not thread.is_alive()
    assert not failures and committed.is_set() and observed == [17]
    cfg = config.require_readable_config_before_write()
    assert cfg['agent']['max_turns'] == 17 and cfg['web']['extract_timeout'] == 99
