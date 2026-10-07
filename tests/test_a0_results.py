"""Actual native plugin result path with explicitly offline A0/Telegram edges.

This verifies the result join, not a live A0 run, Telegram delivery or goal test.
"""
import copy
import importlib
import json
from pathlib import Path

import pytest

from test_host_native import setup, isolated, native, offline_boundary, ingress
from test_a0_host import configure_a0, launch_row, scoped_start
from test_result_tool import enable_results, invoke_result
from test_result_delivery import receipt


async def finished(setup, tmp_path, monkeypatch):
    proof = await ingress(setup)
    state = configure_a0(setup, proof, tmp_path, monkeypatch)
    row = scoped_start(setup, launch_row(setup, state, proof))
    assert row['host']['terminal']['state'] == 'completed'
    assert row['host']['quiescence']['kind'] == 'a0'
    assert state.session.key_cleanup == 'REMOVED'
    package = setup.module.__package__
    supervisor = importlib.import_module(package + '.supervision')
    monkeypatch.setattr(supervisor, 'NativeSupervisor', lambda: state.session.boundary.supervisor)
    setup.host._a0_controllers.clear()
    def refuse_runtime(*args, **kwargs):
        raise AssertionError('Result reading must never reacquire the worker runtime')
    monkeypatch.setattr(setup.host, '_controller', refuse_runtime)
    enable_results(setup)
    module = importlib.import_module(package + '.results')
    return state, row, module


@pytest.mark.asyncio
async def test_a0_same_native_result_inspection_assessment_delivery_after_restart(setup, tmp_path, monkeypatch):
    state, row, module = await finished(setup, tmp_path, monkeypatch)
    original_posts, original_calls = copy.deepcopy(state.posts), copy.deepcopy(state.calls)
    ref = {'reference': row['existing_task_id']}
    listed = invoke_result(setup, row, {**ref, 'action': 'list'})
    content = b'actual retained fixture bytes\n'
    assert listed['files'] == [{'path': name, 'bytes': len(content)} for name in ('diagnosis.txt', 'report.txt')]
    inspected = invoke_result(setup, row, {**ref, 'action': 'inspect', 'paths': ['report.txt']})
    artifact = inspected['artifacts'][0]
    assert artifact['preview'] == content.decode() and artifact['preview_complete']
    assert artifact['media_type'] == 'text/plain'
    assert inspected['goal_verification'] == 'NOT_RUN'
    assessment = invoke_result(setup, row, {**ref, 'action': 'assess', 'verdict': 'UNKNOWN',
        'rationale': 'Retained text inspected; engineering goal needs an executed check.',
        'observations': [inspected['observation_reference']]})
    assert assessment['goal_verification'] == 'UNKNOWN'
    assert assessment['assessment']['method'] == 'parent_file_review'
    current = setup.host.store.get(row['existing_task_id'], row['owner'])
    retained = current['result']['artifacts'][0]
    sent = []
    async def send(**kwargs):
        assert setup.host.store.get(row['existing_task_id'], row['owner'])['delivery'] == 'UNKNOWN'
        sent.append(kwargs)
        return receipt(module, row, retained)
    monkeypatch.setattr(setup.ctx, 'deliver_gateway_document', send)
    result_tool = importlib.import_module(setup.module.__package__ + '.result_tool').ResultTool(setup.host)
    assert await result_tool.deliver(current) == 'DELIVERED'
    assert await result_tool.deliver(current) == 'DELIVERED'
    assert len(sent) == 1
    assert sent[0]['route']['source']['message_id'] == row['owner']['message_id']
    assert module.inspect_outputs(setup.host.store.get(row['existing_task_id'], row['owner']))[0]['preview'] == content.decode()
    assert state.posts == original_posts and state.calls == original_calls
    final = setup.host.store.get(row['existing_task_id'], row['owner'])
    for key in ('native', 'owner', 'created_at_unix', 'deadline_unix', 'budget_seconds', 'elapsed_seconds', 'stop_intent'):
        assert final[key] == row[key]


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['response', 'preparation', 'artifact', 'journal', 'running', 'unknown_file', 'foreign_owner'])
async def test_a0_common_results_refuse_changed_or_foreign_evidence(setup, tmp_path, monkeypatch, mutation):
    state, row, module = await finished(setup, tmp_path, monkeypatch)
    original_posts = copy.deepcopy(state.posts)
    root = Path(row['workspace_reference'])
    fields, paths = None, ['report.txt']
    if mutation in {'response', 'preparation'}:
        path = root / ('worker-response.json' if mutation == 'response' else 'a0-prepared.json')
        value = json.loads(path.read_text())
        value['context_id'] = 'foreign-context'
        path.chmod(0o600)
        path.write_text(json.dumps(value))
    elif mutation == 'artifact':
        item = module.a0_retained_outputs(setup.host.store, row)[0]
        path = module.output_root(row).parent / 'a0-outputs' / item.reference
        path.chmod(0o600)
        path.write_bytes(b'changed bytes')
    elif mutation == 'journal':
        controller = importlib.import_module(setup.module.__package__ + '.controller')
        store = setup.host.store
        journal = store.state_get(controller.KEY, None)
        journal['jobs'][row['existing_task_id']]['prepared'] = None
        store.state_set(controller.KEY, journal)
    elif mutation == 'running':
        state.running = True
    elif mutation == 'unknown_file':
        paths = ['not-admitted.txt']
    else:
        fields = {'USER_ID': 'another-product-user'}
    response = invoke_result(setup, row, {'action': 'inspect', 'reference': row['existing_task_id'], 'paths': paths}, fields=fields)
    assert response == {'accepted': False, 'error': 'result_unavailable'}
    assert 'result' not in setup.host.store.get(row['existing_task_id'], row['owner'])
    assert state.posts == original_posts


@pytest.mark.asyncio
async def test_a0_source_change_during_copy_refuses_manifest_and_retains_orphan(setup, tmp_path, monkeypatch):
    _, row, module = await finished(setup, tmp_path, monkeypatch)
    original = module.stage_file
    def changed(**kwargs):
        path = kwargs['source_root'] / kwargs['relative_path']
        path.chmod(0o600)
        path.write_bytes(b'changed after provenance verification')
        return original(**kwargs)
    monkeypatch.setattr(module, 'stage_file', changed)
    with pytest.raises(RuntimeError, match='changed_during_copy'):
        module.collect_outputs(setup.host.store, row, ['report.txt'])
    assert 'result' not in setup.host.store.get(row['existing_task_id'], row['owner'])
    assert len(list(module.output_root(row).iterdir())) == 1
