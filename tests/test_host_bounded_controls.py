"""Real host/plugin control API; systemd remains an explicit offline fixture."""
import asyncio
import copy
from contextvars import copy_context
from datetime import datetime
import fcntl
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from test_host_native import isolated, setup, native, offline_boundary, ingress, invoke
from agent.secret_scope import set_secret_scope, reset_secret_scope
from hermes_cli import plugins_state
from hermes_cli.plugin_command_context import _command_context
from gateway.config import Platform
from gateway.run import _AGENT_PENDING_SENTINEL
from gateway.session import SessionEntry


def pending(setup, proof):
    setup.native.runner._draining = True
    result = invoke(setup, proof)
    assert not result['accepted'] and result.get('reference')
    return setup.host.store.snapshot()[result['reference']]


def start(setup, row):
    setup.boundary.completed = False
    token = set_secret_scope({'OFFLINE_DSH_KEY': 'offline-profile-value'}, profile_home=str(setup.home))
    try:
        return setup.host._start(row)
    finally:
        reset_secret_scope(token)


def proof_for(proof, command='friday-stop'):
    return dict(command=command, session_key=proof['session_key'], admitted_ingress=proof,
                source=dict(platform='telegram', profile='default', user_id='111', chat_id='-100123', thread_id='17'))


def running(setup):
    return any(value['running'] for value in setup.boundary.units.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('layer', ['outer', 'guard', 'thread', 'file'])
@pytest.mark.parametrize('entry', ['stop', 'control', 'unload'])
async def test_real_contention_reaches_owned_stop_before_release(setup, layer, entry):
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    before = setup.host.store.snapshot()[row['existing_task_id']]
    path = setup.ctx.state.path.with_name('.state.json.lock')
    locks = {'outer': setup.host.store._thread_lock, 'guard': plugins_state._PLUGIN_STATE_LOCKS_GUARD,
             'thread': plugins_state._PLUGIN_STATE_LOCKS[str(path.resolve())]}
    held, release, done = threading.Event(), threading.Event(), threading.Event()
    errors, results = [], []
    def holder():
        if layer == 'file':
            with path.open('a+b') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                held.set()
                assert release.wait(5)
        else:
            with locks[layer]:
                held.set()
                assert release.wait(5)
    def stop():
        try:
            if entry == 'control':
                with _command_context(setup.ctx, proof_for(proof)):
                    results.append(json.loads(setup.host.control('friday-stop', '')))
            elif entry == 'unload':
                setup.host.close()
            else:
                setup.host._stop(row, 'cancel')
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()
    holding = threading.Thread(target=holder)
    stopping = threading.Thread(target=copy_context().run, args=(stop,))
    holding.start()
    try:
        assert await asyncio.to_thread(held.wait, 3)
        stopping.start()
        assert await asyncio.to_thread(done.wait, 3), 'stop must finish while holder remains locked'
        assert not running(setup) and setup.boundary.stops
        if entry == 'control':
            assert not results[0]['accepted']
        else:
            assert errors
    finally:
        release.set()
        await asyncio.to_thread(holding.join, 3)
        if stopping.ident is not None:
            await asyncio.to_thread(stopping.join, 3)
        assert not holding.is_alive() and not stopping.is_alive()
    assert setup.host.store.snapshot()[row['existing_task_id']] == before
    setup.host._stop(row, 'cancel')


def builtin_runner(setup):
    runner = setup.native.runner
    runner._draining = False
    _, event = setup.native.make(text='/stop')
    key = runner._session_key_for_source(event.source)
    entry = SessionEntry(session_key=key, session_id='old-session', created_at=datetime.now(),
                         updated_at=datetime.now(), platform=Platform.TELEGRAM, chat_type='group')
    fresh = SessionEntry(session_key=key, session_id='new-session', created_at=datetime.now(),
                         updated_at=datetime.now(), platform=Platform.TELEGRAM, chat_type='group')
    runner.session_store.get_or_create_session.return_value = entry
    runner.session_store.reset_session.return_value = fresh
    runner.session_store._entries = {key: entry}
    runner._session_db = None
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner._reset_notice_session_info = lambda source: ''
    runner._telegram_topic_new_header = lambda source: None
    runner._is_telegram_topic_lane = lambda source: False
    runner._is_telegram_topic_root_lobby = lambda source: False
    runner._read_user_config = lambda: {'approvals': {'destructive_slash_confirm': False}}
    return runner, key


@pytest.mark.asyncio
@pytest.mark.parametrize('command', ['stop', 'new', 'reset'])
@pytest.mark.parametrize('native_state', ['idle', 'pending', 'active'])
@pytest.mark.parametrize('worker_state', ['pending', 'active'])
async def test_builtin_native_action_cancels_real_owned_host(setup, command, native_state, worker_state):
    row = pending(setup, await ingress(setup))
    if worker_state == 'active':
        row = start(setup, row)
    runner, key = builtin_runner(setup)
    agent = MagicMock()
    if native_state != 'idle':
        runner._session_state(key).turn.agent = _AGENT_PENDING_SENTINEL if native_state == 'pending' else agent
    _, event = setup.native.make(text='/' + command, update_id=702, message_id=502)
    answer = await runner._handle_message(event)
    assert '"stop_intent": "cancel"' in answer
    assert '"quiescent": true' in answer
    assert not running(setup)
    row = setup.host.store.snapshot()[row['existing_task_id']]
    assert row['stop_intent'] == 'cancel' and row['host']['quiescence']
    assert row['goal_verification'] == row['delivery'] == 'NOT_RUN'
    if native_state == 'active':
        agent.interrupt.assert_called_once()
    if command != 'stop':
        runner.session_store.reset_session.assert_called_once_with(key)
    assert setup.ctx.get_command_context() is None


@pytest.mark.asyncio
@pytest.mark.parametrize('command', ['stop', 'new'])
async def test_builtin_without_owned_job_returns_ordinary_native_reply(setup, command):
    await ingress(setup)
    runner, _ = builtin_runner(setup)
    _, event = setup.native.make(text='/' + command, update_id=702, message_id=502)
    answer = await runner._handle_message(event)
    assert answer and 'accepted' not in answer and 'External plugin work' not in answer
    assert not setup.boundary.stops and not setup.boundary.launches


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['bot', 'user', 'chat', 'topic', 'runtime', 'transport', 'operation', 'command', 'binding', 'args', 'expired'])
async def test_builtin_host_proof_never_borrows_foreign_or_expired_authority(setup, fault):
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    receipt = proof_for(copy.deepcopy(proof), 'stop')
    receipt.update(native_operation='stop', control_command='friday-stop')
    field = {'bot': 'bot_id', 'user': 'user_id', 'chat': 'chat_id', 'topic': 'thread_id'}
    if fault in field:
        receipt['admitted_ingress']['message'][field[fault]] = 'foreign'
        if fault != 'bot':
            receipt['source'][field[fault]] = 'foreign'
    elif fault == 'runtime':
        receipt['admitted_ingress']['runtime_profile'] = receipt['source']['profile'] = 'foreign'
    elif fault == 'transport':
        receipt['admitted_ingress']['transport_profile'] = 'foreign'
    elif fault == 'operation':
        receipt['native_operation'] = 'pause'
    elif fault == 'command':
        receipt['command'] = 'new'
    elif fault == 'binding':
        receipt['control_command'] = 'other-command'
    with _command_context(setup.ctx, receipt, valid=lambda: fault != 'expired'):
        result = setup.host.control('friday-stop', 'extra' if fault == 'args' else '')
    assert result is None or not json.loads(result)['accepted']
    assert running(setup) and not setup.boundary.stops
    setup.host._stop(row, 'cancel')


@pytest.mark.asyncio
async def test_expired_control_lease_during_metadata_wait_cannot_stop(setup, monkeypatch):
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    valid = threading.Event()
    valid.set()
    actual = setup.host.store.get_for_control
    results = []
    def blocked(*args):
        entered.set()
        assert release.wait(3)
        return actual(*args)
    monkeypatch.setattr(setup.host.store, 'get_for_control', blocked)
    def control():
        try:
            with _command_context(setup.ctx, proof_for(proof), valid=valid.is_set):
                results.append(json.loads(setup.host.control('friday-stop', row['existing_task_id'])))
        finally:
            done.set()
    thread = threading.Thread(target=copy_context().run, args=(control,))
    thread.start()
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        valid.clear()
        release.set()
        assert await asyncio.to_thread(done.wait, 3)
        assert not results[0]['accepted'] and running(setup) and not setup.boundary.stops
    finally:
        release.set()
        await asyncio.to_thread(thread.join, 3)
        setup.host._stop(row, 'cancel')


@pytest.mark.asyncio
async def test_recovered_snapshot_then_metadata_failure_stops_checked_owned_row(setup, monkeypatch):
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    recovered = setup.module.WorkerHost(setup.ctx, setup.host.admission)
    error = TimeoutError('native metadata lock deadline')
    def failure(*args):
        raise error
    original = recovered.store.get_for_control
    monkeypatch.setattr(recovered.store, 'get_for_control', failure)
    with _command_context(setup.ctx, proof_for(proof)):
        result = json.loads(recovered.control('friday-stop', ''))
    assert not result['accepted'] and not running(setup)
    assert any('STOP_CONFIRMED' in note for note in error.__notes__)
    retained = recovered.store.snapshot()[row['existing_task_id']]
    assert retained['host']['quiescence'] is None and retained['deadline_unix'] == row['deadline_unix']
    monkeypatch.setattr(recovered.store, 'get_for_control', original)
    setup.host._stop(row, 'cancel')
