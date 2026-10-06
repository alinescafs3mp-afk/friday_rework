"""Slow healthy native work and subsequent genuine metadata contention."""
import json
import threading
import time

import pytest
from test_host_native import isolated, setup, native, offline_boundary, ingress
from test_host_bounded_controls import pending, start, running, proof_for
from hermes_cli import plugins_state
from hermes_cli.plugin_command_context import _command_context


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['reconcile', 'status', 'stop'])
async def test_slow_native_then_real_contention_still_emergency_stops(setup, monkeypatch, entry):
    import fcntl
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    original = setup.module.NativeSupervisor.observe
    held = []
    def slow_then_contend(self, association):
        value = original(self, association)
        if not held:
            threading.Event().wait(.35)
            fd = setup.ctx.state.path.with_name('.state.json.lock').open('a+b')
            fcntl.flock(fd, fcntl.LOCK_EX)
            held.append(fd)
        return value
    monkeypatch.setattr(setup.module.NativeSupervisor, 'observe', slow_then_contend)
    try:
        if entry == 'reconcile':
            with pytest.raises(TimeoutError):
                setup.host._reconcile(row)
        else:
            command = 'friday-' + entry
            with _command_context(setup.ctx, proof_for(proof, command)):
                result = json.loads(setup.host.control(command, row['existing_task_id']))
            assert not result['accepted']
        assert setup.boundary.stops and not running(setup)
    finally:
        for fd in held:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        monkeypatch.setattr(setup.module.NativeSupervisor, 'observe', original)
    retained = setup.host.store.snapshot()[row['existing_task_id']]
    assert retained['deadline_unix'] == row['deadline_unix']
    assert retained['budget_seconds'] == row['budget_seconds']
    assert retained['host']['quiescence'] is None
    setup.host._stop(row, 'cancel')


@pytest.mark.asyncio
async def test_real_outer_wait_then_slow_native_preserves_remaining_native_flock_budget(setup, monkeypatch):
    import fcntl
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    store = setup.host.store
    actual_lock = store._thread_lock
    held, release = threading.Event(), threading.Event()
    def holder():
        with actual_lock:
            held.set()
            assert release.wait(3)
    holding = threading.Thread(target=holder)
    holding.start()
    assert held.wait(3)
    timer = threading.Timer(.12, release.set)
    class OuterLock:
        def acquire(self, *, timeout):
            if timer.ident is None:
                timer.start()
            return actual_lock.acquire(timeout=timeout)
        def release(self):
            actual_lock.release()
    monkeypatch.setattr(store, '_thread_lock', OuterLock())
    original_observe = setup.module.NativeSupervisor.observe
    file_holders, offers = [], []
    def observe(self, association):
        value = original_observe(self, association)
        if not file_holders:
            threading.Event().wait(.35)
            fd = store.state.path.with_name('.state.json.lock').open('a+b')
            fcntl.flock(fd, fcntl.LOCK_EX)
            file_holders.append(fd)
        return value
    original_acquire = plugins_state._acquire_state_file
    def acquire(handle, deadline):
        if file_holders:
            offers.append(deadline - time.monotonic())
        return original_acquire(handle, deadline)
    monkeypatch.setattr(setup.module.NativeSupervisor, 'observe', observe)
    monkeypatch.setattr(plugins_state, '_acquire_state_file', acquire)
    try:
        with pytest.raises(TimeoutError):
            setup.host._reconcile(row)
        assert offers and all(0 < value < .15 for value in offers)
        assert not running(setup) and setup.boundary.stops
    finally:
        release.set()
        holding.join(3)
        if timer.ident is not None:
            timer.join(3)
        for fd in file_holders:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        monkeypatch.setattr(setup.module.NativeSupervisor, 'observe', original_observe)
        monkeypatch.setattr(store, '_thread_lock', actual_lock)
        assert not holding.is_alive()
    retained = store.get(row['existing_task_id'], row['owner'])
    assert retained['deadline_unix'] == row['deadline_unix']
    assert retained['host']['quiescence'] is None
    setup.host._stop(row, 'cancel')


@pytest.mark.asyncio
@pytest.mark.parametrize('lease', ['expired', 'revoked'])
async def test_slow_control_resolution_does_not_restore_lease(setup, monkeypatch, lease):
    proof = await ingress(setup)
    row = start(setup, pending(setup, proof))
    store = setup.host.store
    original = store.get_for_control
    valid = [True]
    context = _command_context(setup.ctx, proof_for(proof), valid=lambda: valid[0])
    context.__enter__()
    active = [True]
    def slow_resolution(*args):
        threading.Event().wait(.35)
        value = original(*args)
        if lease == 'expired':
            valid[0] = False
        else:
            context.__exit__(None, None, None)
            active[0] = False
        return value
    monkeypatch.setattr(store, 'get_for_control', slow_resolution)
    try:
        result = json.loads(setup.host.control('friday-stop', row['existing_task_id']))
        assert not result['accepted'] and running(setup) and not setup.boundary.stops
    finally:
        if active[0]:
            context.__exit__(None, None, None)
        monkeypatch.setattr(store, 'get_for_control', original)
        setup.host._stop(row, 'cancel')
