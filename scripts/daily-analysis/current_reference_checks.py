import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from test_daily_finalizer import FinalizerTests, HERE, SCRIPT

resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
t = FinalizerTests('test_required_daily_integrity_reference_refusals')
t.setUp()
t.write('analysis/report/current.json', '{}\n')
good = {'path': 'current.json', 'sha256': hashlib.sha256(b'{}\n').hexdigest(), 'bytes': 3}
cases = [
    ('object_absent', 'ABSENT', 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('object_null', None, 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('object_array', [], 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('object_string', 'current.json', 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('path_absent', {'sha256': good['sha256']}, 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('path_null', {**good, 'path': None}, 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('path_integer', {**good, 'path': 3}, 'INVALID_DAILY_INTEGRITY_REFERENCE'),
    ('target_absent', {**good, 'path': 'missing.json'}, 'PUBLIC_REFERENCE_MISSING'),
    ('target_directory', {**good, 'path': '.'}, 'PUBLIC_REFERENCE_MISSING'),
    ('path_empty', {**good, 'path': ''}, 'PUBLIC_REFERENCE_MISSING'),
    ('path_absolute', {**good, 'path': '/current.json'}, 'PUBLIC_REFERENCE_MISSING'),
    ('path_escape', {**good, 'path': '../../../outside.json'}, 'PUBLIC_REFERENCE_MISSING'),
    ('path_backslash', {**good, 'path': '..\\current.json'}, 'PUBLIC_REFERENCE_MISSING'),
    ('hash_absent', {'path': good['path'], 'bytes': 3}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('hash_null', {**good, 'sha256': None}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('hash_short', {**good, 'sha256': 'bad'}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('hash_uppercase', {**good, 'sha256': good['sha256'].upper()}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('hash_wrong', {**good, 'sha256': '0'*64}, 'PUBLIC_REFERENCE_MISMATCH'),
    ('bytes_wrong', {**good, 'bytes': 4}, 'PUBLIC_REFERENCE_MISMATCH'),
    ('bytes_negative', {**good, 'bytes': -1}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('bytes_bool', {**good, 'bytes': True}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('bytes_string', {**good, 'bytes': '3'}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('bytes_float', {**good, 'bytes': 3.0}, 'PUBLIC_REFERENCE_INVALID_ASSERTION'),
    ('positive_historical_provenance', good, None),
]
results = []
for name, artifact, reason in cases:
    old = {'path': 'current.json', 'sha256': '0'*64, 'bytes': 1}
    report = {
        'schema': 'friday.analysis.daily-period-index.v1',
        'ordered_commits': [{'changed_paths': [old]}],
        'changed_paths': [old], 'net_changed_paths': [old],
        'logical_blocks': [{'paths': ['docs/removed.md']}],
        'intermediate_only_paths': ['docs/removed.md'],
        'publication_gaps': [{'target': 'docs/removed.md'}],
    }
    if artifact != 'ABSENT':
        report['integrity_artifact'] = artifact
    t.write('analysis/report/index.json', json.dumps(report))
    end = t.commit(name)
    output = t.root / name
    cmd = [sys.executable, '-B', str(SCRIPT), '--repo', str(t.repo), '--base', t.base,
           '--end', end, '--output', str(output)]
    cp = subprocess.run(cmd, env=t.env, capture_output=True, text=True, timeout=10)
    row = {'case': name, 'base': t.base, 'end': end, 'exit': cp.returncode,
           'stderr': cp.stderr, 'output_created': output.exists()}
    if reason:
        row['pass'] = cp.returncode == 2 and reason in cp.stderr and not output.exists()
    else:
        integrity = json.loads((output / 'publication-integrity.json').read_text())
        index = json.loads((output / 'daily-period-index.json').read_text())
        row['assertions'] = integrity['hash_references']
        row['gaps'] = integrity['publication_gaps']
        row['pass'] = (cp.returncode == 0 and len(integrity['hash_references']) == 1
                       and integrity['hash_references'][0]['status'] == 'PASS'
                       and not integrity['findings'] and not integrity['publication_gaps']
                       and index['stage'] == 'PROVISIONAL_NOT_DAILY_COMPLETE'
                       and not index['runtime_grant'] and not index['product_accepted']
                       and not index['daily_checkpoint_complete'])
    results.append(row)
evidence = {'cpu_affinity': sorted(os.sched_getaffinity(0)), 'address_space_bytes': 1024**3,
            'fixture': str(t.root), 'checks': results, 'owned_handles': 0}
(HERE / 'current-reference-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({'passed': sum(r['pass'] for r in results), 'total': len(results),
                  'failed': [r for r in results if not r['pass']]}))
sys.exit(0 if all(r['pass'] for r in results) else 1)
