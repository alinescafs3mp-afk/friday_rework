"""Real owned-file primitives on seven neutral files; no native admission.

The exact public primitive ASTs are extracted without importing the installer.
Only its small file-read/require API is supplied by this isolated fixture.
"""
import ast
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest


ROOT = Path(os.environ.get('FRIDAY_PUBLIC_SOURCE_ROOT',
    str(Path(__file__).resolve().parents[1])))
ORDINARY = ROOT / 'scripts/friday_ordinary_install.py'
NAMES = ('worker-runtime-source/plugins/friday_rework/adapters/a0_web.py',
    'worker-runtime-source/scripts/a0_runtime.py', 'config.yaml',
    'profiles/neutral/config.yaml', 'profiles/neutral/.friday-onboarding.json',
    'profiles/neutral/.friday-user-scope.json', '.native-marker.json')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def owned_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid()
            and s.st_nlink == 1, 'fixture_owned_regular_required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def primitives():
    tree = ast.parse(ORDINARY.read_bytes())
    names = {'SourceUpdateDirectories', 'update_file_state_at',
        'update_file_state', 'same_update_file', 'publish_update_file',
        'restore_update_files', 'sync_directory'}
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
        and n.name in names]
    require({n.name for n in nodes} == names, 'fixture_primitive_set_changed')
    api = types.SimpleNamespace(require=require, owned_file=owned_file)
    env = {'os': os, 'Path': Path, 'stat': stat, 'api': lambda: api}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ORDINARY), 'exec'), env)
    return types.SimpleNamespace(**{n: env[n] for n in names})


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = primitives()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='friday-neutral-seven-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.home.chmod(0o700)
        self.before = {}
        for i, name in enumerate(NAMES):
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            for parent in path.parents:
                if parent == self.home.parent:
                    break
                parent.chmod(0o700)
            path.write_bytes(('neutral-before-' + str(i)).encode())
            path.chmod(0o400 if i == 0 else 0o600)
            self.before[name] = self.p.update_file_state(path)

    def publish(self, directories, count=7):
        owned = {}
        for name in NAMES[:count]:
            self.p.publish_update_file(self.home / name, b'neutral-after',
                self.before[name]['mode'], self.before[name], owned, name,
                parent_fd=directories.parent_fd(name))
        return owned

    def test_each_seven_file_prefix_restores_exact_bytes_and_modes(self):
        for count in range(1, 8):
            with self.subTest(published=count):
                with self.p.SourceUpdateDirectories(self.home, NAMES, []) as d:
                    owned = self.publish(d, count)
                    for name in NAMES[:count]:
                        self.assertEqual(self.p.update_file_state(self.home / name,
                            d.parent_fd(name)), owned[name])
                    self.p.restore_update_files(self.home, self.before, owned, d)
                    d.prove()
                for name in NAMES:
                    current = self.p.update_file_state(self.home / name)
                    self.assertEqual(current['data'], self.before[name]['data'])
                    self.assertEqual(current['mode'], self.before[name]['mode'])
                # Rollback creates new owned inodes, so retain their identity
                # for the next independent prefix within this fixture.
                self.before = {n: self.p.update_file_state(self.home / n) for n in NAMES}

    def test_foreign_identity_or_mode_refuses_before_any_rollback(self):
        for damage in ('inode', 'bytes', 'mode', 'symlink'):
            with self.subTest(damage=damage):
                # Independent fixture per damage, retaining every failed state.
                with tempfile.TemporaryDirectory(prefix='neutral-damage-') as tmp:
                    h = Path(tmp)
                    names = ('one', 'two')
                    for n in names:
                        (h / n).write_bytes(b'before'); (h / n).chmod(0o600)
                    saved = {n: self.p.update_file_state(h / n) for n in names}
                    with self.p.SourceUpdateDirectories(h, names, []) as d:
                        owned = {}
                        for n in names:
                            self.p.publish_update_file(h / n, b'after', 0o600,
                                saved[n], owned, n, parent_fd=d.parent_fd(n))
                        p = h / 'one'
                        if damage == 'inode':
                            q = h / 'foreign'; q.write_bytes(b'after'); q.chmod(0o600)
                            os.replace(q, p)
                        elif damage == 'bytes':
                            p.write_bytes(b'foreign')
                        elif damage == 'mode':
                            p.chmod(0o400)
                        else:
                            p.rename(h / 'foreign'); p.symlink_to(h / 'foreign')
                        before_two = self.p.update_file_state(h / 'two')
                        with self.assertRaises((ValueError, OSError)):
                            self.p.restore_update_files(h, saved, owned, d)
                        self.assertEqual(self.p.update_file_state(h / 'two'), before_two)

    def test_replaced_parent_is_detected_and_cannot_redirect_publication(self):
        with self.p.SourceUpdateDirectories(self.home, NAMES, []) as d:
            parent = self.home / 'worker-runtime-source/scripts'
            saved = parent.with_name('scripts-held')
            parent.rename(saved)
            foreign = self.home / 'foreign'
            foreign.mkdir(mode=0o700)
            (foreign / 'a0_runtime.py').write_bytes(b'foreign')
            parent.symlink_to(foreign, target_is_directory=True)
            with self.assertRaises((ValueError, OSError)):
                d.prove()
            self.assertEqual((foreign / 'a0_runtime.py').read_bytes(), b'foreign')


if __name__ == '__main__':
    unittest.main(verbosity=1)
