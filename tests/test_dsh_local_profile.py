import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/render_dsh_local.py"
spec = importlib.util.spec_from_file_location("dsh_profile_renderer", SCRIPT)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class DshLocalProfile(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(purpose="temporary-local-test", api="openai-completions",
                           base_url="http://127.0.0.1:8011/v1", model="fixture-local",
                           context_window=40960, max_tokens=4096,
                           summary_max_tokens=2048, headroom_tokens=4096)

    def test_explicit_route_and_all_independent_rows(self):
        patch = renderer.build_patch(**self.inputs)
        self.assertEqual(len({r['id'] for r in patch}), len(patch))
        route = patch[0]['config']['providers']
        self.assertEqual(set(route), {'friday-local'})
        self.assertNotIn('apiKeyEnv', route['friday-local'])
        self.assertEqual(patch[1]['config'], dict(provider='friday-local', model='fixture-local'))
        self.assertEqual({r['id'] for r in patch[3:]}, set(renderer.DISABLED_ROWS))
        self.assertTrue(all(r['disabled'] is True for r in patch[3:]))
        self.assertEqual(patch[2]['config'], dict(summarizationProvider='friday-local',
                         summarizationModel='fixture-local', maxTokens=2048, headroomTokens=4096))

    def test_capacity_is_explicit_and_not_a_permanent_40960_default(self):
        patch = renderer.build_patch(**dict(self.inputs, context_window=131072, max_tokens=8192))
        model = patch[0]['config']['providers']['friday-local']['models'][0]
        self.assertEqual((model['contextWindow'], model['maxTokens']), (131072, 8192))
        with self.assertRaises(TypeError):
            renderer.build_patch(**{k:v for k,v in self.inputs.items() if k != 'context_window'})

    def test_invalid_capacity_protocol_purpose_and_credential(self):
        for delta in ({'context_window': True}, {'max_tokens': 0}, {'max_tokens': 40960},
                      {'max_tokens': -1}, {'context_window': '40960'},
                      {'request_timeout_ms': 0}, {'summary_max_tokens': 5000},
                      {'headroom_tokens': 40000}, {'api': 'openai-responses'},
                      {'purpose': 'production'}, {'api_key_env': 'a secret'},
                      {'api_key_env': '${API_KEY}'}, {'api_key_env': 'HOME'}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                renderer.build_patch(**dict(self.inputs, **delta))

    def test_public_ambiguous_and_secret_bearing_endpoint_rejects(self):
        for url in ('https://api.openai.com/v1', 'http://8.8.8.8:8011/v1',
                    'http://0.0.0.0:8011/v1', 'http://user:canary@127.0.0.1:8011/v1',
                    'http://127.0.0.1:8011/v1?key=canary', 'http://127.0.0.1:8011/v1#x',
                    'http://127.0.0.1/v1', 'http://127.0.0.1:8011/v1\n',
                    'http://127.0.0.1:8011/../v1', 'http://127.0.0.1:8011/%76%31',
                    'http://127.0.0.1:8011/v1\\x', 'http://localhost:8011/v1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                renderer.build_patch(**dict(self.inputs, base_url=url))

    def test_invalid_or_dynamic_model_rejects(self):
        for model in ('', ' fixture', 'auto', '${MODEL}', 'REPLACE_WITH_MODEL', 'x\n', 'x\x00'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                renderer.build_patch(**dict(self.inputs, model=model))

    def test_inputs_are_independent(self):
        first = renderer.build_patch(**self.inputs)
        original = copy.deepcopy(first)
        renderer.build_patch(**dict(self.inputs, model='second'))
        self.assertEqual(first, original)

    def test_native_retention_must_fit_below_pressure_including_boundary(self):
        # Native retain=floor((40960-4096)*.16)=5898, pressure=36864-headroom.
        valid = renderer.build_patch(**dict(self.inputs, headroom_tokens=30965))
        self.assertEqual(valid[2]['config']['headroomTokens'], 30965)
        for headroom in (30966, 36000):
            with self.subTest(headroom=headroom), self.assertRaises(ValueError):
                renderer.build_patch(**dict(self.inputs, headroom_tokens=headroom))

    def test_atomic_private_file_and_existing_destinations_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'local.patch.yml'
            patch = renderer.build_patch(**self.inputs)
            renderer.publish_private(path, patch)
            before = path.read_bytes()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(json.loads(before), patch)
            with self.assertRaises(FileExistsError):
                renderer.publish_private(path, [])
            self.assertEqual(path.read_bytes(), before)
            link = Path(root)/'link.yml'
            link.symlink_to(path)
            with self.assertRaises(FileExistsError):
                renderer.publish_private(link, [])
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(list(Path(root).glob('.dsh-profile-*')))

    def test_public_or_symlinked_output_parent_rejects(self):
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root)/'public'; parent.mkdir(mode=0o755)
            # The negative control must be public even under a private umask.
            parent.chmod(0o755)
            with self.assertRaises(ValueError):
                renderer.publish_private(parent/'x', [])
            parent.chmod(0o700)
            alias = Path(root)/'alias'; alias.symlink_to(parent)
            with self.assertRaises(ValueError):
                renderer.publish_private(alias/'x', [])

    def test_cli_does_not_read_or_serialize_credentials_or_bad_values(self):
        with tempfile.TemporaryDirectory() as root:
            argv = [sys.executable, '-B', str(SCRIPT), '--purpose', self.inputs['purpose'],
                    '--api', self.inputs['api'], '--base-url', self.inputs['base_url'],
                    '--model', self.inputs['model'], '--context-window', '40960',
                    '--max-tokens', '4096', '--api-key-env', 'FRIDAY_FIXTURE_API_KEY',
                    '--summary-max-tokens', '2048', '--headroom-tokens', '4096',
                    '--output', str(Path(root)/'patch.yml')]
            env = dict(os.environ, FRIDAY_FIXTURE_API_KEY='SECRET_CANARY_NOT_SERIALIZED')
            ok = subprocess.run(argv, env=env, capture_output=True, timeout=10)
            self.assertEqual(ok.returncode, 0)
            combined = ok.stdout + ok.stderr + (Path(root)/'patch.yml').read_bytes()
            self.assertNotIn(b'SECRET_CANARY_NOT_SERIALIZED', combined)
            invalid = subprocess.run(argv + ['--unknown', 'SECRET_CANARY_NOT_SERIALIZED'],
                                     env=env, capture_output=True, timeout=10)
            self.assertEqual(invalid.returncode, 2)
            self.assertNotIn(b'SECRET_CANARY_NOT_SERIALIZED', invalid.stdout + invalid.stderr)
            repeat = subprocess.run(argv + ['--model', 'second'], env=env,
                                    capture_output=True, timeout=10)
            self.assertEqual(repeat.returncode, 2)


if __name__ == '__main__':
    unittest.main()
