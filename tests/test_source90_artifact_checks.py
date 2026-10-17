"""Disposable pure-input regressions; no product state or provider calls."""
import hashlib
import importlib.util
import marshal
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'validation/source90_artifact_checks.py'
SPEC = importlib.util.spec_from_file_location('source90_artifact_checks', SOURCE)
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)


class Source90ArtifactChecks(unittest.TestCase):
    def setUp(self):
        self.raw = b'raise RuntimeError("must never execute")\n'
        self.name = '/synthetic/source.py'
        code = compile(self.raw, self.name, 'exec', dont_inherit=True, optimize=0)
        self.payload = marshal.dumps(code, marshal.version)
        self.files = {'a.py': {'bytes': len(self.raw),
                               'sha256': hashlib.sha256(self.raw).hexdigest(),
                               'mode': '100644'}}

    def check(self, expected=0o600, actual=0o600):
        return CHECKS.check_source_inventory(
            self.files, {'a.py': expected}, lambda _: (self.raw, actual))

    def test_compiled_body_matches_without_executing_source(self):
        self.assertTrue(CHECKS.source_compiled_payload_matches(
            self.raw, self.name, self.payload))

    def test_owning_and_temporary_serializations_match(self):
        holder = [compile(self.raw, self.name, 'exec', dont_inherit=True, optimize=0)]
        for payload in (marshal.dumps(holder[0], marshal.version),
                        marshal.dumps(compile(self.raw, self.name, 'exec',
                                      dont_inherit=True, optimize=0), marshal.version)):
            self.assertTrue(CHECKS.source_compiled_payload_matches(
                self.raw, self.name, payload))

    def test_other_source_and_filename_refused(self):
        self.assertFalse(CHECKS.source_compiled_payload_matches(
            b'pass\n', self.name, self.payload))
        self.assertFalse(CHECKS.source_compiled_payload_matches(
            self.raw, '/synthetic/other.py', self.payload))

    def test_prefix_suffix_and_truncated_payloads_refused(self):
        for payload in (b'x' + self.payload, self.payload + b'x', self.payload[:-1]):
            self.assertFalse(CHECKS.source_compiled_payload_matches(
                self.raw, self.name, payload))

    def test_nonexecutable_private_and_public_modes_match(self):
        self.assertTrue(self.check())
        self.assertTrue(self.check(0o644, 0o644))

    def test_executable_mode_matches(self):
        self.files['a.py']['mode'] = '100755'
        self.assertTrue(self.check(0o755, 0o755))

    def test_mode_drift_refused_even_without_execute_bit_change(self):
        with self.assertRaisesRegex(ValueError, '^source_mode_changed$'):
            self.check(0o600, 0o644)

    def test_execute_bit_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError, '^observed_git_executable_mismatch$'):
            self.check(0o755, 0o755)

    def test_changed_source_bytes_refused(self):
        self.files['a.py']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '^source_bytes_changed$'):
            self.check()

    def test_missing_mode_extra_mode_and_boolean_mode_refused(self):
        for modes in ({}, {'a.py': 0o600, 'extra': 0o600}, {'a.py': True}):
            with self.assertRaises(ValueError):
                CHECKS.check_source_inventory(self.files, modes,
                                              lambda _: (self.raw, 0o600))

    def test_unsafe_relative_name_refused_before_reader(self):
        for name in ('/absolute.py', '../escape.py', 'a/../escape.py', './a.py',
                     '', '.', 'a\x00.py'):
            with self.assertRaisesRegex(ValueError, '^canonical_relative_name_required$'):
                CHECKS.check_source_inventory(
                    {name: self.files['a.py']}, {name: 0o600},
                    lambda _: self.fail('reader must remain unused'))


if __name__ == '__main__':
    unittest.main()
