# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Root-only four-link A0 publication. Import is inert; no command line effects.

Call from the existing authenticated _friday_dashboard_projection graph. Future
proof, clocks, grant and session are deliberately not embedded in this source.
"""
import contextlib
import copy
import fcntl
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

HERE = Path(__file__).resolve().parent
H = Path('<INSTALL_HOME>')
U = H / 'profiles/telegram-bot-9000000001'
NAMES = ('workers/a0/runtime-receipt.json', 'config.yaml', '.friday-onboarding.json', '.friday-user-scope.json')
NATIVE_AFTER = 'PRIVATE_REF_8916093c39ce1493'
NATIVE_BEFORE = 'PRIVATE_REF_6155f4bda62ac687'
PRIMITIVES_SHA = 'PRIVATE_REF_f01d5800ea8e9a94'
ACTUAL_ACCEPTANCE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_48678ca08730fc64'}
ACTUAL_INPUT = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/source-runtime/INPUT-DSH-EVENT-COMPAT.NEXT.json', 'sha256': 'PRIVATE_REF_94a721411b0647b5'}
PERMISSION = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8d49c5d2c21bde3b/ROOT-PUBLICATION-FUTURE-UNBOUND/COMMITTED.json', 'sha256': 'PRIVATE_REF_b90137377799a3f7'}
NATIVE_VERIFIER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/verify_native.py', 'sha256': 'PRIVATE_REF_7ca4b2793c514fe4'}
BRIDGE_VERIFIER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/verify480.py', 'sha256': 'PRIVATE_REF_8140e0cd6deb0e06'}
ACTUAL_PACKAGE = {'path':'<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/source-runtime/PACKAGE.json','sha256':'PRIVATE_REF_84921ebaa8a088b3'}
ACTUAL_COMMIT = {'path':'<INSTALL_HOME>/preparation/ordinary-source-update-PRIVATE_REF_27a6566ffea4bed7/committed.json','sha256':'PRIVATE_REF_0a23597d1a99b048'}
ACTUAL_SIDECAR_COMMIT = {'path':'<PRIVATE_CACHE>/PRIVATE_REF_5b60f42104ae22e9/service/sidecar/committed.json','sha256':'PRIVATE_REF_cc01a00b427119e3'}
ACTUAL_DSH_SIDECAR = {'path':str(U/'workers/dsh/postboot-revalidation.json'),'sha256':'PRIVATE_REF_0c0dd6ad4837503b'}
OPERATION = 'S447_A0_MISSING_COLD_READINESS_PUBLICATION'
SCHEMA = 'frw.Root.S447.fourlink-publication-request.v1'
FULL_KEYS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def identity(info):
    return {key: getattr(info, key) for key in FULL_KEYS}


def read_ref(reference):
    need(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'exact_reference_required')
    path = Path(reference['path'])
    need(path.is_absolute() and path.resolve() == path and str(path) == reference['path'], 'canonical_reference_required')
    parents = {}
    for parent in path.parents:
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022, 'protected_reference_parent_required')
        parents[parent] = (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid() and first.st_gid == os.getegid() == 12345 and first.st_nlink == 1 and stat.S_IMODE(first.st_mode) in (0o400, 0o600), 'private_reference_custody_required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(64 * 1024 ** 2 + 1)
        need(len(raw) <= 64 * 1024 ** 2 and identity(first) == identity(os.fstat(fd)) == identity(path.lstat()) and sha(raw) == reference['sha256'], 'reference_identity_or_hash_changed')
    finally:
        os.close(fd)
    need(all((q.lstat().st_dev, q.lstat().st_ino, q.lstat().st_uid, q.lstat().st_gid, q.lstat().st_mode) == value for q, value in parents.items()), 'reference_parent_changed')
    return raw


def document(reference):
    return json.loads(read_ref(reference))


def pin(path):
    result = {'path': str(path), 'sha256': sha(path.read_bytes())}
    read_ref(result)
    return result


def write_new(path, raw):
    raw = raw if type(raw) is bytes else encode(raw)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def primitives():
    path = HERE / 'ordinary_primitives.py'
    raw = read_ref({'path': str(path), 'sha256': PRIMITIVES_SHA})
    module = types.ModuleType('_S443_exact_ordinary_primitives')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def validate_clock(clock, parent, now, boot, *, cleanup=False):
    for value in (clock, parent):
        need(type(value) is dict and value.get('no_reset') is True and value.get('boot_id') == boot, 'genuine_current_boot_clock_required')
        need(all(type(value.get(k)) in (int, float) and math.isfinite(value[k]) for k in ('origin_monotonic', 'deadline_monotonic', 'budget_seconds', 'reserve_seconds')), 'finite_original_clock_required')
        need(type(value['budget_seconds']) is int and 30 <= value['budget_seconds'] <= 7200 and 0 < value['reserve_seconds'] < value['budget_seconds'] and value['deadline_monotonic'] == value['origin_monotonic'] + value['budget_seconds'], 'finite_clock_geometry_required')
        need(value['origin_monotonic'] <= now < value['deadline_monotonic'] - (0 if cleanup else value['reserve_seconds']), 'original_deadline_or_reserve_exhausted')
    need(clock.get('schema') == 'frw.Root.S447.fourlink-publication-clock.v1' and clock.get('operation_id') == OPERATION, 'separate_future_publication_clock_required')
    need(parent['origin_monotonic'] <= clock['origin_monotonic'] and clock['deadline_monotonic'] <= parent['deadline_monotonic'] - parent['reserve_seconds'], 'publication_outside_original_parent_budget')


class StageBudget:
    def __init__(self, clock_ref, parent_ref):
        self.clock_ref, self.parent_ref = clock_ref, parent_ref
        self.clock, self.parent = document(clock_ref), document(parent_ref)
        need(self.clock.get('original_clock') == parent_ref, 'exact_parent_clock_join_required')
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.deadline = self.clock['deadline_monotonic'] - self.clock['reserve_seconds']
        self.check()

    def check(self, *, reserve=0, cleanup=False):
        need(document(self.clock_ref) == self.clock and document(self.parent_ref) == self.parent, 'original_clock_changed')
        need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == self.boot, 'boot_changed')
        validate_clock(self.clock, self.parent, time.monotonic(), self.boot, cleanup=cleanup)
        remaining = min(self.clock['deadline_monotonic'] - (0 if cleanup else self.clock['reserve_seconds']), self.parent['deadline_monotonic'] - (0 if cleanup else self.parent['reserve_seconds'])) - time.monotonic() - reserve
        need(remaining > 0, 'finite_consumer_budget_exhausted')
        return remaining

    def call(self, function, *args, **kwargs):
        self.check(); result = function(*args, **kwargs); self.check(); return result


def metadata_candidates(raws, *, c, receipt, native480_request, native480_receipt):
    """Validated A0 native480 tuple/receipt, then exactly two hash links."""
    import yaml
    need(type(raws) in (tuple, list) and len(raws) == 4, 'exact_four_beforeimages_required')
    before = yaml.safe_load(raws[1]); after = copy.deepcopy(before)
    entry = before['plugins']['entries']['friday_rework']
    need(entry.get('allow_gateway_delivery') is True, 'actual_delivery_permission_must_survive')
    workers = entry['settings']['runtime']['workers']
    old_c = workers['a0']
    bridge = bridge_module()
    expected = bridge['runtime480'](old_c,native480_request,native480_receipt)
    need(expected['a0']['runtime']['sha256'] == NATIVE_AFTER, 'exact_native480_runtime_required')
    need({k:v for k,v in expected.items() if k != 'runtime_receipt'} == {k:v for k,v in c.items() if k != 'runtime_receipt'}, 'only_authenticated_A0_native480_tuple_may_change')
    need(old_c['runtime_receipt'] == {'path': str(U / NAMES[0]), 'sha256': sha(raws[0])}, 'old_receipt_chain_changed')
    need(receipt.get('schema') == 'friday-rework.a0-runtime.v2' and receipt.get('ready') is True, 'genuine_readiness_receipt_required')
    need(receipt.get('runtime_sha256') == sha(json.dumps({k:v for k,v in c.items() if k != 'runtime_receipt'}, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()), 'readiness_runtime_hash_changed')
    new_receipt = encode(receipt)
    expected['runtime_receipt'] = {'path': str(U / NAMES[0]), 'sha256': sha(new_receipt)}
    after['plugins']['entries']['friday_rework']['settings']['runtime']['workers']['a0'] = expected
    need(after['plugins']['entries']['friday_rework']['settings']['runtime']['workers']['dsh'] == workers['dsh'], 'DSH_subtree_changed')
    new_config = yaml.safe_dump(after, sort_keys=False, allow_unicode=True).encode()
    need(yaml.safe_load(new_config) == after, 'configuration_roundtrip_changed')
    onboard = json.loads(raws[2]); marker = json.loads(raws[3])
    need(onboard['config_sha256'] == sha(raws[1]) and marker['onboarding_sha256'] == sha(raws[2]), 'current_fourlink_join_changed')
    onboard['config_sha256'] = sha(new_config); new_onboard = encode(onboard)
    marker['onboarding_sha256'] = sha(new_onboard)
    return [new_receipt, new_config, new_onboard, encode(marker)]


@contextlib.contextmanager
def retained_lock(path, *, marker=None):
    original = pin(path); first = identity(path.lstat())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(first == identity(os.fstat(fd)), 'lock_identity_changed')
        if marker is not None:
            need(os.pread(fd, len(marker) + 1, 0) == marker, 'existing_admission_marker_required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def prove():
            read_ref(original)
            need(first == identity(os.fstat(fd)) == identity(path.lstat()), 'retained_lock_changed')
        prove(); yield prove; prove()
    finally:
        os.close(fd)


def trusted_graph(onboarding):
    need(type(onboarding).__module__ == '_friday_dashboard_projection.onboarding', 'existing_trusted_projection_required')
    package = '_friday_dashboard_projection'
    modules = {name: importlib.import_module(package + '.' + name) for name in ('onboarding', 'associations', 'supervision', 'host_runtime', 'user_worker_join')}
    need(type(onboarding) is modules['onboarding'].Onboarding, 'single_genuine_Onboarding_graph_required')
    for name, module in modules.items():
        need(Path(module.__file__).resolve() == H / 'plugins/friday_rework' / (name + '.py'), 'actual_installed_projection_module_required')
    need(all(not name.startswith('plugins.friday_rework') for name in sys.modules), 'second_plugin_graph_refused')
    return modules


def quiet_row_shape(row):
    # Native Associations.claim releases capacity on host.quiescence. Settled
    # rows retain historical preparation_reserved=True; never rewrite that fact.
    need(row.get('host', {}).get('terminal') is not None and row['host'].get('quiescence') is not None, 'worker_active_or_unknown')


def bridge_module():
    ns = {'__file__':BRIDGE_VERIFIER['path'], '__name__':'_S443_exact_native480_bridge'}
    exec(compile(read_ref(BRIDGE_VERIFIER),BRIDGE_VERIFIER['path'],'exec'),ns)
    return ns


def actual_ancestor():
    """Fixed actual source-only baseline, with DSH sidecar already published."""
    ancestor = document(ACTUAL_ACCEPTANCE)
    package, committed = document(ACTUAL_PACKAGE), document(ACTUAL_COMMIT)
    need(ancestor['accepted'] is True and ancestor['accepted_source_only'] is True
        and ancestor['runtime_or_user_semantics_accepted'] is False
        and ancestor['current_input'] == package['current_input'] == committed['current_input'] == ACTUAL_INPUT
        and ancestor['committed'] == ACTUAL_COMMIT and ancestor['plan'] == committed['plan']
        and committed['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED', 'actual_2badd_ancestor_changed')
    sidecar = document(ACTUAL_SIDECAR_COMMIT)
    need(sidecar['sidecar'] == ACTUAL_DSH_SIDECAR, 'actual_DSH_sidecar_commit_changed')
    read_ref(ACTUAL_DSH_SIDECAR)
    return ancestor


def source_now(source, modules):
    """Actual exact S447 child; original observations and native receipts stay fixed."""
    need(set(source) == {'installed_acceptance','source_review','source_package','native_request','native_receipt','native480_request','native480_receipt'}, 'exact_source_binding_required')
    actual_ancestor()  # Retain the original DSH publication evidence unchanged.
    compat_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/compat.py', 'sha256': 'PRIVATE_REF_02fcb1106bb4b088'}
    compat={'__file__':compat_ref['path'],'__name__':'_s447_fourlink_source_compat'}
    exec(compile(read_ref(compat_ref),compat_ref['path'],'exec'),compat)
    proof,tx=compat['source_proof']()
    need(source['source_package']==proof['package'] and source['source_review']==document(proof['request'])['source_review'], 's447_exact_installed_package_review_required')
    bridge=bridge_module(); current=bridge['verify480'](source['native480_request'],source['native480_receipt'])
    need(current['source_acceptance']==source['installed_acceptance'], 's447_actual_installed_acceptance_required')
    accepted=document(source['installed_acceptance'])
    need(accepted['accepted'] is True and accepted['accepted_source_only'] is True and accepted['runtime_or_user_semantics_accepted'] is False and all(accepted[k]==proof[v] for k,v in (('current_input','current_input'),('committed','commit'),('marker','current_marker'),('plan','plan'),('source_receipt','source_receipt'))), 's447_actual_source_join_changed')
    native={'__file__':NATIVE_VERIFIER['path'],'__name__':'_s447_fourlink_native_verifier'}
    exec(compile(read_ref(NATIVE_VERIFIER),NATIVE_VERIFIER['path'],'exec'),native)
    native=native['verify_native_historical'](source['native_request'],source['native_receipt'],source['native480_request'],source['native480_receipt'])
    need(native['source_continuity']['package']==proof['package'] and native['source_continuity']['commit']==proof['commit'] and native['current_marker']==proof['current_marker'], 's447_native_source_continuity_changed')
    marker=document(accepted['marker']); current_input=document(accepted['current_input'])
    for name,module in modules.items():
        relative='plugins/friday_rework/'+name+'.py'
        need(marker['plugin_files'][relative]==current_input['project_files'][relative], 'installed_source_graph_pin_changed')
        read_ref({'path':str(Path(module.__file__)),'sha256':marker['plugin_files'][relative]})
    return accepted


@contextlib.contextmanager
def authority(onboarding, arguments, budget, source):
    """Native ordering and current rights, with no alias modules or stale session."""
    modules = trusted_graph(onboarding); om = modules['onboarding']; am = modules['associations']
    from hermes_cli import config as native
    from hermes_cli.auth import _auth_store_lock
    from hermes_cli.plugins_state import PluginState
    from hermes_cli.friday_product_access import current_access, principal_id
    need(set(arguments) == {'profile', 'session', 'expected_config_sha256', 'generation', 'platform', 'transport_profile', 'account_id', 'user_id'}, 'exact_current_authenticated_arguments_required')
    profile, session = arguments['profile'], arguments['session']
    identity_args = {k:arguments[k] for k in om.IDENTITY}
    need(profile == arguments['transport_profile'], 'receiving_profile_changed')
    # Onboarding.transaction owns root state/admission and root config locks.
    with onboarding.transaction(profile, arguments['expected_config_sha256'], session) as (root, access, root_config):
        need(root == H, 'exact_root_home_required')
        home, binding, user, prepared = onboarding._prepared(root, access.state, **identity_args, generation=arguments['generation'])
        need(home == U and user['enabled'] is True and user['role'] == 'user', 'exact_enabled_ordinary_home_required')
        with contextlib.ExitStack() as stack:
            # Retain existing locks; never initialize a lock in this maintenance.
            existing = [root/'config.yaml.lock', home/'config.yaml.lock', root/'auth.lock', home/'auth.lock', root/'.env.lock', home/'.env.lock']
            lock_states = {p:(pin(p), identity(p.lstat())) for p in existing}
            stack.enter_context(native.config_write_transaction(home/'config.yaml'))
            stack.enter_context(_auth_store_lock(timeout_seconds=min(2, budget.check()), target_path=root/'auth.json'))
            stack.enter_context(_auth_store_lock(timeout_seconds=min(2, budget.check()), target_path=home/'auth.json'))
            stack.enter_context(native._env_write_lock(root/'.env'))
            stack.enter_context(native._env_write_lock(home/'.env'))
            with om.scope.authority(home):
                store = am.Associations(PluginState('friday_rework'), storage_readonly=True)
                directory = store._state_directory()
                need(directory.resolve() == directory and directory.is_relative_to(home), 'own_child_state_required')
                state_pin = pin(directory/'state.json')
                admission = stack.enter_context(retained_lock(directory/'admission.lock', marker=b'v1\n'))
                # Native route lock follows the child admission lock.
                with om.scope.authority(home):
                    child_config = native.load_config_storage_readonly()
                c = copy.deepcopy(child_config['plugins']['entries']['friday_rework']['settings']['runtime']['workers']['a0'])
                c = bridge_module()['runtime480'](c,source['native480_request'],source['native480_receipt'])
                runtime = modules['host_runtime'].a0_runtime_module(c)
                native_lock = stack.enter_context(retained_lock(Path(runtime.RUNTIME)/'runtime.lock'))
                initial_store = store.state_get(am.KEY, None); am._validate_store(initial_store)
                state_raw = read_ref(state_pin)
                accepted_source = source_now(source, modules)
                stable_sources = [accepted_source[k] for k in ('marker','current_input','source_receipt')] + [ACTUAL_DSH_SIDECAR,ACTUAL_SIDECAR_COMMIT]
                stable_sources += [{'path':str(Path(module.__file__)), 'sha256':document(accepted_source['marker'])['plugin_files']['plugins/friday_rework/'+name+'.py']} for name,module in modules.items()]
                home_custody = tuple(getattr(home.lstat(), k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode'))
                soul_ref = pin(home/'SOUL.md')
                credentials = modules['user_worker_join'].credentials(home)
                def rights(*, changed=False, cleanup=False):
                    budget.check(cleanup=cleanup)
                    admission(); native_lock()
                    for path, (reference, original) in lock_states.items():
                        read_ref(reference); need(identity(path.lstat()) == original, 'native_lock_custody_changed')
                    for reference in stable_sources: read_ref(reference)
                    with om.scope.authority(root):
                        onboarding._verify_operator(profile, session)
                        principal = principal_id(*(binding[k] for k in om.IDENTITY))
                        row = current_access(access.state)['users'].get(principal)
                        need(row == user and row['enabled'] is True and row['generation'] == arguments['generation'], 'current_access_or_generation_changed')
                        need(om.digest(root/'config.yaml') == arguments['expected_config_sha256'], 'root_config_CAS_changed')
                        # The protected four-link chain is intentionally a
                        # prefix while its four owned replacements are made.
                        # Keep immutable owner/home/credential checks throughout;
                        # whole-chain checks are upfront and final only.
                        need(tuple(getattr(home.lstat(), k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')) == home_custody, 'ordinary_home_custody_changed')
                        read_ref(soul_ref)
                        need(modules['user_worker_join'].credentials(home) == credentials, 'ordinary_credentials_changed')
                        if not changed:
                            om.scope.check_onboarding_home(root, home, binding)
                        need(onboarding._native_grant(root, binding, storage_readonly=True), 'native_grant_revoked')
                        if not changed:
                            need(onboarding._prepared(root, access.state, **identity_args, generation=arguments['generation']) == (home, binding, user, prepared), 'current_preparation_changed')
                    need(read_ref(state_pin) == state_raw and store.state_get(am.KEY, None) == initial_store, 'worker_state_changed')
                    for row in initial_store['jobs'].values():
                        quiet_row_shape(row)
                        observed = modules['supervision'].NativeSupervisor().observe(row, deadline=time.monotonic()+min(5,budget.check(cleanup=cleanup)))
                        need(isinstance(observed, modules['supervision'].UnitObservation) and observed.quiescent, 'fresh_worker_quiet_required')
                    launcher = runtime.checked_launcher(c['a0']['launcher']['sha256'])
                    fields = runtime._route_unit(launcher, runtime.Runtime._command, min(5, budget.check(cleanup=cleanup)))
                    need(fields['ActiveState'] in ('inactive', 'failed') and fields['MainPID'] == '0' and runtime.cgroup_snapshot(launcher['SERVICE_GROUP'])['populated'] is False, 'A0_route_active_or_unknown')
                    need(not os.path.lexists(HERE/'CANCEL') or cleanup, 'owner_cancelled')
                rights(); yield modules, home, binding, prepared, c, rights


def bind_candidates(onboarding, *, arguments, source, postboot_proof_ref, output_directory, clock_ref, parent_clock_ref):
    """Read fresh mutable inputs once, only after genuine future Root proof exists."""
    budget = StageBudget(clock_ref, parent_clock_ref)
    out = Path(output_directory)
    need(out == HERE/('candidates-'+postboot_proof_ref['sha256']) and out.resolve() == out and not os.path.lexists(out), 'fixed_proof_candidate_directory_required')
    with authority(onboarding, arguments, budget, source) as (modules, home, binding, prepared, c, rights):
        join = modules['user_worker_join']; proof = document(postboot_proof_ref)
        need(postboot_proof_ref['path'] == str(home/'workers/a0/postboot-revalidation.json'), 'canonical_future_A0_proof_required')
        join._postboot_a0_validate(c, proof, binding=binding, generation=arguments['generation'])
        receipt = join.readiness_receipt(c, [proof['preparations']['a0'], postboot_proof_ref])
        refs = [pin(home/name) for name in NAMES]; raws = [read_ref(reference) for reference in refs]
        candidates = metadata_candidates(raws, c=c, receipt=receipt, native480_request=source['native480_request'], native480_receipt=source['native480_receipt'])
        dsh = pin(home/'workers/dsh/runtime-receipt.json')
        dsh_raw = read_ref(dsh); read_ref(PERMISSION)
        P = primitives(); items = []
        with P.SourceUpdateDirectories(home, list(NAMES), set()) as dirs:
            for name, reference in zip(NAMES, refs):
                info = os.stat(Path(name).name, dir_fd=dirs.parent_fd(name), follow_symlinks=False)
                need(info.st_gid == os.getegid() == 12345 and stat.S_IMODE(info.st_mode) == 0o600, 'current_metadata_gid_or_mode_changed')
                items.append({'name': name, 'before': reference, 'identity': identity(info)})
        rights(); out.mkdir(mode=0o700)
        for index, (raw, new) in enumerate(zip(raws, candidates)):
            write_new(out/('BEFORE-'+str(index)+'.bin'), raw)
            write_new(out/('AFTER-'+str(index)+'.bin'), new)
            items[index]['before_copy'] = pin(out/('BEFORE-'+str(index)+'.bin'))
            items[index]['candidate'] = pin(out/('AFTER-'+str(index)+'.bin'))
        spec = {'schema':'frw.S447.actual-fourlink-candidates.v1', 'publisher':pin(Path(__file__).resolve()), 'source':source, 'items':items, 'order':list(NAMES), 'postboot_proof':postboot_proof_ref, 'dsh_receipt':dsh, 'dsh_sha256':sha(dsh_raw), 'root_configuration_sha256':arguments['expected_config_sha256'], 'binding':binding, 'generation':arguments['generation'], 'allow_gateway_delivery':True, 'runtime_effects':False, 'clocks_created':False}
        rights(); write_new(out/'PUBLICATION.json', spec)
        return pin(out/'PUBLICATION.json')


def transaction(P, home, items, candidates, *, guard, output):
    """All attempts reconcile saved OR recorded-owned inodes, even helper raises."""
    saved, gids, saved_metadata, owned_metadata = {}, {}, {}, {}
    class Owned(dict):
        def __setitem__(self, name, value):
            # Existing helper records ownership BEFORE replace. Retain the
            # created descriptor's stable GID/mtime/size as well, even if the
            # helper raises immediately after replace and never returns.
            stage = home/name
            info = os.stat(stage.name+'.ordinary-staged', dir_fd=dirs.parent_fd(name), follow_symlinks=False)
            owned_metadata[name] = {k:getattr(info,k) for k in ('st_gid','st_size','st_mtime_ns')}
            super().__setitem__(name, value)
    owned = Owned()
    names = [item['name'] for item in items]
    committed = False
    def put(name, value):
        write_new(output/name, value)
    with P.SourceUpdateDirectories(home, names, set()) as dirs:
        directory_ids = {name:(os.fstat(fd).st_dev, os.fstat(fd).st_ino, os.fstat(fd).st_gid) for name,fd in dirs.fds.items()}
        def custody(*, cleanup=False):
            guard(cleanup=cleanup); dirs.prove()
            for name,fd in dirs.fds.items():
                need((os.fstat(fd).st_dev, os.fstat(fd).st_ino, os.fstat(fd).st_gid) == directory_ids[name], 'foreign_directory_metadata_UNKNOWN')
            for name in names:
                info = os.stat(Path(name).name, dir_fd=dirs.parent_fd(name), follow_symlinks=False)
                need(info.st_gid == gids.get(name, os.getegid()) == os.getegid() == 12345, 'foreign_target_GID_UNKNOWN')
                if name in saved:
                    actual = P.update_file_state_at(home/name, dirs.parent_fd(name))
                    if actual == saved[name]:
                        need(identity(info) == saved_metadata[name], 'foreign_saved_metadata_UNKNOWN')
                    elif name in owned and actual == owned[name]:
                        need(all(getattr(info,k) == v for k,v in owned_metadata[name].items()), 'foreign_owned_metadata_UNKNOWN')
                    else:
                        need(False, 'foreign_or_unknown_target_no_overwrite')
        for item in items:
            name = item['name']; info = os.stat(Path(name).name, dir_fd=dirs.parent_fd(name), follow_symlinks=False)
            need(identity(info) == item['identity'], 'substituted_current_CAS')
            saved[name] = P.update_file_state_at(home/name, dirs.parent_fd(name)); gids[name] = info.st_gid
            saved_metadata[name] = identity(info)
            need(saved[name] is not None and sha(saved[name]['data']) == item['before']['sha256'] and saved[name]['mode'] == 0o600, 'current_beforeimage_changed')
        custody()
        put('INTENT.json', {'state':'CONSUMED_NO_RETRY', 'order':names, 'old_effects_replayed':False})
        for index,name in enumerate(names): put('BEFORE-'+str(index)+'.bin', saved[name]['data'])
        try:
            for index,name in enumerate(names):
                custody()
                for other in names:
                    actual=P.update_file_state_at(home/other, dirs.parent_fd(other))
                    need(actual == owned.get(other, saved[other]), 'publication_CAS_changed')
                P.publish_update_file(home/name, candidates[index], 0o600, saved[name], owned, name, parent_fd=dirs.parent_fd(name))
                owned_metadata[name] = identity(os.stat(Path(name).name, dir_fd=dirs.parent_fd(name), follow_symlinks=False))
                custody()
                need(P.update_file_state_at(home/name, dirs.parent_fd(name)) == owned[name], 'published_file_changed')
                put('PUBLISHED-'+str(index)+'.json', {'name':name, 'sha256':sha(candidates[index])})
            custody()
            guard(final=True)
            # Once commit publication starts, visibility failure is UNKNOWN;
            # never roll back a potentially visible committed publication.
            committed = True
            put('COMMITTED.json', {'state':'A0_FOURLINK_PUBLISHED', 'files':{name:sha(raw) for name,raw in zip(names,candidates)}, 'allow_gateway_delivery':True, 'dsh_unchanged':True, 'user_result_accepted':False})
            return pin(output/'COMMITTED.json')
        except BaseException as error:
            if committed:
                try: put('COMMIT-UNKNOWN.json', {'state':'UNKNOWN_RECONCILE_ONLY', 'failure_class':type(error).__name__})
                except BaseException: pass
                raise RuntimeError('COMMIT_UNKNOWN_RECONCILE_ONLY') from error
            try:
                custody(cleanup=True)
                # Prove ALL attempted targets before restoring any. The helper
                # records its inode before replace, so both failure sides join.
                for name in names:
                    actual = P.update_file_state_at(home/name, dirs.parent_fd(name))
                    need(actual == saved[name] or (name in owned and actual == owned[name]), 'foreign_or_unknown_target_no_overwrite')
                for name in reversed(names):
                    custody(cleanup=True)
                    actual = P.update_file_state_at(home/name, dirs.parent_fd(name))
                    if actual == saved[name]: continue
                    need(name in owned and actual == owned[name], 'rollback_CAS_changed')
                    restored = {}
                    P.publish_update_file(home/name, saved[name]['data'], 0o600, owned[name], restored, name, parent_fd=dirs.parent_fd(name))
                    # Keep the new restored inode map for subsequent guards.
                    saved[name] = restored[name]
                    saved_metadata[name] = identity(os.stat(Path(name).name, dir_fd=dirs.parent_fd(name), follow_symlinks=False))
                custody(cleanup=True)
                need(all(P.update_file_state_at(home/name, dirs.parent_fd(name)) == saved[name] for name in names), 'rollback_readback_changed')
                put('ROLLED-BACK.json', {'state':'ROLLED_BACK_CONSUMED_NO_RETRY', 'failure_class':type(error).__name__})
            except BaseException as unknown:
                try: put('ROLLBACK-UNKNOWN.json', {'state':'UNKNOWN_RECONCILE_ONLY', 'failure_class':type(error).__name__, 'rollback_class':type(unknown).__name__})
                except BaseException: pass
                raise RuntimeError('ROLLBACK_UNKNOWN_RECONCILE_ONLY') from unknown
            raise


def apply(onboarding, *, arguments, request_ref):
    """Root invokes in a fresh authenticated installed context; no CLI shortcut."""
    request = document(request_ref)
    need(set(request) == {'schema','publisher','publication','clock','parent_clock','once_grant','output_directory','source'}, 'exact_future_Root_request_required')
    need(request['schema'] == SCHEMA and request['publisher'] == pin(Path(__file__).resolve()), 'exact_publisher_required')
    body = {k:v for k,v in request.items() if k != 'once_grant'}
    need(document(request['once_grant']) == {'schema':SCHEMA+'.once-grant','operation_id':OPERATION,'request_body_sha256':sha(encode(body)),'no_retry':True}, 'fresh_exact_once_grant_required')
    budget = StageBudget(request['clock'], request['parent_clock'])
    spec = document(request['publication'])
    need(spec['schema'] == 'frw.S447.actual-fourlink-candidates.v1' and spec['publisher'] == request['publisher'] and spec['source'] == request['source'] and spec['order'] == list(NAMES) == [i['name'] for i in spec['items']], 'exact_fourlink_publication_required')
    out = Path(request['output_directory'])
    need(out == HERE/('publication-'+spec['postboot_proof']['sha256']) and out.resolve() == out and not os.path.lexists(out), 'consumed_or_unknown_proof_operation_no_retry')
    with authority(onboarding, arguments, budget, request['source']) as (modules, home, binding, prepared, c, rights):
        need(binding == spec['binding'] and arguments['generation'] == spec['generation'] and arguments['expected_config_sha256'] == spec['root_configuration_sha256'], 'publication_authority_changed')
        join = modules['user_worker_join']; proof = document(spec['postboot_proof'])
        join._postboot_a0_validate(c, proof, binding=binding, generation=arguments['generation'])
        raws = [read_ref(item['before_copy']) for item in spec['items']]
        need(all(item['before']['path'] == str(home/item['name']) and item['before_copy']['sha256'] == item['before']['sha256'] for item in spec['items']), 'publication_before_path_or_hash_changed')
        receipt = join.readiness_receipt(c, [proof['preparations']['a0'], spec['postboot_proof']])
        candidates = [read_ref(item['candidate']) for item in spec['items']]
        need(candidates == metadata_candidates(raws, c=c, receipt=receipt, native480_request=request['source']['native480_request'], native480_receipt=request['source']['native480_receipt']), 'candidate_semantics_or_hash_changed')
        dsh = read_ref(spec['dsh_receipt'])
        need(spec['dsh_receipt']['path'] == str(home/'workers/dsh/runtime-receipt.json') and sha(dsh) == spec['dsh_sha256'], 'DSH_receipt_changed')
        def guard(*, cleanup=False, final=False):
            rights(changed=True, cleanup=cleanup)
            for reference in (request_ref, request['once_grant'], request['publication'], spec['postboot_proof'], PERMISSION): read_ref(reference)
            for item in spec['items']: read_ref(item['candidate'])
            need(read_ref(spec['dsh_receipt']) == dsh, 'DSH_receipt_changed')
            if final:
                import yaml
                actual = yaml.safe_load((home/'config.yaml').read_bytes())
                actual_c = actual['plugins']['entries']['friday_rework']['settings']['runtime']['workers']['a0']
                with modules['onboarding'].scope.authority(H):
                    modules['onboarding'].scope.check_onboarding_home(H, home, binding)
                join.checked_postboot_a0(actual_c, spec['postboot_proof'], binding=binding, generation=arguments['generation'])
                with modules['onboarding'].scope.authority(home):
                    from hermes_cli.config import load_config_storage_readonly
                    need(load_config_storage_readonly()['plugins']['entries']['friday_rework'].get('allow_gateway_delivery') is True, 'effective_delivery_permission_changed')
                need(all((home/name).read_bytes() == raw for name,raw in zip(NAMES,candidates)), 'final_fourlink_readback_changed')
        guard(); out.mkdir(mode=0o700)
        write_new(out/'REQUEST.json', {'request':request_ref,'publication':request['publication'],'clock':request['clock'],'parent_clock':request['parent_clock'],'source':request['source'],'effects':'FOUR_METADATA_LINKS_ONLY'})
        return transaction(primitives(), home, spec['items'], candidates, guard=guard, output=out)
