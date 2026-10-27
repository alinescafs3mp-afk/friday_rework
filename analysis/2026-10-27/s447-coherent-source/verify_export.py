#!/usr/bin/env python3
"""Check this analysis export without importing any implementation module."""
from pathlib import Path
import ast
import hashlib
import json
import re

def check(root):
    sums = root / 'SHA256SUMS'
    expected = {}
    for line in sums.read_text(encoding='utf-8').splitlines():
        sha, rel = line.split('  ', 1)
        p = Path(rel)
        if not re.fullmatch(r'[0-9a-f]{64}', sha) or p.is_absolute() or '..' in p.parts:
            raise ValueError('invalid manifest entry')
        if rel in expected:
            raise ValueError('duplicate manifest entry')
        expected[rel] = sha
    paths = list(root.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('symlink in export')
    actual = {str(p.relative_to(root)) for p in paths if p.is_file() and p != sums}
    if set(expected) != actual:
        raise ValueError('manifest membership mismatch')
    syntax = 0
    forbidden = [(('.'+'jericho').encode()), (('.'+'codex').encode())]
    for rel, sha in expected.items():
        p = root / rel
        if p.is_symlink():
            raise ValueError('symlink in export')
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError('hash mismatch: '+rel)
        if re.search(rb'(?<![A-Za-z0-9_])/(?:home|root)/', data) or any(value in data for value in forbidden):
            raise ValueError('private filesystem reference: '+rel)
        if rel.endswith('.py'):
            ast.parse(data, filename=rel)
            syntax += 1
    provenance = json.loads((root/'EXPORT-PROVENANCE.json').read_text())
    for row in provenance['files']:
        if hashlib.sha256((root/row['path']).read_bytes()).hexdigest() != row['exported_sha256']:
            raise ValueError('source provenance mismatch')
    if provenance['runtime_equivalence_claimed'] or provenance['private_evidence_exported']:
        raise ValueError('invalid export boundary')
    return {'status':'PASS_EXPORT_CONSISTENCY_ONLY', 'files':len(expected),
            'python_files_parsed_without_import':syntax,
            'runtime_or_user_acceptance_tested':False}

if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).resolve().parent), sort_keys=True))
