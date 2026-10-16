"""Finite Source79->80 SOURCE fixtures, real Git and owned publication.

The prior Source78/79 updates execute on synthetic trees. Helper v4 and the
inference rebind are pinned closed ancestry, never actions to dispatch again.
All native admission/configuration checks use synthetic data. No installed
home, service, database, key or model is used by these tests.
"""
import copy
import difflib
import fcntl
import os
from pathlib import Path

import pytest

from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget
import support_spark_source_update as support
import test_spark_multipass_update as spark
from support_spark_source_update import installed as native77, doc, put, pin, snapshot, f
from test_spark_multipass_update import installed as spark79


@pytest.fixture
def installed(monkeypatch, request, tmp_path):
    # Reuse the existing finite fixture with this exact candidate module. The
    # inherited fixture originally imports its own isolated prior updater.
    monkeypatch.setattr(support, 'o', o)
    monkeypatch.setattr(spark, 'o', o)
    s = request.getfixturevalue('spark79')
    home, source, root = s['home'], s['source'], s['root']
    o.update(s['request'], s['requestpath'], Budget(180))
    source79 = pin(s['requestpath'])
    history = copy.deepcopy(s['request']['transaction_history'])
    last = home/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    history.update({str(p.relative_to(home)): f.digest(p.read_bytes()) for p in last.rglob('*') if p.is_file()})
    receipt = f.read_json(home/'hermes-agent.source.json')
    # The accepted helper transaction and its preceding archive reconciliation
    # have their original input references, receipts and consumed journal.
    helper_before = copy.deepcopy(s['current'])
    helper_before_ref = doc(tmp_path/'helper-before.json', helper_before)
    fixed = copy.deepcopy(helper_before)
    fixed['project_files']['scripts/friday_ordinary_install.py'] = put(
        root/'scripts/friday_ordinary_install.py', b'# installed helper v4 before Source80\n')['sha256']
    fixedref = doc(tmp_path/'helper-fixed.json', fixed)
    helper = {'schema':o.PROJECT_INFERENCE_HELPER_SCHEMA, 'seconds':180, 'home':str(home),
        'previous_input':helper_before_ref, 'current_input':fixedref,
        'transaction_history':copy.deepcopy(history), 'predecessor_update':source79}
    helperref = doc(tmp_path/'helper-v4-request.json', helper)
    helper_tx = home/'preparation'/('ordinary-source-update-'+helper_before_ref['sha256'])
    doc(helper_tx/'intent.json', {'schema':'friday.ordinary-telegram-source-update-transaction.v1',
        'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY', 'request_sha256':helperref['sha256'], 'project_only':True})
    doc(helper_tx/'committed.json', {'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
        'previous_input':helper_before_ref, 'current_input':fixedref,
        'source_receipt_sha256':pin(home/'hermes-agent.source.json')['sha256'],
        'gateway_started':False, 'workers_enabled':False, 'project_only':True})
    put(helper_tx/'before/FRIDAY-INSTALL.json', (home/f.MARKER).read_bytes())
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in helper_tx.rglob('*') if p.is_file()})
    reconcile = o.PROJECT_INFERENCE_RECONCILIATION
    archive = home/reconcile
    archived = {}
    archive_names = ['failure.json']+[f'dsh-safety/inputs/retained-{n}' for n in range(7)]+[f'dsh-safety/workspace/retained-{n}' for n in range(15)]
    for name in archive_names:
        mode=0o400 if '/inputs/' in name else 0o664 if '/workspace/' in name else 0o600
        data=b'closed original observation '+name.encode()
        put(archive/'failed-qualification'/name,data,mode)
        state=o.update_file_state(archive/'failed-qualification'/name)
        archived[name]={'sha256':f.digest(data),'bytes':len(data),'mode':mode,'identity':list(state['identity'])}
        put(archive/'failed-before'/name,data,mode&0o700)
    reconcile_pins = {
        reconcile+'/intent.json':doc(archive/'intent.json',{'state':'CONSUMED_NO_RETRY','tree':{'files':archived}})['sha256'],
        reconcile+'/committed.json':doc(archive/'committed.json',{'state':'ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY','workers_enabled':False})['sha256'],
        reconcile+'/before/FRIDAY-INSTALL.json':put(archive/'before/FRIDAY-INSTALL.json',(home/f.MARKER).read_bytes())['sha256']}
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in archive.rglob('*') if p.is_file()})
    previous = copy.deepcopy(fixed)
    previous['product'].update({'inference':{'model':'existing primary'},
        'compression_inference':{'model':'existing separate compressor'},
        'compression_multipass':{'enabled':True}})
    prevref = doc(tmp_path/'current-gen15.json', previous)
    rebind_names = {'.env','config.yaml',f.MARKER,'FRIDAY-PROFILE.json',
        'profiles/dest_telegram/.env','profiles/dest_telegram/config.yaml',
        'profiles/dest_telegram/.friday-onboarding.json','profiles/dest_telegram/.friday-user-scope.json'}
    before = {}
    for name in rebind_names:
        if not (home/name).exists(): put(home/name, b'accepted private fixture '+name.encode())
        before[name] = pin(home/name)
    rebound_marker = f.read_json(home/f.MARKER)
    rebound_marker['input_sha256'] = prevref['sha256']
    rebound_marker['ordinary_gateway']['operator_entry']['input'] = prevref
    doc(home/f.MARKER, rebound_marker)
    # Current split configs, separate credentials and accepted metadata are
    # retained by Source80. Synthetic bytes stand for their private afterimages.
    rebind = {'schema':o.REBIND_SCHEMA, 'seconds':180, 'home':str(home), 'profile':'dest_telegram',
        'previous_input':fixedref, 'current_input':prevref, 'before':before,
        'retained':{}, 'native_unit':s['request']['native_unit'],
        'primary_credentials':{'root':{'synthetic':True},'user':{'synthetic':True}}}
    rebindref = doc(tmp_path/'rebind-request.json', rebind)
    rebind_tx = home/'preparation'/('ordinary-inference-rebind-'+fixedref['sha256'])
    rebind_intent = {'schema':o.REBIND_SCHEMA, 'state':'CONSUMED_NO_RETRY', 'seconds':180,
        'request_sha256':rebindref['sha256'], 'previous_input':fixedref, 'current_input':prevref,
        'before':{n:{'sha256':v['sha256'],'mode':0o600} for n,v in before.items()},
        'consumers_started':False, 'workers_enabled':False, 'database_changed':False}
    rebind_after = {n:pin(home/n)['sha256'] for n in rebind_names}
    committed = {'state':'EXACT_INFERENCE_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED',
        'ready':False, 'consumers_started':False, 'workers_enabled':False,
        'database_changed':False, 'after':rebind_after}
    intentref = doc(rebind_tx/'intent.json', rebind_intent)
    committedref = doc(rebind_tx/'committed.json', committed)
    for name in rebind_names:
        # The marker is the only different synthetic afterimage.
        data = (home/name).read_bytes()
        if name==f.MARKER: data = (helper_tx/'before/FRIDAY-INSTALL.json').read_bytes()
        assert f.digest(data)==before[name]['sha256']
        put(rebind_tx/'before'/name, data)
        put(rebind_tx/'stage'/name, (home/name).read_bytes())
    for name in ('config.yaml.lock','profiles/dest_telegram/config.yaml.lock'):
        put(rebind_tx/'stage'/name, b'')
    history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in rebind_tx.rglob('*') if p.is_file()})
    rows, patches = [], []
    # Synthetic finite three-file fixture; the actual native set stays pending.
    native_files = {'hermes_cli/friday_user_scope.py','agent/tool_result_classification.py','agent/tool_executor.py'}
    new_files = {'tests/agent/test_file_boundary_new.py'} if getattr(request,'param',False) else set()
    native_files |= new_files
    for name in sorted(native_files):
        added = name in new_files
        old = b'' if added else (source/name).read_bytes(); new = old+b'# reviewed file boundary repair\n'
        rows.append({'path':name,'before_sha256':None if added else f.digest(old),'sha256':f.digest(new),
            'bytes':len(new),'mode':'100644','new_file':added})
        patches.append('diff --git a/'+name+' b/'+name+'\n'+('new file mode 100644\n' if added else '')+''.join(difflib.unified_diff(
            old.decode().splitlines(True),new.decode().splitlines(True),fromfile='/dev/null' if added else 'a/'+name,tofile='b/'+name)))
    patchref = put(root/o.SPARK_REQUEST_BUDGET_PATCH, ''.join(patches).encode())
    manifest = {'base_commit':receipt['commit'],'patch':o.SPARK_REQUEST_BUDGET_PATCH,
        'patch_sha256':patchref['sha256'],'files':rows,
        'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in receipt['layers']},
        'prerequisites':{o.SPARK_MULTIPASS_PATCH:s['current']['project_files'][o.SPARK_MULTIPASS_PATCH]}}
    manifestref = doc(root/o.SPARK_REQUEST_BUDGET_MANIFEST, manifest)
    current = copy.deepcopy(previous)
    current['project_files'].update({o.SPARK_REQUEST_BUDGET_MANIFEST:manifestref['sha256'],o.SPARK_REQUEST_BUDGET_PATCH:patchref['sha256']})
    beforepins = {n:previous['project_files'][n] for n in o.SPARK_REQUEST_BUDGET_PROJECT_BEFORE}
    candidate = Path(o.__file__).read_bytes()
    current['project_files']['scripts/friday_ordinary_install.py'] = put(root/'scripts/friday_ordinary_install.py',candidate)['sha256']
    plugin = next(iter(o.SPARK_REQUEST_BUDGET_PLUGIN_FILES))
    pluginref = put(root/plugin, b'# accepted one plugin causal diagnostic\n')
    current['project_files'][plugin] = pluginref['sha256']
    afterpins = {n:put(root/n,b'# accepted producer '+n.encode()+b'\n')['sha256']
        for n in o.SPARK_REQUEST_BUDGET_PROJECT_AFTER if n != plugin}
    afterpins[plugin] = pluginref['sha256']
    current['project_files'].update(afterpins)
    curref = doc(tmp_path/'source80-input.json', current)
    req = {'schema':'friday.ordinary-telegram-source-update.v34', 'seconds':180, 'home':str(home),
        'previous_input':prevref,'current_input':curref,'marker':pin(home/f.MARKER),
        'source_receipt':pin(home/'hermes-agent.source.json'),'stamp':pin(source/'install-stamp.json'),
        'configuration':pin(home/'config.yaml'),'profile':pin(home/'FRIDAY-PROFILE.json'),
        'launcher':s['request']['launcher'],'credential_files':{'.env':pin(home/'.env'),'auth.json':None},
        'native_unit':s['request']['native_unit'],'transaction_history':history,
        'predecessor_update':helperref,'inference_rebind':rebindref}
    requestpath = tmp_path/'source80-request.json'; doc(requestpath, req)
    for name,value in {'SPARK_REQUEST_BUDGET_MANIFEST_SHA256':manifestref['sha256'],
        'SPARK_REQUEST_BUDGET_PATCH_SHA256':patchref['sha256'],'SPARK_REQUEST_BUDGET_FILES':native_files,
        'SPARK_REQUEST_BUDGET_NEW_FILES':new_files,'SPARK_REQUEST_BUDGET_PREVIOUS_INPUT':prevref['sha256'],
        'SOURCE80_HELPER_REQUEST':helperref['sha256'],'SOURCE80_REBIND_REQUEST':rebindref['sha256'],
        'SOURCE80_REBIND_INTENT':intentref['sha256'],'SOURCE80_REBIND_COMMITTED':committedref['sha256'],
        'SPARK_REQUEST_BUDGET_PROJECT_BEFORE':beforepins,'SPARK_REQUEST_BUDGET_PROJECT_AFTER':afterpins,
        'SPARK_REQUEST_BUDGET_NATIVE_FILES':len(receipt['files']),'SOURCE80_HISTORY_FILES':len(history),
        'PROJECT_INFERENCE_RECONCILIATION_PINS':reconcile_pins}.items(): monkeypatch.setattr(o,name,value)
    for directory in (p for p in home.rglob('*') if p.is_dir()): directory.chmod(0o700)
    def no_replay(*args,**kwargs): raise AssertionError('closed action must never dispatch')
    monkeypatch.setattr(o,'project_update',no_replay)
    monkeypatch.setattr(o,'rebind_inference',no_replay)
    return locals()


def repin(s):
    s['req']['current_input'] = doc(Path(s['req']['current_input']['path']),s['current'])
    doc(s['requestpath'],s['req'])


@pytest.mark.parametrize('installed',[False,True],indirect=True)
def test_one_exact_layer_and_plugin_preserve_every_other_byte_mode_and_inode(installed):
    s=installed; before=snapshot(s['home'])
    states={n:o.update_file_state(s['home']/n) for n in before}
    result=o.update(s['req'],s['requestpath'],Budget(180))
    assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['workers_enabled'] is result['gateway_started'] is False
    assert result['full_release_accepted'] is False
    receipt=f.read_json(s['home']/'hermes-agent.source.json')
    assert len(receipt['layers'])==80 and receipt['layers'][:-1]==s['receipt']['layers']
    assert set(receipt['files'])==set(s['receipt']['files']) | s['new_files']
    marker=f.read_json(s['home']/f.MARKER)
    assert len(s['previous']['project_files'])==231 and len(s['current']['project_files'])==233
    assert marker['ordinary_gateway']['operator_entry']['input']==s['req']['current_input']
    assert marker['plugin_files'][s['plugin']]==s['pluginref']['sha256']
    changed={f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json',s['plugin']} | {'hermes-agent/'+n for n in s['native_files']}
    assert len(changed)==7+len(s['new_files'])
    for name,state in states.items():
        if name not in changed: assert o.update_file_state(s['home']/name)==state
    assert marker['original_attempt']==s['rebound_marker']['original_attempt']
    assert f.read_json(s['source']/'install-stamp.json')['original_clock']=={'expired':True,'remaining':0}
    with pytest.raises(ValueError):
        o.update(s['req'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('fault',['pending_manifest','pending_patch','pending_files','pending_new_files',
    'wrong_manifest','wrong_patch','wrong_before_input','wrong_helper_request','wrong_rebind_request',
    'missing_rebind','extra_field','extra_project','extra_changed_plugin','wrong_plugin_after',
    'wrong_old_helper','script_not_running','native_missing','native_extra','beforeimage','prefix',
    'history_missing','history_changed','reconcile_extra','reconcile_changed','rebind_extra',
    'rebind_stage_changed','rebind_lock_changed','rebind_symlink','root_config','user_config','user_key','runtime'])
def test_invalid_or_unbound_boundary_refuses_before_journal_and_publication(installed,monkeypatch,fault):
    s=installed; req=s['req'];home=s['home'];root=s['root']
    if fault.startswith('pending_'):
        key={'pending_manifest':'MANIFEST_SHA256','pending_patch':'PATCH_SHA256','pending_files':'FILES','pending_new_files':'NEW_FILES'}[fault]
        monkeypatch.setattr(o,'SPARK_REQUEST_BUDGET_'+key,None)
    elif fault in ('wrong_manifest','wrong_patch','wrong_before_input','wrong_helper_request','wrong_rebind_request'):
        key={'wrong_manifest':'MANIFEST_SHA256','wrong_patch':'PATCH_SHA256','wrong_before_input':'PREVIOUS_INPUT','wrong_helper_request':'HELPER_REQUEST','wrong_rebind_request':'REBIND_REQUEST'}[fault]
        prefix='SOURCE80_' if fault in ('wrong_helper_request','wrong_rebind_request') else 'SPARK_REQUEST_BUDGET_'
        monkeypatch.setattr(o,prefix+key,'0'*64)
    elif fault=='missing_rebind':req.pop('inference_rebind')
    elif fault=='extra_field':req['retry']=True
    elif fault=='extra_project':s['current']['project_files']['config/foreign']=put(root/'config/foreign',b'foreign')['sha256']
    elif fault=='extra_changed_plugin':
        n='plugins/friday_rework/unchanged.py';s['current']['project_files'][n]=put(root/n,b'foreign')['sha256']
    elif fault=='wrong_plugin_after':monkeypatch.setattr(o,'SPARK_REQUEST_BUDGET_PROJECT_AFTER',dict(o.SPARK_REQUEST_BUDGET_PROJECT_AFTER,**{s['plugin']:'0'*64}))
    elif fault=='wrong_old_helper':monkeypatch.setattr(o,'SPARK_REQUEST_BUDGET_PROJECT_BEFORE',dict(o.SPARK_REQUEST_BUDGET_PROJECT_BEFORE,**{'scripts/friday_ordinary_install.py':'0'*64}))
    elif fault=='script_not_running':s['current']['project_files']['scripts/friday_ordinary_install.py']=put(root/'scripts/friday_ordinary_install.py',b'foreign updater')['sha256']
    elif fault in ('native_missing','native_extra','prefix'):
        if fault=='native_missing':s['manifest']['files'].pop()
        elif fault=='native_extra':s['manifest']['files'].append(dict(s['manifest']['files'][0],path='foreign.py'))
        else:s['manifest']['installed_prefix'].pop(next(iter(s['manifest']['installed_prefix'])))
        s['current']['project_files'][o.SPARK_REQUEST_BUDGET_MANIFEST]=doc(root/o.SPARK_REQUEST_BUDGET_MANIFEST,s['manifest'])['sha256']
    elif fault=='beforeimage':put(s['source']/'agent/tool_executor.py',b'foreign native',0o644)
    elif fault=='history_missing':req['transaction_history'].pop(next(iter(req['transaction_history'])))
    elif fault=='history_changed':put(home/next(iter(req['transaction_history'])),b'foreign history')
    elif fault=='reconcile_extra':put(home/s['reconcile']/'extra',b'foreign')
    elif fault=='reconcile_changed':put(home/s['reconcile']/'intent.json',b'foreign')
    elif fault=='rebind_extra':put(s['rebind_tx']/'rolled-back.json',b'foreign')
    elif fault=='rebind_stage_changed':put(s['rebind_tx']/'stage/config.yaml',b'foreign')
    elif fault=='rebind_lock_changed':put(s['rebind_tx']/'stage/config.yaml.lock',b'foreign')
    elif fault=='rebind_symlink':
        p=s['rebind_tx']/'stage/config.yaml.lock';p.unlink();p.symlink_to(home/'config.yaml')
    elif fault in ('root_config','user_config','user_key'):
        n={'root_config':'config.yaml','user_config':'profiles/dest_telegram/config.yaml','user_key':'profiles/dest_telegram/.env'}[fault];put(home/n,b'foreign')
        if fault=='root_config':req['configuration']=pin(home/n)
    elif fault=='runtime':s['current']['product']['runtime']['enabled']=True
    repin(s);before=snapshot(home)
    with pytest.raises((ValueError,FileNotFoundError,AssertionError,KeyError)):
        o.update(req,s['requestpath'],Budget(180))
    assert snapshot(home)==before
    assert not (home/'preparation'/('ordinary-source-update-'+req['previous_input']['sha256'])).exists()


@pytest.mark.parametrize('publication',range(1,8))
def test_every_owned_publication_failure_rolls_back_and_cannot_retry(installed,monkeypatch,publication):
    s=installed;before=snapshot(s['home']);original=o.publish_update_file;count=0
    def fail(*args):
        nonlocal count
        count+=1
        if count==publication:raise RuntimeError('injected Source80 publication failure')
        return original(*args)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='injected Source80'):o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    for name,value in before.items():assert after[name]==value
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    assert not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('which',['home','build'])
def test_existing_writer_locks_refuse_before_consumption(installed,which):
    s=installed;p=s['home'] if which=='home' else s['source']/'.web_ui_build.lock'
    if which=='build':put(p,b'',0o644)
    fd=os.open(p,os.O_RDONLY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);before=snapshot(s['home'])
        with pytest.raises(BlockingIOError):o.update(s['req'],s['requestpath'],Budget(180))
        assert snapshot(s['home'])==before
    finally:os.close(fd)


@pytest.mark.parametrize('field,value',[('consumers_started',True),('workers_enabled',True),
    ('database_changed',True),('ready',True),('state','RUNTIME_ACCEPTED')])
def test_coherently_repinned_closed_rebind_cannot_gain_authority(installed,monkeypatch,field,value):
    s=installed;p=s['rebind_tx']/'committed.json';body=f.read_json(p);body[field]=value
    ref=doc(p,body);monkeypatch.setattr(o,'SOURCE80_REBIND_COMMITTED',ref['sha256'])
    s['req']['transaction_history'][str(p.relative_to(s['home']))]=ref['sha256']
    repin(s);before=snapshot(s['home'])
    with pytest.raises(ValueError,match='committed_inference_semantics_required'):
        o.update(s['req'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('kind',['native','plugin','marker'])
def test_foreign_replacement_during_failure_is_retained_stop_unconfirmed(installed,monkeypatch,kind):
    from scripts.dsh_prepare import StopUnconfirmed
    s=installed;original=o.publish_update_file;foreign=None
    name={'native':'hermes-agent/agent/tool_executor.py','plugin':s['plugin'],'marker':f.MARKER}[kind]
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
    assert o.update_file_state(s['home']/name)==foreign


@pytest.mark.parametrize('gate',['composition','identity'])
def test_final_validation_failure_restores_all_owned_files(installed,monkeypatch,gate):
    s=installed;before=snapshot(s['home'])
    if gate=='composition':
        original=f.composition_checked
        def fail(value,*args,**kwargs):
            result=original(value,*args,**kwargs)
            if value==s['current']:raise RuntimeError('postpublication Source80 composition')
            return result
        monkeypatch.setattr(f,'composition_checked',fail)
    else:
        import sys
        gateway=sys.modules['hermes_cli.friday_ordinary_gateway'];original=gateway.check
        def fail(home,**kwargs):
            result=original(home,**kwargs)
            if f.read_json(home/f.MARKER)['input_sha256']==s['req']['current_input']['sha256']:
                raise RuntimeError('postpublication Source80 identity')
            return result
        monkeypatch.setattr(gateway,'check',fail)
    with pytest.raises(RuntimeError,match='postpublication Source80'):
        o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    for name,value in before.items():assert after[name]==value
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])
    assert (tx/'rolled-back.json').is_file() and not (tx/'committed.json').exists()


@pytest.mark.parametrize('installed',[True],indirect=True)
def test_additive_file_publication_failure_removes_only_own_new_inode(installed,monkeypatch):
    s=installed;before=snapshot(s['home']);original=o.publish_update_file
    name='hermes-agent/'+next(iter(s['new_files']))
    def fail(path,*args):
        result=original(path,*args)
        if str(path.relative_to(s['home']))==name:raise RuntimeError('new owned file rollback')
        return result
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='new owned file rollback'):
        o.update(s['req'],s['requestpath'],Budget(180))
    assert not (s['home']/name).exists()
    after=snapshot(s['home'])
    for n,value in before.items():assert after[n]==value


@pytest.mark.parametrize('fault',['before_bytes','original_inode','original_mode','archive_symlink'])
def test_closed_archive_refuses_any_loss_of_original_evidence(installed,fault):
    s=installed;folder='failed-before' if fault=='before_bytes' else 'failed-qualification'
    p=s['archive']/folder/'dsh-safety/workspace/retained-0'
    if fault=='before_bytes':put(p,b'changed archive')
    elif fault=='original_inode':
        other=p.with_name('replacement');put(other,p.read_bytes(),p.stat().st_mode&0o777);os.replace(other,p)
    elif fault=='original_mode':p.chmod(0o600)
    else:p.unlink();p.symlink_to(s['home']/'config.yaml')
    before=snapshot(s['home'])
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('name',['profiles/dest_telegram/config.yaml','profiles/dest_telegram/.env'])
def test_final_live_rebind_drift_rolls_back_owned_source_and_preserves_foreign_change(installed,monkeypatch,name):
    s=installed;before=snapshot(s['home']);original=o.publish_update_file;changed=False
    def drift(path,*args):
        nonlocal changed
        result=original(path,*args)
        if not changed:
            changed=True;put(s['home']/name,b'foreign concurrent profile bytes')
        return result
    monkeypatch.setattr(o,'publish_update_file',drift)
    with pytest.raises(ValueError):o.update(s['req'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    for n,value in before.items():
        if n!=name:assert after[n]==value
    assert (s['home']/name).read_bytes()==b'foreign concurrent profile bytes'
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['prevref']['sha256'])
    assert (tx/'rolled-back.json').is_file() and not (tx/'committed.json').exists()
