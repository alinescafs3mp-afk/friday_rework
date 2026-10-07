"""Real bounded file reads, no executable is launched."""
import hashlib
import os

import pytest

from scripts import friday_install as install


def binary(tmp_path, size):
    path = tmp_path / 'owned-python'
    with path.open('wb') as stream:
        stream.truncate(size)
    path.chmod(0o700)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return path, {'path': str(path), 'sha256': digest}


def test_large_native_python_pin_streams_without_expanding_document_limit(tmp_path, monkeypatch):
    path, pin = binary(tmp_path, 65 * 1024**2)
    reads = []; original = os.read
    def bounded(fd, size):
        reads.append(size)
        return original(fd, size)
    monkeypatch.setattr(os, 'read', bounded)
    assert install.bootstrap_pin(pin) == path
    assert reads and max(reads) <= 1024**2
    with pytest.raises(ValueError, match='input_changed_or_too_large'):
        install.owned_file(path)


@pytest.mark.parametrize('bad', ['changed-hash', 'writable', 'not-executable', 'symlink', 'hardlink', 'large', 'empty'])
def test_invalid_or_mutable_executable_refuses(tmp_path, bad):
    path, pin = binary(tmp_path, 100)
    if bad == 'changed-hash': pin['sha256'] = '0' * 64
    if bad == 'writable': path.chmod(0o720)
    if bad == 'not-executable': path.chmod(0o600)
    if bad == 'symlink':
        alias = tmp_path / 'alias'; alias.symlink_to(path); pin['path'] = str(alias)
    if bad == 'hardlink': os.link(path, tmp_path / 'second-name')
    if bad in ('large', 'empty'):
        with path.open('r+b') as stream: stream.truncate(257 * 1024**2 if bad == 'large' else 0)
    with pytest.raises(ValueError): install.bootstrap_pin(pin)


def test_path_replacement_during_read_refuses(tmp_path, monkeypatch):
    path, pin = binary(tmp_path, 100)
    replacement = tmp_path / 'replacement'; replacement.write_bytes(path.read_bytes()); replacement.chmod(0o700)
    original = os.read; done = False
    def replace(fd, size):
        nonlocal done
        data = original(fd, size)
        if not done:
            done = True; os.replace(replacement, path)
        return data
    monkeypatch.setattr(os, 'read', replace)
    with pytest.raises(ValueError, match='bootstrap_executable_changed'):
        install.bootstrap_pin(pin)
