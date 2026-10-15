"""Offline Native58 interaction-scope transaction, real Git patch parser and owned publication.

Native identity/config checks use finite synthetic source; no service, worker,
registration, model or installed runtime is executed. Recursive consumed-history checks use pinned synthetic requests and journals;
no actual Native58 afterimage or runtime acceptance is claimed.
"""
import contextlib
import copy
import difflib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType

import pytest

from scripts import friday_install as f
from scripts.install_containment import Budget

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ordinary58_candidate',HERE/'scripts/friday_ordinary_install.py')
o = importlib.util.module_from_spec(spec);spec.loader.exec_module(o)


def put(path,data,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_bytes(data);path.chmod(mode)
    return {'path':str(path),'sha256':f.digest(data)}


def doc(path,value):return put(path,o.encoded(value))

def pin(path):return {'path':str(path),'sha256':f.digest(path.read_bytes())}


def snapshot(home):
    return {str(p.relative_to(home)):(p.read_bytes(),stat.S_IMODE(p.stat().st_mode))
            for p in home.rglob('*') if p.is_file()}


@pytest.fixture
def installed(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir(mode=0o700);source=home/'hermes-agent';source.mkdir(mode=0o700)
    root=tmp_path/'project';root.mkdir(mode=0o700);monkeypatch.setattr(f,'ROOT',root)
    monkeypatch.setenv('HERMES_HOME',str(home))
    (home/'preparation').mkdir(mode=0o700)
    oldproject={}
    for name in ('scripts/friday_install.py','scripts/friday_ordinary_install.py','scripts/worker_install.py',
                 'scripts/a0_prepare.py','scripts/friday_native.py','scripts/friday_worker_preparation.py',
                 'scripts/friday_ordinary_a0_registration.py','plugins/friday_rework/onboarding.py',
                 'plugins/friday_rework/unchanged.py'):
        oldproject[name]=put(root/name,b'# old source\n')['sha256']
    for n in range(182-len(oldproject)):
        name=f'config/unchanged-{n}.txt';oldproject[name]=put(root/name,b'preserved\n')['sha256']
    oldvalue={'home':str(home),'project_files':oldproject,'product':{'runtime':{'enabled':False}},
              'worker_install':{'dsh':{'web':{'egress_evidence':{'old':'policy'}}}},
              'seconds':1,'original_budget':'never reset','model':'preserve','auth':'preserve'}
    oldref=doc(tmp_path/'old-input.json',oldvalue)
    previous=copy.deepcopy(oldvalue);prevref=oldref
    checker=b'def check(home, *, role):\n    assert role is False\n    return {"checked": True}\n'
    rows=[];patches=[];files={}
    for name in sorted(o.INTERACTION_SCOPE_FILES):
        before=checker if name.endswith('friday_ordinary_gateway.py') else b'# before\n'
        after=before+b'# reviewed Native58\n'
        put(source/name,before,0o644)
        files[name]={'sha256':f.digest(before),'bytes':len(before),'mode':'100644'}
        rows.append({'path':name,'before_sha256':f.digest(before),'sha256':f.digest(after),
                     'bytes':len(after),'mode':'100644','new_file':False})
        patches.append('diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(
            before.decode().splitlines(True),after.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name)))
    put(source/'retained.txt',b'unchanged native\n',0o644)
    files['retained.txt']={'sha256':f.digest(b'unchanged native\n'),'bytes':17,'mode':'100644'}
    layers=[{'manifest':f'patches/hermes/prior-{n}.json','manifest_sha256':f.digest(str(n).encode()),
             'patch_sha256':f.digest(('patch'+str(n)).encode())} for n in range(57)]
    receipt={'commit':'a'*40,'base_tree':'b'*40,'files':files,'layers':layers}
    receiptref=doc(home/'hermes-agent.source.json',receipt)
    stampref=doc(source/'install-stamp.json',{'fridaySource':{'baseTree':receipt['base_tree'],'layers':layers},
                                           'original_clock':{'expired':True,'remaining':0}})
    # Complete real recursive v1..v11 history, including all consumed attempts.
    activation=doc(home/o.TRANSACTION/'committed.json',{'state':'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'})
    doc(home/'preparation/ordinary-gateway-archive/retained.json',{'state':'archived-no-retry'})
    history={str(p.relative_to(home)):f.digest(p.read_bytes()) for name in
             (o.TRANSACTION,'preparation/ordinary-gateway-archive') for p in (home/name).rglob('*') if p.is_file()}
    prior=None
    previous_generation=doc(tmp_path/'history-input-0.json',{'id':0})
    for n in range(1,12):
        next_generation=oldref if n==11 else doc(tmp_path/f'history-input-{n}.json',{'id':n})
        req={'schema':f'friday.ordinary-telegram-source-update.v{n}','home':str(home),
             'previous_input':previous_generation,'current_input':next_generation,
             'transaction_history':copy.deepcopy(history)}
        if prior:req['predecessor_update']=prior
        prior=doc(tmp_path/f'old-request-{n}.json',req)
        tx=home/'preparation'/('ordinary-source-update-'+previous_generation['sha256'])
        doc(tx/'intent.json',{'schema':'friday.ordinary-telegram-source-update-transaction.v1',
             'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':prior['sha256']})
        doc(tx/'committed.json',{'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED','previous_input':previous_generation,
             'current_input':next_generation,'source_receipt_sha256':receiptref['sha256'],
             'gateway_started':False,'workers_enabled':False})
        put(tx/'before/preserved',b'consumed historical bytes\n')
        history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
        previous_generation=next_generation
    configref=put(home/'config.yaml',b'runtime: false\nworkers: {}\n')
    profileref=doc(home/'FRIDAY-PROFILE.json',{'model':'preserve','resources':'preserve'})
    launchref=put(source/'.hermes/bin/hermes',b'preserved executable\n',0o700)
    unitref=put(tmp_path/'native.service',b'never started\n')
    for name in ('plugins/friday_rework/onboarding.py','plugins/friday_rework/unchanged.py'):
        put(home/name,(root/name).read_bytes())
    marker={'schema':f.SCHEMA,'state':'INSTALLED_TEMPLATE_INCOMPLETE','completion_stage':'TELEGRAM_ORDINARY',
        'home':str(home),'source':str(source),'runtime_ready':False,'worker_state':'BOTH_WORKERS_PREPARATION_PENDING',
        'input_sha256':oldref['sha256'],'source_receipt_sha256':receiptref['sha256'],
        'profile_files':{'config.yaml':configref['sha256'],'FRIDAY-PROFILE.json':profileref['sha256']},
        'plugin_files':{n:p for n,p in oldproject.items() if n.startswith('plugins/')},
        'ordinary_gateway':{'operator_entry':{'input':oldref,'script':pin(root/'scripts/friday_native.py')},
            'configuration_sha256':'old-normalized','source_receipt_sha256':receiptref['sha256'],
            'credential_files':{'.env':None,'auth.json':None},'baseline':{'preserved':True}},
        'original_attempt':{'clock':'expired','accounting':[1,2,3]},'target_settings':{'preserved':True}}
    markerref=doc(home/f.MARKER,marker)
    # Existing worker declarations/attempts are retained without a v12 bridge.
    doc(home/'preparation/ordinary-workers-consumed/intent.json',
        {'state':'CONSUMED_NO_RETRY','started_mono':10.0,'deadline_mono':190.0,'runtime_enabled':False})
    patch='patches/hermes/ordinary-interaction-scope.patch';patchref=put(root/patch,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':patch,'patch_sha256':patchref['sha256'],
              'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in layers},'files':rows}
    manref=doc(root/o.INTERACTION_SCOPE_MANIFEST,manifest)
    current=copy.deepcopy(previous)
    current['project_files'].update({patch:patchref['sha256'],o.INTERACTION_SCOPE_MANIFEST:manref['sha256']})
    current['project_files']['scripts/friday_ordinary_install.py']=put(root/'scripts/friday_ordinary_install.py',b'# next helper\n')['sha256']
    curref=doc(tmp_path/'next-input.json',current)
    request={'schema':'friday.ordinary-telegram-source-update.v12','seconds':180,'home':str(home),
        'previous_input':prevref,'current_input':curref,'marker':markerref,'source_receipt':receiptref,
        'stamp':stampref,'configuration':configref,'profile':profileref,'launcher':launchref,
        'credential_files':{'.env':None,'auth.json':None},'native_unit':unitref,'transaction_history':history,
        'predecessor_update':prior}
    requestpath=tmp_path/'request.json';doc(requestpath,request)
    def spec_checked(value,**kwargs):
        for name,sha in value['project_files'].items():assert f.digest(f.owned_file(root/name))==sha
        return home,{'hermes':{}}
    def composition(value,source,receipt,donor):
        for name,row in receipt['files'].items():assert f.digest(f.owned_file(source/name))==row['sha256']
    monkeypatch.setattr(f,'spec_checked',spec_checked);monkeypatch.setattr(f,'composition_checked',composition)
    monkeypatch.setattr(f,'native_packages',lambda source:None)
    @contextlib.contextmanager
    def stopped(*args):yield lambda:None
    monkeypatch.setattr(o,'stopped_consumers',stopped)
    # Unchanged ordinary checker keeps its existing role=False API;
    # this synthetic source fixture replaces only its native identity contract.
    gateway=ModuleType('hermes_cli.friday_ordinary_gateway')
    def check(home,role=False):
        assert role is False
        assert f.read_json(home/f.MARKER)['runtime_ready'] is False
        assert b'runtime: false' in (home/'config.yaml').read_bytes()
    gateway.check=check;monkeypatch.setitem(sys.modules,gateway.__name__,gateway)
    return locals()


def test_source58_exact_three_files_retains_57_layers_and_consumed_state(installed,monkeypatch):
    s=installed;before=snapshot(s['home']);receipt=copy.deepcopy(s['receipt']);marker=copy.deepcopy(s['marker'])
    # v12 must never re-enter the one-off worker declaration bridge.
    def no_bridge(*args):raise AssertionError('v12 must not replay worker publication')
    monkeypatch.setattr(o,'checked_worker_declaration_publication',no_bridge)
    assert len(s['previous']['project_files'])==182 and len(s['current']['project_files'])==184
    assert 'worker_declaration_publication' not in s['request']
    result=o.update(s['request'],s['requestpath'],Budget(180))
    assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['gateway_started'] is result['workers_enabled'] is False
    after=f.read_json(s['home']/'hermes-agent.source.json')
    assert after['layers'][:-1]==receipt['layers'] and len(after['layers'])==58
    assert after['layers'][-1]['manifest']==o.INTERACTION_SCOPE_MANIFEST
    assert set(after['files'])==set(receipt['files'])
    updated=f.read_json(s['home']/f.MARKER)
    assert updated['original_attempt']==marker['original_attempt'] and updated['target_settings']==marker['target_settings']
    assert updated['runtime_ready'] is False and updated['worker_state']==marker['worker_state']
    after_snapshot=snapshot(s['home'])
    for name,state in before.items():
        if name.startswith(('preparation/','plugins/')) or name in ('config.yaml','FRIDAY-PROFILE.json','hermes-agent/.hermes/bin/hermes'):
            assert after_snapshot[name]==state
    assert {row['path'] for row in s['rows']}=={
        'gateway/run_inbound_consumer.py','hermes_cli/friday_dashboard_owner.py','hermes_cli/web_routers/status.py'}
    for row in s['rows']:
        path=s['source']/row['path'];assert f.digest(path.read_bytes())==row['sha256']
        assert stat.S_IMODE(path.stat().st_mode)==0o644
    assert updated['ordinary_gateway']['operator_entry']['input']==s['request']['current_input']
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('fault',[
    'source_prefix','native_extra','native_missing','mode','old_source','settings','foreign_plugin',
    'changed_onboarding','changed_worker_helper','foreign_project','wrong_project_count',
    'missing_predecessor','extra_bridge','unknown_field','predecessor_version','predecessor_input',
    'predecessor_receipt','predecessor_uncommitted','consumed','credential_file','credential_scope',
    'history_bytes','history_inventory','profile_bytes','configuration_bytes','stamp_bytes'])
def test_refusals_before_consumption_leave_home_unchanged(installed,fault):
    s=installed;r=s['request'];home=s['home'];root=s['root'];current=s['current']
    if fault=='credential_file':put(home/'.env',b'foreign credential')
    elif fault=='credential_scope':r['credential_files']['other.json']=None
    elif fault=='history_bytes':put(home/next(n for n in r['transaction_history'] if n.endswith('before/preserved')),b'foreign history')
    elif fault=='history_inventory':r['transaction_history'].pop(next(iter(r['transaction_history'])))
    elif fault=='profile_bytes':put(home/'FRIDAY-PROFILE.json',b'foreign profile')
    elif fault=='configuration_bytes':put(home/'config.yaml',b'runtime: false\nforeign: true\n')
    elif fault=='stamp_bytes':put(s['source']/'install-stamp.json',b'foreign stamp')
    elif fault=='missing_predecessor':r.pop('predecessor_update')
    elif fault=='extra_bridge':r['worker_declaration_publication']={'request':s['prevref'],'result':s['prevref']}
    elif fault=='unknown_field':r['enable_workers']=True
    elif fault=='old_source':put(s['source']/s['rows'][0]['path'],b'foreign',0o644)
    elif fault=='consumed':(home/'preparation'/('ordinary-source-update-'+r['previous_input']['sha256'])).mkdir(mode=0o700)
    elif fault in ('predecessor_version','predecessor_input','predecessor_receipt','predecessor_uncommitted'):
        path=Path(r['predecessor_update']['path']);prior=f.read_json(path)
        tx=home/'preparation'/('ordinary-source-update-'+prior['previous_input']['sha256'])
        if fault=='predecessor_version':prior['schema']='friday.ordinary-telegram-source-update.v10'
        elif fault=='predecessor_input':prior['current_input']=doc(path.with_name('foreign-current.json'),{'foreign':'input'})
        if fault in ('predecessor_version','predecessor_input'):
            r['predecessor_update']=doc(path,prior)
            intent=f.read_json(tx/'intent.json');intent['request_sha256']=r['predecessor_update']['sha256'];doc(tx/'intent.json',intent)
            committed=f.read_json(tx/'committed.json');committed['current_input']=prior['current_input'];doc(tx/'committed.json',committed)
        elif fault=='predecessor_receipt':
            committed=f.read_json(tx/'committed.json');committed['source_receipt_sha256']='0'*64;doc(tx/'committed.json',committed)
        else:doc(tx/'rolled-back.json',{'state':'ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'})
        # Keep the declared archive coherent to exercise exact version/binding checks.
        for path in tx.rglob('*'):
            if path.is_file():r['transaction_history'][str(path.relative_to(home))]=f.digest(path.read_bytes())
    elif fault in ('source_prefix','native_extra','native_missing','mode'):
        m=f.read_json(root/o.INTERACTION_SCOPE_MANIFEST)
        if fault=='source_prefix':m['installed_prefix'].pop(next(iter(m['installed_prefix'])))
        elif fault=='native_extra':m['files'].append(dict(m['files'][0],path='foreign.py'))
        elif fault=='native_missing':m['files'].pop()
        else:m['files'][0]['mode']='100755'
        ref=doc(root/o.INTERACTION_SCOPE_MANIFEST,m);current['project_files'][o.INTERACTION_SCOPE_MANIFEST]=ref['sha256']
    elif fault=='settings':current['product']['runtime']['enabled']=True
    elif fault=='changed_onboarding':current['project_files']['plugins/friday_rework/onboarding.py']=put(root/'plugins/friday_rework/onboarding.py',b'foreign onboarding\n')['sha256']
    elif fault=='changed_worker_helper':current['project_files']['scripts/friday_worker_preparation.py']=put(root/'scripts/friday_worker_preparation.py',b'foreign worker\n')['sha256']
    elif fault=='foreign_project':current['project_files']['config/foreign.txt']=put(root/'config/foreign.txt',b'foreign\n')['sha256']
    elif fault=='wrong_project_count':
        name='config/unchanged-0.txt';current['project_files'].pop(name)
        # Coherently rebind the consumed v11 result, so the 181->183 count
        # refusal cannot pass merely because an earlier request pin is stale.
        s['previous']['project_files'].pop(name)
        r['previous_input']=doc(Path(r['previous_input']['path']),s['previous'])
        marker=f.read_json(home/f.MARKER);marker['input_sha256']=r['previous_input']['sha256']
        marker['ordinary_gateway']['operator_entry']['input']=r['previous_input']
        r['marker']=doc(home/f.MARKER,marker)
        path=Path(r['predecessor_update']['path']);prior=f.read_json(path)
        prior['current_input']=r['previous_input'];r['predecessor_update']=doc(path,prior)
        tx=home/'preparation'/('ordinary-source-update-'+prior['previous_input']['sha256'])
        intent=f.read_json(tx/'intent.json');intent['request_sha256']=r['predecessor_update']['sha256'];doc(tx/'intent.json',intent)
        committed=f.read_json(tx/'committed.json');committed['current_input']=r['previous_input'];doc(tx/'committed.json',committed)
        for path in tx.rglob('*'):
            if path.is_file():r['transaction_history'][str(path.relative_to(home))]=f.digest(path.read_bytes())
    else:current['project_files']['plugins/friday_rework/unchanged.py']='0'*64
    r['current_input']=doc(Path(r['current_input']['path']),current)
    doc(s['requestpath'],r);before=snapshot(home)
    reasons={'wrong_project_count':'ordinary_update_exact_interaction_scope_delta_required',
             'predecessor_version':'ordinary_update_predecessor_version_changed',
             'predecessor_input':'ordinary_update_predecessor_binding_changed',
             'predecessor_receipt':'ordinary_update_predecessor_binding_changed',
             'missing_predecessor':'ordinary_update_explicit_request_required',
             'extra_bridge':'ordinary_update_explicit_request_required',
             'unknown_field':'ordinary_update_explicit_request_required',
             'native_extra':'ordinary_update_exact_native_files_required',
             'native_missing':'ordinary_update_exact_native_files_required',
             'source_prefix':'ordinary_update_exact_prefix_required'}
    with pytest.raises((ValueError,AssertionError),match=reasons.get(fault)):
        o.update(r,s['requestpath'],Budget(180))
    assert snapshot(home)==before


def test_real_git_parser_refuses_unlisted_patch_target_before_journal(installed):
    s=installed;root=s['root'];patch=root/s['patch']
    extra=b'diff --git a/foreign.py b/foreign.py\n--- a/foreign.py\n+++ b/foreign.py\n@@ -1 +1 @@\n-before\n+after\n'
    patchref=put(patch,patch.read_bytes()+extra);s['manifest']['patch_sha256']=patchref['sha256']
    manref=doc(root/o.INTERACTION_SCOPE_MANIFEST,s['manifest'])
    s['current']['project_files'].update({s['patch']:patchref['sha256'],o.INTERACTION_SCOPE_MANIFEST:manref['sha256']})
    s['request']['current_input']=doc(Path(s['request']['current_input']['path']),s['current'])
    doc(s['requestpath'],s['request']);before=snapshot(s['home'])
    from scripts.hermes_prepare import Refused
    with pytest.raises(Refused,match='overlay_file_inventory_mismatch'):o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('publication',[1,2,3,4,5,6])
def test_failed_publication_restores_exact_owned_bytes_and_consumes_retry(installed,monkeypatch,publication):
    s=installed;before=snapshot(s['home']);original=o.publish_update_file;count=0
    def fail(*args):
        nonlocal count
        count+=1
        if count==publication:raise RuntimeError('injected publication failure')
        return original(*args)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='injected'):o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    for name,state in before.items():assert after[name]==state
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    assert not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('foreign',['inode','mode'])
def test_unknown_published_custody_is_never_overwritten_on_rollback(installed,monkeypatch,foreign):
    from scripts.dsh_prepare import StopUnconfirmed
    s=installed;original=o.publish_update_file;count=0;target=None;foreign_state=None
    def fail(homepath,*args):
        nonlocal count,target,foreign_state
        count+=1
        if count==1:
            result=original(homepath,*args);target=homepath
            if foreign=='inode':
                other=homepath.with_name('foreign');put(other,homepath.read_bytes(),0o644);os.replace(other,homepath)
            else:homepath.chmod(0o600)
            foreign_state=o.update_file_state(homepath)
            return result
        raise RuntimeError('injected custody loss')
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(StopUnconfirmed):o.update(s['request'],s['requestpath'],Budget(180))
    assert o.update_file_state(target)==foreign_state
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert not (tx/'committed.json').exists() and not (tx/'rolled-back.json').exists()
