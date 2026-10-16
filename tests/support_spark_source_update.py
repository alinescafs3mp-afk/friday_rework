"""Offline Native78 privacy effect and worker diagnostic transaction, real Git patch parser and owned publication.

Native identity/config checks use finite synthetic source; no service, worker,
registration, model or installed runtime is executed. Recursive consumed-history checks use pinned synthetic requests and journals;
no actual Native78 afterimage or runtime acceptance is claimed.
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
from scripts import dsh_prepare  # Load trusted baseline validator before synthetic ROOT override.
from scripts.install_containment import Budget

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ordinary79_candidate', HERE/'scripts/friday_ordinary_install.py')
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
    for name in ('scripts/friday_install.py','scripts/friday_ordinary_install.py','scripts/worker_install.py','tools/render_dsh_local.py',
                 'scripts/a0_prepare.py','scripts/friday_native.py','scripts/friday_worker_preparation.py',
                 'scripts/friday_ordinary_a0_registration.py','tools/configure_local_test.py','tools/configure_product.py','plugins/friday_rework/user_worker_join.py','plugins/friday_rework/onboarding.py',
                 'plugins/friday_rework/unchanged.py','plugins/friday_rework/adapters/dsh.py','plugins/friday_rework/artifacts.py','plugins/friday_rework/results.py'):
        oldproject[name]=put(root/name,b'# old source\n')['sha256']
    for n in range(39):
        name=f'plugins/friday_rework/retained-{n}.py';oldproject[name]=put(root/name,b'# retained plugin\n')['sha256']
    for n in range(227-len(oldproject)):
        name=f'config/unchanged-{n}.txt';oldproject[name]=put(root/name,b'preserved\n')['sha256']
    oldvalue={'home':str(home),'project_files':oldproject,'product':{'runtime':{'enabled':False}},
              'worker_install':{'dsh':{'web':{'egress_evidence':{'old':'policy'}}}},
              'seconds':1,'original_budget':'never reset','model':'preserve','auth':'preserve'}
    oldvalue['project_files']['tools/render_dsh_local.py']=put(root/'tools/render_dsh_local.py',b'# existing native dialogue continuation\n')['sha256']
    oldref=doc(tmp_path/'old-input.json',oldvalue)
    previous=copy.deepcopy(oldvalue);prevref=oldref
    rows=[];patches=[];files={}
    for name in sorted(o.PRIVACY_EFFECT_FILES):
        before=(b'# existing native privacy-result carrier\n' if name=='gateway/run_turn_runner.py'
                else b'# existing native dialogue continuation\n')
        after=before+b'# reviewed Native77\n'
        added=name in o.PRIVACY_EFFECT_NEW_FILES
        if not added:put(source/name,before,0o644)
        else:(source/name).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if name in oldproject:oldproject[name]=put(root/name,before)['sha256']
        if not added:files[name]={'sha256':f.digest(before),'bytes':len(before),'mode':'100644'}
        rows.append({'path':name,'before_sha256':None if added else f.digest(before),'sha256':f.digest(after),
                     'bytes':len(after),'mode':'100644','new_file':added})
        patches.append('diff --git a/'+name+' b/'+name+'\n'+('new file mode 100644\n' if added else '')+''.join(difflib.unified_diff(
            [] if added else before.decode().splitlines(True),after.decode().splitlines(True),fromfile='/dev/null' if added else 'a/'+name,tofile='b/'+name)))
    for name in sorted(o.SPARK_MULTIPASS_FILES-o.SPARK_MULTIPASS_NEW_FILES):
        data=b'# Native78 existing '+name.encode()+b'\n';put(source/name,data,0o644)
        files[name]={'sha256':f.digest(data),'bytes':len(data),'mode':'100644'}
    # Later layers may modify files introduced by the prior synthetic updates.
    # Keep those absent here so their original addition executes exactly once.
    earlier_additions = o.PRIVACY_EFFECT_NEW_FILES | o.SPARK_MULTIPASS_NEW_FILES
    for name in sorted(o.SPARK_REQUEST_BUDGET_FILES-o.SPARK_REQUEST_BUDGET_NEW_FILES-set(files)-earlier_additions):
        data=b'# Native79 existing '+name.encode()+b'\n';put(source/name,data,0o644)
        files[name]={'sha256':f.digest(data),'bytes':len(data),'mode':'100644'}
    put(source/'retained.txt',b'unchanged native\n',0o644)
    files['retained.txt']={'sha256':f.digest(b'unchanged native\n'),'bytes':17,'mode':'100644'}
    layers=[{'manifest':f'patches/hermes/prior-{n}.json','manifest_sha256':f.digest(str(n).encode()),
             'patch_sha256':f.digest(('patch'+str(n)).encode())} for n in range(77)]
    receipt={'commit':'a'*40,'base_tree':'b'*40,'files':files,'layers':layers}
    receiptref=doc(home/'hermes-agent.source.json',receipt)
    stampref=doc(source/'install-stamp.json',{'fridaySource':{'baseTree':receipt['base_tree'],'layers':layers},
                                           'original_clock':{'expired':True,'remaining':0}})
    # Complete pinned synthetic recursive source.v1..v31 + project.v1..v3 history, including consumed attempts.
    activation=doc(home/o.TRANSACTION/'committed.json',{'state':'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'})
    doc(home/'preparation/ordinary-gateway-archive/retained.json',{'state':'archived-no-retry'})
    history={str(p.relative_to(home)):f.digest(p.read_bytes()) for name in
             (o.TRANSACTION,'preparation/ordinary-gateway-archive') for p in (home/name).rglob('*') if p.is_file()}
    prior=None
    previous_generation=doc(tmp_path/'history-input-0.json',{'id':0})
    for n in range(1,35):
        next_generation=oldref if n==34 else doc(tmp_path/f'history-input-{n}.json',{'id':n})
        req={'schema':f'friday.ordinary-telegram-source-update.v{n}' if n <= 31 else f'friday.ordinary-telegram-project-update.v{n-31}','home':str(home),
             'previous_input':previous_generation,'current_input':next_generation,
             'transaction_history':copy.deepcopy(history)}
        if prior:req['predecessor_update']=prior
        prior=doc(tmp_path/f'old-request-{n}.json',req)
        tx=home/'preparation'/('ordinary-source-update-'+previous_generation['sha256'])
        doc(tx/'intent.json',{'schema':'friday.ordinary-telegram-source-update-transaction.v1',
             'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':prior['sha256'],**({'project_only':True} if n > 31 else {})})
        doc(tx/'committed.json',{'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED','previous_input':previous_generation,
             'current_input':next_generation,'source_receipt_sha256':receiptref['sha256'],
             'gateway_started':False,'workers_enabled':False,**({'project_only':True} if n > 31 else {})})
        put(tx/'before/preserved',b'consumed historical bytes\n')
        history.update({str(p.relative_to(home)):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
        previous_generation=next_generation
    configref=put(home/'config.yaml',b'runtime: false\nworkers: {}\n')
    profileref=doc(home/'FRIDAY-PROFILE.json',{'model':'preserve','resources':'preserve'})
    launchref=put(source/'.hermes/bin/hermes',b'preserved executable\n',0o700)
    unitref=put(tmp_path/'native.service',b'never started\n')
    for name in (n for n in oldproject if n.startswith('plugins/')):
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
    # Existing worker declarations/attempts are retained without a v24 bridge.
    doc(home/'preparation/ordinary-workers-consumed/intent.json',
        {'state':'CONSUMED_NO_RETRY','started_mono':10.0,'deadline_mono':190.0,'runtime_enabled':False})
    # Exact historical project.v3 -> consumed keyless source-only input transition.
    installed_ref = oldref
    recovered = copy.deepcopy(previous)
    for name in ('scripts/friday_install.py','scripts/friday_worker_preparation.py'):
        recovered['project_files'][name] = put(root/name,b'# accepted keyless helper source\n')['sha256']
    recovery_ref = doc(tmp_path/'recovery-input.json',recovered)
    recovery_id = 'native77-project3-keyless-test'
    recovery_tx = home/'preparation'/('ordinary-keyless-recovery-'+recovery_id)
    failed = {'failure.json':b'old consumed failure\n', 'dsh-safety/inputs/bootstrap.py':b'bootstrap',
        'dsh-safety/inputs/web-ca.pem':b'ca', 'dsh-safety/inputs/web-network.mjs':b'network'}
    failures = {n:f.digest(b) for n,b in failed.items()}
    recovery = {'schema':'friday.ordinary-worker-keyless-recovery.v1','recovery_id':recovery_id,
        'home':str(home),'profile':'dest_telegram','installed_input':installed_ref,'recovery_input':recovery_ref,
        'transition':'NEW_PRODUCT_MAINTENANCE_NO_RUNTIME_AUTHORITY','source_receipt':receiptref,
        'root_marker':markerref,'stamp':stampref,'failure':{'path':str(home/'profiles/dest_telegram/workers/qualification/failure.json'),'sha256':failures['failure.json']},
        'qualification_files':failures,'history':[{'path':str(home/n),'sha256':h} for n,h in history.items()]}
    recovery_pin = doc(tmp_path/'recovery-request.json',recovery)
    mapping={str(home/'profiles/dest_telegram/workers/qualification'):str(recovery_tx/'failed-qualification')}
    original_attempt={'started_mono':10,'deadline_mono':310,'budget_seconds':300}
    common={'request_sha256':recovery_pin['sha256'],'recovery_id':recovery_id,'archive_mapping':mapping,
        'original_attempt':original_attempt,'consumers_started':False,'workers_enabled':False,'resume_allowed':False}
    doc(recovery_tx/'intent.json',dict(common,schema=recovery['schema'],state='CONSUMED_NO_RETRY',
        failure=recovery['failure'],runtime_authority='NOT_GRANTED'))
    doc(recovery_tx/'committed.json',dict(common,state='REPAIRED_CONSUMERS_STOPPED_WORKERS_OFF_NEW_RUNTIME_NOT_AUTHORIZED',
        runtime_acceptance='NOT_GRANTED',new_runtime_authority='NOT_GRANTED',ready=False,old_attempt_retry_authorized=False))
    put(recovery_tx/'before'/f.MARKER,(home/f.MARKER).read_bytes())
    for folder in ('failed-before','failed-qualification'):
        for n,b in failed.items():put(recovery_tx/folder/n,b)
    for q in recovery_tx.rglob('*'):
        if q.is_dir():q.chmod(0o700)
    history.update({str(q.relative_to(home)):f.digest(q.read_bytes()) for q in recovery_tx.rglob('*') if q.is_file()})
    previous=recovered;prevref=recovery_ref
    marker['input_sha256']=recovery_ref['sha256'];marker['ordinary_gateway']['operator_entry']['input']=recovery_ref
    markerref=doc(home/f.MARKER,marker)
    # New consumed qualification is preserved in place; it must never be archived by update.
    put(home/'profiles/dest_telegram/workers/qualification/failure.json',b'NEW closed consumed failure\n')
    put(home/'profiles/dest_telegram/workers/qualification/dsh-safety/control.json',b'NEW native control\n')
    put(home/'profiles/dest_telegram/workers/attachment.json',b'workers OFF preparation\n')
    put(home/'preparation/new-normal-setup/intent.json',b'new caller admission closed\n')
    monkeypatch.setattr(o,'PRIVACY_EFFECT_NATIVE_FILES',len(files))
    plugin=next(iter(o.PRIVACY_EFFECT_PLUGIN_FILES))
    monkeypatch.setattr(o,'PRIVACY_EFFECT_PLUGIN_BEFORE',previous['project_files'][plugin])
    plugin_bytes=b'# accepted worker failure diagnostic\n'
    monkeypatch.setattr(o,'PRIVACY_EFFECT_PLUGIN_AFTER',f.digest(plugin_bytes))
    patch='patches/hermes/ordinary-private-refusal-effect.patch';patchref=put(root/patch,''.join(patches).encode())
    manifest={'base_commit':receipt['commit'],'patch':patch,'patch_sha256':patchref['sha256'],
              'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in layers},'files':rows}
    manref=doc(root/o.PRIVACY_EFFECT_MANIFEST,manifest)
    current=copy.deepcopy(previous)
    current['project_files'].update({patch:patchref['sha256'],o.PRIVACY_EFFECT_MANIFEST:manref['sha256']})
    # This is an already consumed synthetic predecessor, not the updater under
    # test. Reading the final working tree here would make its pin unchanged.
    current['project_files']['scripts/friday_ordinary_install.py']=put(root/'scripts/friday_ordinary_install.py',b'# synthetic consumed Native78 updater\n')['sha256']
    current['project_files'][plugin]=put(root/plugin,plugin_bytes)['sha256']
    curref=doc(tmp_path/'next-input.json',current)
    request={'schema':'friday.ordinary-telegram-source-update.v32','seconds':180,'home':str(home),
        'previous_input':prevref,'current_input':curref,'marker':markerref,'source_receipt':receiptref,
        'stamp':stampref,'configuration':configref,'profile':profileref,'launcher':launchref,
        'credential_files':{'.env':None,'auth.json':None},'native_unit':unitref,'transaction_history':history,
        'predecessor_update':prior,'keyless_recovery':recovery_pin}
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
