"""Native stopped root operator custody for the declaration migration writer.

This is an operator CLI transaction, never a dashboard capability.  A request
contains immutable references, not a stopped flag, session, verifier or callback.
The existing installer, PM, onboarding and native host rendezvous remain the
producers and consumers of authority.  This module does not install or start one.
"""
from __future__ import annotations

from contextlib import ExitStack
import ast
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time

from .worker_declarations import DeclarationError, _read_reference, _reference, _same

SCHEMA = 'friday.worker-declarations.apply.v1'
CLOCK_SCHEMA = 'friday.worker-declarations.clock.v1'
FIELDS = {'schema', 'seconds', 'home', 'profile', 'previous_input', 'current_input',
    'native_unit', 'before', 'retained', 'declaration_source', 'launcher_source', 'clock', 'native_pm'}
PROFILE = 'dest_telegram'
LAUNCHER = 'scripts/rootless_docker_launch.py'
RESERVE = 15
MAX_RETAINED = 4096


def _require(value, reason):
    if not value:
        raise DeclarationError(reason)


def _encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False) + '\n').encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _relative(name):
    _require(type(name) is str and name and '\x00' not in name,
        'worker_declaration_retained_name_required')
    path = Path(name)
    _require(not path.is_absolute() and '..' not in path.parts and name == str(path)
        and path != Path('.'), 'worker_declaration_retained_name_required')
    return path


def _stop(reason, primary=None, secondary=()):
    from scripts.dsh_prepare import StopUnconfirmed
    error = StopUnconfirmed(reason)
    error.friday_custody_primary = primary
    error.friday_custody_secondary = tuple(secondary)
    return error


class StoppedOperator:
    """One finite native root operator invocation and its exact deployment.

    ``preflight(); consume(); with authority: ...`` is deliberate: permanent
    consumption is durable before the first native host claim, including a
    partial/uncertain claim.  A failed request has no retry entrypoint here.
    ``prove`` checks retained custody during publication without demanding the
    old five beforeimages.  ``before_unchanged`` adds that comparison explicitly.
    The owning writer alone stages, publishes and rolls back the five targets.
    """
    def __init__(self, request, budget, *, request_reference=None):
        self.request = copy.deepcopy(request)
        self.request_reference = copy.deepcopy(request_reference)
        self.budget = budget
        self.active = False
        self.consumed = False
        self.entered = False
        self.released = False
        self._stack = None
        self._directories = []
        self._directory_edges = {}
        self._native_prove = self._build_prove = self._pm_prove = self._lock_prove = None
        self._worker_runtime_prove = None
        self.external = {}
        self._request_bytes = _encoded(self.request)

    def _clock(self, *, cleanup=False):
        from scripts.install_containment import Budget
        _require(type(self.budget) is Budget,
            'worker_declaration_native_budget_required')
        clock = _read_reference(self.request['clock'])
        _require(type(clock) is dict and set(clock) == {'schema', 'boot_id',
            'started_mono', 'deadline_mono', 'seconds'} and clock['schema'] == CLOCK_SCHEMA
            and type(clock['seconds']) is int and clock['seconds'] == self.request['seconds']
            and all(type(clock[key]) in (int, float) and math.isfinite(clock[key])
                for key in ('started_mono', 'deadline_mono'))
            and 0 <= clock['started_mono'] <= time.monotonic()
            and clock['deadline_mono'] == clock['started_mono'] + clock['seconds']
            and clock['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and self.budget.deadline == clock['deadline_mono'],
            'worker_declaration_original_clock_required')
        self.budget.check(reserve=0 if cleanup else RESERVE)
        return clock

    def _context(self):
        from hermes_cli import friday_user_scope as user
        from hermes_constants import (get_default_hermes_root, get_hermes_home,
            get_process_hermes_home, get_routing_process_hermes_home)
        from hermes_cli.profiles import get_profile_dir
        _require(user._CURRENT.get() is None and os.environ.get('HERMES_HOME') == str(self.home)
            and get_hermes_home() == self.home and get_process_hermes_home() == self.home
            and get_routing_process_hermes_home() == self.home
            and get_default_hermes_root(home=self.home) == self.home
            and get_profile_dir('default') == self.home,
            'worker_declaration_native_root_operator_context_required')
        _require(Path(sys.argv[0]).resolve() == self.f.ROOT / 'scripts/friday_ordinary_install.py',
            'worker_declaration_native_operator_cli_required')

    def _state(self, path, *, private=True):
        state = self.ordinary.update_file_state(path)
        _require(state is not None and state['mode'] in ((0o400, 0o600) if private
            else (0o400, 0o600, 0o644, 0o755)),
            'worker_declaration_owned_reference_required')
        return state

    def _pin(self, ref, *, private=True):
        path = _reference(ref)
        state = self._state(path, private=private)
        _require(_sha(state['data']) == ref['sha256'],
            'worker_declaration_reference_changed')
        prior = self.external.get(path)
        _require(prior is None or prior == state,
            'worker_declaration_reference_identity_changed')
        self.external[path] = state
        return path

    def _module(self, name, expected, expected_sha):
        module = sys.modules.get(name)
        _require(module is not None and getattr(module, '__file__', None)
            and Path(module.__file__).resolve() == expected
            and getattr(getattr(module, '__spec__', None), 'origin', None) == str(expected)
            and _sha(self.f.owned_file(expected)) == expected_sha,
            'worker_declaration_loaded_source_origin_changed')

    def _origins(self):
        project = self.previous['project_files']
        for name in ('scripts.friday_install', 'scripts.friday_ordinary_install'):
            relative = name.replace('.', '/') + '.py'
            self._module(name, self.f.ROOT / relative, project[relative])
        relative = 'plugins/friday_rework/stopped_operator.py'
        own = Path(__file__).resolve()
        _require(relative in project and own in (self.f.ROOT / relative, self.home / relative)
            and _sha(self.f.owned_file(own)) == project[relative],
            'worker_declaration_authority_source_pin_required')
        # Imported validator helpers retain the same exact project bytes as
        # their native installer consumers; installed plugins are also pinned
        # by source_identity. No arbitrary alternate module can supply proofs.
        prefix = __name__.rsplit('.', 1)[0] + '.'
        for name, module in tuple(sys.modules.items()):
            filename = getattr(module, '__file__', None)
            if name.startswith(prefix) and filename:
                path = Path(filename).resolve()
                relative = 'plugins/friday_rework/' + name[len(prefix):].replace('.', '/')
                relative += '/__init__.py' if getattr(module, '__path__', None) is not None else '.py'
                _require(relative in project and path in (self.f.ROOT / relative, self.home / relative)
                    and _sha(self.f.owned_file(path)) == project[relative],
                    'worker_declaration_project_module_origin_required')
            if name.startswith('scripts.') and filename:
                path = Path(filename).resolve()
                relative = name.replace('.', '/') + '.py'
                if relative in project:
                    self._module(name, self.f.ROOT / relative, project[relative])
        # Check every imported native source file, including top-level helpers
        # such as utils and hermes_yaml. Third-party dependency packages remain
        # the real PM environment's responsibility, not a second inventory.
        files = self.receipt['files']
        for name, module in tuple(sys.modules.items()):
            filename = getattr(module, '__file__', None)
            native_name = (name in ('hermes_constants', 'hermes_yaml', 'utils', 'hermes_cli', 'gateway', 'pm')
                or name.startswith(('hermes_cli.', 'gateway.', 'pm.')))
            if filename is None:
                _require(not native_name, 'worker_declaration_native_module_origin_required')
                continue
            path = Path(filename).resolve()
            if not path.is_relative_to(self.source):
                _require(not native_name, 'worker_declaration_native_module_origin_required')
                continue
            relative = str(path.relative_to(self.source))
            _require(relative in files
                and getattr(getattr(module, '__spec__', None), 'origin', None) == str(path)
                and _sha(self.f.owned_file(path)) == files[relative]['sha256'],
                'worker_declaration_native_module_origin_required')

    def _profile(self, *, original=False):
        from hermes_cli import friday_user_scope as user
        from hermes_cli.friday_product_access import current_access, principal_id
        from hermes_cli.plugins_state import PluginState
        from .onboarding import Onboarding
        with user.authority(self.home):
            policy = user.policy(self.home)
            bindings = [] if policy is None else [binding for binding in policy['bindings']
                if binding['runtime_profile'] == self.request['profile']]
            _require(len(bindings) == 1, 'worker_declaration_single_native_binding_required')
            binding = bindings[0]
            principal = tuple(binding[key] for key in
                ('platform', 'transport_profile', 'account_id', 'user_id'))
            row = current_access()['users'].get(principal_id(*principal))
            _require(type(row) is dict and row.get('enabled') is True and row.get('role') == 'user'
                and type(row.get('generation')) is int and row['generation'] >= 1,
                'worker_declaration_current_user_generation_required')
            if hasattr(self, 'binding'):
                _require(_same(binding, self.binding) and _same(row, self.row),
                    'worker_declaration_current_user_authority_changed')
            self._pairing_custody(binding)
            from gateway.pairing import PairingStore
            _require(PairingStore(initialize=False).is_approved(binding['platform'], binding['user_id']),
                'worker_declaration_current_native_grant_required')
            self._pairing_custody(binding)
            if original:
                home, verified_binding, verified_row, proof = Onboarding(None)._prepared(
                    self.home, PluginState('friday_rework'), *principal, row['generation'])
                _require(home == self.profile_home and _same(verified_binding, binding)
                    and _same(verified_row, row),
                    'worker_declaration_current_profile_proof_required')
                self.binding, self.row, self.proof = copy.deepcopy(binding), copy.deepcopy(row), copy.deepcopy(proof)
                info = self.profile_home.lstat()
                with user.authority(self.profile_home):
                    user.UserScope(self.home, self.profile_home, self.request['profile'], principal,
                        dict(binding), (info.st_dev, info.st_ino), row['generation']).check()

    def _pairing_custody(self, binding):
        """Retain the existing grant layout around the native non-initializing read.

        PairingStore(initialize=False) cannot mkdir or migrate even when a
        concurrent pairing CLI changes this layout. These comparisons detect
        such drift without repairing it or implementing a second grant store.
        """
        from gateway import pairing
        from .worker_archive import _Directory
        _require(binding['platform'] == 'telegram' and pairing.PAIRING_DIR is None,
            'worker_declaration_native_pairing_scope_required')
        active = pairing._default_pairing_dir()
        choices = (self.home / 'pairing', self.home / 'platforms/pairing')
        _require(active in choices and active == active.resolve(),
            'worker_declaration_native_pairing_scope_required')
        alternate = choices[1] if active == choices[0] else choices[0]
        _require(not os.path.lexists(alternate),
            'worker_declaration_native_pairing_migration_refused')
        with _Directory(active) as retained:
            names = sorted(os.listdir(retained.fd))
            _require(len(names) <= MAX_RETAINED and 'telegram-approved.json' in names,
                'worker_declaration_existing_native_pairing_required')
            inventory = {name: self._state(active / name) for name in names}
            retained.prove()
            info = os.fstat(retained.fd)
            signature = (str(active), (info.st_dev, info.st_ino, info.st_uid, info.st_mode), inventory)
        if hasattr(self, '_pairing_state'):
            _require(signature == self._pairing_state,
                'worker_declaration_native_pairing_custody_changed')
        else:
            self._pairing_state = signature
            for name, state in inventory.items():
                self.external[active / name] = state
        _require(not os.path.lexists(alternate),
            'worker_declaration_native_pairing_migration_refused')

    def _launcher_layout(self):
        """Read the pinned existing launcher's native paths without importing it."""
        raw = self.external[Path(self.request['launcher_source']['path'])]['data']
        tree = ast.parse(raw)
        wanted = {'ROOT', 'STATE', 'UID', 'INSTALLED_UNIT', 'UNIT_SHA256'}
        values = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            if name not in wanted:
                continue
            _require(name not in values, 'worker_declaration_launcher_layout_required')
            value = node.value
            if name in ('ROOT', 'STATE', 'INSTALLED_UNIT'):
                _require(isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id == 'Path' and len(value.args) == 1 and not value.keywords
                    and isinstance(value.args[0], ast.Constant) and type(value.args[0].value) is str,
                    'worker_declaration_launcher_layout_required')
                values[name] = Path(value.args[0].value)
            else:
                _require(isinstance(value, ast.Constant), 'worker_declaration_launcher_layout_required')
                values[name] = value.value
        _require(set(values) == wanted and type(values['UID']) is int and values['UID'] == os.getuid()
            and values['ROOT'] / 'launch.py' == Path(self.worker_inputs['workers']['a0']['a0']['launcher']['path'])
            and values['STATE'] == Path('/run/user') / str(os.getuid()) / 'friday-rework-docker'
            and values['INSTALLED_UNIT'].name == 'friday-rework-docker.service',
            'worker_declaration_launcher_installation_lineage_required')
        self._worker_root = values['ROOT']
        self._worker_state = values['STATE']
        self._worker_unit_name = values['INSTALLED_UNIT'].name
        self._pin({'path': str(values['INSTALLED_UNIT']), 'sha256': values['UNIT_SHA256']}, private=False)

    def _worker_runtime_layout(self):
        """Bind the existing A0 route's actual lifetime lock, not a new slot."""
        relative = 'scripts/a0_runtime.py'
        source = self._pin({'path': str(self.f.ROOT / relative),
            'sha256': self.current['project_files'][relative]}, private=False)
        tree = ast.parse(self.external[source]['data'])
        values = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            if name not in ('PROJECT', 'RUNTIME'):
                continue
            _require(name not in values, 'worker_declaration_native_runtime_layout_required')
            value = node.value
            if name == 'PROJECT':
                _require(isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id == 'Path' and len(value.args) == 1 and not value.keywords
                    and isinstance(value.args[0], ast.Constant) and type(value.args[0].value) is str,
                    'worker_declaration_native_runtime_layout_required')
                values[name] = Path(value.args[0].value)
            else:
                _require(isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div)
                    and isinstance(value.left, ast.Name) and value.left.id == 'PROJECT'
                    and isinstance(value.right, ast.Constant) and type(value.right.value) is str,
                    'worker_declaration_native_runtime_layout_required')
                values[name] = value.right.value
        _require(set(values) == {'PROJECT', 'RUNTIME'}
            and values['PROJECT'].is_absolute()
            and values['PROJECT'] == values['PROJECT'].resolve(),
            'worker_declaration_native_runtime_layout_required')
        runtime = values['PROJECT'] / values['RUNTIME']
        _require(runtime == runtime.resolve() and runtime.parent == self._worker_root.parent
            and runtime.name == 'a0-runtime-sol', 'worker_declaration_native_runtime_owner_required')
        from .worker_archive import _Directory
        with _Directory(runtime):
            pass
        self._worker_runtime_lock = runtime / 'runtime.lock'
        self._pin({'path': str(self._worker_runtime_lock), 'sha256': _sha(b'')})
        _require(self.external[self._worker_runtime_lock]['mode'] == 0o600,
            'worker_declaration_existing_native_runtime_lock_required')

    def _state_layout(self):
        # Fresh native PluginState readers may initialize/tighten their store.
        # Prove the complete already-initialized private layout first, so the
        # existing native read path has nothing to initialize or repair.
        from .worker_archive import _Directory
        for path in (self.home / 'plugin-data', self.access_path.parent):
            with _Directory(path):
                pass
        for path, data in ((self.access_path.with_name('.state.json.lock'), b''),
                (self.access_path.with_name('admission.lock'), b'v1\n')):
            state = self._state(path)
            _require(state['mode'] == 0o600 and state['data'] == data,
                'worker_declaration_existing_native_state_lock_required')
            self.external[path] = state
        state = self._state(self.access_path)
        _require(state['mode'] == 0o600, 'worker_declaration_existing_native_state_required')
        self.external[self.access_path] = state

    def preflight(self):
        """Read-only native validation, before durable single-use consumption."""
        from scripts import friday_ordinary_install as ordinary
        from hermes_cli import friday_user_scope as user
        from hermes_cli.plugins_state import _plugin_data_namespace
        self.ordinary, self.f = ordinary, ordinary.api()
        request = self.request
        _require(type(request) is dict and set(request) == FIELDS
            and request['schema'] == SCHEMA and request['profile'] == PROFILE
            and type(request['seconds']) is int and 30 <= request['seconds'] <= 180
            and type(request['before']) is dict and type(request['retained']) is dict,
            'worker_declaration_exact_native_request_required')
        _require(self.request_reference is not None,
            'worker_declaration_exact_raw_request_reference_required')
        request_path = self._pin(self.request_reference)
        _require(_same(self.f.read_json(request_path), request),
            'worker_declaration_raw_request_changed')
        self.home = self.f.directory(self.f.canonical(request['home']))
        self.source = self.f.directory(self.home / 'hermes-agent')
        self.profile_home = self.f.directory(self.home / 'profiles' / PROFILE)
        self.f.directory(self.home / 'preparation')
        self._context()
        self.access_path = self.home / 'plugin-data' / _plugin_data_namespace('friday_rework', '') / 'state.json'
        self._state_layout()
        self.clock = self._clock()
        self.previous = self.f.read_json(self._pin(request['previous_input']))
        self.current = self.f.read_json(self._pin(request['current_input']))
        _require(request['previous_input'] != request['current_input']
            and self.previous.get('home') == self.current.get('home') == str(self.home)
            and type(self.previous.get('product')) is dict and type(self.current.get('product')) is dict
            and self.previous['product'].get('runtime') == self.current['product'].get('runtime') == {'enabled': False},
            'worker_declaration_exact_input_successor_required')
        restored = copy.deepcopy(self.current)
        for components in (('product', 'a0_deployment'), ('worker_install', 'a0', 'policy'),
                ('worker_install', 'a0', 'network', 'policy'),
                ('worker_install', 'a0', 'network', 'endpoints')):
            old, new = self.previous, restored
            for key in components[:-1]:
                _require(type(old) is dict and type(new) is dict and key in old and key in new,
                    'worker_declaration_input_counterpart_required')
                old, new = old[key], new[key]
            _require(type(old) is dict and type(new) is dict and components[-1] in old and components[-1] in new,
                'worker_declaration_input_counterpart_required')
            new[components[-1]] = copy.deepcopy(old[components[-1]])
        _require(_same(restored, self.previous), 'worker_declaration_exact_input_successor_required')
        # These real validators include all project/native files and source
        # overlays, supported worker input validation, and the native marker.
        self.budget.call(self.f.inspect, self.previous, request['previous_input']['sha256'])
        self.budget.call(self.f.spec_checked, self.current, cli_only=True)
        self.marker = self.f.read_json(self.home / self.f.MARKER)
        _require(self.marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
            and self.marker.get('runtime_ready') is False
            and self.marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
            and self.f.cli_historical_scope_closed(self.marker['original_attempt'], 'friday.native-install.v1')
            and (self.marker.get('cli_segment') is None or self.f.cli_historical_scope_closed(
                self.marker['cli_segment']['clock'], 'friday.cli-segment-clock.v1')),
            'worker_declaration_closed_native_install_required')
        entry = self.marker['ordinary_gateway']['operator_entry']
        _require(type(entry) is dict and set(entry) == {'script', 'input'}
            and entry['input'] == request['previous_input']
            and entry['script'] == {'path': str(self.f.ROOT / 'scripts/friday_native.py'),
                'sha256': self.previous['project_files']['scripts/friday_native.py']},
            'worker_declaration_native_operator_entry_required')
        self._pin(entry['script'], private=False)
        self._pin(request['native_unit'], private=False)
        companion = request['declaration_source']
        _require(type(companion) is dict and set(companion) == {'bundle', 'worker_inputs', 'identity'},
            'worker_declaration_exact_source_companion_required')
        for ref in companion.values():
            self._pin(ref)
        from .worker_declarations import load_declaration_source
        self.declaration_bundle, self.worker_inputs, self.identity = load_declaration_source(companion)
        _require(type(self.identity.get('source_refs')) is dict,
            'worker_declaration_identity_source_references_required')
        _require(_reference(self.identity['source_refs']['access_state']) == self.access_path,
            'worker_declaration_exact_native_access_state_required')
        # Current target files have their own five-file publication custody.
        # Their immutable data-only capture references remain provenance: if a
        # capture is also the live destination, before_unchanged owns its CAS.
        for name, ref in self.identity['source_refs'].items():
            if name == 'stale_attachment':
                continue
            path = _reference(ref)
            mutable = {self.home / 'config.yaml', self.profile_home / 'config.yaml',
                self.profile_home / user.ONBOARDING, self.profile_home / user.MARKER}
            if path in mutable:
                relative = str(path.relative_to(self.home))
                _require(request['before'].get(relative) == ref,
                    'worker_declaration_identity_beforeimage_reference_changed')
            else:
                self._pin(ref)
        runtime_a0 = self.worker_inputs['workers']['a0']['a0']
        worker_a0 = self.current['worker_install']['a0']
        _require(_same(self.current['product']['a0_deployment'], runtime_a0['deployment'])
            and _same(worker_a0['policy'], runtime_a0['policy'])
            and _same(worker_a0['network']['policy'], self.worker_inputs['a0_network']['policy'])
            and _same(worker_a0['network']['endpoints'], self.worker_inputs['a0_network']['endpoints']),
            'worker_declaration_input_counterpart_join_required')
        launcher = runtime_a0['launcher']
        _require(launcher['sha256'] == request['launcher_source']['sha256'],
            'worker_declaration_installed_launcher_successor_required')
        self._pin(launcher, private=False)
        self._pin(request['clock'])
        _require(request['launcher_source'] == {'path': str(self.f.ROOT / LAUNCHER),
            'sha256': self.current['project_files'][LAUNCHER]},
            'worker_declaration_launcher_successor_source_required')
        self._pin(request['launcher_source'], private=False)
        self._launcher_layout()
        self._worker_runtime_layout()
        self.receipt = self.f.read_json(self.home / 'hermes-agent.source.json')
        self._origins()
        prefix = 'profiles/' + PROFILE + '/'
        before_names = {'config.yaml', self.f.MARKER, prefix + 'config.yaml',
            prefix + user.ONBOARDING, prefix + user.MARKER}
        _require(type(request['before']) is dict and set(request['before']) == before_names,
            'worker_declaration_exact_before_inventory_required')
        self.before = {}
        for name, ref in request['before'].items():
            _require(_reference(ref) == self.home / name,
                'worker_declaration_exact_before_path_required')
            state = self._state(self.home / name)
            _require(state['mode'] == 0o600 and _sha(state['data']) == ref['sha256'],
                'worker_declaration_beforeimage_changed')
            self.before[name] = state
        self.access_path = self.home / 'plugin-data' / _plugin_data_namespace('friday_rework', '') / 'state.json'
        retained = request['retained']
        required = {'hermes-agent.source.json', 'hermes-agent/install-stamp.json',
            'hermes-agent/.hermes/bin/hermes', 'hermes-agent/hermes_cli/web_dist/hermes-build.json',
            'SOUL.md', prefix + 'SOUL.md', 'FRIDAY-PROFILE.json', '.env', prefix + '.env',
            'auth.json', prefix + 'auth.json', str(self.access_path.relative_to(self.home)),
            str(self.access_path.with_name('admission.lock').relative_to(self.home)),
            str(self.access_path.with_name('.state.json.lock').relative_to(self.home)),
            *self.marker['ordinary_gateway']['history']}
        _require(type(retained) is dict and len(retained) <= MAX_RETAINED
            and required <= set(retained) and not set(retained) & before_names,
            'worker_declaration_exact_retained_inventory_required')
        self.retained = {}
        for name, ref in retained.items():
            path = self.home / _relative(name)
            if ref is None:
                _require(name in ('auth.json', prefix + 'auth.json') and not os.path.lexists(path),
                    'worker_declaration_retained_absence_changed')
                self.retained[name] = None
            else:
                _require(_reference(ref) == path, 'worker_declaration_exact_retained_path_required')
                state = self._state(path, private=name not in (
                    'hermes-agent/install-stamp.json', 'hermes-agent/.hermes/bin/hermes',
                    'hermes-agent/hermes_cli/web_dist/hermes-build.json'))
                _require(_sha(state['data']) == ref['sha256'],
                    'worker_declaration_retained_reference_changed')
                self.retained[name] = state
        _require(self.marker['source_receipt_sha256'] == retained['hermes-agent.source.json']['sha256'],
            'worker_declaration_native_source_receipt_required')
        # References may neither alias destinations nor borrow an inode from
        # retained deployment data. Hard links are already refused by readers.
        _require(not set(self.external) & {self.home / name for name in self.before},
            'worker_declaration_external_target_alias_refused')
        self._profile(original=True)
        self.tx = self.home / 'preparation' / ('ordinary-worker-declarations-' + request['previous_input']['sha256'])
        _require(not os.path.lexists(self.tx), 'worker_declaration_consumed_no_retry')
        self._pm_preflight()
        self.source_unchanged()
        return self

    def source_unchanged(self):
        """Real source/installation check at intake and final publication."""
        from hermes_cli.friday_dashboard_owner import source_identity
        self._clock()
        self._origins()
        identity = source_identity(self.home, source=self.source)
        _require(identity['receipt'] == self.marker['source_receipt_sha256'],
            'worker_declaration_native_source_changed')
        self.budget.call(self.f.spec_checked, self.current, cli_only=True)
        if hasattr(self, '_pm_state'):
            self._pm_identity(check_build=True)
        return identity

    def _pm_preflight(self):
        references = self.request['native_pm']
        _require(type(references) is dict and set(references) == {
            'runtime_facts', 'tool_facts', 'pyvenv_cfg', 'node'},
            'worker_declaration_exact_native_pm_references_required')
        for name in ('runtime_facts', 'tool_facts', 'pyvenv_cfg'):
            self._pin(references[name], private=False)
        node_path = _reference(references['node'])
        state = self._binary_state(node_path, full=True)
        _require(state['sha256'] == references['node']['sha256'],
            'worker_declaration_native_pm_node_reference_changed')
        self._pm_identity(check_build=False)

    def _pm_identity(self, *, check_build=False):
        from pm import environments, paths
        from pm.lock import Facts, Lockfile
        from pm.registry import get_package, walk
        from pm.store import Store, current_target
        from pm.package import compose_env
        _require(paths.repo_root() == self.source and paths.install_root() == self.source
            and environments.store_root(self.source) == environments.store_root(
                self.source, honor_runtime_override=False)
            and environments.install_state_dir(self.source) == self.home / 'installs' / environments.install_key(self.source),
            'worker_declaration_native_pm_owner_required')
        selected = environments.committed_venv(self.source)
        _require(selected is not None and selected == selected.resolve()
            and environments.running_from_selected_environment(self.source),
            'worker_declaration_native_pm_environment_required')
        # installed_package/env_for can call _heal_exec_bit. Use the same
        # native Facts/Lockfile/package selectors directly without that repair
        # branch; no PM mutation is allowed in this five-file transaction.
        store_root = paths.store_root()
        _require(paths.writable_store_root() == store_root,
            'worker_declaration_native_pm_fallback_refused')
        facts = Facts(paths.facts_path(), strict=True)
        # Lockfile's generic malformed-input fallback may archive .corrupt.
        # Refuse malformed source data before entering that native reader.
        lock_state = self._state(paths.lockfile_path(), private=False)
        lock_document = json.loads(lock_state['data'], object_pairs_hook=self.f.unique)
        _require(type(lock_document) is dict and lock_document.get('schema') == 1
            and type(lock_document.get('packages')) is dict,
            'worker_declaration_native_pm_lock_document_required')
        lock = Lockfile(paths.lockfile_path())
        target = current_target()
        package = get_package('node')
        _require([dependency.name for dependency in walk(['node'])] == ['node'],
            'worker_declaration_native_pm_node_closure_required')
        artifacts = lock.artifacts('node', target)
        identity = (target, tuple(row['sha256'] for row in artifacts)) if artifacts else None
        fact = facts.get('node')
        _require(type(fact) is dict and type(fact.get('entry')) is str
            and fact['entry'] not in ('', '.', '..') and not any(char in fact['entry'] for char in '/\\:')
            and identity is not None and facts.installed('node', lock.version('node'), store_root, identity),
            'worker_declaration_existing_native_pm_node_required')
        node_path = package.binary(Store(store_root).entry(fact['entry']), target)
        _require(node_path is not None and node_path == node_path.resolve()
            and node_path == _reference(self.request['native_pm']['node'])
            and os.access(node_path, os.X_OK), 'worker_declaration_native_pm_node_path_required')
        immutable = (environments.runtime_facts_path(self.source), selected / 'pyvenv.cfg',
            paths.facts_path())
        expected_paths = {'runtime_facts': immutable[0], 'pyvenv_cfg': immutable[1], 'tool_facts': immutable[2]}
        _require(all(_reference(self.request['native_pm'][name]) == path for name, path in expected_paths.items()),
            'worker_declaration_native_pm_producer_paths_required')
        states = {path: self._state(path, private=False) for path in immutable}
        _require(all(_sha(states[path]['data']) == self.request['native_pm'][name]['sha256']
            for name, path in expected_paths.items()), 'worker_declaration_native_pm_producer_changed')
        binary = self._binary_state(node_path, full=check_build or not hasattr(self, '_pm_state'))
        _require(binary['sha256'] == self.request['native_pm']['node']['sha256'],
            'worker_declaration_native_pm_node_reference_changed')
        signature = (str(selected), str(node_path), states, binary)
        if hasattr(self, '_pm_state'):
            _require(signature == self._pm_state, 'worker_declaration_native_pm_selection_changed')
        else:
            self._pm_state = signature
        if check_build:
            from scripts.dsh_prepare import run
            script = self.source / 'scripts/build/freshness.mjs'
            self._clock()
            output = run([str(node_path), str(script), '--source', str(self.source),
                '--product', 'web', '--out', str(self.source / 'hermes_cli/web_dist')],
                self.source, env=compose_env([facts.env_for('node', store_root)], base=self.f.clean_environment(self.home)),
                timeout=min(10, self.budget.check(reserve=RESERVE)),
                deadline=self.budget.deadline - RESERVE)[0]
            _require(output.strip() == 'true', 'worker_declaration_current_native_web_build_required')
        return signature

    def _binary_state(self, path, *, full):
        # PM's supported Node executable can exceed the installer's 64MiB
        # document limit. Stream the existing executable with a separate bound;
        # never copy its bytes into the journal or loosen document validation.
        fields = ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode',
            'st_size', 'st_mtime_ns', 'st_ctime_ns')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            first = os.fstat(fd)
            identity = tuple(getattr(first, key) for key in fields)
            _require(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid()
                and first.st_nlink == 1 and stat.S_IMODE(first.st_mode) in (0o500, 0o555, 0o700, 0o755)
                and 0 < first.st_size <= 512 * 1024**2,
                'worker_declaration_native_pm_executable_required')
            if not full and hasattr(self, '_pm_binary'):
                _require(identity == self._pm_binary['identity'],
                    'worker_declaration_native_pm_executable_changed')
                digest = self._pm_binary['sha256']
            else:
                hasher = hashlib.sha256()
                total = 0
                while True:
                    self.budget.check(reserve=RESERVE)
                    block = os.read(fd, 1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    _require(total <= 512 * 1024**2,
                        'worker_declaration_native_pm_executable_required')
                    hasher.update(block)
                _require(total == first.st_size,
                    'worker_declaration_native_pm_executable_changed')
                digest = hasher.hexdigest()
            _require(identity == tuple(getattr(os.fstat(fd), key) for key in fields)
                == tuple(getattr(path.lstat(), key) for key in fields),
                'worker_declaration_native_pm_executable_changed')
            current = {'identity': identity, 'sha256': digest}
            if hasattr(self, '_pm_binary'):
                _require(current == self._pm_binary,
                    'worker_declaration_native_pm_executable_changed')
            else:
                self._pm_binary = current
            return current
        finally:
            os.close(fd)

    def consume(self):
        """Permanently consume this input generation before any native claim."""
        from .worker_archive import _Directory
        _require(hasattr(self, 'tx') and not self.consumed and not self.entered,
            'worker_declaration_preflight_before_consume_required')
        self.before_unchanged()
        self.clock = self._clock()
        attempted = False
        try:
            with _Directory(self.tx.parent) as parent:
                # Even failure between mkdir and intent publication consumes
                # this fixed input generation. No repair/adoption/retry here.
                attempted = True
                try:
                    os.mkdir(self.tx.name, 0o700, dir_fd=parent.fd)
                except FileExistsError:
                    attempted = False
                    raise DeclarationError('worker_declaration_consumed_no_retry') from None
                os.fsync(parent.fd)
                info = os.stat(self.tx.name, dir_fd=parent.fd, follow_symlinks=False)
                self._tx_identity = (info.st_dev, info.st_ino, info.st_uid, info.st_mode)
                txfd = os.open(self.tx.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent.fd)
                try:
                    opened = os.fstat(txfd)
                    _require((opened.st_dev, opened.st_ino, opened.st_uid, opened.st_mode) == self._tx_identity,
                        'worker_declaration_created_transaction_identity_changed')
                    intent = {'schema': SCHEMA, 'state': 'CONSUMED_NO_RETRY',
                        'request_sha256': self.request_reference['sha256'],
                        'request_reference': self.request_reference,
                        'request_semantic_sha256': _sha(self._request_bytes), 'clock': self.clock,
                        'clock_reference': self.request['clock'],
                        'previous_input': self.request['previous_input'], 'current_input': self.request['current_input'],
                        'before': self.request['before'], 'ready': False, 'retry_authorized': False,
                        'consumers_started': False, 'workers_enabled': False, 'runtime_acceptance': 'NOT_GRANTED'}
                    data = _encoded(intent)
                    fd = os.open('intent.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=txfd)
                    try:
                        os.fchmod(fd, 0o600)
                        created = os.fstat(fd)
                        owned_intent = {'data': data, 'mode': 0o600,
                            'identity': tuple(getattr(created, key) for key in
                                ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode'))}
                        _require(stat.S_ISREG(created.st_mode) and created.st_uid == os.getuid()
                            and created.st_nlink == 1, 'worker_declaration_created_intent_identity_required')
                        offset = 0
                        while offset < len(data):
                            written = os.write(fd, data[offset:])
                            _require(written > 0, 'worker_declaration_intent_write_unconfirmed')
                            offset += written
                        os.fsync(fd)
                        written = os.fstat(fd)
                        _require(tuple(getattr(written, key) for key in
                            ('st_dev', 'st_ino', 'st_uid', 'st_nlink', 'st_mode')) == owned_intent['identity']
                            and written.st_size == len(data), 'worker_declaration_created_intent_identity_changed')
                    finally:
                        os.close(fd)
                    os.fsync(txfd)
                    os.fsync(parent.fd)
                    parent.prove()
                    self._intent = owned_intent
                    _require(self.ordinary.same_update_file(self.tx / 'intent.json', self._intent),
                        'worker_declaration_intent_identity_changed')
                    self.consumed = True
                    self._consumption()
                finally:
                    os.close(txfd)
        except BaseException as error:
            if attempted:
                raise _stop('worker declaration consumption requires reconciliation', error) from error
            raise
        return self

    def _consumption(self):
        _require(self.consumed and _encoded(self.request) == self._request_bytes,
            'worker_declaration_consumed_exact_request_required')
        info = self.tx.lstat()
        _require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino, info.st_uid, info.st_mode) == self._tx_identity
            and self.ordinary.same_update_file(self.tx / 'intent.json', self._intent),
            'worker_declaration_consumption_custody_changed')

    def pins_unchanged(self, *, cleanup=False):
        _require(hasattr(self, 'before'), 'worker_declaration_preflight_required')
        self._context()
        self._clock(cleanup=cleanup)
        _require(all(self.ordinary.same_update_file(self.home / name, state)
            for name, state in self.retained.items())
            and all(self.ordinary.same_update_file(path, state) for path, state in self.external.items()),
            'worker_declaration_retained_or_external_changed')
        if self.consumed:
            self._consumption()
        return self

    def before_unchanged(self):
        self.pins_unchanged()
        _require(all(self.ordinary.same_update_file(self.home / name, state)
            for name, state in self.before.items()), 'worker_declaration_beforeimage_changed')
        return self

    def prove(self, *, cleanup=False):
        _require(self.active and not self.released, 'worker_declaration_active_native_custody_required')
        self._clock(cleanup=cleanup)
        self.pins_unchanged(cleanup=cleanup)
        for directory in self._directories:
            directory.prove()
        info = os.fstat(self._home_fd)
        _require((info.st_dev, info.st_ino) == (self.home.lstat().st_dev, self.home.lstat().st_ino),
            'worker_declaration_native_home_identity_changed')
        self._worker_runtime_prove()
        self._native_prove()
        self._workers_stopped(cleanup=cleanup)
        self._build_prove()
        self._pm_prove()
        self._lock_prove()
        from gateway import host_rendezvous as hr
        _require(all(hr.owns_host_lock(role) and self.ordinary.same_update_file(hr.lock_path(role), state)
            for role, state in self._role_states.items()),
            'worker_declaration_native_role_custody_changed')
        self._profile()
        self._pm_identity()
        return self

    def _workers_stopped(self, *, cleanup=False):
        """Native cessation observations; absence grants no archive acceptance."""
        from gateway.status import get_running_pid_identity_strict
        from scripts.dsh_prepare import run
        runtime = Path('/run/user') / str(os.getuid())
        command = ['/usr/bin/env', 'XDG_RUNTIME_DIR=' + str(runtime),
            'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime / 'bus'), 'SYSTEMCTL_FORCE_BUS=1',
            '/usr/bin/systemctl', '--user', 'show', self._worker_unit_name,
            '--property=LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup,InvocationID']
        output = run(command, self.f.ROOT,
            timeout=min(5, self.budget.check(reserve=0 if cleanup else RESERVE)),
            env=self.f.clean_environment(self.home),
            deadline=self.budget.deadline if cleanup else self.budget.deadline - RESERVE)[0]
        rows = [line.split('=', 1) for line in output.splitlines() if line]
        expected = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
            'MainPID': '0', 'ControlPID': '0', 'ControlGroup': '', 'InvocationID': ''}
        _require(len(rows) == len(expected) and all(len(row) == 2 for row in rows)
            and dict(rows) == expected, 'worker_declaration_native_workers_stop_required')
        for folder in ('dsh-safety', 'dsh-probe'):
            prefix = 'friday-qualify-dsh-' + _sha(str(
                self.profile_home / 'workers/qualification' / folder).encode())[:24]
            scopes = command[:6] + ['list-units', '--all', '--no-legend', '--plain', prefix + '-*.scope']
            # Native qualifier scope prefixes only; no foreign profile or
            # historical request supplies observation names or authority.
            listed = run(scopes, self.f.ROOT,
                timeout=min(5, self.budget.check(reserve=0 if cleanup else RESERVE)),
                env=self.f.clean_environment(self.home),
                deadline=self.budget.deadline if cleanup else self.budget.deadline - RESERVE)[0]
            _require(not listed.strip(), 'worker_declaration_native_worker_scope_present')
        absent = (self.profile_home / 'workers',
            self._worker_root / 'config/local-route.json',
            self._worker_state / 'rootlesskit/child_pid',
            self._worker_state / 'route-guard.json')
        _require(not any(os.path.lexists(path) for path in absent)
            and get_running_pid_identity_strict(self.profile_home / 'gateway.pid') is None,
            'worker_declaration_native_worker_activity_present')

    def _retain_directory(self, path, *, private=False):
        from .worker_archive import _Directory
        retained = self._stack.enter_context(_Directory(path, private=private))
        self._directories.append(retained)
        current = Path('/')
        for component, edge in zip(path.parts[1:], retained.edges):
            current = current / component
            previous = self._directory_edges.get(current)
            _require(previous is None or previous == tuple(edge[3]),
                'worker_declaration_parent_identity_changed')
            self._directory_edges[current] = tuple(edge[3])

    def __enter__(self):
        from .worker_archive import _Directory
        from gateway import host_rendezvous as hr
        from hermes_cli import friday_user_scope as user
        _require(self.consumed and not self.entered, 'worker_declaration_consume_before_native_claim_required')
        self.entered = True
        self._consumption()
        self.before_unchanged()
        self._stack = ExitStack()
        try:
            # All native paths are the existing retained deployment. No lock
            # registry, dashboard session or active onboarding can replace them.
            for path, private in ((self.home, True), (self.home / 'profiles', True),
                    (self.profile_home, True), (self.source, False), (self.home / 'preparation', True),
                    (self.access_path.parent, True), (self.tx, True), (hr.host_state_dir(), True)):
                self._retain_directory(path, private=private)
            for path in sorted({path.parent for path in self.external}, key=str):
                self._retain_directory(path)
            self._home_fd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._stack.callback(os.close, self._home_fd)
            fcntl.flock(self._home_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._stack.enter_context(user.authority(self.home))
            self._worker_runtime_prove = self._stack.enter_context(self.ordinary.retained_build_lock(
                self.source, lock_path=self._worker_runtime_lock, required=True))
            _require(not any(hr.owns_host_lock(role) for role in (
                hr.ROLE_GATEWAY, hr.ROLE_SERVE, hr.ROLE_DESKTOP_SERVE)),
                'worker_declaration_existing_native_role_owner_refused')
            self._native_claim_entered = True
            self._native_prove = self._stack.enter_context(
                self.ordinary.stopped_consumers(self.home, self.request['native_unit'], self.budget))
            self._role_states = {role: self._state(hr.lock_path(role)) for role in (
                hr.ROLE_GATEWAY, hr.ROLE_SERVE, hr.ROLE_DESKTOP_SERVE)}
            _require(all(state['data'] == b'' for state in self._role_states.values()),
                'worker_declaration_native_empty_role_lock_required')
            self._build_prove = self._stack.enter_context(self.ordinary.retained_build_lock(self.source, required=True))
            self._pm_prove = self._stack.enter_context(self.ordinary.retained_pm_lock(self.home, self.source))
            self._lock_prove = self._stack.enter_context(
                self.ordinary.inference_locks(self.home, self.profile_home, self.access_path, self.budget))
            self._pm_identity(check_build=True)
            for path in sorted({path.parent for path in self._pm_state[2]}
                    | {Path(self._pm_state[1]).parent}, key=str):
                self._retain_directory(path)
            self._profile(original=True)
            self.active = True
            self.prove()
            self.before_unchanged()
            return self
        except BaseException as error:
            self.active = False
            secondary = []
            try:
                self._stack.close()
            except BaseException as cleanup:
                secondary.append(cleanup)
            if getattr(self, '_native_claim_entered', False):
                for role in (hr.ROLE_DESKTOP_SERVE, hr.ROLE_SERVE, hr.ROLE_GATEWAY):
                    try:
                        if hr.owns_host_lock(role):
                            hr.release_host_lock(role)
                        _require(not hr.owns_host_lock(role),
                            'worker_declaration_partial_native_release_unconfirmed')
                    except BaseException as cleanup:
                        secondary.append(cleanup)
            # Native stopped_consumers cannot identify a claim interrupted
            # before its local claimed list append. Never label that outcome a
            # clean refusal or reacquire it; retain the consumed generation.
            raise _stop('worker declaration native admission requires reconciliation', error, secondary) from error

    def __exit__(self, kind, error, traceback):
        primary = error
        try:
            if primary is None:
                self.prove(cleanup=True)
        except BaseException as check:
            primary = check
        self.active = False
        secondary = []
        try:
            self._stack.__exit__(kind, error, traceback)
        except BaseException as cleanup:
            if primary is None:
                primary = cleanup
            elif cleanup is not primary:
                secondary.append(cleanup)
        self.released = True
        try:
            self.prove_released()
        except BaseException as cleanup:
            if primary is None:
                primary = cleanup
            elif cleanup is not primary:
                secondary.append(cleanup)
        if primary is not None and (primary is not error or secondary):
            raise _stop('worker declaration native custody release requires reconciliation', primary, secondary) from primary
        return False

    def prove_released(self):
        """Fresh stop/release evidence only; never reacquire or permit rollback."""
        from gateway import host_rendezvous as hr
        from gateway.status import get_running_pid_identity_strict
        _require(self.released and not self.active,
            'worker_declaration_native_release_boundary_required')
        try:
            return self._released_observations()
        except BaseException as error:
            raise _stop('worker declaration final native release requires reconciliation', error) from error

    def _released_observations(self):
        from gateway import host_rendezvous as hr
        from gateway.status import get_running_pid_identity_strict
        self.pins_unchanged(cleanup=True)
        for path, expected in self._directory_edges.items():
            info = path.lstat()
            _require((info.st_dev, info.st_ino, info.st_uid, info.st_mode) == expected,
                'worker_declaration_released_parent_identity_changed')
        _require(not any(hr.owns_host_lock(role) or os.path.lexists(hr.record_path(role))
            or hr.read_record(role, include_stale=True) is not None for role in self._role_states)
            and get_running_pid_identity_strict(self.home / 'gateway.pid') is None,
            'worker_declaration_native_release_unconfirmed')
        # The old prover observes systemd/pid/records and takes no new lock.
        self._native_prove()
        self._workers_stopped(cleanup=True)
        for role, state in self._role_states.items():
            _require(self.ordinary.same_update_file(hr.lock_path(role), state),
                'worker_declaration_native_released_lock_changed')
        return self
