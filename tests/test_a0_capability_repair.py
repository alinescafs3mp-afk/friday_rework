"""Changed producer paths; fake OS routes and owned real offline Git fixtures."""
import json
from pathlib import Path
import subprocess

import pytest

from test_a0_current_capability import automatic
from test_a0_host import configure_a0
from test_host_native import setup, isolated, native, offline_boundary, ingress, invoke, CALL


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['guard_removed', 'invocation', 'namespace', 'stop'])
async def test_final_inspect_drift_cannot_publish_current_capability(setup, tmp_path, monkeypatch, fault):
    proof = await ingress(setup)
    s = configure_a0(setup, proof, tmp_path, monkeypatch, native_launcher=True)
    def damage(st):
        count = 0
        def after_inspect():
            nonlocal count
            count += 1
            if count != 2:
                return
            if fault == 'guard_removed':
                st.guard.unlink()
            elif fault == 'invocation':
                st.context['invocation_id'] = 'f' * 32
            elif fault == 'namespace':
                st.drift = True
            else:
                setup.host.store.request_stop(st.row['existing_task_id'], st.row['owner'], 'cancel')
        st.after_inspect = after_inspect
    states = automatic(setup, s, monkeypatch, fault=damage)
    result = invoke(setup, proof, args=s.args)
    assert not result['accepted'] and len(states) == 1
    row = setup.host.store.get(result['reference'], setup.record.owner_from_ingress(CALL, proof))
    assert row['host']['a0']['capability'] is None and row['host']['a0']['launch'] is None
    assert not s.schedules and not s.posts and not s.calls
    assert not (Path(row['workspace_reference']) / 'a0-current-route.json').exists()
    assert row['host']['a0']['acceptance'] == states[0].row['host']['a0']['acceptance']


@pytest.mark.asyncio
async def test_constructor_metadata_receives_original_host_stop_check(setup, tmp_path, monkeypatch):
    proof = await ingress(setup)
    s = configure_a0(setup, proof, tmp_path, monkeypatch, native_launcher=True)
    states = automatic(setup, s, monkeypatch)
    calls = []
    def metadata(value, *, budget):
        row = states[0].row
        calls.append(budget())
        setup.host.store.request_stop(row['existing_task_id'], row['owner'], 'cancel')
        budget()
        pytest.fail('metadata continued after original stop')
    monkeypatch.setattr(s.module, 'check_git_metadata', metadata)
    result = invoke(setup, proof, args=s.args)
    assert not result['accepted'] and len(calls) == 1 and 0 < calls[0] < 35
    assert not s.schedules and not s.posts and not s.calls
    row = setup.host.store.get(result['reference'], setup.record.owner_from_ingress(CALL, proof))
    assert row['stop_intent'] == 'cancel' and row['host']['a0']['capability'] is None


@pytest.fixture
def actual_metadata():
    # Existing fixture creates only its own tiny local repository, without
    # donor copying, external remotes, network or product seeding/continuation.
    from test_a0_runtime import GitMetadataControls, a0
    case = GitMetadataControls()
    try:
        case.setUp()
        yield case, a0
    finally:
        case.doCleanups()


@pytest.mark.parametrize('mode', ['complete', 'expire', 'timeout'])
def test_existing_real_git_reader_uses_one_remaining_budget(actual_metadata, monkeypatch, mode):
    case, a0 = actual_metadata
    real = subprocess.run
    left = [1.9]
    calls = []
    before = {p: a0.sha(case.source / p) for p in case.snapshot['files']}
    def run(argv, **kwargs):
        assert argv[:3] == ['/usr/bin/git', '--no-optional-locks', '--git-dir=' + str(case.source)]
        calls.append(kwargs['timeout'])
        assert kwargs['timeout'] == pytest.approx(left[0])
        assert kwargs['env']['GIT_OPTIONAL_LOCKS'] == '0'
        if mode == 'timeout':
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
        value = real(argv, **kwargs)
        left[0] -= .1
        if mode == 'expire' and len(calls) == 3:
            left[0] = 0
        return value
    monkeypatch.setattr(subprocess, 'run', run)
    if mode == 'complete':
        a0.validate(case.p, budget=lambda: left[0])
        assert len(calls) == 10 and all(a > b for a, b in zip(calls, calls[1:]))
    else:
        expected = 'git_metadata_budget_exhausted' if mode == 'expire' else 'git_metadata_read_failed'
        with pytest.raises(a0.RuntimeErrorBoundary, match=expected):
            a0.validate(case.p, budget=lambda: left[0])
        assert len(calls) == (3 if mode == 'expire' else 1)
    assert {p: a0.sha(case.source / p) for p in before} == before


def test_metadata_file_read_checks_stop_between_chunks(tmp_path):
    from test_a0_runtime import a0
    p = tmp_path / 'owned-large-metadata'
    p.write_bytes(b'x' * (3 * 1024 * 1024))
    calls = []
    def budget():
        calls.append(True)
        if len(calls) == 3:
            raise RuntimeError('original_stop')
        return 1.2
    with pytest.raises(RuntimeError, match='original_stop'):
        a0.metadata_sha(p, budget)
    assert len(calls) == 3


@pytest.mark.parametrize('left', [0, -1, True, float('inf'), float('nan')])
def test_invalid_metadata_remaining_time_refused(left):
    from test_a0_runtime import a0
    with pytest.raises(a0.RuntimeErrorBoundary, match='git_metadata_budget_exhausted'):
        a0.metadata_budget(lambda: left)
