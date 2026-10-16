"""Real guard with isolated file/metadata seams; no root policy or execution."""
import hashlib
import importlib
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest
import test_dsh_adapter as fixture

dsh = importlib.import_module('friday_dsh_adapter_test.adapters.dsh')
NODE_SHA = '3517c2df0b2f8cd7f422b4b8450ef81c6889f08eb03e281d6de9079b15e6a327'


@pytest.fixture
def guard(tmp_path, monkeypatch):
    files = {}
    refs = []
    for number, (name, _) in enumerate(dsh._APPARMOR_FILES):
        path = tmp_path/str(number)
        data = b'isolated host input '+str(number).encode()
        path.write_bytes(data)
        path.chmod(0o755)
        class Input:
            def __init__(self, path):
                self.path = path
                self.uid = 0
                self.nlink = 1
                self.mode = stat.S_IFREG | 0o755
                self.canonical = True
                self.missing = False
            def lstat(self):
                if self.missing:
                    raise FileNotFoundError('synthetic missing file')
                return SimpleNamespace(st_uid=self.uid, st_nlink=self.nlink, st_mode=self.mode)
            def resolve(self):
                return self if self.canonical else object()
            def read_bytes(self):
                return self.path.read_bytes()
        files[name] = Input(path)
        refs.append((name, hashlib.sha256(data).hexdigest()))
    monkeypatch.setattr(dsh, '_APPARMOR_FILES', tuple(refs))
    monkeypatch.setattr(dsh, 'Path', lambda name: files[name])
    config = SimpleNamespace(node=SimpleNamespace(path=dsh._APPARMOR_NODE, sha256=NODE_SHA))
    return config, files


def test_guard_only_replaces_outer_executable_and_preserves_every_argument(guard):
    config, _ = guard
    argv = ['/usr/bin/bwrap', '--cap-drop', 'ALL', '--unshare-user', '--', '/usr/bin/python3.14', '-I']
    assert dsh._apparmor_boundary(config, argv) == [dsh._APPARMOR_ENTRY, *argv[1:]]
    assert argv[0] == '/usr/bin/bwrap'


@pytest.mark.parametrize('index', range(4))
@pytest.mark.parametrize('fault', ['uid','nlink','write','symlink','type','digest','missing'])
def test_each_guard_input_rejects_foreign_identity_and_bytes(guard, index, fault):
    config, files = guard
    target = list(files.values())[index]
    if fault == 'uid': target.uid = 1000
    elif fault == 'nlink': target.nlink = 2
    elif fault == 'write': target.mode |= 0o020
    elif fault == 'symlink': target.canonical = False
    elif fault == 'type': target.mode = stat.S_IFDIR | 0o755
    elif fault == 'digest': target.path.write_bytes(b'foreign afterimage')
    else: target.missing = True
    with pytest.raises(dsh.AdapterError, match='apparmor_host_input_(changed|missing)'):
        dsh._apparmor_boundary(config, ['/usr/bin/bwrap', '--', 'fixture'])


@pytest.mark.parametrize('fault', ['node_path','node_sha','empty_outer','foreign_outer'])
def test_guard_rejects_node_and_outer_entry_drift(guard, fault):
    config, _ = guard
    argv = ['/usr/bin/bwrap', '--', 'fixture']
    if fault == 'node_path': config.node.path = Path('/synthetic/foreign/node')
    elif fault == 'node_sha': config.node.sha256 = '0'*64
    elif fault == 'empty_outer': argv = []
    else: argv[0] = '/synthetic/foreign/bwrap'
    with pytest.raises(dsh.AdapterError, match='apparmor_(native_node|outer_entry)_changed'):
        dsh._apparmor_boundary(config, argv)
