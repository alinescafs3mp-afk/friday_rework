"""Synthetic native config/proof transaction; source/process custody is a stub.

Actual accepted composer, local/split guards, ordinary check, user admission,
config/auth/env/admission locks, atomic writer, native onboarding prepare/finish,
owned-inode publisher and rollback run on private synthetic files. No network,
service, actual source-install or DB authority is asserted by these fixtures.
"""
import copy,hashlib,json,os,time,ast
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import pytest,yaml
from scripts import friday_ordinary_install as u
from scripts import friday_install as f
from scripts.install_containment import Budget
from tools.configure_product import compose_product
from hermes_cli import friday_user_scope as users
from hermes_cli import friday_ordinary_gateway as ordinary
from hermes_cli import friday_dashboard_owner as owner
from hermes_cli import friday_credential_admission as admission
from hermes_cli.plugins_state import _plugin_data_namespace
from hermes_cli.friday_product_access import principal_id
from hermes_cli.config_effective import _effective
from scripts.dsh_prepare import StopUnconfirmed

D=Path(f.__file__).resolve().parents[1]

def write(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else data.encode());path.chmod(0o600)

def pin(path):return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def spec():
    return {'profile':'default','inference':{'base_url':'http://192.168.1.78:8001/v1','model':'dispatcher',
        'key_env':'FRIDAY_LLM_API_KEY','context':40960,'max_input':40960,'main_output':4096,
        'summary_output':4096,'margin':1024,'template_overhead':2048},
        'web':{'profile':'exa-keyless','extract_char_limit':20000,'extract_timeout':30},
        'dashboard':{'host':'127.0.0.1','port':9119,'public_url':'https://friday.example:9119',
            'operator':{'provider':'basic','user_id':'fixture-operator','org_id':''}},
        'accounts':[{'platform':'telegram','transport_profile':'default','account_id':'fixture-bot'}],
        'runtime':{'enabled':False},'a0_deployment':__import__('plugins.friday_rework.adapters.a0_profile',fromlist=['legacy_profile']).legacy_profile()}

@contextmanager
def no_process_custody(*args,**kwargs):yield lambda:None

@pytest.fixture
def case(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir(mode=0o700);source=home/'hermes-agent';source.mkdir(mode=0o700)
    user=home/'profiles/dest_telegram';user.mkdir(mode=0o700,parents=True)
    (home/'profiles').chmod(0o700)
    for name in ('memories','workspace'):(user/name).mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME',str(home))
    old=spec();new=copy.deepcopy(old)
    new['compression_inference']=dict(old['inference'],key_env='FRIDAY_COMPRESSION_API_KEY')
    new['inference']=dict(old['inference'],base_url='http://127.0.0.1:30000/v1',model='synthetic-spark',
        context=262144,max_input=250000,main_output=8192,template_overhead=512,
        request_options={'reasoning_echo':True,'extra_body':{'chat_template_kwargs':{'enable_thinking':False}}})
    new['compression_multipass']={'enabled':True,'max_calls':64,'max_depth':16,'max_attempt_seconds':1800,'max_call_seconds':180}
    oldbundle=compose_product(old);cfg=copy.deepcopy(oldbundle['config'])
    binding=dict(platform='telegram',transport_profile='default',account_id='fixture-bot',user_id='synthetic-user',
        runtime_profile='dest_telegram',tools=oldbundle['contract']['ordinary_scope'])
    principal=tuple(binding[k] for k in ('platform','transport_profile','account_id','user_id'));key=principal_id(*principal)
    settings=cfg['plugins']['entries']['friday_rework']['settings']
    ordinary_template=copy.deepcopy(settings['onboarding']['templates']['friday-local'])
    ordinary_template.pop('worker_inputs',None)
    ordinary_template['config'].setdefault('tools',{}).setdefault('tool_search',{})['defer']=['synthetic_progressive_tool']
    settings['onboarding']['templates']['friday-ordinary-local']=ordinary_template
    settings['user_isolation']={'enabled':True,'bindings':[binding]}
    settings['admin']['profiles'].append('dest_telegram')
    settings['product_access']['accounts'][0]['runtime_profiles'].append('dest_telegram')
    cfg['gateway'].update(systemd_watchdog_seconds=30,profile_routes=[dict(name='friday-'+key,platform='telegram',
        bot_profile='default',user_id='synthetic-user',profile='dest_telegram',enabled=True)])
    cfg['platforms']['telegram']['extra']={'drop_pending_on_cold_boot':False,'unauthorized_dm_behavior':'pair'}
    cfg['display']['tone']='owner-setting-retained';cfg['owner_other']={'keep':'UNCHANGED'}
    usercfg=copy.deepcopy(settings['onboarding']['templates']['friday-local']['config'])
    usercfg['onboarding']={'seen':{'profile_build_offered':True}}
    usercfg['owner_other']={'keep':'PRIVATE_USER_SETTING'}
    for scope in (cfg,usercfg,*[t['config'] for t in settings['onboarding']['templates'].values()]):
        scope.pop('display',None);scope['model'].pop('reasoning_echo',None)
    usercfg.setdefault('tools',{}).setdefault('tool_search',{})['defer']=['synthetic_progressive_tool']
    for path,data in [(home/'config.yaml',yaml.safe_dump(cfg)),(user/'config.yaml',yaml.safe_dump(usercfg)),
        (home/'FRIDAY-PROFILE.json',json.dumps(oldbundle['contract'])),(home/'SOUL.md',oldbundle['soul']),(user/'SOUL.md',oldbundle['soul']),
        (home/'.env',"# root comment\nFRIDAY_LLM_API_KEY='SYNTH_ROOT_27B'\nEXA_API_KEY='ROOT_WEB_UNCHANGED'\nTELEGRAM_BOT_TOKEN='ROOT_CHANNEL_UNCHANGED'\n"),
        (user/'.env',"# user comment\nFRIDAY_LLM_API_KEY='SYNTH_USER_27B'\nEXA_API_KEY='USER_WEB_UNCHANGED'\n"),
        (source/'install-stamp.json','{}'),(source/'.hermes/bin/hermes','native-launcher-not-executed'),
        (home/'hermes-agent.source.json','{}')]:write(path,data)
    for own in (home,user):
        write(own/'.env',(own/'.env').read_bytes()+b"FRIDAY_EMBEDDINGS_API_KEY='SYNTH_EMBEDDING_PRESERVED'\nSEARXNG_SECRET='SYNTH_SEARX_PRESERVED'\n")
    statepath=home/'plugin-data'/_plugin_data_namespace('friday_rework','')/'state.json'
    access={'schema':'product_access.v1','users':{key:dict(zip(('platform','transport_profile','account_id','user_id'),principal),
        enabled=True,role='user',generation=7)}}
    write(statepath,json.dumps({'product_access.v1':access,'associations.v1':{'schema_version':1,'jobs':{}}}))
    write(statepath.with_name('admission.lock'),b'v1\n');write(statepath.with_name('.state.json.lock'),b'')
    for own in (home,user):
        for name in ('config.yaml.lock','.env.lock','auth.lock'):write(own/name,b'')
    info=user.stat()
    proof={'schema':'friday.onboarding.v1','binding_sha256':users._fingerprint(binding),'config_sha256':pin(user/'config.yaml')['sha256'],
        'soul_sha256':pin(user/'SOUL.md')['sha256'],'required_secrets':['FRIDAY_LLM_API_KEY','FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET'],
        'directory_identity':[info.st_dev,info.st_ino],'template':'friday-ordinary-local','authorization_home':str(home)}
    write(user/users.ONBOARDING,json.dumps(proof))
    write(user/users.MARKER,json.dumps({'schema':'friday.user-home.v1','principal':key,'profile':'dest_telegram',
        'binding_sha256':users._fingerprint(binding),'onboarding_sha256':pin(user/users.ONBOARDING)['sha256']}))
    previous={'home':str(home),'product':old,'project_files':{},'seconds':660}
    current=dict(previous,product=new)
    previouspath=tmp_path/'old-input.json';currentpath=tmp_path/'new-input.json'
    write(previouspath,json.dumps(previous));write(currentpath,json.dumps(current))
    history='preparation/ordinary-gateway/before/FRIDAY-INSTALL.json'
    historical={'completion_stage':'CLI_HOST_ONLY','original_attempt':{'seconds':300},'cli_segment':{'clock':{'seconds':660}}}
    write(home/history,json.dumps(historical))
    marker=dict(historical,completion_stage='TELEGRAM_ORDINARY',state='INSTALLED_TEMPLATE_INCOMPLETE',runtime_ready=False,
        worker_state='BOTH_WORKERS_PREPARATION_PENDING',input_sha256=pin(previouspath)['sha256'],
        source_receipt_sha256=pin(home/'hermes-agent.source.json')['sha256'],
        profile_files={n:pin(home/n)['sha256'] for n in ('config.yaml','SOUL.md','FRIDAY-PROFILE.json')})
    marker['ordinary_gateway']={'schema':'friday.ordinary-telegram.v1','scope':'TELEGRAM_RECEIVER_AND_AUTHENTICATED_ONBOARDING_ONLY',
        'configuration_sha256':ordinary.normalized_configuration(_effective(cfg)),
        'credential_files':{'.env':ordinary.credential_identity(home)[0],'auth.json':None},
        'profile_sha256':pin(home/'FRIDAY-PROFILE.json')['sha256'],'source_receipt_sha256':marker['source_receipt_sha256'],
        'baseline':{'runtime_profiles':['default'],'admin_profiles':['default'],'telegram_allowed_users':[]},
        'history':{history:pin(home/history)['sha256']},'operator_entry':{'input':pin(previouspath),'script':{'path':'SYNTHETIC_NOT_INVOKED','sha256':'0'*64}}}
    write(home/f.MARKER,json.dumps(marker))
    # Fake source/clock/process-custody only. Native config/contracts/proofs and
    # real host-independent lock/CAS/writer/admission checks remain actual.
    monkeypatch.setattr(f,'inspect',lambda *a,**kw:ordinary.check(home,role=False))
    monkeypatch.setattr(f,'spec_checked',lambda value,**kw:compose_product(value['product']))
    monkeypatch.setattr(f,'cli_historical_scope_closed',lambda *a:True)
    monkeypatch.setattr(owner,'SOURCE',source)
    monkeypatch.setattr(owner,'source_identity',lambda *a,**kw:{'receipt':pin(home/'hermes-agent.source.json')['sha256']})
    monkeypatch.setattr(u,'stopped_consumers',no_process_custody)
    monkeypatch.setattr(u,'retained_build_lock',no_process_custody)
    for n in range(23):write(home/'workers/closed-failed'/str(n),f'CLOSED_WORKER_{n}')
    for name in ('transcript.json','sessions.json','artifacts/owned.txt','preparation/attempt300.json','preparation/attempt660.json'):
        write(home/name,'KEEP_'+name)
    unit=tmp_path/'native.service';write(unit,'NOT_EXECUTED')
    for who in ('root','user'):write(tmp_path/(who+'-spark.json'),json.dumps({'selected':'SYNTH_SPARK_'+who.upper()}))
    prefix='profiles/dest_telegram/'
    before={n:pin(home/n) for n in ('config.yaml','FRIDAY-PROFILE.json',f.MARKER,'.env',prefix+'config.yaml',prefix+'.env',prefix+users.ONBOARDING,prefix+users.MARKER)}
    protected=['hermes-agent.source.json','hermes-agent/install-stamp.json','hermes-agent/.hermes/bin/hermes','SOUL.md',prefix+'SOUL.md',
        str(statepath.relative_to(home)),str(statepath.with_name('admission.lock').relative_to(home)),history]
    protected += [str(p.relative_to(home)) for p in (home/'workers/closed-failed').iterdir()]
    protected += ['transcript.json','sessions.json','artifacts/owned.txt','preparation/attempt300.json','preparation/attempt660.json']
    request=dict(schema=u.REBIND_SCHEMA,seconds=180,home=str(home),profile='dest_telegram',previous_input=pin(previouspath),current_input=pin(currentpath),
        native_unit=pin(unit),before=before,retained={n:pin(home/n) for n in protected},
        primary_credentials={who:{'path':str(tmp_path/(who+'-spark.json')),'format':'json','name':'selected'} for who in ('root','user')})
    rp=tmp_path/'request.json';write(rp,json.dumps(request))
    return SimpleNamespace(home=home,user=user,request=request,path=rp,marker=marker,proof=proof,protected=protected,before={n:(home/n).read_bytes() for n in before},
        protected_bytes={n:(home/n).read_bytes() for n in protected},tx=home/'preparation'/('ordinary-inference-rebind-'+request['previous_input']['sha256']))

def run(case):return u.rebind_inference(case.request,case.path,Budget(180))

def assert_restored(case):
    assert {n:(case.home/n).read_bytes() for n in case.before}==case.before
    assert {n:(case.home/n).read_bytes() for n in case.protected}==case.protected_bytes


def test_full_native_rebind_preserves_per_home_keys_proofs_history_and_settings(case):
    result=run(case)
    assert result['state']=='EXACT_INFERENCE_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
    root_values=u.inference_env_values((case.home/'.env').read_bytes())[0]
    user_values=u.inference_env_values((case.user/'.env').read_bytes())[0]
    assert root_values['FRIDAY_COMPRESSION_API_KEY']=='SYNTH_ROOT_27B'
    assert user_values['FRIDAY_COMPRESSION_API_KEY']=='SYNTH_USER_27B'
    assert root_values['FRIDAY_LLM_API_KEY']=='SYNTH_SPARK_ROOT'
    assert user_values['FRIDAY_LLM_API_KEY']=='SYNTH_SPARK_USER'
    assert b"EXA_API_KEY='ROOT_WEB_UNCHANGED'\nTELEGRAM_BOT_TOKEN='ROOT_CHANNEL_UNCHANGED'\n" in (case.home/'.env').read_bytes()
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes());usercfg=yaml.safe_load((case.user/'config.yaml').read_bytes())
    assert cfg['display']['show_reasoning'] is False and cfg['display']['platforms']['telegram']['show_reasoning'] is False
    assert usercfg['display']['show_reasoning'] is False and usercfg['display']['platforms']['telegram']['show_reasoning'] is False
    templates=cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    assert set(templates)=={'friday-local','friday-ordinary-local'}
    for template in templates.values():
        assert template['config']['model']['default']=='synthetic-spark'
        assert template['config']['display']['show_reasoning'] is False
        assert template['config']['display']['platforms']['telegram']['show_reasoning'] is False
        assert 'FRIDAY_COMPRESSION_API_KEY' in template['required_secrets']
    assert 'worker_inputs' not in templates['friday-ordinary-local']
    assert templates['friday-ordinary-local']['config']['tools']['tool_search']['defer']==['synthetic_progressive_tool']
    assert usercfg['tools']['tool_search']['defer']==['synthetic_progressive_tool']
    assert user_values['FRIDAY_EMBEDDINGS_API_KEY']=='SYNTH_EMBEDDING_PRESERVED' and user_values['SEARXNG_SECRET']=='SYNTH_SEARX_PRESERVED'
    assert cfg['a0_deployment']==spec()['a0_deployment'] and usercfg['a0_deployment']==spec()['a0_deployment']
    assert cfg['owner_other']=={'keep':'UNCHANGED'}
    assert usercfg['owner_other']=={'keep':'PRIVATE_USER_SETTING'} and usercfg['onboarding']=={'seen':{'profile_build_offered':True}}
    assert cfg['model']['context_length']==262144 and cfg['auxiliary']['compression']['context_length']==40960
    assert cfg['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}
    marker=json.loads((case.home/f.MARKER).read_bytes())
    assert marker['original_attempt']==case.marker['original_attempt'] and marker['cli_segment']==case.marker['cli_segment']
    assert marker['ordinary_gateway']['history']==case.marker['ordinary_gateway']['history']
    proof=json.loads((case.user/users.ONBOARDING).read_bytes())
    assert {k:v for k,v in proof.items() if k not in ('required_secrets','config_sha256')}=={k:v for k,v in case.proof.items() if k not in ('required_secrets','config_sha256')}
    assert {n:(case.home/n).read_bytes() for n in case.protected}==case.protected_bytes
    assert (case.tx/'committed.json').is_file()
    with pytest.raises(ValueError,match='input_pin_changed|ordinary_gateway_|consumed_no_retry'):run(case)

@pytest.mark.parametrize('failure_index',range(8))
def test_each_partial_publication_rolls_back_own_files(case,monkeypatch,failure_index):
    original=u.publish_update_file;calls=[]
    def fail(path,*a,**kw):
        result=original(path,*a,**kw)
        if path.is_relative_to(case.home) and '/stage/' not in str(path) and len(calls)<=failure_index:
            calls.append(path)
            if len(calls)==failure_index+1:raise RuntimeError('SYNTH_PRIMARY_FAILURE')
        return result
    monkeypatch.setattr(u,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='SYNTH_PRIMARY_FAILURE'):run(case)
    assert_restored(case);assert (case.tx/'rolled-back.json').is_file()


def test_foreign_inode_after_publication_is_not_overwritten_and_primary_error_retained(case,monkeypatch):
    original=u.publish_update_file
    def foreign(path,*a,**kw):
        result=original(path,*a,**kw)
        if path==case.home/'.env':
            replacement=path.with_name('foreign');write(replacement,path.read_bytes());os.replace(replacement,path)
            raise RuntimeError('SYNTH_PRIMARY_FAILURE')
        return result
    monkeypatch.setattr(u,'publish_update_file',foreign)
    with pytest.raises(StopUnconfirmed) as caught:run(case)
    assert isinstance(caught.value.__cause__,RuntimeError)
    assert caught.value.__cause__.args==('SYNTH_PRIMARY_FAILURE',)
    assert getattr(caught.value.__cause__,'friday_secondary_failures',())
    assert not (case.tx/'rolled-back.json').exists()

@pytest.mark.parametrize('kind',['auth_pool','symlink','hardlink','public_mode','cas','source_change','compressor_change','missing_key','lock_symlink'])
def test_meaningful_negative_controls_refuse_before_live_publication(case,monkeypatch,kind):
    if kind=='auth_pool':write(case.user/'auth.json',json.dumps({'credential_pool':{'custom:friday-local':[{'access_token':'SYNTH_OLD'}]}}))
    elif kind=='symlink':
        p=case.user/'config.yaml';p.unlink();p.symlink_to(case.home/'config.yaml')
    elif kind=='hardlink':
        p=case.user/'config.yaml';p.unlink();os.link(case.home/'config.yaml',p)
    elif kind=='public_mode':(case.user/'.env').chmod(0o644)
    elif kind=='cas':write(case.home/'config.yaml',(case.home/'config.yaml').read_bytes()+b'# concurrent\n')
    elif kind in ('source_change','compressor_change'):
        p=Path(case.request['current_input']['path']);value=json.loads(p.read_bytes())
        if kind=='source_change':value['project_files']['foreign.py']='0'*64
        else:value['product']['compression_inference']['context']=32768
        write(p,json.dumps(value));case.request['current_input']=pin(p);write(case.path,json.dumps(case.request))
    elif kind=='missing_key':write(Path(case.request['primary_credentials']['user']['path']),'{}')
    elif kind=='lock_symlink':
        p=case.user/'.env.lock';p.unlink();p.symlink_to(case.home/'.env.lock')
    before={n:(case.home/n).read_bytes() for n in case.before}
    with pytest.raises((ValueError,OSError,PermissionError)):run(case)
    assert {n:(case.home/n).read_bytes() for n in case.before}==before
    assert not (case.tx/'committed.json').exists()


def test_credential_duplicate_interpolation_and_existing_compressor_conflict():
    for raw in (b'FRIDAY_LLM_API_KEY=A\nFRIDAY_LLM_API_KEY=B\n',b'FRIDAY_LLM_API_KEY=${OTHER}\n',b'FRIDAY_LLM_API_KEY=A\nFRIDAY_COMPRESSION_API_KEY=DIFFERENT\n'):
        with pytest.raises(ValueError):u.inference_env_after(raw,'NEW')
    assert u.inference_env_values(u.inference_env_after(b"FRIDAY_LLM_API_KEY='a\\\'b\\\\c'\nKEEP=literal\n",'new\'\\key'))[0]=={
        'FRIDAY_LLM_API_KEY':"new'\\key",'FRIDAY_COMPRESSION_API_KEY':"a'b\\c",'KEEP':'literal'}


def test_compiler_delta_refuses_changed_route_but_preserves_unrelated_values():
    assert u.inference_delta({'route':'OLD','other':9},{'route':'OLD','other':1},{'route':'NEW','other':1})=={'route':'NEW','other':9}
    with pytest.raises(ValueError):u.inference_delta({'route':'UNKNOWN'},{'route':'OLD'},{'route':'NEW'})






def test_request_changes_under_native_locks_are_not_adopted(case,monkeypatch):
    original=u.inference_locks
    @contextmanager
    def raced(*a,**kw):
        with original(*a,**kw) as proof:
            write(case.path,case.path.read_bytes()+b'\n')
            yield proof
    monkeypatch.setattr(u,'inference_locks',raced)
    with pytest.raises(ValueError,match='retained_or_protected_reference_changed'):run(case)
    assert_restored(case)
    assert not (case.tx/'intent.json').exists()


def test_cancellation_after_first_owned_write_rolls_back_without_replaying(case,monkeypatch):
    original=u.publish_update_file;cancelled=[]
    def cancel(path,*a,**kw):
        result=original(path,*a,**kw)
        if path==case.home/'.env' and not cancelled:
            cancelled.append(True);raise KeyboardInterrupt()
        return result
    monkeypatch.setattr(u,'publish_update_file',cancel)
    with pytest.raises(KeyboardInterrupt):run(case)
    assert_restored(case)
    assert (case.tx/'rolled-back.json').exists()
    with pytest.raises(ValueError,match='consumed_no_retry'):run(case)


def test_concurrent_retained_access_change_is_kept_and_primary_error_retained(case,monkeypatch):
    original=u.publish_update_file;mutated=[]
    def mutate(path,*a,**kw):
        result=original(path,*a,**kw)
        if path==case.home/'.env' and not mutated:
            mutated.append(True)
            state=next(n for n in case.protected if n.endswith('/state.json'))
            write(case.home/state,(case.home/state).read_bytes()+b'\n')
            raise RuntimeError('SYNTH_PRIMARY_ACCESS_RACE')
        return result
    monkeypatch.setattr(u,'publish_update_file',mutate)
    with pytest.raises(StopUnconfirmed) as caught:run(case)
    assert caught.value.__cause__.args==('SYNTH_PRIMARY_ACCESS_RACE',)
    state=next(n for n in case.protected if n.endswith('/state.json'))
    assert (case.home/state).read_bytes()==case.protected_bytes[state]+b'\n'
    assert not (case.tx/'rolled-back.json').exists()






def test_unknown_template_and_worker_import_into_ordinary_are_rejected(case):
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    templates=cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    templates['unapproved-custom']=copy.deepcopy(templates['friday-ordinary-local'])
    from test_ordinary_inference_rebind_consumers import reseal_changed_fixture
    reseal_changed_fixture(case,cfg)
    with pytest.raises(ValueError,match='exact_existing_templates_required'):run(case)


def test_rebind_runtime_zero_never_counts_as_workers_off(case):
    for field in ('previous_input','current_input'):
        path=Path(case.request[field]['path']);value=json.loads(path.read_bytes());value['product']['runtime']={'enabled':0}
        write(path,json.dumps(value));case.request[field]=pin(path)
    # Initial inspect stub checks root binding; preserve its active source input
    # precondition in this synthetic native contract for the new before pin.
    marker=json.loads((case.home/f.MARKER).read_bytes());marker['input_sha256']=case.request['previous_input']['sha256']
    marker['ordinary_gateway']['operator_entry']['input']=case.request['previous_input']
    write(case.home/f.MARKER,json.dumps(marker));case.request['before'][f.MARKER]=pin(case.home/f.MARKER)
    write(case.path,json.dumps(case.request))
    with pytest.raises(ValueError,match='exact_preserved_compressor_and_scope_required'):run(case)
    assert not case.tx.exists()
