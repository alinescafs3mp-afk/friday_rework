import hashlib,json,stat
from pathlib import Path
p=Path(__file__).resolve().parent
m=json.loads((p/'MANIFEST.json').read_bytes())
assert m['count']==len(m['files'])==7
for row in m['files']:
 f=p/row['path'];assert f.resolve().is_relative_to(p) and not f.is_symlink() and stat.S_ISREG(f.stat().st_mode)
 b=f.read_bytes();assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
assert json.loads((p/'STATUS.json').read_bytes())['release_accepted'] is False
print('8 public files authenticated; SOURCE only; runtime admission false')
