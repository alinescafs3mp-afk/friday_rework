"""Native preprocessing precedes persistence; synthetic native transport only."""
from pathlib import Path
from types import SimpleNamespace
import pytest
import test_web_stream_native as native
from test_web_runtime_runner import M


def test_native_exact_registry_overlap_keeps_no_interior_span(tmp_path, monkeypatch, capsys):
    period='ABCD_EFGH_IJKL_MNOP_QRST_UVWX_YZab_cdef_ghij_'
    key=period+period[:10]
    native.test_real_native_agent_reaches_web_and_cleanup(
        tmp_path,monkeypatch,capsys,'explicit','retry_4xx',key,period)
    files=[p for p in tmp_path.rglob('*') if p.is_file() and
           (p.is_relative_to(tmp_path/'output') or p.is_relative_to(tmp_path/'profile/cache') or
            p.name.startswith('request_dump_'))]
    assert any(p.name.startswith('request_dump_') for p in files)
    assert any(p.suffix=='.md' for p in files)
    assert len(period[10:])==35
    assert not [str(p) for p in files if period[10:].encode() in p.read_bytes()]


def test_constructor_failure_restores_actual_native_redaction(tmp_path,monkeypatch,capsys):
    native.test_real_native_agent_reaches_web_and_cleanup(
        tmp_path,monkeypatch,capsys,'explicit','retry_4xx',None,'',construction_failure=True)


def test_cleanup_refuses_to_clobber_replaced_native_hook():
    original=lambda value:value
    ours=lambda value:value
    replacement=lambda value:value
    module=SimpleNamespace(redact_registered_vault_values=replacement)
    obj=M['Native']()
    obj.redact_module=module
    obj.old_registered_redact=original
    obj.registered_redactor=ours
    with pytest.raises(M['Refused'],match='native_cleanup_unconfirmed'):
        obj.close()
    assert module.redact_registered_vault_values is replacement
