"""One profile selects intact workers; association custody remains unchanged."""
import copy
import sys

import pytest

from test_host_native import setup, isolated, native, offline_boundary, ingress, invoke, settle


def a0_candidate(dsh, tmp_path):
    r = copy.deepcopy(dsh)
    del r['dsh']
    for k in ('workspace_root', 'staging_root'):
        r[k] = str(tmp_path / ('a0-' + k))
    r['cache_roots'] = [str(tmp_path / 'a0-cache')]
    p = {'path': str(tmp_path / 'unexecuted'), 'sha256': 'a' * 64}
    r['a0'] = {k: copy.deepcopy(p) for k in ('runtime', 'launcher', 'docker', 'daemon_unit', 'policy')}
    r['a0'].update(owner_slot='astra', capability=None,
                   expected_files=[{'logical_name': 'result.txt', 'media_type': 'text/plain'}],
                   git_metadata={'source': str(tmp_path / 'metadata'), 'manifest_sha256': 'a' * 64})
    return r


def mapped(setup, tmp_path):
    return {'enabled': True, 'workers': {'dsh': setup.runtime, 'a0': a0_candidate(setup.runtime, tmp_path)}}


def hr(setup):
    return sys.modules[setup.module.__package__ + '.host_runtime']


def test_each_worker_keeps_exact_runtime_and_original_single_profile(setup, tmp_path):
    m = hr(setup); value = mapped(setup, tmp_path)
    assert m.select_runtime(value, 'dsh') == setup.runtime
    assert m.select_runtime(value, 'a0') == value['workers']['a0']
    assert m.select_runtime(setup.runtime, 'dsh') == setup.runtime
    assert m.configured_runtimes({'enabled': False}) == {}
    selected = m.select_runtime(value, 'a0'); selected['budget_seconds'] += 1
    assert selected != value['workers']['a0']
    assert value['workers']['a0']['a0']['capability'] is None


@pytest.mark.parametrize('change', ['home', 'profile', 'kind', 'workspace', 'cache', 'enabled', 'extra', 'empty', 'unknown', 'nested'])
def test_map_refuses_foreign_or_ambiguous_runtime_before_native_effect(setup, tmp_path, change):
    value = mapped(setup, tmp_path); a = value['workers']['a0']
    if change == 'home': a['runtime_home'] = str(tmp_path / 'other-home')
    if change == 'profile': a['runtime_profile'] = 'other'
    if change == 'kind': value['workers']['a0'] = setup.runtime
    if change == 'workspace': a['workspace_root'] = setup.runtime['staging_root'] + '/nested'
    if change == 'cache': a['cache_roots'] = setup.runtime['cache_roots']
    if change == 'enabled': value['enabled'] = 1
    if change == 'extra': value['owner'] = 'model-supplied'
    if change == 'empty': value['workers'] = {}
    if change == 'unknown': value['workers']['other'] = setup.runtime
    if change == 'nested': value['workers']['a0'] = {'enabled': True, 'workers': {'a0': a}}
    with pytest.raises(hr(setup).HostUnavailable): hr(setup).select_runtime(value, 'dsh')
    assert not setup.boundary.launches and setup.host.store.snapshot() == {}


def test_addition_never_replaces_existing_worker_or_resets_its_budget(setup, tmp_path):
    m = hr(setup); first = m.add_runtime({'enabled': False}, 'dsh', setup.runtime)
    assert first == setup.runtime
    pair = m.add_runtime(first, 'a0', a0_candidate(first, tmp_path))
    assert pair['workers']['dsh'] == first
    with pytest.raises(m.HostUnavailable, match='existing_worker_not_adopted'):
        m.add_runtime(pair, 'dsh', first)
    with pytest.raises(m.HostUnavailable): m.select_runtime({'enabled': False}, 'dsh')
    with pytest.raises(m.HostUnavailable): m.configured_runtimes({'enabled': 0})


@pytest.mark.asyncio
async def test_native_dsh_selection_through_real_host_and_result_state(setup, tmp_path):
    setup.configure(mapped(setup, tmp_path))
    proof = await ingress(setup, file=True)
    answer = invoke(setup, proof)
    assert answer['accepted'] and answer['worker'] == 'dsh'
    await settle(setup)
    row = setup.host.store.get(answer['reference'], next(iter(setup.host.store.snapshot().values()))['owner'])
    assert row['host']['binding']['runtime'] == setup.runtime
    assert row['host']['quiescence'] is not None
    assert len(setup.boundary.launches) == 1
    original_deadline = row['deadline_unix']
    duplicate = invoke(setup, proof)
    assert duplicate['deadline_unix'] == original_deadline
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_unadmitted_a0_is_not_redirected_to_ready_dsh(setup, tmp_path):
    setup.configure(mapped(setup, tmp_path))
    proof = await ingress(setup)
    answer = invoke(setup, proof, args={'worker': 'a0', 'brief': 'Engineering', 'goal_check': 'Observe actual result'})
    assert not answer['accepted']
    assert not setup.boundary.launches
    assert setup.host.store.snapshot() == {}


@pytest.mark.parametrize('web_profile', ['exa-paid', 'exa-keyless'])
def test_normal_profile_preserves_both_worker_configs_and_credential_domains(setup, tmp_path, web_profile):
    from test_product_profile import inputs
    from tools.configure_product import compose_product
    value = mapped(setup, tmp_path)
    d = copy.deepcopy(value['workers']['dsh'])
    value['workers']['dsh'] = d
    p = {'path': str(tmp_path / 'unused-web-source'), 'sha256': 'a' * 64}
    d['dsh']['web'] = dict(profile=web_profile, **{k: copy.deepcopy(p) for k in
        ('resolver', 'trust_bundle', 'egress_evidence', 'research_policy')})
    value['workers']['a0']['a0']['web'] = {
        'profile': 'searxng-google', 'timeout_seconds': 10, 'dns': ['1.1.1.1'],
        'version': 'fixture', 'image': 'sha256:' + 'a' * 64,
        'source_pins': {
            '/exe/run_searxng.sh': 'a' * 64,
            '/usr/local/searxng/searxng-src/searx/webapp.py': 'a' * 64,
            '/usr/local/searxng/searxng-src/searx/settings_loader.py': 'a' * 64,
            '/a0/helpers/searxng.py': '4020eca255497dbf95076166ebefaff14a095abafaff69cb6176a8ae31c2fcc2',
            '/a0/tools/search_engine.py': 'c13c14560d0ac1947b63ed1ad795bd2fad5e026673d2cc615f34ef6da57a9efb'}}
    spec = inputs(); spec['runtime'] = value; spec['web']['profile'] = web_profile
    spec['inference']['key_env'] = 'FRIDAY_LLM_API_KEY'
    bundle = compose_product(spec)
    assert bundle['config']['plugins']['entries']['friday_rework']['settings']['runtime'] == value
    assert {'FRIDAY_LLM_API_KEY', 'FRIDAY_EMBEDDINGS_API_KEY', 'SEARXNG_SECRET'} <= set(
        bundle['contract']['required_scoped_names']['inference_web'])
    assert ('EXA_API_KEY' in bundle['contract']['required_scoped_names']['inference_web']) == (web_profile == 'exa-paid')
    assert bundle['contract']['ready'] is False
    value['workers']['a0']['runtime_profile'] = 'foreign'
    with pytest.raises(ValueError): compose_product(spec)


def test_administration_observes_each_worker_without_granting_a0(setup, tmp_path, monkeypatch):
    import importlib
    from contextlib import contextmanager
    module = importlib.import_module(setup.module.__package__ + '.startup_health')
    admin = importlib.import_module(setup.module.__package__ + '.admin')
    class Scope:
        def profiles(self): return ['default']
        @contextmanager
        def scope(self, profile):
            assert profile == 'default'
            yield setup.home
    setup.configure(mapped(setup, tmp_path)); (setup.home / 'config.yaml').chmod(0o600)
    monkeypatch.setattr(admin, 'Administration', Scope)
    report = module.worker_health()
    assert {r['worker'] for r in report['workers']} == {'dsh', 'a0'}
    assert all(r['profile'] == 'default' for r in report['workers'])
    assert report['runtime_ready'] is False
    assert next(r for r in report['workers'] if r['worker'] == 'a0')['deployment_verified'] is False
    assert not setup.boundary.launches
