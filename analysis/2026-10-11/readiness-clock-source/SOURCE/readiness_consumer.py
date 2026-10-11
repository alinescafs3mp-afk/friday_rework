"""Strict SOURCE data consumer; no packet can grant live execution authority."""
import json
import os
import stat
import time
from readiness_packet import SCHEMA, GAPS, MAX_PACKET, closed_json, expected_refs, derived, validate_clock
from startup_inventory import Refusal, canonical, need, sha


def consume(raw, *, inputs, collector_refs, native_r2, clock, input_ref, held_bytes, held_metadata, now_epoch=None):
    validate_clock(clock, now_epoch=now_epoch)
    packet = closed_json(raw)
    fields = {'schema', 'assignment', 'input_ref', 'clock', 'records', 'ancestors', 'unsafe_ancestors', 'data',
              'captured_files_count', 'captured_bytes', 'admission', 'independent_acceptance', 'runtime', 'fullgate',
              'missing_proofs', 'readonly_capture_verified', 'payload_sha256'}
    need(type(packet) is dict and set(packet) == fields, 'CLOSED_PACKET_FIELDS')
    need(canonical(packet) == raw, 'CANONICAL_PACKET_BYTES')
    digest = packet['payload_sha256']; unsigned = {k:v for k,v in packet.items() if k != 'payload_sha256'}
    need(type(digest) is str and digest == sha(canonical(unsigned)), 'PACKET_DIGEST')
    need(packet['schema'] == SCHEMA and packet['assignment'] == inputs['assignment'], 'EXACT_SCHEMA_ASSIGNMENT')
    need(type(packet['admission']) is bool and packet['admission'] is False and type(packet['independent_acceptance']) is bool and packet['independent_acceptance'] is False, 'NO_ADMISSION')
    need(packet['runtime'] == 'UNBOUND_NOT_RUN' and packet['fullgate'] == 'NOT_RUN_NOT_ACCEPTED', 'NO_EXECUTION_CREDIT')
    need(type(packet['readonly_capture_verified']) is bool and packet['readonly_capture_verified'] is True, 'CAPTURE_EVIDENCE_REQUIRED')
    need(packet['missing_proofs'] == list(GAPS), 'ALL_MISSING_PROOFS')
    need(type(clock) is dict and packet['clock'] == clock and canonical(packet['clock']) == canonical(clock), 'EXACT_ORIGINAL_CLOCK')
    need(packet['input_ref'] == input_ref and canonical(packet['input_ref']) == canonical(input_ref), 'EXACT_INPUT_PIN')
    refs = expected_refs(inputs, collector_refs, native_r2)
    need(type(held_bytes) is dict and set(held_bytes) == set(refs), 'EXACT_HELD_BUFFERS')
    need(type(held_metadata) is dict and set(held_metadata) == {'signatures', 'ancestors'} and type(held_metadata['signatures']) is dict and set(held_metadata['signatures']) == set(refs) and type(held_metadata['ancestors']) is dict, 'EXACT_EXTERNAL_HELD_METADATA')
    records = packet['records']; need(type(records) is list and len(records) == len(refs), 'EXACT_RECORD_COUNT')
    need([r.get('path') for r in records if type(r) is dict] == sorted(refs), 'SORTED_EXACT_PATHS_NO_ALIAS')
    private = {r['path'] for r in inputs['private_account_inputs4'].values()}
    required_ancestors = {'/'}
    for record in records:
        need(type(record) is dict and set(record) == {'path','bytes','sha256','signature','private','unsafe_file_metadata','capture','startup_history'}, 'CLOSED_RECORD')
        ref = refs[record['path']]; buffer = held_bytes[record['path']]
        need(type(buffer) is bytes and len(buffer) == ref['bytes'] and sha(buffer) == ref['sha256'], 'INDEPENDENT_BUFFER_PIN')
        need(type(record['bytes']) is int and record['bytes'] == ref['bytes'] and record['sha256'] == ref['sha256'], 'EXACT_RECORD_PIN')
        sig = record['signature']; need(type(sig) is list and len(sig) == 9 and all(type(x) is int and x >= 0 for x in sig), 'STRICT_FILE_SIGNATURE')
        need(canonical(sig) == canonical(held_metadata['signatures'][record['path']]), 'EXTERNAL_HELD_SIGNATURE_JOIN')
        need(stat.S_ISREG(sig[4]) and not sig[4] & (stat.S_ISUID|stat.S_ISGID) and sig[5] == 1 and sig[6] == record['bytes'], 'REGULAR_SINGLE_LINK_HELD_SIGNATURE')
        need(type(record['private']) is bool and record['private'] == (record['path'] in private), 'PRIVATE_CLASSIFICATION')
        need(type(record['unsafe_file_metadata']) is bool and record['unsafe_file_metadata'] == bool(sig[2] not in (0, os.getuid()) or sig[4] & 0o022), 'UNSAFE_FILE_UNBOUND')
        need(record['capture'] == 'HELD_NOFOLLOW_BYTES_CURRENT_BINDING' and record['startup_history'] == 'UNKNOWN_NOT_AUTHENTICATED', 'HONEST_CAPTURE_SCOPE')
        path = record['path'].rsplit('/',1)[0]
        while path:
            required_ancestors.add(path); path = path.rsplit('/',1)[0]
    ancestors = packet['ancestors']; need(type(ancestors) is list and [r.get('path') for r in ancestors if type(r) is dict] == sorted(required_ancestors), 'COMPLETE_SORTED_ANCESTOR_CUSTODY')
    need(set(held_metadata['ancestors']) == required_ancestors, 'EXTERNAL_COMPLETE_ANCESTORS')
    unsafe = []
    for record in ancestors:
        need(type(record) is dict and set(record) == {'path','signature'}, 'CLOSED_ANCESTOR')
        sig = record['signature']; need(type(sig) is list and len(sig) == 5 and all(type(x) is int and x >= 0 for x in sig) and stat.S_ISDIR(sig[4]), 'STRICT_ANCESTOR_SIGNATURE')
        need(canonical(sig) == canonical(held_metadata['ancestors'][record['path']]), 'EXTERNAL_ANCESTOR_SIGNATURE_JOIN')
        if sig[2] not in (0,os.getuid()) or sig[4] & (0o022|stat.S_ISUID|stat.S_ISGID): unsafe.append(record['path'])
    need(packet['unsafe_ancestors'] == unsafe, 'UNSAFE_ANCESTORS_UNBOUND')
    recomputed = derived(held_bytes, inputs, collector_refs, native_r2)
    need(type(packet['data']) is dict and canonical(packet['data']) == canonical(recomputed), 'FULL_STATIC_REDERIVATION_JOIN')
    need(type(packet['captured_files_count']) is int and packet['captured_files_count'] == len(refs) and type(packet['captured_bytes']) is int and packet['captured_bytes'] == sum(v['bytes'] for v in refs.values()), 'EXACT_TYPED_TOTALS')
    return dict(status='SOURCE_READINESS_PACKET_VALIDATED', captured_files=len(refs), control_files=19, private_inputs=4,
                schema_files=recomputed['counts']['schema_files'], rpc_methods=recomputed['counts']['rpc_methods'],
                rpc_cases=recomputed['counts']['rpc_cases'], executed_tests=0, admission=False, independent_acceptance=False,
                runtime='UNBOUND_NOT_RUN', fullgate='NOT_RUN_NOT_ACCEPTED', candidate_guard='UNINSTALLED',
                packet_sha256=sha(raw), payload_sha256=digest)


def qualify(*args, **kwargs):
    raise Refusal('UNBOUND_INDEPENDENT_STARTUP_ELF_AGGREGATE_WHOLE9_NATIVE19_PROOFS; SOURCE_ONLY')
