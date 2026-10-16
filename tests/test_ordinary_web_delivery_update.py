"""Source81 -> combined package83 layer82 preserves current admin edits and consumed history.

Synthetic homes only; real Git staging/publication/rollback. Native product
admission and service custody remain explicit fixtures, not runtime evidence.
"""
import copy,difflib,os
from pathlib import Path
import pytest
import test_ordinary_file_tool_contract_update as previous_test
from test_ordinary_file_tool_contract_update import native77,spark79
from support_spark_source_update import doc,put,pin,snapshot,f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget

@pytest.fixture
def installed(tmp_path,monkeypatch,request):
    real_path=o.__file__
    with monkeypatch.context() as before:
        before.setattr(o,'__file__',str(tmp_path/'source81-updater.py'))
        put(Path(o.__file__),b'# exact archived Source81 updater\n')
        s=previous_test.installed.__wrapped__(tmp_path,monkeypatch,request)
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
    native_files=set(o.COMBINED_INPUT_FILES)
    rows=[];patches=[]
    for n in sorted(native_files):
        old=(source/n).read_bytes();new=old+b'# reviewed credential preflight\n'
        rows.append(dict(path=n,before_sha256=f.digest(old),sha256=f.digest(new),bytes=len(new),mode='100644',new_file=False))
        patches.append('diff --git a/'+n+' b/'+n+'\n'+''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+n,tofile='b/'+n)))
    patchref=put(root/o.COMBINED_INPUT_PATCH,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':o.COMBINED_INPUT_PATCH,'patch_sha256':patchref['sha256'],'files':rows,
        'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in receipt['layers']},
        'prerequisites':{o.FILE_TOOL_CONTRACT_PATCH:previous['project_files'][o.FILE_TOOL_CONTRACT_PATCH]}}
    manifestref=doc(root/o.COMBINED_INPUT_MANIFEST,manifest)
    current=copy.deepcopy(previous);current['project_files'].update({
        o.COMBINED_INPUT_MANIFEST:manifestref['sha256'],o.COMBINED_INPUT_PATCH:patchref['sha256'],
        'scripts/friday_ordinary_install.py':put(root/'scripts/friday_ordinary_install.py',Path(real_path).read_bytes())['sha256']})
    req={k:v for k,v in s['req'].items() if k!='inference_rebind'}
    req.update(schema='friday.ordinary-telegram-source-update.v37',previous_input=prevref,
        current_input=doc(tmp_path/'source83-input.json',current),marker=pin(home/f.MARKER),
        source_receipt=pin(home/'hermes-agent.source.json'),stamp=pin(source/'install-stamp.json'),
        transaction_history=history,predecessor_update=predecessor,retained_profile_files=profile_refs)
    requestpath=tmp_path/'source83-request.json';doc(requestpath,req)
    for k,v in {'COMBINED_INPUT_MANIFEST_SHA256':manifestref['sha256'],'COMBINED_INPUT_PATCH_SHA256':patchref['sha256'],
        'COMBINED_INPUT_FILES':native_files,'COMBINED_INPUT_PREVIOUS_INPUT':prevref['sha256'],
        'COMBINED_INPUT_PREDECESSOR_REQUEST':predecessor['sha256'],
        'COMBINED_INPUT_PREVIOUS_UPDATER':previous['project_files']['scripts/friday_ordinary_install.py'],
        'COMBINED_INPUT_NATIVE_FILES':len(receipt['files']),'COMBINED_INPUT_HISTORY_FILES':len(history),
        'WEB_INPUT_SELECTED_CONFIG':profile_refs['profiles/dest_telegram/config.yaml']['sha256']}.items():monkeypatch.setattr(o,k,v)
    for directory in (p for p in home.rglob('*') if p.is_dir()):directory.chmod(0o700)
    return {**s,**locals()}

def test_update_preserves_current_admin_profile_and_closed_ancestry(installed):
    s=installed;before={n:o.update_file_state(s['home']/n) for n in snapshot(s['home'])}
    result=o.update(s['req'],s['requestpath'],Budget(180))
    assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    assert len(f.read_json(s['home']/'hermes-agent.source.json')['layers'])==82
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'}|{'hermes-agent/'+n for n in s['native_files']}
    assert all(o.update_file_state(s['home']/n)==v for n,v in before.items() if n not in changed)
    assert b'enabled: off' in (s['home']/'profiles/dest_telegram/config.yaml').read_bytes()
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('fault',['pending_manifest','pending_patch','wrong_input','wrong_predecessor','wrong_updater','history_missing','profile_missing','profile_extra','profile_path','profile_changed','proof_changed','scope_changed','key_changed','old_auto_hash','extra_plugin','extra_native','foreign_native','extra_rebind'])
def test_invalid_boundary_refuses_before_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req'];home=s['home']
    constants={'pending_manifest':('COMBINED_INPUT_MANIFEST_SHA256',None),'pending_patch':('COMBINED_INPUT_PATCH_SHA256',None),
        'wrong_input':('COMBINED_INPUT_PREVIOUS_INPUT','0'*64),'wrong_predecessor':('COMBINED_INPUT_PREDECESSOR_REQUEST','0'*64),
        'wrong_updater':('COMBINED_INPUT_PREVIOUS_UPDATER','0'*64),'old_auto_hash':('WEB_INPUT_SELECTED_CONFIG','0'*64)}
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
        s['manifest']['files'].append(dict(s['rows'][0],path='other.py'));ref=doc(s['root']/o.COMBINED_INPUT_MANIFEST,s['manifest']);s['current']['project_files'][o.COMBINED_INPUT_MANIFEST]=ref['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'COMBINED_INPUT_MANIFEST_SHA256',ref['sha256'])
    elif fault=='foreign_native':put(s['source']/next(iter(s['native_files'])),b'foreign',0o644)
    elif fault=='extra_rebind':req['inference_rebind']=s['budgetref']
    doc(s['requestpath'],req);before=snapshot(home)
    with pytest.raises((ValueError,KeyError,AssertionError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(home)==before

@pytest.mark.parametrize('number',range(1,9))
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

test_source83_locks=previous_test.test_source81_existing_writer_locks
@pytest.mark.parametrize('kind',['native','marker'])
def test_source83_foreign_custody(installed,monkeypatch,kind):
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
test_source83_final_validation=previous_test.test_source81_final_validation
test_source83_original_archive=previous_test.test_source81_original_archive


@pytest.mark.parametrize('fault',['source82_prepared_predecessor','wrong_schema','operational_model','operational_budget','omitted_web','omitted_delivery'])
def test_combined_exactness_refuses_without_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req']
    if fault=='source82_prepared_predecessor':
        prepared=copy.deepcopy(s['req']);prepared['schema']='friday.ordinary-telegram-source-update.v36'
        req['predecessor_update']=doc(s['root']/'unexecuted-v36-request.json',prepared)
        monkeypatch.setattr(o,'COMBINED_INPUT_PREDECESSOR_REQUEST',req['predecessor_update']['sha256'])
    elif fault=='wrong_schema':req['schema']='friday.ordinary-telegram-source-update.v36'
    elif fault in ('operational_model','operational_budget'):
        key='model' if fault=='operational_model' else 'original_budget'
        s['current'][key]='unauthorized change';req['current_input']=doc(Path(req['current_input']['path']),s['current'])
    else:
        target='tools/web_tools.py' if fault=='omitted_web' else 'gateway/run_plugin_delivery.py'
        s['manifest']['files']=[r for r in s['manifest']['files'] if r['path']!=target]
        ref=doc(s['root']/o.COMBINED_INPUT_MANIFEST,s['manifest']);s['current']['project_files'][o.COMBINED_INPUT_MANIFEST]=ref['sha256']
        req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'COMBINED_INPUT_MANIFEST_SHA256',ref['sha256'])
    doc(s['requestpath'],req);before=snapshot(s['home'])
    with pytest.raises((ValueError,KeyError,AssertionError,OSError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before
