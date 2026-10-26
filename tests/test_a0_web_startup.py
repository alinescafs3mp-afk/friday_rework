"""Offline web startup/receipt controls; no Docker, services or external network.

Run: python3 -B -m unittest discover -s tests -p test_a0_web_startup.py -v
The Unix XMLRPC test uses one temporary local IPC socket and fixed neutral rows.
"""
import ast
import contextlib
import copy
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import xmlrpc.client

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


web = load('offline_web_startup', 'plugins/friday_rework/adapters/a0_web.py')
runtime = load('offline_web_runtime', 'scripts/a0_runtime.py')


def web_plan():
    return {'profile': 'searxng-google', 'timeout_seconds': 7,
            'dns': ['1.1.1.1'], 'version': 'offline-version',
            'image': 'sha256:' + 'a' * 64,
            'source_pins': {
                '/exe/run_searxng.sh': 'a' * 64,
                '/usr/local/searxng/searxng-src/searx/webapp.py': 'b' * 64,
                '/usr/local/searxng/searxng-src/searx/settings_loader.py': 'c' * 64,
                '/a0/helpers/searxng.py': '4020eca255497dbf95076166ebefaff14a095abafaff69cb6176a8ae31c2fcc2',
                '/a0/tools/search_engine.py': 'c13c14560d0ac1947b63ed1ad795bd2fad5e026673d2cc615f34ef6da57a9efb'}}


FAILURE = {'status': 'NATIVE_WEB_PROBE_REFUSED', 'phase': 'supervisor',
           'error_class': 'ModuleNotFoundError'}


class WebStartup(unittest.TestCase):
    def test_real_overlay_payloads_match_existing_reviewed_pins(self):
        self.assertEqual(len(web.NATIVE_WEB_OVERLAYS), 2)
        for name, size, before, after, text in web.NATIVE_WEB_OVERLAYS:
            self.assertIn(name, web_plan()['source_pins'])
            self.assertEqual(after, web_plan()['source_pins'][name])
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), after)
            self.assertNotEqual(before, after)
            self.assertGreater(size, 0)
            compile(text, name, 'exec')
        compile(web.install_script(web_plan()), '<overlay-installer>', 'exec')
        compile(web.service_probe(web_plan()), '<service-probe>', 'exec')

    def test_no_web_startup_stays_exact_and_web_installs_before_supervision(self):
        self.assertEqual(runtime.startup_script({}), runtime.START_SCRIPT)
        with patch.object(runtime, 'web_module', return_value=web):
            command = runtime.startup_script({'web': web_plan()})
        self.assertEqual(command.count('. /ins/copy_A0.sh; '), 1)
        self.assertEqual(command.count(' || exit $?; '), 1)
        self.assertLess(command.index('native_web_overlay_refused'),
                        command.index('exec /usr/bin/supervisord'))

    def test_changed_copy_boundary_refuses(self):
        for script in ('printf SUPERVISOR', '. /ins/copy_A0.sh; . /ins/copy_A0.sh; '):
            fake = types.SimpleNamespace(START_SCRIPT=script, install_script=lambda _: 'pass')
            with self.subTest(script=script), patch.object(runtime, 'web_module', return_value=fake):
                with self.assertRaises(runtime.RuntimeErrorBoundary):
                    runtime.startup_script({'web': {}})

    def test_real_shell_without_errexit_never_supervises_after_installer_failure(self):
        fake = types.SimpleNamespace(START_SCRIPT='. /ins/copy_A0.sh; printf SUPERVISOR')
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'python').symlink_to(sys.executable)
            for code, rc, output in [("print('INSTALL');raise SystemExit(41)", 41, 'INSTALL\n'),
                                     ("print('INSTALL')", 0, 'INSTALL\nSUPERVISOR')]:
                fake.install_script = lambda _, code=code: code
                with patch.object(runtime, 'web_module', return_value=fake):
                    script = runtime.startup_script({'web': {}})
                # Only the absolute image copy seam is replaced by a neutral shell no-op.
                script = script.replace('. /ins/copy_A0.sh; ', ':; ', 1)
                result = subprocess.run(['/bin/bash', '-c', script],
                                        env={'PATH': tmp, 'LC_ALL': 'C'},
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (rc, output, ''))

    def fixture(self, root):
        rows = []
        for index in range(2):
            path = root / ('file' + str(index) + '.py')
            old = ('original_' + str(index) + ' = True\n').encode()
            new = 'replacement_' + str(index) + ' = True\n'
            path.write_bytes(old)
            path.chmod(0o640)
            rows.append((str(path), len(old), hashlib.sha256(old).hexdigest(),
                         hashlib.sha256(new.encode()).hexdigest(), new))
        return tuple(rows)

    def installer(self, rows):
        # The generated installer is unchanged; only its two data rows point to
        # neutral owned files. Exact production payload hashes are checked above.
        with patch.object(web, 'NATIVE_WEB_OVERLAYS', rows), patch.object(web, 'checked_web',
                return_value={'source_pins': {row[0]: row[3] for row in rows}}):
            return compile(web._install_native_overlays({}), '<neutral-installer>', 'exec')

    def test_installer_exact_preimages_atomic_outputs_modes_and_no_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self.fixture(root)
            code = self.installer(rows)
            exec(code, {})
            for name, _, _, after, _ in rows:
                self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), after)
                self.assertEqual(stat.S_IMODE(Path(name).stat().st_mode), 0o640)
            self.assertFalse(list(root.glob('.friday-web-*')))
            with self.assertRaisesRegex(RuntimeError, 'native_web_overlay_refused'):
                exec(code, {})

    def test_second_preimage_drift_prevents_every_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self.fixture(Path(tmp))
            original = Path(rows[0][0]).read_bytes()
            Path(rows[1][0]).write_bytes(b'foreign')
            with self.assertRaisesRegex(RuntimeError, 'native_web_overlay_refused'):
                exec(self.installer(rows), {})
            self.assertEqual(Path(rows[0][0]).read_bytes(), original)
            self.assertFalse(list(Path(tmp).glob('.friday-web-*')))

    def test_symlink_and_wrong_payload_digest_refuse_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self.fixture(root)
            path = Path(rows[0][0])
            path.rename(root / 'original')
            path.symlink_to(root / 'original')
            with self.assertRaises(RuntimeError):
                exec(self.installer(rows), {})
            path.unlink()
            path.write_bytes((root / 'original').read_bytes())
            changed = (rows[0][:-1] + ('unreviewed = True\n',), rows[1])
            with self.assertRaises(RuntimeError):
                exec(self.installer(changed), {})
            self.assertEqual(path.read_bytes(), (root / 'original').read_bytes())

    def test_missing_secret_exports_only_categorical_failure(self):
        output = io.StringIO()
        with (patch('pathlib.Path.read_text', side_effect=FileNotFoundError('SECRET_SENTINEL')),
              contextlib.redirect_stdout(output)):
            exec(compile(web.service_probe(web_plan()), '<probe>', 'exec'), {})
        self.assertEqual(json.loads(output.getvalue()),
                         {'status': 'NATIVE_WEB_PROBE_REFUSED', 'phase': 'secret',
                          'error_class': 'FileNotFoundError'})
        self.assertNotIn('SECRET_SENTINEL', output.getvalue())

    def test_category_validator_rejects_unbounded_or_untyped_evidence(self):
        self.assertEqual(runtime.web_probe_failure_checked(FAILURE), FAILURE)
        for delta in ({'phase': []}, {'phase': 'foreign'}, {'error_class': 'SECRET_SENTINEL'},
                      {'status': 'CURRENT_NATIVE_WEB_SERVICE_CHECKED'}, {'message': 'SECRET_SENTINEL'}):
            with self.subTest(delta=delta), self.assertRaises(runtime.RuntimeErrorBoundary):
                runtime.web_probe_failure_checked(dict(FAILURE, **delta))

    def receipt_runtime(self, root):
        instance = runtime.Runtime.__new__(runtime.Runtime)
        now = time.time()
        instance.p = {'state_dir': str(root / 'usr'), 'web': web_plan(),
                      'accepted_unix': now, 'deadline_unix': now + 300,
                      'original_budget_seconds': 300}
        instance.receipt_path = root / 'native.json'
        instance.directory = root
        instance.known = {'plan_sha256': runtime.digest(instance.p),
                          'container_id': 'a' * 64, 'invocation_id': 'b' * 32,
                          'observations': [{'retained': True}]}
        runtime.write_json(instance.receipt_path, instance.known)
        return instance

    def test_failure_survives_stale_memory_and_retains_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = self.receipt_runtime(Path(tmp))
            latest = copy.deepcopy(instance.known)
            latest['observations'].append({'new': True})
            latest['web_probe_failure'] = dict(FAILURE)
            runtime.write_json(instance.receipt_path, latest, replace=True)
            merged = instance.durable_receipt()
            self.assertEqual(merged['observations'], latest['observations'])
            self.assertEqual(merged['web_probe_failure'], FAILURE)
            self.assertEqual(instance.durable_receipt(), merged)

    def test_receipt_foreign_identity_or_changed_failure_refuses(self):
        for delta in ({'container_id': 'c' * 64}, {'plan_sha256': 'c' * 64},
                      {'invocation_id': 'c' * 32},
                      {'web_probe_failure': dict(FAILURE, phase='settings')},
                      {'web_probe_failure': dict(FAILURE, message='SECRET_SENTINEL')}):
            with tempfile.TemporaryDirectory() as tmp:
                instance = self.receipt_runtime(Path(tmp))
                instance.known['web_probe_failure'] = dict(FAILURE)
                latest = dict(copy.deepcopy(instance.known), **delta)
                runtime.write_json(instance.receipt_path, latest, replace=True)
                with self.subTest(delta=delta), self.assertRaises(runtime.RuntimeErrorBoundary):
                    instance.durable_receipt()

    def test_host_refuses_persists_failure_and_never_sets_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = self.receipt_runtime(root)
            for relative, value in web.service_files(web_plan()).items():
                path = root / 'usr' / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value if isinstance(value, str) else json.dumps(value))
            instance.check_network = lambda **kw: None
            instance.docker = lambda *args, **kw: json.dumps(FAILURE)
            instance.locked = contextlib.nullcontext
            with patch.object(runtime, 'web_module', return_value=web):
                with self.assertRaisesRegex(runtime.RuntimeErrorBoundary,
                        'a0_native_web_probe_supervisor_ModuleNotFoundError'):
                    instance.check_web('a' * 64)
            self.assertEqual(json.loads(instance.receipt_path.read_text())['web_probe_failure'], FAILURE)
            self.assertFalse(hasattr(instance, 'web_observation'))

    def test_stdlib_transport_real_neutral_unix_xmlrpc(self):
        tree = ast.parse(web.service_probe(web_plan()))
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
                   and node.name in ('UnixHTTPConnection', 'UnixTransport')]
        self.assertEqual(len(classes), 2)
        rows = [{'name': 'run_ui', 'pid': 11, 'start': 12, 'statename': 'RUNNING'},
                {'name': 'run_searxng', 'pid': 13, 'start': 14, 'statename': 'RUNNING'}]
        payload = xmlrpc.client.dumps((rows,), methodresponse=True).encode()
        requests, connects, timeouts, errors = [], [], [], []
        with tempfile.TemporaryDirectory() as tmp:
            endpoint = str(Path(tmp) / 'rpc.sock')
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.settimeout(2)
            server.bind(endpoint)
            server.listen(1)

            def serve():
                try:
                    with server.accept()[0] as conn:
                        conn.settimeout(2)
                        data = b''
                        while b'\r\n\r\n' not in data:
                            data += conn.recv(4096)
                        headers, body = data.split(b'\r\n\r\n', 1)
                        length = int(next(line.split(b':', 1)[1] for line in headers.split(b'\r\n')
                                          if line.lower().startswith(b'content-length:')))
                        while len(body) < length:
                            body += conn.recv(4096)
                        requests.append(headers + b'\r\n\r\n' + body)
                        conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\nContent-Length: '
                                     + str(len(payload)).encode() + b'\r\nConnection: close\r\n\r\n' + payload)
                except BaseException as exc:
                    errors.append(type(exc).__name__)

            class ClientSocket:
                def __init__(self, family, kind):
                    self.sock = socket.socket(family, kind)
                def settimeout(self, value):
                    timeouts.append(value)
                    self.sock.settimeout(value)
                def connect(self, value):
                    connects.append(value)
                    if value != '/var/run/friday-supervisor.sock':
                        raise AssertionError('unexpected endpoint')
                    self.sock.connect(endpoint)
                def __getattr__(self, name):
                    return getattr(self.sock, name)

            namespace = {'http': types.SimpleNamespace(client=http.client),
                         'xmlrpc': types.SimpleNamespace(client=xmlrpc.client),
                         'socket': types.SimpleNamespace(AF_UNIX=socket.AF_UNIX,
                                   SOCK_STREAM=socket.SOCK_STREAM, socket=ClientSocket)}
            exec(compile(ast.Module(body=classes, type_ignores=[]), '<actual-transport>', 'exec'), namespace)
            worker = threading.Thread(target=serve)
            worker.start()
            try:
                with xmlrpc.client.ServerProxy('http://127.0.0.1',
                        transport=namespace['UnixTransport']()) as proxy:
                    self.assertEqual(proxy.supervisor.getAllProcessInfo(), rows)
            finally:
                worker.join(3)
                server.close()
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(connects, ['/var/run/friday-supervisor.sock'])
            self.assertEqual(timeouts, [2])
            self.assertIn(b'POST /RPC2', requests[0])
            self.assertIn(b'supervisor.getAllProcessInfo', requests[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
