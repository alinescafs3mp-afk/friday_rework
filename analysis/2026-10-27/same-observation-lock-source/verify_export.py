#!/usr/bin/env python3
"""Verify analysis source layers only. Never import or execute reconstructed code."""
import ast,hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
PROVENANCE_SHA256='5fd990530a64bb3bb931fb95719db77267db89f30ac17c70c34a64b3a566afaf'
PRIOR_PROVENANCE=['cb5172f6fd8c491832cccc60617f2ef9f491664c6817627a38d873112e4bb3c7', '81ca85e0f927c0cb02bc2c75c215dbf68bb5c051ffb0b44e48a246dae573575b']
def digest(b):return hashlib.sha256(b).hexdigest()
def relative(s):
    if not isinstance(s,str) or not s or "\\" in s:raise ValueError('invalid relative path')
    p=Path(s)
    if p.is_absolute() or '..' in p.parts or str(p)!=s:raise ValueError('invalid relative path')
    return p
def read(root,name):
    if root.is_symlink() or not root.is_dir():raise ValueError('unsafe root')
    current=root
    for part in relative(name).parts:
        current=current/part
        if current.is_symlink():raise ValueError('symlink')
    if not current.is_file() or current.stat().st_size>1048576:raise ValueError('invalid file')
    return current.read_bytes()
def privacy(raw):
    patterns=[rb'(?<![A-Za-z0-9_])/(?:home|root)/',rb'FRW-(?:ROOT|S[0-9]|R[0-9])',rb'\.(?:codex|jericho)/',
      rb'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b',rb'\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b',
      rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\b(?:https?|wss?|ssh|postgres(?:ql)?|redis)://',
      rb'(?<![A-Za-z0-9_])(?:88[0-9]{8}|87[0-9]{8})(?![A-Za-z0-9_])',rb'(?<![\w.])(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2})(?![\w.])']
    if any(re.search(p,raw)for p in patterns):raise ValueError('private data pattern')
def patch(scratch,logical,raw):
    header=('--- a/'+logical+'\n+++ b/'+logical+'\n').encode()
    if not raw.startswith(header) or raw.count(b'\n--- a/'):raise ValueError('unexpected patch header')
    env={k:v for k,v in os.environ.items()if not k.startswith('GIT_')}|{'GIT_OPTIONAL_LOCKS':'0'}
    s=subprocess.run(['git','--no-optional-locks','apply','--numstat'],cwd=scratch,input=raw,capture_output=True,env=env)
    lines=s.stdout.decode().splitlines()
    if s.returncode or len(lines)!=1 or lines[0].split('\t',2)[-1]!=logical:raise ValueError('unexpected patch target')
    for flag in ['--check',None]:
        result=subprocess.run(['git','--no-optional-locks','apply']+([flag]if flag else[]),cwd=scratch,input=raw,capture_output=True,env=env)
        if result.returncode:raise ValueError('patch application refused')
def layer(scratch,root,row):
    logical=str(relative(row['logical_path']));dest=scratch/logical;raw=read(root,row['path'])
    if digest(raw)!=row['payload_sha256'] or len(raw)!=row['payload_bytes']:raise ValueError('payload mismatch')
    if row['kind']=='addition':
        if dest.exists() or row['base_exported_sha256']is not None:raise ValueError('addition overwrite')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    elif row['kind']=='replacement':
        if not dest.is_file() or digest(dest.read_bytes())!=row['base_exported_sha256']:raise ValueError('wrong replacement beforeimage')
        dest.write_bytes(raw)
    elif row['kind']=='delta':
        if not dest.is_file() or digest(dest.read_bytes())!=row['base_exported_sha256']:raise ValueError('wrong beforeimage')
        patch(scratch,logical,raw)
    else:raise ValueError('invalid layer kind')
    out=dest.read_bytes()
    if digest(out)!=row['exported_sha256'] or len(out)!=row['exported_bytes']:raise ValueError('wrong reconstructed source')
    ast.parse(out,filename=logical)
def check(root,prior):
    if root.is_symlink() or not root.is_dir():raise ValueError('unsafe root')
    paths=list(root.rglob('*'))
    if any(p.is_symlink()for p in paths):raise ValueError('symlink')
    sums={}
    for line in read(root,'SHA256SUMS').decode().splitlines():
        sha,name=line.split('  ',1);relative(name)
        if not re.fullmatch('[a-f0-9]{64}',sha) or name in sums or name=='SHA256SUMS':raise ValueError('bad checksum entry')
        sums[name]=sha
    actual={str(p.relative_to(root))for p in paths if p.is_file()and p!=root/'SHA256SUMS'}
    if actual!=set(sums):raise ValueError('manifest membership mismatch')
    for name,sha in sums.items():
        raw=read(root,name)
        if digest(raw)!=sha:raise ValueError('file hash mismatch')
        privacy(raw)
        if name.endswith('.py'):ast.parse(raw,filename=name)
    raw=read(root,'EXPORT-PROVENANCE.json')
    if digest(raw)!=PROVENANCE_SHA256:raise ValueError('wrong frozen provenance')
    p=json.loads(raw)
    if p['schema']!='frw.public.same-observation-lock.export-provenance.v1' or any(p[k]for k in ['runtime_equivalence_claimed','private_evidence_exported','raw_redaction_mapping_exported']):raise ValueError('analysis boundary')
    if not p['exported_sources_intentionally_UNBOUND']:raise ValueError('missing UNBOUND boundary')
    old,previous=p['prior_prefixes'];oldroot=prior/Path(old).name;prevroot=prior/Path(previous).name
    rawold=read(oldroot,'EXPORT-PROVENANCE.json');rawprev=read(prevroot,'EXPORT-PROVENANCE.json')
    if [digest(rawold),digest(rawprev)]!=PRIOR_PROVENANCE:raise ValueError('wrong prior provenance')
    po=json.loads(rawold);pp=json.loads(rawprev)
    with tempfile.TemporaryDirectory(prefix='analysis-source-check-')as folder:
        scratch=Path(folder)
        for row in po['files']:
            raw=read(oldroot,row['path'])
            if digest(raw)!=row['exported_sha256']:raise ValueError('wrong old source')
            dest=scratch/relative(row['path']);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        for row in pp['files']:layer(scratch,prevroot,row)
        expected={row['path']:row for row in p['prior_snapshot_sources']}
        actual={str(f.relative_to(scratch))for f in scratch.rglob('*')if f.is_file()}
        if actual!=set(expected):raise ValueError('wrong prior membership')
        for name,row in expected.items():
            raw=read(scratch,name)
            if digest(raw)!=row['sha256']or len(raw)!=row['bytes']:raise ValueError('wrong prior snapshot')
        seen=set();payloads=set();layers=[]
        for row in p['files']:
            key=(row['layer'],row['logical_path'])
            if key in seen or row['path']in payloads:raise ValueError('duplicate source layer')
            seen.add(key);payloads.add(row['path']);layers.append(row['layer']);layer(scratch,root,row)
        if layers!=['source3']*11+['lock_compat']*3:raise ValueError('wrong layer sequence')
        actualpayloads={n for n in sums if n.startswith(('source3/','lock_compat/'))}
        if payloads!=actualpayloads:raise ValueError('unmapped source payload')
        for row in p['unchanged_sources_reused']:
            if digest(read(scratch,row['logical_path']))!=row['exported_sha256']:raise ValueError('unchanged source mismatch')
    return {'status':'PASS_EXPORT_CONSISTENCY_ONLY','public_files':len(sums)+1,'prior_sources':len(expected),'source3_layers':11,'lock_compat_layers':3,'reconstructed_code_imported_or_executed':False,'runtime_or_user_acceptance_tested':False,'temporary_storage_removed':True}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--prior',type=Path,default=Path(__file__).absolute().parent.parent);args=p.parse_args()
    print(json.dumps(check(Path(__file__).absolute().parent,args.prior),sort_keys=True))
