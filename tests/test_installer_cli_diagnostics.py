"""Public CLI refusal across a real helper import, without install effects."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def isolated_installer_modules():
    original_umask = os.umask(0o077)
    try:
        with patch.dict(sys.modules):
            # Reuse no scripts package object: imports also set attributes on
            # its parent, which restoring sys.modules alone cannot undo.
            for name in tuple(sys.modules):
                if name == 'scripts' or name.startswith('scripts.'):
                    del sys.modules[name]
            yield
    finally:
        os.umask(original_umask)


class InstallerCliDiagnostics(unittest.TestCase):
    def invoke(self, value, *, foreign_module=False):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_text(json.dumps(value))
            source.chmod(0o600)
            stdout, stderr = io.StringIO(), io.StringIO()
            with isolated_installer_modules(), patch.object(sys, 'path', list(sys.path)), patch.object(sys, 'argv', [
                    str(ROOT / 'scripts/friday_install.py'), 'plan', '--input', str(source)]), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                if foreign_module:
                    foreign = types.ModuleType('scripts.friday_install')
                    sys.modules['scripts.friday_install'] = foreign
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(ROOT / 'scripts/friday_install.py'), run_name='__main__')
                if foreign_module:
                    self.assertIs(sys.modules['scripts.friday_install'], foreign)
            self.assertEqual(result.exception.code, 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(list(Path(directory).iterdir()), [source])
            return stderr.getvalue()

    def test_helper_refusal_keeps_its_public_reason(self):
        # references() imports require from scripts.friday_install. This fails
        # before any home, executable, donor, worker or credential-value read.
        value = dict.fromkeys(('home', 'bootstrap_python', 'hermes_donor',
            'hermes_prepare', 'sources_lock', 'dsh_donor', 'a0_donor', 'product',
            'project_files', 'containment'))
        value.update(seconds=30, credential_sources={})
        self.assertEqual(self.invoke(value),
            'Friday entry refused: phase=plan reason=explicit_credential_references_required\n')

    def test_frontend_refusal_still_masks_arbitrary_input(self):
        self.assertEqual(self.invoke({'seconds': 30, 'private-value': 'DO_NOT_ECHO'}),
            'Friday entry refused: phase=plan reason=explicit_install_fields_required\n')

    def test_foreign_canonical_module_is_not_replaced(self):
        self.assertEqual(self.invoke({}, foreign_module=True),
            'Friday entry refused: phase=entry reason=installer_module_identity_conflict\n')

    def test_preloaded_package_and_umask_are_restored(self):
        with isolated_installer_modules(), patch.object(sys, 'path', [str(ROOT), *sys.path]):
            import scripts
            import scripts.friday_install as entry
            package_attributes = dict(vars(scripts))
            namespace = {name: module for name, module in sys.modules.items()
                         if name == 'scripts' or name.startswith('scripts.')}
            os.umask(0o022)
            self.test_helper_refusal_keeps_its_public_reason()
            self.assertEqual(os.umask(0o022), 0o022)
            self.assertEqual(vars(scripts), package_attributes)
            self.assertEqual({name: module for name, module in sys.modules.items()
                              if name == 'scripts' or name.startswith('scripts.')}, namespace)
            from scripts import dsh_prepare
            self.assertEqual(entry.safe_diagnostic(dsh_prepare.StopUnconfirmed(), 'plan')['reason'],
                             'stop_unconfirmed')
            self.assertIs(dsh_prepare, sys.modules['scripts.dsh_prepare'])


if __name__ == '__main__':
    unittest.main()
