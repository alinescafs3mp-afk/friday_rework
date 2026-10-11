#!/usr/bin/env python3
"""Bounded packaging verification; never import or execute bundled source."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_FILE = 1024 * 1024
MAX_TOTAL = 4 * MAX_FILE

def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result

def load(raw):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def stable(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

def read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
        raise ValueError('unsafe or oversized bundle member')
    raw = path.read_bytes()
    if len(raw) != info.st_size or stable(path.stat()) != stable(info):
        raise ValueError('bundle member changed')
    return raw

def name(value):
    if not isinstance(value, str) or not value:
        raise ValueError('invalid relative member')
    p = Path(value)
    if p.is_absolute() or p.as_posix() != value or any(x in ('.', '..') for x in p.parts):
        raise ValueError('invalid relative member')
    return p

def verify(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('invalid bundle root')
    manifest = load(read(root / 'MANIFEST.json'))
    entries = manifest['files']
    if not 1 <= len(entries) <= 64 or len({e['path'] for e in entries}) != len(entries):
        raise ValueError('invalid manifest cardinality')
    expected = {e['path'] for e in entries} | {'MANIFEST.json'}
    observed = {p.relative_to(root).as_posix() for p in root.rglob('*') if not p.is_dir() or p.is_symlink()}
    if observed != expected or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('bundle membership mismatch')
    total = 0
    documents = {}
    for entry in entries:
        rel = name(entry['path'])
        raw = read(root / rel)
        total += len(raw)
        if total > MAX_TOTAL or len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('bundle byte pin mismatch')
        if rel.suffix == '.py':
            ast.parse(raw, filename=rel.as_posix())
        elif rel.suffix == '.json':
            documents[rel.as_posix()] = load(raw)
    def refs(value, document):
        if isinstance(value, dict):
            if '$ref' in value:
                ref = value['$ref']
                if not isinstance(ref, str) or not ref.startswith('#/'):
                    raise ValueError('unsupported schema reference')
                target = document
                for token in ref[2:].split('/'):
                    key = token.replace('~1', '/').replace('~0', '~')
                    target = target[int(key)] if isinstance(target, list) else target[key]
            for child in value.values():
                refs(child, document)
        elif isinstance(value, list):
            for child in value:
                refs(child, document)
    for rel, document in documents.items():
        if rel.endswith('.schema.json'):
            refs(document, document)
    for target in re.findall(r'\]\(([^)]+)\)', read(root / 'README.md').decode('utf-8')):
        if target not in expected:
            raise ValueError('unresolved README link')
    reconstruction = documents['RECONSTRUCTION.json']['files']
    source_entries = {e['path']: e for e in entries if e['path'].startswith('SOURCE/')}
    if len(reconstruction) != 6 or {e['bundle_path'] for e in reconstruction} != set(source_entries):
        raise ValueError('invalid reconstruction mapping')
    if any(e['sha256'] != source_entries[e['bundle_path']]['sha256'] or
           e['bytes'] != source_entries[e['bundle_path']]['bytes'] or
           e['output_name'] != Path(e['bundle_path']).name for e in reconstruction):
        raise ValueError('reconstruction identity mismatch')
    return reconstruction, total

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--reconstruct', type=Path)
    args = parser.parse_args()
    records, total = verify(args.bundle)
    if args.reconstruct is not None:
        args.reconstruct.mkdir(mode=0o700, exist_ok=False)
        for record in records:
            raw = read(args.bundle / name(record['bundle_path']))
            with (args.reconstruct / name(record['output_name'])).open('xb') as output:
                output.write(raw)
            if hashlib.sha256(read(args.reconstruct / name(record['output_name']))).hexdigest() != record['sha256']:
                raise ValueError('reconstruction byte mismatch')
    print(json.dumps({'status': 'PASS_PACKAGING_ONLY', 'source_files': 6,
                      'manifest_bytes': total, 'source_execution': False,
                      'independent_acceptance': 'PENDING', 'runtime': 'NOT_RUN_NOT_ACCEPTED'}))

if __name__ == '__main__':
    main()
