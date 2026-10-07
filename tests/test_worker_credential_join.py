import json
import pytest
from test_host_native import setup,isolated,native,offline_boundary
from test_worker_selection import test_normal_profile_preserves_both_worker_configs_and_credential_domains as build

@pytest.mark.parametrize('tier',['exa-paid','exa-keyless'])
def test_compiled_mixed_profile_passes_native_credentials_and_refuses_domain_mutation(setup,tmp_path,monkeypatch,tier):
    import tools.configure_product as compiler
    from hermes_cli import friday_credential_admission as admission
    original=compiler.compose_product;bundles=[]
    def capture(spec):
        b=original(spec);bundles.append(b);return b
    monkeypatch.setattr(compiler,'compose_product',capture)
    build(setup,tmp_path,tier)
    assert len(bundles)==1
    b=bundles[0];setup.home.chmod(0o700)
    p=setup.home/'FRIDAY-PROFILE.json';p.write_text(json.dumps(b['contract']));p.chmod(0o600)
    assert b['config']['plugins']['entries']['friday_rework']['settings']['runtime']['workers']['a0']
    assert b['contract']['required_scoped_names']['worker_service']==['FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET']
    assert admission.profile_policy(setup.home,b['config']) == b['contract']
    import copy
    for name, replacement in [('inference_web',['FRIDAY_LLM_API_KEY']),
                               ('worker_service',[]),
                               ('worker_service',['FOREIGN_KEY'])]:
        bad=copy.deepcopy(b['contract']);bad['required_scoped_names'][name]=replacement
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):admission.profile_policy(setup.home,b['config'])
    p.write_text(json.dumps(b['contract']))
    bad=copy.deepcopy(b['config']);r=bad['plugins']['entries']['friday_rework']['settings']['runtime']
    r['workers']['a0']['enabled']=False
    with pytest.raises(ValueError,match='worker_map_shape'):admission.profile_policy(setup.home,bad)
    assert not setup.boundary.launches
