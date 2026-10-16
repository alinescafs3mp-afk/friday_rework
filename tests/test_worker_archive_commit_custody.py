"""Commit persistence/custody failures against private archive fixtures only."""
import os
from pathlib import Path

import pytest

from scripts.dsh_prepare import StopUnconfirmed
from test_worker_current_archive import (
    normal, installed, env, legacy, receiver, closed_receiver, service,
    install_input, closed_user_bus, current_archive, keep_historical_fixture_at79,
    reconcile, current_tree, snapshot, admit, f, ordinary,
)


@pytest.mark.parametrize('fault', ['publication-fsync', 'lost-ack', 'final-fsync'])
def test_owned_commit_is_withdrawn_before_confirmed_rollback(current_archive, monkeypatch, fault):
    s = current_archive
    tree = current_tree(s)[0]
    marker = ordinary.update_file_state(s.home / f.MARKER)
    commit = s.tx / 'committed.json'
    publish = ordinary.publish_update_file
    sync = ordinary.sync_directory
    unlink = Path.unlink
    primary = OSError('synthetic commit persistence ' + fault)
    owned = []; removed = []; syncs = []; fired = []

    def checked_unlink(path, *args, **kwargs):
        if path == commit:
            state = ordinary.update_file_state(path)
            assert owned and state == owned[0]
            # Receipt withdrawal precedes marker restoration and rename-back.
            assert ordinary.update_file_state(s.home / f.MARKER) != marker
            assert not s.old_tree.exists()
            assert current_tree(s, s.tx / 'failed-qualification')[0] == tree
            removed.append(state)
        return unlink(path, *args, **kwargs)

    def failing_sync(path):
        if path == s.tx and commit.exists():
            syncs.append(True)
            if not owned:
                owned.append(ordinary.update_file_state(commit))
            if (fault == 'publication-fsync' or
                    fault == 'final-fsync' and len(syncs) == 2) and not fired:
                fired.append(True)
                raise primary
        return sync(path)

    def failing_publish(path, *args, **kwargs):
        publish(path, *args, **kwargs)
        if path == commit and fault == 'lost-ack':
            fired.append(True)
            raise primary

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, 'unlink', checked_unlink)
        scoped.setattr(ordinary, 'sync_directory', failing_sync)
        scoped.setattr(ordinary, 'publish_update_file', failing_publish)
        with pytest.raises(OSError) as caught:
            reconcile(s)
    assert caught.value is primary and fired == [True]
    assert removed == owned and len(removed) == 1
    assert not os.path.lexists(commit)
    assert not (s.tx / 'committed.json.ordinary-staged').exists()
    assert current_tree(s)[0] == tree and not (s.tx / 'failed-qualification').exists()
    restored = ordinary.update_file_state(s.home / f.MARKER)
    assert all(restored[key] == marker[key] for key in ('data', 'mode'))
    failure = f.read_json(s.tx / 'failure.json')
    assert failure['state'] == 'ROLLED_BACK_CONSUMED_NO_RETRY'
    assert failure['retry_authorized'] is False and failure['runtime_authority'] == 'NOT_GRANTED'
    assert f.read_json(s.tx / 'intent.json')['state'] == 'CONSUMED_NO_RETRY'
    with pytest.raises(ValueError):
        reconcile(s)
    s.recovery_request['recovery_id'] = 'another-commit-custody-id'
    admit(s)
    with pytest.raises(ValueError, match='failure_already_consumed'):
        reconcile(s)
    assert not s.calls


@pytest.mark.parametrize('target', ['commit', 'marker', 'archive'])
def test_foreign_inode_prevents_every_rollback_mutation(current_archive, monkeypatch, target):
    s = current_archive
    commit = s.tx / 'committed.json'
    paths = {'commit': commit, 'marker': s.home / f.MARKER,
             'archive': s.tx / 'failed-qualification/dsh-safety/workspace/artifact'}
    publish = ordinary.publish_update_file
    primary = OSError('synthetic foreign ' + target + ' after commit publication')
    retained = {}
    locks = {str(path.relative_to(s.home)): ordinary.update_file_state(path)
             for path in (s.home / 'config.yaml.lock', s.user / 'config.yaml.lock')}

    def foreign_publish(path, *args, **kwargs):
        publish(path, *args, **kwargs)
        if path == commit:
            changed = paths[target]
            before = ordinary.update_file_state(changed)
            other = s.deploy / 'foreign-exact-bytes-mode'
            other.write_bytes(before['data']); other.chmod(before['mode'])
            os.replace(other, changed)
            retained['foreign'] = ordinary.update_file_state(changed)
            assert retained['foreign']['identity'] != before['identity']
            assert retained['foreign']['data'] == before['data']
            assert retained['foreign']['mode'] == before['mode']
            retained['marker'] = ordinary.update_file_state(paths['marker'])
            retained['commit'] = ordinary.update_file_state(commit)
            retained['tree'] = current_tree(s, s.tx / 'failed-qualification')[0]
            retained['home'] = snapshot(s.home)
            raise primary

    monkeypatch.setattr(ordinary, 'publish_update_file', foreign_publish)
    with pytest.raises(StopUnconfirmed) as caught:
        reconcile(s)
    assert caught.value.__cause__ is primary
    assert ordinary.update_file_state(paths[target]) == retained['foreign']
    assert ordinary.update_file_state(paths['marker']) == retained['marker']
    assert ordinary.update_file_state(commit) == retained['commit']
    assert current_tree(s, s.tx / 'failed-qualification')[0] == retained['tree']
    after = snapshot(s.home)
    # Native context-manager release removes its PID stamp from the same lock
    # inode; this required cleanup is separate from archive rollback writes.
    assert {name: value for name, value in after.items() if name not in locks} == {
        name: value for name, value in retained['home'].items() if name not in locks}
    assert all(ordinary.update_file_state(s.home / name) == state
               for name, state in locks.items())
    assert not s.old_tree.exists() and not (s.tx / 'failure.json').exists()
    assert f.read_json(s.tx / 'intent.json')['state'] == 'CONSUMED_NO_RETRY'
    assert not s.calls


@pytest.mark.parametrize('fault', ['unlink', 'withdrawal-fsync'])
def test_unconfirmed_commit_withdrawal_stops_before_marker_and_tree_restore(current_archive, monkeypatch, fault):
    s = current_archive
    commit = s.tx / 'committed.json'
    publish = ordinary.publish_update_file
    unlink = Path.unlink
    sync = ordinary.sync_directory
    primary = OSError('synthetic lost commit acknowledgement')
    retained = {}; attempted = []; secondary = []

    def lost_ack(path, *args, **kwargs):
        publish(path, *args, **kwargs)
        if path == commit:
            retained['commit'] = ordinary.update_file_state(commit)
            retained['marker'] = ordinary.update_file_state(s.home / f.MARKER)
            retained['tree'] = current_tree(s, s.tx / 'failed-qualification')[0]
            raise primary

    def failed_unlink(path, *args, **kwargs):
        if path == commit:
            assert ordinary.update_file_state(path) == retained['commit']
            attempted.append(True)
            if fault == 'unlink':
                secondary.append(True)
                raise OSError('synthetic withdrawal unlink failure')
        return unlink(path, *args, **kwargs)

    def failed_sync(path):
        if path == s.tx and attempted and not commit.exists():
            secondary.append(True)
            raise OSError('synthetic withdrawal directory fsync failure')
        return sync(path)

    monkeypatch.setattr(ordinary, 'publish_update_file', lost_ack)
    monkeypatch.setattr(Path, 'unlink', failed_unlink)
    monkeypatch.setattr(ordinary, 'sync_directory', failed_sync)
    with pytest.raises(StopUnconfirmed) as caught:
        reconcile(s)
    assert caught.value.__cause__ is primary
    assert attempted == [True] and secondary == [True]
    assert ordinary.update_file_state(s.home / f.MARKER) == retained['marker']
    assert current_tree(s, s.tx / 'failed-qualification')[0] == retained['tree']
    assert commit.exists() == (fault == 'unlink')
    if fault == 'unlink':
        assert ordinary.update_file_state(commit) == retained['commit']
    assert not s.old_tree.exists() and not (s.tx / 'failure.json').exists()
    assert f.read_json(s.tx / 'intent.json')['state'] == 'CONSUMED_NO_RETRY'
    assert not s.calls
