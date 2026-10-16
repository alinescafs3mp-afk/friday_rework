"""Synthetic transactions use the real bounded v1/v2 journal and publication helpers."""
import copy
from pathlib import Path
import pytest
from test_ordinary_dsh_project_update import (installed, doc, put, snapshot,
    test_partial_publication_rolls_back_and_consumes_attempt as rollback_case,
    test_same_bytes_on_foreign_inode_are_not_restored as custody_case)
from scripts import friday_install as f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget

@pytest.fixture
def qualified(installed, monkeypatch):
    s = installed
    o.update(s['request'], s['requestpath'], Budget(180))
    predecessor = doc(s['requestpath'].with_name('committed-v1-request.json'), s['request'])
    old = copy.deepcopy(s['current'])
    oldref = s['request']['current_input']
    names = ['plugins/friday_rework/host_runtime.py',
             'plugins/friday_rework/user_worker_join.py', 'scripts/worker_qualification.py']
    before = {n: old['project_files'][n] for n in names+['scripts/friday_ordinary_install.py']}
    monkeypatch.setattr(o, 'PROJECT_QUALIFICATION_BEFORE', before)
    after = {n: b'# exact qualification after '+n.encode()+b'\n' for n in names}
    monkeypatch.setattr(o, 'PROJECT_QUALIFICATION_AFTER', {n:f.digest(b) for n,b in after.items()})
    current = copy.deepcopy(old)
    for n,b in {**after, 'scripts/friday_ordinary_install.py':b'# reviewed updater v2\n'}.items():
        current['project_files'][n] = put(s['root']/n,b)['sha256']
    r = copy.deepcopy(s['request'])
    r.update(schema=o.PROJECT_QUALIFICATION_SCHEMA, previous_input=oldref,
        current_input=doc(s['requestpath'].with_name('qualification-current.json'),current),
        predecessor_update=predecessor,
        marker=doc(s['home']/f.MARKER,f.read_json(s['home']/f.MARKER)))
    r['transaction_history'] = {n:f.digest(b) for n,(b,_) in snapshot(s['home']).items()
        if n.startswith('preparation/')}
    monkeypatch.setattr(o,'PROJECT_QUALIFICATION_NATIVE_FILES',len(s['receipt']['files']))
    monkeypatch.setattr(o,'PROJECT_QUALIFICATION_HISTORY_FILES',len(r['transaction_history']))
    requestpath=s['requestpath'].with_name('qualification-request.json');doc(requestpath,r)
    s.update(previous=old,current=current,request=r,requestpath=requestpath,
        marker=f.read_json(s['home']/f.MARKER),after=after)
    return s

def repin(s):
    s['request']['current_input']=doc(Path(s['request']['current_input']['path']),s['current'])
    doc(s['requestpath'],s['request'])

def test_exact_qualification_transaction_preserves_all_other_files(qualified):
    s=qualified;before=snapshot(s['home'])
    identities={n:o.update_file_state(s['home']/n) for n in before}
    out=o.update(s['request'],s['requestpath'],Budget(180));after=snapshot(s['home'])
    changed={n for n in before if before[n]!=after[n]}
    assert changed==set(s['after'])-{'scripts/worker_qualification.py'}|{f.MARKER}
    assert all(o.update_file_state(s['home']/n)==row for n,row in identities.items() if n not in changed)
    updated=f.read_json(s['home']/f.MARKER)
    expected=copy.deepcopy(s['marker']);expected['input_sha256']=s['request']['current_input']['sha256']
    expected['ordinary_gateway']['operator_entry']['input']=s['request']['current_input']
    for n in changed-{f.MARKER}:expected['plugin_files'][n]=s['current']['project_files'][n]
    assert updated==expected
    assert out['native_source_unchanged'] and out['ready'] is False
    assert len(s['previous']['project_files'])==len(s['current']['project_files'])==223
    assert len(f.read_json(s['home']/'hermes-agent.source.json')['layers'])==77
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('fault',['extra','missing','host_after','join_after','script_after','host_before',
    'updater_before','updater_unchanged','policy','settings','history','predecessor','native','installed'])
def test_qualification_mutations_fail_before_any_publication(qualified,fault):
    s=qualified;r=s['request'];cur=s['current'];host='plugins/friday_rework/host_runtime.py'
    if fault=='extra':cur['project_files']['extra.py']=put(s['root']/'extra.py',b'extra')['sha256']
    elif fault=='missing':cur['project_files'].pop('config/unchanged-0.txt')
    elif fault in ('host_after','join_after','script_after'):
        n={'host_after':host,'join_after':'plugins/friday_rework/user_worker_join.py','script_after':'scripts/worker_qualification.py'}[fault]
        cur['project_files'][n]=put(s['root']/n,b'unreviewed')['sha256']
    elif fault in ('host_before','updater_before'):
        prev=copy.deepcopy(s['previous']);prev['project_files'][host if fault=='host_before' else 'scripts/friday_ordinary_install.py']='0'*64
        r['previous_input']=doc(Path(r['previous_input']['path']),prev)
    elif fault=='updater_unchanged':cur['project_files']['scripts/friday_ordinary_install.py']=s['previous']['project_files']['scripts/friday_ordinary_install.py']
    elif fault=='policy':cur['project_files'][o.PROJECT_POLICY]=put(s['root']/o.PROJECT_POLICY,b'changed policy')['sha256']
    elif fault=='settings':cur['model']='changed'
    elif fault=='history':r['transaction_history'].pop(next(iter(r['transaction_history'])))
    elif fault=='predecessor':r['predecessor_update']=doc(s['requestpath'].with_name('wrong-predecessor.json'),{'schema':o.PROJECT_QUALIFICATION_SCHEMA})
    elif fault=='native':put(s['source']/'retained.txt',b'foreign',0o644)
    else:put(s['home']/host,b'foreign installed')
    repin(s);before=snapshot(s['home'])
    with pytest.raises((ValueError,AssertionError,KeyError)):o.update(r,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before

@pytest.mark.parametrize('publication',[1,2,3])
def test_qualification_rollback_consumes_exact_attempt(qualified,monkeypatch,publication):
    rollback_case(qualified,monkeypatch,publication)

def test_qualification_uncertain_inode_is_not_overwritten(qualified,monkeypatch):
    custody_case(qualified,monkeypatch)


def test_committed_project_predecessor_flag_is_required(qualified):
    s=qualified;r=s['request'];prior=f.read_json(Path(r['predecessor_update']['path']))
    tx=s['home']/'preparation'/('ordinary-source-update-'+prior['previous_input']['sha256'])
    commit=f.read_json(tx/'committed.json');commit['project_only']=False
    (tx/'committed.json').chmod(0o600);doc(tx/'committed.json',commit)
    r['transaction_history'][str((tx/'committed.json').relative_to(s['home']))]=f.digest((tx/'committed.json').read_bytes())
    doc(s['requestpath'],r);before=snapshot(s['home'])
    with pytest.raises(ValueError,match='exact_committed_project_predecessor'):o.update(r,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before

@pytest.mark.parametrize('constant',['PROJECT_QUALIFICATION_NATIVE_FILES','PROJECT_QUALIFICATION_HISTORY_FILES'])
def test_exact_inventory_sizes_are_mandatory(qualified,monkeypatch,constant):
    s=qualified;monkeypatch.setattr(o,constant,getattr(o,constant)+1);before=snapshot(s['home'])
    with pytest.raises(ValueError,match='exact_qualification_inventory'):o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before

def test_failure_after_all_three_publications_restores_all(qualified,monkeypatch):
    import sys
    s=qualified;before=snapshot(s['home']);gateway=sys.modules['hermes_cli.friday_ordinary_gateway'];check=gateway.check
    def fail_after(home,role=False):
        if f.read_json(home/f.MARKER)['input_sha256']==s['request']['current_input']['sha256']:
            raise RuntimeError('post-publication check failure')
        return check(home,role=role)
    monkeypatch.setattr(gateway,'check',fail_after)
    with pytest.raises(RuntimeError,match='post-publication'):o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home']);assert all(after[n]==row for n,row in before.items())
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert (tx/'rolled-back.json').is_file() and not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))
