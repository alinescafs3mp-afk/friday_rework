"""Exact genuine f.inspect once; callable only after carrier's explicit admission."""
from __future__ import annotations
import hashlib, importlib.util, json, os, stat, time
from pathlib import Path

def run(root,a,inv,previous,clock,deadline,pins):
    state={'phase':'native_inventory','sources':{},'correlation':hashlib.sha256(('inspect:'+pins['request']['sha256']+':'+root['operation_id']).encode()).hexdigest()[:32], 'request_sha256':pins['request']['sha256']}
    d=Path(root['operation_directory'])
    def put(name,value):
        raw=a.encoded(value);fd=os.open(d/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
        directory=os.open(d,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
    try:
        # Authenticate receipt and all 14 exact immediate native consumers BEFORE
        # loader imports native packages. Copies and installed rows must agree.
        receipt=a.protected_read(inv['installed_receipt'],private=False)
        a.require(receipt.get('schema')=='friday.hermes-source.v1','actual_native_receipt_schema')
        for name,row in pins['native'].items():
            a.protected_read(row['cached'],json_document=False)
            actual=receipt.get('files',{}).get(name)
            a.require(type(actual)is dict and actual.get('sha256')==row['actual']['sha256'],'native_receipt_row_join')
            a.protected_read(row['actual'],json_document=False,private=False)
            a._diagnostic_source(state,row['actual'],'native')
        state['phase']='canonical_inventory'
        a.canonical_sources_checked(inv['project_root'],previous)
        for name,digest in previous['project_files'].items():
            a._diagnostic_source(state,{'path':str(Path(inv['project_root'])/name),'sha256':digest},'canonical')
        for name,ref in inv['private_package'].items():
            a.protected_read(ref,json_document=False);a._diagnostic_source(state,ref,'private')
        raw=a.protected_read(pins['loader'],json_document=False);a._diagnostic_source(state,pins['loader'],'private_loader')
        spec=importlib.util.spec_from_file_location('_s344_genuine_private_loader',pins['loader']['path']);loader=importlib.util.module_from_spec(spec)
        exec(compile(raw,pins['loader']['path'],'exec'),loader.__dict__)
        state['phase']='private_loader'
        with loader.load_maintenance(inv['receiver'],package_refs=inv['private_package'],canonical_project=inv['project_root'],project_files=previous['project_files'],installed_receipt=inv['installed_receipt']) as(receiver,Budget,stable):
            # All inherited APPLY clocks/grants in inv/receiver are data only.
            # This route never invokes the receiver's declaration/update APIs.
            start=root['phase_origin_monotonic'];budget=Budget(600,started=start,deadline=start+600)
            budget.check();stable();a.require(time.monotonic()<start+570,'useful_phase_exhausted')
            f=receiver.ordinary.api()
            a.require(f.__file__==str(Path(inv['project_root'])/'scripts/friday_install.py'),'genuine_factory_identity')
            state['phase']='genuine_inspect'
            try:
                result=f.inspect(previous,pins['previous_input']['sha256'])
                # Preserve genuine result before any stable/postcheck/advance.
                put('INSPECT-RETURNED.json',{'schema':'frw.Root.genuine-inspect-return.v1','result':result,'correlation':state['correlation'],'request_sha256':pins['request']['sha256'],'original_clock':pins['original_clock'],'native_backup_effects':'POSSIBLE_UNMEASURED_RECONCILE_WITH_ROOT_SCOPE','unconditional_readonly_claim':False,'no_retry':True})
                state['phase']='inspect_return_saved'
                stable();budget.check()
            finally:
                state['stable_unwind_entered']=True;stable()
    except Exception as error:
        # Reuse accepted privacy projection; no messages, raw paths, locals,
        # exceptions repr or user configuration are serialized in diagnostics.
        put('INSPECT-FAILURE.json',a._diagnostic_payload(state,error))
        raise
