"""Changed shared rollback path through the historical request boundary."""
import pytest

from test_worker_current_archive import (
    normal, installed, env, legacy, receiver, closed_receiver, service,
    install_input, closed_user_bus, keep_historical_fixture_at79, old,
)


@pytest.mark.parametrize('fault', ['publish', 'archive-fsync', 'commit'])
def test_legacy_closed_archive_rollback_after_shared_commit_change(closed_receiver, monkeypatch, fault):
    old.test_closed_partial_failure_restores_original_tree_and_marker_then_deduplicates_failure(
        closed_receiver, monkeypatch, fault)
