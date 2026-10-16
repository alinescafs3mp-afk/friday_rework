"""Budget-only continuation after the real synthetic split-inference transaction."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from test_ordinary_inference_rebind import case as cutover, run, write, pin, u, f, users, Budget


@pytest.fixture
def case(cutover):
    case=cutover
    run(case)
    previous=case.request['current_input']
    current=json.loads(Path(previous['path']).read_bytes())
    current['product']['inference']['request_budget_seconds']={'first_event':360,'idle':150,'total':900}
    currentpath=case.path.with_name('budget-input.json');write(currentpath,json.dumps(current))
    prefix='profiles/dest_telegram/'
    retained=dict(case.request['retained'])
    for name in ('.env',prefix+'.env','FRIDAY-PROFILE.json'):
        retained[name]=pin(case.home/name)
    for path in case.tx.rglob('*'):
        if path.is_file():retained[str(path.relative_to(case.home))]=pin(path)
    before={n:pin(case.home/n) for n in case.request['before'] if n not in ('.env',prefix+'.env','FRIDAY-PROFILE.json')}
    case.request=dict(schema=u.REBIND_BUDGET_SCHEMA,seconds=180,home=str(case.home),profile='dest_telegram',
        previous_input=previous,current_input=pin(currentpath),native_unit=case.request['native_unit'],
        before=before,retained=retained)
    case.path=case.path.with_name('budget-request.json');write(case.path,json.dumps(case.request))
    case.tx=case.home/'preparation'/('ordinary-inference-rebind-'+previous['sha256'])
    case.before={n:(case.home/n).read_bytes() for n in before}
    case.retained={n:u.update_file_state(case.home/n) for n in retained}
    case.configs={n:yaml.safe_load((case.home/n).read_bytes()) for n in ('config.yaml',prefix+'config.yaml')}
    return case


def test_budget_only_changes_compiled_budget_leaves_without_credential_migration(case,monkeypatch):
    def credential_migration_forbidden(*args,**kwargs):raise AssertionError('credential migration called')
    monkeypatch.setattr(u,'inference_primary_reference',credential_migration_forbidden)
    monkeypatch.setattr(u,'inference_env_after',credential_migration_forbidden)
    result=run(case)
    assert result['state']=='EXACT_REQUEST_BUDGET_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
    assert result['ready'] is result['workers_enabled'] is result['consumers_started'] is result['database_changed'] is False
    budget={'first_event':360,'idle':150,'total':900}
    for name,original in case.configs.items():
        expected=copy.deepcopy(original)
        expected['providers']['friday-local']['request_budget_seconds']=budget
        if name=='config.yaml':
            templates=expected['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
            for template in templates.values():
                template['config']['providers']['friday-local']['request_budget_seconds']=budget
        assert yaml.safe_load((case.home/name).read_bytes())==expected
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    intent=json.loads((case.tx/'intent.json').read_bytes())
    assert intent['schema']==u.REBIND_BUDGET_SCHEMA
    assert set(intent['before'])==set(case.before)
    assert all(not n.endswith('.env') and n!='FRIDAY-PROFILE.json' for n in result['after'])
    assert not any(p.name=='.env' for p in case.tx.rglob('*'))
    with pytest.raises(ValueError):run(case)


@pytest.mark.parametrize('fault',['compressor','multipass','primary_model','primary_options','key_env',
    'missing_budget','unchanged','invalid_budget','source','credential_field','writable_env','missing_retained_env'])
def test_budget_scope_drift_refuses_without_consuming(case,fault):
    path=Path(case.request['current_input']['path']);value=json.loads(path.read_bytes())
    if fault=='compressor':value['product']['compression_inference']['model']='foreign'
    elif fault=='multipass':value['product']['compression_multipass']['max_calls']=63
    elif fault=='primary_model':value['product']['inference']['model']='foreign'
    elif fault=='primary_options':value['product']['inference']['request_options']['reasoning_echo']=False
    elif fault=='key_env':value['product']['inference']['key_env']='FOREIGN_KEY'
    elif fault in ('missing_budget','unchanged'):value['product']['inference'].pop('request_budget_seconds')
    elif fault=='invalid_budget':value['product']['inference']['request_budget_seconds']['first_event']=True
    elif fault=='source':value['project_files']['foreign.py']='0'*64
    elif fault=='credential_field':case.request['primary_credentials']={}
    elif fault=='writable_env':case.request['before']['.env']=case.request['retained'].pop('.env')
    elif fault=='missing_retained_env':case.request['retained'].pop('.env')
    write(path,json.dumps(value));case.request['current_input']=pin(path);write(case.path,json.dumps(case.request))
    with pytest.raises((ValueError,PermissionError)):run(case)
    assert all((case.home/n).read_bytes()==data for n,data in case.before.items())
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    assert not case.tx.exists()


@pytest.mark.parametrize('publication',range(1,6))
def test_each_budget_publication_failure_restores_exact_owned_files(case,monkeypatch,publication):
    publish=u.publish_update_file;count=0
    def fail(path,*args,**kwargs):
        nonlocal count
        result=publish(path,*args,**kwargs);count+=1
        if count==publication:raise RuntimeError('synthetic budget publication failure')
        return result
    monkeypatch.setattr(u,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='synthetic budget publication'):run(case)
    assert all((case.home/n).read_bytes()==data for n,data in case.before.items())
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    assert (case.tx/'rolled-back.json').is_file() and not (case.tx/'committed.json').exists()
    with pytest.raises(ValueError,match='consumed_no_retry'):run(case)
