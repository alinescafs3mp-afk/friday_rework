# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Fresh Root source acceptance for the exact reviewed S447 Source92 successor.

Import and unbound main are inert. Installation, readiness publication, service
control and user effects belong to Root's separate finite operations.
"""
from pathlib import Path
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
import time

HOME = Path('<INSTALL_HOME>')
PM = HOME / 'installs/PRIVATE_REF_e7cfb7d5cf3d9888/environments/PRIVATE_REF_f236aa5525a8c3d7/venv/bin/python'
PRODUCER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/producer.py', 'sha256': 'PRIVATE_REF_0aa93e04fba6c1ea'}
ROOT_RUN = None
FIELDS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(ok, code):
    if not ok:
        raise ValueError(code)


def unique(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 's447_duplicate_json_key')
        out[key] = value
    return out


def raw(reference):
    need(type(reference) is dict and set(reference) == {'path', 'sha256'}
         and type(reference['path']) is str
         and type(reference['sha256']) is str
         and re.fullmatch('[a-f0-9]{64}', reference['sha256']), 's447_exact_ref')
    path = Path(reference['path'])
    need(path.is_absolute() and path.resolve() == path
         and str(path) == reference['path'], 's447_canonical_ref')
    parents = {}
    for parent in path.parents:
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid())
             and not info.st_mode & 0o022, 's447_protected_parent')
        parents[parent] = tuple(getattr(info, k) for k in FIELDS[:5])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid()
             and first.st_gid == os.getgid() and first.st_nlink == 1
             and stat.S_IMODE(first.st_mode) in (0o400, 0o600), 's447_private_ref')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(32 * 1024**2 + 1)
        last, named = os.fstat(fd), path.lstat()
        need(len(data) <= 32 * 1024**2
             and all(getattr(first, k) == getattr(last, k) == getattr(named, k)
                     for k in FIELDS)
             and hashlib.sha256(data).hexdigest() == reference['sha256'],
             's447_ref_changed')
    finally:
        os.close(fd)
    need(all(tuple(getattr(p.lstat(), k) for k in FIELDS[:5]) == identity
             for p, identity in parents.items()), 's447_parent_changed')
    return data


def document(reference):
    return json.loads(raw(reference), object_pairs_hook=unique,
                      parse_constant=lambda _: need(False, 's447_nonfinite_json'))


def load_producer():
    need(PRODUCER is not None, 's447_producer_unbound')
    namespace = {'__file__': PRODUCER['path'], '__name__': '_s447_checked_source_producer'}
    exec(compile(raw(PRODUCER), PRODUCER['path'], 'exec'), namespace)
    need(callable(namespace.get('verify_installed')), 's447_verifier_api_missing')
    return namespace


def check_clock(reference, *, now=None, boot=None):
    clock = document(reference)
    need(type(clock) is dict and set(clock) == {'schema', 'operation_id', 'no_reset',
         'boot_id', 'origin_monotonic', 'deadline_monotonic', 'budget_seconds',
         'reserve_seconds'} and clock['schema'] == 'frw.Root.S447.source-check-clock.v1'
         and clock['operation_id'] == 'S447_SOURCE_ONLY_FRESH_ACCEPTANCE'
         and clock['no_reset'] is True, 's447_exact_source_clock')
    now = time.monotonic() if now is None else now
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip() if boot is None else boot
    need(clock['boot_id'] == boot
         and all(type(clock[k]) in (int, float) and math.isfinite(clock[k]) for k in (
             'origin_monotonic', 'deadline_monotonic', 'budget_seconds', 'reserve_seconds'))
         and type(clock['budget_seconds']) is int and 30 <= clock['budget_seconds'] <= 600
         and 0 < clock['reserve_seconds'] < clock['budget_seconds']
         and abs(clock['deadline_monotonic'] - clock['origin_monotonic']
                 - clock['budget_seconds']) < 1e-6
         and 0 <= clock['origin_monotonic'] <= now
         < clock['deadline_monotonic'] - clock['reserve_seconds'], 's447_source_clock_exhausted')
    return clock


def fresh_imports(producer, facts):
    need(not any(n == '_friday_dashboard_projection'
                 or n.startswith('_friday_dashboard_projection.')
                 or n == 'friday_rework' or n.startswith('friday_rework.')
                 or n == 'plugins.friday_rework' or n.startswith('plugins.friday_rework.')
                 for n in sys.modules), 's447_fresh_single_projection_required')
    package = document(facts['package'])
    current = document(facts['current_input'])
    sys.path.insert(0, str(HOME / 'hermes-agent'))
    path = HOME / 'plugins/friday_rework/dashboard/api.py'
    data = raw({'path': str(path),
                'sha256': current['project_files']['plugins/friday_rework/dashboard/api.py']})
    name = 'hermes_dashboard_plugin_friday_rework'
    need(name not in sys.modules, 's447_fresh_dashboard_required')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(data, str(path), 'exec'), module.__dict__)
    names = []
    for relative in sorted(package['plugin_after']):
        suffix = relative.removeprefix('plugins/friday_rework/').removesuffix('.py').replace('/', '.')
        name = '_friday_dashboard_projection.' + suffix
        imported = importlib.import_module(name)
        need(Path(imported.__file__).resolve() == HOME / relative,
             's447_actual_installed_module_required')
        raw({'path': str(HOME / relative), 'sha256': current['project_files'][relative]})
        names.append(name)
    return names


def emit(request):
    need(type(request) is dict and set(request) == {'schema', 'package', 'request',
         'committed', 'source_check_clock', 'output_directory'}
         and request['schema'] == 'frw.Root.S447.source-acceptance-entry.v1',
         's447_exact_source_check_request')
    need(sys.flags.isolated and sys.dont_write_bytecode and __debug__
         and sys.executable == str(PM) and os.environ.get('HERMES_HOME') == str(HOME),
         's447_real_native_lexical_process_required')
    output = Path(request['output_directory'])
    need(output.is_absolute() and output.resolve() == output
         and output.parent == Path('<PRIVATE_CACHE>')
         and output.name.startswith('PRIVATE_REF_6161093b7304eba4'), 's447_root_output_family')
    for path in (output, *output.parents):
        info = path.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid())
             and not info.st_mode & 0o022, 's447_protected_output')
    info = output.lstat()
    need(info.st_uid == os.getuid() and info.st_gid == os.getgid()
         and stat.S_IMODE(info.st_mode) == 0o700, 's447_owned_output')
    producer = load_producer()
    check_clock(request['source_check_clock'])
    args = (request['package'], request['request'], request['committed'])
    before = producer['verify_installed'](*args)
    imports = fresh_imports(producer, before)
    need(producer['verify_installed'](*args) == before, 's447_final_source_cas_changed')
    check_clock(request['source_check_clock'])
    value = {'schema': 'frw.Root.dsh_source.installed-source-accepted.v1',
             'accepted': True, 'accepted_source_only': True, 'source_only': True,
             'runtime_or_user_semantics_accepted': False,
             'current_input': before['current_input'],
             'input_sha256': before['current_input']['sha256'],
             'committed': before['commit'], 'marker': before['current_marker'],
             'plan': before['plan'], 'source_receipt': before['source_receipt'],
             'changed_native_files': [], 'changed_plugin_files': before['changed_plugin_files'],
             'fresh_process': True, 'fresh_process_pid': os.getpid(),
             'fresh_process_imports': imports, 'source_check_clock': request['source_check_clock'],
             'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'observed_monotonic': time.monotonic()}
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    target = output / 'ROOT-INSTALLED-SOURCE-ACCEPTED.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(target), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    if ROOT_RUN is None:
        raise SystemExit('UNBOUND_NO_READ_OR_WRITE')
    need(type(ROOT_RUN) is dict and set(ROOT_RUN) == {'request'}, 's447_explicit_root_request')
    return emit(document(ROOT_RUN['request']))


if __name__ == '__main__':
    print(json.dumps(main(), sort_keys=True))
