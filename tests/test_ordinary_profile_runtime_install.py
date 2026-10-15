"""Offline Native57 transaction, real Git patch parser and owned publication.

Native identity/config checks use finite synthetic source; no service, worker,
registration, model or installed runtime is executed. History and bridge checks
use actual request pins, native journals and protected beforeimage publication.
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
spec = importlib.util.spec_from_file_location('ordinary57_candidate',HERE/'scripts/friday_ordinary_install.py')
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
                 'scripts/a0_prepare.py','scripts/friday_native.py','plugins/friday_rework/onboarding.py',
                 'plugins/friday_rework/unchanged.py'):
        oldproject[name]=put(root/name,b'# old source\n')['sha256']
    for n in range(178-len(oldproject)):
        name=f'config/unchanged-{n}.txt';oldproject[name]=put(root/name,b'preserved\n')['sha256']
    oldvalue={'home':str(home),'project_files':oldproject,'product':{'runtime':{'enabled':False}},
              'worker_install':{'dsh':{'web':{'egress_evidence':{'old':'policy'}}}},
              'seconds':1,'original_budget':'never reset','model':'preserve','auth':'preserve'}
    oldref=doc(tmp_path/'old-input.json',oldvalue)
    previous=copy.deepcopy(oldvalue)
    for name in ('scripts/friday_worker_preparation.py','scripts/friday_ordinary_a0_registration.py'):
        previous['project_files'][name]=put(root/name,b'# prepared\n')['sha256']
    previous['worker_install']['dsh']['web']['egress_evidence']={'new':'policy'}
    prevref=doc(tmp_path/'declarations-input.json',previous)
    checker=b'def check(home, *, role):\n    assert role is False\n    return {"checked": True}\n'
    rows=[];patches=[];files={}
    for name in sorted(o.PROFILE_RUNTIME_FILES):
        before=checker if name.endswith('friday_ordinary_gateway.py') else b'# before\n'
        after=before+b'# reviewed Native57\n'
        put(source/name,before,0o644)
        files[name]={'sha256':f.digest(before),'bytes':len(before),'mode':'100644'}
        rows.append({'path':name,'before_sha256':f.digest(before),'sha256':f.digest(after),
                     'bytes':len(after),'mode':'100644','new_file':False})
        patches.append('diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(
            before.decode().splitlines(True),after.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name)))
    put(source/'retained.txt',b'unchanged native\n',0o644)
    files['retained.txt']={'sha256':f.digest(b'unchanged native\n'),'bytes':17,'mode':'100644'}
    layers=[{'manifest':f'patches/hermes/prior-{n}.json','manifest_sha256':f.digest(str(n).encode()),
             'patch_sha256':f.digest(('patch'+str(n)).encode())} for n in range(56)]
    receipt={'commit':'a'*40,'base_tree':'b'*40,'files':files,'layers':layers}
    receiptref=doc(home/'hermes-agent.source.json',receipt)
    stampref=doc(source/'install-stamp.json',{'fridaySource':{'baseTree':receipt['base_tree'],'layers':layers},
                                           'original_clock':{'expired':True,'remaining':0}})
    # Complete real recursive v1..v10 history, including all consumed attempts.
    activation=doc(home/o.TRANSACTION/'committed.json',{'state':'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'})
    doc(home/'preparation/ordinary-gateway-archive/retained.json',{'state':'archived-no-retry'})
    history={str(p.relative_to(home)):f.digest(p.read_bytes()) for name in
             (o.TRANSACTION,'preparation/ordinary-gateway-archive') for p in (home/name).rglob('*') if p.is_file()}
    prior=None
    previous_generation=doc(tmp_path/'history-input-0.json',{'id':0})
    for n in range(1,11):
        next_generation=oldref if n==10 else doc(tmp_path/f'history-input-{n}.json',{'id':n})
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
    reports={name:doc(home/'preparation/reports'/(name+'.json'),{'already_completed':name}) for name in
             ('source','toolchain','build','smoke','inventory','a0')}
    prep={'schema':'friday.ordinary-worker-preparation.v1','request_id':'declarations180','seconds':180,
          'home':str(home),'current_input':oldref,'preparation_input':prevref,'source_receipt':receiptref,
          'profile':profileref,'native_unit':unitref,'marker':markerref,'configuration':configref,
          'reports':reports,'history':[activation]}
    prepref=doc(tmp_path/'preparation-request.json',prep)
    worker_tx=home/'preparation/ordinary-workers-declarations180'
    put(worker_tx/('before-'+f.MARKER),(home/f.MARKER).read_bytes())
    put(worker_tx/'before-config.yaml',(home/'config.yaml').read_bytes())
    intent={'request_sha256':prepref['sha256'],'request_id':'declarations180','started_mono':10.0,
            'deadline_mono':190.0,'seconds':180,'resume_allowed':False,'boot_id':'preserve'}
    doc(worker_tx/'intent.json',intent)
    configref=put(home/'config.yaml',b'runtime: false\nworkers: {a0: declared, dsh: declared}\n')
    marker['input_sha256']=prevref['sha256'];marker['profile_files']['config.yaml']=configref['sha256']
    marker['ordinary_gateway']['operator_entry']['input']=prevref
    marker['ordinary_gateway']['configuration_sha256']='declarations-normalized'
    markerref=doc(home/f.MARKER,marker)
    resultref=doc(worker_tx/'result.json',{'state':'BOTH_WORKER_DECLARATIONS_PUBLISHED_QUALIFICATION_PENDING',
        'ready':False,'runtime_enabled':False,'runtime_acceptance':'NOT_GRANTED',
        'original_attempt':intent,'reports':reports,'configuration_sha256':configref['sha256']})
    patch='patches/hermes/ordinary-profile-runtime.patch';patchref=put(root/patch,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':patch,'patch_sha256':patchref['sha256'],
              'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in layers},'files':rows}
    manref=doc(root/o.PROFILE_RUNTIME_MANIFEST,manifest)
    current=copy.deepcopy(previous)
    current['project_files'].update({patch:patchref['sha256'],o.PROFILE_RUNTIME_MANIFEST:manref['sha256']})
    current['project_files']['scripts/friday_ordinary_install.py']=put(root/'scripts/friday_ordinary_install.py',b'# next helper\n')['sha256']
    curref=doc(tmp_path/'next-input.json',current)
    request={'schema':'friday.ordinary-telegram-source-update.v11','seconds':180,'home':str(home),
        'previous_input':prevref,'current_input':curref,'marker':markerref,'source_receipt':receiptref,
        'stamp':stampref,'configuration':configref,'profile':profileref,'launcher':launchref,
        'credential_files':{'.env':None,'auth.json':None},'native_unit':unitref,'transaction_history':history,
        'predecessor_update':prior,'worker_declaration_publication':{'request':prepref,'result':resultref}}
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
    # Unchanged Native56 ordinary checker keeps its existing role=False API;
    # this synthetic source fixture replaces only its native identity contract.
    gateway=ModuleType('hermes_cli.friday_ordinary_gateway')
    def check(home,role=False):
        assert role is False
        assert f.read_json(home/f.MARKER)['runtime_ready'] is False
        assert b'runtime: false' in (home/'config.yaml').read_bytes()
    gateway.check=check;monkeypatch.setitem(sys.modules,gateway.__name__,gateway)
    return locals()


def test_update_preserves_old_layers_attempts_declarations_and_modes(installed):
    s=installed;before=snapshot(s['home']);receipt=copy.deepcopy(s['receipt']);marker=copy.deepcopy(s['marker'])
    result=o.update(s['request'],s['requestpath'],Budget(180))
    assert result['state']=='TELEGRAM_ORDINARY_SOURCE_UPDATED'
    assert result['ready'] is result['gateway_started'] is result['workers_enabled'] is False
    after=f.read_json(s['home']/'hermes-agent.source.json')
    assert after['layers'][:-1]==receipt['layers'] and len(after['layers'])==57
    assert set(after['files'])==set(receipt['files'])
    updated=f.read_json(s['home']/f.MARKER)
    assert updated['original_attempt']==marker['original_attempt'] and updated['target_settings']==marker['target_settings']
    assert updated['runtime_ready'] is False and updated['worker_state']==marker['worker_state']
    for name in ('config.yaml','FRIDAY-PROFILE.json','hermes-agent/.hermes/bin/hermes'):
        assert snapshot(s['home'])[name]==before[name]
    for name,state in before.items():
        if name.startswith('preparation/'):assert snapshot(s['home'])[name]==state
    for row in s['rows']:
        path=s['source']/row['path'];assert f.digest(path.read_bytes())==row['sha256']
        assert stat.S_IMODE(path.stat().st_mode)==0o644
    assert updated['ordinary_gateway']['operator_entry']['input']==s['request']['current_input']
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('fault',['source_prefix','native_extra','mode','old_source','settings','foreign_plugin','changed_onboarding','missing_bridge','predecessor','consumed','credential_file','history_bytes','profile_bytes','stamp_bytes'])
def test_refusals_before_consumption_leave_home_unchanged(installed,fault):
    s=installed;r=s['request'];home=s['home'];root=s['root']
    if fault=='credential_file':put(home/'.env',b'foreign credential')
    elif fault=='history_bytes':put(home/next(n for n in r['transaction_history'] if n.endswith('before/preserved')),b'foreign history')
    elif fault=='profile_bytes':put(home/'FRIDAY-PROFILE.json',b'foreign profile')
    elif fault=='stamp_bytes':put(s['source']/'install-stamp.json',b'foreign stamp')
    elif fault=='missing_bridge':r.pop('worker_declaration_publication')
    elif fault=='old_source':put(s['source']/s['rows'][0]['path'],b'foreign',0o644)
    elif fault=='consumed':(home/'preparation'/('ordinary-source-update-'+r['previous_input']['sha256'])).mkdir(mode=0o700)
    elif fault=='predecessor':
        prior=f.read_json(Path(r['predecessor_update']['path']));prior['schema']='friday.ordinary-telegram-source-update.v9'
        r['predecessor_update']=doc(Path(r['predecessor_update']['path']),prior)
    elif fault in ('source_prefix','native_extra','mode'):
        m=f.read_json(root/o.PROFILE_RUNTIME_MANIFEST)
        if fault=='source_prefix':m['installed_prefix'].pop(next(iter(m['installed_prefix'])))
        elif fault=='native_extra':m['files'].append(dict(m['files'][0],path='foreign.py'))
        else:m['files'][0]['mode']='100755'
        ref=doc(root/o.PROFILE_RUNTIME_MANIFEST,m);s['current']['project_files'][o.PROFILE_RUNTIME_MANIFEST]=ref['sha256']
    elif fault=='settings':s['current']['product']['runtime']['enabled']=True
    elif fault=='changed_onboarding':s['current']['project_files']['plugins/friday_rework/onboarding.py']=put(root/'plugins/friday_rework/onboarding.py',b'foreign onboarding\n')['sha256']
    else:s['current']['project_files']['plugins/friday_rework/unchanged.py']='0'*64
    if fault not in ('missing_bridge','old_source','consumed','predecessor','credential_file','history_bytes','profile_bytes','stamp_bytes'):
        r['current_input']=doc(Path(r['current_input']['path']),s['current'])
    doc(s['requestpath'],r);before=snapshot(home)
    with pytest.raises((ValueError,AssertionError)):o.update(r,s['requestpath'],Budget(180))
    assert snapshot(home)==before


@pytest.mark.parametrize('fault',['result_state','report_pin','attempt_clock','marker_scope','before_config','bridge_input','report_bytes'])
def test_declaration_publication_bridge_rejects_unproved_mismatch(installed,fault):
    s=installed;r=s['request'];m=copy.deepcopy(s['marker']);proof=r['worker_declaration_publication']
    if fault in ('result_state','report_pin','attempt_clock'):
        path=Path(proof['result']['path']);value=f.read_json(path)
        if fault=='result_state':value['state']='PENDING_NATIVE_HOST_MAINTENANCE_REQUIRED'
        elif fault=='report_pin':value['reports']['build']['sha256']='0'*64
        else:value['original_attempt']['seconds']=181
        proof['result']=doc(path,value)
    elif fault=='report_bytes':put(Path(s['reports']['build']['path']),b'foreign report')
    elif fault=='marker_scope':m['target_settings']['preserved']=False
    elif fault=='before_config':put(s['worker_tx']/'before-config.yaml',b'foreign')
    else:r['previous_input']=r['current_input']
    with pytest.raises(ValueError):o.checked_worker_declaration_publication(s['home'],r,s['req'],m)


def test_failed_publication_restores_exact_owned_bytes_without_replaying(installed,monkeypatch):
    s=installed;before=snapshot(s['home']);original=o.publish_update_file;count=0
    def fail(*args):
        nonlocal count
        count+=1
        if count==4:raise RuntimeError('injected publication failure')
        return original(*args)
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(RuntimeError,match='injected'):o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    for name,state in before.items():assert after[name]==state
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state']=='ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    assert not (tx/'committed.json').exists()
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


def test_unchanged_plugin_is_accepted_without_republication(installed):
    s=installed;name='plugins/friday_rework/onboarding.py';path=s['home']/name
    before=o.update_file_state(path)
    s['current']['project_files'][name]=put(s['root']/name,b'# old source\n')['sha256']
    s['request']['current_input']=doc(Path(s['request']['current_input']['path']),s['current'])
    doc(s['requestpath'],s['request'])
    o.update(s['request'],s['requestpath'],Budget(180))
    assert o.update_file_state(path)==before


def test_real_git_parser_refuses_unlisted_patch_target_before_journal(installed):
    s=installed;root=s['root'];patch=root/s['patch']
    extra=b'diff --git a/foreign.py b/foreign.py\n--- a/foreign.py\n+++ b/foreign.py\n@@ -1 +1 @@\n-before\n+after\n'
    patchref=put(patch,patch.read_bytes()+extra)
    s['manifest']['patch_sha256']=patchref['sha256']
    manref=doc(root/o.PROFILE_RUNTIME_MANIFEST,s['manifest'])
    s['current']['project_files'].update({s['patch']:patchref['sha256'],o.PROFILE_RUNTIME_MANIFEST:manref['sha256']})
    s['request']['current_input']=doc(Path(s['request']['current_input']['path']),s['current'])
    doc(s['requestpath'],s['request']);before=snapshot(s['home'])
    from scripts.hermes_prepare import Refused
    with pytest.raises(Refused,match='overlay_file_inventory_mismatch'):
        o.update(s['request'],s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


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


def test_worker_journal_drift_before_commit_refuses_and_restores_own_source(installed,monkeypatch):
    s=installed;gateway=s['gateway'];original=gateway.check;before=snapshot(s['home']);calls=0
    def drift(home,role=False):
        nonlocal calls
        original(home,role=role);calls+=1
        if calls==3:put(s['worker_tx']/'before-config.yaml',b'foreign journal')
    monkeypatch.setattr(gateway,'check',drift)
    with pytest.raises(ValueError,match='worker_beforeimage_changed'):
        o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    for name,state in before.items():
        if name!='preparation/ordinary-workers-declarations180/before-config.yaml':assert after[name]==state
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert not (tx/'committed.json').exists()
