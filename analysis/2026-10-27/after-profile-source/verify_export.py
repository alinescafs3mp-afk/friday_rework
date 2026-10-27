#!/usr/bin/env python3
"""Verify/reconstruct analysis layers in temporary storage; never import them."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

PROVENANCE_SHA256='81ca85e0f927c0cb02bc2c75c215dbf68bb5c051ffb0b44e48a246dae573575b'

def digest(b):
    return hashlib.sha256(b).hexdigest()

def relative(value):
    if not isinstance(value,str) or not value or '\\' in value:
        raise ValueError('invalid relative path')
    p=Path(value)
    if p.is_absolute() or '..' in p.parts or str(p)!=value:
        raise ValueError('invalid relative path')
    return p

def read(root,name):
    p=relative(name)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('unsafe root')
    current=root
    for part in p.parts:
        current=current/part
        if current.is_symlink(): raise ValueError('symlink')
    if not current.is_file() or current.stat().st_size>1048576:
        raise ValueError('invalid file')
    return current.read_bytes()

def check(root,base):
    if root.is_symlink() or not root.is_dir(): raise ValueError('unsafe root')
    paths=list(root.rglob('*'))
    if any(p.is_symlink() for p in paths): raise ValueError('symlink')
    expected={}
    for line in read(root,'SHA256SUMS').decode().splitlines():
        sha,name=line.split('  ',1)
        relative(name)
        if not re.fullmatch('[0-9a-f]{64}',sha) or name in expected or name=='SHA256SUMS':
            raise ValueError('invalid digest entry')
        expected[name]=sha
    actual={str(p.relative_to(root)) for p in paths if p.is_file() and p!=root/'SHA256SUMS'}
    if set(expected)!=actual: raise ValueError('manifest membership mismatch')
    for name,sha in expected.items():
        raw=read(root,name)
        if digest(raw)!=sha: raise ValueError('payload hash mismatch')
        if re.search(rb'(?<![A-Za-z0-9_])/(?:home|root)/',raw):
            raise ValueError('private filesystem path')
        if name.endswith('.py'): ast.parse(raw,filename=name)
    provenance=read(root,'EXPORT-PROVENANCE.json')
    if digest(provenance)!=PROVENANCE_SHA256: raise ValueError('wrong frozen provenance')
    p=json.loads(provenance)
    if p['schema']!='frw.public.after-profile.export-provenance.v1':
        raise ValueError('unknown provenance schema')
    if p['runtime_equivalence_claimed'] or p['private_evidence_exported'] or p['raw_redaction_mapping_exported']:
        raise ValueError('invalid analysis boundary')
    seen=set(); payloads=set(); logical=set(); parsed=0; layers=[]
    with tempfile.TemporaryDirectory(prefix='analysis-export-') as name:
        scratch=Path(name)
        for row in p['base_sources']:
            dest=relative(row['path'])
            if row['path'] in seen: raise ValueError('duplicate baseline source')
            seen.add(row['path']);raw=read(base,row['path'])
            if digest(raw)!=row['sha256'] or len(raw)!=row['bytes']:
                raise ValueError('wrong baseline source')
            target=scratch/dest;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
        if len(seen)!=19: raise ValueError('incomplete prior baseline')
        if len(p['files'])!=15: raise ValueError('incomplete source layers')
        for index,row in enumerate(p['files']):
            expected_layer='after_profile_frozen' if index<13 else 'reviewed_Root_forwarding'
            if row['layer']!=expected_layer: raise ValueError('invalid source layer order')
            if index>=13 and row['logical_path'] not in ['tools/cold/cold_root_entry.py','tools/cold/run_cold_original_clock.UNBOUND.py']:
                raise ValueError('invalid forwarding target')
            dest=relative(row['logical_path']); key=(row['layer'],str(dest))
            if key in logical or row['path'] in payloads: raise ValueError('duplicate source entry')
            logical.add(key);payloads.add(row['path'])
            raw=read(root,row['path'])
            if digest(raw)!=row['payload_sha256'] or len(raw)!=row['payload_bytes']:
                raise ValueError('source payload mismatch')
            target=scratch/dest
            if row['kind']=='addition':
                if row['base_exported_sha256'] is not None or target.exists():
                    raise ValueError('addition overwrites source')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            elif row['kind']=='delta':
                if not target.is_file() or digest(target.read_bytes())!=row['base_exported_sha256']:
                    raise ValueError('wrong delta beforeimage')
                header=('--- a/'+str(dest)+'\n+++ b/'+str(dest)+'\n').encode()
                if not raw.startswith(header) or raw.count(b'\n--- a/'):
                    raise ValueError('unexpected patch target')
                stat=subprocess.run(['git','--no-optional-locks','apply','--numstat'],cwd=scratch,input=raw,capture_output=True,
                                    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}|{'GIT_OPTIONAL_LOCKS':'0'})
                statlines=stat.stdout.decode().splitlines()
                if stat.returncode or len(statlines)!=1 or statlines[0].split('\t',2)[-1]!=str(dest):
                    raise ValueError('unexpected patch membership')
                for flag in ['--check','--apply']:
                    cmd=['git','--no-optional-locks','apply']
                    if flag=='--check': cmd.append('--check')
                    result=subprocess.run(cmd,cwd=scratch,input=raw,capture_output=True,
                                          env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}|{'GIT_OPTIONAL_LOCKS':'0'})
                    if result.returncode: raise ValueError('delta application refused')
            else: raise ValueError('unknown source kind')
            out=target.read_bytes()
            if digest(out)!=row['exported_sha256'] or len(out)!=row['exported_bytes']:
                raise ValueError('reconstructed source mismatch')
            ast.parse(out,filename=str(dest));parsed+=1;layers.append(row['layer'])
        code_payloads={n for n in expected if n.startswith(('deltas/','forwarding/','additions/'))}
        if payloads!=code_payloads: raise ValueError('unmapped source payload')
        for row in p['unchanged_sources_reused']:
            if digest(read(scratch,row['path']))!=row['exported_sha256']:
                raise ValueError('unchanged source mismatch')
    return {'status':'PASS_EXPORT_CONSISTENCY_ONLY','payload_files':len(expected)+1,
            'prior_sources':len(seen),'reconstructed_layers_parsed_without_import':parsed,
            'after_profile_layers':layers.count('after_profile_frozen'),
            'forwarding_layers':layers.count('reviewed_Root_forwarding'),
            'runtime_or_user_acceptance_tested':False,'temporary_storage_removed':True}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,default=Path(__file__).absolute().parent.parent/'s447-coherent-source')
    args=parser.parse_args()
    print(json.dumps(check(Path(__file__).absolute().parent,args.base),sort_keys=True))
