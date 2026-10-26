"""Neutral controls for the public stopped service-source transaction.

The declaration module is imported standalone. Native transaction functions
and operator methods are AST-loaded verbatim with an explicit import allowlist
of neutral fixtures. No native package, home, worker, service, network, model or
Telegram consumer is imported or exercised. These tests check extracted pure
boundaries and simulated transaction behavior; they cannot establish native
authority, installed state, service health or user acceptance.
"""
import ast
import builtins
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / 'plugins/friday_rework'
SPEC = importlib.util.spec_from_file_location('neutral_declarations',
    MODULES / 'worker_declarations.py')
declaration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(declaration)
SOURCE_NAMES = ('worker-runtime-source/plugins/friday_rework/adapters/a0_web.py',
    'worker-runtime-source/scripts/a0_runtime.py')
PROFILE = 'profiles/dest_telegram/'
CONFIG_NAMES = ('config.yaml', PROFILE + 'config.yaml',
    PROFILE + '.friday-onboarding.json', PROFILE + '.friday-user-scope.json',
    'FRIDAY-INSTALL.json')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False) + '\n').encode()


def extract(filename, names, namespace):
    """Compile selected original AST nodes without executing module imports."""
    tree = ast.parse(filename.read_bytes(), filename=str(filename))
    nodes = [node for node in tree.body if isinstance(node,
        (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError('required source boundary missing')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(filename), 'exec'),
        namespace)
    return namespace


def installed_tuple():
    return {'project_files': dict(declaration.WEB_PROBE_TARGET,
        **{'synthetic/retained.py': 'a' * 64}),
        'product': {'runtime': {'enabled': False},
            'a0_deployment': {'name': 'unchanged', 'chat': {'model': 'unchanged'}}},
        'worker_install': {'a0': {'policy': {'path': '/synthetic/policy',
            'sha256': 'b' * 64}, 'network': {'endpoints': ['http://192.0.2.1']}}},
        'budget_seconds': 1, 'consumed': True, 'credentials': {'retained': None}}


class PureInstallationControls(unittest.TestCase):
    def test_exact_installed_target_retains_complete_tuple_without_mutation(self):
        previous = installed_tuple(); current = copy.deepcopy(previous)
        plan = {'service_source_transition': declaration.WEB_PROBE_SERVICE_DISCRIMINATOR}
        snapshot = encoded([previous, current, plan])
        self.assertIsNone(declaration.service_installation_delta(previous, current, plan))
        self.assertEqual(encoded([previous, current, plan]), snapshot)

    def test_refuses_uninstalled_partial_and_foreign_source_pins(self):
        for mode in ('anchor', 'partial', 'foreign', 'missing', 'extra-service'):
            previous = installed_tuple()
            if mode == 'anchor': previous['project_files'].update(declaration.SERVICE_ANCHOR)
            elif mode == 'partial':
                previous['project_files']['scripts/a0_runtime.py'] = declaration.SERVICE_ANCHOR['scripts/a0_runtime.py']
            elif mode == 'foreign': previous['project_files']['scripts/a0_runtime.py'] = 'f' * 64
            elif mode == 'missing': previous['project_files'].pop('plugins/friday_rework/adapters/a0_web.py')
            else: previous['project_files']['scripts/rootless_docker_launch.py'] = 'e' * 64
            with self.subTest(mode=mode), self.assertRaises(declaration.DeclarationError):
                declaration.service_installation_delta(previous, copy.deepcopy(previous),
                    {'service_source_transition': declaration.WEB_PROBE_SERVICE_DISCRIMINATOR})

    def test_refuses_every_unrelated_tuple_delta_and_false_typed_values(self):
        for mode in ('budget', 'consumed', 'credential', 'deployment', 'endpoint',
                'unrelated-project', 'extra', 'runtime-enabled', 'runtime-int'):
            previous = installed_tuple(); current = copy.deepcopy(previous)
            if mode == 'budget': current['budget_seconds'] = True
            elif mode == 'consumed': current['consumed'] = 1
            elif mode == 'credential': current['credentials']['retained'] = ''
            elif mode == 'deployment': current['product']['a0_deployment']['chat']['model'] = 'foreign'
            elif mode == 'endpoint': current['worker_install']['a0']['network']['endpoints'].append('http://192.0.2.2')
            elif mode == 'unrelated-project': current['project_files']['synthetic/retained.py'] = 'f' * 64
            elif mode == 'extra': current['extra'] = None
            else:
                previous['product']['runtime']['enabled'] = current['product']['runtime']['enabled'] = (True if mode == 'runtime-enabled' else 0)
            with self.subTest(mode=mode), self.assertRaises(declaration.DeclarationError):
                declaration.service_installation_delta(previous, current,
                    {'service_source_transition': declaration.WEB_PROBE_SERVICE_DISCRIMINATOR})

    def test_refuses_wrong_plan_discriminator_and_document_types(self):
        for plan in ({}, {'service_source_transition': True},
                {'service_source_transition': None}, {'service_source_transition': 'foreign'}, False):
            with self.subTest(plan=plan), self.assertRaises(declaration.DeclarationError):
                declaration.service_installation_delta(installed_tuple(), installed_tuple(), plan)
        for value in (None, [], False):
            with self.subTest(value=value), self.assertRaises(declaration.DeclarationError):
                declaration.service_installation_delta(value, value,
                    {'service_source_transition': declaration.WEB_PROBE_SERVICE_DISCRIMINATOR})


class NeutralStopUnconfirmed(RuntimeError):
    pass


def operator_namespace():
    def refuse_import(*args, **kwargs):
        raise AssertionError('native import forbidden in operator controls')
    neutral_builtins = dict(vars(builtins)); neutral_builtins['__import__'] = refuse_import
    return extract(MODULES / 'stopped_operator.py', ('StoppedOperator',), {
        '__builtins__': neutral_builtins, 'copy': copy, 'Path': Path,
        '_encoded': encoded, '_reference': declaration._reference,
        '_require': declaration.require,
        '_sha': lambda data: hashlib.sha256(data).hexdigest(),
        'service_installation_delta': declaration.service_installation_delta,
        'service_source_transition': declaration.service_source_transition,
        'service_transition_pair': declaration.service_transition_pair,
        'service_installed_discriminator': declaration.service_installed_discriminator,
        'SERVICE_ANCHOR': declaration.SERVICE_ANCHOR,
        'WEB_PROBE_TARGET': declaration.WEB_PROBE_TARGET,
        'WEB_PROBE_SERVICE_DISCRIMINATOR': declaration.WEB_PROBE_SERVICE_DISCRIMINATOR})


class ExtractedOperatorControls(unittest.TestCase):
    def operator(self):
        operator = operator_namespace()['StoppedOperator']({}, None)
        operator.home = Path('/synthetic/home')
        operator.f = SimpleNamespace(ROOT=Path('/synthetic/canonical'))
        operator.previous = installed_tuple(); operator.current = installed_tuple()
        operator.request['before'] = {name: {'path': str(operator.home / name),
            'sha256': declaration.SERVICE_ANCHOR[name.removeprefix('worker-runtime-source/')]}
            for name in SOURCE_NAMES}
        return operator

    def test_layout_pins_all_five_canonical_targets_and_selects_only_two_mirrors(self):
        operator = self.operator(); calls = []
        def pin(reference, *, private):
            path = declaration._reference(reference)
            calls.append((copy.deepcopy(reference), private))
            operator.external[path] = {'data': b'neutral donor', 'mode': 0o644,
                'identity': ('neutral', len(calls))}
            return path
        operator._pin = pin
        operator._service_source_layout()
        self.assertEqual({reference['path']: reference['sha256'] for reference, private in calls},
            {str(operator.f.ROOT / name): digest for name, digest in declaration.WEB_PROBE_TARGET.items()})
        self.assertTrue(all(private is False for reference, private in calls))
        self.assertEqual(set(operator.service_after), set(SOURCE_NAMES))
        for name, state in operator.service_after.items():
            self.assertIs(state, operator.external[operator.f.ROOT / name.removeprefix('worker-runtime-source/')])

    def test_layout_refuses_wrong_before_path_hash_shape_and_noninstalled_target(self):
        for fault in ('path', 'hash', 'missing', 'extra-ref', 'canonical-anchor', 'typed-tuple'):
            operator = self.operator()
            operator._pin = lambda reference, private=False: operator.external.setdefault(
                Path(reference['path']), {'data': b'neutral', 'mode': 0o644}) and Path(reference['path'])
            name = SOURCE_NAMES[0]
            if fault == 'path': operator.request['before'][name]['path'] += '.foreign'
            elif fault == 'hash': operator.request['before'][name]['sha256'] = 'f' * 64
            elif fault == 'missing': operator.request['before'].pop(name)
            elif fault == 'extra-ref': operator.request['before'][name]['mode'] = 0o600
            elif fault == 'canonical-anchor':
                operator.previous['project_files'].update(declaration.SERVICE_ANCHOR)
                operator.current['project_files'].update(declaration.SERVICE_ANCHOR)
            else: operator.current['budget_seconds'] = True
            with self.subTest(fault=fault), self.assertRaises(declaration.DeclarationError):
                operator._service_source_layout()

    def test_real_pin_method_refuses_wrong_digest_identity_and_private_mode(self):
        operator = self.operator(); path = Path('/synthetic/source')
        data = b'neutral-pin'; reference = {'path': str(path),
            'sha256': hashlib.sha256(data).hexdigest()}
        states = {path: {'data': data, 'mode': 0o600, 'identity': (1, 2)}}
        operator.ordinary = SimpleNamespace(update_file_state=lambda path: states.get(path))
        self.assertEqual(operator._pin(reference), path)
        states[path] = dict(states[path], identity=(1, 3))
        with self.assertRaisesRegex(declaration.DeclarationError, 'reference_identity_changed'):
            operator._pin(reference)
        operator.external.clear(); states[path] = dict(states[path], mode=0o644)
        with self.assertRaisesRegex(declaration.DeclarationError, 'owned_reference_required'):
            operator._pin(reference)
        self.assertEqual(operator._pin(reference, private=False), path)
        bad = dict(reference, sha256='f' * 64)
        with self.assertRaisesRegex(declaration.DeclarationError, 'reference_changed'):
            operator._pin(bad, private=False)

    def test_beforeimage_cas_keeps_mode_data_and_identity_checks(self):
        for fault in ('data', 'mode', 'identity'):
            operator = self.operator(); path = operator.home / 'config.yaml'
            before = {'data': b'before', 'mode': 0o600, 'identity': (1, 2)}
            operator.before = {'config.yaml': copy.deepcopy(before)}
            operator.retained = {}; operator.external = {}; operator.consumed = False
            operator._context = lambda: None; operator._clock = lambda **kwargs: None
            current = copy.deepcopy(before)
            operator.ordinary = SimpleNamespace(same_update_file=lambda path, expected: current == expected)
            self.assertIs(operator.before_unchanged(), operator)
            current[fault] = {'data': b'foreign', 'mode': 0o400, 'identity': (1, 3)}[fault]
            with self.subTest(fault=fault), self.assertRaisesRegex(
                    declaration.DeclarationError, 'beforeimage_changed'):
                operator.before_unchanged()

    def test_exact_preflight_alias_guard_rejects_donor_destination_overlap(self):
        tree = ast.parse((MODULES / 'stopped_operator.py').read_bytes())
        guards = [node for node in ast.walk(tree) if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call) and len(node.value.args) == 2
            and isinstance(node.value.args[1], ast.Constant)
            and node.value.args[1].value == 'worker_declaration_external_target_alias_refused']
        self.assertEqual(len(guards), 1)
        namespace = {'_require': declaration.require}
        # This compiles the original complete guard statement, not a substitute
        # preflight. Native validators preceding it are explicitly untested.
        helper = ast.parse('def check(self):\n    pass\n').body[0]
        helper.body = [guards[0]]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[helper],
            type_ignores=[])), '<extracted-native-alias-guard>', 'exec'), namespace)
        operator = self.operator(); operator.before = {SOURCE_NAMES[0]: {}}
        operator.external = {operator.f.ROOT / 'scripts/a0_runtime.py': {}}
        namespace['check'](operator)
        operator.external[operator.home / SOURCE_NAMES[0]] = {}
        with self.assertRaisesRegex(declaration.DeclarationError, 'external_target_alias_refused'):
            namespace['check'](operator)


class NeutralTransaction:
    """Explicit state fixture, not an implementation of native authority."""
    def __init__(self, root, fault=None, legacy=False):
        self.root = root; self.fault = fault; self.legacy = legacy
        self.home = root / 'home'; self.home.mkdir(mode=0o700)
        self.profile_home = self.home / 'profiles/dest_telegram'
        self.tx = root / 'transaction'
        self.request_path = root / 'request.json'
        self.events = []; self.files = {}; self.counter = 0
        self.publications = []; self.restored = False; self.secondary = []
        self.names = CONFIG_NAMES if legacy else SOURCE_NAMES + CONFIG_NAMES
        self.before = {name: self.state(('before:' + name).encode(),
            0o400 if name in SOURCE_NAMES else 0o600) for name in self.names}
        for name, state in self.before.items(): self.files[self.home / name] = state
        self.request = {key: None for key in (
            'schema', 'seconds', 'home', 'profile', 'previous_input', 'current_input',
            'native_unit', 'before', 'retained', 'declaration_source', 'launcher_source',
            'clock', 'native_pm')}
        self.request.update(schema='friday.worker-declarations.apply.v1', seconds=60,
            home=str(self.home), profile='dest_telegram',
            previous_input={'path': '/synthetic/previous', 'sha256': 'a' * 64},
            current_input={'path': '/synthetic/current', 'sha256': 'a' * 64},
            clock={'path': '/synthetic/clock', 'sha256': 'b' * 64})
        self.request_state = self.state(encoded(self.request), 0o600)
        self.files[self.request_path] = self.request_state
        self.plan = {'semantic_changes': [{'document': 'root_config',
            'path': list(declaration.TEMPLATE_INPUTS)}]}
        if not legacy:
            self.plan['service_source_transition'] = declaration.WEB_PROBE_SERVICE_DISCRIMINATOR
        self.f = SimpleNamespace(MARKER=CONFIG_NAMES[-1],
            digest=lambda data: hashlib.sha256(data).hexdigest(),
            remember_secondary=lambda primary, secondary: self.secondary.append(secondary))

    def state(self, data, mode):
        self.counter += 1
        return {'data': data, 'mode': mode, 'identity': ('neutral-inode', self.counter)}

    def same(self, path, state, parent_fd=None):
        return self.files.get(Path(path)) == state

    def write(self, path, data, mode):
        self.files[Path(path)] = self.state(data, mode)

    def publish(self, path, data, mode, before, owned, name, *, parent_fd):
        declaration.require(self.same(path, before), 'neutral_publish_cas_changed')
        if self.fault == 'publication' and len(self.publications) == 1:
            raise OSError('neutral publication fault')
        self.publications.append((name, mode)); self.events.append('publish:' + name)
        owned[name] = self.state(data, mode); self.files[Path(path)] = owned[name]

    def restore(self, home, before, owned, *, directories):
        self.events.append('restore')
        if self.fault == 'rollback-failure': raise OSError('neutral rollback fault')
        for name in owned:
            declaration.require(self.same(home / name, owned[name]),
                'neutral_restore_cas_changed')
            self.files[home / name] = before[name]
        self.restored = True

    def stage(self, authority, plan, stage):
        self.events.append('stage')
        after = {name: self.state(('after:' + name).encode(), self.before[name]['mode'])
            for name in self.names}
        for name, state in after.items(): self.files[stage / name] = state
        if self.fault == 'stage-identity':
            name = self.names[0]
            self.files[stage / name] = self.state(after[name]['data'], after[name]['mode'])
        if self.fault in ('target-identity', 'target-mode', 'target-data'):
            name = self.names[0]; state = copy.deepcopy(self.before[name])
            if self.fault == 'target-identity': state['identity'] = ('foreign', 0)
            elif self.fault == 'target-mode': state['mode'] = 0o600
            else: state['data'] += b'drift'
            self.files[self.home / name] = state
        if self.fault == 'request-identity':
            self.files[self.request_path] = self.state(self.request_state['data'], 0o600)
        return after

    def journal(self, path, data):
        self.events.append('journal:' + path.name)
        path.write_bytes(data); path.chmod(0o600)
        state = self.state(data, 0o600); self.files[path] = state
        if path.name == 'committed.json':
            if self.fault == 'uncertain-commit': raise OSError('neutral fsync fault')
            if self.fault == 'commit-receipt': return None
        return state

    def final_check(self, authority):
        self.events.append('final-check')
        if self.fault in ('final-check', 'rollback-failure'): raise ValueError('neutral final check fault')

    def authority_class(self):
        harness = self
        class NeutralAuthority:
            def __init__(self, request, budget, *, request_reference):
                self.home = harness.home; self.profile_home = harness.profile_home
                self.tx = harness.tx; self.before = harness.before
                self.active = False; self.consumed = False; self.released = False
            def preflight(self): harness.events.append('preflight')
            def before_unchanged(self): harness.events.append('before-check')
            def consume(self):
                harness.events.append('consume'); self.consumed = True
                self.tx.mkdir(mode=0o700)
            def __enter__(self):
                harness.events.append('claim'); self.active = True
                declaration.require(self.consumed, 'neutral_consume_before_claim')
                return self
            def __exit__(self, kind, error, trace):
                harness.events.append('release'); self.active = False; self.released = True
                return False
            def prove(self, *, cleanup=False): harness.events.append('prove-cleanup' if cleanup else 'prove')
            def source_unchanged(self): harness.events.append('source-check')
            def prove_released(self):
                harness.events.append('released-check')
                if harness.fault == 'release-check': raise ValueError('neutral release fault')
                if harness.fault == 'released-identity':
                    name = harness.names[0]; state = harness.files[harness.home / name]
                    harness.files[harness.home / name] = harness.state(state['data'], state['mode'])
        return NeutralAuthority

    def namespace(self):
        harness = self
        class NeutralDirectories:
            def __init__(self, home, before, extra): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def prove(self): harness.events.append('directories-check')
            def parent_fd(self, key): return ('neutral-directory', key)
        class NeutralBudget:
            def __init__(self, *args, **kwargs): pass
            def check(self, **kwargs): harness.events.append('budget-check')
            def call(self, function, *args): return function(*args)
        ordinary = SimpleNamespace(api=lambda: self.f, encoded=encoded,
            same_update_file=self.same, SourceUpdateDirectories=NeutralDirectories,
            publish_update_file=self.publish, restore_update_files=self.restore,
            private_parents=lambda *args: None, write=self.write,
            sync_directory=lambda path: None)
        imports = {('scripts.install_containment', 0): SimpleNamespace(Budget=NeutralBudget),
            ('stopped_operator', 1): SimpleNamespace(StoppedOperator=self.authority_class()),
            ('scripts', 0): SimpleNamespace(friday_ordinary_install=ordinary),
            ('scripts.dsh_prepare', 0): SimpleNamespace(StopUnconfirmed=NeutralStopUnconfirmed)}
        def neutral_import(name, globals=None, locals=None, fromlist=(), level=0):
            if (name, level) not in imports:
                raise AssertionError('unexpected import in extracted transaction')
            return imports[(name, level)]
        neutral_builtins = dict(vars(builtins)); neutral_builtins['__import__'] = neutral_import
        namespace = {'__builtins__': neutral_builtins, '__name__': 'neutral_writer',
            'Path': Path, 'os': os, 'require': declaration.require,
            '_reference': declaration._reference, '_same': declaration._same,
            'APPLY_FIELDS': frozenset(self.request), 'APPLY_SCHEMA': self.request['schema'],
            'CLEANUP_RESERVE': 20,
            '_request_snapshot': lambda reference: self.request_state,
            '_read_reference': lambda reference: copy.deepcopy(self.request),
            'validated_clock': lambda *args: {'started_mono': 1, 'deadline_mono': 61},
            '_planned_delta': lambda authority: copy.deepcopy(self.plan),
            'prepare_afterimages': self.stage, '_native_final_check': self.final_check,
            '_native_rollback_check': lambda authority: self.events.append('rollback-check'),
            '_new_journal': self.journal,
            'WEB_PROBE_SERVICE_DISCRIMINATOR': declaration.WEB_PROBE_SERVICE_DISCRIMINATOR,
            'service_transition_pair': declaration.service_transition_pair}
        return extract(MODULES / 'worker_declaration_writer.py',
            ('apply_declarations', '_service_publication_names'), namespace)

    def run(self):
        return self.namespace()['apply_declarations'](copy.deepcopy(self.request),
            request_path=self.request_path, request_sha256='c' * 64)


class SimulatedTransactionControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='neutral-')
        self.root = Path(self.temporary.name); self.root.chmod(0o700)
        self.addCleanup(self.temporary.cleanup)

    def test_source_first_marker_last_seven_file_commit_with_preserved_modes(self):
        tx = NeutralTransaction(self.root); result = tx.run()
        self.assertEqual(tuple(name for name, mode in tx.publications), SOURCE_NAMES + CONFIG_NAMES)
        self.assertEqual(tuple(mode for name, mode in tx.publications), (0o400,) * 2 + (0o600,) * 5)
        self.assertLess(tx.events.index('consume'), tx.events.index('claim'))
        self.assertLess(tx.events.index('final-check'), tx.events.index('journal:committed.json'))
        self.assertLess(tx.events.index('journal:committed.json'), tx.events.index('release'))
        self.assertFalse(tx.restored)
        self.assertIs(result['ready'], False); self.assertIs(result['workers_enabled'], False)
        self.assertEqual(result['runtime_acceptance'], 'NOT_GRANTED')
        self.assertEqual(set(result['after']), set(SOURCE_NAMES + CONFIG_NAMES))

    def test_legacy_five_file_publication_order_is_retained(self):
        tx = NeutralTransaction(self.root, legacy=True); tx.run()
        self.assertEqual(tuple(name for name, mode in tx.publications), CONFIG_NAMES)

    def test_partial_publication_failure_restores_owned_files_without_retry(self):
        tx = NeutralTransaction(self.root, 'publication')
        with self.assertRaisesRegex(OSError, 'neutral publication fault'): tx.run()
        self.assertEqual(len(tx.publications), 1); self.assertTrue(tx.restored)
        self.assertEqual(tx.files[tx.home / SOURCE_NAMES[0]], tx.before[SOURCE_NAMES[0]])
        self.assertIn('journal:rolled-back.json', tx.events)
        self.assertNotIn('journal:committed.json', tx.events)
        self.assertEqual(tx.events.count('consume'), 1); self.assertEqual(tx.events.count('claim'), 1)

    def test_final_consumer_failure_rolls_back_all_seven_owned_files(self):
        tx = NeutralTransaction(self.root, 'final-check')
        with self.assertRaisesRegex(ValueError, 'neutral final check fault'): tx.run()
        self.assertTrue(tx.restored); self.assertEqual(len(tx.publications), 7)
        for name in tx.names: self.assertEqual(tx.files[tx.home / name], tx.before[name])
        self.assertIn('rollback-check', tx.events)

    def test_rollback_failure_is_uncertain_and_preserves_secondary(self):
        tx = NeutralTransaction(self.root, 'rollback-failure')
        with self.assertRaisesRegex(NeutralStopUnconfirmed, 'rollback requires reconciliation'): tx.run()
        self.assertFalse(tx.restored); self.assertEqual(len(tx.secondary), 1)
        self.assertNotIn('journal:rolled-back.json', tx.events)

    def test_uncertain_commit_never_rolls_back(self):
        tx = NeutralTransaction(self.root, 'uncertain-commit')
        with self.assertRaisesRegex(NeutralStopUnconfirmed, 'commit requires reconciliation'): tx.run()
        self.assertTrue((tx.tx / 'committed.json').exists()); self.assertFalse(tx.restored)
        self.assertNotIn('restore', tx.events); self.assertNotIn('rollback-check', tx.events)

    def test_bad_commit_receipt_never_rolls_back(self):
        tx = NeutralTransaction(self.root, 'commit-receipt')
        with self.assertRaisesRegex(NeutralStopUnconfirmed, 'commit requires reconciliation'): tx.run()
        self.assertNotIn('restore', tx.events)

    def test_stage_same_body_identity_drift_is_refused_before_publication(self):
        tx = NeutralTransaction(self.root, 'stage-identity')
        with self.assertRaisesRegex(declaration.DeclarationError, 'stage_identity_changed'): tx.run()
        self.assertFalse(tx.publications); self.assertTrue(tx.restored)

    def test_target_data_mode_and_identity_cas_drift_is_refused(self):
        for fault in ('target-data', 'target-mode', 'target-identity'):
            path = self.root / fault; path.mkdir(mode=0o700)
            tx = NeutralTransaction(path, fault)
            with self.subTest(fault=fault), self.assertRaisesRegex(
                    declaration.DeclarationError, 'publication_cas_changed'): tx.run()
            self.assertFalse(tx.publications)

    def test_same_body_request_replacement_is_uncertain_without_publication(self):
        tx = NeutralTransaction(self.root, 'request-identity')
        with self.assertRaisesRegex(declaration.DeclarationError, 'request_identity_changed'): tx.run()
        self.assertFalse(tx.publications); self.assertNotIn('journal:committed.json', tx.events)

    def test_post_release_proof_failure_never_reacquires_or_rolls_back(self):
        tx = NeutralTransaction(self.root, 'release-check')
        with self.assertRaisesRegex(NeutralStopUnconfirmed, 'committed outcome requires reconciliation'): tx.run()
        self.assertNotIn('restore', tx.events); self.assertEqual(tx.events.count('claim'), 1)

    def test_post_release_same_body_destination_replacement_is_uncertain(self):
        tx = NeutralTransaction(self.root, 'released-identity')
        with self.assertRaisesRegex(NeutralStopUnconfirmed, 'committed outcome requires reconciliation'): tx.run()
        self.assertNotIn('restore', tx.events)


if __name__ == '__main__':
    unittest.main()
