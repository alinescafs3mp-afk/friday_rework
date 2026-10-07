"""Real host/store recovery; native Docker/cgroup interfaces are offline fakes.

The retained live PID belongs to this test process. No signal is sent to it.
"""
import copy
import os
from pathlib import Path
import pytest
from test_a0_host import configure_a0, launch_row
from test_host_native import setup, isolated, native, offline_boundary, ingress, CALL


def current(setup, row):
    return setup.host.store.get(row['existing_task_id'], row['owner'])


def prepare(setup, s, row):
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    token = set_secret_scope({'FRIDAY_LLM_API_KEY': 'offline-one',
                             'FRIDAY_EMBEDDINGS_API_KEY': 'offline-two'},
                            profile_home=str(setup.home))
    try:
        return setup.host._controller(row).prepare(
            row['existing_task_id'], row['owner'], s.a0.parse_brief(s.args), ())
    finally:
        reset_secret_scope(token)


def second_claim(setup, s, row):
    binding = copy.deepcopy(row['host']['binding'])
    binding['correlation']['tool_call_id'] = 'recovery-second-call'
    address = setup.record.association_address(binding['correlation'], binding['ingress'])
    return setup.host.store.claim(task_id=address, admission_key=address,
        owner=setup.record.owner_from_ingress(binding['correlation'], binding['ingress']),
        brief=s.a0.parse_brief(s.args),
        workspace_reference=str(Path(s.runtime['workspace_root'])/address),
        supervisor={'scope': 'user', 'unit': 'friday-rework-worker-'+address[7:39]+'.service'},
        budget_seconds=row['budget_seconds'], deadline_unix=row['deadline_unix'],
        host_binding=binding, acceptance=row['host']['a0']['acceptance'])


def sample(alive=True):
    start = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]
    return {'group': '/user.slice/offline/docker-'+('d'*64)+'.scope',
            'populated': True,
            'processes': [{'pid': os.getpid(), 'start_ticks': start if alive else '0'}]}


def native_sample(s, monkeypatch, value):
    def capture(boundary, obj, *, caps):
        boundary.samples.append((Path('/sys/fs/cgroup')/value['group'].lstrip('/'),
                                 [(p['pid'], p['start_ticks']) for p in value['processes']]))
    monkeypatch.setattr(s.native.A0NativeBoundary, '_sample', capture)


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['initial', 'after_grant'])
@pytest.mark.parametrize('alive', [True, False])
async def test_restart_keeps_all_samples_and_real_capacity(setup, tmp_path, monkeypatch, phase, alive):
    proof = await ingress(setup)
    s = configure_a0(setup, proof, tmp_path, monkeypatch)
    row = launch_row(setup, s, proof)
    value = sample(alive)
    if phase == 'initial':
        monkeypatch.setattr(s.module.Runtime, 'snapshot_container', lambda *args: copy.deepcopy(value))
    prepare(setup, s, row)
    if phase == 'after_grant':
        native_sample(s, monkeypatch, value)
        s.session.boundary._sample(s.obj, caps=False)
    retained = current(setup, row)['host']['a0']['observations']
    assert not retained['pending'] and value in retained['samples']
    key_path = s.session.keys.path
    keys = key_path.read_bytes()
    s.running = False
    s.obj['State'].update(Running=False, Pid=0)
    setup.host._a0_controllers.clear()
    if alive:
        with pytest.raises(Exception, match='STOP_UNCONFIRMED'):
            setup.host._reconcile(current(setup, row))
        assert current(setup, row)['host']['quiescence'] is None
        with pytest.raises(Exception, match='worker_capacity_reserved'):
            second_claim(setup, s, row)
    else:
        result = setup.host._reconcile(current(setup, row))
        assert result['host']['quiescence']['kind'] == 'a0'
        assert second_claim(setup, s, row)[1]
    recovered = setup.host._controller(current(setup, row)).bindings['a0'].adapter
    assert recovered.retained_samples == retained['samples']
    assert recovered.boundary.stop_only and recovered.runtime is None and recovered.keys is None
    assert recovered.native_cessation is (not alive)
    assert len(s.posts) == 1 and sum('create' in x for x in s.calls) == 1
    assert key_path.read_bytes() == keys
    assert current(setup, row)['host']['a0']['acceptance'] == row['host']['a0']['acceptance']


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['missing', 'empty', 'pending'])
async def test_missing_or_incomplete_history_stops_but_cannot_release(setup, tmp_path, monkeypatch, case):
    proof = await ingress(setup)
    s = configure_a0(setup, proof, tmp_path, monkeypatch)
    row = launch_row(setup, s, proof)
    prepare(setup, s, row)
    with setup.host.store._locked() as data:
        a = data['jobs'][row['existing_task_id']]['host']['a0']
        if case == 'missing':
            del a['observations']
        elif case == 'empty':
            a['observations']['samples'] = []
        else:
            a['observations']['pending'] = True
        setup.host.store._save(data)
    setup.host._a0_controllers.clear()
    # Empty history must not become valid simply by taking a new stop sample.
    with pytest.raises(Exception, match='STOP_UNCONFIRMED'):
        setup.host._reconcile(current(setup, row))
    assert not s.running and current(setup, row)['host']['quiescence'] is None
    with pytest.raises(Exception, match='worker_capacity_reserved'):
        second_claim(setup, s, row)
    assert len(s.posts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['begin_before', 'begin_after', 'finish_before', 'finish_after'])
async def test_observation_write_failure_survives_restart(setup, tmp_path, monkeypatch, stage):
    proof = await ingress(setup)
    s = configure_a0(setup, proof, tmp_path, monkeypatch)
    row = launch_row(setup, s, proof)
    prepare(setup, s, row)
    value = sample()
    native_sample(s, monkeypatch, value)
    store = setup.host.store
    save = store._save
    fired = []
    def failing(data):
        obs = data['jobs'][row['existing_task_id']]['host']['a0']['observations']
        target = not fired and (obs['pending'] if stage.startswith('begin') else value in obs['samples'])
        if target:
            fired.append(True)
            if stage.endswith('before'):
                raise OSError('INJECTED_OBSERVATION_WRITE')
        result = save(data)
        if target:
            raise OSError('INJECTED_OBSERVATION_WRITE')
        return result
    monkeypatch.setattr(store, '_save', failing)
    with pytest.raises(OSError, match='INJECTED_OBSERVATION_WRITE'):
        s.session.boundary._sample(s.obj, caps=False)
    assert fired and s.session.observation_pending
    monkeypatch.setattr(store, '_save', save)
    s.running = False
    s.obj['State'].update(Running=False, Pid=0)
    setup.host._a0_controllers.clear()
    if stage == 'begin_before':
        # No read was attempted and durable state was never changed.
        assert setup.host._reconcile(current(setup, row))['host']['quiescence']['kind'] == 'a0'
    else:
        with pytest.raises(Exception, match='STOP_UNCONFIRMED'):
            setup.host._reconcile(current(setup, row))
        assert current(setup, row)['host']['quiescence'] is None
        with pytest.raises(Exception, match='worker_capacity_reserved'):
            second_claim(setup, s, row)


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['foreign_container', 'traversal', 'pid_bool', 'start_unknown'])
async def test_invalid_samples_do_not_complete_pending_observation(setup, tmp_path, monkeypatch, mutation):
    proof = await ingress(setup)
    s = configure_a0(setup, proof, tmp_path, monkeypatch)
    row = launch_row(setup, s, proof)
    prepare(setup, s, row)
    value = sample()
    if mutation == 'foreign_container': value['group'] = value['group'].replace('d'*64, 'c'*64)
    elif mutation == 'traversal': value['group'] = value['group'].replace('/offline/', '/offline/../')
    elif mutation == 'pid_bool': value['processes'][0]['pid'] = True
    else: value['processes'][0]['start_ticks'] = 'unknown'
    store = setup.host.store
    store.a0_observation(row['existing_task_id'], row['owner'])
    with pytest.raises(ValueError):
        store.a0_observation(row['existing_task_id'], row['owner'], value)
    assert current(setup, row)['host']['a0']['observations']['pending']
