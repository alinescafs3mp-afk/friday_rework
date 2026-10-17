"""Independent late-CAS controls; synthetic homes only."""
import copy
from pathlib import Path
import pytest
from test_ordinary_dashboard_project_update import dashboard, put, doc, snapshot, f, o, Budget
from test_ordinary_dsh_project_update import installed

@pytest.mark.parametrize('fault',['request','history','unit','unknown_partial'])
def test_independent_late_retained_drift(dashboard,monkeypatch,fault):
    from scripts.dsh_prepare import StopUnconfirmed
    s=dashboard;home=s['home'];before=snapshot(home);publish=o.publish_update_file;foreign={}
    def drift(path,*args,**kwargs):
        result=publish(path,*args,**kwargs)
        if not foreign:
            if fault=='request':
                target=s['requestpath'];value=copy.deepcopy(s['request']);value['foreign_late_writer']=True;doc(target,value)
            elif fault=='history':
                target=home/next(n for n in s['request']['transaction_history'] if n.endswith('/before/preserved'));put(target,b'late foreign historical bytes\n')
            elif fault=='unit':
                target=Path(s['request']['native_unit']['path']);other=target.with_name('unit.foreign');put(other,target.read_bytes());other.replace(target)
            else:
                target=home/'preparation'/('ordinary-inference-rebind-'+'e'*64)/'intent.json';put(target,b'late partial foreign transaction\n')
            foreign.update(path=target,state=o.update_file_state(target))
        return result
    monkeypatch.setattr(o,'publish_update_file',drift)
    with pytest.raises(StopUnconfirmed):o.update(s['request'],s['requestpath'],Budget(180))
    assert o.update_file_state(foreign['path'])==foreign['state']
    for n in set(o.PROJECT_DASHBOARD_AFTER)|{f.MARKER}:
        assert snapshot(home)[n]==before[n]
    tx=home/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert(tx/'intent.json').exists() and not(tx/'committed.json').exists() and not(tx/'rolled-back.json').exists()
    with pytest.raises((ValueError,KeyError)):o.update(s['request'],s['requestpath'],Budget(180))

def test_independent_keyboardinterrupt_after_marker(dashboard,monkeypatch):
    s=dashboard;home=s['home'];before=snapshot(home);publish=o.publish_update_file;injected=False
    def interrupt(path,*args,**kwargs):
        nonlocal injected
        result=publish(path,*args,**kwargs)
        if path==home/f.MARKER and not injected:
            injected=True;raise KeyboardInterrupt('review cancellation after all publications')
        return result
    monkeypatch.setattr(o,'publish_update_file',interrupt)
    with pytest.raises(KeyboardInterrupt):o.update(s['request'],s['requestpath'],Budget(180))
    assert all(snapshot(home)[n]==row for n,row in before.items())
    tx=home/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert(tx/'intent.json').exists() and(tx/'rolled-back.json').exists() and not(tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))
