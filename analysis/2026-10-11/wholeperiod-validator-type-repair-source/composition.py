"""Exact SOURCE composition, relative paths, links, byte pins and public markers."""
import pathlib,json,hashlib,re,sys,argparse,os,stat
if sys.flags.optimize:raise SystemExit('REFUSED: SOURCE requires Python assertions enabled')

def trusted_path(value, *, missing_leaf=False):
 p=pathlib.Path(value).absolute()
 assert '..' not in p.parts,'root contains parent traversal'
 parts=p.parts;current=pathlib.Path(parts[0])
 for i,part in enumerate(parts[1:],1):
  current=current/part
  if missing_leaf and i==len(parts)-1 and not os.path.lexists(current):
   assert current.parent.is_dir();return p
  st=current.lstat()
  assert not stat.S_ISLNK(st.st_mode),'symlink root/ancestor/component refused'
  assert stat.S_ISDIR(st.st_mode) if i<len(parts)-1 else (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)),'nonregular path refused'
 assert p==p.resolve(strict=True),'root must be canonical'
 return p

def trusted_members(root):
 root=trusted_path(root);assert root.is_dir();found=set()
 for p in root.rglob('*'):
  st=p.lstat();assert not stat.S_ISLNK(st.st_mode),'symlink payload/component refused'
  assert stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode),'nonregular member refused'
  if stat.S_ISREG(st.st_mode):found.add(str(p.relative_to(root)))
 return found

def verify(root,expected):
 root=trusted_path(root);trusted_members(root);raw=(root/'MANIFEST.json').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==expected,'SOURCE manifest SHA mismatch'
 obj=json.loads(raw);seen=set()
 for r in obj['files']:
  name=r['path'];assert isinstance(name,str) and name and not name.startswith('/')
  assert all(t not in ('','.','..') for t in name.split('/')) and name not in seen
  seen.add(name);p=trusted_path(root/name);assert p.is_file()
  b=p.read_bytes();assert type(r['bytes']) is int and len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
  assert not re.search(rb'/h[o]me/[A-Za-z0-9_.-]+/|/run/user/[0-9]+|[.]jericho/runtime/|[.]codex/sessions/|-----BEGIN [A-Z ]*PRIVATE KEY-----|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',b),'private marker'
 assert trusted_members(root)==seen|{'MANIFEST.json'}
 return {'SOURCE_files':len(seen),'SOURCE_manifest_sha256':expected,'private_marker_hits':0,'independent_privacy_acceptance':False}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--sha256',required=True);a=p.parse_args();print(json.dumps(verify(a.source,a.sha256)))
