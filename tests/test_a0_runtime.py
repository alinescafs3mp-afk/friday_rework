"""Offline native contract/fault controls. Never contact Docker/systemd/models."""
import copy
import importlib.util
import json
import os
import io
import hashlib
from pathlib import Path
import tempfile
import subprocess
import sys
import zlib
import time
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch
import pytest

SPEC = importlib.util.spec_from_file_location('a0_runtime', Path(__file__).parents[1] / 'scripts/a0_runtime.py')
a0 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = a0
SPEC.loader.exec_module(a0)
CID = 'a' * 64
INV = 'b' * 32


def protected_native_files(root):
    """Exact source helpers and explicit unexecuted OS-interface fixtures."""
    source = Path(__file__).resolve().parents[1]
    root.mkdir(mode=0o700)
    unit = root / '.runtime/rootless-docker/supervisor/friday-rework-docker.service'
    unit.parent.mkdir(parents=True)
    unit.write_bytes(b'OFFLINE UNIT PIN; NEVER INSTALLED'); unit.chmod(0o400)
    files = {'PROJECT': root}
    for name, relative in [('DOCKER', None), ('LAUNCHER', 'scripts/rootless_docker_launch.py'),
                           ('PROFILE_SOURCE', 'plugins/friday_rework/adapters/a0_profile.py'),
                           ('WEB_SOURCE', 'plugins/friday_rework/adapters/a0_web.py')]:
        path = root / name.lower()
        path.write_bytes((source / relative).read_bytes() if relative else b'OFFLINE DOCKER PIN; NEVER EXECUTED')
        path.chmod(0o400); files[name] = path
    return files


@pytest.fixture(autouse=True)
def offline_native_files(tmp_path, monkeypatch):
    # Unit retirement and writable development files cannot supply trusted
    # runtime inputs. Use protected exact helpers with intercepted native IO.
    for name, path in protected_native_files(tmp_path / 'offline-native').items():
        monkeypatch.setattr(a0, name, path)


def obj(p, *, running=False):
    return {'Id': CID, 'Name': '/' + p['container_name'], 'Image': a0.IMAGE,
            'Config': {'Image': a0.IMAGE, 'Labels': dict(a0.labels(p), upstream='intact'),
                       'Entrypoint': ['/bin/bash'],
                       'Cmd': ['-ceu', a0.START_SCRIPT if p['mode'] == 'runtime' else a0.INVENTORY_COMMAND],
                       'WorkingDir': '/a0'},
            'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'PortBindings': {},
                           'PublishAllPorts': False, 'Binds': None, 'Devices': [], 'DeviceRequests': None,
                           'PidMode': '', 'IpcMode': 'private', 'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                           'CapDrop': ['ALL'], 'CapAdd': None, 'SecurityOpt': ['no-new-privileges'],
                           'Memory': a0.MEMORY, 'MemorySwap': a0.MEMORY, 'NanoCpus': 2_000_000_000,
                           'PidsLimit': a0.PIDS, 'ReadonlyRootfs': p['mode'] == 'inventory'},
            'Mounts': [] if p['mode'] == 'inventory' else
            [{'Type': 'bind', 'Source': p['state_dir'], 'Destination': '/a0/usr', 'RW': True, 'Propagation': 'rprivate'}],
            'State': {'Running': running, 'Pid': os.getpid() if running else 0, 'ExitCode': 0}}


class Supervisor:
    def __init__(self):
        self.stops = []

    def observe(self, association):
        return SimpleNamespace(missing=False, invocation_id=INV, quiescent=False)

    def stop(self, association):
        self.stops.append(association)
        return SimpleNamespace(quiescent=True)


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name); self.root.chmod(0o700)
        self.patch_root = patch.object(a0, 'RUNTIME', self.root)
        self.patch_root.start(); self.addCleanup(self.patch_root.stop); self.addCleanup(self.tmp.cleanup)
        self.now = time.time()
        self.p = a0.plan(self.now, self.now + 1800, assignment='fixture', generation=1,
                         owner_slot='astra', original_budget_seconds=1800)
        self.plan_file = self.root / 'plan.json'
        a0.write_json(self.plan_file, self.p)
        self.calls = []; self.container = obj(self.p)
        self.sup = Supervisor()
        self.runtime = a0.Runtime(self.p, runner=self.command, supervisor=self.sup)

    def command(self, argv, timeout):
        self.calls.append(list(argv))
        if 'systemctl' in argv[0]:
            return ('ActiveState=active\nDelegateSubgroup=dockerd\nMemoryMax=21474836480\n'
                    'TasksMax=2048\nCPUQuotaPerSecUSec=8s\nRestart=no\nKillMode=control-group\n'
                    'SendSIGKILL=yes\nDropInPaths=\n')
        if 'systemd-run' in argv[0]: return ''
        if 'info' in argv:
            return json.dumps({'CgroupVersion': '2', 'CgroupDriver': 'systemd',
                               'SecurityOptions': ['name=rootless'], 'ServerVersion': '29.8.2',
                               **{k: True for k in ['MemoryLimit', 'SwapLimit', 'CpuCfsPeriod', 'CpuCfsQuota', 'PidsLimit']}})
        if 'ps' in argv: return ''
        if 'create' in argv: return CID + '\n'
        if 'inspect' in argv: return json.dumps([self.container])
        if 'stop' in argv:
            self.container['State'].update(Running=False, Pid=0)
            return CID
        self.fail('Unexpected native command in fixture')

    def ready_receipt(self, *, running=False):
        self.runtime.directory.mkdir(mode=0o700)
        r = {'plan_sha256': a0.digest(self.p), 'container_id': CID,
             'invocation_id': INV, 'observations': []}
        a0.write_json(self.runtime.receipt_path, r)
        self.container = obj(self.p, running=running)
        return r

    def test_plan_exact_original_budget_and_finite_startup(self):
        self.assertEqual(a0.remaining(self.p, self.now + 100), 1675)
        argv = self.runtime.unit_argv(CID, self.plan_file, a0.sha(self.plan_file))
        self.assertIn('--property=RuntimeMaxSec=120s', argv)
        self.assertIn('--property=Restart=no', argv)
        self.assertIn('--property=StandardOutput=null', argv)
        self.assertIn('--property=StandardError=null', argv)
        self.assertIn('--property=KillMode=control-group', argv)
        self.assertIn('--property=SendSIGKILL=yes', argv)
        stop_post = next(x for x in argv if x.startswith('--property=ExecStopPost='))
        self.assertEqual(stop_post, '--property=ExecStopPost=' +
                         ' '.join([str(a0.DOCKER), '--host', a0.SOCKET, 'stop', '--time', '2', CID]))
        self.assertNotIn(str(self.plan_file), stop_post)

    def test_explicit_phase_identity_and_budget_are_hash_bound(self):
        options = dict(assignment='first-runtime', generation=1, owner_slot='astra',
                       original_budget_seconds=300)
        p = a0.plan(self.now, self.now + 300, **options)
        self.assertEqual(p['owner'], 'astra:first-runtime#1')
        self.assertEqual(a0.remaining(p, self.now + 200), 75)
        self.assertNotEqual(p['identity'], self.p['identity'])
        for field, value in [('assignment', 'other'), ('generation', 2), ('owner_slot', 'sol')]:
            changed = a0.plan(self.now, self.now + 300, **{**options, field: value})
            self.assertNotEqual(changed['unit'], p['unit'])
            self.assertNotEqual(a0.labels(changed), a0.labels(p))
            damaged = {**p, field: value}
            with self.assertRaises(a0.RuntimeErrorBoundary):
                a0.validate(damaged)
        for field, value in [('deadline_unix', p['deadline_unix'] + 60),
                             ('original_budget_seconds', 360), ('owner', 'sol:other#1'),
                             ('schema', 'friday.a0.runtime-plan.v1')]:
            with self.assertRaises(a0.RuntimeErrorBoundary):
                a0.validate({**p, field: value})
        self.assertEqual(self.calls, [])

    def test_new_plan_rejects_implicit_or_invalid_grants(self):
        options = dict(assignment='first-runtime', generation=1, owner_slot='astra',
                       original_budget_seconds=300)
        with self.assertRaises(TypeError):
            a0.plan(self.now, self.now + 1800)
        for field, value in [('assignment', '../foreign'), ('assignment', ''),
                             ('generation', True), ('generation', 0),
                             ('owner_slot', 'foreign'), ('owner_slot', {}),
                             ('original_budget_seconds', True), ('original_budget_seconds', 1801)]:
            with self.assertRaises(a0.RuntimeErrorBoundary):
                a0.plan(self.now, self.now + 300, **{**options, field: value})
        with self.assertRaises(a0.RuntimeErrorBoundary):
            a0.plan(0, 300, **options)
        with self.assertRaises(a0.RuntimeErrorBoundary):
            a0.remaining(self.p, self.now - 1)
        self.assertEqual(self.calls, [])

    def test_expiry_and_clock_rollback_refuse(self):
        for now in [self.now - 1, self.now + 1790, float('nan')]:
            with self.subTest(now=now), self.assertRaises(a0.RuntimeErrorBoundary):
                a0.remaining(self.p, now)

    def test_plan_foreign_owner_image_budget_mount_and_network_drift(self):
        for field, value in [('owner', 'other'), ('image', 'latest'), ('original_budget_seconds', 7200),
                             ('state_dir', '/home/jericho'), ('network', 'host'), ('ports', [80]),
                             ('generation', 2), ('code_sha256', '0' * 64)]:
            changed = dict(self.p, **{field: value})
            with self.subTest(field=field), self.assertRaises(a0.RuntimeErrorBoundary):
                a0.validate(changed)

    def test_native_commands_use_exact_pinned_image_and_no_mount_exposure(self):
        argv = a0.create_argv(self.p)
        self.assertIn('--pull=never', argv); self.assertIn('--network=none', argv)
        self.assertIn('--restart=no', argv); self.assertIn(a0.IMAGE, argv)
        mounts = [argv[i + 1] for i, x in enumerate(argv) if x == '--mount']
        self.assertEqual(mounts, ['type=bind,src=' + self.p['state_dir'] + ',dst=/a0/usr'])
        self.assertFalse(any(x.startswith('--publish') or 'docker.sock' in x for x in argv[3:]))

    def test_inventory_two_complete_runtime_distributions_readonly_without_mounts(self):
        p = a0.plan(self.now, self.now + 1800, assignment='fixture', generation=1,
                    owner_slot='astra', original_budget_seconds=1800, mode='inventory')
        argv = a0.create_argv(p)
        self.assertIn('--read-only', argv); self.assertNotIn('--mount', argv)
        self.assertIn('/opt/venv-a0/bin/python', argv[-1])
        self.assertIn('/opt/venv/bin/python', argv[-1])
        a0.container_checked(p, obj(p), CID)
        runtime = a0.Runtime(p, runner=self.command, supervisor=self.sup)
        unit = runtime.unit_argv(CID, self.plan_file, a0.sha(self.plan_file))
        self.assertIn('--property=RemainAfterExit=yes', unit)
        self.assertTrue(any(x.startswith('--property=StandardOutput=append:') for x in unit))

    def test_wrong_image_label_id_command_reject_before_stop(self):
        self.ready_receipt(running=True)
        for mutate in [lambda x: x.update(Image='sha256:' + '0' * 64),
                       lambda x: x['Config']['Labels'].update({'friday.rework.owner': 'foreign'}),
                       lambda x: x.update(Id='c' * 64),
                       lambda x: x['Config'].update(Cmd=['-c', 'different'])]:
            self.container = obj(self.p, running=True); mutate(self.container); self.calls.clear()
            with self.assertRaises(a0.RuntimeErrorBoundary): self.runtime.stop()
            self.assertFalse(any('stop' in c for c in self.calls))
            self.assertEqual(self.sup.stops, [])

    def test_foreign_mount_or_network_or_privilege_refuses(self):
        for field, value in [('NetworkMode', 'host'), ('Privileged', True), ('PidMode', 'host'),
                             ('Memory', 0), ('PidsLimit', -1), ('CapAdd', ['SYS_ADMIN']),
                             ('RestartPolicy', {'Name': 'always', 'MaximumRetryCount': 0}),
                             ('PortBindings', {'5000/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '5000'}]})]:
            x = obj(self.p); x['HostConfig'][field] = value
            with self.subTest(field=field), self.assertRaises(a0.RuntimeErrorBoundary):
                a0.container_checked(self.p, x, CID)
        for source in ['/home/jericho', '/run/user/1000', '/var/run/docker.sock']:
            x = obj(self.p); x['Mounts'][0]['Source'] = source
            with self.subTest(source=source), self.assertRaises(a0.RuntimeErrorBoundary):
                a0.container_checked(self.p, x, CID)

    def test_missing_resource_support_refuses_before_attempt_or_create(self):
        original = self.runtime.runner
        for key in ['MemoryLimit', 'SwapLimit', 'CpuCfsPeriod', 'CpuCfsQuota', 'PidsLimit']:
            for value in [False, None, 'true', 1]:
                with self.subTest(key=key, value=value):
                    def runner(argv, timeout):
                        raw = original(argv, timeout)
                        if 'info' in argv:
                            d = json.loads(raw); d[key] = value; return json.dumps(d)
                        return raw
                    self.runtime.runner = runner; self.calls.clear()
                    with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'resource_limits_unsupported'):
                        self.runtime.start(self.plan_file, a0.sha(self.plan_file))
                    self.assertFalse(self.runtime.directory.exists())
                    self.assertFalse(any('create' in x or 'systemd-run' in x[0] for x in self.calls))
        self.runtime.runner = original

    def test_go_field_names_are_not_docker_json_capabilities(self):
        original = self.runtime.runner
        def runner(argv, timeout):
            raw = original(argv, timeout)
            if 'info' in argv:
                data = json.loads(raw)
                data['CPUCfsPeriod'] = data.pop('CpuCfsPeriod')
                data['CPUCfsQuota'] = data.pop('CpuCfsQuota')
                return json.dumps(data)
            return raw
        self.runtime.runner = runner
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'resource_limits_unsupported'):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertFalse(self.runtime.directory.exists())
        self.assertFalse(any('create' in x or 'systemd-run' in x[0] for x in self.calls))

    def test_resource_drift_still_allows_only_checked_owned_stop(self):
        for key, value in [('MemorySwap', -1), ('Memory', 0), ('NanoCpus', 0), ('PidsLimit', -1)]:
            with self.subTest(key=key):
                x = obj(self.p); x['HostConfig'][key] = value
                with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'resource_boundary_changed'):
                    a0.container_checked(self.p, x, CID)
                a0.container_checked(self.p, x, CID, stop_owned=True)
                x['Id'] = 'f' * 64
                with self.assertRaises(a0.RuntimeErrorBoundary):
                    a0.container_checked(self.p, x, CID, stop_owned=True)

    def test_start_converted_swap_refuses_native_start_and_retains_exact_stopped_object(self):
        self.container['HostConfig']['MemorySwap'] = -1
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'resource_boundary_changed'):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertFalse(any('systemd-run' in x[0] for x in self.calls))
        stopped = json.loads((self.runtime.directory / 'stop.json').read_text())
        self.assertEqual(stopped['container_id'], CID)
        self.assertEqual(stopped['status'], 'STOP_CONFIRMED')
        self.assertEqual(stopped['pid_start_sampling'], 'NOT_RETAINED')
        self.assertTrue((self.runtime.directory / 'attempt.json').exists())

    def test_resource_drift_in_observe_stops_both_owned_boundaries(self):
        self.ready_receipt(running=True)
        self.container['HostConfig']['MemorySwap'] = -1
        sample = {'group': '/fixture/docker-' + CID + '.scope', 'populated': True, 'processes': []}
        with patch.object(self.runtime, 'snapshot_container', return_value=sample), patch.object(a0, 'cessation', return_value={'confirmed': True}):
            with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'resource_boundary_changed'):
                self.runtime.observe()
        self.assertFalse(self.container['State']['Running'])
        self.assertEqual(sum('stop' in x for x in self.calls), 1)
        self.assertEqual(len(self.sup.stops), 1)

    def test_resource_drift_in_explicit_stop_does_not_block_native_control(self):
        self.ready_receipt(running=True)
        self.container['HostConfig']['MemorySwap'] = -1
        sample = {'group': '/fixture/docker-' + CID + '.scope', 'populated': True, 'processes': []}
        with patch.object(self.runtime, 'snapshot_container', return_value=sample), patch.object(a0, 'cessation', return_value={'confirmed': True}):
            result = self.runtime.stop()
        self.assertEqual(result['status'], 'STOP_CONFIRMED')
        self.assertFalse(self.container['State']['Running'])
        self.assertEqual(len(self.sup.stops), 1)

    def actual_caps(self, swap='0'):
        read = Path.read_text
        values = {'memory.max': str(a0.MEMORY), 'memory.swap.max': swap,
                  'cpu.max': '200000 100000', 'pids.max': str(a0.PIDS)}
        def reader(path, *args, **kwargs):
            if str(path).startswith('/sys/fs/cgroup/fixture/'):
                if values[path.name] is None:
                    raise FileNotFoundError('missing actual swap interface fixture')
                return values[path.name]
            return read(path, *args, **kwargs)
        return patch.object(Path, 'read_text', reader)

    def test_actual_zero_swap_is_observed_and_budget_unchanged(self):
        self.ready_receipt(running=True)
        original = copy.deepcopy(self.p)
        sample = {'group': '/fixture/docker-' + CID + '.scope', 'populated': True,
                  'processes': [{'pid': 1234, 'start_ticks': 7}]}
        with patch.object(self.runtime, 'snapshot_container', return_value=sample), self.actual_caps():
            result = self.runtime.observe()
        self.assertEqual(result['caps']['memory.swap.max'], '0')
        self.assertEqual(self.p, original)
        self.assertEqual(self.sup.stops, [])
        self.assertFalse(any('stop' in x or 'create' in x for x in self.calls))

    def test_actual_nonzero_or_missing_swap_stops_without_replay(self):
        for swap in ['max', '2147483648', '1', '', None]:
            with self.subTest(swap=swap):
                if not self.runtime.directory.exists():
                    self.ready_receipt(running=True)
                self.container = obj(self.p, running=True)
                self.sup.stops.clear(); self.calls.clear()
                sample = {'group': '/fixture/docker-' + CID + '.scope', 'populated': True,
                          'processes': [{'pid': 1234, 'start_ticks': 7}]}
                with patch.object(self.runtime, 'snapshot_container', return_value=sample), \
                        self.actual_caps(swap), patch.object(a0, 'cessation', return_value={'confirmed': True}), \
                        self.assertRaises(FileNotFoundError if swap is None else a0.RuntimeErrorBoundary):
                    self.runtime.observe()
                self.assertFalse(self.container['State']['Running'])
                self.assertEqual(len(self.sup.stops), 1)
                self.assertEqual(self.sup.stops[0]['native']['invocation_id'], INV)
                self.assertEqual(sum('stop' in x for x in self.calls), 1)
                self.assertFalse(any('create' in x or 'systemd-run' in x[0] for x in self.calls))

    def test_swap_read_failure_keeps_original_with_secondary_cleanup_uncertainty(self):
        self.ready_receipt(running=True)
        original = PermissionError('swap read denied fixture')
        sample = {'group': '/fixture/docker-' + CID + '.scope', 'populated': True, 'processes': []}
        with patch.object(self.runtime, 'snapshot_container', return_value=sample), \
                self.actual_caps(), \
                patch.object(self.sup, 'stop', side_effect=RuntimeError('native stop uncertain')) as stop, \
                patch.object(a0, 'cessation', return_value={'confirmed': True}), \
                self.assertRaises(a0.RuntimeStopUnconfirmed) as ctx:
            fixture_read = Path.read_text
            def swap_read(path, *args, **kwargs):
                if path.name == 'memory.swap.max': raise original
                return fixture_read(path, *args, **kwargs)
            with patch.object(Path, 'read_text', swap_read):
                self.runtime.observe()
        self.assertIs(ctx.exception.__cause__, original)
        self.assertTrue(any('STOP_UNCONFIRMED' in x for x in original.__notes__))
        self.assertEqual(stop.call_count, 1)
        self.assertFalse(self.container['State']['Running'])

    def test_live_start_once_then_restart_refused_without_native_replay(self):
        outcome = self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertEqual(outcome['container_id'], CID)
        self.assertEqual(outcome['invocation_id'], INV)
        count = len(self.calls)
        with self.assertRaises(a0.RuntimeErrorBoundary):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertEqual(len(self.calls), count)

    def test_unknown_create_reconciles_and_stops_exact_object_without_retry(self):
        def runner(argv, timeout):
            if 'create' in argv:
                self.calls.append(argv); self.container = obj(self.p, running=True)
                raise a0.RuntimeErrorBoundary('native_control_uncertain')
            return self.command(argv, timeout)
        self.runtime.runner = runner
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'native_control_uncertain'):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertEqual(sum('create' in x for x in self.calls), 1)
        self.assertEqual(sum('stop' in x for x in self.calls), 1)
        self.assertTrue((self.runtime.directory / 'attempt.json').is_file())

    def test_receipt_persistence_failure_stops_known_container_and_preserves_error(self):
        original = a0.write_json
        def write(path, value, **kw):
            if Path(path).name == 'native.json':
                raise OSError('owned write fixture failure')
            return original(path, value, **kw)
        # Treat created object as running to check cleanup independent of storage.
        self.container = obj(self.p, running=True)
        with patch.object(a0, 'write_json', side_effect=write), self.assertRaises(OSError):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertEqual(sum('stop' in x for x in self.calls), 1)
        self.assertFalse(self.container['State']['Running'])

    def test_unconfirmed_cleanup_does_not_replace_initial_uncertainty(self):
        def runner(argv, timeout):
            if 'create' in argv: raise a0.RuntimeErrorBoundary('native_control_uncertain')
            if 'inspect' in argv: raise a0.RuntimeErrorBoundary('native_command_failed')
            return self.command(argv, timeout)
        self.runtime.runner = runner
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'native_control_uncertain') as ctx:
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertIn('STOP_UNCONFIRMED', ctx.exception.__notes__[0])

    def test_stop_preserves_state_and_releases_lock_before_native_stop(self):
        self.ready_receipt(running=True)
        marker = self.runtime.directory / 'retained.txt'; marker.write_bytes(b'old output')
        old_stop = self.sup.stop
        def native_stop(a):
            # A second owned observer can take the lock while systemd stops.
            self.runtime.stop(from_stop_post=True)
            return old_stop(a)
        self.sup.stop = native_stop
        result = self.runtime.stop()
        self.assertEqual(result['status'], 'STOP_CONFIRMED')
        self.assertEqual(result['pid_start_sampling'], 'NOT_RETAINED')
        self.assertEqual(marker.read_bytes(), b'old output')
        self.assertEqual(len(self.sup.stops), 1)

    def test_stop_receipt_error_preserves_error_and_stops_native_outside_lock(self):
        self.ready_receipt(running=True)
        original = OSError('stop receipt ENOSPC')
        writer = a0.write_json
        def failwrite(path, value, **kw):
            if Path(path).name == 'stop.json': raise original
            return writer(path, value, **kw)
        old_stop = self.sup.stop
        def native_stop(association):
            with self.runtime.locked(): pass
            return old_stop(association)
        self.sup.stop = native_stop
        with patch.object(a0, 'write_json', side_effect=failwrite), self.assertRaises(a0.RuntimeStopUnconfirmed) as ctx:
            self.runtime.stop()
        self.assertIs(ctx.exception.__cause__, original)
        self.assertEqual(len(self.sup.stops), 1)
        self.assertFalse(self.container['State']['Running'])

    def test_foreign_native_identity_refuses_both_stop_paths(self):
        self.ready_receipt(running=True)
        for method in [self.runtime.stop, self.runtime.observe]:
            self.calls.clear()
            with patch.object(self.sup, 'observe', side_effect=a0.RuntimeErrorBoundary('replaced invocation')):
                with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'replaced invocation'): method()
            self.assertEqual(self.sup.stops, [])
            self.assertFalse(any('stop' in c for c in self.calls))
            self.assertTrue(self.container['State']['Running'])

    def test_native_stop_uncertainty_is_not_replayed(self):
        self.ready_receipt(running=True)
        with patch.object(self.sup, 'stop', side_effect=a0.RuntimeErrorBoundary('uncertain')) as stop:
            with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'uncertain'): self.runtime.stop()
        self.assertEqual(stop.call_count, 1)

    def test_corrupt_receipt_is_uncertain_no_inferred_stop(self):
        self.ready_receipt(); self.runtime.receipt_path.write_bytes(b'{')
        with self.assertRaises(json.JSONDecodeError): self.runtime.stop()
        self.assertEqual(self.calls, [])

    def test_active_foreign_container_prevents_create(self):
        def runner(argv, timeout):
            if 'ps' in argv: return 'foreign-id\n'
            return self.command(argv, timeout)
        self.runtime.runner = runner
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'active_container'):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertFalse(self.runtime.directory.exists())

    def test_unsupported_actual_daemon_driver_prevents_create(self):
        def runner(argv, timeout):
            if 'info' in argv:
                return json.dumps({'CgroupVersion': '1', 'CgroupDriver': 'none',
                                   'ServerVersion': '29.8.2', 'SecurityOptions': []})
            return self.command(argv, timeout)
        self.runtime.runner = runner
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'unsupported'):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertFalse(self.runtime.directory.exists())

    def test_post_start_receipt_failure_keeps_actual_invocation_for_cleanup(self):
        original = a0.write_json
        def writer(path, value, **kw):
            if Path(path).name == 'native.json' and kw.get('replace'):
                self.container['State'].update(Running=True, Pid=os.getpid())
                raise OSError('post-start write fixture failure')
            return original(path, value, **kw)
        with patch.object(a0, 'write_json', side_effect=writer), self.assertRaises(OSError):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertEqual(self.sup.stops[-1]['native']['invocation_id'], INV)
        self.assertFalse(self.container['State']['Running'])

    def test_corrected_wrapper_can_stop_prior_plan_without_resetting_identity(self):
        changed = dict(self.p, code_sha256='0' * 64)
        with self.assertRaises(a0.RuntimeErrorBoundary): a0.Runtime(changed, supervisor=self.sup)
        a0.Runtime(changed, supervisor=self.sup, stopping=True)
        self.assertEqual(a0.validate(changed, check_files=False)['accepted_unix'], self.now)

    def test_symlink_and_loose_plan_refuse(self):
        link = self.root / 'link'; link.symlink_to(self.plan_file)
        with self.assertRaises(a0.RuntimeErrorBoundary): a0.private(link)
        self.plan_file.chmod(0o644)
        with self.assertRaises(a0.RuntimeErrorBoundary):
            self.runtime.start(self.plan_file, a0.sha(self.plan_file))
        self.assertEqual(self.calls, [])

    def test_same_checked_receipt_stop_works_after_launch_pin_drift(self):
        self.ready_receipt(running=True)
        # Instantiate while pins are valid; already checked memory identity must
        # still permit immediate stop if a later launch validation would fail.
        with patch.object(a0, 'validate', side_effect=a0.RuntimeErrorBoundary('changed')):
            self.assertEqual(self.runtime.stop()['status'], 'STOP_CONFIRMED')

    def test_cgroup_and_pid_reuse_quiescence_controls(self):
        old = {'group': '/owned', 'processes': [{'pid': 100, 'start_ticks': 7}]}
        for current, populated, expected in [({'pid': 100, 'start_ticks': 7, 'state': 'S'}, False, False),
                                               ({'pid': 100, 'start_ticks': 8, 'state': 'S'}, False, True),
                                               (None, True, False), (None, False, True)]:
            with self.subTest(current=current, populated=populated), \
                    patch.object(a0, 'process_identity', return_value=current), \
                    patch.object(a0, 'cgroup_snapshot', return_value={'populated': populated}):
                self.assertEqual(a0.cessation(old)['confirmed'], expected)

    def test_observed_detached_survivor_refuses_confirmed_stop(self):
        r = self.ready_receipt(running=True)
        r['observations'] = [{'group': '/owned', 'processes': [{'pid': 100, 'start_ticks': 7}]}]
        self.runtime.known = r
        with patch.object(a0, 'cessation', return_value={'confirmed': False}), \
                self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'STOP_UNCONFIRMED'):
            self.runtime.stop()

    def test_materialized_native_config_is_private_no_cloud_no_model_secrets(self):
        usr = self.root / 'usr'; a0.materialize(usr)
        values = json.loads((usr / 'plugins/_model_config/presets.yaml').read_text())
        self.assertEqual(values[0]['name'], 'Default')
        self.assertEqual(set(values[0]), {'name', 'chat', 'utility', 'embedding'})
        for slot in ['chat', 'utility', 'embedding']:
            self.assertEqual(values[0][slot]['provider'], 'other' if slot == 'embedding' else 'openai')
            self.assertTrue(values[0][slot]['api_base'].startswith('http://192.168.1.78:'))
        self.assertEqual(json.loads((usr / 'plugins/_code_execution/config.json').read_text()), {'ssh_enabled': 'false'})
        env = (usr / '.env').read_text()
        self.assertIn('AUTH_PASSWORD=', env); self.assertIn('A0_PERSISTENT_RUNTIME_ID=', env)
        self.assertNotIn('API_KEY', env)
        self.assertEqual((usr / '.env').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): a0.materialize(usr)

    def test_health_and_native_auth_checks_get_only_never_message_or_token_output(self):
        self.assertNotIn('api_message', a0.HEALTH_SCRIPT + a0.AUTH_SCRIPT)
        self.assertNotIn('POST', a0.HEALTH_SCRIPT + a0.AUTH_SCRIPT)
        self.assertIn('settings.create_auth_token()', a0.AUTH_SCRIPT)
        self.assertIn('"key_kind":label,"http":status', a0.AUTH_SCRIPT)

    def test_probe_checks_running_exact_native_boundary_before_one_finite_exec(self):
        self.ready_receipt(running=True)
        # A real probe result is tested with native dependency doubles below;
        # this control isolates the existing executor's identity/timeout path.
        def runner(argv, timeout):
            if 'exec' in argv:
                self.calls.append(argv)
                self.assertLessEqual(timeout, 15)
                self.assertEqual(argv[3:8], ['exec', '--workdir=/a0', CID, '/opt/venv-a0/bin/python', '-B'])
                self.assertIn('native_probe(DEPLOYMENT)', argv[-1])
                return json.dumps({'status': 'REFUSED', 'code': 'native_token_cache_unavailable'})
            return self.command(argv, timeout)
        self.runtime.runner = runner
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, '^native_token_cache_unavailable$'):
            self.runtime.probe()
        self.assertEqual(sum('exec' in x for x in self.calls), 1)
        self.assertEqual(self.sup.stops, [])

    def test_probe_wrong_network_mount_stopped_or_foreign_unit_refuse_without_exec(self):
        self.ready_receipt(running=True)
        baseline = copy.deepcopy(self.container)
        for change in (lambda x: x['HostConfig'].update(NetworkMode='host'),
                       lambda x: x['Mounts'].append({'Destination': '/foreign'}),
                       lambda x: x['State'].update(Running=False, Pid=0)):
            self.container = copy.deepcopy(baseline); change(self.container); self.calls.clear()
            with self.assertRaises(a0.RuntimeErrorBoundary): self.runtime.probe()
            self.assertFalse(any('exec' in x for x in self.calls))
        self.container = baseline; self.calls.clear()
        with patch.object(self.sup, 'observe', return_value=SimpleNamespace(missing=False, invocation_id='foreign', quiescent=False)):
            with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'probe_unit'): self.runtime.probe()
        self.assertFalse(any('exec' in x for x in self.calls))

    def test_probe_expired_budget_refuses_before_control_call(self):
        self.ready_receipt(running=True)
        with patch.object(a0.time, 'time', return_value=self.p['deadline_unix']), self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'budget_exhausted'):
            self.runtime.probe()
        self.assertEqual(self.calls, [])

    def test_no_clobber_atomic_receipt(self):
        path = self.root / 'receipt.json'; a0.write_json(path, {'old': 1})
        with self.assertRaises(FileExistsError): a0.write_json(path, {'new': 2})
        self.assertEqual(json.loads(path.read_text()), {'old': 1})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class GitMetadataControls(unittest.TestCase):
    """Real disposable Git objects; never clone/read/mount the A0 donor."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.root.chmod(0o700)
        self.patch = patch.object(a0, 'RUNTIME', self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        base = self.root / 'git-metadata'; base.mkdir(mode=0o700)
        self.stage = base / ('1' * 64); self.stage.mkdir(mode=0o700)
        self.repo = self.stage / 'repo'; self.repo.mkdir(mode=0o700)
        self.source = self.repo / '.git'
        self.env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0'}
        self.git('init', '--quiet')
        (self.repo / 'fixture.txt').write_text('real offline fixture\n')
        (self.repo / 'empty.txt').touch()
        self.git('add', 'fixture.txt', 'empty.txt')
        self.git('-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@invalid',
                 '-c', 'core.hooksPath=/dev/null', 'commit', '--quiet', '-m', 'fixture')
        commit = self.git('rev-parse', 'HEAD').strip(); tree = self.git('rev-parse', 'HEAD^{tree}').strip()
        self.git('checkout', '--detach', '--quiet', commit)
        for ref in self.git('for-each-ref', '--format=%(refname)').splitlines():
            self.git('update-ref', '-d', ref)
        (self.source / 'shallow').write_text(commit + '\n')
        for k, v in [('DONOR', commit), ('DONOR_TREE', tree), ('DONOR_DESCRIBE', commit[:7])]:
            p = patch.object(a0, k, v); p.start(); self.addCleanup(p.stop)
        self.snapshot = a0.git_metadata_snapshot(self.source)
        self.manifest = self.stage / 'metadata.json'; a0.write_json(self.manifest, self.snapshot)
        self.pin = {'source': str(self.source), 'manifest_sha256': a0.sha(self.manifest)}
        self.now = time.time()
        self.p = a0.plan(self.now, self.now + 300, assignment='git-fixture', generation=1,
                         owner_slot='astra', original_budget_seconds=300, git_metadata=self.pin)

    def git(self, *args):
        r = subprocess.run(['/usr/bin/git', '--no-optional-locks', '-C', str(self.repo), *args],
                           env=self.env, capture_output=True, text=True, timeout=5,
                           preexec_fn=lambda: os.umask(0o077))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def mounted(self, running=False):
        x = obj(self.p, running=running)
        x['Mounts'].append({'Type': 'bind', 'Source': str(self.source), 'Destination': '/a0/.git',
                            'RW': False, 'Propagation': 'rprivate'})
        return x

    def test_real_objects_manifest_read_does_not_change_index_or_metadata(self):
        a0.validate(self.p)
        self.assertEqual(self.snapshot, a0.git_metadata_snapshot(self.source))
        self.assertEqual(self.snapshot['files']['index']['sha256'], a0.sha(self.source / 'index'))
        argv = a0.create_argv(self.p)
        self.assertIn('type=bind,src=' + str(self.source) + ',dst=/a0/.git,readonly,bind-propagation=rprivate', argv)
        a0.container_checked(self.p, self.mounted(), CID)
        x = self.mounted(); x['Mounts'].reverse(); a0.container_checked(self.p, x, CID)

    def test_empty_refs_native_description_and_index_match(self):
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)'), '')
        self.assertEqual(self.git('describe', '--tags', '--always').strip(), a0.DONOR_DESCRIBE)
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}').strip(), a0.DONOR_TREE)
        self.assertEqual(self.git('write-tree').strip(), a0.DONOR_TREE)

    def test_loose_and_packed_replacements_refuse_before_sealing(self):
        (self.repo / 'fixture.txt').write_text('replacement tree\n')
        self.git('add', 'fixture.txt'); changed = self.git('write-tree').strip()
        replacement = self.git('-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@invalid',
                               'commit-tree', changed, '-m', 'replacement').strip()
        self.git('read-tree', a0.DONOR_TREE)
        self.git('update-ref', 'refs/replace/' + a0.DONOR, replacement)
        self.assertNotEqual(self.git('rev-parse', 'HEAD^{tree}').strip(), a0.DONOR_TREE)
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'external_git_metadata_reference'):
            a0.git_metadata_snapshot(self.source)
        self.git('pack-refs', '--all', '--prune')
        self.assertIn('refs/replace/', (self.source / 'packed-refs').read_text())
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_refs_changed'):
            a0.git_metadata_snapshot(self.source)

    def test_fabricated_loose_and_packed_tags_and_branch_refuse(self):
        for ref in ('refs/tags/v999.0-fixture', 'refs/heads/fabricated'):
            with self.subTest(ref=ref):
                self.git('update-ref', ref, a0.DONOR)
                if '/tags/' in ref:
                    self.assertEqual(self.git('describe', '--tags', '--always').strip(), 'v999.0-fixture')
                with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_refs_changed'):
                    a0.git_metadata_snapshot(self.source)
                self.git('pack-refs', '--all', '--prune')
                with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_refs_changed'):
                    a0.git_metadata_snapshot(self.source)
                self.git('update-ref', '-d', ref)

    def test_initial_index_content_mode_missing_extra_and_unmerged_entries_refuse(self):
        blob = self.git('rev-parse', a0.DONOR + ':fixture.txt').strip()
        for change in ('content', 'mode', 'missing', 'extra', 'unmerged'):
            with self.subTest(change=change):
                self.git('read-tree', '--reset', a0.DONOR_TREE)
                if change == 'content':
                    (self.repo / 'fixture.txt').write_text('different index\n'); self.git('add', 'fixture.txt')
                elif change == 'mode': self.git('update-index', '--chmod=+x', 'fixture.txt')
                elif change == 'missing': self.git('update-index', '--force-remove', 'fixture.txt')
                elif change == 'extra': self.git('update-index', '--add', '--cacheinfo', '100644,' + blob + ',extra')
                else:
                    self.git('update-index', '--force-remove', 'fixture.txt')
                    r = subprocess.run(['/usr/bin/git', '--no-optional-locks', '-C', str(self.repo),
                                        'update-index', '--index-info'], env=self.env,
                                       input='100644 ' + blob + ' 1\tfixture.txt\n', text=True,
                                       capture_output=True, timeout=5)
                    self.assertEqual(r.returncode, 0)
                with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_index_changed'):
                    a0.git_metadata_snapshot(self.source)

    def test_initial_index_flags_refuse_even_with_same_entries(self):
        for flag, undo in (('--assume-unchanged', '--no-assume-unchanged'),
                           ('--skip-worktree', '--no-skip-worktree')):
            with self.subTest(flag=flag):
                original = self.git('ls-files', '--stage', '-z')
                self.git('update-index', flag, 'fixture.txt')
                self.assertEqual(self.git('ls-files', '--stage', '-z'), original)
                with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_index_flags_changed'):
                    a0.git_metadata_snapshot(self.source)
                self.git('update-index', undo, 'fixture.txt')

    def test_intent_to_add_refuses_even_when_empty_blob_entries_match(self):
        original = self.git('ls-files', '--stage', '-z')
        self.git('update-index', '--force-remove', 'empty.txt')
        self.git('add', '--intent-to-add', 'empty.txt')
        self.assertEqual(self.git('ls-files', '--stage', '-z'), original)
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_index_flags_changed'):
            a0.git_metadata_snapshot(self.source)

    def test_wrong_missing_shallow_and_wrong_describe_refuse(self):
        shallow = self.source / 'shallow'; shallow.unlink()
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_shallow_changed'):
            a0.git_metadata_snapshot(self.source)
        shallow.write_text('0' * 40 + '\n')
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'git_metadata_shallow_changed'):
            a0.git_metadata_snapshot(self.source)
        shallow.write_text(a0.DONOR + '\n')
        with patch.object(a0, 'DONOR_DESCRIBE', 'fake'), self.assertRaisesRegex(
                a0.RuntimeErrorBoundary, 'git_metadata_describe_changed'):
            a0.git_metadata_snapshot(self.source)

    def test_metadata_pin_changes_plan_attempt_and_no_inventory_mount(self):
        p = a0.plan(self.now, self.now + 300, assignment='git-fixture', generation=1,
                    owner_slot='astra', original_budget_seconds=300)
        self.assertNotEqual(p['identity'], self.p['identity'])
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'inventory_git_mount'):
            a0.plan(self.now, self.now + 300, assignment='git-fixture', generation=1,
                    owner_slot='astra', original_budget_seconds=300, mode='inventory', git_metadata=self.pin)
        for changed in ({**self.pin, 'manifest_sha256': '0' * 64},
                        {**self.pin, 'source': '/home/jericho/donor/.git'}):
            with self.assertRaises(a0.RuntimeErrorBoundary):
                a0.validate({**self.p, 'git_metadata': changed})

    def test_missing_and_changed_manifest_or_bytes_refuse(self):
        self.manifest.unlink()
        with self.assertRaises(FileNotFoundError): a0.validate(self.p)
        a0.write_json(self.manifest, self.snapshot)
        (self.source / 'index').write_bytes(b'changed-index')
        with self.assertRaises(a0.RuntimeErrorBoundary): a0.validate(self.p)

    def test_wrong_head_and_wrong_tree_refuse_authentic_objects(self):
        head = self.source / 'HEAD'; saved = head.read_bytes(); head.write_text('0' * 40 + '\n')
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'head_or_index'): a0.git_metadata_snapshot(self.source)
        head.write_bytes(saved)
        with patch.object(a0, 'DONOR_TREE', '0' * 40), self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'object_identity'):
            a0.git_metadata_snapshot(self.source)

    def test_missing_objects_refuse_before_mount(self):
        target = next(x for x in (self.source / 'objects').rglob('*') if x.is_file())
        target.unlink()
        with self.assertRaises(a0.RuntimeErrorBoundary): a0.validate(self.p)

    def test_valid_but_wrong_blob_contents_fail_real_object_hash_check(self):
        oid = self.git('hash-object', 'fixture.txt').strip()
        p = self.source / 'objects' / oid[:2] / oid[2:]
        p.chmod(0o600); p.write_bytes(zlib.compress(b'blob 8\0forged!\n'))
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'objects_invalid'):
            a0.git_metadata_snapshot(self.source)

    def test_pointer_symlink_alternates_and_hardlink_refuse(self):
        for rel in ('commondir', 'gitdir', 'objects/info/alternates', 'objects/info/http-alternates', 'info/grafts'):
            p = self.source / rel; p.parent.mkdir(mode=0o700, exist_ok=True); p.write_text('/foreign\n'); p.chmod(0o600)
            with self.subTest(rel=rel), self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'external_git'):
                a0.git_metadata_snapshot(self.source)
            p.unlink()
        p = self.source / 'linked'; p.symlink_to(self.source / 'HEAD')
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'unsafe_git'): a0.git_metadata_snapshot(self.source)
        p.unlink(); os.link(self.source / 'HEAD', p)
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'sharing'): a0.git_metadata_snapshot(self.source)
        p.unlink()
        renamed = self.repo / 'saved'; self.source.rename(renamed)
        self.source.write_text('gitdir: /foreign\n')
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'pointer'): a0.git_metadata_snapshot(self.source)

    def test_external_git_config_is_rejected_before_git_reads(self):
        with (self.source / 'config').open('a') as f: f.write('[include]\n path = /foreign/private\n')
        with patch.object(a0.subprocess, 'run') as run, self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'config_changed'):
            a0.git_metadata_snapshot(self.source)
        run.assert_not_called()

    def test_rw_extra_foreign_and_duplicate_mounts_refuse_both_admission_and_stop(self):
        for change in (lambda x: x['Mounts'][1].update(RW=True),
                       lambda x: x['Mounts'][1].update(Source='/foreign/.git'),
                       lambda x: x['Mounts'][1].update(Propagation='rshared'),
                       lambda x: x['Mounts'][1].update(Destination='/a0/usr'),
                       lambda x: x['Mounts'].append({'Type': 'bind', 'Destination': '/extra'}),
                       lambda x: x['Mounts'].pop()):
            x = self.mounted(); change(x)
            for stopping in (False, True):
                with self.subTest(change=change, stopping=stopping), self.assertRaises(a0.RuntimeErrorBoundary):
                    a0.container_checked(self.p, x, CID, stop_owned=stopping)

    def test_owned_stop_keeps_mount_identity_without_reading_drifted_metadata(self):
        directory = self.root / self.p['identity']; directory.mkdir(mode=0o700)
        r = {'plan_sha256': a0.digest(self.p), 'container_id': CID, 'invocation_id': INV, 'observations': []}
        a0.write_json(directory / 'native.json', r)
        self.manifest.unlink()
        x = self.mounted(); x['HostConfig'].update(Memory=1, MemorySwap=-1, PidsLimit=1, NanoCpus=1)
        calls = []
        def runner(argv, timeout):
            calls.append(argv)
            if 'inspect' in argv: return json.dumps([x])
            self.fail('Already stopped container must not be stopped again')
        sup = Supervisor(); runtime = a0.Runtime(self.p, runner=runner, supervisor=sup, stopping=True)
        self.assertEqual(runtime.stop()['status'], 'STOP_CONFIRMED')
        self.assertEqual(len(sup.stops), 1)
        x['Mounts'][1]['RW'] = True
        sup.stops.clear()
        with self.assertRaises(a0.RuntimeErrorBoundary): runtime.stop()
        self.assertEqual(sup.stops, [])


class NativeProbeControls(unittest.TestCase):
    """Native dependency doubles certify offline refusal/selection, not live A0."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.root.chmod(0o700)
        self.usr = self.root / 'usr'; a0.materialize(self.usr)
        self.preset = a0.templates()['plugins/_model_config/presets.yaml'][0]
        self.cfg = {slot + '_model': copy.deepcopy(self.preset[slot]) for slot in ('chat', 'utility', 'embedding')}
        self.cfg.update(model_preset='Default', vision_model={}, allow_chat_override=True)
        self.calls = []; self.keys = {'openai': 'test-only-chat', 'other': 'test-only-embedding'}
        self.configured = 'Default'; self.selected_path = self.usr / 'plugins/_model_config/config.json'
        def build(cfg, typ):
            return SimpleNamespace(provider=cfg['provider'], name=cfg['name'], api_base=cfg['api_base'],
                                   api_key=cfg.get('api_key', ''), ctx_length=cfg.get('ctx_length', 0),
                                   vision=cfg.get('vision', False), limit_requests=cfg.get('rl_requests', 0),
                                   limit_input=cfg.get('rl_input', 0), limit_output=cfg.get('rl_output', 0),
                                   kwargs=copy.deepcopy(cfg['kwargs']))
        def config(**kw):
            self.calls.append(kw); return self.cfg
        self.native = SimpleNamespace(get_config=config, get_configured_preset_name=lambda **kw: self.configured,
                                      build_model_config=build)
        self.provider = lambda typ, provider: {'litellm_provider': 'openai',
                                             'kwargs': {} if typ == 'embedding' else {'a0_api_mode': 'chat'}}
        helpers = ModuleType('helpers'); helpers.__path__ = []
        helpers.plugins = SimpleNamespace(find_plugin_asset=lambda *a, **kw: {'path': str(self.selected_path)})
        helpers.providers = SimpleNamespace(get_provider_config=lambda *a: self.provider(*a))
        self.tokens = SimpleNamespace(count_tokens=lambda text: 12, approximate_tokens=lambda text: 13)
        helpers.tokens = self.tokens
        models = ModuleType('models'); models.ModelType = SimpleNamespace(CHAT='chat', EMBEDDING='embedding')
        models.get_api_key = lambda provider: self.keys[provider]
        def forbidden(*a, **kw): self.fail('No-model probe tried to construct/call a model')
        models.get_chat_model = models.get_embedding_model = models.unified_call = forbidden
        plugin = ModuleType('plugins'); plugin.__path__ = []
        mc = ModuleType('plugins._model_config'); mc.__path__ = []
        mch = ModuleType('plugins._model_config.helpers'); mch.model_config = self.native
        self.module_patch = patch.dict(sys.modules, {'helpers': helpers, 'models': models, 'plugins': plugin,
             'plugins._model_config': mc, 'plugins._model_config.helpers': mch})
        self.module_patch.start(); self.addCleanup(self.module_patch.stop)
        self.path = patch.object(a0, 'Path', side_effect=lambda *a: self.usr if a == ('/a0/usr',) else Path(*a))
        self.path.start(); self.addCleanup(self.path.stop)

    def test_selected_native_slots_and_separate_keys_sanitized(self):
        report = a0.probe_report_checked(a0.native_probe())
        self.assertEqual(self.calls, [{'agent_profile': 'agent0', 'project_name': None}])
        self.assertEqual(report['slots']['chat']['max_tokens'], 4096)
        self.assertEqual(report['slots']['embedding']['transport_provider'], 'openai')
        self.assertFalse(report['hard_total_prompt_bound'])
        for value in self.keys.values(): self.assertNotIn(value, json.dumps(report))

    def test_missing_malformed_presets_and_wrong_raw_selection_refuse_before_resolution(self):
        p = self.usr / 'plugins/_model_config/presets.yaml'; saved = p.read_bytes()
        selection = self.usr / 'plugins/_model_config/config.json'; original = selection.read_bytes()
        selection.write_text('{"model_preset":"Foreign"}')
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'native_input'): a0.native_probe()
        self.assertEqual(self.calls, [])
        selection.write_bytes(original)
        for contents in (b'[]', b'[{}]', b'{', b'[{"name":"Foreign"}]'):
            p.write_bytes(contents)
            with self.assertRaises((a0.RuntimeErrorBoundary, json.JSONDecodeError)): a0.native_probe()
            self.assertEqual(self.calls, [])
        p.write_bytes(saved); p.unlink()
        with self.assertRaises(a0.RuntimeErrorBoundary): a0.native_probe()

    def test_missing_slot_cannot_accept_native_fallback(self):
        p = self.usr / 'plugins/_model_config/presets.yaml'
        raw = copy.deepcopy([self.preset]); del raw[0]['embedding']; p.write_text(json.dumps(raw))
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'native_input'): a0.native_probe()
        self.assertEqual(self.calls, [])

    def test_profile_override_and_foreign_resolved_preset_refuse(self):
        self.selected_path = self.usr / 'agents/agent0/plugins/_model_config/config.json'
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'scope_override'): a0.native_probe()
        self.selected_path = self.usr / 'plugins/_model_config/config.json'
        self.configured = 'Foreign'
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'preset_or_override'): a0.native_probe()

    def test_wrong_route_model_output_context_and_vision_refuse(self):
        original = copy.deepcopy(self.cfg)
        for slot, field, value in [('chat','provider','other'), ('utility','name','cloud'),
                                  ('embedding','api_base','https://foreign.invalid/v1'),
                                  ('chat','ctx_length',81920), ('chat','kwargs',{'max_tokens':8192}),
                                  ('chat','ctx_history',1), ('utility','ctx_input',0.9),
                                  ('chat','api_key','test-only-inline-secret')]:
            self.cfg = copy.deepcopy(original); self.cfg[slot + '_model'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'slot_changed'):
                a0.native_probe()
        self.cfg = copy.deepcopy(original); self.cfg['vision_model'] = {'name': 'foreign'}
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'preset_or_override'): a0.native_probe()

    def test_missing_embedding_key_does_not_fall_back_to_ready_chat_key(self):
        for provider in ('other', 'openai'):
            old = self.keys[provider]
            for missing in ('', 'None', 'NA', ' '):
                self.keys[provider] = missing
                with self.subTest(provider=provider, missing=missing), self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'distinct_key'):
                    a0.native_probe()
            self.keys[provider] = old

    def test_provider_mapping_and_constructor_drift_refuse(self):
        old = self.provider
        self.provider = lambda *a: {'litellm_provider': 'foreign'}
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'provider_mapping'): a0.native_probe()
        self.provider = old
        build = self.native.build_model_config
        def changed(cfg, typ):
            value = build(cfg, typ); value.ctx_length += 1; return value
        self.native.build_model_config = changed
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'constructed_slot'): a0.native_probe()

    def test_token_cache_failure_has_categorical_error_no_network_retry(self):
        called = []
        def uncached(text):
            called.append(text); raise RuntimeError('test-only-secret raw token URL')
        self.tokens.count_tokens = uncached
        with self.assertRaisesRegex(a0.RuntimeErrorBoundary, '^native_token_cache_unavailable$'):
            a0.native_probe()
        self.assertEqual(len(called), 1)

    def test_report_unknown_fields_or_wrong_selected_output_are_not_exported(self):
        report = a0.native_probe()
        for damage in (lambda x: x.update(kwargs={'api_key': 'test-only-secret'}),
                       lambda x: x['slots']['chat'].update(max_tokens=8192),
                       lambda x: x['key_ready'].update(other=False),
                       lambda x: x.update(hard_total_prompt_bound=True)):
            value = copy.deepcopy(report); damage(value)
            with self.assertRaisesRegex(a0.RuntimeErrorBoundary, 'report_changed'): a0.probe_report_checked(value)

    def test_standalone_script_same_functions_suppresses_native_prints_and_raw_errors(self):
        # Execute the exact generated functions with dependency doubles and only
        # the fixed container Path translated to the owned test directory.
        script = a0.probe_script(); body, tail = script.rsplit('try:\n print(json.dumps(native_probe(DEPLOYMENT)', 1)
        namespace = {}; exec(compile(body, '<native-probe>', 'exec'), namespace)
        namespace['Path'] = lambda *a: self.usr if a == ('/a0/usr',) else Path(*a)
        original = self.native.get_config
        def noisy(**kw):
            print('test-only-secret-native-log'); return original(**kw)
        self.native.get_config = noisy
        out = io.StringIO()
        with patch('sys.stdout', out):
            exec('try:\n print(json.dumps(native_probe()' + tail, namespace)
        self.assertNotIn('test-only-secret', out.getvalue())
        a0.probe_report_checked(json.loads(out.getvalue()))
        self.tokens.count_tokens = lambda text: (_ for _ in ()).throw(RuntimeError('test-only-secret'))
        out = io.StringIO()
        with patch('sys.stdout', out): exec('try:\n print(json.dumps(native_probe()' + tail, namespace)
        self.assertEqual(json.loads(out.getvalue()), {'status': 'REFUSED', 'code': 'native_token_cache_unavailable'})


if __name__ == '__main__':
    unittest.main()
