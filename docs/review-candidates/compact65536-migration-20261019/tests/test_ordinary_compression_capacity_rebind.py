"""Two real native managed-profile configs/proofs with synthetic process/source custody."""
import copy,json,os
from pathlib import Path
import pytest,yaml
import test_ordinary_inference_rebind as previous
from test_ordinary_inference_rebind import case as cutover,run,write,pin,u,f,users,ordinary,owner,_effective,principal_id,_plugin_data_namespace
from scripts.dsh_prepare import StopUnconfirmed

@pytest.fixture
def baseline(monkeypatch):
    original=previous.spec
    def spec():
        value=original();value['inference']['max_input']=40954;return value
    monkeypatch.setattr(previous,'spec',spec)

@pytest.fixture
def case(baseline,request):
    c=request.getfixturevalue('cutover');run(c)
    return prepare_capacity_case(c)


def prepare_capacity_case(c):
    # Add a second admitted native home using the real policy/access/proof shape.
    cfg=yaml.safe_load((c.home/'config.yaml').read_bytes())
    settings=cfg['plugins']['entries']['friday_rework']['settings']
    binding=copy.deepcopy(settings['user_isolation']['bindings'][0]);binding.update(user_id='synthetic-jarvis',runtime_profile='telegram-bot-100000002')
    settings['user_isolation']['bindings'].append(binding)
    settings['admin']['profiles'].append(binding['runtime_profile'])
    settings['product_access']['accounts'][0]['runtime_profiles'].append(binding['runtime_profile'])
    key=principal_id(*(binding[k] for k in ('platform','transport_profile','account_id','user_id')))
    cfg['gateway']['profile_routes'].append(dict(name='friday-'+key,platform='telegram',bot_profile='default',user_id='synthetic-jarvis',profile=binding['runtime_profile'],enabled=True))
    own=c.home/'profiles'/binding['runtime_profile'];own.mkdir(mode=0o700)
    for name in ('memories','workspace'):(own/name).mkdir(mode=0o700)
    for name in ('config.yaml','.env','SOUL.md'):write(own/name,(c.user/name).read_bytes())
    # Jarvis deliberately has no auth.lock; capacity-only must never create it.
    for name in ('config.yaml.lock','.env.lock'):write(own/name,b'')
    proof=json.loads((c.user/users.ONBOARDING).read_bytes());info=own.stat()
    proof.update(binding_sha256=users._fingerprint(binding),directory_identity=[info.st_dev,info.st_ino])
    write(own/users.ONBOARDING,json.dumps(proof))
    write(own/users.MARKER,json.dumps(dict(schema='friday.user-home.v1',principal=key,profile=own.name,binding_sha256=users._fingerprint(binding),onboarding_sha256=pin(own/users.ONBOARDING)['sha256'])))
    statepath=c.home/'plugin-data'/_plugin_data_namespace('friday_rework','')/'state.json'
    state=json.loads(statepath.read_bytes());row=copy.deepcopy(next(iter(state['product_access.v1']['users'].values())))
    row.update(user_id=binding['user_id'],generation=11);state['product_access.v1']['users'][key]=row;write(statepath,json.dumps(state))
    write(c.home/'config.yaml',yaml.safe_dump(cfg))
    marker=json.loads((c.home/f.MARKER).read_bytes())
    marker['profile_files']['config.yaml']=pin(c.home/'config.yaml')['sha256']
    marker['ordinary_gateway']['configuration_sha256']=ordinary.normalized_configuration(_effective(cfg))
    write(c.home/f.MARKER,json.dumps(marker));c.marker=marker
    previous_input=c.request['current_input'];current=json.loads(Path(previous_input['path']).read_bytes())
    current['product']['compression_inference'].update(context=65536,max_input=65530)
    currentpath=c.path.with_name('capacity-input.json');write(currentpath,json.dumps(current))
    retained=dict(c.request['retained'])
    for name in ('.env','FRIDAY-PROFILE.json','profiles/dest_telegram/.env','profiles/'+own.name+'/.env','profiles/'+own.name+'/SOUL.md'):
        retained[name]=pin(c.home/name)
    retained[str(statepath.relative_to(c.home))]=pin(statepath)
    for path in c.tx.rglob('*'):
        if path.is_file():retained[str(path.relative_to(c.home))]=pin(path)
    names=['config.yaml',f.MARKER]+[f'profiles/{p}/{n}' for p in ('dest_telegram',own.name) for n in ('config.yaml',users.ONBOARDING,users.MARKER)]
    before={n:pin(c.home/n) for n in names}
    c.request=dict(schema=u.REBIND_CAPACITY_SCHEMA,seconds=180,home=str(c.home),profiles=sorted(['dest_telegram',own.name]),
        previous_input=previous_input,current_input=pin(currentpath),native_unit=c.request['native_unit'],before=before,retained=retained)
    c.path=c.path.with_name('capacity-request.json');write(c.path,json.dumps(c.request))
    c.tx=c.home/'preparation'/('ordinary-inference-rebind-'+previous_input['sha256'])
    c.before={n:(c.home/n).read_bytes() for n in before};c.retained={n:u.update_file_state(c.home/n) for n in retained}
    c.configs={n:yaml.safe_load(data) for n,data in c.before.items() if n.endswith('config.yaml')}
    c.jarvis=own;return c

def test_exact_fifteen_leaves_and_native_proofs_preserve_all_other_semantics(case,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('credential migration called')
    monkeypatch.setattr(u,'inference_primary_reference',forbidden);monkeypatch.setattr(u,'inference_env_after',forbidden)
    result=run(case)
    assert result['state']=='EXACT_COMPRESSION_CAPACITY_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
    assert len(result['after'])==8
    for name,before in case.configs.items():u.inference_capacity_configuration(before,yaml.safe_load((case.home/name).read_bytes()),root=name=='config.yaml')
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    assert not (case.jarvis/'auth.lock').exists()
    assert not any(p.name=='.env' for p in case.tx.rglob('*'))
    ordinary.check(case.home,role=False)
    assert u.inference_capacity_profiles(case.home,case.request)==(case.user,case.jarvis)
    with pytest.raises(ValueError):run(case)

@pytest.mark.parametrize('fault',['primary','options','a0','budget','multipass','renderer','output','context_bool','input_bool','unchanged','source_bool','missing_profile','extra_profile','unknown_template','missing_proof','cas'])
def test_refuses_unrelated_delta_or_incomplete_scope_before_consumption(case,fault):
    path=Path(case.request['current_input']['path']);value=json.loads(path.read_bytes())
    if fault=='primary':value['product']['inference']['model']='foreign'
    elif fault=='options':value['product']['inference']['request_options']={}
    elif fault=='a0':value['product']['a0_deployment']['name']='foreign'
    elif fault=='budget':value['product']['inference']['request_budget_seconds']={'first_event':100,'idle':20,'total':200}
    elif fault=='multipass':value['product']['compression_multipass']['max_calls']=63
    elif fault=='renderer':value['product']['compression_inference']['exact_renderer']={}
    elif fault=='output':value['product']['compression_inference']['summary_output']=8192
    elif fault=='context_bool':value['product']['compression_inference']['context']=True
    elif fault=='input_bool':value['product']['compression_inference']['max_input']=True
    elif fault=='unchanged':value['product']['compression_inference'].update(context=40960,max_input=40954)
    elif fault=='source_bool':value['seconds']=True
    elif fault=='missing_profile':case.request['profiles'].pop()
    elif fault=='extra_profile':case.request['profiles'].append('unbound')
    elif fault=='unknown_template':
        p=case.jarvis/users.ONBOARDING;proof=json.loads(p.read_bytes());proof['template']='unknown';write(p,json.dumps(proof))
    elif fault=='missing_proof':(case.jarvis/users.ONBOARDING).unlink()
    elif fault=='cas':write(case.jarvis/'config.yaml',(case.jarvis/'config.yaml').read_bytes()+b'# foreign\n')
    write(path,json.dumps(value));case.request['current_input']=pin(path);write(case.path,json.dumps(case.request))
    with pytest.raises((ValueError,PermissionError,OSError)):run(case)
    assert not case.tx.exists()

@pytest.mark.parametrize('publication',range(1,9))
@pytest.mark.parametrize('cancel',[False,True])
def test_each_eight_file_failure_or_cancel_rolls_back_owned_beforeimages(case,monkeypatch,publication,cancel):
    publish=u.publish_update_file;count=0
    def fail(*a,**kw):
        nonlocal count
        result=publish(*a,**kw);count+=1
        if count==publication:raise KeyboardInterrupt('capacity cancellation') if cancel else RuntimeError('capacity publication failure')
        return result
    monkeypatch.setattr(u,'publish_update_file',fail)
    with pytest.raises(KeyboardInterrupt if cancel else RuntimeError):run(case)
    assert all((case.home/n).read_bytes()==data for n,data in case.before.items())
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    assert (case.tx/'rolled-back.json').is_file()
    with pytest.raises(ValueError,match='consumed_no_retry'):run(case)

def test_foreign_inode_is_retained_and_cleanup_reports_uncertain(case,monkeypatch):
    publish=u.publish_update_file
    def foreign(path,*a,**kw):
        result=publish(path,*a,**kw)
        if path==case.home/'config.yaml':
            other=path.with_name('foreign');write(other,path.read_bytes());os.replace(other,path)
            raise RuntimeError('capacity foreign inode')
        return result
    monkeypatch.setattr(u,'publish_update_file',foreign)
    with pytest.raises(StopUnconfirmed):run(case)
    assert not (case.tx/'rolled-back.json').exists()


from test_ordinary_renderer_rebind_transaction import case as renderer_transaction

@pytest.fixture
def renderer_capacity(baseline,request):
    c=request.getfixturevalue('renderer_transaction');run(c)
    return prepare_capacity_case(c)


def test_capacity_keeps_existing_renderer_documents_and_native_policy_refs(renderer_capacity):
    c=renderer_capacity;states={Path(ref['path']):u.update_file_state(Path(ref['path'])) for ref in c.exact.values()}
    result=run(c)
    assert result['state']=='EXACT_COMPRESSION_CAPACITY_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
    for name,before in c.configs.items():u.inference_capacity_configuration(before,yaml.safe_load((c.home/name).read_bytes()),root=name=='config.yaml')
    assert all(u.update_file_state(p)==state for p,state in states.items())
    assert not (c.jarvis/'auth.lock').exists()


def test_capacity_rejects_foreign_renderer_reference_inode_without_overwriting(renderer_capacity,monkeypatch):
    c=renderer_capacity;path=Path(c.exact['binding']['path']);publish=u.publish_update_file
    def foreign(destination,*a,**kw):
        result=publish(destination,*a,**kw)
        if destination==c.home/'config.yaml':
            other=path.with_name('foreign-binding.json');write(other,path.read_bytes());os.replace(other,path)
        return result
    monkeypatch.setattr(u,'publish_update_file',foreign)
    with pytest.raises(StopUnconfirmed):run(c)
    assert not (c.tx/'rolled-back.json').exists()
    assert json.loads(path.read_bytes())=={'synthetic_binding':True}
