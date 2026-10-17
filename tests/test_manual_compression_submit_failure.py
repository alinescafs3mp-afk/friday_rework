"""Offline submit/registration failure controls on the actual native executor.

Run through run_manual_ordinary_compress.py. Agents, compression and persistence
are synthetic; admission, owner tasks, raw executor futures and release are native.
Each thread has a bounded wait and is joined even when an assertion fails.
"""
import asyncio
import sys
import threading
from types import ModuleType, SimpleNamespace as NS

import pytest

from test_ordinary_first_contact_copy import source
from test_ordinary_tool_metadata_progress_privacy import scoped
from manual_owned_fixture import own_runner
from gateway import slash_commands_session as session
from gateway.turn_executor import _UnboundedThreadExecutor
from agent.conversation_compression_manual import CompressRequest, CompressResult


def _runner(source, monkeypatch, build, clean, persist):
    native = ModuleType('gateway.run')
    native._platform_config_key = lambda platform: platform.value
    native._AGENT_PENDING_SENTINEL = object()
    monkeypatch.setitem(sys.modules, 'gateway.run', native)
    runner = own_runner(NS(
        _session_key_for_source=lambda value: 'key',
        _resolve_session_agent_runtime=lambda **kw: ('fixture-model', {'api_key': 'fixture-only'}),
        _resolve_session_reasoning_config=lambda **kw: {},
        _build_manual_compression_agent=build,
        _persist_manual_compression=persist,
        _cleanup_agent_resources_off_loop=clean,
    ), source)
    runner.evicted = []
    runner.released = []
    runner._evict_cached_agent = runner.evicted.append
    native_release = runner._release_running_agent_state

    def release(key, **kw):
        runner.released.append((key, kw['run_generation'], runner._state.turn.agent))
        return native_release(key, **kw)

    runner._release_running_agent_state = release
    return runner


def _agent():
    stopped = threading.Event()
    return NS(session_id='parent', context_compressor=NS(_last_compress_aborted=False),
              _hard_interrupt_requested=stopped,
              hard_interrupt=lambda *a, **kw: stopped.set())


def _start(runner, source):
    return session.GatewaySessionCommandsMixin._run_manual_compression(
        runner, source, NS(session_id='parent'),
        [{'role': 'user', 'content': 'synthetic original'}] * 4, CompressRequest())


@pytest.mark.parametrize('failure', ['get_executor', 'thread_start'])
@pytest.mark.parametrize('successor', [False, True])
def test_native_acquisition_and_submit_failure_cleanup_and_next_admission(
        scoped, source, monkeypatch, failure, successor):
    import agent.conversation_compression_manual as core

    async def go():
        agents = []
        cleaned = []
        compressed = []
        leases_released = []
        failed_starts = []
        pool = _UnboundedThreadExecutor('manual-submit-fixture')
        replacement = object()
        replacement_lease = NS(release=lambda: leases_released.append('successor'))
        replacement_event = object()

        async def build(*args):
            value = _agent()
            agents.append(value)
            return value

        async def clean(agent, **kw):
            if agent is agents[0]:
                assert not pool._threads, 'no-worker failure must not leave an executor thread'
            cleaned.append(agent)

        async def persist(*args):
            raise AssertionError('submit failure and nothing_to_do must never publish')

        def compress(agent, messages, request, **kw):
            compressed.append(agent)
            return CompressResult('nothing_to_do', messages, messages, 10, 10, request)

        monkeypatch.setattr(core, 'compress_now', compress)
        runner = _runner(source, monkeypatch, build, clean, persist)
        runner._claim_active_session_slot = lambda *a: (
            NS(release=lambda: leases_released.append('owner')), None)

        def inject_failure():
            if successor:
                runner._begin_session_run_generation('key')
                runner._state.turn.agent = replacement
                runner._state.turn.lease = replacement_lease
                runner._state.turn.event = replacement_event
            raise RuntimeError("can't start new thread" if failure == 'thread_start'
                               else 'fixture executor acquisition refused')

        def get_executor():
            if failure == 'get_executor':
                inject_failure()
            return pool

        runner._get_executor = get_executor
        expected = "can't start new thread" if failure == 'thread_start' else 'fixture executor acquisition refused'
        try:
            # Patch the actual native Thread.start seam, not run_in_executor or submit.
            with monkeypatch.context() as patch:
                if failure == 'thread_start':
                    def fail_start(thread):
                        failed_starts.append(thread)
                        assert thread.name.startswith('manual-submit-fixture_')
                        inject_failure()
                    patch.setattr(threading.Thread, 'start', fail_start)
                with pytest.raises(RuntimeError, match=expected):
                    await _start(runner, source)
            assert not compressed
            assert cleaned == [agents[0]], 'temporary agent must be cleaned exactly once'
            assert getattr(agents[0], '_gateway_manual_compression_task', None) is None
            assert not pool._threads
            if failure == 'thread_start':
                assert len(failed_starts) == 1 and failed_starts[0].ident is None
            if successor:
                assert runner._state.turn.agent is replacement
                assert runner._state.turn.lease is replacement_lease
                assert runner._state.turn.event is replacement_event
                assert not runner.released and not runner.evicted and not leases_released
                assert 'Дождитесь' in await _start(runner, source)
                assert len(agents) == 1
            else:
                assert runner._state.turn.agent is None
                assert runner.evicted == ['key']
                assert runner.released == [('key', 1, agents[0])]
                assert leases_released == ['owner']
                # A real subsequent executor submission proves admission recovered.
                runner._get_executor = lambda: pool
                assert 'нечего сжимать' in await _start(runner, source)
                assert len(agents) == 2 and compressed == [agents[1]]
                assert cleaned == agents
                assert getattr(agents[1], '_gateway_manual_compression_task', None) is None
                assert runner._state.turn.agent is None
                assert runner.evicted == ['key', 'key']
                assert runner.released == [('key', 1, agents[0]), ('key', 2, agents[1])]
                assert leases_released == ['owner', 'owner']
        finally:
            pool.shutdown(wait=True)
        assert not pool._threads

    asyncio.run(go())


@pytest.mark.parametrize('registered_before_error', [False, True])
@pytest.mark.parametrize('unwind', ['plain', 'repeat_cancel', 'successor_repeat_cancel'])
def test_registration_failure_retains_raw_worker_until_terminal_and_cleans_once(
        scoped, source, monkeypatch, registered_before_error, unwind):
    import agent.conversation_compression_manual as core

    class RegistrationFailure(RuntimeError):
        pass

    async def go():
        raw_started = threading.Event()
        release_worker = threading.Event()
        raw_finished = threading.Event()
        tracker_failed = asyncio.Event()
        worker_futures = []
        cleaned = []
        published = []
        pool = _UnboundedThreadExecutor('manual-registration-fixture')
        agent = _agent()
        replacement = object()
        replacement_lease = object()
        replacement_event = object()

        def compress(value, messages, request, **kw):
            assert value is agent
            raw_started.set()
            try:
                assert release_worker.wait(3), 'bounded synthetic worker timed out'
                return CompressResult('compressed', messages, messages, 10, 10, request,
                                      summary={'noop': True})
            finally:
                raw_finished.set()

        monkeypatch.setattr(core, 'compress_now', compress)

        async def build(*args):
            return agent

        async def clean(value, **kw):
            assert raw_finished.is_set(), 'resources closed while raw worker still live'
            assert worker_futures[0].done() and not worker_futures[0].cancelled()
            cleaned.append(value)

        async def persist(*args):
            published.append(args)

        runner = _runner(source, monkeypatch, build, clean, persist)
        runner._get_executor = lambda: pool
        native_track = runner._track_deferred_agent_worker

        def track(worker, value):
            assert isinstance(worker, asyncio.Future) and not isinstance(worker, asyncio.Task)
            assert value is agent and raw_started.wait(1), 'raw worker must actually start'
            assert not raw_finished.is_set() and not worker.done()
            worker_futures.append(worker)
            if registered_before_error:
                native_track(worker, value)
            tracker_failed.set()
            raise RegistrationFailure('fixture raw-worker registration refused')

        runner._track_deferred_agent_worker = track
        invocation = asyncio.create_task(_start(runner, source))
        try:
            await asyncio.wait_for(tracker_failed.wait(), 1)
            owner = agent._gateway_manual_compression_task
            raw = worker_futures[0]
            assert not owner.done(), 'registration failure lost custody of a live raw worker'
            assert not invocation.done() and not raw.done() and not raw.cancelled()
            assert not cleaned and not published and not runner.evicted and not runner.released
            assert runner._state.turn.agent is agent
            if registered_before_error:
                assert runner._deferred_agent_workers == {raw: agent}
            assert 'Дождитесь' in await _start(runner, source)
            if unwind == 'successor_repeat_cancel':
                runner._begin_session_run_generation('key')
                runner._state.turn.agent = replacement
                runner._state.turn.lease = replacement_lease
                runner._state.turn.event = replacement_event
            if unwind != 'plain':
                for _ in range(3):
                    owner.cancel()
                    await asyncio.sleep(0)
                    assert not owner.done() and not raw.done() and not raw.cancelled()
                    assert not cleaned and not published and not runner.evicted and not runner.released
            release_worker.set()
            with pytest.raises(RegistrationFailure, match='fixture raw-worker registration refused'):
                await asyncio.wait_for(asyncio.shield(invocation), 2)
            assert raw_finished.is_set() and raw.done() and not raw.cancelled()
            assert cleaned == [agent] and not published
            assert agent._gateway_manual_compression_task is None
            if unwind == 'successor_repeat_cancel':
                assert runner._state.turn.agent is replacement
                assert runner._state.turn.lease is replacement_lease
                assert runner._state.turn.event is replacement_event
                assert not runner.evicted and not runner.released
            else:
                assert runner._state.turn.agent is None
                assert runner.evicted == ['key']
                assert runner.released == [('key', 1, agent)]
            await asyncio.sleep(0)
            assert not getattr(runner, '_deferred_agent_workers', {})
        finally:
            release_worker.set()
            await asyncio.gather(invocation, return_exceptions=True)
            pool.shutdown(wait=True)
        assert not pool._threads

    asyncio.run(go())
