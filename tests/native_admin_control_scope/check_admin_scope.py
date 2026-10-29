"""Real native auth/state/store/host/controller; only worker boundary is inert.

Every file effect belongs to a fresh temporary directory.
No gateway, network, model, service or subprocess-worker operation is possible.
"""
import copy
from contextvars import copy_context
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-root', type=Path, required=True)
parser.add_argument('--plugin-root', type=Path,
    default=Path(__file__).resolve().parents[2] / 'plugins/friday_rework')
parser.add_argument('--host-overlay', type=Path)
args = parser.parse_args()
NATIVE = args.native_root.resolve(strict=True)
PLUGIN = args.plugin_root.resolve(strict=True)
sys.argv = [sys.argv[0]]
TMP = tempfile.TemporaryDirectory(prefix='friday-admin-source-test-')
os.chmod(TMP.name, 0o700)
os.environ['HERMES_HOME'] = str(Path(TMP.name) / 'launch')
Path(os.environ['HERMES_HOME']).mkdir(mode=0o700)
sys.path.insert(0, str(NATIVE))
import hermes_cli
import hermes_constants
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli import friday_user_scope as users
from hermes_cli import friday_cli_work as cli_work
from hermes_cli.plugins_state import PluginState
from hermes_cli.dashboard_auth.registry import register_provider

pkg = ModuleType('admin_scope_fixture')
pkg.__path__ = ([str(args.host_overlay.resolve(strict=True))] if args.host_overlay else []) + [str(PLUGIN)]
sys.modules[pkg.__name__] = pkg
from admin_scope_fixture.associations import Associations
from admin_scope_fixture.host import WorkerHost
from admin_scope_fixture.host_record import association_address, owner_from_ingress, validate_host_record, digest
from admin_scope_fixture.boundary import WorkBrief
from admin_scope_fixture.controller import Controller, WorkerBinding
from admin_scope_fixture.adapters.contract import NativeObservation, PreparedNative
from admin_scope_fixture.supervision import UnitObservation
from admin_scope_fixture.admin_controls import host_command, prove_operator
import admin_scope_fixture.host as host_module

# Baseline instrumentation can write outside HERMES_HOME. Its one call is an
# observation-only boundary and is deliberately unavailable to this source test.
baseline = ModuleType('agent.friday_baseline_bridge')
baseline.observe_worker = lambda row: None
sys.modules[baseline.__name__] = baseline

spec = importlib.util.spec_from_file_location('fixture_basic', NATIVE / 'plugins/dashboard_auth/basic/__init__.py')
basic_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = basic_module
spec.loader.exec_module(basic_module)
provider = basic_module.BasicAuthProvider(username='owner', password_hash='fixture-unused',
    secret=b'source-test-signing-secret-not-real-0000')
register_provider(provider, scope=os.environ['HERMES_HOME'])
session = provider._mint_session('owner')


def save_config(home, *, profiles=None, enabled=True, consent=True):
    config = {'plugins': {'entries': {'friday_rework': {
        'allow_gateway_control': consent,
        'settings': {'admin': {'enabled': enabled,
            'operators': [{'provider': 'basic', 'user_id': 'owner', 'org_id': ''}],
            'profiles': profiles or ['default']}}}}}}
    path = home / 'config.yaml'
    path.write_text(json.dumps(config))
    path.chmod(0o600)


class Boundary:
    """No actual worker exists; these are explicit observation/stop fixtures."""
    def __init__(self):
        self.events = []
        self.running = True
    def prepare(self, row, brief, inputs):
        self.events.append('fixture_prepare')
        return PreparedNative('fixture-prepared', 'fixture-preparation-receipt')
    def submit(self, *args):
        raise AssertionError('worker submission forbidden')
    def observe(self, row, prepared):
        self.events.append('fixture_observe')
        return NativeObservation('a' * 32, 'fixture-native', 'fixture-observation', 2, 'running')
    def stop(self, row, prepared, intent):
        assert intent == 'cancel' and row['stop_intent'] == 'cancel'
        self.events.append('fixture_stop')
        self.running = False
        return NativeObservation('a' * 32, 'fixture-native', 'fixture-stop', 3, 'stopped')
    def unit(self, row):
        return UnitObservation(row['supervisor']['unit'], 'a' * 32,
            'active' if self.running else 'inactive', 'running' if self.running else 'dead',
            'success', 1 if self.running else 0, '/fixture' if self.running else '', self.running, False)


class Case:
    def __init__(self, *, submitted=True):
        # Each case has a fresh real state document but one native launch auth.
        self.home = Path(tempfile.mkdtemp(dir=TMP.name, prefix='profile-'))
        self.home.chmod(0o700)
        self.token = set_hermes_home_override(str(self.home))
        save_config(Path(os.environ['HERMES_HOME']))
        save_config(self.home)
        users._ENGAGED = False  # Test process only: construct before first admission.
        self.state = PluginState('friday_rework')
        self.store = Associations(self.state, clock=lambda: 1000)
        self.boundary = Boundary()
        self.controller = Controller(self.store, {'dsh': WorkerBinding(self.boundary, self.boundary.unit)})
        pin = lambda name: {'path': str(self.home / name), 'sha256': 'b' * 64}
        runtime = dict(enabled=True, runtime_profile='default', runtime_home=str(self.home),
            workspace_root=str(self.home / 'jobs'), staging_root=str(self.home / 'staging'),
            cache_roots=[str(self.home / 'cache')], budget_seconds=60,
            max_file_bytes=1024, max_total_bytes=4096,
            dsh=dict(payload_root=str(self.home / 'payload'), toolchain_root=str(self.home / 'tools'),
                node=pin('node'), cli=pin('cli'), patch=pin('patch'), native_files=[pin('native')],
                key_name='FIXTURE_KEY', profile='headless', memory_bytes=1024**3,
                cpu_percent=100, tasks=64, shutdown_seconds=2, tmp_bytes=1024**2),
            runtime_receipt=pin('receipt'))
        ingress = dict(platform='telegram', session_key='fixture-session', source_profile='default',
            transport_profile='default', runtime_profile='default', chat_type='dm',
            message=dict(bot_id='fixture-bot', user_id='fixture-user', chat_id='fixture-chat',
                thread_id='', message_id='fixture-message', platform_update_id='fixture-update',
                reply_to_message_id='', media=[]))
        call = dict(task_id='fixture-session', session_id='fixture-session', turn_id='fixture-turn',
            api_request_id='fixture-api', tool_call_id='fixture-tool')
        self.reference = association_address(call, ingress)
        self.owner = owner_from_ingress(call, ingress)
        brief = WorkBrief('dsh', 'Fixture only.', 'Read fixture observations.')
        binding = dict(correlation=call, ingress=ingress, brief=vars(brief), runtime=runtime,
            user_authority={'principal_id': users.principal_id('telegram', 'default', 'fixture-bot', 'fixture-user'),
                            'generation': 1})
        self.row, _ = self.store.claim(task_id=self.reference, admission_key=self.reference,
            owner=self.owner, brief=brief, workspace_reference=str(self.home / 'jobs' / self.reference),
            supervisor={'scope': 'user', 'unit': 'friday-rework-worker-' + self.reference[7:39] + '.service'},
            budget_seconds=60, deadline_unix=1060, host_binding=binding)
        self.store.retain_inputs(self.reference, self.owner, [])
        self.controller.prepare(self.reference, self.owner, brief, ())
        if submitted:
            self.store.begin_submission(self.reference, self.owner)
            self.store.attach_native(self.reference, self.owner,
                {'invocation_id': 'a' * 32, 'worker_reference': 'fixture-native'})
        self.row = self.store.get(self.reference, self.owner)
        validate_host_record(self.row)
        self.host = WorkerHost(SimpleNamespace(plugin_id='friday_rework'), SimpleNamespace(associations=self.store))
        self.host._controller = lambda row: self.controller
        self.host._failure_diagnostic = lambda *args: None
        self.host._owned[self.reference] = copy.deepcopy(self.row)
        boundary = self.boundary
        class Supervisor:
            def observe(self, row): return boundary.unit(row)
            def stop(self, row):
                boundary.running = False
                boundary.events.append('fixture_emergency_stop')
                return boundary.unit(row)
        host_module.NativeSupervisor = Supervisor
        self.command = host_command(self.host)  # Captured before global engagement.
        self.context = copy_context()
        users._ENGAGED = True
    def close(self):
        reset_hermes_home_override(self.token)
    def request(self, action='status', **changes):
        value = dict(profile='default', provider='basic', access_token=session.access_token,
                     task_id=self.reference, action=action)
        value.update(changes)
        return self.command(json.dumps(value))
    def verify(self):
        return prove_operator('basic', session.access_token, Path(os.environ['HERMES_HOME']), 'default')
    def scope(self, **changes):
        from hermes_cli.friday_admin_control import verified_store
        value = dict(state=self.state, directory=self.host._state_directory, profile='default',
                     reference=self.reference, action='status', verify=self.verify)
        value.update(changes)
        return verified_store(**value)


class AdminScopeTests(unittest.TestCase):
    def setUp(self): self.case = Case()
    def tearDown(self): self.case.close()

    def test_actual_status_cancel_and_settlement_chain(self):
        c = self.case
        before = copy.deepcopy(c.row)
        with self.assertRaises(users.ScopeDenied): c.store.snapshot()
        with self.assertRaises(users.ScopeDenied): users.current()
        status = c.request()
        self.assertTrue(status['accepted'], status)
        self.assertEqual(status['execution'], 'running')
        self.assertIn('fixture_observe', c.boundary.events)
        result = c.request('cancel')
        self.assertTrue(result['accepted'], result)
        self.assertEqual((result['execution'], result['stop_intent'], result['quiescent']), ('stopped', 'cancel', True))
        self.assertIn('fixture_stop', c.boundary.events)
        self.assertNotIn('fixture_emergency_stop', c.boundary.events)
        with c.scope():
            row = c.store.get(c.reference, c.owner)
        validate_host_record(row)
        for key in ('owner', 'admission_hash', 'deadline_unix', 'budget_seconds', 'created_at_unix'):
            self.assertEqual(before[key], row[key])
        self.assertEqual(row['host']['binding'], before['host']['binding'])
        self.assertEqual(row['goal_verification'], 'NOT_RUN')
        self.assertEqual(row['delivery'], 'NOT_RUN')
        with self.assertRaises(users.ScopeDenied): c.store.snapshot()
        with self.assertRaises(users.ScopeDenied): users.current()

    def test_unsubmitted_cancel_uses_original_never_submitted_settlement(self):
        self.case.close()
        self.case = Case(submitted=False)
        c = self.case
        result = c.request('cancel')
        self.assertTrue(result['accepted'], result)
        self.assertTrue(result['quiescent'])
        self.assertNotIn('fixture_stop', c.boundary.events)
        with c.scope(): row = c.store.get(c.reference, c.owner)
        self.assertEqual(row['host']['quiescence']['kind'], 'never_submitted')

    def test_wrong_profile_token_consent_and_revoked_operator_denied(self):
        c = self.case
        for changes in ({'profile': 'foreign'}, {'access_token': 'fabricated'},
                        {'access_token': provider._mint_session('ordinary').access_token},
                        {'access_token': basic_module._sign({'sub': 'owner', 'kind': 'access', 'exp': 1},
                            b'source-test-signing-secret-not-real-0000')}):
            self.assertFalse(c.request('cancel', **changes)['accepted'])
        save_config(c.home, consent=False)
        self.assertFalse(c.request('cancel')['accepted'])
        save_config(c.home)
        save_config(Path(os.environ['HERMES_HOME']), profiles=['foreign'])
        self.assertFalse(c.request('cancel')['accepted'])
        self.assertNotIn('fixture_stop', c.boundary.events)

    def test_noop_or_fabricated_verifier_cannot_create_authority(self):
        c = self.case
        for verify in (lambda: None, lambda: SimpleNamespace(provider='basic', access_token=session.access_token)):
            with self.assertRaises(users.ScopeDenied):
                with c.scope(verify=verify): pass

    def test_exact_state_home_namespace_context_and_lifetime(self):
        c = self.case
        from hermes_cli.friday_admin_control import bind_job, check_job
        with c.scope():
            cli_work.check_store(None, c.state)
            with self.assertRaises(users.ScopeDenied): cli_work.check_store(None, PluginState('friday_rework'))
            with self.assertRaises(users.ScopeDenied): check_job(c.state, c.row)
            bind_job(c.state, c.row)
            self.assertTrue(check_job(c.state, c.row))
            changed = copy.deepcopy(c.row); changed['owner']['user_id'] = 'other'
            with self.assertRaises(users.ScopeDenied): check_job(c.state, changed)
            copied = copy_context()
            with self.assertRaises(users.ScopeDenied): copied.run(cli_work.check_store, None, c.state)
            with self.assertRaises(users.ScopeDenied): users.current()
            with self.assertRaises(users.ScopeDenied): c.host._start(c.row)
            token = set_hermes_home_override(str(c.home / 'foreign'))
            try:
                with self.assertRaises((users.ScopeDenied, OSError)): cli_work.check_store(None, c.state)
            finally: reset_hermes_home_override(token)
            old = c.state._data_namespace
            c.state._data_namespace = 'foreign'
            try:
                with self.assertRaises(users.ScopeDenied): cli_work.check_store(None, c.state)
            finally: c.state._data_namespace = old
        with self.assertRaises(users.ScopeDenied): copied.run(cli_work.check_store, None, c.state)
        self.assertFalse(check_job(c.state, c.row))
        self.assertNotIn('fixture_stop', c.boundary.events)

    def test_revocation_is_rechecked_inside_existing_scope(self):
        c = self.case
        with c.scope():
            cli_work.check_store(None, c.state)
            save_config(Path(os.environ['HERMES_HOME']), profiles=['foreign'])
            with self.assertRaises(PermissionError): cli_work.check_store(None, c.state)

    def test_native_session_revocation_after_entry_is_denied(self):
        c = self.case
        temporary = provider._mint_session('owner')
        def verify():
            return prove_operator('basic', temporary.access_token,
                                  Path(os.environ['HERMES_HOME']), 'default')
        with c.scope(verify=verify):
            cli_work.check_store(None, c.state)
            provider.revoke_session(refresh_token=temporary.refresh_token,
                                    access_token=temporary.access_token)
            with self.assertRaises(PermissionError): cli_work.check_store(None, c.state)

    def test_nonadmin_user_scope_keeps_native_checks(self):
        c = self.case
        class TelegramCapability:
            principal = ('telegram', 'default', 'fixture-bot', 'fixture-user')
            def check(self): return self
        token = users._CURRENT.set(TelegramCapability())
        try:
            cli_work.check_store(None, c.state)
            self.assertEqual(len(c.store.snapshot()), 1)
            with self.assertRaises(users.ScopeDenied):
                with c.scope(): pass
            with self.assertRaises(users.ScopeDenied): cli_work.check_store(object(), c.state)
        finally: users._CURRENT.reset(token)
        with self.assertRaises(users.ScopeDenied): c.store.snapshot()


if __name__ == '__main__':
    try:
        program = unittest.main(exit=False, verbosity=2)
        if not program.result.wasSuccessful(): sys.exit(1)
    finally:
        TMP.cleanup()
