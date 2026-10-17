"""Bind accepted Source89/90 bytes to the preserved public Source88 prefix.

These tests check publication source identity. They issue no runtime authority.
Normal hermes_prepare composition separately verifies all final native files.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'patches/hermes/ordinary-exact-response-manifest.json'
PREFIX_SHA = '6773522b77f93015c125f28b183e45f255a684095f4518c1e2d00e516771ef31'
LAYERS = [{'manifest': 'patches/hermes/ordinary-web-stop-pm-source-refresh-manifest.json', 'patch': 'patches/hermes/ordinary-web-stop-pm-source-refresh.patch', 'patch_sha256': 'f0b0ff689504988f7be8fe021c3d420016c73ca085e853ccebf107c20c0d897a', 'files_sha256': '9da69a3887e10508fa73b952aa23f1d917613b64718589ac7fed1f46ac23aa1e', 'prefix_count': 88}, {'manifest': 'patches/hermes/ordinary-coherent-memory-skills-source90-manifest.json', 'patch': 'patches/hermes/ordinary-coherent-memory-skills-source90.patch', 'patch_sha256': '4f4bc66c38670127d3cd8903351fa06e717b67acb9d7093019e61e0cddeb0ea8', 'files_sha256': '1f84f5859ad7966f10f09d1a629d2a7ab4b80a71e6c87c8859f3df5ba5b58cbc', 'prefix_count': 89}]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def certify_source_layers(root, manifests=None, patches=None):
    def require(value, reason):
        if not value:
            raise ValueError(reason)

    source = (root / PREFIX).read_bytes()
    require(digest(source) == PREFIX_SHA, 'prefix_identity')
    previous = json.loads(source)
    prefix = {**previous['installed_prefix'], PREFIX: PREFIX_SHA}
    prerequisites = {**previous['prerequisites'], previous['patch']: previous['patch_sha256']}
    require(len(prefix) == len(prerequisites) == 88, 'prefix_inventory')
    require(all(digest((root / name).read_bytes()) == pin for name, pin in prefix.items()),
            'prefix_source_bytes')
    require(all(digest((root / name).read_bytes()) == pin for name, pin in prerequisites.items()),
            'prefix_patch_bytes')
    for pin in LAYERS:
        manifest = (manifests[pin['manifest']] if manifests is not None
                    else json.loads((root / pin['manifest']).read_text()))
        patch = (patches[pin['patch']] if patches is not None
                 else (root / pin['patch']).read_bytes())
        require(set(manifest) == {'base_commit', 'files', 'installed_prefix', 'patch',
                                  'patch_sha256', 'prerequisites'}, 'manifest_fields')
        require(manifest['base_commit'] == '781334eea4b9225a3e194faf0c241d9afe218634',
                'base_commit')
        require(len(prefix) == len(prerequisites) == pin['prefix_count'], 'prefix_inventory')
        require(manifest['installed_prefix'] == prefix, 'prefix_hashes')
        require(manifest['prerequisites'] == prerequisites, 'prerequisite_hashes')
        require(manifest['patch'] == pin['patch'] and
                manifest['patch_sha256'] == digest(patch) == pin['patch_sha256'], 'patch_identity')
        require(digest(canonical(manifest['files'])) == pin['files_sha256'], 'native_body_pins')
        prefix = {**prefix, pin['manifest']: digest((root / pin['manifest']).read_bytes())}
        prerequisites = {**prerequisites, pin['patch']: pin['patch_sha256']}
    return True


class Source89And90IdentityTests(unittest.TestCase):
    def setUp(self):
        self.manifests = {row['manifest']: json.loads((ROOT / row['manifest']).read_text())
                          for row in LAYERS}
        self.patches = {row['patch']: (ROOT / row['patch']).read_bytes() for row in LAYERS}

    def check(self):
        return certify_source_layers(ROOT, self.manifests, self.patches)

    def assert_refused(self, reason):
        with self.assertRaisesRegex(ValueError, '^' + reason + '$'):
            self.check()

    def test_accepted_patches_body_pins_and_complete_public_chain(self):
        self.assertTrue(self.check())

    def test_each_wrong_prefix_hash_refused(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                body = self.manifests[layer['manifest']]
                body['installed_prefix'][next(iter(body['installed_prefix']))] = '0' * 64
                self.assert_refused('prefix_hashes')

    def test_each_missing_prefix_manifest_refused(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                body = self.manifests[layer['manifest']]
                body['installed_prefix'].pop(next(iter(body['installed_prefix'])))
                self.assert_refused('prefix_hashes')

    def test_each_wrong_prerequisite_refused(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                body = self.manifests[layer['manifest']]
                body['prerequisites'][next(iter(body['prerequisites']))] = '0' * 64
                self.assert_refused('prerequisite_hashes')

    def test_each_patch_and_manifest_repin_cannot_replace_accepted_patch(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                self.patches[layer['patch']] += b'\n'
                self.manifests[layer['manifest']]['patch_sha256'] = digest(self.patches[layer['patch']])
                self.assert_refused('patch_identity')

    def test_each_changed_beforeimage_refused(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                self.manifests[layer['manifest']]['files'][0]['before_sha256'] = '0' * 64
                self.assert_refused('native_body_pins')

    def test_each_changed_mode_refused(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                self.manifests[layer['manifest']]['files'][0]['mode'] = '100755'
                self.assert_refused('native_body_pins')

    def test_each_added_body_refused(self):
        for layer in LAYERS:
            with self.subTest(layer=layer['manifest']):
                self.setUp()
                body = self.manifests[layer['manifest']]
                body['files'].append(copy.deepcopy(body['files'][0]))
                self.assert_refused('native_body_pins')

    def test_wrong_base_commit_refused(self):
        self.manifests[LAYERS[0]['manifest']]['base_commit'] = '0' * 40
        self.assert_refused('base_commit')

    def test_runtime_binding_field_refused(self):
        self.manifests[LAYERS[1]['manifest']]['runtime_binding'] = 'synthetic-forbidden-field'
        self.assert_refused('manifest_fields')


if __name__ == '__main__':
    unittest.main()
