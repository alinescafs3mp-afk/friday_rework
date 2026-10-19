"""Physical custody mutation regressions on the existing synthetic native fixture."""
import os
from pathlib import Path
import pytest
from test_ordinary_compression_capacity_rebind import (
    baseline, cutover, renderer_transaction, renderer_capacity, run, write, u, f)
from scripts.dsh_prepare import StopUnconfirmed


def assert_uncertified_restoration(c, caught, reason):
    assert str(caught.value.__cause__) == reason
    assert not (c.tx/'rolled-back.json').exists()
    assert not (c.tx/'committed.json').exists()
    assert (c.tx/'intent.json').is_file()
    assert all((c.home/name).read_bytes()==data for name,data in c.before.items())
    secondary=getattr(caught.value.__cause__,'friday_secondary_failures',())
    assert any(str(error)=='ordinary_rebind_rollback_retained_custody_lost' for error in secondary)
    assert not (c.jarvis/'auth.lock').exists()


@pytest.mark.parametrize('kind',['external','retained'])
def test_one_shot_foreign_reference_is_preserved_and_never_certified(renderer_capacity,monkeypatch,kind):
    c=renderer_capacity
    path=Path(c.exact['binding']['path']) if kind=='external' else c.home/'SOUL.md'
    original=u.update_file_state(path);publish=u.publish_update_file;states=[]
    with path.open('rb') as held_original:
        def foreign(destination,*args,**kwargs):
            result=publish(destination,*args,**kwargs)
            if destination==c.home/'config.yaml' and not states:
                other=path.with_name('one-shot-foreign');write(other,path.read_bytes());os.replace(other,path)
                states.append(u.update_file_state(path))
            return result
        monkeypatch.setattr(u,'publish_update_file',foreign)
        with pytest.raises(StopUnconfirmed) as caught:run(c)
        assert states[0] != original
        assert u.update_file_state(path)==states[0]
        assert held_original.read()==original['data']
    assert_uncertified_restoration(c,caught,'ordinary_rebind_retained_or_protected_reference_changed')


def test_physical_reference_aba_does_not_recover_custody_certificate(renderer_capacity,monkeypatch):
    c=renderer_capacity;path=Path(c.exact['binding']['path']);parked=path.with_name('original-binding-parked')
    original=u.update_file_state(path);publish=u.publish_update_file;states=[]
    def aba(destination,*args,**kwargs):
        result=publish(destination,*args,**kwargs)
        if destination==c.home/'config.yaml':
            if not states:
                os.replace(path,parked);write(path,original['data'])
            else:
                assert len(states)==1
                os.replace(parked,path)
            states.append(u.update_file_state(path))
        return result
    monkeypatch.setattr(u,'publish_update_file',aba)
    with pytest.raises(StopUnconfirmed) as caught:run(c)
    assert len(states)==2 and states[0]!=original and states[1]==original
    assert u.update_file_state(path)==original and not parked.exists()
    assert_uncertified_restoration(c,caught,'ordinary_rebind_retained_or_protected_reference_changed')


def test_renderer_reference_proof_failure_is_latched_after_publication(renderer_capacity,monkeypatch):
    c=renderer_capacity;publish=u.publish_update_file;proof=u.inference_renderer_references;published=False;failed=False
    def publication(destination,*args,**kwargs):
        nonlocal published
        result=publish(destination,*args,**kwargs)
        if destination==c.home/'config.yaml':published=True
        return result
    def reference_proof(product):
        nonlocal failed
        if published and not failed:
            failed=True;f.require(False,'synthetic_renderer_reference_proof_lost')
        return proof(product)
    monkeypatch.setattr(u,'publish_update_file',publication)
    monkeypatch.setattr(u,'inference_renderer_references',reference_proof)
    with pytest.raises(StopUnconfirmed) as caught:run(c)
    assert failed
    assert_uncertified_restoration(c,caught,'synthetic_renderer_reference_proof_lost')


def test_protected_reference_refusal_before_first_publication_stays_ordinary(renderer_capacity,monkeypatch):
    c=renderer_capacity;path=Path(c.exact['binding']['path']);validate=u.inference_capacity_configuration;changed=False
    original=u.update_file_state(path)
    with path.open('rb'):
        def validation(before,after,*,root):
            nonlocal changed
            result=validate(before,after,root=root)
            if root and not changed:
                other=path.with_name('pre-effect-foreign');write(other,path.read_bytes());os.replace(other,path);changed=True
            return result
        monkeypatch.setattr(u,'inference_capacity_configuration',validation)
        with pytest.raises(ValueError,match='ordinary_rebind_retained_or_protected_reference_changed') as caught:run(c)
        assert not isinstance(caught.value,StopUnconfirmed)
        assert changed and u.update_file_state(path)!=original
    assert not c.tx.exists()
    assert all((c.home/name).read_bytes()==data for name,data in c.before.items())
