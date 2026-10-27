#!/usr/bin/env python3
# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Exact DSH associations/host contention fix; existing source overlay algorithm.

Reuses the executed source-only sibling of S426 and its identical protected
read/write, admission, CAS, publication, rollback and no-retry algorithm.
No native file or source graph addition is allowed. Root alone binds reviewed
bytes and a distinct future maintenance clock; this module creates no clock.

No service/model/dependency operation is implemented here. Root supplies a real
stopped-consumer guard, pinned stop evidence and distinct finite apply/rollback
deadlines. Importing this module has no effects.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

BASE = Path('<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/source-runtime')
OUT = Path(__file__).resolve().parent
HOME = Path('<INSTALL_HOME>')
INPUT_SHA = 'PRIVATE_REF_94a721411b0647b5'
INPUT_NAME = 'INPUT-A0-CURRENTBOOT.NEXT.json'
ACCEPTANCE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_48678ca08730fc64'}
META = {'FRIDAY-INSTALL.json': 'PRIVATE_REF_5658fcef6ae552d6', 'hermes-agent.source.json': 'PRIVATE_REF_0b2edba82b83b89f', 'hermes-agent/install-stamp.json': 'PRIVATE_REF_29800c802189ddf1'}
# No native overlay or donor change is permitted by this adapter.
PLUGIN_PATHS = frozenset({'plugins/friday_rework/user_worker_join.py', 'plugins/friday_rework/host_runtime.py', 'plugins/friday_rework/worker_provision.py', 'plugins/friday_rework/adapters/a0_native.py'})
PREDECESSOR = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/source-runtime/bound/REQUEST.json', 'sha256': 'PRIVATE_REF_6d1b836a2f69f072'}
MANIFEST = 'patches/hermes/ordinary-s428-compression-envelope-manifest.json'
SOURCE_GIDS = {'plugins/friday_rework/user_worker_join.py': 12345, 'FRIDAY-INSTALL.json': 12345, 'plugins/friday_rework/adapters/a0_native.py': 12345, 'plugins/friday_rework/host_runtime.py': 12345, 'plugins/friday_rework/worker_provision.py': 12345, 'hermes-agent/install-stamp.json': 12345, 'hermes-agent.source.json': 12345}



PREVIOUS = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_56fbcca7bb9f75bc/CURRENT-INPUT.SAME-BYTES.json', 'sha256': 'PRIVATE_REF_94a721411b0647b5'}
S442_NATIVE_REQUEST = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_56fbcca7bb9f75bc/REQUEST.json', 'sha256': 'PRIVATE_REF_edff57001635ee77'}
S442_NATIVE_RECEIPT = {'path': '<INSTALL_HOME>/preparation/worker-declarations-successor-PRIVATE_REF_0f471d086ef225e7/service-source-receipt.json', 'sha256': 'PRIVATE_REF_3a9c9afff1711a10'}
S442_VERIFIER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_174e7fdd15606bc8/native-graph/verify_native.py', 'sha256': 'PRIVATE_REF_5ac5356545db0451'}
S442_ORIGINAL_MARKER = {'path': '<INSTALL_HOME>/FRIDAY-INSTALL.json', 'sha256': 'PRIVATE_REF_deb2ebcd85229b41'}

PROJECT_PATHS = frozenset({'scripts/friday-rework-docker.service', 'plugins/friday_rework/user_worker_join.py', 'plugins/friday_rework/adapters/a0_native.py', 'plugins/friday_rework/host_runtime.py', 'scripts/a0_runtime.py', 'scripts/rootless_docker_launch.py', 'scripts/worker_install.py', 'scripts/a0_prepare.py', 'plugins/friday_rework/worker_provision.py', 'scripts/friday_worker_declarations.py'})

def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def read(path):
    path = Path(path)
    require(path.is_absolute() and path.parent.resolve() == path.parent, 'canonical_parent_required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid() and first.st_nlink == 1
                and not first.st_mode & 0o002,
                'owned_regular_single_link_required')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read(64 * 1024**2 + 1)
        last, named = os.fstat(fd), path.lstat()
        keys = ('st_dev','st_ino','st_uid','st_nlink','st_mode','st_size','st_mtime_ns','st_ctime_ns')
        require(len(data) <= 64*1024**2 and all(getattr(first,k) == getattr(last,k) == getattr(named,k) for k in keys),
                'input_identity_changed')
        return data, first
    finally:
        os.close(fd)


def pinned(pin):
    data, info = read(pin['path'])
    require(sha(data) == pin['sha256'], 'input_pin_changed')
    return data


def ref(path):
    data, _ = read(path)
    return {'path':str(path), 'sha256':sha(data)}


def state_record(state):
    if state is None:
        return {'absent': True}
    return {'sha256':sha(state['data']), 'bytes':len(state['data']),
            'mode':state['mode'], 'identity':list(state['identity'])}


def write(path, data, mode=0o600):
    path = Path(path)
    missing = []; parent = path.parent
    while not parent.exists():
        missing.append(parent); parent = parent.parent
    require(parent.resolve() == parent, 'output_parent_link')
    for item in reversed(missing):
        item.mkdir(mode=0o700)
    require(path.parent.resolve() == path.parent, 'output_parent_link')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), mode)
        f.write(data); f.flush(); os.fsync(f.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def imports(root):
    """Only exact small project generation, never native Hermes imports."""
    require(not any(n == 'scripts' or n.startswith('scripts.') for n in sys.modules),
            'fresh_interpreter_required')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    from scripts import friday_install as f, friday_ordinary_install as o, hermes_prepare as h
    require(f.ROOT == root, 'wrong_installer_root')
    return f, o, h


def baseline_links(marker, receipt, stamp, previous_pin, previous):
    previous_root = BASE/'source'
    require(marker['input_sha256'] == previous_pin['sha256']
            and marker['source_receipt_sha256'] == marker['ordinary_gateway']['source_receipt_sha256']
            and marker['ordinary_gateway']['operator_entry'] == {
                'input':previous_pin,'script':{
                    'path':str(previous_root/'scripts/friday_native.py'),
                    'sha256':previous['project_files']['scripts/friday_native.py']}},
            'actual_operator_input_join_changed')
    pinned(marker['ordinary_gateway']['operator_entry']['input'])
    pinned(marker['ordinary_gateway']['operator_entry']['script'])
    require(stamp['fridaySource'] == {'baseTree':receipt['base_tree'],'layers':receipt['layers']},
            'actual_stamp_join_changed')


def check_source_gids():
    # Existing installer state omits GID; refuse drift before any target write
    # and in every cleanup preflight/atomic check without changing native code.
    for name, expected in SOURCE_GIDS.items():
        require((HOME/name).lstat().st_gid == expected == os.getegid(),
                'source_update_group_custody_changed')


def bind_root_operation(*, accepted_review, original_clock, deadline_monotonic):
    """Root's real once admission. Writes no installed file; no fake clocks.

    Must be called only for this new maintenance. The caller supplies its real
    already-created original clock and accepted review. Existing bound output
    refuses instead of inventing another operation/generation.
    """
    package = json.loads(read(OUT/'PACKAGE.json')[0])
    review = json.loads(pinned(accepted_review))
    clock = json.loads(pinned(original_clock))
    tuples = ('target_frozen','current_input','manifest','target_source_receipt')
    require(review.get('schema')=='friday.ordinary-source92-feature-source-review.v1'
            and review.get('accepted') is True and review.get('open_HIGH_MEDIUM')==0
            and all(review.get(k)==package[k] for k in tuples), 'accepted_current_package_review_required')
    now = time.monotonic()
    require(clock.get('no_reset') is True and clock.get('boot_id')==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and 0 <= clock['origin_monotonic'] <= now < deadline_monotonic
            <= clock['deadline_monotonic']-clock['reserve_seconds']
            and deadline_monotonic <= clock['origin_monotonic']+180
            and 0 < clock['reserve_seconds'] < clock['budget_seconds']
            and abs(clock['deadline_monotonic']-clock['origin_monotonic']-clock['budget_seconds'])<1e-6,
            'real_current_original_clock_required')
    bound = OUT/'bound'; bound.mkdir(mode=0o700)
    validate_package(package)
    marker = json.loads(pinned({'path':str(HOME/'FRIDAY-INSTALL.json'),'sha256':META['FRIDAY-INSTALL.json']}))
    core = {'schema':'friday.ordinary-telegram-source92-feature-update.v1','home':str(HOME),'seconds':180,
            'previous_input':package['previous_input'],'current_input':package['current_input'],
            'marker':{'path':str(HOME/'FRIDAY-INSTALL.json'),'sha256':META['FRIDAY-INSTALL.json']},
            'source_receipt':{'path':str(HOME/'hermes-agent.source.json'),'sha256':META['hermes-agent.source.json']},
            'stamp':{'path':str(HOME/'hermes-agent/install-stamp.json'),'sha256':META['hermes-agent/install-stamp.json']},
            'predecessor_update':marker['ordinary_source_update_request'],
            'target_frozen':package['target_frozen'],'source_review':accepted_review}
    operation = {'schema':'friday.ordinary-source92-feature-operation.v1','state':'ADMITTED_ONCE_NO_RETRY',
                 'home':str(HOME),'previous_input':core['previous_input'],'source_receipt':core['source_receipt'],
                 'source_review':accepted_review,'request_core_sha256':sha(encode(core)),
                 'original_clock':original_clock,'deadline_monotonic':deadline_monotonic,
                 **{k:package[k] for k in tuples}}
    write(bound/'ROOT-OPERATION.json',encode(operation))
    request = dict(core,root_operation=ref(bound/'ROOT-OPERATION.json'))
    write(bound/'REQUEST.json',encode(request))
    receipt_raw = saved_receipt_bytes(package)
    stamp_raw = pinned(package['retained_stamp'])
    receipt = json.loads(receipt_raw)
    stamp = json.loads(stamp_raw)
    require(core['source_receipt']['sha256'] == sha(receipt_raw)
            and core['stamp']['sha256'] == sha(stamp_raw), 'retained_metadata_pin_changed')
    marker['input_sha256']=core['current_input']['sha256']
    marker['source_receipt_sha256']=marker['ordinary_gateway']['source_receipt_sha256']=package['target_source_receipt']['sha256']
    current=json.loads(pinned(core['current_input']))
    marker['plugin_files']={n:v for n,v in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
    marker['ordinary_gateway']['operator_entry']={'input':core['current_input'],
       'script':{'path':str(Path(package['source'])/'scripts/friday_native.py'),
                 'sha256':current['project_files']['scripts/friday_native.py']}}
    marker['ordinary_source_update_request']=ref(bound/'REQUEST.json')
    after=dict(package['plugin_after'])
    for name,value in [('FRIDAY-INSTALL.json',marker),('hermes-agent.source.json',receipt),('hermes-agent/install-stamp.json',stamp)]:
        data = receipt_raw if name == 'hermes-agent.source.json' else stamp_raw if name == 'hermes-agent/install-stamp.json' else encode(value)
        write(bound/'after'/name, data); after[name]=ref(bound/'after'/name)
    plan={'schema':'friday.dsh-retained-existing-plugin-overlay-plan.v1','request':ref(bound/'REQUEST.json'),
          'helper':ref(Path(__file__).resolve()),'source':package['source'],'before':package['baseline'],
          'after':after,'order':[*sorted(package['plugin_after']),'hermes-agent.source.json','hermes-agent/install-stamp.json','FRIDAY-INSTALL.json']}
    write(bound/'PLAN.json',encode(plan))
    return ref(bound/'PLAN.json')


def apply(plan_path, plan_sha256, *, guard, stopped_evidence, boot_id,
          deadline_mono, rollback_deadline_mono):
    """Root only, in a fresh interpreter, under its existing maintenance owner.

    guard must freshly validate only the exact stopped gateway/Dashboard trees
    and retained Kimi owner; it must raise on uncertainty and return True on
    success. It must not assert old source/marker hashes after intended writes.
    The evidence pin is audit input, not a substitute for that guard. No CLI
    exposes this function. Any existing journal refuses retry.
    """
    require(callable(guard), 'external_stopped_consumer_guard_required')
    require(type(deadline_mono) in (float,int) and type(rollback_deadline_mono) in (float,int)
            and time.monotonic() < deadline_mono < rollback_deadline_mono, 'finite_future_deadlines_required')
    def check(cleanup=False):
        check_source_gids()
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot_id, 'boot_changed')
        require(time.monotonic() < (rollback_deadline_mono if cleanup else deadline_mono), 'maintenance_deadline')
        require(guard() is True, 'stopped_guard_not_confirmed')
        require(sha(pinned(stopped_evidence)) == stopped_evidence['sha256'], 'stopped_evidence_changed')
    check()
    plan_pin = {'path':str(Path(plan_path)), 'sha256':plan_sha256}
    plan = json.loads(pinned(plan_pin)); request = json.loads(pinned(plan['request']))
    require(plan['schema'] == 'friday.dsh-retained-existing-plugin-overlay-plan.v1'
            and request['schema'] == 'friday.ordinary-telegram-source92-feature-update.v1'
            and request['home'] == str(HOME), 'wrong_dsh_retained_plan')
    operation=json.loads(pinned(request['root_operation']))
    clock=json.loads(pinned(operation['original_clock']))
    require(operation['state']=='ADMITTED_ONCE_NO_RETRY'
            and deadline_mono==operation['deadline_monotonic']
            and rollback_deadline_mono<=clock['deadline_monotonic']
            and clock['boot_id']==boot_id
            and operation['request_core_sha256']==sha(encode({k:v for k,v in request.items() if k!='root_operation'})),
            'original_bound_operation_required')
    require(pinned(plan['helper']) == read(Path(__file__).resolve())[0], 'wrong_helper')
    source = Path(plan['source']); current = json.loads(pinned(request['current_input']))
    previous = json.loads(pinned(request['previous_input']))
    require({k:v for k,v in previous.items() if k!='project_files'} ==
            {k:v for k,v in current.items() if k!='project_files'}, 'operational_settings_changed')
    package = json.loads(read(OUT/'PACKAGE.json')[0])
    validate_package(package)
    require(request['previous_input'] == package['previous_input']
            and request['current_input'] == package['current_input']
            and request['target_frozen'] == package['target_frozen']
            and plan['source'] == package['source']
            and plan['before'] == package['baseline'], 'package_request_join_changed')
    validate_plugin_delta(previous, current, package['project_after'])
    for name,pin in current['project_files'].items():
        require(sha(read(source/name)[0]) == pin, 'project_source_changed')
    f, o, h = imports(source)
    o.checked_plugin_inventory(HOME, {n:v for n,v in previous['project_files'].items()
                                      if n.startswith('plugins/friday_rework/')})
    after = {n:pinned(pin) for n,pin in plan['after'].items()}
    receipt = json.loads(after['hermes-agent.source.json'])
    lock = json.loads(read(source/'sources.lock.json')[0])
    donor = next(r for r in lock['repositories'] if r['id']=='hermes')
    names = plan['order']
    require(names == [*sorted(package['plugin_after']), 'hermes-agent.source.json',
                      'hermes-agent/install-stamp.json', 'FRIDAY-INSTALL.json']
            and len(set(names)) == len(names) and set(names) == set(plan['before']) == set(after),
            'exact_write_set_required')
    require(after['hermes-agent.source.json'] == saved_receipt_bytes(package)
            and after['hermes-agent/install-stamp.json'] == pinned(package['retained_stamp']),
            'native_metadata_must_remain_byte_identical')
    for name, pin in package['plugin_after'].items():
        require(after[name] == pinned(pin), 'plugin_afterimage_changed')
    f.directory(HOME/'preparation')
    tx = HOME/'preparation'/('ordinary-source-update-'+request['previous_input']['sha256'])
    require(not os.path.lexists(tx), 'existing_journal_requires_reconciliation_no_retry')
    with o.SourceUpdateDirectories(HOME,names,set()) as directories:
        saved = {n:o.update_file_state(HOME/n,directories.parent_fd(n)) for n in names}
        require({n:state_record(v) for n,v in saved.items()} == plan['before'], 'baseline_cas_changed')
        expected_marker = json.loads(saved['FRIDAY-INSTALL.json']['data'])
        expected_marker['input_sha256'] = request['current_input']['sha256']
        expected_marker['plugin_files'] = {n:v for n,v in current['project_files'].items()
                                           if n.startswith('plugins/friday_rework/')}
        expected_marker['ordinary_source_update_request'] = plan['request']
        expected_marker['ordinary_gateway']['operator_entry'] = {
            'input':request['current_input'], 'script':{'path':str(source/'scripts/friday_native.py'),
              'sha256':current['project_files']['scripts/friday_native.py']}}
        require(json.loads(after['FRIDAY-INSTALL.json']) == expected_marker,
                'exact_marker_projection_required')
        baseline_links(json.loads(saved['FRIDAY-INSTALL.json']['data']),
                       json.loads(saved['hermes-agent.source.json']['data']),
                       json.loads(saved['hermes-agent/install-stamp.json']['data']),
                       request['previous_input'],previous)
        f.composition_checked(previous,HOME/'hermes-agent',
                              json.loads(saved['hermes-agent.source.json']['data']),donor)
        check(); directories.prove()
        tx.mkdir(mode=0o700)
        for name,before in saved.items():
            if before is not None:
                write(tx/'before'/name,before['data'])
        write(tx/'request.json',pinned(plan['request']))
        write(tx/'intent.json',encode({'schema':'friday.ordinary-telegram-source-update-transaction.v1',
              'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':plan['request']['sha256'],'plan':plan_pin,
              'stopped_evidence':stopped_evidence,'boot_id':boot_id,'deadline_mono':deadline_mono,
              'rollback_deadline_mono':rollback_deadline_mono,'before':{n:({'absent':True} if v is None else {'sha256':sha(v['data']),'mode':v['mode']}) for n,v in saved.items()}}))
        owned = {}
        try:
            for name in names:
                check(); directories.prove()
                mode = saved[name]['mode'] if saved[name] is not None else 0o644
                o.publish_update_file(HOME/name,after[name],mode,saved[name],owned,name,
                                      parent_fd=directories.parent_fd(name))
                write(tx/('published-'+str(names.index(name))+'.json'),encode({name:state_record(owned[name])}))
                write(tx/('published/'+name), after[name])
            check(); directories.prove()
            f.composition_checked(current,HOME/'hermes-agent',receipt,donor)
            o.checked_plugin_inventory(HOME, expected_marker['plugin_files'])
            check()
            require(all(o.update_file_state(HOME/n,directories.parent_fd(n)) == owned[n] for n in names),
                    'published_cas_changed')
        except BaseException as exc:
            try:
                class CleanupDeadline:
                    def check(self):
                        check(cleanup=True)

                    @contextlib.contextmanager
                    def atomic(self):
                        self.check()
                        yield
                        self.check()

                check(cleanup=True); directories.prove()
                o.restore_update_files(HOME,saved,owned,directories,_deadline=CleanupDeadline())
                write(tx/'rolled-back.json',encode({'state':'ROLLED_BACK_NO_RETRY',
                      'exception_class':type(exc).__name__,'plan':plan_pin}))
            except BaseException as cleanup_exc:
                # Preserve everything for Root reconciliation, never blind replay.
                write(tx/'rollback-unconfirmed.json',encode({'state':'UNKNOWN_NO_RETRY',
                      'exception_class':type(exc).__name__,'cleanup_exception_class':type(cleanup_exc).__name__}))
                raise RuntimeError('plugin_overlay_rollback_unconfirmed_keep_consumers_stopped') from cleanup_exc
            raise
        # Outcome publication is outside the rollback catch: a failed return
        # read cannot invalidate an already durable COMMITTED record. If this
        # write fails, Root reconciles the journal and exact installed states;
        # there is no automatic replay or retroactive source rollback.
        write(tx/'committed.json',encode({'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
              'previous_input':request['previous_input'],'current_input':request['current_input'],
              'source_receipt_sha256':sha(after['hermes-agent.source.json']),
              'gateway_started':False,'workers_enabled':False,
              'plan':plan_pin,'after':{n:{'sha256':sha(v['data']),'mode':v['mode']} for n,v in owned.items()}}))
        return ref(tx/'committed.json')


def validate_plugin_delta(previous, current, project_after):
    """Ten exact existing project files; only four are installed plugins."""
    require(type(project_after) is dict and set(project_after) == PROJECT_PATHS,
            's443_exact_ten_project_paths_required')
    require(type(previous) is dict and type(current) is dict
            and {k:v for k,v in previous.items() if k != 'project_files'} ==
                {k:v for k,v in current.items() if k != 'project_files'},
            'operational_settings_changed')
    old, new = previous['project_files'], current['project_files']
    require(type(old) is dict and type(new) is dict and set(old) == set(new),
            'no_project_inventory_additions_or_deletions')
    for name, pin in project_after.items():
        path = Path(name)
        require(type(name) is str and not path.is_absolute()
                and path.as_posix() == name and all(part not in ('.', '..') for part in path.parts)
                and name in PROJECT_PATHS and name in old, 'exact_existing_project_path_required')
        require(type(pin) is dict and set(pin) == {'path','sha256'}
                and type(pin['path']) is str and Path(pin['path']).is_absolute()
                and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256'])
                and new[name] == pin['sha256'] and new[name] != old[name],
                'exact_changed_project_pin_required')
    require({n for n in old if old[n] != new[n]} == set(project_after),
            'unlisted_project_change')
    return sorted(project_after)


def saved_receipt_bytes(package):
    raw = pinned(package['target_source_receipt'])
    require(sha(raw) == META['hermes-agent.source.json'], 'native_source_receipt_changed')
    return raw


def accepted_baseline():
    acceptance = json.loads(pinned(ACCEPTANCE))
    require(acceptance.get('accepted') is True and acceptance.get('accepted_source_only') is True
        and acceptance.get('current_input') == {'path': '<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/source-runtime/INPUT-DSH-EVENT-COMPAT.NEXT.json', 'sha256': 'PRIVATE_REF_94a721411b0647b5'}
        and acceptance.get('marker') == S442_ORIGINAL_MARKER, 's443_exact_2badd_acceptance')
    namespace={'__file__':S442_VERIFIER['path'],'__name__':'_s442_source_native_bridge'}
    exec(compile(pinned(S442_VERIFIER),S442_VERIFIER['path'],'exec'),namespace)
    proof=namespace['verify_native_maintenance'](S442_NATIVE_REQUEST,S442_NATIVE_RECEIPT)
    require(proof['before_marker']==S442_ORIGINAL_MARKER
        and proof['current_marker']=={'path':str(HOME/'FRIDAY-INSTALL.json'),'sha256':META['FRIDAY-INSTALL.json']}, 's442_exact_current_native_bridge')
    native=json.loads(pinned(S442_NATIVE_RECEIPT))
    require(native['current_input']==PREVIOUS and PREVIOUS['sha256']==INPUT_SHA
        and pinned(PREVIOUS)==pinned({'path': '<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/source-runtime/INPUT-DSH-EVENT-COMPAT.NEXT.json', 'sha256': 'PRIVATE_REF_94a721411b0647b5'}), 's442_native_alias_input_changed')
    require(acceptance['source_receipt']=={'path':str(HOME/'hermes-agent.source.json'),'sha256':META['hermes-agent.source.json']},'s442_native_hermes_unchanged')
    return acceptance


def validate_package(package):
    accepted_baseline()
    check_source_gids()
    require(package.get('accepted_baseline') == ACCEPTANCE, 'accepted_baseline_pin_changed')
    require(package.get('native_after') == {}, 'zero_native_delta_required')
    require(package.get('schema') == 'friday.dsh-retained-existing-plugin-package.v1'
            and package.get('home') == str(HOME)
            and package.get('previous_input') == PREVIOUS
            and package.get('adapter') == ref(Path(__file__).resolve()),
            'exact_existing_plugin_package_required')
    previous = json.loads(pinned(package['previous_input']))
    current = json.loads(pinned(package['current_input']))
    changed = validate_plugin_delta(previous, current, package['project_after'])
    require(package['plugin_after'] == {n:r for n,r in package['project_after'].items() if n in PLUGIN_PATHS}, 's443_exact_four_plugin_write_set')
    frozen = json.loads(pinned(package['target_frozen']))
    require(frozen == {'schema':'friday.source-package-frozen.v1',
            'project':package['source'], 'project_files':current['project_files'],
            'parent':{'genuine_conditional_receipt_sha256':META['hermes-agent.source.json']},
            'delta':{'native_rows':[], 'project_added':[], 'project_changed':changed}},
            'frozen_project_delta_changed')
    source = Path(package['source'])
    require(source == OUT/'source' and source.resolve() == source, 'canonical_source_required')
    require(package['current_input']['path'] == str(OUT/INPUT_NAME), 'current_input_path_changed')
    for name, digest in current['project_files'].items():
        require(sha(read(source/name)[0]) == digest, 'project_source_changed')
    require(package['manifest'] == {'path':str(source/MANIFEST),
            'sha256':previous['project_files'][MANIFEST]}, 'retained_manifest_changed')
    pinned(package['manifest'])
    saved_receipt_bytes(package)
    require(package['retained_stamp']['sha256'] == META['hermes-agent/install-stamp.json'],
            'retained_stamp_changed')
    pinned(package['retained_stamp'])
    require(set(package['baseline']) == set(PLUGIN_PATHS) | set(META), 'baseline_scope_changed')
    for name, row in package['baseline'].items():
        expected = META[name] if name in META else previous['project_files'][name]
        require(row.get('sha256') == expected and row.get('mode') in (0o600,0o644)
                and type(row.get('identity')) is list and len(row['identity']) == 5,
                'baseline_pin_or_mode_changed')
    for name, pin in package['plugin_after'].items():
        require(pin == {'path':str(source/name), 'sha256':current['project_files'][name]},
                'plugin_source_pin_changed')
    return changed


def prepare_source_package(*, final_files):
    """Root calls ONCE after combined final reviewable bytes exist.

    final_files: explicit map {existing 'plugins/friday_rework/x.py':
    {'path': absolute_final_file, 'sha256': exact_final_sha256}} for the two exact paired plugin paths.
    This writes only this adapter's own OUT; no admission or installed effects.
    No candidate is selected automatically. Every graph addition and native delta refuses.
    """
    require(not any((OUT/n).exists() for n in ('PACKAGE.json',INPUT_NAME,'source','FROZEN.json','bound')),
            'prepared_package_exists_do_not_replay')
    accepted_baseline()
    previous_pin = PREVIOUS
    previous = json.loads(pinned(previous_pin))
    current = copy.deepcopy(previous)
    require(type(final_files) is dict, 'explicit_final_file_map_required')
    for name, pin in final_files.items():
        # validate_plugin_delta checks the path and exact changed inventory below.
        require(type(pin) is dict and set(pin) == {'path','sha256'}, 'exact_candidate_pin_required')
        current['project_files'][name] = pin['sha256']
    changed = validate_plugin_delta(previous,current,final_files)
    final_data = {name:pinned(pin) for name,pin in final_files.items()}
    baseline = {}
    for name in [*sorted(PLUGIN_PATHS),*META]:
        data, st = read(HOME/name)
        expected = META[name] if name in META else previous['project_files'][name]
        require(sha(data) == expected and stat.S_IMODE(st.st_mode) in (0o600,0o644),
                'current_installed_baseline_changed')
        baseline[name] = {'sha256':sha(data), 'bytes':len(data), 'mode':stat.S_IMODE(st.st_mode),
                         'identity':[st.st_dev,st.st_ino,st.st_uid,st.st_nlink,st.st_mode]}
    marker = json.loads(pinned({'path':str(HOME/'FRIDAY-INSTALL.json'),'sha256':META['FRIDAY-INSTALL.json']}))
    receipt_raw = pinned({'path':str(HOME/'hermes-agent.source.json'),'sha256':META['hermes-agent.source.json']})
    stamp_raw = pinned({'path':str(HOME/'hermes-agent/install-stamp.json'),'sha256':META['hermes-agent/install-stamp.json']})
    receipt, stamp = json.loads(receipt_raw), json.loads(stamp_raw)
    require(marker['plugin_files'] == {n:v for n,v in previous['project_files'].items()
                if n.startswith('plugins/friday_rework/')}, 'installed_plugin_inventory_changed')
    baseline_links(marker, receipt, stamp, previous_pin, previous)
    require(marker['ordinary_source_update_request'] == PREDECESSOR, 'current_predecessor_changed')
    pinned(marker['ordinary_source_update_request'])
    # Pin/check the complete small project graph, then copy it. Native tree is not copied.
    source = OUT/'source'
    for name, digest in current['project_files'].items():
        data = final_data.get(name)
        if data is None:
            data = pinned({'path':str(BASE/'source'/name), 'sha256':previous['project_files'][name]})
        require(sha(data) == digest, 'final_project_pin_changed')
        write(source/name,data)
    write(OUT/INPUT_NAME,encode(current))
    write(OUT/'TARGET-SOURCE-RECEIPT.json',receipt_raw)
    write(OUT/'RETAINED-STAMP.json',stamp_raw)
    frozen = {'schema':'friday.source-package-frozen.v1', 'project':str(source),
              'project_files':current['project_files'],
              'parent':{'genuine_conditional_receipt_sha256':META['hermes-agent.source.json']},
              'delta':{'native_rows':[], 'project_added':[], 'project_changed':changed}}
    write(OUT/'FROZEN.json',encode(frozen))
    package = {'schema':'friday.dsh-retained-existing-plugin-package.v1', 'home':str(HOME),
       'adapter':ref(Path(__file__).resolve()), 'source':str(source),
       'accepted_baseline':ACCEPTANCE, 'native_after':{},
       'previous_input':previous_pin, 'current_input':ref(OUT/INPUT_NAME),
       'target_frozen':ref(OUT/'FROZEN.json'),
       'manifest':ref(source/MANIFEST), 'target_source_receipt':ref(OUT/'TARGET-SOURCE-RECEIPT.json'),
       'retained_stamp':ref(OUT/'RETAINED-STAMP.json'), 'baseline':baseline,
       'project_after':{name:ref(source/name) for name in changed},
       'plugin_after':{name:ref(source/name) for name in sorted(PLUGIN_PATHS)}}
    validate_package(package)
    write(OUT/'PACKAGE.json',encode(package))
    return ref(OUT/'PACKAGE.json')


if __name__ == '__main__':
    raise SystemExit('Library only. Exact one final reviewed pin and distinct Root maintenance required.')
