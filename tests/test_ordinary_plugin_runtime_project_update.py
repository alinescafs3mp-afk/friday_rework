"""Exact helper-closure transactions in a synthetic private home only."""
import copy
import os
from pathlib import Path
import stat
import sys

import pytest

from test_ordinary_dsh_qualification_project_update import qualified
from test_ordinary_dsh_project_update import installed, doc, put, snapshot
from scripts import friday_install as f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget


@pytest.fixture
def runtime(qualified, monkeypatch):
    s = qualified
    o.update(s['request'], s['requestpath'], Budget(180))
    old = copy.deepcopy(s['current'])
    # The smaller shared fixture uses filler entries for these real project files.
    missing = set(o.PROJECT_RUNTIME_BEFORE)-set(old['project_files'])
    for n, filler in zip(sorted(missing), sorted(n for n in old['project_files'] if n.startswith('config/unchanged-'))):
        del old['project_files'][filler]
        data = b'# prior helper consumer '+n.encode()+b'\n'
        old['project_files'][n] = put(s['root']/n, data)['sha256']
        if n.startswith('plugins/'):
            put(s['home']/n, data)
    oldref = doc(s['requestpath'].with_name('runtime-previous.json'), old)
    prior = copy.deepcopy(s['request']); prior['current_input'] = oldref
    priorref = doc(s['requestpath'].with_name('runtime-predecessor.json'), prior)
    tx = s['home']/'preparation'/('ordinary-source-update-'+prior['previous_input']['sha256'])
    for name, field, value in [('intent.json', 'request_sha256', priorref['sha256']),
                              ('committed.json', 'current_input', oldref)]:
        data = f.read_json(tx/name); data[field] = value
        (tx/name).chmod(0o600); doc(tx/name, data); (tx/name).chmod(0o400)
    marker = f.read_json(s['home']/f.MARKER)
    marker['input_sha256'] = oldref['sha256']
    marker['ordinary_gateway']['operator_entry']['input'] = oldref
    marker['plugin_files'] = {n:h for n,h in old['project_files'].items() if n.startswith('plugins/')}
    markerref = doc(s['home']/f.MARKER, marker)
    before = {n:old['project_files'][n] for n in o.PROJECT_RUNTIME_BEFORE}
    after = {n:b'# frozen helper closure '+n.encode()+b'\n' for n in
             (set(before)-{'scripts/friday_ordinary_install.py'}) | o.PROJECT_RUNTIME_NEW}
    monkeypatch.setattr(o, 'PROJECT_RUNTIME_BEFORE', before)
    monkeypatch.setattr(o, 'PROJECT_RUNTIME_AFTER', {n:f.digest(b) for n,b in after.items()})
    current = copy.deepcopy(old)
    for n,data in {**after, 'scripts/friday_ordinary_install.py':b'# updater v3\n'}.items():
        current['project_files'][n] = put(s['root']/n,data)['sha256']
    r = copy.deepcopy(s['request'])
    r.update(schema=o.PROJECT_RUNTIME_SCHEMA, previous_input=oldref,
        current_input=doc(s['requestpath'].with_name('runtime-current.json'),current),
        predecessor_update=priorref, marker=markerref)
    r['transaction_history'] = {n:f.digest(b) for n,(b,_) in snapshot(s['home']).items()
        if n.startswith('preparation/')}
    monkeypatch.setattr(o, 'PROJECT_RUNTIME_NATIVE_FILES', len(s['receipt']['files']))
    monkeypatch.setattr(o, 'PROJECT_RUNTIME_HISTORY_FILES', len(r['transaction_history']))
    requestpath=s['requestpath'].with_name('runtime-request.json'); doc(requestpath,r)
    # Normal user preparations are retained data, with no adoption or cleanup.
    put(s['home']/'users/ordinary/workers/attachment.json', b'prepared workers OFF\n')
    put(s['home']/'users/ordinary/runtime-input.json', b'private admission retained\n')
    s.update(previous=old,current=current,request=r,requestpath=requestpath,marker=marker,after=after)
    return s


def repin(s):
    s['request']['current_input']=doc(Path(s['request']['current_input']['path']),s['current'])
    doc(s['requestpath'],s['request'])


def test_exact_write_set_and_all_retained_inodes(runtime):
    s=runtime; before=snapshot(s['home'])
    states={n:o.update_file_state(s['home']/n) for n in before}
    result=o.update(s['request'],s['requestpath'],Budget(180)); after=snapshot(s['home'])
    plugins={n for n in s['after'] if n.startswith('plugins/')}
    assert {n for n in before if before[n]!=after[n]} == (plugins-o.PROJECT_RUNTIME_NEW)|{f.MARKER}
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    additions=set(after)-set(before)
    assert {n for n in additions if not n.startswith('preparation/')}==o.PROJECT_RUNTIME_NEW
    for n,state in states.items():
        if n not in plugins|{f.MARKER}: assert o.update_file_state(s['home']/n)==state
    for n in plugins:
        assert after[n][0]==s['after'][n]
        if n in o.PROJECT_RUNTIME_NEW: assert after[n][1]==0o600
    assert not (s['home']/'scripts').exists()
    intent=f.read_json(tx/'intent.json')
    assert all(intent['before'][n] is None for n in o.PROJECT_RUNTIME_NEW)
    assert all(not (tx/'before'/n).exists() for n in o.PROJECT_RUNTIME_NEW)
    expected=copy.deepcopy(s['marker']);expected['input_sha256']=s['request']['current_input']['sha256']
    expected['ordinary_gateway']['operator_entry']['input']=s['request']['current_input']
    expected['plugin_files'].update({n:s['current']['project_files'][n] for n in plugins})
    assert f.read_json(s['home']/f.MARKER)==expected
    assert result['native_source_unchanged'] and not result['ready']
    assert len(s['previous']['project_files'])==223 and len(s['current']['project_files'])==227
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('fault',['extra','missing','wrong_new','wrong_consumer','wrong_script','wrong_before',
    'settings','principal','predecessor','history','native_count','history_count','extra_installed',
    'missing_afterpin','extra_afterpin','updater_unchanged','symlink_parent'])
def test_rejects_unreviewed_inputs_before_effects(runtime,monkeypatch,fault):
    s=runtime;r=s['request'];cur=s['current'];new=sorted(o.PROJECT_RUNTIME_NEW)[0]
    if fault=='extra':cur['project_files']['extra.py']=put(s['root']/'extra.py',b'extra')['sha256']
    elif fault=='missing':cur['project_files'].pop(new)
    elif fault in ('wrong_new','wrong_consumer','wrong_script'):
        n={'wrong_new':new,'wrong_consumer':'plugins/friday_rework/host_runtime.py','wrong_script':'scripts/friday_install.py'}[fault]
        cur['project_files'][n]=put(s['root']/n,b'wrong')['sha256']
    elif fault=='wrong_before':
        old=copy.deepcopy(s['previous']);old['project_files']['scripts/friday_install.py']='0'*64
        r['previous_input']=doc(Path(r['previous_input']['path']),old)
    elif fault=='settings':cur['model']='changed'
    elif fault=='principal':monkeypatch.setenv('HERMES_HOME',str(s['home'].parent))
    elif fault=='predecessor':r['predecessor_update']=doc(s['requestpath'].with_name('bad-prior.json'),{'schema':o.PROJECT_UPDATE_SCHEMA})
    elif fault=='history':r['transaction_history'].pop(next(iter(r['transaction_history'])))
    elif fault=='native_count':monkeypatch.setattr(o,'PROJECT_RUNTIME_NATIVE_FILES',999)
    elif fault=='history_count':monkeypatch.setattr(o,'PROJECT_RUNTIME_HISTORY_FILES',999)
    elif fault=='extra_installed':put(s['home']/new,b'foreign preexisting helper')
    elif fault=='missing_afterpin':monkeypatch.setattr(o,'PROJECT_RUNTIME_AFTER',{n:h for n,h in o.PROJECT_RUNTIME_AFTER.items() if n!=new})
    elif fault=='extra_afterpin':monkeypatch.setattr(o,'PROJECT_RUNTIME_AFTER',dict(o.PROJECT_RUNTIME_AFTER,unapproved='0'*64))
    elif fault=='updater_unchanged':cur['project_files']['scripts/friday_ordinary_install.py']=s['previous']['project_files']['scripts/friday_ordinary_install.py']
    else:
        # Inventory traversal rejects a linked directory before publication.
        (s['home']/'plugins/friday_rework/foreign').symlink_to(s['root'],target_is_directory=True)
    repin(s);before=snapshot(s['home'])
    with pytest.raises((ValueError,AssertionError,KeyError)):o.update(r,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('publication',range(1,9))
def test_failure_restores_new_helpers_and_consumes_attempt(runtime,monkeypatch,publication):
    s=runtime;before=snapshot(s['home']);original=o.publish_update_file;count=0
    def fail(*args,**kwargs):
        nonlocal count
        count+=1
        if count==publication:raise RuntimeError('publication failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='publication failure'):o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home']);assert all(after[n]==row for n,row in before.items())
    assert not (set(after)-set(before)) & o.PROJECT_RUNTIME_NEW
    assert any(n.endswith('/rolled-back.json') for n in set(after)-set(before))
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


def test_failure_after_all_publications_rolls_back(runtime,monkeypatch):
    s=runtime;before=snapshot(s['home']);gateway=sys.modules['hermes_cli.friday_ordinary_gateway'];original=gateway.check
    def check(home,role=False):
        if f.read_json(home/f.MARKER)['input_sha256']==s['request']['current_input']['sha256']:raise RuntimeError('after publication')
        return original(home,role=role)
    monkeypatch.setattr(gateway,'check',check)
    with pytest.raises(RuntimeError,match='after publication'):o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home']);assert all(after[n]==row for n,row in before.items())
    assert not (set(after)-set(before)) & o.PROJECT_RUNTIME_NEW
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert (tx/'rolled-back.json').exists() and not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


def test_foreign_new_inode_is_never_removed(runtime,monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s=runtime;original=o.publish_update_file;foreign={}
    def lose(path,*args,**kwargs):
        if foreign:raise RuntimeError('custody lost')
        result=original(path,*args,**kwargs)
        if str(path.relative_to(s['home'])) in o.PROJECT_RUNTIME_NEW:
            other=path.with_name(path.name+'.foreign');put(other,path.read_bytes(),stat.S_IMODE(path.stat().st_mode));os.replace(other,path)
            foreign.update(path=path,state=o.update_file_state(path))
        return result
    monkeypatch.setattr(o,'publish_update_file',lose)
    with pytest.raises(StopUnconfirmed):o.update(s['request'],s['requestpath'],Budget(180))
    assert o.update_file_state(foreign['path'])==foreign['state']
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert not (tx/'rolled-back.json').exists() and not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('name', sorted((set(o.PROJECT_RUNTIME_BEFORE)-{'scripts/friday_ordinary_install.py'}) | o.PROJECT_RUNTIME_NEW))
def test_every_reviewed_afterpin_is_required(runtime,name):
    s=runtime;s['current']['project_files'][name]=put(s['root']/name,b'wrong reviewed pin')['sha256']
    repin(s);before=snapshot(s['home'])
    with pytest.raises(ValueError,match='reviewed_runtime_delta'):o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('name',sorted(o.PROJECT_RUNTIME_BEFORE))
def test_every_existing_beforepin_is_required(runtime,name):
    s=runtime;old=copy.deepcopy(s['previous']);old['project_files'][name]='0'*64
    s['request']['previous_input']=doc(Path(s['request']['previous_input']['path']),old)
    doc(s['requestpath'],s['request']);before=snapshot(s['home'])
    with pytest.raises(ValueError,match='reviewed_runtime_delta'):o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


def test_wrong_file_owner_rejected_before_effects(runtime,monkeypatch):
    s=runtime;before=snapshot(s['home']);uid=os.getuid()
    monkeypatch.setattr(os,'getuid',lambda:uid+1)
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


def test_exclusive_new_file_race_preserves_foreign_inode(runtime,monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s=runtime;original=os.link;foreign={};target=s['home']/sorted(o.PROJECT_RUNTIME_NEW)[0]
    def race(source,destination,**kwargs):
        if Path(destination)==target and not foreign:
            put(target,b'concurrent owner\n');foreign.update(state=o.update_file_state(target))
        return original(source,destination,**kwargs)
    monkeypatch.setattr(os,'link',race)
    with pytest.raises(StopUnconfirmed):o.update(s['request'],s['requestpath'],Budget(180))
    assert o.update_file_state(target)==foreign['state']
    assert not target.with_name(target.name+'.ordinary-staged').exists()
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert not (tx/'committed.json').exists() and not (tx/'rolled-back.json').exists()


def test_foreign_staging_is_retained(runtime):
    s=runtime;target=s['home']/sorted(o.PROJECT_RUNTIME_NEW)[0]
    staged=target.with_name(target.name+'.ordinary-staged');put(staged,b'foreign staging inode\n')
    # Inventory rejects an unapproved staging path before creating the journal.
    state=o.update_file_state(staged);before=snapshot(s['home'])
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before and o.update_file_state(staged)==state
