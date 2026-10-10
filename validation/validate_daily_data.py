"""Data integrity only. Never imports/runs fixture checkers or native workers."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
from decimal import Decimal, ROUND_HALF_UP


CATEGORIES = {
    'telegram_chat', 'telegram_research', 'short_coding', 'long_coding',
    'engineering_repair', 'files', 'status', 'stop_active', 'stop_queued_retry',
    'recoverable_failure', 'unsatisfied', 'worker_failure',
}
PENDING_LIMITS = {
    'budget_seconds', 'deadline_unix', 'deadline_monotonic', 'boot_id',
    'worker_resources', 'retry_policy', 'polling_timeout_seconds',
    'silence_timeout_seconds',
}
PENDING_SOAK = {
    'duration_seconds', 'concurrent_chats', 'arrival_schedule', 'mix_weights',
    'queue_depth_bound', 'latency_thresholds', 'resource_baseline',
    'resource_sample_interval_seconds', 'accepted_recovery_retry_policy',
    'candidate_fingerprint', 'selected_local_profile',
}


# Fixed oracle metadata verified against the pinned checker limit/timeout code.
# These are not worker grants or soak defaults.
CHECKER_LIMITS = {'host': {'checker_source': 'product:fixtures/host-repair/check.py',
          'owner_tests_source': 'product:fixtures/host-repair/owner/test_calculator.py',
          'affinity_entries': 2,
          'address_space_bytes_per_process': 1073741824,
          'cpu_seconds_per_process': 3,
          'wall_seconds': 5,
          'forced_cleanup_reserve_seconds': 0.25,
          'file_bytes': 65536,
          'core_bytes': 0,
          'scope': 'UNCHANGED_FINITE_OWNER_CHECK_ONLY; not worker/job/soak limits; NOT_RUN'},
 'engineering': {'checker_source': 'product:fixtures/engineering-repair/check.py',
                 'owner_tests_source': 'product:fixtures/engineering-repair/owner/test_report.py',
                 'affinity_entries': 2,
                 'address_space_bytes_per_process': 1073741824,
                 'cpu_seconds_per_process': 3,
                 'inner_app_wall_seconds': 3,
                 'outer_sandbox_wall_seconds': 5,
                 'file_bytes': 65536,
                 'core_bytes': 0,
                 'scope': 'UNCHANGED_FINITE_OWNER_CHECK_ONLY; not aggregate worker memory or '
                          'job/soak grant; NOT_RUN'}}
CHECKER_PINS = {'product:fixtures/host-repair/check.py': '7f42526e8d4ae75f0eb86c05190702fa285898aae755ea1fdbe818f91434e1b9',
 'product:fixtures/engineering-repair/check.py': 'b9599e9c29cc396a480e31c10eea143248c683d80616a93bd04dc0cb1ba81215'}


# Exact independently reviewable historical long-task bytes; no worker authority.
LONG_SOURCE_PINS = {'product:fixtures/long-repository/worker-input.tar.gz': '21c635d246f3eb8b17dfcbfe56e2fcd29654b4c26ab579108ef5d6d4d02abc9f', 'product:fixtures/long-repository/brief.txt': 'f466dc3266e3eccc637f898eb495cbc741a23d29a5b2efc2ebd1ea0eabeddad5', 'product:fixtures/long-repository/owner/selection.json': '73e2612775b31590aa08e2388216bb7ab257773d05d364d81aebe7e8a0dbd69c', 'product:fixtures/long-repository/owner/known_solution.py': '8bdbf15f9950dadb69df9e910463587d72a74e1ee35934fd43b9cf5f6c1d27db', 'product:fixtures/long-repository/owner/test_daily_finalizer.py': 'c842884bb1638e76fba4a914d3785593fcb16527d45d967c3fb6422dfd16b729', 'product:fixtures/long-repository/owner/current_reference_checks.py': '77f7a98192c08c582c8b25c02d2ebdbc6c7cd68666f557b0175b080b54a6f86a'}
LONG_PREFIX = 'product:fixtures/long-repository/'


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def relative(value):
    need(isinstance(value, str) and value, 'missing path')
    path = Path(value)
    need(not path.is_absolute() and all(x not in ('', '.', '..') for x in value.split('/')),
         'escaping/noncanonical path')
    return path


def open_directory(path):
    """Capture every directory identity for a second named-path check."""
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    ancestors = []
    try:
        metadata = os.fstat(directory)
        ancestors.append((metadata.st_dev, metadata.st_ino))
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
            metadata = os.fstat(directory)
            ancestors.append((metadata.st_dev, metadata.st_ino))
        return directory, ancestors
    except BaseException:
        os.close(directory)
        raise


def read_file(path):
    """One bounded regular FD, no symlink ancestors, stable current path."""
    path = Path(os.path.abspath(path))
    directory, ancestors = open_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and 0 < before.st_size <= 1024 * 1024, 'nonregular/empty/oversize source')
            chunks, remaining = [], 1024 * 1024 + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b''.join(chunks)
            after = os.fstat(fd)
            def identity(x):
                return (x.st_dev, x.st_ino, x.st_mode, x.st_uid, x.st_gid, x.st_nlink,
                        x.st_size, x.st_mtime_ns, x.st_ctime_ns)
            current, current_ancestors = open_directory(path.parent)
            try:
                named = os.stat(path.name, dir_fd=current, follow_symlinks=False)
                need(ancestors == current_ancestors
                     and identity(before) == identity(after) == identity(named)
                     and len(data) == before.st_size, 'source or containing path changed during read')
            finally:
                os.close(current)
            return data
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load(data):
    result = json.loads(data, object_pairs_hook=pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    json.dumps(result, allow_nan=False)  # also reject numeric overflow, e.g. 1e999
    return result


def same_json(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False)


def validate(document, sources, corpus_root, roots):
    need(document['schema'] == 'friday.daily-use.tasks.v1'
         and type(document['version']) is int and document['version'] == 1
         and document['status'] == 'PREPARED_SOURCE_DATA_ONLY_NOT_RUN'
         and document['source_pins_ref'] == 'source-pins.json', 'corpus state/schema')
    need(sources['schema'] == 'friday.daily-use.source-pins.v1'
         and sources['product_commit'] == document['product_commit']
         and re.fullmatch('[0-9a-f]{40}', document['product_commit']), 'commit/source association')
    source_bytes, source_rows = {}, {}
    for row in sources['sources']:
        key = row['id']
        need(key not in source_bytes, 'duplicate source id')
        need(row['root'] in roots, 'unknown source root')
        path = relative(row['path'])
        need(key == row['root'] + ':' + str(path), 'source identity mismatch')
        need(type(row['bytes']) is int and row['bytes'] > 0
             and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'invalid source pin')
        raw = read_file(roots[row['root']] / path)
        need(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
             'source bytes/hash drift: ' + key)
        source_bytes[key], source_rows[key] = raw, row
    need(same_json(document['fixture_checker_limits'], CHECKER_LIMITS),
         'changed pinned checker limits or scope')
    need(all(hashlib.sha256(source_bytes[key]).hexdigest() == pin
             for key, pin in CHECKER_PINS.items()), 'checker metadata source changed')
    limits = document['original_limits']
    need(limits['state'] == 'PENDING_ORIGINAL_ADMISSION'
         and all(limits[x] is None for x in PENDING_LIMITS), 'invented original limits')
    need(document['acceptance']['FRW-030'] == 'SOURCE_DATA_PREPARED_REVIEW_REQUIRED; LIVE_NOT_ACCEPTED'
         and document['acceptance']['AC034'] == document['acceptance']['AC040'] == 'NOT_RUN'
         and document['acceptance']['exclusions'] == []
         and set(document['acceptance']['prerequisites']) == {'FRW-022', 'FRW-023', 'FRW-029'}
         and all(x == 'UNACCEPTED' for x in document['acceptance']['prerequisites'].values()),
         'invented acceptance/exclusion')
    need(document['acceptance']['seven_installed_journeys'] ==
         document['acceptance']['four_web_journeys'] == 'UNACCEPTED', 'invented product acceptance')
    ids, categories, briefs = set(), set(), set()
    all_owner_sources = {key for task in document['tasks'] for key in task['owner_only_sources']}
    for task in document['tasks']:
        key = task['id']
        need(key not in ids, 'duplicate task id')
        ids.add(key)
        need(task['category'] in CATEGORIES, 'unknown task category')
        categories.add(task['category'])
        need(task['state'] == 'NOT_RUN' and task['evidence']['observed_status'] == 'NOT_RUN'
             and task['evidence']['actual_artifacts'] == []
             and all(v is None for k, v in task['evidence'].items()
                     if k not in ('observed_status', 'actual_artifacts')), 'invented task observation')
        need(task['original_limits_ref'] == limits['id'], 'missing original limit binding')
        need(all(x in task['dependencies'] for x in ('FRW-022', 'FRW-023', 'FRW-029')),
             'missing live prerequisite')
        need(task['expected_outcomes'] and all(
            isinstance(x.get('predicate'), str) and x['predicate'].strip()
            and x.get('kind') for x in task['expected_outcomes']), 'empty expected outcome')
        need(len(set(task['expected_artifacts'])) == len(task['expected_artifacts']),
             'duplicate artifact name')
        uploads, owner = task['user_input_sources'], task['owner_only_sources']
        source_briefs = [task['brief_source']] if 'brief_source' in task else []
        if task['category'] == 'engineering_repair':
            need(source_briefs == ['product:fixtures/engineering-repair/brief.txt'],
                 'exact original engineering brief required')
        else:
            need(not source_briefs, 'unexpected worker-visible source brief')
        visible_sources = uploads + source_briefs
        need(not set(visible_sources).intersection(all_owner_sources), 'owner input exposure')
        for key in visible_sources + owner:
            need(key in source_bytes, 'missing source reference')
        need(all('/owner/' not in x and '/calibration/' not in x
                 and not x.endswith(('/check.py', '/manifest.json', '/mapping.json'))
                 for x in visible_sources), 'owner-only bytes in worker input or brief')
        brief = relative(task['brief_ref'])
        need(len(brief.parts) == 2 and brief.parts[0] == 'briefs' and brief.suffix == '.txt',
             'dedicated text brief required')
        need(str(brief) not in briefs, 'shared/duplicate brief')
        briefs.add(str(brief))
        raw = read_file(corpus_root / brief)
        pin = task['brief_pin']
        need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
             and raw.decode('utf-8').strip(), 'brief missing/changed')
        if task['category'] == 'long_coding':
            if task['data_readiness'] == 'PENDING_REAL_TARGET':
                need(task['target']['repository'] is None
                     and task['target']['original_user_goal'] is None
                     and any(x.startswith('MISSING_REAL_LONG_TASK:') for x in task['dependencies'])
                     and uploads == [] and document['acceptance']['long_coding_coverage'] ==
                     'PENDING_REAL_TARGET; not satisfied by short arithmetic or engineering calibration',
                     'fake long coding coverage')
                long_readiness = 'PENDING_REAL_TARGET'
            else:
                need(task['data_readiness'] == 'REAL_REPOSITORY_SOURCE_SELECTED_NOT_RUN'
                     and document['acceptance']['long_coding_coverage'] ==
                     'REAL_REPOSITORY_SOURCE_SELECTED; execution, continuation and duration NOT_RUN',
                     'source selection is not runtime coverage')
                need(all(key in source_bytes and hashlib.sha256(source_bytes[key]).hexdigest() == pin
                         for key, pin in LONG_SOURCE_PINS.items()), 'long-task exact source/oracle pins')
                selection = load(source_bytes[LONG_PREFIX + 'owner/selection.json'])
                target = task['target']
                need(same_json(target['repository'], {
                    'kind': 'PINNED_HISTORICAL_GIT_SEED',
                    'archive_source': LONG_PREFIX + 'worker-input.tar.gz',
                    'seed_commit': selection['seed_commit'],
                    'source_commit': selection['source_commit'],
                    'worker_repository': 'worker/repository'}), 'long-task original repository binding')
                need(same_json(target['input_pin_set'], list(LONG_SOURCE_PINS))
                     and target['original_user_goal'] == LONG_PREFIX + 'brief.txt'
                     and target['owner_selection'] == LONG_PREFIX + 'owner/selection.json',
                     'long-task goal/input binding')
                need(uploads == [LONG_PREFIX + 'worker-input.tar.gz', LONG_PREFIX + 'brief.txt']
                     and {LONG_PREFIX + name for name in selection['owner_only']} <= set(owner)
                     and raw == source_bytes[LONG_PREFIX + 'brief.txt'], 'long-task input/owner separation')
                need(selection['worker_grant'] == 'PENDING_ORIGINAL_ADMISSION'
                     and selection['runtime_limit_seconds'] is None
                     and selection['runtime_deadline'] is None
                     and selection['runtime_task_id'] is None
                     and selection['runtime_native_association'] is None
                     and selection['runtime_executed'] is False
                     and selection['long_duration_proven'] is False
                     and selection['continuation']['observed'] is False
                     and selection['continuation']['reset_original_deadline'] is False,
                     'long-task invented runtime/grant/continuation')
                need(not any(x.startswith('MISSING_REAL_LONG_TASK:') for x in task['dependencies']),
                     'obsolete selected-task prerequisite')
                long_readiness = 'REAL_REPOSITORY_SOURCE_SELECTED_NOT_RUN'
    need(categories == CATEGORIES and len(ids) == len(CATEGORIES), 'missing/extra task category')
    actual_briefs = {str(p.relative_to(corpus_root)) for p in (corpus_root / 'briefs').iterdir()}
    need(actual_briefs == briefs, 'orphan/missing brief file')
    soak = document['soak']
    need(soak['state'] == 'PLANNED_PENDING_ADMISSION_NOT_RUN'
         and all(soak[x] is None for x in PENDING_SOAK), 'silently selected soak limits')
    mix = soak['planned_mix']
    need(len(mix) == len(ids) and {x['task_id'] for x in mix} == ids
         and all(x['occurrences'] is None for x in mix), 'missing/duplicate/selected mix')
    need(type(soak['heavy_worker_capacity']['canonical_active_slots']) is int
         and soak['heavy_worker_capacity']['canonical_active_slots'] == 1
         and all(soak['heavy_worker_capacity'][x] in source_bytes
                 for x in ('source', 'admission_source')), 'changed canonical worker topology')
    events = soak['required_interruptions']
    need(len(events) == 2 and {x['id'] for x in events} == {'gateway-restart', 'worker-failure'}
         and all(x['minimum_count'] == 1 and x['state'] == 'NOT_RUN'
                 and x['timing'] is None and x['method'] is None for x in events),
         'missing real restart/failure requirement')
    need(soak['observations']['acceptance'] == 'NOT_RUN'
         and all(v is None for k, v in soak['observations'].items() if k != 'acceptance'),
         'invented soak measurements')
    # Join the ORIGINAL engineering manifest and calibration as data, no app import.
    prefix = 'product:fixtures/engineering-repair/'
    manifest = load(source_bytes[prefix + 'manifest.json'])
    for name, pin in manifest['pins'].items():
        row = source_rows[prefix + name]
        need(row['bytes'] == pin['bytes'] and row['sha256'] == pin['sha256'],
             'engineering owner manifest mismatch')
    eng = next(x for x in document['tasks'] if x['category'] == 'engineering_repair')
    need(set(eng['user_input_sources']) == {prefix + x for x in manifest['worker_input_files']}
         and {prefix + x for x in manifest['owner_only_files']} <= set(eng['owner_only_sources'])
         and set(eng['expected_artifacts']) == {'settings.json', 'report.json', 'repair.diff', 'diagnosis.txt'},
         'engineering mapping/boundary incomplete')
    mapping = load(source_bytes[prefix + 'mapping.json'])
    for row in mapping['input_files']:
        pin = source_rows[prefix + 'input/' + row['logical_name']]
        need(row['bytes'] == pin['bytes'] and row['sha256'] == pin['sha256'], 'mapping input mismatch')
    need({x['logical_name'] for x in mapping['output_files']} == set(eng['expected_artifacts']),
         'mapping output mismatch')
    rows = list(csv.DictReader(io.StringIO(source_bytes[prefix+'input/readings.csv'].decode('cp1251')),
                               delimiter=';'))
    total_kwh = sum((Decimal(x['kwh']) for x in rows), Decimal(0))
    total_rub = sum(((Decimal(x['kwh']) * Decimal(x['rate'])).quantize(
        Decimal('.01'), ROUND_HALF_UP) for x in rows), Decimal(0))
    golden = load(source_bytes[prefix + 'calibration/report.json'])
    need(len(rows) == golden['records'] == 4 and total_kwh == Decimal(golden['total_kwh'])
         and total_rub == Decimal(golden['total_amount']), 'CSV/calibration oracle inconsistency')
    return {'state': 'PASS_DATA_INTEGRITY_ONLY', 'tasks': len(ids),
            'categories': len(categories), 'source_pins_verified': len(source_bytes),
            'brief_pins_verified': len(briefs), 'original_engineering_manifest_pins': len(manifest['pins']),
            'long_coding': long_readiness, 'soak_parameters': 'PENDING_ADMISSION',
            'fixture_checkers_executed': False, 'runtime_executed': False,
            'attests_runtime_truth': False, 'review_required': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-root', type=Path, required=True)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--corpus-root', type=Path,
                        help='Explicit private proposal corpus; defaults to product fixtures/daily-use')
    args = parser.parse_args()
    corpus = args.corpus_root if args.corpus_root is not None else args.product_root / 'fixtures/daily-use'
    result = validate(load(read_file(corpus / 'tasks.json')),
                      load(read_file(corpus / 'source-pins.json')), corpus,
                      {'product': args.product_root, 'archive': args.archive_root})
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
