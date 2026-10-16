"""Source85 isolated binding refusals and exact new-layer controls.

Production constants remain exact; disabled and historical pins are fixture mutations.
"""
import copy
from pathlib import Path
import pytest
from test_worker_current_archive import (
    normal, installed, env, legacy, receiver, closed_receiver, service,
    install_input, closed_user_bus, current_archive, keep_historical_fixture_at79,
    source_inventory, old, recovery, ordinary, f, snapshot, doc, Budget,
)


@pytest.mark.parametrize('disabled', ['both', 'update', 'input'])
def test_final_bindings_disabled_before_any_pin_read_or_history(tmp_path, monkeypatch, disabled):
    monkeypatch.setattr(recovery, 'CLOSED_CURRENT_UPDATE_SHA', 'a'*64 if disabled=='input' else None)
    monkeypatch.setattr(recovery, 'CLOSED_CURRENT_INPUT_SHA', 'b'*64 if disabled=='update' else None)
    def forbidden(*a, **kw):raise AssertionError('disabled source binding reached pin/read/history')
    monkeypatch.setattr(f, 'pin', forbidden)
    monkeypatch.setattr(f, 'read_json', forbidden)
    monkeypatch.setattr(ordinary, 'update_history', forbidden)
    before=snapshot(tmp_path)
    with pytest.raises(f.Refused, match='ordinary_closed_current_source85_final_binding_required'):
        recovery._closed_current_source({},tmp_path,{},Budget(30))
    assert snapshot(tmp_path)==before


@pytest.mark.parametrize('fault', ['schema84', 'stale-update-pin', 'stale-input-pin'])
def test_source84_schema_and_exact_authority_pins_fail_before_history(current_archive, monkeypatch, fault):
    s=current_archive;r=s.recovery_request
    if fault=='schema84':
        value=f.read_json(Path(r['current_update']['path']))
        value['schema']='friday.ordinary-telegram-source-update.v38'
        r['current_update']=doc(Path(r['current_update']['path']),value)
        monkeypatch.setattr(recovery,'CLOSED_CURRENT_UPDATE_SHA',r['current_update']['sha256'])
    elif fault=='stale-update-pin':
        monkeypatch.setattr(recovery,'CLOSED_CURRENT_UPDATE_SHA','c' * 64)
    else:
        monkeypatch.setattr(recovery,'CLOSED_CURRENT_INPUT_SHA','d' * 64)
    before=snapshot(s.home)
    with pytest.raises(f.Refused,match='ordinary_closed_(current_update_binding_changed|exact_current_update_required)'):
        recovery._closed_current_source(r,s.home,{},Budget(30))
    assert not s.history_calls and snapshot(s.home)==before and not s.tx.exists() and not s.calls


@pytest.mark.parametrize('fault', ['missing85', 'manifest85', 'patch85', 'wrong-project-manifest85', 'wrong-project-patch85'])
def test_exact_source85_new_overlay_refuses_missing_or_mutated_pins_before_native(tmp_path,monkeypatch,fault):
    value,receipt=source_inventory()
    manifest='patches/hermes/ordinary-web-runtime-history-manifest.json'
    patch='patches/hermes/ordinary-web-runtime-history.patch'
    row=next(r for r in receipt['layers'] if r['manifest']==manifest)
    called=[]
    monkeypatch.setattr(f,'source_checked',lambda *a,**kw:called.append(True))
    if fault=='missing85':receipt['layers'].remove(row)
    elif fault=='manifest85':row['manifest_sha256']='0'*64
    elif fault=='patch85':row['patch_sha256']='0'*64
    elif fault=='wrong-project-manifest85':value['project_files'][manifest]='0'*64
    else:value['project_files'][patch]='0'*64
    with pytest.raises(f.Refused,match='composition_overlay_'):
        old.REAL_COMPOSITION_CHECK(value,tmp_path/'never-native',receipt,{})
    assert not called and not list(tmp_path.iterdir())


def test_real_bound_constants_match_exact_source_contract():
    assert recovery.CLOSED_CURRENT_UPDATE_SHA == 'f7809de47b0f654cf3a18f04cbb6411f0af3fe4f2babaec8dd44df7ab7b2d438'
    assert recovery.CLOSED_CURRENT_INPUT_SHA == '2c08186aa921614a2e77ffd3efbeb5a135671f1f98d8a010cdefbd7902f2eda0'
