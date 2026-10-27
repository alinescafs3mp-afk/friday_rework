"""Static analysis-package check. Never imports or executes source excerpts."""
import ast
import hashlib
import json
from pathlib import Path
import re
import textwrap

EXPECTED_FILES = {'README.md', 'manifest.json', 'SOURCE-PROVENANCE.json', 'SHA256SUMS',
                  'verify_export.py', 'host_limits.py', 'runtime_shadow.py',
                  'current_inputs.py', 'installed_source_branch.py', 'native480_bridge.py'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def privacy(raw):
    # Reused analysis-export categories; literal-value screening is private.
    patterns = [rb'(?<![A-Za-z0-9_])/(?:home|root)/', rb'FRW-(?:ROOT|S[0-9]|R[0-9])',
                rb'\.(?:codex|jericho)/',
                rb'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b',
                rb'\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b',
                rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'\b(?:https?|wss?|ssh|postgres(?:ql)?|redis)://',
                rb'(?<![A-Za-z0-9_])(?:88[0-9]{8}|87[0-9]{8})(?![A-Za-z0-9_])',
                rb'(?<![\w.])(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2})(?![\w.])']
    if any(re.search(pattern, raw) for pattern in patterns):
        raise ValueError('private data pattern')


def read(root, name):
    if name not in EXPECTED_FILES or root.is_symlink() or not root.is_dir():
        raise ValueError('unexpected package path')
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise ValueError('invalid package file')
    return path.read_bytes()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def check(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('unsafe package root')
    entries = list(root.iterdir())
    if {p.name for p in entries} != EXPECTED_FILES or any(p.is_symlink() or not p.is_file() for p in entries):
        raise ValueError('package membership mismatch')
    sums = {}
    for line in read(root, 'SHA256SUMS').decode().splitlines():
        sha, name = line.split('  ', 1)
        if (name not in EXPECTED_FILES - {'SHA256SUMS'} or name in sums
                or re.fullmatch('[a-f0-9]{64}', sha) is None):
            raise ValueError('invalid checksum entry')
        sums[name] = sha
    if set(sums) != EXPECTED_FILES - {'SHA256SUMS'}:
        raise ValueError('checksum membership mismatch')
    payloads = {}
    for name in EXPECTED_FILES:
        raw = read(root, name)
        privacy(raw)
        if name != 'SHA256SUMS' and digest(raw) != sums[name]:
            raise ValueError('file hash mismatch')
        payloads[name] = raw
        if name.endswith('.py'):
            ast.parse(raw, filename=name)
    manifest = json.loads(payloads['manifest.json'], object_pairs_hook=unique)
    provenance = json.loads(payloads['SOURCE-PROVENANCE.json'], object_pairs_hook=unique)
    if (manifest['status'] != 'UNBOUND_ANALYSIS'
            or manifest['runtime_equivalence_claimed'] or manifest['worker_or_user_acceptance_claimed']
            or provenance['status'] != 'UNBOUND_ANALYSIS_NOT_A_RUNNABLE_PRODUCT'):
        raise ValueError('analysis boundary changed')
    code = {row['path']: row for row in manifest['code_files']}
    if len(code) != 5 or set(code) != {n for n in EXPECTED_FILES if n.endswith('.py') and n != 'verify_export.py'}:
        raise ValueError('code membership changed')
    for name, row in code.items():
        raw = payloads[name]
        if len(raw) != row['bytes'] or digest(raw) != row['sha256']:
            raise ValueError('code bytes changed')
    counts = {'complete_function_excerpt': 0, 'selected_statement_excerpt': 0}
    if manifest.get('complete_functions') != 8 or manifest.get('selected_statements') != 3:
        raise ValueError('manifest count changed')
    for row in provenance['selected']:
        name = row['output']
        source = payloads[name].decode()
        tree = ast.parse(source)
        if row['kind'] == 'complete_function_excerpt':
            matches = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == row['selector']]
            if len(matches) != 1:
                raise ValueError('function selection changed')
            node = matches[0]
            text = textwrap.dedent('\n'.join(source.splitlines()[node.lineno - 1:node.end_lineno])) + '\n'
        elif row['kind'] == 'selected_statement_excerpt':
            wrappers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == row['selector']]
            if len(wrappers) != 1:
                raise ValueError('statement wrapper changed')
            node = wrappers[0].body[row['statement_index']]
            text = textwrap.dedent('\n'.join(source.splitlines()[node.lineno - 1:node.end_lineno]))
        else:
            raise ValueError('unknown excerpt kind')
        if (digest(text.encode()) != row['exported_excerpt_sha256']
                or digest(ast.dump(node, include_attributes=False).encode()) != row['exported_ast_sha256']):
            raise ValueError('excerpt fidelity changed')
        counts[row['kind']] += 1
    if counts != {'complete_function_excerpt': 8, 'selected_statement_excerpt': 3}:
        raise ValueError('excerpt count changed')
    return {'status': 'PASS_STATIC_EXPORT_ONLY', 'files': len(EXPECTED_FILES),
            'complete_functions': 8, 'selected_statements': 3,
            'source_imports_or_execution': False, 'runtime_or_user_acceptance': False}


if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).absolute().parent), sort_keys=True))
