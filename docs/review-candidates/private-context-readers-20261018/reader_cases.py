"""Real managed Source readers over synthetic private regular text files.

Only deterministic scheduling wrappers forward real os.read unchanged; they
coordinate benign owned-file replacement/revocation, never supply read bytes.
"""
import contextvars
import os
from pathlib import Path
import threading

import pytest
from test_user_isolation import users
from hermes_cli import friday_user_scope as scope
from agent import prompt_builder
from tools.memory_tool import MemoryStore


def private_text(path, value):
    path.write_bytes(value if isinstance(value, bytes) else value.encode('utf-8'))
    path.chmod(0o600)
    return path


def target(users, kind):
    return users.homes[0] / ('workspace/AGENTS.md' if kind == 'context' else 'memories/MEMORY.md')


def read(path, kind):
    if kind == 'context':
        return prompt_builder._read_text_with_timeout(path, timeout=2)
    raw, ok = MemoryStore._read_raw_checked(path)
    assert ok
    return raw


@pytest.mark.parametrize('kind', ['context', 'memory'])
@pytest.mark.parametrize('content', ['', 'обычные заметки ☃', '\ufefffirst\r\nsecond\rthird', 'x' * 130001, 'x' * 1000000],
                         ids=['empty', 'unicode', 'bom_newlines', 'multiple_chunks', 'exact_byte_limit'])
def test_managed_owned_text_exact_decoding_and_cleanup(users, kind, content):
    path = private_text(target(users, kind), content)
    with users.enter(0):
        fds = set(os.listdir('/proc/self/fd'))
        threads = set(threading.enumerate())
        expected = content.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
        assert read(path, kind) == expected
        assert set(os.listdir('/proc/self/fd')) == fds
        assert set(threading.enumerate()) == threads


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_managed_missing_retains_native_empty_semantics(users, kind):
    path = target(users, kind)
    with users.enter(0):
        if kind == 'memory':
            assert MemoryStore._read_raw_checked(path) == ('', True)
            store = MemoryStore(); store.load_from_disk()
            assert store.memory_entries == [] and store.user_entries == []
        else:
            assert prompt_builder._read_context_file(path) == ''


@pytest.mark.parametrize('kind', ['context', 'memory'])
@pytest.mark.parametrize('variant', ['symlink', 'hardlink', 'public_file', 'directory', 'fifo', 'oversize'])
def test_managed_static_invalid_file_objects_refuse_without_leaks(users, kind, variant):
    path = target(users, kind)
    if variant == 'symlink':
        original = private_text(path.with_name('owned-backup.txt'), 'ordinary text')
        path.symlink_to(original)
    elif variant == 'hardlink':
        original = private_text(path.with_name('owned-backup.txt'), 'ordinary text')
        os.link(original, path)
    elif variant == 'directory':
        path.mkdir(mode=0o700)
    elif variant == 'fifo':
        os.mkfifo(path, 0o600)
    else:
        private_text(path, 'x' * (1000001 if variant == 'oversize' else 5))
        if variant == 'public_file':path.chmod(0o644)
    with users.enter(0):
        before = set(os.listdir('/proc/self/fd'))
        with pytest.raises(scope.ScopeDenied):read(path, kind)
        assert set(os.listdir('/proc/self/fd')) == before


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_foreign_root_cannot_be_read_even_with_matching_basename(users, kind):
    foreign = users.homes[1] / ('workspace/AGENTS.md' if kind == 'context' else 'memories/MEMORY.md')
    private_text(foreign, 'ordinary user two note')
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):read(foreign, kind)


def test_memory_non_target_filename_is_not_authority(users):
    path = private_text(users.homes[0] / 'workspace' / 'MEMORY.md', 'ordinary workspace text')
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):MemoryStore._read_raw_checked(path)


@pytest.mark.parametrize('variant', ['public_directory', 'symlink_directory'])
def test_context_parent_descriptor_is_private_and_unlinked(users, variant):
    workspace = users.homes[0] / 'workspace'
    actual = workspace / 'project'; actual.mkdir(mode=0o700)
    path = private_text(actual / 'AGENTS.md', 'ordinary project guidance')
    if variant == 'public_directory':actual.chmod(0o755)
    else:
        alias = workspace / 'linked-project'; alias.symlink_to(actual, target_is_directory=True)
        path = alias / 'AGENTS.md'
    with users.enter(0):
        with pytest.raises(scope.ScopeDenied):read(path, 'context')


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_undecodable_text_preserves_native_read_failure(users, kind):
    path = private_text(target(users, kind), b'\xff\xfe')
    with users.enter(0):
        if kind == 'memory':assert MemoryStore._read_raw_checked(path) == ('', False)
        else:
            with pytest.raises(UnicodeDecodeError):read(path, kind)


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_actual_atomic_replacement_during_owned_read_refuses_mixed_snapshot(users, monkeypatch, kind):
    path = private_text(target(users, kind), 'old ordinary text\n' * 8000)
    replacement = private_text(path.with_name('new-owned.txt'), 'new ordinary text\n')
    original_read = os.read
    replaced = False
    def scheduling_read(fd, size):
        nonlocal replaced
        data = original_read(fd, size)
        if not replaced and os.fstat(fd).st_ino == opened_inode:
            replaced = True
            os.replace(replacement, path)
        return data
    opened_inode = path.stat().st_ino
    with users.enter(0):
        before = set(os.listdir('/proc/self/fd'))
        with monkeypatch.context() as patch:
            patch.setattr(os, 'read', scheduling_read)
            with pytest.raises(scope.ScopeDenied):read(path, kind)
        assert replaced and path.read_text() == 'new ordinary text\n'
        assert set(os.listdir('/proc/self/fd')) == before


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_actual_generation_change_during_read_rejects_old_admission(users, monkeypatch, kind):
    path = private_text(target(users, kind), 'ordinary retained note\n' * 5000)
    original_read = os.read
    changed = False
    inode = path.stat().st_ino
    def scheduling_read(fd, size):
        nonlocal changed
        data = original_read(fd, size)
        if not changed and os.fstat(fd).st_ino == inode:
            changed = True
            users.access('1', enabled=False)
        return data
    with users.enter(0):
        with monkeypatch.context() as patch:
            patch.setattr(os, 'read', scheduling_read)
            with pytest.raises(scope.ScopeDenied):read(path, kind)
        assert changed


def test_managed_context_deadline_and_precancel_leave_no_reader(users):
    path = private_text(target(users, 'context'), 'ordinary context')
    with users.enter(0):
        before_fd = set(os.listdir('/proc/self/fd')); before_threads = set(threading.enumerate())
        assert prompt_builder._read_text_with_timeout(path, timeout=0) is None
        with pytest.raises(scope.ManagedTextReadTimeout):scope.read_context_text(path, timeout=-1)
        assert set(os.listdir('/proc/self/fd')) == before_fd
        assert set(threading.enumerate()) == before_threads


def test_copied_source_context_runs_real_read_and_lost_context_refuses(users):
    path = private_text(target(users, 'context'), 'same admitted context')
    with users.enter(0):
        context = contextvars.copy_context()
        results = []
        def worker():
            results.append(prompt_builder._read_text_with_timeout(path, timeout=2))
        thread = threading.Thread(target=context.run, args=(worker,)); thread.start(); thread.join(timeout=5)
        assert not thread.is_alive() and results == ['same admitted context']
        errors = []
        def lost():
            try:prompt_builder._read_text_with_timeout(path, timeout=2)
            except scope.ScopeDenied:errors.append('refused')
        thread = threading.Thread(target=lost); thread.start(); thread.join(timeout=5)
        assert not thread.is_alive() and errors == ['refused']


def test_retained_memory_refusal_does_not_become_empty_success(users):
    with users.enter(0):
        store = MemoryStore(); store.load_from_disk(); assert store.add('memory', 'ordinary user note')['success']
    original = (users.homes[0] / 'memories/MEMORY.md').read_bytes()
    with users.enter(1):
        with pytest.raises(scope.ScopeDenied):store.load_from_disk()
        with pytest.raises(scope.ScopeDenied):store.add('memory', 'ordinary second note')
    assert (users.homes[0] / 'memories/MEMORY.md').read_bytes() == original


def test_real_managed_prompt_and_memory_consumers_load_own_text(users):
    home = users.homes[0]
    private_text(home / 'SOUL.md', 'Ordinary identity in Russian: помощник')
    private_text(home / 'workspace/AGENTS.md', 'Ordinary project guidance')
    private_text(home / 'memories/MEMORY.md', 'User likes ordinary tea\n§\nUser lives in Paris')
    private_text(home / 'memories/USER.md', 'User name is Alex')
    with users.enter(0):
        memory = MemoryStore();memory.load_from_disk()
        assert memory.memory_entries == ['User likes ordinary tea', 'User lives in Paris']
        assert memory.user_entries == ['User name is Alex']
        assert 'User likes ordinary tea' in memory._system_prompt_snapshot['memory']
        assert 'помощник' in prompt_builder.load_soul_md(home_override=home)
        assert 'Ordinary project guidance' in prompt_builder.build_context_files_prompt(cwd=str(home / 'workspace'), skip_soul=True)


def test_unmanaged_context_and_memory_keep_native_paths_and_text(tmp_path, monkeypatch):
    import hermes_constants
    root = tmp_path / 'operator'; root.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(root))
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(root))
    monkeypatch.setattr(scope, '_ENGAGED', False)
    monkeypatch.setattr(scope, '_CURRENT', contextvars.ContextVar('unmanaged', default=None))
    path = private_text(root / 'ordinary.txt', 'native operator text\r\n')
    with scope.authority(root):
        assert prompt_builder._read_text_with_timeout(path, timeout=2) == 'native operator text\n'
        assert MemoryStore._read_raw_checked(path) == ('native operator text\n', True)
        assert MemoryStore._read_raw_checked(root / 'missing.txt') == ('', True)


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_leaf_disappearance_after_real_read_is_refusal_not_empty(users, monkeypatch, kind):
    path = private_text(target(users, kind), 'ordinary disposable note')
    inode = path.stat().st_ino
    original_read = os.read
    changed = False
    def scheduling_read(fd, size):
        nonlocal changed
        data = original_read(fd, size)
        if not changed and os.fstat(fd).st_ino == inode:
            changed = True; path.unlink()
        return data
    with users.enter(0):
        before = set(os.listdir('/proc/self/fd'))
        with monkeypatch.context() as patch:
            patch.setattr(os, 'read', scheduling_read)
            with pytest.raises(scope.ScopeDenied):read(path, kind)
        assert changed and not path.exists()
        assert set(os.listdir('/proc/self/fd')) == before


def test_context_directory_atomic_replacement_does_not_change_pinned_root(users, monkeypatch):
    directory = users.homes[0] / 'workspace/project';directory.mkdir(mode=0o700)
    path = private_text(directory / 'AGENTS.md', 'ordinary original project note')
    inode = path.stat().st_ino
    original_read = os.read
    changed = False
    def scheduling_read(fd, size):
        nonlocal changed
        data = original_read(fd, size)
        if not changed and os.fstat(fd).st_ino == inode:
            changed = True
            directory.rename(directory.with_name('previous-project'))
            directory.mkdir(mode=0o700)
            private_text(path, 'ordinary replacement project note')
        return data
    with users.enter(0):
        before = set(os.listdir('/proc/self/fd'))
        with monkeypatch.context() as patch:
            patch.setattr(os, 'read', scheduling_read)
            with pytest.raises(scope.ScopeDenied):read(path, 'context')
        assert changed and path.read_text() == 'ordinary replacement project note'
        assert set(os.listdir('/proc/self/fd')) == before


def test_deadline_after_real_bounded_read_closes_all_owned_descriptors(users, monkeypatch):
    import time
    path = private_text(target(users, 'context'), 'ordinary context' * 10000)
    inode = path.stat().st_ino
    original_read = os.read
    delayed = False
    def scheduling_read(fd, size):
        nonlocal delayed
        data = original_read(fd, size)
        if not delayed and os.fstat(fd).st_ino == inode:
            delayed = True; time.sleep(0.15)
        return data
    with users.enter(0):
        before_fd = set(os.listdir('/proc/self/fd')); before_threads = set(threading.enumerate())
        with monkeypatch.context() as patch:
            patch.setattr(os, 'read', scheduling_read)
            assert prompt_builder._read_text_with_timeout(path, timeout=0.1) is None
        assert delayed
        assert set(os.listdir('/proc/self/fd')) == before_fd
        assert set(threading.enumerate()) == before_threads


@pytest.mark.parametrize('variant', ['foreign_missing', 'dangling_link', 'revoked_missing'])
def test_soul_preflight_cannot_swallow_managed_refusal(users, variant):
    home = users.homes[0]
    with users.enter(0):
        if variant == 'dangling_link':(home / 'SOUL.md').symlink_to(home / 'absent-soul.txt')
        if variant == 'revoked_missing':users.access('1', enabled=False)
        requested_home = users.homes[1] if variant == 'foreign_missing' else home
        with pytest.raises(scope.ScopeDenied):prompt_builder.load_soul_md(home_override=requested_home)


@pytest.mark.parametrize('kind', ['context', 'memory'])
def test_caller_cancellation_after_real_read_closes_descriptors(users, monkeypatch, kind):
    class Cancelled(BaseException):
        pass
    path = private_text(target(users, kind), 'ordinary cancellable text')
    inode = path.stat().st_ino
    original_read = os.read
    cancelled = False
    def scheduling_read(fd, size):
        nonlocal cancelled
        data = original_read(fd, size)
        if not cancelled and os.fstat(fd).st_ino == inode:
            cancelled = True
            raise Cancelled()
        return data
    with users.enter(0):
        before_fd = set(os.listdir('/proc/self/fd')); before_threads = set(threading.enumerate())
        with monkeypatch.context() as patch:
            patch.setattr(os, 'read', scheduling_read)
            with pytest.raises(Cancelled):read(path, kind)
        assert cancelled
        assert set(os.listdir('/proc/self/fd')) == before_fd
        assert set(threading.enumerate()) == before_threads
