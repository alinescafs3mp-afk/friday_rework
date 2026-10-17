"""Source85 -> manual ordinary compression package86 layer85 preserves current admin edits and consumed history.

Synthetic homes only; real Git staging/publication/rollback. Native product
admission and service custody remain explicit fixtures, not runtime evidence.
"""
import copy,difflib,json,os
from pathlib import Path
import pytest
import test_ordinary_file_tool_contract_update as previous_test
import test_ordinary_web_runtime_history_update as previous85
from test_ordinary_file_tool_contract_update import native77,spark79
from support_spark_source_update import doc,put,pin,snapshot,f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget

SYNTHETIC_NATIVE_FILES = {'gateway/platforms/base.py','gateway/run_agent_cache.py','gateway/run_busy.py','gateway/run_shutdown.py','gateway/slash_commands.py','gateway/slash_commands_session.py','hermes_cli/friday_user_scope.py'}

@pytest.fixture
def installed(tmp_path,monkeypatch,request):
    real_path=o.__file__
    with monkeypatch.context() as before:
        before.setattr(o,'__file__',str(tmp_path/'source85-updater.py'))
        put(Path(o.__file__),b'# exact archived Source85 updater\n')
        s=previous85.installed.__wrapped__(tmp_path,monkeypatch,request)
        o.update(s['req'],s['requestpath'],Budget(180))
    home,source,root=s['home'],s['source'],s['root']
    previous=copy.deepcopy(s['current']);prevref=s['req']['current_input']
    predecessor=pin(s['requestpath']);history=dict(s['req']['transaction_history'])
    tx=home/'preparation'/('ordinary-source-update-'+s['req']['previous_input']['sha256'])
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
    receipt=f.read_json(home/'hermes-agent.source.json')
    # Legitimate selected-profile admin edit after Source81 closure. Its current
    # beforeimages must survive; the closed budget journal still contains auto.
    put(home/'profiles/dest_telegram/config.yaml',b'tools:\n  tool_search:\n    enabled: off\n')
    put(home/'profiles/dest_telegram/.friday-onboarding.json',b'{"config_sha256":"fixture-admin-after"}\n')
    put(home/'profiles/dest_telegram/.friday-user-scope.json',b'{"onboarding_sha256":"fixture-admin-after"}\n')
    profile_refs={n:pin(home/n) for n in o.WEB_INPUT_PROFILE_FILES}
    put(home/'profiles/dest_telegram/workspace/existing.txt',b'current revised file:36 bytes fixture')
    put(home/'profiles/dest_telegram/workspace/original.before',b'original beforeimage:38 bytes fixture!!')
    put(home/'profiles/dest_telegram/history/current.jsonl',b'{"native_user_turn":"retained exact local history"}\n')
    put(home/'profiles/dest_telegram/state.db',b'opaque unopened synthetic db')
    for number in range(3):put(home/f'profiles/dest_telegram/receipt-{number}.json',b'untouched file receipt')
    installed_ref=prevref
    previous['project_files']['scripts/friday_ordinary_install.py']=put(root/'scripts/friday_ordinary_install.py',b'# archived source85 current updater\n')['sha256']
    prevref=doc(tmp_path/'archived-source85-input.json',previous)
    marker=f.read_json(home/f.MARKER);marker['input_sha256']=prevref['sha256']
    marker['ordinary_gateway']['operator_entry']['input']=prevref;doc(home/f.MARKER,marker)
    archive_request={'schema':'friday.ordinary-closed-worker-reconciliation.v2','home':str(home),
        'profile':'dest_telegram','transition':'EXPLICIT_CLOSED_ARCHIVE_NO_RUNTIME_AUTHORITY',
        'current_update':predecessor,'installed_input':installed_ref,'recovery_input':prevref,
        'history':[{'path':str(home/n),'sha256':h} for n,h in history.items()], 'recovery_id':'synthetic-source85'}
    archive_ref=doc(tmp_path/'archive-request.json',archive_request)
    archive_tx=home/'preparation/ordinary-closed-reconciliation-synthetic-source85'
    failed=put(archive_tx/'failed-qualification/failure.json',b'closed failed attempt\n')
    state=o.update_file_state(Path(failed['path']));put(archive_tx/'failed-before/failure.json',state['data'])
    archived_marker=put(archive_tx/'before'/f.MARKER,b'archived marker before source85 archive\n')
    mapping={str(home/'profiles/dest_telegram/workers/qualification'):str(archive_tx/'failed-qualification')}
    archive_intent={'state':'CONSUMED_NO_RETRY','request_sha256':archive_ref['sha256'],
        'archive_mapping':mapping,'original_attempt':{'budget_seconds':300,'expired':True},
        'runtime_authority':'NOT_GRANTED','old_attempt_retry_authorized':False,
        'before':{f.MARKER:{'sha256':archived_marker['sha256']}},
        'tree':{'directories':{'.':[getattr((archive_tx/'failed-qualification').lstat(),k) for k in ('st_dev','st_ino','st_uid','st_mode')]},'files':{'failure.json':dict(sha256=failed['sha256'],bytes=len(state['data']),mode=state['mode'],identity=list(state['identity']))}}}
    archive_intent_ref=doc(archive_tx/'intent.json',archive_intent)
    archive_commit=dict(state='ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY',
        archive_mapping=mapping,original_attempt=archive_intent['original_attempt'],runtime_authority='NOT_GRANTED',
        **dict.fromkeys(('ready','runtime_acceptance','consumers_started','workers_enabled','resume_allowed','old_attempt_retry_authorized'),False))
    archive_commit_ref=doc(archive_tx/'committed.json',archive_commit)
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in archive_tx.rglob('*') if p.is_file()})
    for k,v in {'MANUAL_COMPRESSION_ARCHIVE_REQUEST':archive_ref['sha256'],
        'MANUAL_COMPRESSION_ARCHIVE_INTENT':archive_intent_ref['sha256'],
        'MANUAL_COMPRESSION_ARCHIVE_COMMITTED':archive_commit_ref['sha256']}.items():monkeypatch.setattr(o,k,v)
    native_files=set(o.MANUAL_COMPRESSION_FILES or SYNTHETIC_NATIVE_FILES)
    rows=[];patches=[]
    for n in sorted(native_files):
        old=(source/n).read_bytes();new=old+b'# reviewed credential preflight\n'
        rows.append(dict(path=n,before_sha256=f.digest(old),sha256=f.digest(new),bytes=len(new),mode='100644',new_file=False))
        patches.append('diff --git a/'+n+' b/'+n+'\n'+''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+n,tofile='b/'+n)))
    patchref=put(root/o.MANUAL_COMPRESSION_PATCH,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':o.MANUAL_COMPRESSION_PATCH,'patch_sha256':patchref['sha256'],'files':rows,
        'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in receipt['layers']},
        'prerequisites':{o.WEB_RUNTIME_HISTORY_PATCH:previous['project_files'][o.WEB_RUNTIME_HISTORY_PATCH]}}
    manifestref=doc(root/o.MANUAL_COMPRESSION_MANIFEST,manifest)
    current=copy.deepcopy(previous);current['project_files'].update({
        o.MANUAL_COMPRESSION_MANIFEST:manifestref['sha256'],o.MANUAL_COMPRESSION_PATCH:patchref['sha256'],
        'scripts/friday_ordinary_install.py':put(root/'scripts/friday_ordinary_install.py',Path(real_path).read_bytes())['sha256']})
    req={k:v for k,v in s['req'].items() if k!='inference_rebind'}
    req.update(schema='friday.ordinary-telegram-source-update.v40',previous_input=prevref,
        current_input=doc(tmp_path/'source86-input.json',current),marker=pin(home/f.MARKER),
        source_receipt=pin(home/'hermes-agent.source.json'),stamp=pin(source/'install-stamp.json'),
        transaction_history=history,predecessor_update=predecessor,retained_profile_files=profile_refs,worker_archive=archive_ref)
    requestpath=tmp_path/'source86-request.json';doc(requestpath,req)
    for k,v in {'MANUAL_COMPRESSION_MANIFEST_SHA256':manifestref['sha256'],'MANUAL_COMPRESSION_PATCH_SHA256':patchref['sha256'],
        'MANUAL_COMPRESSION_FILES':native_files,'MANUAL_COMPRESSION_PREVIOUS_INPUT':prevref['sha256'],
        'MANUAL_COMPRESSION_PREDECESSOR_REQUEST':predecessor['sha256'],
        'MANUAL_COMPRESSION_PREDECESSOR_COMMITTED':pin(tx/'committed.json')['sha256'],
        'MANUAL_COMPRESSION_PREVIOUS_UPDATER':previous['project_files']['scripts/friday_ordinary_install.py'],
        'MANUAL_COMPRESSION_NATIVE_FILES':len(receipt['files']),'MANUAL_COMPRESSION_HISTORY_FILES':len(history),
        'WEB_INPUT_SELECTED_CONFIG':profile_refs['profiles/dest_telegram/config.yaml']['sha256']}.items():monkeypatch.setattr(o,k,v)
    for directory in (p for p in home.rglob('*') if p.is_dir()):directory.chmod(0o700)
    return {**s,**locals()}

def test_update_preserves_current_admin_profile_and_closed_ancestry(installed):
    s=installed;before={n:o.update_file_state(s['home']/n) for n in snapshot(s['home'])}
    result=o.update(s['req'],s['requestpath'],Budget(180))
    assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    assert len(f.read_json(s['home']/'hermes-agent.source.json')['layers'])==85
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'}|{'hermes-agent/'+n for n in s['native_files']}
    assert all(o.update_file_state(s['home']/n)==v for n,v in before.items() if n not in changed)
    assert b'enabled: off' in (s['home']/'profiles/dest_telegram/config.yaml').read_bytes()
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('fault',['pending_files','wrong_committed','pending_manifest','pending_patch','wrong_input','wrong_predecessor','wrong_updater','history_missing','profile_missing','profile_extra','profile_path','profile_changed','proof_changed','scope_changed','key_changed','old_auto_hash','extra_plugin','extra_native','foreign_native','extra_rebind'])
def test_invalid_boundary_refuses_before_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req'];home=s['home']
    constants={'pending_files':('MANUAL_COMPRESSION_FILES',None),'wrong_committed':('MANUAL_COMPRESSION_PREDECESSOR_COMMITTED','0'*64),'pending_manifest':('MANUAL_COMPRESSION_MANIFEST_SHA256',None),'pending_patch':('MANUAL_COMPRESSION_PATCH_SHA256',None),
        'wrong_input':('MANUAL_COMPRESSION_PREVIOUS_INPUT','0'*64),'wrong_predecessor':('MANUAL_COMPRESSION_PREDECESSOR_REQUEST','0'*64),
        'wrong_updater':('MANUAL_COMPRESSION_PREVIOUS_UPDATER','0'*64),'old_auto_hash':('WEB_INPUT_SELECTED_CONFIG','0'*64)}
    if fault in constants:monkeypatch.setattr(o,*constants[fault])
    elif fault=='history_missing':req['transaction_history'].pop(next(iter(req['transaction_history'])))
    elif fault=='profile_missing':req['retained_profile_files'].pop('profiles/dest_telegram/config.yaml')
    elif fault=='profile_extra':req['retained_profile_files']['extra']=pin(home/'config.yaml')
    elif fault=='profile_path':req['retained_profile_files']['profiles/dest_telegram/config.yaml']['path']=str(home/'config.yaml')
    elif fault in ('profile_changed','proof_changed','scope_changed','key_changed'):
        n={'profile_changed':'config.yaml','proof_changed':'.friday-onboarding.json','scope_changed':'.friday-user-scope.json','key_changed':'.env'}[fault]
        put(home/'profiles/dest_telegram'/n,b'foreign bytes')
    elif fault=='extra_plugin':
        n='plugins/friday_rework/unchanged.py';s['current']['project_files'][n]=put(s['root']/n,b'foreign plugin')['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current'])
    elif fault=='extra_native':
        s['manifest']['files'].append(dict(s['rows'][0],path='other.py'));ref=doc(s['root']/o.MANUAL_COMPRESSION_MANIFEST,s['manifest']);s['current']['project_files'][o.MANUAL_COMPRESSION_MANIFEST]=ref['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'MANUAL_COMPRESSION_MANIFEST_SHA256',ref['sha256'])
    elif fault=='foreign_native':put(s['source']/next(iter(s['native_files'])),b'foreign',0o644)
    elif fault=='extra_rebind':req['inference_rebind']=s['budgetref']
    doc(s['requestpath'],req);before=snapshot(home)
    with pytest.raises((ValueError,KeyError,AssertionError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(home)==before

@pytest.mark.parametrize('number',range(1,len(o.MANUAL_COMPRESSION_FILES or SYNTHETIC_NATIVE_FILES)+4))
def test_every_publication_failure_retains_admin_and_rolls_back(installed,monkeypatch,number):
    s=installed;original=o.publish_update_file;calls=0;before=snapshot(s['home'])
    def fail(*a,**kw):
        nonlocal calls
        calls+=1
        if calls==number:raise ValueError('synthetic publication failure')
        return original(*a,**kw)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home']);assert all(after[n]==v for n,v in before.items())
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('name',sorted(o.WEB_INPUT_PROFILE_FILES))
def test_postpublication_profile_drift_is_preserved_and_source_rolled_back(installed,monkeypatch,name):
    s=installed;original=o.checked_source82_retained;calls=0
    def drift(*a,**kw):
        nonlocal calls
        calls+=1
        if calls==3:put(s['home']/name,b'foreign concurrent admin or key change')
        return original(*a,**kw)
    monkeypatch.setattr(o,'checked_source82_retained',drift)
    before=snapshot(s['home'])
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home']);assert all(after[n]==v for n,v in before.items() if n!=name)
    assert (s['home']/name).read_bytes()==b'foreign concurrent admin or key change'
    assert calls==3
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

test_source86_locks=previous_test.test_source81_existing_writer_locks
@pytest.mark.parametrize('kind',['native','marker'])
def test_source86_foreign_custody(installed,monkeypatch,kind):
    from scripts.dsh_prepare import StopUnconfirmed
    s=installed;original=o.publish_update_file;foreign=None
    name='hermes-agent/'+sorted(s['native_files'])[0] if kind=='native' else f.MARKER
    def lose(path,*args):
        nonlocal foreign
        result=original(path,*args)
        if str(path.relative_to(s['home']))==name:
            other=path.with_name('foreign-file');put(other,path.read_bytes(),path.stat().st_mode&0o777)
            os.replace(other,path);foreign=o.update_file_state(path)
            raise RuntimeError('lost custody')
        return result
    monkeypatch.setattr(o,'publish_update_file',lose)
    with pytest.raises(StopUnconfirmed):o.update(s['req'],s['requestpath'],Budget(180))
    assert foreign is not None and o.same_update_file(s['home']/name,foreign)
    with pytest.raises((ValueError,AssertionError)):o.update(s['req'],s['requestpath'],Budget(180))
test_source86_final_validation=previous_test.test_source81_final_validation
test_source86_original_archive=previous_test.test_source81_original_archive


@pytest.mark.parametrize('fault',['source82_prepared_predecessor','wrong_schema','operational_model','operational_budget','omitted_web','omitted_history'])
def test_combined_exactness_refuses_without_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req']
    if fault=='source82_prepared_predecessor':
        prepared=copy.deepcopy(s['req']);prepared['schema']='friday.ordinary-telegram-source-update.v36'
        req['predecessor_update']=doc(s['root']/'unexecuted-v36-request.json',prepared)
        monkeypatch.setattr(o,'MANUAL_COMPRESSION_PREDECESSOR_REQUEST',req['predecessor_update']['sha256'])
    elif fault=='wrong_schema':req['schema']='friday.ordinary-telegram-source-update.v36'
    elif fault in ('operational_model','operational_budget'):
        key='model' if fault=='operational_model' else 'original_budget'
        s['current'][key]='unauthorized change';req['current_input']=doc(Path(req['current_input']['path']),s['current'])
    else:
        target='gateway/run_busy.py' if fault=='omitted_web' else 'gateway/slash_commands_session.py'
        assert target in {r['path'] for r in s['manifest']['files']}
        s['manifest']['files']=[r for r in s['manifest']['files'] if r['path']!=target]
        ref=doc(s['root']/o.MANUAL_COMPRESSION_MANIFEST,s['manifest']);s['current']['project_files'][o.MANUAL_COMPRESSION_MANIFEST]=ref['sha256']
        req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'MANUAL_COMPRESSION_MANIFEST_SHA256',ref['sha256'])
    doc(s['requestpath'],req);before=snapshot(s['home'])
    with pytest.raises((ValueError,KeyError,AssertionError,OSError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('fault',['empty_files','invalid_files','wrong_manifest_sha','wrong_patch_sha','changed_history','extra_history','duplicate_target'])
def test_final_binding_and_complete_history_refuse_without_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req']
    constants={'empty_files':('MANUAL_COMPRESSION_FILES',set()),'invalid_files':('MANUAL_COMPRESSION_FILES',list(s['native_files'])),
        'wrong_manifest_sha':('MANUAL_COMPRESSION_MANIFEST_SHA256','0'*64),'wrong_patch_sha':('MANUAL_COMPRESSION_PATCH_SHA256','0'*64)}
    if fault in constants:monkeypatch.setattr(o,*constants[fault])
    elif fault=='changed_history':req['transaction_history'][next(iter(req['transaction_history']))]='0'*64
    elif fault=='extra_history':req['transaction_history']['preparation/foreign.json']='0'*64
    else:
        s['manifest']['files'][-1]=dict(s['manifest']['files'][0])
        ref=doc(s['root']/o.MANUAL_COMPRESSION_MANIFEST,s['manifest']);s['current']['project_files'][o.MANUAL_COMPRESSION_MANIFEST]=ref['sha256']
        req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'MANUAL_COMPRESSION_MANIFEST_SHA256',ref['sha256'])
    doc(s['requestpath'],req);before=snapshot(s['home'])
    with pytest.raises((ValueError,KeyError,AssertionError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


def test_prepared_candidate_refuses_before_any_runtime_path_read(monkeypatch):
    fields={'schema','seconds','home','previous_input','current_input','marker','source_receipt','stamp','configuration','profile','launcher','credential_files','native_unit','transaction_history','predecessor_update','retained_profile_files','worker_archive'}
    req=dict.fromkeys(fields);req.update(schema='friday.ordinary-telegram-source-update.v40',seconds=180)
    for name in ('MANUAL_COMPRESSION_MANIFEST_SHA256','MANUAL_COMPRESSION_PATCH_SHA256','MANUAL_COMPRESSION_FILES'):
        monkeypatch.setattr(o,name,None)
    def denied(*a,**kw):raise AssertionError('unbound candidate accessed runtime paths')
    monkeypatch.setattr(f,'directory',denied)
    with pytest.raises(ValueError,match='ordinary_update_final_manual_compression_pins_required'):
        o.update_inputs(req,Budget(180))


@pytest.mark.parametrize('fault', ['request_pin','intent_pin','commit_pin','wrong_installed_input',
    'wrong_recovery_input','wrong_predecessor','missing_original_history','extra_original_history',
    'retry_allowed','runtime_accepted','archive_bytes','archive_custody','archive_extra_file','archive_directory'])
def test_consumed_worker_archive_refuses_drift_without_consumption(installed, monkeypatch, fault):
    s=installed; req=s['req']; tx=s['archive_tx']
    constants={'request_pin':'MANUAL_COMPRESSION_ARCHIVE_REQUEST',
        'intent_pin':'MANUAL_COMPRESSION_ARCHIVE_INTENT','commit_pin':'MANUAL_COMPRESSION_ARCHIVE_COMMITTED'}
    if fault in constants:
        monkeypatch.setattr(o,constants[fault],'0'*64)
    elif fault in ('wrong_installed_input','wrong_recovery_input','wrong_predecessor','missing_original_history','extra_original_history'):
        value=copy.deepcopy(s['archive_request'])
        if fault=='wrong_installed_input':value['installed_input']=s['prevref']
        elif fault=='wrong_recovery_input':value['recovery_input']=s['installed_ref']
        elif fault=='wrong_predecessor':value['current_update']=s['installed_ref']
        elif fault=='missing_original_history':value['history'].pop()
        else:value['history'].append(dict(value['history'][0]))
        ref=doc(Path(s['archive_ref']['path']),value);req['worker_archive']=ref
        monkeypatch.setattr(o,'MANUAL_COMPRESSION_ARCHIVE_REQUEST',ref['sha256'])
    elif fault in ('retry_allowed','runtime_accepted'):
        value=copy.deepcopy(s['archive_commit'])
        value['old_attempt_retry_authorized' if fault=='retry_allowed' else 'runtime_acceptance']=True
        ref=doc(tx/'committed.json',value)
        monkeypatch.setattr(o,'MANUAL_COMPRESSION_ARCHIVE_COMMITTED',ref['sha256'])
    elif fault=='archive_bytes':put(tx/'failed-before/failure.json',b'changed failure')
    elif fault=='archive_custody':
        path=tx/'failed-qualification/failure.json'; other=tx/'foreign-file'
        put(other,path.read_bytes());os.replace(other,path)
    elif fault=='archive_directory':(tx/'failed-qualification/unknown').mkdir(mode=0o700)
    else:put(tx/'unrecorded.json',b'foreign history')
    doc(s['requestpath'],req); before=snapshot(s['home'])
    with pytest.raises((ValueError,KeyError,AssertionError)):
        o.update(req,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


def test_shipped_manual_compression_bindings_match_exact_seven_existing_files():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / o.MANUAL_COMPRESSION_MANIFEST).read_text())
    assert o.MANUAL_COMPRESSION_FILES == SYNTHETIC_NATIVE_FILES
    assert f.digest((root / o.MANUAL_COMPRESSION_MANIFEST).read_bytes()) == o.MANUAL_COMPRESSION_MANIFEST_SHA256
    assert f.digest((root / o.MANUAL_COMPRESSION_PATCH).read_bytes()) == o.MANUAL_COMPRESSION_PATCH_SHA256 == manifest['patch_sha256']
    assert manifest['patch'] == o.MANUAL_COMPRESSION_PATCH
    assert len(manifest['files']) == 7
    assert {row['path'] for row in manifest['files']} == SYNTHETIC_NATIVE_FILES
    assert all(row['new_file'] is False and row['mode'] == '100644'
               and len(row['before_sha256']) == len(row['sha256']) == 64
               and row['bytes'] > 0 for row in manifest['files'])
    assert len(manifest['installed_prefix']) == 84
    assert o.MANUAL_COMPRESSION_HISTORY_FILES == 752


@pytest.mark.parametrize('name', ['gateway/platforms/base.py', 'gateway/run_agent_cache.py', 'gateway/run_shutdown.py'])
def test_omitted_native_ownership_seam_refuses_before_consumption(installed, monkeypatch, name):
    s = installed
    s['manifest']['files'] = [row for row in s['manifest']['files'] if row['path'] != name]
    reference = doc(s['root'] / o.MANUAL_COMPRESSION_MANIFEST, s['manifest'])
    s['current']['project_files'][o.MANUAL_COMPRESSION_MANIFEST] = reference['sha256']
    s['req']['current_input'] = doc(Path(s['req']['current_input']['path']), s['current'])
    monkeypatch.setattr(o, 'MANUAL_COMPRESSION_MANIFEST_SHA256', reference['sha256'])
    doc(s['requestpath'], s['req'])
    before = snapshot(s['home'])
    with pytest.raises(ValueError, match='ordinary_update_exact_native_files_required'):
        o.update(s['req'], s['requestpath'], Budget(180))
    assert snapshot(s['home']) == before
