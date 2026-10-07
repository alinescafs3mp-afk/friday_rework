"""Actual native onboarding -> private worker inputs -> original admission.

All sources, keys and reviewer receipts are explicitly synthetic. Native grants,
configuration writers, scopes, source hashes and worker admission are real;
only scheduling/SDK/transport effects are intercepted. Never runtime acceptance.
"""
import asyncio
import contextvars
import copy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys

import httpx
import pytest
from test_user_onboarding import (env, prepare, secrets, grant, activate, row, home, ident,
                                  cas, sha, admitted, source, raw, save)
from hermes_cli import friday_user_scope as scope
from hermes_cli.friday_product_access import current_access, principal_id
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from friday_admin_controls import worker_provision as provision
from friday_admin_controls import host_runtime
from friday_admin_controls.host_record import digest
from tools.render_dsh_local import build_patch

ROOT = Path(__file__).resolve().parents[1]


def pin(p):
    return {'path': str(p), 'sha256': sha(p)}


def inputs(env, uid='1', worker='dsh'):
    h = home(env, uid); root = h / 'workers' / worker
    shared = env.home / 'synthetic-readonly-sources'
    if not shared.exists():
        shared.mkdir(mode=0o700)
        for n, data in {'node': b'NEVER EXECUTED NODE', 'cli': b'NEVER EXECUTED INTACT CLI',
                        'native': b'NEVER EXECUTED SOURCE', 'resolver': b'nameserver 192.0.2.53',
                        'trust': b'SYNTHETIC CA', 'egress': b'NO NETWORK AUTHORITY',
                        'research': (ROOT / 'config/RESEARCH.md').read_bytes(),
                        'a0-runtime': b'NEVER EXECUTED INTACT A0 SOURCE', 'a0-launcher': b'NEVER EXECUTED',
                        'docker': b'NEVER EXECUTED', 'daemon': b'NEVER EXECUTED', 'policy': b'NO LIVE GRANT'}.items():
            p=shared/n;p.write_bytes(data);p.chmod(0o600)
    c = dict(enabled=True, runtime_profile='user-'+uid, runtime_home=str(h),
        workspace_root=str(root/'jobs'), staging_root=str(root/'staging'), cache_roots=[str(root/'cache')],
        budget_seconds=60, max_file_bytes=1024, max_total_bytes=4096,
        runtime_receipt={'path':str(root/'runtime-receipt.json'), 'sha256':'0'*64})
    network=None
    if worker=='dsh':
        cfg=env.template['config'];provider=cfg['providers']['friday-local'];model=cfg['model'];capacity=provider['models'][model['default']];b=capacity['bounded_context']
        rows=build_patch(purpose='temporary-local-test',api='openai-completions',base_url=model['base_url'],model=model['default'],
            api_key_env='LOCAL_KEY',context_window=capacity['context_length'],max_tokens=b['main_max_output_tokens'],
            summary_max_tokens=b['compression_max_output_tokens'],headroom_tokens=b['safety_margin_tokens']+b['template_overhead_tokens'],web_profile='exa-paid')
        data=(json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode()
        c['dsh']=dict(payload_root=str(shared),toolchain_root=str(shared),node=pin(shared/'node'),cli=pin(shared/'cli'),
            native_files=[pin(shared/'native')],patch={'path':str(root/'inputs/dsh-local.json'),'sha256':hashlib.sha256(data).hexdigest()},
            key_name='LOCAL_KEY',profile='headless',memory_bytes=2*1024**3,cpu_percent=200,tasks=64,shutdown_seconds=2,tmp_bytes=64*1024**2,
            web={'profile':'exa-paid','resolver':pin(shared/'resolver'),'trust_bundle':pin(shared/'trust'),
                 'egress_evidence':pin(shared/'egress'),'research_policy':pin(shared/'research')})
    else:
        c['a0']={'runtime':pin(shared/'a0-runtime'),'launcher':pin(shared/'a0-launcher'),'docker':pin(shared/'docker'),
            'daemon_unit':pin(shared/'daemon'),'policy':pin(shared/'policy'),'git_metadata':{'source':str(shared),'manifest_sha256':'a'*64},
            'expected_files':[{'logical_name':'result.txt','media_type':'text/plain'}],'capability':None,'owner_slot':'sol'}
        network={'name':'synthetic-existing-private-bridge','endpoints':['http://192.168.122.1:8001/v1','http://192.168.122.1:8002/v1'],'policy':pin(shared/'policy')}
    return c,network


def worker_prepare(env,uid='1',worker='dsh',runtime=None,network=None,**changes):
    c,n=inputs(env,uid,worker)
    return env.admin.onboarding_worker_prepare('default',**(dict(session=env.operator,expected_config_sha256=cas(env),generation=row(env,uid)['generation'],
        **ident(uid),worker=worker,runtime=c if runtime is None else runtime,a0_network=n if network is None else network)|changes))


def reviewed(env,prepared):
    """Synthetic external evidence producer, intentionally NOT product code."""
    c=prepared['runtime'];d=c['dsh'];p=Path(c['runtime_receipt']['path']);e=p.parent/'synthetic-independent-evidence.json'
    e.write_text('{"fixture_only":true,"runtime_acceptance":"NOT_RUN"}');e.chmod(0o600)
    r=dict(schema='friday-rework.dsh-runtime.v1',ready=True,runtime_sha256=digest({k:v for k,v in c.items() if k!='runtime_receipt'}),
        adapter_sha256=sha(ROOT/'plugins/friday_rework/adapters/dsh.py'),evidence=[pin(e)],web_source_pins={
            'plugins/friday_rework/worker_web.py':sha(ROOT/'plugins/friday_rework/worker_web.py'),
            'tools/web_profile.py':sha(ROOT/'tools/web_profile.py'),'config/RESEARCH.md':d['web']['research_policy']['sha256']})
    p.write_text(json.dumps(r));p.chmod(0o600)
    return pin(p)


def configure(env,prepared,receipt,uid='1',**changes):
    return env.admin.onboarding_worker_configure('default',**(dict(session=env.operator,expected_config_sha256=cas(env),generation=row(env,uid)['generation'],
        **ident(uid),worker='dsh',preparation=prepared['preparation'],runtime_receipt=receipt)|changes))


def configured(env,uid='1'):
    prepare(env,uid);p=worker_prepare(env,uid);secrets(env,uid);grant(env,uid)
    receipt=reviewed(env,p);r=configure(env,p,receipt,uid);assert not r['enabled'] and r['state']=='CONFIGURED_NATIVE_ACTIVATION_REQUIRED'
    assert activate(env,uid)['enabled'];return p,receipt


def test_two_distinct_homes_inputs_original_budgets_no_operator_adoption(env):
    a,b=[configured(env,u) for u in ('1','2')]
    for uid,pair in [('1',a),('2',b)]:
        p,r=pair;c=p['runtime'];assert c['runtime_home']==str(home(env,uid));assert c['budget_seconds']==60
        for field in ['workspace_root','staging_root']:assert Path(c[field]).is_relative_to(home(env,uid))
        assert Path(r['path']).is_relative_to(home(env,uid));assert not Path(c['runtime_receipt']['path']).samefile(env.home/'config.yaml')
        assert admitted(env,uid)[0];assert sha(env.home/'config.yaml')==cas(env)
        cfg=json.loads((home(env,uid)/scope.ONBOARDING).read_text());assert cfg['config_sha256']==sha(home(env,uid)/'config.yaml')
    assert a[0]['preparation']['path']!=b[0]['preparation']['path']
    assert a[1]['path']!=b[1]['path'];assert a[0]['runtime']['dsh']['patch']['path']!=b[0]['runtime']['dsh']['patch']['path']
    assert raw(env)['owner_unrelated']=='PRESERVE_ME'
    from agent.secret_scope import load_env_file
    assert load_env_file(home(env,'1')/'.env')['LOCAL_KEY']!=load_env_file(home(env,'2')/'.env')['LOCAL_KEY']


def test_preparation_cannot_mint_readiness_or_enable_worker_without_facts(env):
    prepare(env);p=worker_prepare(env);secrets(env);grant(env)
    assert not row(env)['enabled'];assert not (home(env)/scope.MARKER).exists()
    assert not Path(p['runtime']['runtime_receipt']['path']).exists()
    r=configure(env,p,p['runtime']['runtime_receipt']);assert r['state']=='DISABLED_WORKER_RUNTIME_UNVERIFIED'
    from hermes_cli.config import require_readable_config_before_write
    assert require_readable_config_before_write(home(env)/'config.yaml')['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}
    # Native non-worker profile activation is separate; it grants no worker.
    assert activate(env)['worker_execution']=='DISABLED_EXPLICIT_INSTALLATION_INPUT'


@pytest.mark.parametrize('bad',['principal','generation','home','workspace','cache','receipt','source','web','patch','key','budget','inline','account','transport'])
def test_wrong_worker_inputs_refuse_before_worker_preparation(env,bad):
    prepare(env);c,n=inputs(env);changes={}
    if bad=='principal':changes['user_id']='other'
    elif bad=='generation':changes['generation']=row(env)['generation']+1
    elif bad=='home':c['runtime_home']=str(env.home)
    elif bad=='workspace':c['workspace_root']=str(env.home/'jobs')
    elif bad=='cache':c['cache_roots']=[str(env.home/'cache')]
    elif bad=='receipt':c['runtime_receipt']['path']=str(env.home/'owner-receipt.json')
    elif bad=='source':c['dsh']['cli']['sha256']='f'*64
    elif bad=='web':c['dsh']['web']['egress_evidence']['sha256']='f'*64
    elif bad=='patch':c['dsh']['patch']['sha256']='f'*64
    elif bad=='key':c['dsh']['key_name']='FOREIGN_KEY'
    elif bad=='budget':c['budget_seconds']=True
    elif bad=='inline':c['dsh']['web']['api_key']='SECRET_CANARY'
    elif bad=='account':changes['account_id']='other'
    elif bad=='transport':changes['transport_profile']='foreign'
    original=sha(home(env)/scope.ONBOARDING)
    with pytest.raises(Exception):worker_prepare(env,runtime=c,**changes)
    assert not (home(env)/'workers/dsh').exists();assert sha(home(env)/scope.ONBOARDING)==original
    assert not row(env)['enabled']


@pytest.mark.parametrize('bad',['owner','other-user','source','web','config','preparation','ready','receipt-path','receipt-hash','budget','missing-keys','grant','generation'])
def test_existing_original_receipt_source_and_admission_guards_cannot_be_bypassed(env,bad):
    prepare(env);p=worker_prepare(env);secrets(env);grant(env);r=reviewed(env,p);changes={}
    if bad=='owner':r={'path':str(env.home/'owner-receipt.json'),'sha256':r['sha256']}
    elif bad=='other-user':
        prepare(env,'2');q=worker_prepare(env,'2');r=reviewed(env,q)
    elif bad=='source':Path(p['runtime']['dsh']['cli']['path']).write_text('DRIFT')
    elif bad=='web':Path(p['runtime']['dsh']['web']['egress_evidence']['path']).write_text('DRIFT')
    elif bad=='config':(home(env)/'config.yaml').write_text('{}')
    elif bad=='preparation':Path(p['preparation']['path']).write_text('{}')
    elif bad in ('ready','budget'):
        f=Path(r['path']);v=json.loads(f.read_text());v['ready']=False if bad=='ready' else True
        if bad=='budget':v['runtime_sha256']='f'*64
        f.write_text(json.dumps(v));r=pin(f)
    elif bad=='receipt-path':r['path']=str(home(env)/'other.json')
    elif bad=='receipt-hash':r['sha256']='f'*64
    elif bad=='missing-keys':(home(env)/'.env').write_text('EXA_API_KEY=synthetic-only\n')
    elif bad=='grant':
        from gateway.pairing import PairingStore
        PairingStore().revoke('telegram','1')
    elif bad=='generation':changes['generation']=row(env)['generation']+1
    original=(home(env)/'config.yaml').read_bytes()
    try:out=configure(env,p,r,**changes)
    except (PermissionError,ValueError,KeyError,OSError,host_runtime.HostUnavailable,scope.ScopeDenied):pass
    except Exception as exc:
        from friday_admin_controls.adapters.dsh import AdapterError
        assert isinstance(exc,AdapterError),type(exc)
    else:assert out['state'] in ('DISABLED_WORKER_RUNTIME_UNVERIFIED','DISABLED_NATIVE_GRANT_MISSING')
    assert (home(env)/'config.yaml').read_bytes()==original;assert not row(env)['enabled']
    assert not (home(env)/scope.MARKER).exists()


def test_interrupted_preparation_keeps_disabled_and_cannot_adopt_partial(env,monkeypatch):
    prepare(env);from friday_admin_controls import onboarding
    original=onboarding._new_file
    def fail(path,data):
        if path.name=='runtime-input.json':raise OSError('synthetic partial write')
        return original(path,data)
    monkeypatch.setattr(onboarding,'_new_file',fail)
    with pytest.raises(OSError):worker_prepare(env)
    monkeypatch.setattr(onboarding,'_new_file',original)
    with pytest.raises(FileExistsError):worker_prepare(env)
    assert not row(env)['enabled'];assert not (home(env)/scope.MARKER).exists()


@pytest.mark.parametrize('worker',['dsh','a0'])
def test_preexisting_symlink_worker_tree_refused(env,worker):
    prepare(env);base=home(env)/'workers';base.mkdir(mode=0o700);(base/worker).symlink_to(env.home,target_is_directory=True)
    with pytest.raises(Exception):worker_prepare(env,worker=worker)
    assert not row(env)['enabled']


def test_a0_own_native_settings_prepared_current_live_reconciliation_stays_blocked(env):
    # The original A0 local_profile has pinned dispatcher/embedding capacities.
    c=env.template['config'];old=c['model']['default'];model='dispatcher';url='http://192.168.122.1:8001/v1'
    c['model'].update(default=model,base_url=url);p=c['providers']['friday-local'];p['api']=url;p['models'][model]=p['models'][old];p['models'][model]['context_length']=40960
    for v in c['auxiliary'].values():
        if isinstance(v,dict):v.update(model=model,base_url=url)
    c['delegation'].update(model=model,base_url=url)
    cfg=raw(env);cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local']['config']=c;save(env,cfg)
    prepare(env);p=worker_prepare(env,worker='a0')
    assert p['state']=='PREPARED_RUNTIME_UNOBSERVED';assert not row(env)['enabled'];assert not Path(p['runtime']['runtime_receipt']['path']).exists()
    f=home(env)/'workers/a0/inputs/a0-native-files.json';v=json.loads(f.read_text())
    assert v['settings.json']['agent_profile']=='agent0';assert v['plugins/_code_execution/config.json']['ssh_enabled']=='false'
    assert v['/etc/searxng/settings.yml']['use_default_settings']['engines']['keep_only']==['google']
    assert {'FRIDAY_LLM_API_KEY','FRIDAY_EMBEDDINGS_API_KEY','EXA_API_KEY'}<=set(p['required_names'])
    for n in p['required_names']:
        env.setup.credentials('default',session=env.operator,expected_config_sha256=cas(env),generation=row(env)['generation'],**ident(),name=n,value='synthetic-'+n)
    result=env.admin.onboarding_worker_configure('default',session=env.operator,expected_config_sha256=cas(env),generation=row(env)['generation'],**ident(),
        worker='a0',preparation=p['preparation'],runtime_receipt=p['runtime']['runtime_receipt'])
    assert result['state']=='DISABLED_A0_RECONCILIATION_REQUIRED';assert not row(env)['enabled']
    prepare(env,'2');other=worker_prepare(env,'2',worker='a0')
    assert other['preparation']['path']!=p['preparation']['path']
    assert other['runtime']['runtime_home']!=p['runtime']['runtime_home']
    assert not row(env,'2')['enabled'] and not Path(other['runtime']['runtime_receipt']['path']).exists()


@pytest.mark.parametrize('bad',['native-route','cloud','missing'])
def test_a0_preparation_preserves_original_route_contract(env,bad):
    prepare(env);c,n=inputs(env,worker='a0')
    if bad=='cloud':n['endpoints'][0]='https://api.openai.com/v1'
    if bad=='missing':n={}
    with pytest.raises(Exception):worker_prepare(env,worker='a0',runtime=c,network=n)
    assert not (home(env)/'workers/a0').exists()


def test_existing_signed_operator_api_connects_prepare_and_configure(env):
    from test_admin_repair import basic_app
    prepare(env);c,_=inputs(env);app,token=basic_app(env)
    body=dict(expected_config_sha256=cas(env),generation=row(env)['generation'],**ident(),worker='dsh',runtime=c)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic') as client:
            path='/api/plugins/friday_rework/onboarding/worker/prepare?profile=default'
            refused=await client.post(path,json=body,headers={'Authorization':'Bearer forged'});assert refused.status_code==401
            response=await client.post(path,json=body,headers={'Authorization':'Bearer '+token});assert response.status_code==200,response.text
            return response.json()
    result=asyncio.run(scenario());assert result['state']=='PREPARED_RUNTIME_UNOBSERVED';assert not result['enabled']
    p={'runtime':c,'preparation':pin(home(env)/'workers/dsh/runtime-input.json')};secrets(env);grant(env);r=reviewed(env,p)
    body={k:v for k,v in body.items() if k!='runtime'};body.update(preparation=p['preparation'],runtime_receipt=r)
    async def finish():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic') as client:
            response=await client.post('/api/plugins/friday_rework/onboarding/worker/configure?profile=default',json=body,
                headers={'Authorization':'Bearer '+token});assert response.status_code==200,response.text
            return response.json()
    assert asyncio.run(finish())['state']=='CONFIGURED_NATIVE_ACTIVATION_REQUIRED';assert not row(env)['enabled']

@pytest.fixture
def joined(env,monkeypatch):
    configured(env);h=home(env);accepted,s=admitted(env);assert accepted
    token=set_hermes_home_override(str(h))
    try:
        with scope.scoped_source(s) as cap:
            from agent.secret_scope import load_env_file,set_secret_scope,reset_secret_scope
            secret_token=set_secret_scope(load_env_file(h/'.env'),profile_home=str(h));manager=None
            try:
                from hermes_cli import plugins
                from tools.registry import registry
                destination=h/'plugins/friday_rework'
                shutil.copytree(ROOT/'plugins/friday_rework',destination,ignore=shutil.ignore_patterns('__pycache__'))
                monkeypatch.setattr(plugins,'get_bundled_plugins_dir',lambda:h/'empty')
                monkeypatch.setattr(plugins.PluginManager,'_scan_entry_points',lambda self:[])
                manager=plugins.PluginManager(scope_key=str(h));manager.discover_and_load()
                assert manager._plugins['friday_rework'].enabled,manager._plugins['friday_rework'].error
                monkeypatch.setattr(plugins,'get_plugin_manager',lambda:manager)
                host=registry.get_entry('friday_work',scope=manager.scope_key).handler.__self__
                scheduled=[]
                def schedule(coro,**kwargs):scheduled.append(kwargs);coro.close()
                monkeypatch.setattr(host.ctx,'schedule_gateway_work',schedule)
                fields=dict(PLATFORM='telegram',CHAT_ID='shared-chat',CHAT_TYPE='group',THREAD_ID='topic',USER_ID='1',
                    KEY='own-key',ID='own-session',MESSAGE_ID='own-message',PROFILE='user-1')
                variables=[contextvars.ContextVar('HERMES_SESSION_'+k) for k in fields]
                tokens=[v.set(fields[k]) for v,k in zip(variables,fields)]
                ingress=dict(platform='telegram',session_key=fields['KEY'],source_profile='user-1',transport_profile='default',runtime_profile='user-1',chat_type='group',
                    message=dict(bot_id='bot-A',user_id='1',chat_id='shared-chat',thread_id='topic',message_id=fields['MESSAGE_ID'],platform_update_id='own-update',reply_to_message_id='',media=[]))
                origin=dict(user_id='1',chat_id='shared-chat',thread_id='topic',message_id=fields['MESSAGE_ID'],profile='user-1',chat_type='group')
                for callback in manager._hooks['post_gateway_admission']:
                    callback(admitted_ingress=ingress,session_key=fields['KEY'],message_id=fields['MESSAGE_ID'],platform='telegram',source=origin)
                call=dict(task_id=fields['ID'],session_id=fields['ID'],turn_id='own-turn',api_request_id='own-api',tool_call_id='own-call')
                args=dict(worker='dsh',brief='Check original owned private worker admission only',goal_check='Native admission retains original authority and budget')
                from model_tools import handle_function_call
                def invoke(name,args):
                    return json.loads(handle_function_call('tool_call',{'calls':[{'name':name,'arguments':args}]},**call,enabled_toolsets=['friday_rework']))
                from types import SimpleNamespace
                value=SimpleNamespace(env=env,home=h,host=host,scheduled=scheduled,cap=cap,args=args,call=call,invoke=invoke,ingress=ingress)
                try:yield value
                finally:
                    for v,t in zip(variables,tokens):v.reset(t)
            finally:
                if manager is not None:manager.unload()
                reset_secret_scope(secret_token)
    finally:reset_hermes_home_override(token)


def test_actual_onboarded_runtime_native_worker_and_result_admission(joined):
    w=joined;result=w.invoke('friday_work',w.args);assert result['accepted'],result
    original=w.host.store.snapshot()[result['reference']]
    assert original['budget_seconds']==60 and original['stop_intent'] is None and original['native'] is None
    assert original['host']['binding']['runtime']['runtime_home']==str(w.home)
    assert original['host']['binding']['user_authority']=={'principal_id':w.cap.key,'generation':w.cap.admission_generation}
    assert w.invoke('friday_result',{'action':'status','reference':result['reference']})['accepted']
    assert w.invoke('friday_work',w.args)==result;assert len(w.scheduled)==1
    assert w.host.store.snapshot()[result['reference']]==original


def test_configured_user_keys_home_and_receipt_stay_scoped_at_actual_consumer(joined):
    w=joined;from friday_admin_controls.worker_web import scoped_environment
    assert scoped_environment(str(w.home),('LOCAL_KEY','EXA_API_KEY'))['LOCAL_KEY']=='synthetic-1-LOCAL_KEY'
    with pytest.raises(Exception):scoped_environment(str(w.env.home),('LOCAL_KEY','EXA_API_KEY'))
    assert not w.invoke('friday_result',{'action':'status','reference':'foreign-job'})['accepted']
    from agent.secret_scope import set_secret_scope,reset_secret_scope
    token=set_secret_scope({'LOCAL_KEY':'foreign-canary','EXA_API_KEY':'foreign-web'},profile_home=str(w.env.home))
    try:
        with pytest.raises(Exception):scoped_environment(str(w.home),('LOCAL_KEY','EXA_API_KEY'))
    finally:reset_secret_scope(token)


def test_revoke_reenable_preserves_old_job_budget_result_refusal_and_owned_stop(joined):
    w=joined;result=w.invoke('friday_work',w.args);assert result['accepted']
    original=w.host.store.snapshot()[result['reference']];generation=w.cap.admission_generation
    with scope.authority(w.env.home):
        w.env.admin.set_user('default',**ident(),enabled=False,role='user')
        assert not row(w.env)['enabled']
        w.env.admin.set_user('default',**ident(),enabled=True,role='user')
    token=scope._CURRENT.set(None)
    try:
        with scope.authority(w.env.home):
            accepted,s=admitted(w.env);assert accepted
        with scope.scoped_source(s) as current:
            assert current.admission_generation>generation
            assert not w.invoke('friday_work',w.args)['accepted']
            assert not w.invoke('friday_result',{'action':'status','reference':result['reference']})['accepted']
            with pytest.raises(scope.ScopeDenied):w.host._start(original)
            assert w.host.store.snapshot()[result['reference']]==original and len(w.scheduled)==1
            from hermes_cli.plugin_command_context import _command_context
            command=dict(command='friday-stop',session_key='own-key',admitted_ingress=w.ingress,
                source=dict(platform='telegram',profile='user-1',user_id='1',chat_id='shared-chat',thread_id='topic'))
            with _command_context(w.host.ctx,command):stopped=json.loads(w.host.control('friday-stop',result['reference']))
            assert stopped['accepted'] and stopped['stop_intent']=='cancel' and stopped['quiescent']
            after=w.host.store.snapshot()[result['reference']]
            assert after['budget_seconds']==original['budget_seconds'] and after['deadline_unix']==original['deadline_unix']
            assert after['host']['binding']==original['host']['binding']
            assert after['host']['quiescence']['kind']=='never_submitted'
    finally:scope._CURRENT.reset(token)


@pytest.mark.parametrize('missing',['runtime_receipt','dsh','native_files','web'])
def test_missing_original_contract_refuses_whole_operator_workflow(env,missing):
    prepare(env);c,_=inputs(env)
    if missing in ('runtime_receipt','dsh'):c.pop(missing)
    else:c['dsh'].pop(missing)
    before=(home(env)/scope.ONBOARDING).read_bytes()
    with pytest.raises((host_runtime.HostUnavailable,KeyError)):worker_prepare(env,runtime=c)
    assert not row(env)['enabled'] and not (home(env)/'workers').exists()
    assert (home(env)/scope.ONBOARDING).read_bytes()==before


@pytest.mark.parametrize('disabled',[False,True])
def test_active_or_revoked_home_cannot_reprepare_or_relabel_worker(env,disabled):
    configured(env);generation=row(env)['generation'];existing=(home(env)/'workers/dsh/runtime-input.json').read_bytes()
    if disabled:env.admin.set_user('default',**ident(),enabled=False,role='user')
    with pytest.raises((PermissionError,ValueError)):worker_prepare(env)
    assert (home(env)/'workers/dsh/runtime-input.json').read_bytes()==existing
    assert row(env)['generation']==generation+(1 if disabled else 0)


def test_profile_config_drift_before_native_profile_lock_refuses_effects(env,monkeypatch):
    prepare(env);c,_=inputs(env);from hermes_cli import config as native
    from contextlib import contextmanager
    original=native.config_write_transaction;target=home(env)/'config.yaml'
    @contextmanager
    def raced(path,*args,**kwargs):
        with original(path,*args,**kwargs):
            if Path(path)==target:target.write_text(target.read_text()+'\n')
            yield
    monkeypatch.setattr(native,'config_write_transaction',raced)
    with pytest.raises(PermissionError,match='prepared_home_changed'):worker_prepare(env,runtime=c)
    assert not (home(env)/'workers').exists() and not row(env)['enabled']
