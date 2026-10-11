import argparse,json,hashlib,pathlib,sys
if not __debug__:raise SystemExit('optimized Python refused')
p=pathlib.Path(__file__).resolve().parent;a=argparse.ArgumentParser();a.add_argument('--manifest-sha256',required=True);x=a.parse_args();raw=(p/'MANIFEST.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==x.manifest_sha256
m=json.loads(raw);names={'MANIFEST.json'}|{r['path']for r in m['files']};assert len(m['files'])==5 and len(names)==6;assert {str(f.relative_to(p))for f in p.rglob('*')if f.is_file()}==names
for r in m['files']:
 f=p/r['path'];assert f.is_file()and not f.is_symlink();b=f.read_bytes();assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256']
s=json.loads((p/'STATUS.json').read_bytes());assert all(s[k]is False for k in ('runtime_admission','daily_checkpoint_complete','release_accepted'));assert 'NOT_ACCEPTED'in s['resources']['strict_from_birth_le_1GiB'];print(json.dumps({'files':6,'source_files':2,'source_execution':False,'runtime_admission':False}))
