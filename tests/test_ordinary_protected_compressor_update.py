"""Synthetic Source86 -> Source87; actual staged Git apply and file publication.

Service and native package checks are explicit synthetic fixtures. No PM install,
real source home, service, database, network or model effect is exercised here.
"""
import copy
import difflib
import os
from pathlib import Path
import pytest
import test_ordinary_manual_compression_update as previous86
from test_ordinary_file_tool_contract_update import native77,spark79
from support_spark_source_update import doc,put,pin,snapshot,f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget
from scripts.dsh_prepare import StopUnconfirmed

ASSET='hermes_cli/data/protected_compressor/'+'5'*64
NEW_DIRECTORIES={'hermes_cli/data','hermes_cli/data/protected_compressor',ASSET,ASSET+'/model',ASSET+'/processor-evidence'}
NEW_FILES={'agent/compression_attempts.py','agent/protected_compressor_normalize.py','agent/protected_compressor_renderer.py'}|{ASSET+'/'+n for n in ('LICENSE','NOTICE','manifest.json','model/chat_template.jinja','model/config.json','model/generation_config.json','model/tokenizer.json','model/tokenizer_config.json','processor-evidence/preprocessor_config.json','processor-evidence/video_preprocessor_config.json')}
EXISTING={'agent/bounded_context.py','agent/context_compressor_multipass.py','hermes_cli/friday_credential_admission.py','pyproject.toml','uv.lock'}

@pytest.fixture
def installed(tmp_path,monkeypatch,request):
    real_path=o.__file__
    # Add dependency declarations to the synthetic base before its history is
    # committed. The source closure fixture still checks every receipt file.
    monkeypatch.setattr(o,'WEB_RUNTIME_HISTORY_FILES',o.WEB_RUNTIME_HISTORY_FILES|{'pyproject.toml','uv.lock'})
    with monkeypatch.context() as before:
        before.setattr(o,'__file__',str(tmp_path/'source86-updater.py'))
        put(Path(o.__file__),b'# exact archived Source86 updater\n')
        s=previous86.installed.__wrapped__(tmp_path,monkeypatch,request)
        o.update(s['req'],s['requestpath'],Budget(180))
    home,source,root=s['home'],s['source'],s['root']
    previous=copy.deepcopy(s['current']);prevref=s['req']['current_input']
    predecessor=pin(s['requestpath']);history=dict(s['req']['transaction_history'])
    tx=home/'preparation'/('ordinary-source-update-'+s['req']['previous_input']['sha256'])
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
    receipt=f.read_json(home/'hermes-agent.source.json')
    profile_refs={n:pin(home/n) for n in o.WEB_INPUT_PROFILE_FILES}
    pm_lock=home/'installs'/f.digest(str(source).encode('utf-8'))[:16]/'.install.lock'
    put(pm_lock,b'',0o600);pm_lock.parent.parent.chmod(0o700)
    native_files=EXISTING|NEW_FILES;rows=[];patches=[]
    for n in sorted(native_files):
        added=n in NEW_FILES;old=b'' if added else (source/n).read_bytes()
        new=(b'{"fixture":"'+b'x'*131072+b'"}\n' if n.endswith('/tokenizer.json') else old+('# Source87 '+n+'\n').encode())
        rows.append(dict(path=n,before_sha256=None if added else f.digest(old),sha256=f.digest(new),bytes=len(new),mode='100644',new_file=added))
        patches.append('diff --git a/'+n+' b/'+n+'\n'+('new file mode 100644\n' if added else '')+''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='/dev/null' if added else 'a/'+n,tofile='b/'+n)))
    patchref=put(root/o.PROTECTED_COMPRESSOR_PATCH,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':o.PROTECTED_COMPRESSOR_PATCH,'patch_sha256':patchref['sha256'],'files':rows,
        'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in receipt['layers']},
        'prerequisites':{o.MANUAL_COMPRESSION_PATCH:previous['project_files'][o.MANUAL_COMPRESSION_PATCH]}}
    manifestref=doc(root/o.PROTECTED_COMPRESSOR_MANIFEST,manifest)
    current=copy.deepcopy(previous);current['project_files'].update({o.PROTECTED_COMPRESSOR_MANIFEST:manifestref['sha256'],o.PROTECTED_COMPRESSOR_PATCH:patchref['sha256'],
        'scripts/friday_ordinary_install.py':put(root/'scripts/friday_ordinary_install.py',Path(real_path).read_bytes())['sha256']})
    req={k:v for k,v in s['req'].items() if k!='worker_archive'}
    req.update(schema='friday.ordinary-telegram-source-update.v41',previous_input=prevref,
        current_input=doc(tmp_path/'source87-input.json',current),marker=pin(home/f.MARKER),source_receipt=pin(home/'hermes-agent.source.json'),
        stamp=pin(source/'install-stamp.json'),transaction_history=history,predecessor_update=predecessor,retained_profile_files=profile_refs)
    requestpath=tmp_path/'source87-request.json';doc(requestpath,req)
    for k,v in {'MANIFEST_SHA256':manifestref['sha256'],'PATCH_SHA256':patchref['sha256'],'FILES':native_files,'NEW_FILES':NEW_FILES,'NEW_DIRECTORIES':NEW_DIRECTORIES,
        'PREVIOUS_INPUT':prevref['sha256'],'PREDECESSOR_REQUEST':predecessor['sha256'],'PREDECESSOR_COMMITTED':pin(tx/'committed.json')['sha256'],
        'PREVIOUS_UPDATER':previous['project_files']['scripts/friday_ordinary_install.py'],'NATIVE_FILES':len(receipt['files']),'HISTORY_FILES':len(history)}.items():
        monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_'+k,v)
    return {**s,**locals()}


def transaction(s): return s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])

def assert_rolled_back(s,before):
    after=snapshot(s['home']);assert all(after[n]==value for n,value in before.items())
    assert all(not os.path.lexists(s['source']/n) for n in NEW_FILES|NEW_DIRECTORIES)
    assert f.read_json(transaction(s)/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))


def test_source87_real_patch_receipt_and_preservation(installed):
    s=installed;before={n:o.update_file_state(s['home']/n) for n in snapshot(s['home'])}
    result=o.update(s['req'],s['requestpath'],Budget(180))
    assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    receipt=f.read_json(s['home']/'hermes-agent.source.json')
    assert len(receipt['layers'])==86 and set(receipt['files'])==set(s['receipt']['files'])|NEW_FILES
    assert all(f.digest((s['source']/r['path']).read_bytes())==r['sha256'] for r in s['rows'])
    assert all((s['source']/n).is_dir() and (s['source']/n).stat().st_mode&0o777==0o700 for n in NEW_DIRECTORIES)
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'}|{'hermes-agent/'+n for n in EXISTING}
    assert all(o.update_file_state(s['home']/n)==v for n,v in before.items() if n not in changed)
    intent=f.read_json(transaction(s)/'intent.json')
    assert intent['new_directories']==sorted('hermes-agent/'+n for n in NEW_DIRECTORIES)
    assert all(intent['before']['hermes-agent/'+n]=={'absent':True} for n in NEW_FILES)
    assert set(f.read_json(transaction(s)/'created-directories.json'))==set(intent['new_directories'])
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('number',range(1,len(NEW_FILES|EXISTING)+4))
def test_every_publication_failure_rolls_back_new_directories(installed,monkeypatch,number):
    s=installed;original=o.publish_update_file;calls=0;before=snapshot(s['home'])
    def fail(*a,**kw):
        nonlocal calls
        calls+=1
        if calls==number:raise ValueError('synthetic publication failure')
        return original(*a,**kw)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))
    assert_rolled_back(s,before)


@pytest.mark.parametrize('kind',['foreign','symlink','file'])
def test_preexisting_asset_parent_refuses_before_consumption(installed,kind):
    s=installed;p=s['source']/'hermes_cli/data'
    if kind=='foreign':p.mkdir(mode=0o700)
    elif kind=='symlink':p.symlink_to(s['source']/'agent',target_is_directory=True)
    else:put(p,b'foreign data parent')
    before=snapshot(s['home'])
    with pytest.raises((ValueError,OSError)):o.update(s['req'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before and not transaction(s).exists()


@pytest.mark.parametrize('kind',['replace','symlink','foreign_child'])
def test_new_nested_directory_custody_loss_preserves_foreign(installed,monkeypatch,kind):
    s=installed;original=o.publish_update_file;done=False;target=s['source']/ASSET/'model'
    foreign=s['tmp_path']/'foreign-model';foreign.mkdir(mode=0o700);put(foreign/'sentinel',b'foreign')
    displaced=s['tmp_path']/'displaced-model'
    def race(path,*a,**kw):
        nonlocal done
        result=original(path,*a,**kw)
        if not done and str(path.relative_to(s['source'])) in NEW_FILES:
            done=True
            if kind=='foreign_child':put(target/'foreign',b'foreign')
            else:
                target.rename(displaced)
                if kind=='replace':target.mkdir(mode=0o700);put(target/'sentinel',b'foreign')
                else:target.symlink_to(foreign,target_is_directory=True)
        return result
    monkeypatch.setattr(o,'publish_update_file',race)
    with pytest.raises(StopUnconfirmed):o.update(s['req'],s['requestpath'],Budget(180))
    assert done and (foreign/'sentinel').read_bytes()==b'foreign'
    assert (target/('foreign' if kind=='foreign_child' else 'sentinel')).read_bytes()==b'foreign'
    assert not (transaction(s)/'committed.json').exists() and not (transaction(s)/'rolled-back.json').exists()


@pytest.mark.parametrize('kind',['new_asset','new_module','existing','marker'])
def test_same_bytes_foreign_inode_is_not_rolled_back(installed,monkeypatch,kind):
    s=installed;original=o.publish_update_file;foreign=None
    n={'new_asset':'hermes-agent/'+ASSET+'/model/config.json','new_module':'hermes-agent/agent/compression_attempts.py',
       'existing':'hermes-agent/pyproject.toml','marker':f.MARKER}[kind]
    def race(path,*a,**kw):
        nonlocal foreign
        result=original(path,*a,**kw)
        if str(path.relative_to(s['home']))==n:
            other=path.with_name('foreign-file');put(other,path.read_bytes(),path.stat().st_mode&0o777)
            os.replace(other,path);foreign=o.update_file_state(path)
            raise RuntimeError('lost custody')
        return result
    monkeypatch.setattr(o,'publish_update_file',race)
    with pytest.raises(StopUnconfirmed):o.update(s['req'],s['requestpath'],Budget(180))
    assert foreign is not None and o.same_update_file(s['home']/n,foreign)
    assert not (transaction(s)/'rolled-back.json').exists()


@pytest.mark.parametrize('fault',['pending_manifest','pending_patch','pending_files','pending_new_files','pending_dirs','pending_history',
    'wrong_input','wrong_predecessor','wrong_committed','wrong_updater','wrong_patch','wrong_manifest','history_missing','profile_changed',
    'extra_archive','foreign_module','bad_before','wrong_new_classification','undeclared_directory','extra_directory','parent_traversal'])
def test_invalid_source87_boundary_refuses_before_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req'];home=s['home']
    constants={'pending_manifest':('MANIFEST_SHA256',None),'pending_patch':('PATCH_SHA256',None),'pending_files':('FILES',None),
        'pending_new_files':('NEW_FILES',None),'pending_dirs':('NEW_DIRECTORIES',None),'pending_history':('HISTORY_FILES',None),
        'wrong_input':('PREVIOUS_INPUT','0'*64),'wrong_predecessor':('PREDECESSOR_REQUEST','0'*64),'wrong_committed':('PREDECESSOR_COMMITTED','0'*64),
        'wrong_updater':('PREVIOUS_UPDATER','0'*64),'wrong_patch':('PATCH_SHA256','0'*64),'wrong_manifest':('MANIFEST_SHA256','0'*64)}
    if fault in constants:
        k,v=constants[fault];monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_'+k,v)
    elif fault=='history_missing':req['transaction_history'].pop(next(iter(req['transaction_history'])))
    elif fault=='profile_changed':put(home/'profiles/dest_telegram/config.yaml',b'foreign admin edit')
    elif fault=='extra_archive':req['worker_archive']=s['archive_ref']
    elif fault=='foreign_module':put(s['source']/'agent/compression_attempts.py',b'foreign')
    elif fault=='undeclared_directory':monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_NEW_DIRECTORIES',NEW_DIRECTORIES-{ASSET+'/model'})
    elif fault=='extra_directory':monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_NEW_DIRECTORIES',NEW_DIRECTORIES|{'unused'})
    elif fault=='parent_traversal':monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_NEW_DIRECTORIES',NEW_DIRECTORIES|{'hermes_cli/../foreign'})
    else:
        row=s['manifest']['files'][0];row['before_sha256']='0'*64 if fault=='bad_before' else None
        if fault=='wrong_new_classification':row['new_file']=not row['new_file']
        ref=doc(s['root']/o.PROTECTED_COMPRESSOR_MANIFEST,s['manifest']);s['current']['project_files'][o.PROTECTED_COMPRESSOR_MANIFEST]=ref['sha256']
        req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_MANIFEST_SHA256',ref['sha256'])
    doc(s['requestpath'],req);before=snapshot(home)
    with pytest.raises((ValueError,KeyError,AssertionError,OSError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(home)==before and not transaction(s).exists()


def test_rehashed_patch_wrong_afterimage_rolls_back_exactly(installed,monkeypatch):
    s=installed;path=s['root']/o.PROTECTED_COMPRESSOR_PATCH
    ref=put(path,path.read_bytes().replace(b'# Source87 agent/compression_attempts.py',b'# WRONG87 agent/compression_attempts.py'))
    s['manifest']['patch_sha256']=ref['sha256'];m=doc(s['root']/o.PROTECTED_COMPRESSOR_MANIFEST,s['manifest'])
    s['current']['project_files'].update({o.PROTECTED_COMPRESSOR_PATCH:ref['sha256'],o.PROTECTED_COMPRESSOR_MANIFEST:m['sha256']})
    s['req']['current_input']=doc(Path(s['req']['current_input']['path']),s['current']);doc(s['requestpath'],s['req'])
    monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_PATCH_SHA256',ref['sha256']);monkeypatch.setattr(o,'PROTECTED_COMPRESSOR_MANIFEST_SHA256',m['sha256'])
    before=snapshot(s['home'])
    with pytest.raises(ValueError,match='ordinary_update_patch_output_changed'):o.update(s['req'],s['requestpath'],Budget(180))
    assert_rolled_back(s,before)


test_source87_writer_locks=previous86.test_source86_locks
test_source87_admin_drift=previous86.test_postpublication_profile_drift_is_preserved_and_source_rolled_back
test_source87_final_validation=previous86.test_source86_final_validation


def test_unbound_source87_rejects_before_runtime_paths(monkeypatch):
    fields={'schema','seconds','home','previous_input','current_input','marker','source_receipt','stamp','configuration','profile','launcher','credential_files','native_unit','transaction_history','predecessor_update','retained_profile_files'}
    req=dict.fromkeys(fields);req.update(schema='friday.ordinary-telegram-source-update.v41',seconds=180)
    def denied(*a,**kw):raise AssertionError('unbound candidate accessed runtime')
    monkeypatch.setattr(f,'directory',denied)
    with pytest.raises(ValueError,match='ordinary_update_final_protected_compressor_pins_required'):o.update_inputs(req,Budget(180))


@pytest.mark.parametrize('kind',['held','missing','symlink','payload','replaced'])
def test_native_pm_lock_refuses_or_retains_custody(installed,monkeypatch,kind):
    import fcntl
    s=installed;path=s['pm_lock'];fd=None
    if kind=='held':
        fd=os.open(path,os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    elif kind=='missing':path.unlink()
    elif kind=='symlink':path.unlink();path.symlink_to(s['source']/'.web_ui_build.lock')
    elif kind=='payload':put(path,b'foreign lock')
    else:
        original=o.publish_update_file;done=False
        def race(*a,**kw):
            nonlocal done
            result=original(*a,**kw)
            if not done:
                done=True;other=path.with_name('foreign');put(other,b'');os.replace(other,path)
            return result
        monkeypatch.setattr(o,'publish_update_file',race)
    before=snapshot(s['home'])
    try:
        with pytest.raises((ValueError,OSError,StopUnconfirmed)):o.update(s['req'],s['requestpath'],Budget(180))
        if kind!='replaced':assert snapshot(s['home'])==before and not transaction(s).exists()
        else:assert not (transaction(s)/'committed.json').exists() and not (transaction(s)/'rolled-back.json').exists()
    finally:
        if fd is not None:os.close(fd)


def test_directory_publication_refuses_racing_foreign_target(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir(mode=0o700)
    stage=tmp_path/'transaction-directories'
    foreign=tmp_path/'foreign';foreign.mkdir(mode=0o700);inode=foreign.stat().st_ino
    original=o.rename_directory_noreplace;done=False
    def race(srcfd,src,dstfd,dst):
        nonlocal done
        if dst=='assets' and not done:done=True;foreign.rename(home/'assets')
        return original(srcfd,src,dstfd,dst)
    with o.SourceUpdateDirectories(home,['assets/config.json'],{'assets'}) as directories:
        monkeypatch.setattr(o,'rename_directory_noreplace',race)
        with pytest.raises(FileExistsError):directories.create(stage)
        assert done and (home/'assets').stat().st_ino==inode and not directories.created
        assert (stage/next(n for n in os.listdir(stage) if n.startswith('new-'))).is_dir()


def test_directory_rollback_quarantines_and_restores_racing_foreign_target(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir(mode=0o700);stage=tmp_path/'transaction-directories'
    foreign=tmp_path/'foreign';foreign.mkdir(mode=0o700);inode=foreign.stat().st_ino
    original=o.rename_directory_noreplace;done=False
    with o.SourceUpdateDirectories(home,['assets/config.json'],{'assets'}) as directories:
        directories.create(stage)
        def race(srcfd,src,dstfd,dst):
            nonlocal done
            if src=='assets' and not done:
                done=True;(home/'assets').rename(tmp_path/'owned-displaced');foreign.rename(home/'assets')
            return original(srcfd,src,dstfd,dst)
        monkeypatch.setattr(o,'rename_directory_noreplace',race)
        with pytest.raises(ValueError,match='ordinary_update_directory_ownership_changed'):directories.remove_created()
        assert done and (home/'assets').stat().st_ino==inode
        assert (tmp_path/'owned-displaced').is_dir()


def test_pinned_parent_cannot_redirect_publication_into_foreign_symlink(tmp_path):
    home=tmp_path/'home';home.mkdir(mode=0o700);assets=home/'assets';assets.mkdir(mode=0o700)
    foreign=tmp_path/'foreign';foreign.mkdir(mode=0o700)
    with o.SourceUpdateDirectories(home,['assets/config.json'],set()) as directories:
        assets.rename(tmp_path/'owned-displaced');assets.symlink_to(foreign,target_is_directory=True)
        o.publish_update_file(assets/'config.json',b'owned',0o600,None,{},'assets/config.json',parent_fd=directories.parent_fd('assets/config.json'))
        assert not (foreign/'config.json').exists() and (tmp_path/'owned-displaced/config.json').read_bytes()==b'owned'
        with pytest.raises(ValueError):directories.prove()


@pytest.mark.parametrize('kind',['build','pm'])
def test_lock_acquisition_never_adopts_same_bytes_replacement(tmp_path,monkeypatch,kind):
    import fcntl
    home=tmp_path/'home';home.mkdir(mode=0o700);source=home/'hermes-agent';source.mkdir(mode=0o700)
    path=source/'.web_ui_build.lock' if kind=='build' else home/'installs'/f.digest(str(source).encode())[:16]/'.install.lock'
    put(path,b'',0o600)
    if kind=='pm':path.parent.parent.chmod(0o700)
    fd=os.open(path,os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    original=f.owned_file;done=False;old=path.with_name('held-old-lock')
    def race(target,*a,**kw):
        nonlocal done
        result=original(target,*a,**kw)
        if Path(target)==path and not done:
            done=True;path.rename(old);put(path,b'',0o600)
        return result
    monkeypatch.setattr(f,'owned_file',race)
    try:
        with pytest.raises(ValueError,match='ordinary_update_native_build_lock_changed'):
            with (o.retained_build_lock(source) if kind=='build' else o.retained_pm_lock(home,source)):pass
        assert done and old.stat().st_ino==os.fstat(fd).st_ino and old.stat().st_ino!=path.stat().st_ino
    finally:os.close(fd)
