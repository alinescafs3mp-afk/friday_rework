#!/usr/bin/env python3
"""Finite real owned Git controls for historical/current reference separation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from test_daily_finalizer import FinalizerTests

HERE = Path(__file__).resolve().parent
SCHEMA = 'friday.normal28.public-project-inventory.v2'
INDEX = 'analysis/history/project-source-index.json'


def run_controls():
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    rows = []
    def case(name, change, expect=True, delete=False, sibling=False):
        t = FinalizerTests('test_incremental_manifest_and_readonly'); t.setUp()
        t.write('docs/item.txt', 'original source\n'); origin = t.commit('historical source')
        item = {'repository_file': '../../docs/item.txt',
                'sha256': hashlib.sha256(b'original source\n').hexdigest(), 'bytes': 16}
        obj = {'schema': SCHEMA, 'project_files_count': 1, 'references': [item], 'snapshot_commit': origin}
        if delete:
            (t.repo / 'docs/item.txt').unlink()
        else:
            t.write('docs/item.txt', 'later changed source\n')
        t.write('docs/live.txt', 'current live\n')
        if sibling:
            obj['current_reference'] = {'repository_file': '../../docs/live.txt',
                                        'sha256': hashlib.sha256(b'current live\n').hexdigest(), 'bytes': 13}
        change(obj, t, origin)
        raw = json.dumps(obj, indent=2) + '\n'; t.write(INDEX, raw)
        t.write('analysis/history/MANIFEST.json', json.dumps({'files': [{'path': 'project-source-index.json',
            'sha256': hashlib.sha256(raw.encode()).hexdigest(), 'bytes': len(raw.encode())}]}))
        end = t.commit(name)
        pins = {p: p.read_bytes() for p in [t.repo / '.git/index', t.repo / '.git/config', t.repo / INDEX]}
        result = t.invoke(end=end, success=expect)
        if expect:
            idx, integrity = result
            assert idx['counts']['historical_git_references'] == 1
            assert len(integrity['historical_git_references']) == 1
            assert integrity['historical_git_references'][0]['snapshot_commit'] == origin
            assert integrity['historical_git_references'][0]['status'] == 'PASS'
            assert integrity['findings'] == [] and integrity['publication_gaps'] == []
        else:
            assert not (t.root / 'output').exists()
            expected_kind = (
                'HISTORICAL_GIT_REFERENCE_MISMATCH' if name in {
                    'wrong_historical_hash_even_current_matches', 'wrong_historical_byte_count'}
                else 'INVALID_HISTORICAL_INVENTORY' if name in {
                    'boolean_count_not_an_integer', 'declared_count_mismatch'}
                else 'INVALID_HISTORICAL_SNAPSHOT' if name in {
                    'unknown_snapshot_refused', 'noncommit_snapshot_refused', 'nonancestor_snapshot_refused'}
                else 'HISTORICAL_GIT_REFERENCE_MISSING' if name == 'missing_historical_blob'
                else 'PUBLIC_REFERENCE_MISMATCH' if name in {
                    'legacy_v1_remains_current_assertion', 'unknown_schema_does_not_waive_current_assertion',
                    'current_sibling_bad_hash_still_refused', 'current_sibling_bad_size_still_refused'}
                else 'INVALID_HISTORICAL_INVENTORY' if name == 'snapshot_abbreviation_refused'
                else 'INVALID_HISTORICAL_REFERENCE')
            assert expected_kind in result.stderr, (name, result.stderr)

        assert all(p.read_bytes() == b for p, b in pins.items())
        rows.append({'name': name, 'expected': 'PASS' if expect else 'REFUSED', 'actual': 'PASS',
                     'negative': not expect, 'refusal_kind': expected_kind if not expect else None,
                     'source_executed': False, 'runtime_grant': False})
    noop = lambda o,t,c: None
    case('historical_source_changed_at_current_cutoff', noop)
    case('historical_source_deleted_at_current_cutoff', noop, delete=True)
    case('historical_and_current_sibling_both_checked', noop, sibling=True)
    case('wrong_historical_hash_even_current_matches', lambda o,t,c: o['references'][0].update(
        sha256=hashlib.sha256(b'later changed source\n').hexdigest(),bytes=21), False)
    case('wrong_historical_byte_count', lambda o,t,c: o['references'][0].update(bytes=17), False)
    case('boolean_bytes_not_an_integer', lambda o,t,c: o['references'][0].update(bytes=True), False)
    case('boolean_count_not_an_integer', lambda o,t,c: o.update(project_files_count=True), False)
    case('declared_count_mismatch', lambda o,t,c: o.update(project_files_count=2), False)
    case('duplicate_historical_target', lambda o,t,c: (o['references'].append(copy.deepcopy(o['references'][0])),
                                                    o.update(project_files_count=2)), False)
    case('ambiguous_current_alias_cannot_waive_reference', lambda o,t,c: o['references'][0].update(
        public_sha256=o['references'][0]['sha256']), False)
    case('missing_historical_blob', lambda o,t,c: o['references'][0].update(repository_file='../../docs/missing.txt'),False)
    case('absolute_path_refused', lambda o,t,c: o['references'][0].update(repository_file='/docs/item.txt'), False)
    case('repository_escape_refused', lambda o,t,c: o['references'][0].update(repository_file='../../../outside.txt'),False)
    case('snapshot_abbreviation_refused', lambda o,t,c: o.update(snapshot_commit=c[:12]), False)
    case('unknown_snapshot_refused', lambda o,t,c: o.update(snapshot_commit='f'*40), False)
    case('noncommit_snapshot_refused', lambda o,t,c: o.update(snapshot_commit=t.git('hash-object','docs/item.txt')),False)
    def wrong_branch(o,t,c):
        t.git('checkout','-q','-b','side',c); t.write('side.txt','side\n'); side=t.commit('side snapshot')
        t.git('checkout','-q','main'); o['snapshot_commit']=side
        t.write('docs/item.txt','later changed source\n'); t.write('docs/live.txt','current live\n')
    case('nonancestor_snapshot_refused', wrong_branch, False)
    case('legacy_v1_remains_current_assertion', lambda o,t,c: o.update(schema='friday.normal28.public-project-inventory.v1'),False)
    case('unknown_schema_does_not_waive_current_assertion', lambda o,t,c: o.update(schema=SCHEMA+'-unknown'),False)
    case('current_sibling_bad_hash_still_refused', lambda o,t,c: o['current_reference'].update(sha256='0'*64),False,sibling=True)
    case('current_sibling_bad_size_still_refused', lambda o,t,c: o['current_reference'].update(bytes=999),False,sibling=True)
    result = {'schema': 'friday.historical-reference-owned-controls.v1', 'checks': rows,
              'count': len(rows), 'PASS': len(rows), 'FAIL': 0,
              'negative_controls': sum(x['negative'] for x in rows),
              'fixture_git_only': True, 'runtime_grant': False,
              'all_commands_returned': True, 'background_handles': 0}
    (HERE/'HISTORICAL-REFERENCE-CONTROLS.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'checks'}))


if __name__ == '__main__':
    run_controls()
