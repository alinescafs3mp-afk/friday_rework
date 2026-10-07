"""Native owner checks require an actual OS owner identity, never a fallback."""
import os
import pytest
from hermes_cli import friday_dashboard_owner as boundary


def test_read_owned_uses_actual_owner(tmp_path):
    p = tmp_path / 'native-input'; p.write_bytes(b'synthetic'); p.chmod(0o600)
    assert boundary.read_owned(p, private=True) == b'synthetic'


def test_missing_owner_identity_refuses_before_file_open(tmp_path, monkeypatch):
    p = tmp_path / 'native-input'; p.write_bytes(b'synthetic'); calls = []
    with monkeypatch.context() as patch:
        patch.delattr(boundary.os, 'getuid')
        patch.setattr(boundary.os, 'open', lambda *a, **kw: calls.append(a))
        with pytest.raises(ValueError, match='friday_dashboard_owner_unproved'):
            boundary.read_owned(p)
    assert calls == []


def test_foreign_uid_refuses_even_for_private_regular_file(tmp_path, monkeypatch):
    p = tmp_path / 'native-input'; p.write_bytes(b'synthetic'); p.chmod(0o600)
    real_uid = os.getuid()
    with monkeypatch.context() as patch:
        patch.setattr(boundary.os, 'getuid', lambda: real_uid + 1)
        with pytest.raises(ValueError, match='friday_dashboard_owner_unproved'):
            boundary.read_owned(p, private=True)
