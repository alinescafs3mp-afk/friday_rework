"""v42 synthetic real Git/publication across Source86 -> two layers + plugins.

Product/native admission is explicitly stubbed by the historical fixtures;
these tests prove transaction boundaries, not installation/runtime acceptance.
"""
import copy
import difflib
import os
from pathlib import Path
import pytest
import test_ordinary_protected_compressor_update as protected
from test_ordinary_file_tool_contract_update import native77,spark79
from support_spark_source_update import doc,put,pin,snapshot,f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget
from scripts.dsh_prepare import StopUnconfirmed
from scripts.hermes_prepare import Refused as SourceRefused

BOT_NEW={'hermes_cli/friday_bot_principal.py'}
BOT_OLD={'gateway/run_busy.py','gateway/run_shutdown.py'}
ASSET_EXTRA=protected.ASSET+'/model/special_tokens_map.json'
NEW_FILES=protected.NEW_FILES|{ASSET_EXTRA}|BOT_NEW
NEW_DIRECTORIES=protected.NEW_DIRECTORIES


def patch_row(root,source,name,added,label):
    before=b'' if added else (source/name).read_bytes();after=before+('# '+label+' '+name+'\n').encode()
    row=dict(path=name,new_file=added,mode='100644',before_sha256=None if added else f.digest(before),sha256=f.digest(after),bytes=len(after))
    patch='diff --git a/'+name+' b/'+name+'\n'+('new file mode 100644\n' if added else '')+''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),fromfile='/dev/null' if added else 'a/'+name,tofile='b/'+name))
    return row,patch

@pytest.fixture
def installed(tmp_path,monkeypatch,request):
    s=protected.installed.__wrapped__(tmp_path,monkeypatch,request)
    root,source,home=s['root'],s['source'],s['home']
    first=s['manifest'];row,extra=patch_row(root,source,ASSET_EXTRA,True,'asset extra')
    first['files'].append(row)
    first['patch_sha256']=put(root/o.BUNDLE_PATCHES[0],(root/o.BUNDLE_PATCHES[0]).read_bytes()+extra.encode())['sha256']
    firstref=doc(root/o.BUNDLE_MANIFESTS[0],first)
    botrows=[];patch=[]
    for name in sorted(BOT_OLD|BOT_NEW):
        row,text=patch_row(root,source,name,name in BOT_NEW,'bot admission');botrows.append(row);patch.append(text)
    botpatch=put(root/o.BUNDLE_PATCHES[1],''.join(patch).encode())
    second={'base_commit':s['receipt']['commit'],'patch':o.BUNDLE_PATCHES[1],'patch_sha256':botpatch['sha256'],'files':botrows,
        'installed_prefix':{**first['installed_prefix'],o.BUNDLE_MANIFESTS[0]:firstref['sha256']},
        'prerequisites':{o.BUNDLE_PATCHES[0]:first['patch_sha256']}}
    secondref=doc(root/o.BUNDLE_MANIFESTS[1],second)
    current=s['current'];before={name:s['previous']['project_files'][name] for name in o.BUNDLE_PROJECT_FILES}
    for name in o.BUNDLE_PROJECT_FILES-{'scripts/friday_ordinary_install.py'}:
        current['project_files'][name]=put(root/name,(root/name).read_bytes()+b'# exact bundled project repair\n')['sha256']
    after={name:current['project_files'][name] for name in o.BUNDLE_PROJECT_FILES-{'scripts/friday_ordinary_install.py'}}
    current['project_files'].update({o.BUNDLE_MANIFESTS[0]:firstref['sha256'],o.BUNDLE_PATCHES[0]:first['patch_sha256'],o.BUNDLE_MANIFESTS[1]:secondref['sha256'],o.BUNDLE_PATCHES[1]:botpatch['sha256']})
    layerpins=tuple(dict(manifest_sha256=ref['sha256'],patch_sha256=manifest['patch_sha256'],files={row['path'] for row in manifest['files']},new_files={row['path'] for row in manifest['files'] if row['new_file']}) for ref,manifest in ((firstref,first),(secondref,second)))
    req=s['req'];req['schema']=o.BUNDLE_SCHEMA;req['current_input']=doc(tmp_path/'bundle-input.json',current)
    doc(s['requestpath'],req)
    for key,value in dict(LAYER_PINS=layerpins,NEW_DIRECTORIES=NEW_DIRECTORIES,PROJECT_BEFORE=before,PROJECT_AFTER=after,
            PREVIOUS_INPUT=req['previous_input']['sha256'],PREDECESSOR_REQUEST=req['predecessor_update']['sha256'],
            PREDECESSOR_COMMITTED=pin(s['tx']/'committed.json')['sha256'],HISTORY_FILES=len(req['transaction_history']),NATIVE_FILES=len(s['receipt']['files'])).items():
        monkeypatch.setattr(o,'BUNDLE_'+key,value)
    # The inherited fixture has 77 synthetic historical receipt-only layers.
    # Preserve those immutable placeholder identities; all ten materialized
    # layers still run the real Git parser, dependency sort and byte checks.
    from scripts import hermes_prepare
    overlay=hermes_prepare.overlay_layers
    def fixture_overlay(*args,**kwargs):
        parsed=overlay(*args,**kwargs);materialized={row[1]['manifest'] for row in parsed}
        historical=[('synthetic:'+row['manifest'],dict(row)) for row in s['receipt']['layers'] if row['manifest'] not in materialized]
        return historical+parsed
    monkeypatch.setattr(hermes_prepare,'overlay_layers',fixture_overlay)
    return {**s,**locals(),'rows':first['files']+botrows,'native_files':protected.EXISTING|NEW_FILES|BOT_OLD}


def transaction(s):return s['home']/'preparation'/('ordinary-source-update-'+s['req']['previous_input']['sha256'])

def assert_rolled_back(s,before):
    after=snapshot(s['home']);assert all(after[n]==value for n,value in before.items())
    assert all(not os.path.lexists(s['source']/n) for n in NEW_FILES|NEW_DIRECTORIES)
    assert f.read_json(transaction(s)/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    o.checked_plugin_inventory(s['home'],{n:p for n,p in s['previous']['project_files'].items() if n.startswith('plugins/friday_rework/')})
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))


def test_bundle_commits_both_layers_plugins_marker_preserves_history(installed):
    s=installed;before={n:o.update_file_state(s['home']/n) for n in snapshot(s['home'])}
    result=o.update(s['req'],s['requestpath'],Budget(180))
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    receipt=f.read_json(s['home']/'hermes-agent.source.json');marker=f.read_json(s['home']/f.MARKER)
    assert len(receipt['layers'])==87 and receipt['layers'][:-2]==s['receipt']['layers']
    assert [r['manifest'] for r in receipt['layers'][-2:]]==list(o.BUNDLE_MANIFESTS)
    assert set(receipt['files'])==set(s['receipt']['files'])|NEW_FILES
    for row in s['rows']:assert f.digest((s['source']/row['path']).read_bytes())==row['sha256']
    o.checked_plugin_inventory(s['home'],marker['plugin_files'])
    assert marker['plugin_files']=={n:p for n,p in s['current']['project_files'].items() if n.startswith('plugins/friday_rework/')}
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'}|{'hermes-agent/'+n for n in protected.EXISTING|BOT_OLD}|o.BUNDLE_PLUGIN_FILES
    assert all(o.update_file_state(s['home']/n)==v for n,v in before.items() if n not in changed)
    assert len(f.read_json(transaction(s)/'intent.json')['before'])==27
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('number',range(1,28))
def test_every_publication_rolls_back_bundle_and_plugin_copies(installed,monkeypatch,number):
    s=installed;original=o.publish_update_file;calls=0;before=snapshot(s['home'])
    def fail(*a,**kw):
        nonlocal calls
        calls+=1
        if calls==number:raise ValueError('exact primary publication failure')
        return original(*a,**kw)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(ValueError,match='exact primary publication failure'):o.update(s['req'],s['requestpath'],Budget(180))
    assert_rolled_back(s,before)

@pytest.mark.parametrize('unchanged',['tools/configure_local_test.py','tools/configure_product.py','both'])
def test_exact_pinned_helper_subset_is_allowed(installed,monkeypatch,unchanged):
    s=installed
    names={'tools/configure_local_test.py','tools/configure_product.py'} if unchanged=='both' else {unchanged}
    after=dict(o.BUNDLE_PROJECT_AFTER)
    for name in names:
        # Baseline helper bytes are synthetic and retained under fixture history.
        # Helpers have no installed copies. The fixture archives their previous
        # source content before changing it, so restore precisely that content.
        data=(s['root']/name).read_bytes().removesuffix(b'# exact bundled project repair\n')
        ref=put(s['root']/name,data);assert ref['sha256']==o.BUNDLE_PROJECT_BEFORE[name]
        s['current']['project_files'][name]=after[name]=ref['sha256']
    monkeypatch.setattr(o,'BUNDLE_PROJECT_AFTER',after)
    s['req']['current_input']=doc(Path(s['req']['current_input']['path']),s['current']);doc(s['requestpath'],s['req'])
    assert o.update(s['req'],s['requestpath'],Budget(180))['ready'] is False

@pytest.mark.parametrize('fault',['unbound','extra_project','extra_plugin','wrong_helper','wrong_before','wrong_after','missing_after','unchanged_required_plugin',
    'bad_prefix','wrong_order','overlap','extra_row','bad_native_before','extra_patch_target','bad_output','predecessor_v41','wrong_input','wrong_commit','changed_history','config_change','extra_worker_archive','extra_rebind'])
def test_bundle_rejects_wrong_tuple_or_rolls_back_staged_output(installed,monkeypatch,fault):
    s=installed;req=s['req'];pins=copy.deepcopy(o.BUNDLE_LAYER_PINS);first,second=s['first'],s['second'];before=None
    if fault=='unbound':monkeypatch.setattr(o,'BUNDLE_PROJECT_AFTER',None)
    elif fault in ('extra_project','extra_plugin','wrong_helper'):
        n={'extra_project':'scripts/friday_native.py','extra_plugin':'plugins/friday_rework/unchanged.py','wrong_helper':'tools/configure_product.py'}[fault]
        s['current']['project_files'][n]=put(s['root']/n,b'# unreviewed delta\n')['sha256']
    elif fault=='wrong_before':monkeypatch.setattr(o,'BUNDLE_PROJECT_BEFORE',{**o.BUNDLE_PROJECT_BEFORE,'tools/configure_product.py':'0'*64})
    elif fault=='wrong_after':monkeypatch.setattr(o,'BUNDLE_PROJECT_AFTER',{**o.BUNDLE_PROJECT_AFTER,'tools/configure_product.py':'0'*64})
    elif fault=='missing_after':monkeypatch.setattr(o,'BUNDLE_PROJECT_AFTER',{n:p for n,p in o.BUNDLE_PROJECT_AFTER.items() if n!='tools/configure_local_test.py'})
    elif fault=='unchanged_required_plugin':
        n=next(iter(o.BUNDLE_PLUGIN_FILES));monkeypatch.setattr(o,'BUNDLE_PROJECT_AFTER',{**o.BUNDLE_PROJECT_AFTER,n:o.BUNDLE_PROJECT_BEFORE[n]})
    elif fault=='wrong_order':second['prerequisites']={o.MANUAL_COMPRESSION_PATCH:s['previous']['project_files'][o.MANUAL_COMPRESSION_PATCH]}
    elif fault=='bad_prefix':second['installed_prefix'].pop(o.BUNDLE_MANIFESTS[0])
    elif fault=='overlap':pins[1]['files'].remove(next(iter(BOT_OLD)));pins[1]['files'].add(next(iter(protected.EXISTING)))
    elif fault=='extra_row':second['files'].append(dict(second['files'][0],path='foreign.py'))
    elif fault=='bad_native_before':next(row for row in second['files'] if not row['new_file'])['before_sha256']='0'*64
    elif fault in ('extra_patch_target','bad_output'):
        path=s['root']/o.BUNDLE_PATCHES[1];data=path.read_bytes()
        if fault=='bad_output':data=data.replace(b'# bot admission',b'# wrong content')
        else:data+=patch_row(s['root'],s['source'],'foreign.py',True,'foreign')[1].encode()
        second['patch_sha256']=put(path,data)['sha256'];pins[1]['patch_sha256']=second['patch_sha256']
    elif fault=='predecessor_v41':
        old=f.read_json(Path(req['predecessor_update']['path']));old['schema']='friday.ordinary-telegram-source-update.v41'
        req['predecessor_update']=doc(Path(req['predecessor_update']['path']),old);monkeypatch.setattr(o,'BUNDLE_PREDECESSOR_REQUEST',req['predecessor_update']['sha256'])
    elif fault=='wrong_input':monkeypatch.setattr(o,'BUNDLE_PREVIOUS_INPUT','0'*64)
    elif fault=='wrong_commit':monkeypatch.setattr(o,'BUNDLE_PREDECESSOR_COMMITTED','0'*64)
    elif fault=='changed_history':req['transaction_history'].pop(next(iter(req['transaction_history'])))
    elif fault=='config_change':s['current']['seconds']+=1
    elif fault=='extra_worker_archive':req['worker_archive']=s['archive_ref']
    elif fault=='extra_rebind':req['inference_rebind']=s['archive_ref']
    if fault in ('bad_prefix','wrong_order','extra_row','bad_native_before','extra_patch_target','bad_output'):
        ref=doc(s['root']/o.BUNDLE_MANIFESTS[1],second);pins[1]['manifest_sha256']=ref['sha256']
        s['current']['project_files'][o.BUNDLE_MANIFESTS[1]]=ref['sha256'];s['current']['project_files'][o.BUNDLE_PATCHES[1]]=second['patch_sha256']
    if fault in ('overlap','bad_prefix','wrong_order','extra_row','bad_native_before','extra_patch_target','bad_output'):monkeypatch.setattr(o,'BUNDLE_LAYER_PINS',pins)
    req['current_input']=doc(Path(req['current_input']['path']),s['current']);doc(s['requestpath'],req);before=snapshot(s['home'])
    with pytest.raises((ValueError,AssertionError,KeyError,SourceRefused)):o.update(req,s['requestpath'],Budget(180))
    if fault=='bad_output':assert_rolled_back(s,before)
    else:assert snapshot(s['home'])==before and not transaction(s).exists()

@pytest.mark.parametrize('name',sorted(o.BUNDLE_PLUGIN_FILES))
def test_same_bytes_foreign_plugin_inode_is_retained(installed,monkeypatch,name):
    s=installed;original=o.publish_update_file;state=None
    def replace(path,*a,**kw):
        nonlocal state
        result=original(path,*a,**kw)
        if path==s['home']/name:
            other=path.with_name('foreign');put(other,path.read_bytes());os.replace(other,path);state=o.update_file_state(path)
            raise ValueError('plugin custody lost')
        return result
    monkeypatch.setattr(o,'publish_update_file',replace)
    with pytest.raises(StopUnconfirmed):o.update(s['req'],s['requestpath'],Budget(180))
    assert state is not None and o.same_update_file(s['home']/name,state)
    assert not (transaction(s)/'rolled-back.json').exists() and not (transaction(s)/'committed.json').exists()


def test_unbound_v42_rejects_before_runtime_paths(monkeypatch):
    monkeypatch.setattr(o,'BUNDLE_PROJECT_AFTER',None)
    fields={'schema','seconds','home','previous_input','current_input','marker','source_receipt','stamp','configuration','profile','launcher','credential_files','native_unit','transaction_history','predecessor_update','retained_profile_files'}
    req=dict.fromkeys(fields);req.update(schema=o.BUNDLE_SCHEMA,seconds=180)
    def denied(*a,**kw):raise AssertionError('runtime accessed without pins')
    monkeypatch.setattr(f,'directory',denied)
    with pytest.raises(ValueError,match='ordinary_update_final_bundle_pins_required'):o.update_inputs(req,Budget(180))

# Reuse meaningful directory, lock, retained-user and final-check controls on v42.
test_asset_parent_refuses=protected.test_preexisting_asset_parent_refuses_before_consumption
test_directory_custody=protected.test_new_nested_directory_custody_loss_preserves_foreign
test_foreign_file_inode=protected.test_same_bytes_foreign_inode_is_not_rolled_back
test_pm_lock=protected.test_native_pm_lock_refuses_or_retains_custody
test_writer_locks=protected.test_source87_writer_locks
test_admin_drift=protected.test_source87_admin_drift
test_final_validation=protected.test_source87_final_validation


def test_foreign_unchanged_plugin_during_failure_cannot_claim_complete_rollback(installed,monkeypatch):
    s=installed;original=o.publish_update_file;foreign=s['home']/'plugins/friday_rework/unchanged.py';done=False
    def race(path,*a,**kw):
        nonlocal done
        result=original(path,*a,**kw)
        if not done:
            done=True;put(foreign,b'foreign concurrent plugin edit');raise ValueError('primary failure')
        return result
    monkeypatch.setattr(o,'publish_update_file',race)
    with pytest.raises(StopUnconfirmed) as error:o.update(s['req'],s['requestpath'],Budget(180))
    assert str(error.value.__cause__)=='primary failure'
    assert foreign.read_bytes()==b'foreign concurrent plugin edit'
    assert not (transaction(s)/'rolled-back.json').exists() and not (transaction(s)/'committed.json').exists()


def test_late_unchanged_plugin_drift_cannot_commit_stale_inventory(installed,monkeypatch):
    s=installed;spec=f.spec_checked;foreign=s['home']/'plugins/friday_rework/unchanged.py';changed=False
    def race(*a,**kw):
        nonlocal changed
        result=spec(*a,**kw)
        if (transaction(s)/'intent.json').exists() and not changed:
            changed=True;put(foreign,b'foreign edit during final spec validation')
        return result
    monkeypatch.setattr(f,'spec_checked',race)
    with pytest.raises(StopUnconfirmed):o.update(s['req'],s['requestpath'],Budget(180))
    assert changed and foreign.read_bytes()==b'foreign edit during final spec validation'
    assert not (transaction(s)/'rolled-back.json').exists() and not (transaction(s)/'committed.json').exists()


def test_original_budget_expiring_in_final_inventory_refuses_commit(installed,monkeypatch):
    s=installed;check=o.checked_plugin_inventory;budget=Budget(180);calls=0;before=snapshot(s['home'])
    def expire(*a,**kw):
        nonlocal calls
        result=check(*a,**kw);calls+=1
        # Two input checks, pre-metadata, post-metadata, then final precommit.
        if calls==5:budget.deadline=0
        return result
    monkeypatch.setattr(o,'checked_plugin_inventory',expire)
    with pytest.raises(ValueError,match='original_install_budget_exhausted'):o.update(s['req'],s['requestpath'],budget)
    assert calls>=5 and budget.deadline==0
    assert_rolled_back(s,before)
