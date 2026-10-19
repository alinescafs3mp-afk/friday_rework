"""Execute the previous v3 writer; renderer artifact validation is a named synthetic boundary."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest,yaml
from test_ordinary_inference_rebind import case as cutover,run,write,pin,u,f

@pytest.fixture
def case(cutover,monkeypatch):
    c=cutover;run(c);previous=c.request['current_input']
    current=json.loads(Path(previous['path']).read_bytes())
    binding=c.path.with_name('synthetic-renderer-binding.json');deployment=c.path.with_name('synthetic-renderer-deployment.json')
    write(binding,'{"synthetic_binding":true}');write(deployment,'{"synthetic_deployment":true}')
    exact={'binding':pin(binding),'deployment':pin(deployment)}
    # Whole transaction/compiler/native policy parsing is real. A synthetic
    # already-reviewed renderer replaces only local asset/attestation loading.
    from agent import protected_compressor_renderer as renderer
    monkeypatch.setattr(renderer,'load_renderer',lambda *a:SimpleNamespace(identity={'synthetic_fixture_only':True}))
    current['product']['compression_inference']['exact_renderer']=exact
    path=c.path.with_name('renderer-input.json');write(path,json.dumps(current))
    prefix='profiles/dest_telegram/';retained=dict(c.request['retained'])
    for name in ('.env',prefix+'.env','FRIDAY-PROFILE.json'):retained[name]=pin(c.home/name)
    for p in c.tx.rglob('*'):
        if p.is_file():retained[str(p.relative_to(c.home))]=pin(p)
    before={n:pin(c.home/n) for n in c.request['before'] if n not in ('.env',prefix+'.env','FRIDAY-PROFILE.json')}
    c.request=dict(schema=u.REBIND_RENDERER_SCHEMA,seconds=180,home=str(c.home),profile='dest_telegram',
        previous_input=previous,current_input=pin(path),native_unit=c.request['native_unit'],before=before,retained=retained)
    c.path=c.path.with_name('renderer-request.json');write(c.path,json.dumps(c.request))
    c.tx=c.home/'preparation'/('ordinary-inference-rebind-'+previous['sha256'])
    c.before={n:(c.home/n).read_bytes() for n in before};c.retained={n:u.update_file_state(c.home/n) for n in retained}
    c.exact=exact;return c

def test_previous_renderer_schema_runs_full_native_configuration_transaction(case):
    result=run(case)
    assert result['state']=='EXACT_COMPRESSOR_RENDERER_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    views=[cfg,yaml.safe_load((case.user/'config.yaml').read_bytes())]
    views.extend(t['config'] for t in cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates'].values())
    for view in views:
        assert view['providers']['friday-compression']['models']['dispatcher']['bounded_context']['exact_renderer']==case.exact
        assert view['auxiliary']['compression']['context_length']==40960
    with pytest.raises(ValueError):run(case)

@pytest.mark.parametrize('index',range(1,6))
def test_previous_renderer_rollback_still_restores_owned_files(case,monkeypatch,index):
    publish=u.publish_update_file;count=0
    def fail(*a,**kw):
        nonlocal count
        result=publish(*a,**kw);count+=1
        if count==index:raise RuntimeError('synthetic renderer transaction publication')
        return result
    monkeypatch.setattr(u,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='synthetic renderer'):run(case)
    assert all((case.home/n).read_bytes()==data for n,data in case.before.items())
    assert all(u.update_file_state(case.home/n)==state for n,state in case.retained.items())
    assert (case.tx/'rolled-back.json').is_file()
