"""Public HTTP/Git delta controls on neutral files and responses; no native effects."""
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from test_a0_web_startup import web, runtime, web_plan


class HttpConfigControls(unittest.TestCase):
    def http_probe(self, response=None, error=None):
        tree = ast.parse(web.service_probe(web_plan()))
        guard = next(node for node in tree.body if isinstance(node, ast.Try))
        body = guard.body[0].body
        start = next(i for i, node in enumerate(body) if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant) and node.value.value == 'http_config')
        # Run the original HTTP section, categorical exception handler and output.
        guard.body = body[start:]
        response = response or {'status': 200, 'raw': json.dumps(
            {'version': 'offline-version', 'engines': [{'name': 'google'}]}).encode()}
        class Reply:
            status = response['status']
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, bound):
                self_test.assertEqual(bound, 65537)
                return response['raw']
        self_test = self
        output = io.StringIO()
        with patch('urllib.request.urlopen', side_effect=error, return_value=Reply()) as request:
            with contextlib.redirect_stdout(output):
                exec(compile(ast.fix_missing_locations(tree), '<actual-http-section>', 'exec'),
                    {'expected': web_plan(), 'rows': []})
        request.assert_called_once_with('http://127.0.0.1:55510/config', timeout=2)
        return json.loads(output.getvalue())

    def test_http_success_and_every_precise_failure_phase(self):
        self.assertEqual(self.http_probe()['status'], 'CURRENT_NATIVE_WEB_SERVICE_CHECKED')
        cases = [('http_status', {'status': 503, 'raw': b'{}'}),
            ('http_body_bound', {'status': 200, 'raw': b'x' * 65537}),
            ('http_json', {'status': 200, 'raw': b'{' }),
            ('http_version', {'status': 200, 'raw': b'{"version":"wrong"}'}),
            ('http_engines', {'status': 200,
                'raw': b'{"version":"offline-version","engines":[{"name":"foreign"}]}'} )]
        for phase, response in cases:
            with self.subTest(phase=phase):
                failure = self.http_probe(response)
                self.assertEqual(failure['phase'], phase)
                self.assertEqual(runtime.web_probe_failure_checked(failure), failure)
                self.assertEqual(set(failure), {'status', 'phase', 'error_class'})
        failure = self.http_probe(error=OSError('private-sentinel'))
        self.assertEqual(failure['phase'], 'http_config')
        self.assertNotIn('private-sentinel', str(failure))

    def test_real_http_error_keeps_request_phase_without_status_or_body(self):
        error = urllib.error.HTTPError('http://127.0.0.1:55510/config', 503,
            'PRIVATE_MESSAGE_SENTINEL', {}, io.BytesIO(b'PRIVATE_BODY_SENTINEL'))
        try:
            failure = self.http_probe(error=error)
        finally:
            error.close()
        self.assertEqual(failure, {'status': 'NATIVE_WEB_PROBE_REFUSED',
            'phase': 'http_config', 'error_class': 'OSError'})
        self.assertEqual(runtime.web_probe_failure_checked(failure), failure)
        self.assertNotIn('503', str(failure))
        self.assertNotIn('PRIVATE_', str(failure))

    def git_fixture(self, root, *, etc_mode=0o775):
        git_data = b'[safe]\n\tdirectory = /usr/local/searxng/searxng-src\n'
        paths = {name: root / name.lstrip('/') for name in (
            '/a0', '/a0/usr', '/a0/usr/web/gitconfig', '/etc', '/etc/gitconfig',
            '/usr/local/searxng/searxng-src/searx/version.py')}
        for path in paths.values(): path.parent.mkdir(parents=True, exist_ok=True)
        for directory in root.rglob('*'):
            if directory.is_dir(): directory.chmod(0o700)
        # Match the reviewed image's /etc metadata before its bounded
        # normalization; all effects still target this neutral temporary tree.
        paths['/etc'].chmod(etc_mode)
        paths['/a0/usr/web/gitconfig'].write_bytes(git_data)
        paths['/a0/usr/web/gitconfig'].chmod(0o600)
        version = paths['/usr/local/searxng/searxng-src/searx/version.py']
        version.write_bytes(b'neutral version fixture')
        donor = root / 'neutral-donor'; donor.write_bytes(b'neutral donor')
        pins = {str(donor): hashlib.sha256(donor.read_bytes()).hexdigest()}
        with (patch.object(web, 'checked_web', return_value={
                  'source_pins': pins,
                  'image': 'sha256:6b300a0a4341632f021fb1b5d2641296ff4882ba7636e228f57c58bc9105c4f8'}),
              patch.object(web, '_install_native_overlays', return_value='')):
            source = web.install_script({})
        self.assertIn("hashlib.sha256(version_path.read_bytes()).hexdigest()=='eb975f55c2041e150412cbf5f4f2d7da60dea9e24a37e349e2b3cefc1932cfa0'", source)
        stage = 'WEB_SOURCE_PINS=' + source.split('\nWEB_SOURCE_PINS=', 1)[1]
        class NeutralPaths(ast.NodeTransformer):
            def visit_Constant(self, node):
                if isinstance(node.value, str) and node.value in paths:
                    return ast.copy_location(ast.Constant(str(paths[node.value])), node)
                if node.value == 'eb975f55c2041e150412cbf5f4f2d7da60dea9e24a37e349e2b3cefc1932cfa0':
                    return ast.copy_location(ast.Constant(hashlib.sha256(b'neutral version fixture').hexdigest()), node)
                return node
            def visit_Compare(self, node):
                self.generic_visit(node)
                if isinstance(node.left, ast.Attribute) and node.left.attr in {'st_uid', 'st_gid'}:
                    assert len(node.comparators) == 1 and node.comparators[0].value == 0
                    owner = os.geteuid() if node.left.attr == 'st_uid' else os.getegid()
                    node.comparators[0] = ast.copy_location(ast.Constant(owner), node.comparators[0])
                return node
        code = compile(ast.fix_missing_locations(NeutralPaths().visit(ast.parse(stage))), '<actual-git-stage-neutral-paths>', 'exec')
        def check(ok):
            if not ok: raise RuntimeError('native_web_overlay_refused')
        namespace = {'Path': Path, 'os': os, 'stat': stat, 'hashlib': hashlib, 'check': check}
        return code, namespace, paths, git_data, donor

    def test_git_exact_config_mode_and_no_overwrite(self):
        self.assertEqual(web.service_files(web_plan())['web/gitconfig'],
            '[safe]\n\tdirectory = /usr/local/searxng/searxng-src\n')
        for etc_mode in (0o755, 0o775):
            with self.subTest(etc_mode=oct(etc_mode)), tempfile.TemporaryDirectory() as tmp:
                code, namespace, paths, expected, _ = self.git_fixture(Path(tmp), etc_mode=etc_mode)
                original = paths['/etc'].stat()
                exec(code, namespace)
                current = paths['/etc'].stat()
                self.assertEqual((current.st_dev, current.st_ino), (original.st_dev, original.st_ino))
                self.assertEqual(stat.S_IMODE(current.st_mode), 0o755)
                target = paths['/etc/gitconfig']
                self.assertEqual(target.read_bytes(), expected)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                with self.assertRaises(FileExistsError): exec(code, namespace)
                self.assertEqual(target.read_bytes(), expected)

    def test_git_rejects_changed_inputs_and_unsafe_paths_before_target_write(self):
        for fault in ('config', 'config-mode', 'config-link', 'parent-mode', 'version', 'donor',
                      'target-link', 'etc-private-mode', 'etc-world-write', 'etc-link'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                code, namespace, paths, _, donor = self.git_fixture(Path(tmp))
                source, target = paths['/a0/usr/web/gitconfig'], paths['/etc/gitconfig']
                if fault == 'config': source.write_bytes(b'[safe]\n directory = *\n')
                elif fault == 'config-mode': source.chmod(0o644)
                elif fault == 'config-link':
                    held = source.with_name('held'); source.rename(held); source.symlink_to(held)
                elif fault == 'parent-mode': source.parent.chmod(0o777)
                elif fault == 'version': paths['/usr/local/searxng/searxng-src/searx/version.py'].write_bytes(b'changed')
                elif fault == 'donor': donor.write_bytes(b'changed')
                elif fault == 'etc-private-mode': paths['/etc'].chmod(0o700)
                elif fault == 'etc-world-write': paths['/etc'].chmod(0o777)
                elif fault == 'etc-link':
                    held = paths['/etc'].with_name('held-etc')
                    paths['/etc'].rename(held); paths['/etc'].symlink_to(held, target_is_directory=True)
                else: target.symlink_to(donor)
                with self.assertRaises((RuntimeError, FileExistsError, OSError)): exec(code, namespace)
                if fault != 'target-link': self.assertFalse(target.exists())
                else: self.assertEqual(donor.read_bytes(), b'neutral donor')


if __name__ == '__main__': unittest.main()
