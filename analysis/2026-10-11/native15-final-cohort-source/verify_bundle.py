"""Portable analysis bundle verifier. Never imports/executes SOURCE or captured targets."""
import ast, hashlib, json, re
from pathlib import Path

def verify(base):
    base=Path(base)
    manifest=json.loads((base/'MANIFEST.json').read_bytes())
    entries=manifest['files']
    names=[v['path'] for v in entries]
    assert len(names)==len(set(names)) and len(entries)<=64
    assert set(p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file())==set(names)|{'MANIFEST.json'}
    for row in entries:
        rel=Path(row['path'])
        assert not rel.is_absolute() and '..' not in rel.parts
        p=base/rel; assert p.is_file() and not p.is_symlink()
        raw=p.read_bytes(); assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        text=raw.decode('utf-8')
        assert not re.search(('/'+'home/|/'+'root/|'+r'\.jericho'+'/runtime/|'+'rollout'+'-20|'+r'sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY'),text)
        if p.suffix=='.py':ast.parse(raw,filename=row['path'])
        if p.suffix=='.json':json.loads(raw)
    reconstruction=json.loads((base/'RECONSTRUCTION.json').read_bytes())
    assert len(reconstruction['source6'])==6
    for row in reconstruction['source6']:
        raw=(base/row['path']).read_bytes()
        assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    state=json.loads((base/'STATUS.json').read_bytes())
    assert state['C5_collector3']=='INDEPENDENT_SOURCE_ACCEPTED'
    assert state['corrected_readiness3']=='INDEPENDENT_SOURCE_ACCEPTED'
    assert state['composition']=='AUTHOR_INERT_DATA_ONLY'
    assert state['runtime']=='NOT_RUN_NOT_ACCEPTED' and state['admission'] is False
    assert state['privacy_review']=='INDEPENDENT_PENDING' and state['publication']=='ROOT_PENDING'
    readme=(base/'README.md').read_text()
    for target in re.findall(r'\[[^]]+\]\(([^)]+)\)',readme):
        assert not Path(target).is_absolute() and '..' not in Path(target).parts and (base/target).is_file()
    return dict(status='PASS_PACKAGING_ONLY',files=len(entries),source6=6,source_execution=0,independent_acceptance=False)

if __name__=='__main__':
    print(json.dumps(verify(Path(__file__).parent)))
