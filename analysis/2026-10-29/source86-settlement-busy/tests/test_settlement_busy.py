"""Offline exact host/Associations regression; native boundary has no effects."""
import copy
import json
import threading
import time
import unittest
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from candidate import host as module
from candidate.associations import Associations, AssociationLockBusy, AssociationError
from candidate.adapters.contract import NativeObservation
from candidate.supervision import UnitObservation

REF = 'native-' + 'a' * 64
INV = 'b' * 32
SESSION = 'session-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


def row():
    return dict(existing_task_id=REF, owner={'platform': 'telegram'}, native=dict(invocation_id=INV, worker_reference=SESSION),
                worker_kind='dsh', submission_observation='OBSERVED', stop_intent=None, deadline_unix=100.,
                elapsed_seconds=10., budget_seconds=90., host={'binding': {'runtime': {'generation': 85}},
                'terminal': None, 'quiescence': None, 'observation': {'state': 'running'}})


class Store(Associations):
    """Use the real RLock admission path with local in-memory storage only."""
    def __init__(self, r):
        self.state = SimpleNamespace(data_dir='/offline/owned')
        self._thread_lock = threading.RLock()
        self._lock_allowance = ContextVar('regression_allowance', default=None)
        self._native_expected = ContextVar('regression_native', default=None)
        self._storage_readonly = False
        self._cli_authority = None
        self.now = 20.
        self.clock = lambda: self.now
        self.data = {'jobs': {REF: copy.deepcopy(r)}}
        self.gets = 0
        self.retains = 0
        self.failure = None
        self.target = None
        self.held, self.release = threading.Event(), threading.Event()
        self.thread = None
        self.held_for = 0.

    def _check_local_state(self):
        pass

    @contextmanager
    def _locked_file(self):
        yield self.data

    def _owned(self, data, reference, owner):
        r = data['jobs'][reference]
        if r['owner'] != owner:
            raise AssociationError('foreign_owner')
        return r

    @staticmethod
    def consumer_copy(value):
        return copy.deepcopy(value)

    def _save(self, data):
        pass

    def hold(self):
        def owner():
            with self._thread_lock:
                started = time.monotonic()
                self.held.set()
                if not self.release.wait(5):
                    raise AssertionError('test lock cleanup not reached')
                self.held_for = time.monotonic() - started
        self.thread = threading.Thread(target=owner)
        self.thread.start()
        if not self.held.wait(1):
            raise AssertionError('lock not acquired')

    def maybe_fail(self, point):
        if self.target == point:
            self.target = None
            if self.failure is not None:
                raise self.failure
            self.hold()

    def get(self, reference, owner):
        self.gets += 1
        self.maybe_fail(('get', self.gets))
        return super().get(reference, owner)

    def retain_outcome(self, *args, **kwargs):
        self.retains += 1
        self.maybe_fail(('retain', self.retains))
        return super().retain_outcome(*args, **kwargs)

    def unhold(self):
        self.release.set()
        if self.thread:
            self.thread.join(2)
            if self.thread.is_alive():
                raise AssertionError('test leaked holder')
            self.thread = None
        self.held.clear()
        self.release.clear()


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.r = row()
        self.store = Store(self.r)
        self.host = module.WorkerHost.__new__(module.WorkerHost)
        self.host.store = self.store
        self.host.ctx = SimpleNamespace(get_config=lambda key: {'generation': 85})
        self.host._state_directory = Path('/offline/owned')
        self.host._closed = False
        self.host._owned = {REF: copy.deepcopy(self.r)}
        self.host._pending_observations = {}
        self.stops = []
        self.checks = []
        self.host._stop_on_error = lambda r, error: self.stops.append(type(error).__name__)
        self.obs = NativeObservation(INV, SESSION, '/offline/events', 11., 'running')
        self.calls = 0
        def reconcile(reference, owner):
            self.calls += 1
            return self.obs
        self.host._controller = lambda r: SimpleNamespace(reconcile=reconcile)
        self.patches = [
            patch('agent.friday_baseline_bridge.observe_worker', lambda r: None),
            patch('hermes_cli.friday_user_scope.check_retained_job', lambda r: self.checks.append('scope')),
            patch('hermes_cli.friday_cli_work.check_local_job', lambda h, r: self.checks.append('local')),
            patch('hermes_cli.friday_cli_work.should_stop', lambda: False),
            patch.object(module, 'select_runtime', lambda config, worker: config),
            patch.object(module, 'NativeSupervisor', lambda: SimpleNamespace(observe=lambda r:
                UnitObservation('unit', INV, 'inactive', 'dead', 'success', 0, '', False))),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.addCleanup(self.store.unhold)

    def call(self, flag=True):
        return self.host._reconcile(copy.deepcopy(self.r), defer_owned_busy=flag)

    def check_deferred(self, result):
        self.assertEqual(self.stops, [])
        self.assertEqual(result['native'], self.r['native'])
        self.assertIsNone(result['host']['terminal'])
        self.assertIsNone(result['host']['quiescence'])
        self.assertEqual(result['host']['observation']['state'], 'running')
        self.assertEqual(self.host._pending_observations[REF], self.obs)
        self.assertEqual(self.host._owned[REF]['native'], self.r['native'])
        self.assertGreaterEqual(self.store.held_for or .25, .25)

    def test_existing_success(self):
        result = self.call()
        self.assertEqual(result['host']['observation']['elapsed_seconds'], 11.)
        self.assertEqual(self.stops, [])
        self.assertEqual(self.host._pending_observations, {})
        self.assertEqual(self.calls, 1)

    def test_real_post_observation_read_busy_then_fresh_settlement(self):
        self.store.target = ('get', 2)
        result = self.call()
        self.check_deferred(result)
        self.store.unhold()
        self.assertGreaterEqual(self.store.held_for, .24)
        result = self.call()
        self.assertEqual(self.calls, 2)
        self.assertEqual(result['host']['observation']['elapsed_seconds'], 11.)
        self.assertEqual(self.host._pending_observations, {})
        self.assertEqual(self.stops, [])

    def test_real_retain_busy_then_fresh_settlement(self):
        self.store.target = ('retain', 1)
        self.check_deferred(self.call())
        self.store.unhold()
        self.assertGreaterEqual(self.store.held_for, .24)
        result = self.call()
        self.assertEqual(result['host']['observation']['elapsed_seconds'], 11.)
        self.assertEqual(self.calls, 2)
        self.assertEqual(self.host._pending_observations, {})

    def test_initial_read_still_defers_without_observation(self):
        self.store.target = ('get', 1)
        result = self.call()
        self.assertEqual(result, self.r)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.host._pending_observations, {})
        self.assertEqual(self.stops, [])

    def test_terminal_pending_is_not_completion_then_fresh_settles(self):
        self.obs = NativeObservation(INV, SESSION, '/offline/events', 12., 'completed')
        self.store.target = ('retain', 1)
        self.check_deferred(self.call())
        self.store.unhold()
        with patch.object(module, 'quiescence_record', lambda unit, clock: {'proved': True}):
            result = self.call()
        self.assertEqual(result['host']['terminal']['state'], 'completed')
        self.assertEqual(result['host']['quiescence'], {'proved': True})
        self.assertEqual(self.host._pending_observations, {})
        self.assertEqual(self.calls, 2)

    def test_ordinary_call_never_defers(self):
        self.store.failure = AssociationLockBusy('same-store')
        self.store.target = ('get', 2)
        with self.assertRaises(AssociationLockBusy):
            self.call(False)
        self.assertTrue(self.stops)
        self.assertEqual(self.host._pending_observations, {})

    def test_start_default_settlement_never_defers(self):
        self.store.failure = AssociationLockBusy('same-store')
        self.store.target = ('get', 1)
        with self.assertRaises(AssociationLockBusy):
            self.host._settle(self.r, self.obs)
        self.assertEqual(self.stops, ['AssociationLockBusy'])
        self.assertEqual(self.host._pending_observations, {})

    def test_all_unsafe_states_fail_stop(self):
        variants = {
            'cancel': lambda: self.r.update(stop_intent='cancel'),
            'pause': lambda: self.r.update(stop_intent='pause'),
            'closed': lambda: setattr(self.host, '_closed', True),
            'deadline': lambda: setattr(self.store, 'now', 100.),
            'elapsed': lambda: self.r.update(elapsed_seconds=90.),
            'unknown': lambda: self.r.update(submission_observation='UNKNOWN'),
            'not_submitted': lambda: self.r.update(submission_observation='NOT_SUBMITTED'),
            'missing_native': lambda: self.r.update(native=None),
            'terminal': lambda: self.r['host'].update(terminal={'state': 'failed'}),
            'quiescent': lambda: self.r['host'].update(quiescence={'proved': True}),
            'runtime_changed': lambda: setattr(self.host.ctx, 'get_config', lambda key: {'generation': 86}),
        }
        baseline = copy.deepcopy(self.r)
        for name, mutate in variants.items():
            with self.subTest(name=name):
                self.r = copy.deepcopy(baseline)
                self.host._closed = False
                self.store.now = 20.
                self.host.ctx.get_config = lambda key: {'generation': 85}
                self.stops.clear()
                self.store.failure = AssociationLockBusy('same-store')
                self.store.target = ('get', self.store.gets + 1)
                mutate()
                # Missing native is unsafe even though the observation contains an ID:
                # it is a first-identity settlement, not an already OBSERVED live loop.
                obs = self.obs if name != 'missing_native' else NativeObservation('', '', '/offline/events', 11., 'unknown')
                with self.assertRaises(AssociationLockBusy):
                    self.host._settle(self.r, obs, defer_owned_busy=True)
                self.assertTrue(self.stops)
                self.assertEqual(self.host._pending_observations, {})

    def test_foreign_flock_and_other_errors_do_not_defer(self):
        for error in [AssociationError('admission_busy'), TimeoutError('native lock'), ValueError('bad state')]:
            with self.subTest(type=type(error).__name__):
                self.store.failure = error
                self.store.target = ('get', self.store.gets + 2)
                with self.assertRaises(type(error)):
                    self.call()
                self.assertTrue(self.stops)
                self.assertEqual(self.host._pending_observations, {})
                self.stops.clear()

    def test_authority_refusal_still_stops(self):
        self.store.failure = AssociationLockBusy('same-store')
        self.store.target = ('get', 2)
        # Initial scope succeeds; the current recheck at deferral refuses.
        with patch('hermes_cli.friday_user_scope.check_retained_job', side_effect=[None, AssociationError('scope revoked')]):
            with self.assertRaises(AssociationError):
                self.call()
        self.assertTrue(self.stops)
        self.assertEqual(self.host._pending_observations, {})

    def test_changed_home_still_stops(self):
        self.store.failure = AssociationLockBusy('same-store')
        self.store.target = ('get', 2)
        self.store.state.data_dir = '/offline/foreign'
        with self.assertRaises(module.HostUnavailable):
            self.call()
        self.assertTrue(self.stops)
        self.assertEqual(self.host._pending_observations, {})

    def test_identity_mismatch_still_stops(self):
        self.obs = NativeObservation('c' * 32, SESSION, '/offline/events', 11., 'running')
        with self.assertRaises(module.HostUnavailable):
            self.call()
        self.assertTrue(self.stops)
        self.assertEqual(self.host._pending_observations, {})

    def test_repeated_contention_cannot_renew_original_deadline(self):
        for now in [20., 50., 99.]:
            self.store.now = now
            self.store.failure = AssociationLockBusy('same-store')
            self.store.target = ('get', self.store.gets + 2)
            result = self.call()
            self.assertEqual(result['deadline_unix'], 100.)
            self.assertEqual(self.stops, [])
        self.store.now = 100.
        self.store.target = ('get', self.store.gets + 2)
        with self.assertRaises(AssociationLockBusy):
            self.call()
        self.assertTrue(self.stops)
        self.assertEqual(self.r['deadline_unix'], 100.)

    def test_cli_cancellation_recheck_still_stops(self):
        self.r['owner']['platform'] = 'cli'
        self.store.data['jobs'][REF]['owner']['platform'] = 'cli'
        self.store.failure = AssociationLockBusy('same-store')
        self.store.target = ('get', 2)
        with patch('hermes_cli.friday_cli_work.should_stop', return_value=True):
            with self.assertRaises(AssociationLockBusy):
                self.call()
        self.assertTrue(self.stops)
        self.assertEqual(self.host._pending_observations, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
