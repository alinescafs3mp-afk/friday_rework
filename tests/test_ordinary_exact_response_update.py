"""Source87→88 real private Git/publication; native/service admission is synthetic."""
import copy,difflib,os,stat
from pathlib import Path
import pytest
import test_ordinary_bundle_update as bundled
from test_ordinary_file_tool_contract_update import native77,spark79
from support_spark_source_update import f,put,doc,pin,snapshot
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget
from scripts.dsh_prepare import StopUnconfirmed

@pytest.fixture
def installed(tmp_path,monkeypatch,request):
    real_path=o.__file__
    # Commit genuine synthetic v42 first, retaining all recursive real journals.
    with monkeypatch.context() as before:
        before.setattr(o,'__file__',str(tmp_path/'source87-updater.py'))
        put(Path(o.__file__),b'# archived source87 updater\n')
        s=bundled.installed.__wrapped__(tmp_path,monkeypatch,request)
        o.update(s['req'],s['requestpath'],Budget(180))
    home,source,root=s['home'],s['source'],s['root']
    previous=copy.deepcopy(s['current']);prevref=s['req']['current_input'];predecessor=pin(s['requestpath'])
    history=dict(s['req']['transaction_history']);oldtx=bundled.transaction(s)
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in oldtx.rglob('*') if p.is_file()})
    receipt=f.read_json(home/'hermes-agent.source.json')
    rows=[];patch=[]
    for name in sorted(o.EXACT_RESPONSE_FILES):
        if not (source/name).exists():
            data=b'# source87 exact response before\n';put(source/name,data,0o644)
            receipt['files'][name]=dict(sha256=f.digest(data),bytes=len(data),mode='100644')
        old=(source/name).read_bytes();new=old+b'# reviewed source88 exact response\n'
        rows.append(dict(path=name,before_sha256=f.digest(old),sha256=f.digest(new),bytes=len(new),mode='100644',new_file=False))
        patch.append('diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name)))
    receiptref=doc(home/'hermes-agent.source.json',receipt)
    marker=f.read_json(home/f.MARKER);marker['source_receipt_sha256']=receiptref['sha256'];marker['ordinary_gateway']['source_receipt_sha256']=receiptref['sha256'];doc(home/f.MARKER,marker)
    committed=f.read_json(oldtx/'committed.json');committed['source_receipt_sha256']=receiptref['sha256'];doc(oldtx/'committed.json',committed)
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in oldtx.rglob('*') if p.is_file()})
    patchref=put(root/o.EXACT_RESPONSE_PATCH,''.join(patch).encode())
    manifest=dict(base_commit=receipt['commit'],patch=o.EXACT_RESPONSE_PATCH,patch_sha256=patchref['sha256'],files=rows,
        installed_prefix={row['manifest']:row['manifest_sha256'] for row in receipt['layers']},
        prerequisites={o.BUNDLE_PATCHES[-1]:previous['project_files'][o.BUNDLE_PATCHES[-1]]})
    manifestref=doc(root/o.EXACT_RESPONSE_MANIFEST,manifest)
    current=copy.deepcopy(previous);current['project_files'].update({o.EXACT_RESPONSE_MANIFEST:manifestref['sha256'],o.EXACT_RESPONSE_PATCH:patchref['sha256'],
        'scripts/friday_ordinary_install.py':put(root/'scripts/friday_ordinary_install.py',Path(real_path).read_bytes())['sha256']})
    # Fresh legitimate owner/tester data added after the v42 request.
    put(home/'profiles/own_tester/state.db',b'opaque fixture 25 legitimate messages\n')
    put(home/'platforms/pairing/telegram-approved.json',b'opaque current account permission fixture\n')
    put(home/'plugin-data/native/access.json',b'opaque product access registry fixture\n')
    put(home/'user-artifacts/owner.txt',b'legitimate retained user artifact\n')
    put(home/'kanban.db',b'opaque retained task database\n')
    put(home/'state.db',b'opaque current root history\n')
    for name in o.EXACT_RESPONSE_BINDING_FILES:put(home/name,b'opaque inactive current renderer binding\n')
    req={**s['req'], 'schema':o.EXACT_RESPONSE_SCHEMA,'previous_input':prevref,'predecessor_update':predecessor,
        'current_input':doc(tmp_path/'source88-input.json',current),'marker':pin(home/f.MARKER),
        'source_receipt':receiptref,'stamp':pin(source/'install-stamp.json'),'transaction_history':history,
        'retained_data_directories':o.source88_retained_inventory(home,Budget(180))[1],
        'retained_data_files':{n:{**pin(home/n),'mode':stat.S_IMODE((home/n).stat().st_mode)} for n in o.source88_retained_paths(home,Budget(180))}}
    requestpath=tmp_path/'source88-request.json';doc(requestpath,req)
    for key,value in dict(MANIFEST_SHA256=manifestref['sha256'],PATCH_SHA256=patchref['sha256'],PREVIOUS_INPUT=prevref['sha256'],
            PREDECESSOR_REQUEST=predecessor['sha256'],PREDECESSOR_COMMITTED=pin(oldtx/'committed.json')['sha256'],
            PREVIOUS_UPDATER=previous['project_files']['scripts/friday_ordinary_install.py'],NATIVE_FILES=len(receipt['files'])).items():monkeypatch.setattr(o,'EXACT_RESPONSE_'+key,value)
    for path in [home,*home.rglob('*')]:
        if path.is_dir():path.chmod(0o700)
    # Legitimate native directories beneath the admitted private home.
    (home/'platforms').chmod(0o775);(home/'platforms/pairing').chmod(0o775)
    req['retained_data_directories']=o.source88_retained_inventory(home,Budget(180))[1]
    doc(requestpath,req)
    return {**s,**locals()}

def tx(s):return s['home']/'preparation'/('ordinary-source-update-'+s['req']['previous_input']['sha256'])

def test_commits_exact_two_files_preserves_current_owner_tester_data(installed):
    s=installed;before={n:o.update_file_state(s['home']/n) for n in snapshot(s['home'])};result=o.update(s['req'],s['requestpath'],Budget(180))
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    receipt=f.read_json(s['home']/'hermes-agent.source.json');assert len(receipt['layers'])==88 and receipt['layers'][:-1]==s['receipt']['layers']
    assert set(receipt['files'])==set(s['receipt']['files']);assert len(f.read_json(tx(s)/'intent.json')['before'])==5
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'}|{'hermes-agent/'+n for n in o.EXACT_RESPONSE_FILES}
    assert all(o.update_file_state(s['home']/n)==state for n,state in before.items() if n not in changed)
    o.checked_source88_retained(s['home'],s['req'],Budget(180))
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('fault',['missing_data','extra_data','missing_directory','directory_mode','directory_replaced','world_writable_directory','missing_permissions','changed_permissions','missing_plugin_data','changed_artifact','changed_kanban','stale_tester','changed_mode','wrong_path','missing_binding','binding_mode','profile_symlink','wrong_previous','wrong_commit','wrong_updater','extra_project','changed_setting','history_missing','foreign_native','extra_manifest_file','layer_order','unknown_field'])
def test_refuses_changed_ancestry_data_and_scope_before_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req'];home=s['home'];own='profiles/own_tester/state.db'
    if fault=='missing_data':req['retained_data_files'].pop(own)
    elif fault=='missing_directory':req['retained_data_directories'].pop('platforms/pairing')
    elif fault=='directory_mode':(home/'platforms/pairing').chmod(0o755)
    elif fault=='directory_replaced':
        original=home/'platforms/pairing';new=home/'platforms/replacement';original.rename(new);original.mkdir(mode=0o700);(new/'telegram-approved.json').rename(original/'telegram-approved.json');new.rmdir()
    elif fault=='world_writable_directory':(home/'platforms/pairing').chmod(0o777)
    elif fault=='missing_permissions':req['retained_data_files'].pop('platforms/pairing/telegram-approved.json')
    elif fault=='changed_permissions':put(home/'platforms/pairing/telegram-approved.json',b'foreign account approval\n')
    elif fault=='missing_plugin_data':req['retained_data_files'].pop('plugin-data/native/access.json')
    elif fault=='changed_artifact':put(home/'user-artifacts/owner.txt',b'legitimate newer artifact\n')
    elif fault=='changed_kanban':put(home/'kanban.db',b'newer legitimate task\n')
    elif fault=='extra_data':req['retained_data_files']['unowned']=dict(req['retained_data_files'][own])
    elif fault=='stale_tester':put(home/own,b'legitimate newer message\n')
    elif fault=='changed_mode':(home/own).chmod(0o644)
    elif fault=='wrong_path':req['retained_data_files'][own]['path']=str(home/'state.db')
    elif fault=='missing_binding':(home/next(iter(o.EXACT_RESPONSE_BINDING_FILES))).unlink()
    elif fault=='binding_mode':(home/next(iter(o.EXACT_RESPONSE_BINDING_FILES))).chmod(0o644)
    elif fault=='profile_symlink':(home/'profiles/foreign').symlink_to(home/'profiles/own_tester',target_is_directory=True)
    elif fault=='wrong_previous':monkeypatch.setattr(o,'EXACT_RESPONSE_PREVIOUS_INPUT','0'*64)
    elif fault=='wrong_commit':monkeypatch.setattr(o,'EXACT_RESPONSE_PREDECESSOR_COMMITTED','0'*64)
    elif fault=='wrong_updater':monkeypatch.setattr(o,'EXACT_RESPONSE_PREVIOUS_UPDATER','0'*64)
    elif fault=='extra_project':s['current']['project_files']['unexpected']=put(s['root']/'unexpected',b'x')['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current'])
    elif fault=='changed_setting':s['current']['model']='other';req['current_input']=doc(Path(req['current_input']['path']),s['current'])
    elif fault=='history_missing':req['transaction_history'].pop(next(iter(req['transaction_history'])))
    elif fault=='foreign_native':put(s['source']/next(iter(o.EXACT_RESPONSE_FILES)),b'foreign native bytes',0o644)
    elif fault=='extra_manifest_file':
        s['manifest']['files'].append(dict(s['rows'][0],path='foreign.py'));ref=doc(s['root']/o.EXACT_RESPONSE_MANIFEST,s['manifest']);s['current']['project_files'][o.EXACT_RESPONSE_MANIFEST]=ref['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'EXACT_RESPONSE_MANIFEST_SHA256',ref['sha256'])
    elif fault=='layer_order':
        s['receipt']['layers'][-1],s['receipt']['layers'][-2]=s['receipt']['layers'][-2],s['receipt']['layers'][-1];req['source_receipt']=doc(home/'hermes-agent.source.json',s['receipt']);marker=f.read_json(home/f.MARKER);marker['source_receipt_sha256']=req['source_receipt']['sha256'];req['marker']=doc(home/f.MARKER,marker)
    elif fault=='unknown_field':req['relax_scope']=True
    before=snapshot(home)
    with pytest.raises(AssertionError if fault=='foreign_native' else (ValueError,KeyError)):o.update_inputs(req,Budget(180))
    assert snapshot(home)==before and not tx(s).exists()

@pytest.mark.parametrize('number',range(1,6))
def test_each_publication_failure_rolls_back_only_owned_files(installed,monkeypatch,number):
    s=installed;before=snapshot(s['home']);original=o.publish_update_file;calls=0
    def fail(*a,**kw):
        nonlocal calls
        calls+=1
        if calls==number:raise ValueError('primary publication failure')
        return original(*a,**kw)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(ValueError,match='primary publication failure'):o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home']);assert all(after[n]==state for n,state in before.items());assert f.read_json(tx(s)/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'

@pytest.mark.parametrize('fault',['absent','partial','visible','sync'])
def test_commit_ambiguity_retains_forward_bytes_without_clean_rollback(installed,monkeypatch,fault):
    s=installed;original_write=o.write;original_sync=o.sync_directory;original=OSError('commit ambiguity')
    def write(path,data,*a,**kw):
        if Path(path)==tx(s)/'committed.json' and fault!='sync':
            if fault=='partial':Path(path).write_bytes(b'{"partial":')
            elif fault=='visible':original_write(path,data,*a,**kw)
            raise original
        return original_write(path,data,*a,**kw)
    def sync(path):
        if Path(path)==tx(s) and (tx(s)/'committed.json').exists() and fault=='sync':raise original
        return original_sync(path)
    monkeypatch.setattr(o,'write',write);monkeypatch.setattr(o,'sync_directory',sync)
    with pytest.raises(StopUnconfirmed) as caught:o.update(s['req'],s['requestpath'],Budget(180))
    assert caught.value.__cause__ is original;assert not (tx(s)/'rolled-back.json').exists()
    assert len(f.read_json(s['home']/'hermes-agent.source.json')['layers'])==88
    assert f.read_json(tx(s)/'intent.json')['state']=='SOURCE_UPDATE_CONSUMED_NO_RETRY'

@pytest.mark.parametrize('fault',['expired_scan','count_bound','byte_bound','expired_hash'])
def test_retained_checks_share_original_budget_and_fixed_limits(tmp_path,monkeypatch,fault):
    import time
    home=tmp_path/'bounded-retained';home.mkdir(mode=0o700)
    for name in o.EXACT_RESPONSE_BINDING_FILES:put(home/name,b'opaque binding\n')
    put(home/'profiles/own_tester/state.db',b'opaque 25 messages\n')
    for path in home.rglob('*'):
        if path.is_dir():path.chmod(0o700)
    budget=Budget(180);deadline=budget.deadline
    if fault=='expired_scan':budget.deadline=time.monotonic()-1
    elif fault=='count_bound':monkeypatch.setattr(o,'EXACT_RESPONSE_RETAINED_MAX_FILES',0)
    elif fault=='byte_bound':monkeypatch.setattr(o,'EXACT_RESPONSE_RETAINED_MAX_BYTES',0)
    elif fault=='expired_hash':
        refs={n:{**pin(home/n),'mode':stat.S_IMODE((home/n).stat().st_mode)} for n in o.source88_retained_paths(home,budget)}
        original=f.pin
        def pin_expire(ref):
            result=original(ref);budget.deadline=time.monotonic()-1;return result
        monkeypatch.setattr(f,'pin',pin_expire)
        with pytest.raises(ValueError,match='original_install_budget_exhausted'):o.checked_source88_retained(home,{'retained_data_files':refs,'retained_data_directories':o.source88_retained_inventory(home,budget)[1]},budget)
        assert budget.deadline<time.monotonic();return
    with pytest.raises(ValueError,match='original_install_budget_exhausted' if fault=='expired_scan' else 'ordinary_update_retained_resource_limit'):o.source88_retained_paths(home,budget)
    assert budget.deadline==deadline if fault!='expired_scan' else budget.deadline<time.monotonic()
