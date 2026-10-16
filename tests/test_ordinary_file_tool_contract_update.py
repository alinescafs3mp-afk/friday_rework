import copy,difflib,json
from pathlib import Path
import pytest
import test_ordinary_file_boundary_update as previous_test
from support_spark_source_update import doc,put,pin,snapshot,f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget

@pytest.fixture
def installed(tmp_path,monkeypatch,request):
    s=previous_test.installed.__wrapped__(monkeypatch,request,tmp_path)
    home,root,source=s['home'],s['root'],s['source']
    o.update(s['req'],s['requestpath'],Budget(180))
    predecessor=pin(s['requestpath']);receipt=f.read_json(home/'hermes-agent.source.json')
    history=dict(s['req']['transaction_history'])
    tx=home/'preparation'/('ordinary-source-update-'+s['req']['previous_input']['sha256'])
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
    previous=copy.deepcopy(s['current']);previous['product']['request_budget_fixture']={'sdk':180}
    prevref=doc(tmp_path/'budget-input.json',previous)
    names={f.MARKER,'config.yaml','profiles/dest_telegram/config.yaml','profiles/dest_telegram/.friday-onboarding.json','profiles/dest_telegram/.friday-user-scope.json'}
    before={n:pin(home/n) for n in names}
    data={n:(home/n).read_bytes() for n in names}
    mark=f.read_json(home/f.MARKER);mark['input_sha256']=prevref['sha256'];mark['ordinary_gateway']['operator_entry']['input']=prevref
    doc(home/f.MARKER,mark)
    # Real budget code has already completed; synthetic immutable journal only.
    retained={n:pin(home/n) for n in snapshot(home) if n not in names}
    budget={'schema':o.REBIND_BUDGET_SCHEMA,'seconds':180,'home':str(home),'profile':'dest_telegram',
        'previous_input':s['req']['current_input'],'current_input':prevref,'before':before,'retained':retained,'native_unit':s['req']['native_unit']}
    budgetref=doc(tmp_path/'budget-request.json',budget)
    btx=home/'preparation'/('ordinary-inference-rebind-'+budget['previous_input']['sha256'])
    intent={'schema':o.REBIND_BUDGET_SCHEMA,'state':'CONSUMED_NO_RETRY','seconds':180,
        'request_sha256':budgetref['sha256'],'previous_input':budget['previous_input'],'current_input':prevref,
        'before':{n:{'sha256':before[n]['sha256'],'mode':0o600} for n in names},
        'consumers_started':False,'workers_enabled':False,'database_changed':False}
    after={n:pin(home/n)['sha256'] for n in names}
    commit={'state':'EXACT_REQUEST_BUDGET_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED','ready':False,
        'consumers_started':False,'workers_enabled':False,'database_changed':False,'after':after}
    intentref=doc(btx/'intent.json',intent);commitref=doc(btx/'committed.json',commit)
    for n in names:put(btx/'before'/n,data[n]);put(btx/'stage'/n,(home/n).read_bytes())
    put(btx/'stage/FRIDAY-PROFILE.json',(home/'FRIDAY-PROFILE.json').read_bytes())
    for n in ['config.yaml.lock','profiles/dest_telegram/config.yaml.lock']:put(btx/'stage'/n,b'')
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in btx.rglob('*') if p.is_file()})
    native_files=s['native_files']|{'gateway/run_turn.py'};rows=[];patches=[]
    for n in sorted(native_files):
        old=(source/n).read_bytes();new=old+b'# source81 file tool contract\n'
        rows.append(dict(path=n,before_sha256=f.digest(old),sha256=f.digest(new),bytes=len(new),mode='100644',new_file=False))
        patches.append('diff --git a/'+n+' b/'+n+'\n'+''.join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='a/'+n,tofile='b/'+n)))
    patchref=put(root/o.FILE_TOOL_CONTRACT_PATCH,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':o.FILE_TOOL_CONTRACT_PATCH,'patch_sha256':patchref['sha256'],'files':rows,
        'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in receipt['layers']},
        'prerequisites':{o.SPARK_REQUEST_BUDGET_PATCH:previous['project_files'][o.SPARK_REQUEST_BUDGET_PATCH]}}
    manifestref=doc(root/o.FILE_TOOL_CONTRACT_MANIFEST,manifest)
    plugin=s['plugin']
    assert plugin in previous['project_files']
    beforepins={n:previous['project_files'][n] for n in [plugin,'scripts/friday_ordinary_install.py']}
    current=copy.deepcopy(previous)
    # Fixture predecessor used this same running updater; replace its old project
    # pin with an actual different archived predecessor file before forming refs.
    old_update=put(tmp_path/'old-updater.py',b'# archived old update\n')['sha256']
    previous['project_files']['scripts/friday_ordinary_install.py']=old_update
    prevref=doc(Path(prevref['path']),previous);budget['current_input']=prevref
    budgetref=doc(Path(budgetref['path']),budget);intent['current_input']=prevref;intent['request_sha256']=budgetref['sha256']
    intentref=doc(btx/'intent.json',intent);mark['input_sha256']=prevref['sha256'];mark['ordinary_gateway']['operator_entry']['input']=prevref;doc(home/f.MARKER,mark)
    commit['after'][f.MARKER]=pin(home/f.MARKER)['sha256'];put(btx/'stage'/f.MARKER,(home/f.MARKER).read_bytes());commitref=doc(btx/'committed.json',commit)
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in btx.rglob('*') if p.is_file()})
    beforepins['scripts/friday_ordinary_install.py']=old_update
    current['project_files'].update({o.FILE_TOOL_CONTRACT_MANIFEST:manifestref['sha256'],o.FILE_TOOL_CONTRACT_PATCH:patchref['sha256'],
        'scripts/friday_ordinary_install.py':put(root/'scripts/friday_ordinary_install.py',Path(o.__file__).read_bytes())['sha256'],
        plugin:put(root/plugin,b'# typed off editor\n')['sha256']})
    req={**s['req'],'schema':'friday.ordinary-telegram-source-update.v35','previous_input':prevref,
        'current_input':doc(tmp_path/'source81-input.json',current),'marker':pin(home/f.MARKER),
        'source_receipt':pin(home/'hermes-agent.source.json'),'stamp':pin(source/'install-stamp.json'),
        'transaction_history':history,'predecessor_update':predecessor,'inference_rebind':budgetref}
    requestpath=tmp_path/'source81-request.json';doc(requestpath,req)
    for k,v in {'FILE_TOOL_CONTRACT_MANIFEST_SHA256':manifestref['sha256'],'FILE_TOOL_CONTRACT_PATCH_SHA256':patchref['sha256'],
        'FILE_TOOL_CONTRACT_FILES':native_files,'FILE_TOOL_CONTRACT_PLUGIN_FILES':{plugin},'FILE_TOOL_CONTRACT_PREVIOUS_INPUT':prevref['sha256'],
        'FILE_TOOL_CONTRACT_NATIVE_FILES':len(receipt['files']),'FILE_TOOL_CONTRACT_PROJECT_BEFORE':beforepins,
        'FILE_TOOL_CONTRACT_PROJECT_AFTER':{plugin:current['project_files'][plugin]},
        'SOURCE81_PREDECESSOR_REQUEST':predecessor['sha256'],'SOURCE81_BUDGET_REQUEST':budgetref['sha256'],
        'SOURCE81_BUDGET_INTENT':intentref['sha256'],'SOURCE81_BUDGET_COMMITTED':commitref['sha256'],
        'SOURCE81_HISTORY_FILES':len(history),'SOURCE81_RETAINED_FILES':len(retained)}.items():monkeypatch.setattr(o,k,v)
    for directory in (p for p in home.rglob("*") if p.is_dir()): directory.chmod(0o700)
    return {**s,**locals()}

from support_spark_source_update import installed as native77
from test_spark_multipass_update import installed as spark79

def test_update_preserves_history_config_proofs_keys_and_no_retry(installed):
    s=installed;before={n:o.update_file_state(s['home']/n) for n in snapshot(s['home'])}
    result=o.update(s['req'],s['requestpath'],Budget(180));assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    receipt=f.read_json(s['home']/'hermes-agent.source.json');assert len(receipt['layers'])==81
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json',s['plugin']}|{'hermes-agent/'+n for n in s['native_files']}
    assert all(o.update_file_state(s['home']/n)==state for n,state in before.items() if n not in changed)
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('fault',['pending_manifest','pending_patch','wrong_input','wrong_predecessor','wrong_budget','history_missing','retained_changed','user_config','root_key','extra_plugin','bad_before','budget_extra','budget_stage','budget_flags','manifest_extra','foreign_native'])
def test_invalid_boundary_no_consumption(installed,monkeypatch,fault):
    s=installed;req=s['req'];home=s['home']
    if fault.startswith('pending_'):monkeypatch.setattr(o,'FILE_TOOL_CONTRACT_'+('MANIFEST' if fault.endswith('manifest') else 'PATCH')+'_SHA256',None)
    elif fault=='wrong_input':monkeypatch.setattr(o,'FILE_TOOL_CONTRACT_PREVIOUS_INPUT','0'*64)
    elif fault=='wrong_predecessor':monkeypatch.setattr(o,'SOURCE81_PREDECESSOR_REQUEST','0'*64)
    elif fault=='wrong_budget':monkeypatch.setattr(o,'SOURCE81_BUDGET_REQUEST','0'*64)
    elif fault=='history_missing':req['transaction_history'].pop(next(iter(req['transaction_history'])))
    elif fault=='retained_changed':put(home/'profiles/dest_telegram/.env',b'foreign retained key')
    elif fault=='user_config':put(home/'profiles/dest_telegram/config.yaml',b'foreign')
    elif fault=='root_key':put(home/'.env',b'foreign')
    elif fault=='extra_plugin':s['current']['project_files']['plugins/friday_rework/unchanged.py']=put(s['root']/'plugins/friday_rework/unchanged.py',b'foreign plugin')['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current'])
    elif fault=='bad_before':monkeypatch.setattr(o,'FILE_TOOL_CONTRACT_PROJECT_BEFORE',{**o.FILE_TOOL_CONTRACT_PROJECT_BEFORE,s['plugin']:'0'*64})
    elif fault=='budget_extra':put(s['btx']/'extra.json',b'{}')
    elif fault=='budget_stage':put(s['btx']/'stage/FRIDAY-PROFILE.json',b'foreign')
    elif fault=='budget_flags':
        s['commit']['workers_enabled']=True;ref=doc(s['btx']/'committed.json',s['commit']);monkeypatch.setattr(o,'SOURCE81_BUDGET_COMMITTED',ref['sha256']);req['transaction_history'][str((s['btx']/'committed.json').relative_to(home))]=ref['sha256']
    elif fault=='manifest_extra':
        s['manifest']['files'].append(dict(s['rows'][0],path='other.py'));ref=doc(s['root']/o.FILE_TOOL_CONTRACT_MANIFEST,s['manifest']);s['current']['project_files'][o.FILE_TOOL_CONTRACT_MANIFEST]=ref['sha256'];req['current_input']=doc(Path(req['current_input']['path']),s['current']);monkeypatch.setattr(o,'FILE_TOOL_CONTRACT_MANIFEST_SHA256',ref['sha256'])
    elif fault=='foreign_native':put(s['source']/next(iter(s['native_files'])),b'foreign',0o644)
    doc(s['requestpath'],req);before=snapshot(home)
    with pytest.raises((ValueError,KeyError,AssertionError)):o.update(req,s['requestpath'],Budget(180))
    assert snapshot(home)==before

@pytest.mark.parametrize('number',range(1,9))
def test_every_publication_failure_rolls_back_owned_only(installed,monkeypatch,number):
    s=installed;original=o.publish_update_file;calls=0;before=snapshot(s['home'])
    def fail(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==number:raise ValueError('synthetic publication failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    assert all(after[n]==value for n,value in before.items())
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    assert not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

# The unchanged publication machinery must exercise these branches under v35 too.
test_source81_existing_writer_locks = previous_test.test_existing_writer_locks_refuse_before_consumption
test_source81_foreign_custody = previous_test.test_foreign_replacement_during_failure_is_retained_stop_unconfirmed
test_source81_final_validation = previous_test.test_final_validation_failure_restores_all_owned_files
test_source81_original_archive = previous_test.test_closed_archive_refuses_any_loss_of_original_evidence
test_source81_final_user_drift = previous_test.test_final_live_rebind_drift_rolls_back_owned_source_and_preserves_foreign_change
