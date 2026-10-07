"""Real local Git source/patch composition; no donor code or services execute."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import time
import unittest

M = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/hermes_prepare.py'))
sha = M['sha']


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.donor = self.root / 'donor'; self.donor.mkdir()
        self.repo = self.root / 'product'; self.repo.mkdir()
        self.patches = self.repo / 'patches/hermes'; self.patches.mkdir(parents=True)
        self.dest = self.root / 'composed'
        self.git('init', '-q')
        self.git('remote', 'add', 'origin', 'https://github.com/NousResearch/hermes-agent.git')
        (self.donor / 'base.txt').write_text('original\n')
        (self.donor / 'untouched.txt').write_text('preserve complete donor\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid', 'commit', '-qm', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        tree = self.git('rev-parse', 'HEAD^{tree}').strip()
        self.lock = {'repositories': [{'id': 'hermes', 'commit': self.commit, 'tree': tree,
                                     'clone_url': 'https://github.com/NousResearch/hermes-agent.git'}]}
        self.save_lock()
        self.first = self.layer('z-first', 'original', 'changed')
        self.second = self.layer('a-second', 'changed', 'final',
                                 {'z-first.patch': self.first['patch_sha256']})

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(self.donor), *args],
                                       env=dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull),
                                       stderr=subprocess.PIPE, text=True, timeout=5)

    def save_lock(self):
        (self.repo / 'sources.lock.json').write_text(json.dumps(self.lock))

    def layer(self, name, before, after, requires=None):
        patch = (f'diff --git a/base.txt b/base.txt\n--- a/base.txt\n+++ b/base.txt\n'
                 f'@@ -1 +1 @@\n-{before}\n+{after}\n').encode()
        (self.patches / (name + '.patch')).write_bytes(patch)
        body = {'base_commit': self.commit, 'patch_file': name + '.patch', 'patch_sha256': sha(patch),
                'prerequisites': requires or {},
                'expected_base_files': {'base.txt': {'sha256': sha((before + '\n').encode())}},
                'expected_patched_files': {'base.txt': {'sha256': sha((after + '\n').encode()),
                                                      'bytes': len(after) + 1}}}
        self.save_layer(name, body)
        return body

    def save_layer(self, name, body):
        (self.patches / (name + '.json')).write_text(json.dumps(body))

    def prepare(self):
        return M['compose'](self.repo, self.donor, self.dest, seconds=10)

    def refuse(self, reason):
        with self.assertRaisesRegex(M['Refused'], '^' + reason + '$'):
            self.prepare()

    def test_complete_export_and_dependency_order_without_donor_changes(self):
        (self.donor / '.env').write_text('UNTRACKED_FIXTURE_DO_NOT_COPY=yes\n')
        before = self.git('status', '--porcelain=v1')
        result = self.prepare()
        self.assertEqual((self.dest / 'base.txt').read_text(), 'final\n')
        self.assertEqual((self.dest / 'untouched.txt').read_text(), 'preserve complete donor\n')
        self.assertFalse((self.dest / '.env').exists())
        self.assertFalse((self.dest / '.git').exists())
        self.assertEqual(result['source_file_count'], 2)
        self.assertEqual(result['layers'][0]['manifest'], 'patches/hermes/z-first.json')
        self.assertEqual(self.git('status', '--porcelain=v1'), before)
        self.assertEqual((self.donor / 'base.txt').read_text(), 'original\n')

    def test_existing_destination_never_adopted(self):
        self.dest.mkdir(); (self.dest / 'owner.txt').write_text('owner')
        self.refuse('fresh_destination_required')
        self.assertEqual((self.dest / 'owner.txt').read_text(), 'owner')

    def test_declared_crlf_checkout_exports_canonical_git_bytes(self):
        (self.donor / '.gitattributes').write_text('script.ps1 text eol=crlf\n')
        (self.donor / 'script.ps1').write_bytes(b'Write-Output fixture\r\n')
        self.git('add', '.gitattributes', 'script.ps1')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid', 'commit', '-qm', 'CRLF fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.lock['repositories'][0].update(commit=self.commit, tree=self.git('rev-parse', 'HEAD^{tree}').strip())
        self.save_lock()
        for name, body in (('z-first', self.first), ('a-second', self.second)):
            body['base_commit'] = self.commit
            self.save_layer(name, body)
        self.prepare()
        self.assertEqual((self.dest / 'script.ps1').read_bytes(), b'Write-Output fixture\n')
        self.assertEqual((self.donor / 'script.ps1').read_bytes(), b'Write-Output fixture\r\n')

    def test_unmanifested_layer_cannot_be_silently_omitted(self):
        (self.patches / 'forgotten.patch').write_text('unlisted')
        self.refuse('unmanifested_overlay'); self.assertFalse(self.dest.exists())

    def test_changed_patch_refused_before_export(self):
        (self.patches / 'z-first.patch').write_text('changed')
        self.refuse('overlay_hash_mismatch'); self.assertFalse(self.dest.exists())

    def test_missing_dependency_refused(self):
        self.second['prerequisites'] = {'missing.patch': '0' * 64}
        self.save_layer('a-second', self.second)
        self.refuse('overlay_prerequisite_mismatch')

    def test_dependency_cycle_refused(self):
        self.first['prerequisites'] = {'a-second.patch': self.second['patch_sha256']}
        self.save_layer('z-first', self.first)
        self.refuse('overlay_dependency_cycle')

    def test_unlisted_patch_target_refused(self):
        self.first['expected_patched_files']['extra.txt'] = {'sha256': '0' * 64, 'bytes': 0}
        self.save_layer('z-first', self.first)
        self.refuse('overlay_file_inventory_mismatch')

    def test_wrong_output_digest_cannot_produce_receipt(self):
        self.second['expected_patched_files']['base.txt']['sha256'] = '0' * 64
        self.save_layer('a-second', self.second)
        self.refuse('overlay_output_mismatch')
        self.assertTrue(self.dest.exists())  # retained partial output, never reused

    def test_wrong_before_digest_refused(self):
        self.first['expected_base_files']['base.txt']['sha256'] = '0' * 64
        self.save_layer('z-first', self.first)
        self.refuse('overlay_input_changed')
        self.assertEqual((self.dest / 'base.txt').read_text(), 'original\n')

    def test_dirty_owner_source_is_preserved_and_refused(self):
        (self.donor / 'base.txt').write_text('owner change\n')
        self.refuse('dirty_donor_refused')
        self.assertEqual((self.donor / 'base.txt').read_text(), 'owner change\n')
        self.assertFalse(self.dest.exists())

    def test_symlinked_donor_input_refused(self):
        alias = self.root / 'alias'; alias.symlink_to(self.donor, target_is_directory=True)
        with self.assertRaisesRegex(M['Refused'], 'canonical_donor_required'):
            M['compose'](self.repo, alias, self.dest)

    def test_duplicate_manifest_keys_refused(self):
        (self.patches / 'z-first.json').write_text('{"base_commit":"x","base_commit":"y"}')
        self.refuse('duplicate_json_key')

    def test_path_and_original_deadline_controls(self):
        for path in ('../escape', '.git/config', '/outside', '.', 'a//b', 'a/../b'):
            with self.subTest(path=path), self.assertRaises(M['Refused']): M['relative'](path)
        with self.assertRaisesRegex(M['Refused'], 'source_preparation_deadline'):
            M['Budget'](time.monotonic() - 1).remaining()


if __name__ == '__main__':
    unittest.main()
