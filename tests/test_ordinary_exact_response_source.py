"""Source88 publication identity and prefix controls, without runtime effects.

The public prefix has different intermediate bytes from the private deployment
prefix. Its final composition must be compared separately with the accepted
source receipt. These tests certify source inputs only, never deployment.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'patches/hermes/ordinary-exact-response-manifest.json'
PATCH = 'patches/hermes/ordinary-exact-response.patch'
PATCH_SHA = '3c8df6c5eb99aa97dea6f4622bd389adccbbcaff63c282243f7c759f9fe2e880'
PREFIX = 'patches/hermes/ordinary-bot-principal-manifest.json'
PREFIX_SHA = 'd124ae40a6c5ce30831f8c16eab6080cefd223bd783e3fe9345746ab164879ee'
BODIES = {
    'agent/onboarding.py': {
        'before_sha256': 'c7953d740dc399713bb8eb6a7c8faec3a87f3efec9463639ac273c5c6675f9cd',
        'sha256': 'd492d64d2258b5952b8f28904fabaf098485841f25fddc49ad02c89a4ca10e6f',
        'bytes': 13458, 'mode': '100644', 'new_file': False,
    },
    'hermes_cli/friday_prompt_scope.py': {
        'before_sha256': '274a8edeaf895db5e8cc24f9deeb7832b2c830acadeff7151002cbc7a7be8a3c',
        'sha256': '438e20d5d8922a218ca2eb69ef4822dcd9f2cc1af41ee98885b3dae04fe37702',
        'bytes': 18067, 'mode': '100644', 'new_file': False,
    },
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def certify_source_inputs(root, manifest, patch):
    def require(value, reason):
        if not value:
            raise ValueError(reason)

    # Bind the immutable Source87 prefix. Later additive layers do not alter
    # this certificate or require changing the Source88 body pins.
    prefix_bytes = (root / PREFIX).read_bytes()
    require(digest(prefix_bytes) == PREFIX_SHA, 'prefix_identity')
    prefix = json.loads(prefix_bytes)
    expected_prefix = {**prefix['installed_prefix'], PREFIX: PREFIX_SHA}
    expected_patches = {**prefix['prerequisites'], prefix['patch']: prefix['patch_sha256']}
    require(len(expected_prefix) == len(expected_patches) == 87, 'prefix_inventory')
    require(all(digest((root / name).read_bytes()) == pin
                for name, pin in expected_prefix.items()), 'prefix_source_bytes')
    require(all(digest((root / name).read_bytes()) == pin
                for name, pin in expected_patches.items()), 'prefix_patch_bytes')
    require(manifest['installed_prefix'] == expected_prefix, 'prefix_hashes')
    require(manifest['prerequisites'] == expected_patches, 'prerequisite_hashes')
    require(manifest['base_commit'] == '781334eea4b9225a3e194faf0c241d9afe218634', 'base_commit')
    require(manifest['patch'] == PATCH and manifest['patch_sha256'] == digest(patch) == PATCH_SHA,
            'patch_hash')
    rows = manifest['files']
    require(len(rows) == 2 and {r['path'] for r in rows} == set(BODIES), 'body_inventory')
    for row in rows:
        require(row == {'path': row['path'], **BODIES[row['path']]}, 'body_identity')
    targets = re.findall(rb'^--- a/(\S+)\n\+\+\+ b/(\S+)$', patch, flags=re.MULTILINE)
    require(len(targets) == 2 and all(a == b for a, b in targets)
            and {b.decode() for a, b in targets} == set(BODIES), 'patch_inventory')
    return True


class ExactResponseSourceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / MANIFEST).read_text())
        self.patch = (ROOT / PATCH).read_bytes()

    def check(self):
        return certify_source_inputs(ROOT, self.manifest, self.patch)

    def test_public_prefix_and_exact_two_bodies(self):
        self.assertTrue(self.check())

    def test_wrong_prefix_hash_refused(self):
        key = next(iter(self.manifest['installed_prefix']))
        self.manifest['installed_prefix'][key] = '0' * 64
        with self.assertRaisesRegex(ValueError, '^prefix_hashes$'):
            self.check()

    def test_missing_prefix_refused(self):
        self.manifest['installed_prefix'].pop(next(iter(self.manifest['installed_prefix'])))
        with self.assertRaisesRegex(ValueError, '^prefix_hashes$'):
            self.check()

    def test_wrong_prerequisite_hash_refused(self):
        key = next(iter(self.manifest['prerequisites']))
        self.manifest['prerequisites'][key] = '0' * 64
        with self.assertRaisesRegex(ValueError, '^prerequisite_hashes$'):
            self.check()

    def test_changed_patch_refused(self):
        self.patch += b'\n'
        with self.assertRaisesRegex(ValueError, '^patch_hash$'):
            self.check()

    def test_patch_and_manifest_repin_cannot_replace_reviewed_patch(self):
        self.patch += b'\n'
        self.manifest['patch_sha256'] = digest(self.patch)
        with self.assertRaisesRegex(ValueError, '^patch_hash$'):
            self.check()

    def test_changed_beforeimage_refused(self):
        self.manifest['files'][0]['before_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '^body_identity$'):
            self.check()

    def test_added_body_refused(self):
        self.manifest['files'].append(copy.deepcopy(self.manifest['files'][0]))
        with self.assertRaisesRegex(ValueError, '^body_inventory$'):
            self.check()

    def test_changed_mode_refused(self):
        self.manifest['files'][0]['mode'] = '100755'
        with self.assertRaisesRegex(ValueError, '^body_identity$'):
            self.check()


if __name__ == '__main__':
    unittest.main()
