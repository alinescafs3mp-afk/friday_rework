"""One unchanged installed validator invocation, with passive evidence and own process accounting."""
raise RuntimeError('INACTIVE_SOURCE_ONLY_FRESH_VALIDATION_INPUTS_GATED_LAUNCH_REVIEW_REQUIRED')
import sys
sys.dont_write_bytecode = True
import types
import os, json, hashlib, importlib.util, inspect, marshal, stat, fcntl, time, signal, ctypes, subprocess, traceback, tomllib
from pathlib import Path
from datetime import datetime, timezone, timedelta
OUT = Path('/PORTABLE_UNBOUND/PATH_0002')
ROOT = OUT.parent
SOURCE = Path('/PORTABLE_UNBOUND/PATH_0003')
RELEASE = Path('/PORTABLE_UNBOUND/PATH_0004')
CANDIDATE = Path('/PORTABLE_UNBOUND/PATH_0005')
PROVENANCE = Path('/PORTABLE_UNBOUND/PATH_0006')
LIVE_COMPAT = Path('/PORTABLE_UNBOUND/PATH_0007')
INSTALLED = Path('/PORTABLE_UNBOUND/PATH_0008')
ORIGINAL = Path('/PORTABLE_UNBOUND/PATH_0009')
NATIVE_CHECKPOINT = OUT / 'NATIVE-CHECKPOINT-FRESH.json'
MSK = timezone(timedelta(hours=3))
CLOCK = json.loads((OUT / 'CLOCK.json').read_text())
DEADLINE = datetime.fromisoformat(CLOCK['deadline_msk']).timestamp()
PINNED = {str(SOURCE): 'a17caac467eca718ffa87b0aef2a55037914b3e3562bd808c6959c160dbd8365', str(PROVENANCE): 'a905d4e2620388cd26b8aeb6a244d760a4f7dffb1313475328293771584afdb1', str(LIVE_COMPAT): 'e02e2548cd85936be0e59642dabb1d9a7e0155d4a346206144e4b51f21b09ede', str(CANDIDATE): 'b4849ae6e999c869c577288f1acd21fd23015b4c7c4428381e493b39ec2da72a', str(INSTALLED): '20604f9f31c5be9cdc77f8ae88be3348f60b0ed3141d2ae1e47ffe0febd6058f', str(ORIGINAL): 'PORTABLE_UNBOUND_PRIVATE_RECEIPT_SHA256', str(ROOT / 'native-transport-forensic-hardening-r2-review/RESULT.json'): 'aba136ed7e77411f9dfcc9612b3be9c954cd8dcb7c8bea3b3ff139b911853870', str(ROOT / 'native-transport-forensic-hardening-r2-review/RESULT-RECEIVED.json'): 'bdc1e0a57cce6c40a8fe7d85df5673bc090c296b066cf32327579597e407e743', str(NATIVE_CHECKPOINT): 'UNRESOLVED_FRESH_EXACT_NATIVE_CUSTODY_SHA_REQUIRED'}

def now():
    return datetime.now(MSK).isoformat()

def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def write(name, value):
    p = OUT / name
    with p.open('w', encoding='utf8') as f:
        os.chmod(p, 384)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    d = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(d)
    finally:
        os.close(d)

def readproc(pid):
    try:
        s = Path(f'/proc/{pid}/stat').read_text()
        a = s[s.rfind(')') + 2:].split()
        return {'pid': pid, 'ppid': int(a[1]), 'state': a[0], 'start': a[19], 'rss_bytes': int(a[21]) * os.sysconf('SC_PAGE_SIZE'), 'vsize_bytes': int(a[20])}
    except (OSError, ValueError, IndexError):
        return None

def proc_children(pid):
    try:
        return [int(v) for v in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
    except OSError:
        return []

def owned_tree():
    found = {}
    pending = [os.getpid()]
    while pending:
        p = pending.pop()
        if p in found:
            continue
        r = readproc(p)
        if r:
            found[p] = r
            pending.extend(proc_children(p))
    return found

def describe(r):
    p = r['pid']
    v = dict(r)
    try:
        v['cmdline'] = Path(f'/proc/{p}/cmdline').read_bytes().replace(b'\x00', b' ').decode('utf8', 'replace')
        v['exe'] = os.readlink(f'/proc/{p}/exe')
        v['affinity'] = sorted(os.sched_getaffinity(p))
    except OSError:
        pass
    return v

def snapshot(m):
    pins = {p: {'sha256': digest(p), 'mode': oct(stat.S_IMODE(Path(p).lstat().st_mode)), 'bytes': Path(p).stat().st_size} for p in PINNED}
    for p, sha in PINNED.items():
        if pins[p]['sha256'] != sha:
            raise RuntimeError('pinned source changed: ' + p)
    current = m.current_root()
    if current != RELEASE:
        raise RuntimeError('actual selected release differs')
    prov = m.safe_private_receipt(PROVENANCE)
    tree = m.tree_digest(RELEASE)
    expected = {'schema': 'friday.codex-source-provenance.v1', 'version': '0.160.1', 'target': m.TARGET, 'release_root': str(RELEASE), 'source_url': f'https://releases.openai.com/codex/releases/0.160.1/{m.ASSET_NAME}', 'source_archive_sha256': prov['source_archive_sha256'], 'tree_sha256': tree}
    if prov != expected:
        raise RuntimeError('authentic source provenance/full release tree mismatch')
    profiles, roles = m.role_profile_snapshot()
    return {'at_msk': now(), 'pins': pins, 'current_root': str(current), 'provenance': prov, 'tree_sha256': tree, 'binary_sha256': m.sha256_file(m.release_binary(RELEASE)), 'code_mode_host_sha256': m.sha256_file(RELEASE / 'bin/codex-code-mode-host'), 'manifest_sha256': m.sha256_file(RELEASE / 'codex-package.json'), 'account_input_sha256': m.profile_input_hashes(m.SLOTS), 'validation_controls_sha256': m.validation_control_hashes(), 'role_profile_sha256': roles, 'roles': {f'{a}/{b}': str(p) for (a, b), p in profiles.items()}}

def identities(m):
    return {'module_dict_id': id(m.__dict__), 'control_paths_dict_id': id(m.VALIDATION_CONTROL_PATHS), 'function_records': {n: {'id': id(v), 'globals_id': id(v.__globals__), 'globals_are_module_dict': v.__globals__ is m.__dict__, 'code_id': id(v.__code__), 'bytecode_sha256': hashlib.sha256(v.__code__.co_code).hexdigest()} for n, v in vars(m).items() if inspect.isfunction(v) and v.__module__ == m.__name__}, 'control_paths': {n: str(p) for n, p in m.VALIDATION_CONTROL_PATHS.items()}}

def worker():
    ready = worker_ready_barrier()
    os.umask(63)
    lock_path = Path('/PORTABLE_UNBOUND/PATH_0010')
    lock_fd = None
    m = None
    before = None
    started = now()
    verdict = 'FAIL'
    error = None
    called = 0
    events = None
    receipt = None
    try:
        if time.time() >= DEADLINE:
            raise RuntimeError('original parent CLOCK exhausted before invocation')
        info = lock_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 18:
            raise RuntimeError('unsafe existing updater lock')
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.fstat(lock_fd).st_ino != info.st_ino:
            raise RuntimeError('updater lock identity changed')
        if digest(SOURCE) != PINNED[str(SOURCE)]:
            raise RuntimeError('updater source mismatch before import')
        b = source_boundary()
        host = b.require_host_custody()
        with b.VerifiedBytes(SOURCE, PINNED[str(SOURCE)], max_bytes=128 * 1024 ** 2) as source:
            m = types.ModuleType('friday_exact_staged_validator')
            m.__file__ = str(SOURCE)
            sys.modules[m.__name__] = m
            host.verify_import_graph_and_environment()
            b.execute_verified(source, m.__dict__)
        original_ids = identities(m)
        original_functions = {n: v for n, v in vars(m).items() if inspect.isfunction(v) and v.__module__ == m.__name__}
        original_codes = {n: v.__code__ for n, v in original_functions.items()}

        def assert_functions_original():
            if not all((getattr(m, n) is v and v.__code__ is original_codes[n] and (v.__globals__ is m.__dict__) for n, v in original_functions.items())):
                raise RuntimeError('actual validator function/code/global identity replaced')
        before = snapshot(m)
        write('INPUT-SNAPSHOT-BEFORE.json', before)
        actual_settings = {slot: {k: tomllib.loads((home / 'config.toml').read_text()).get(k) for k in ('model', 'model_reasoning_effort', 'service_tier', 'model_provider')} for slot, home in m.SLOTS.items()}
        native = json.loads(NATIVE_CHECKPOINT.read_text())
        write('ACTUAL-INPUT-DISTINCTION.json', {'clone_default_inputs': actual_settings, 'actual_native_thread_settings_evidence': {'path': str(NATIVE_CHECKPOINT), 'sha256': PINNED[str(NATIVE_CHECKPOINT)], 'slots': native['slots']}, 'runtime_API_calls_here': 0, 'clone_defaults_do_not_assert_thread_overrides': True, 'reconnect_ASTRA_MODEL': 'gpt-6-astra', 'reconnect_resume_probe_is_parser_help_only': True, 'live_profile_repair': False})
        m.RUNTIME = OUT / 'runtime'
        m.RUNTIME.mkdir(mode=448, exist_ok=True)
        m.VALIDATED = OUT / 'validated'
        m.VALIDATION_CONTROL_PATHS['native_send'] = CANDIDATE
        redirected_ids = identities(m)
        assert_functions_original()
        if not (original_ids['module_dict_id'] == redirected_ids['module_dict_id'] and original_ids['control_paths_dict_id'] == redirected_ids['control_paths_dict_id']):
            raise RuntimeError('EXPLICIT_BOUNDARY_ADMISSION_FAILED')
        for label, p in original_ids['control_paths'].items():
            if not redirected_ids['control_paths'][label] == (str(CANDIDATE) if label == 'native_send' else p):
                raise RuntimeError('EXPLICIT_BOUNDARY_ADMISSION_FAILED')
        staged_controls = m.validation_control_hashes()
        if not staged_controls == {**before['validation_controls_sha256'], 'native_send': PINNED[str(CANDIDATE)]}:
            raise RuntimeError('EXPLICIT_BOUNDARY_ADMISSION_FAILED')
        write('VALIDATOR-IDENTITIES-BEFORE.json', {'original': original_ids, 'staged': redirected_ids, 'runtime': str(m.RUNTIME), 'validated': str(m.VALIDATED), 'staged_controls_sha256': staged_controls, 'no_function_replacement': True})
        events = (OUT / 'EXECUTION-EVIDENCE.jsonl').open('w', encoding='utf8')
        os.chmod(OUT / 'EXECUTION-EVIDENCE.jsonl', 384)
        watched = {'validate_candidate', 'run', 'require_success', 'clone_config_home', 'strict_protocol_probe', 'role_profile_snapshot', 'role_profile_probes', 'validate_rpc_contract', 'isolated_remote_rpc_probe', 'resolve_control_socket', 'slot_state', 'ensure_path', 'build_resume_command', 'atomic_private_json'}
        event_counter = 0

        def serial(v):
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, subprocess.CompletedProcess):
                return {'args': v.args, 'returncode': v.returncode, 'stdout': v.stdout, 'stderr': v.stderr}
            if isinstance(v, subprocess.Popen):
                return {'pid': v.pid, 'args': v.args, 'returncode': v.returncode}
            if isinstance(v, bytes):
                return v.decode('utf8', 'replace')
            if isinstance(v, set):
                return sorted(v)
            if isinstance(v, tuple):
                return [serial(a) for a in v]
            if isinstance(v, dict):
                return {str(k): serial(a) for k, a in v.items()}
            if isinstance(v, list):
                return [serial(a) for a in v]
            if v is None or isinstance(v, (str, int, float, bool)):
                return v
            return type(v).__name__

        def emit(e):
            nonlocal event_counter
            event_counter += 1
            e['event_seq'] = event_counter
            e['at_msk'] = now()
            events.write(json.dumps(serial(e), ensure_ascii=False, separators=(',', ':')) + '\n')
            events.flush()

        def profile(frame, event, arg):
            filename = frame.f_code.co_filename
            name = frame.f_code.co_name
            if filename == subprocess.__file__ and name == '__init__' and (event == 'return'):
                obj = frame.f_locals.get('self')
                if isinstance(obj, subprocess.Popen):
                    emit({'kind': 'subprocess_created', 'process': serial(obj), 'proc': readproc(obj.pid)})
                return
            if name not in watched or not (filename == str(SOURCE) or filename.startswith('/PORTABLE_UNBOUND/PATH_0011')):
                return
            l = frame.f_locals
            keys = ['root', 'version', 'source_digest', 'source_url', 'source_tree_digest', 'command', 'timeout', 'cwd', 'label', 'clone', 'home', 'prefix', 'slot', 'thread', 'endpoint', 'expected_home', 'schema_path', 'path', 'exact_argv', 'responses', 'stdout_buffer', 'stderr_buffer', 'process', 'topology', 'listener', 'smoke', 'stopped']
            details = {k: serial(l[k]) for k in keys if k in l}
            if isinstance(l.get('env'), dict):
                details['env_CODEX_HOME'] = l['env'].get('CODEX_HOME')
            if event == 'call' and name == 'strict_protocol_probe':
                c = l['clone']
                cfg = tomllib.loads((c / 'config.toml').read_text())
                details['actual_clone_config_sha256'] = digest(c / 'config.toml')
                details['actual_clone_defaults'] = {k: cfg.get(k) for k in ('model', 'model_reasoning_effort', 'service_tier', 'model_provider')}
                if str(c).startswith('/var/tmp/friday-astra-config-'):
                    if not details['actual_clone_config_sha256'] == before['account_input_sha256']['astra/config.toml']:
                        raise RuntimeError('profile helper changed actual config inputs')
            if event == 'return':
                details['return'] = serial(arg)
                if name == 'resolve_control_socket' and isinstance(arg, Path):
                    try:
                        st = arg.lstat()
                        details['socket_identity'] = {'path': str(arg), 'inode': st.st_ino, 'uid': st.st_uid, 'mode': oct(stat.S_IMODE(st.st_mode)), 'is_socket': stat.S_ISSOCK(st.st_mode), 'proc_net_unix_matches': [a for a in Path('/proc/net/unix').read_text().splitlines() if a.endswith(' ' + str(arg))]}
                    except OSError as e:
                        details['socket_identity_error'] = str(e)
            if event in ('call', 'return'):
                emit({'kind': event, 'function': name, 'source': filename, 'line': frame.f_lineno, 'details': details})
        sys.setprofile(profile)
        called += 1
        checks = m.validate_candidate(RELEASE, '0.160.1', source_digest=before['provenance']['source_archive_sha256'], source_url=before['provenance']['source_url'], source_tree_digest=before['tree_sha256'])
        sys.setprofile(None)
        events.flush()
        os.fsync(events.fileno())
        events.close()
        events = None
        receipt = m.VALIDATED / '0.160.1.json'
        generated = m.safe_private_receipt(receipt)
        if not generated == checks:
            raise RuntimeError('validator-generated receipt changed')
        if not generated['validation_controls_sha256'] == staged_controls:
            raise RuntimeError('EXPLICIT_BOUNDARY_ADMISSION_FAILED')
        if not generated['account_input_sha256'] == before['account_input_sha256']:
            raise RuntimeError('clone inputs differ from actual pinned accounts')
        assert_functions_original()
        post_ids = identities(m)
        if not (post_ids['module_dict_id'] == redirected_ids['module_dict_id'] and post_ids['control_paths_dict_id'] == redirected_ids['control_paths_dict_id'] and (post_ids['control_paths'] == redirected_ids['control_paths'])):
            raise RuntimeError('validator identity drift')
        write('VALIDATOR-IDENTITIES-AFTER.json', post_ids)
        m.VALIDATION_CONTROL_PATHS['native_send'] = INSTALLED
        after = snapshot(m)
        write('INPUT-SNAPSHOT-AFTER.json', after)
        comparable = lambda j: {k: v for k, v in j.items() if k != 'at_msk'}
        if not comparable(before) == comparable(after):
            raise RuntimeError('actual source/control/account input drift')
        verdict = 'PASS'
    except BaseException as e:
        sys.setprofile(None)
        error = {'type': type(e).__name__, 'message': str(e), 'traceback': traceback.format_exc()}
    finally:
        if events:
            events.flush()
            os.fsync(events.fileno())
            events.close()
        if m and before and (verdict != 'PASS'):
            try:
                m.VALIDATION_CONTROL_PATHS['native_send'] = INSTALLED
                after = snapshot(m)
                write('INPUT-SNAPSHOT-AFTER.json', after)
            except BaseException as e:
                write('AFTER-SNAPSHOT-ERROR.json', {'type': type(e).__name__, 'message': str(e)})
        if lock_fd is not None:
            os.close(lock_fd)
        ended = now()
        write('VALIDATOR-RESULT.json', {'schema': 'friday.exact-staged-validator-run.v1', 'assignment': CLOCK['assignment'], 'generation': 1, 'verdict': verdict, 'actual_validate_candidate_calls': called, 'validator_started_msk': started, 'validator_finished_msk': ended, 'actual_finish_unix': time.time(), 'ready_binding': ready, 'run_token': source_boundary().require_host_custody().run_token, 'receipt': str(receipt) if receipt else None, 'receipt_sha256': digest(receipt) if receipt and receipt.exists() else None, 'error': error, 'installation': False, 'peer_settlement': False, 'Friday_runtime_acceptance': False, 'actual_live_native_calls': 0, 'original_parent_clock': CLOCK})
    return 0 if verdict == 'PASS' else 1

def source_boundary():
    b = globals().get('__verified_source_boundary__')
    if b is None:
        raise RuntimeError('HOST_VERIFIED_INTERPRETER_IMPORT_ENV_CUSTODY_REQUIRED')
    b.require_host_custody()
    return b

def worker_ready_barrier():
    b = source_boundary()
    host = b.require_host_custody()
    ready = host.actual_worker_ready_before_go(readproc(os.getpid()), sorted(os.sched_getaffinity(0)))
    host.wait_verified_go_with_original_deadline(ready, CLOCK)
    return ready

def supervisor():
    b = source_boundary()
    host = b.require_host_custody()
    clock = host.validate_original_clock(CLOCK, original_seconds=1200, cleanup_seconds=120)
    hard_end = min(clock['final_deadline_unix'], host.parent_final_deadline_unix)
    useful_end = min(clock['useful_deadline_unix'], host.parent_useful_deadline_unix)
    if time.time() >= useful_end:
        raise RuntimeError('ORIGINAL_USEFUL_DEADLINE_EXHAUSTED')
    identities_seen = {}
    child = None
    ready = None
    launch_custody = None
    ready_admitted = False
    resource_stop = None
    peak = 0
    samples = 0
    with b.VerifiedBytes(Path(__file__), host.staged_validator_sha256, mode=320) as source:
        try:
            child = host.launch_verified_source_held(source, None, ['--worker'], OUT, host.run_token, None, None)
            launch_custody = b.LaunchCustody(child)
            ready = host.validate_actual_ready(child, host.run_token, source.identity, None, host.reserved_root_identity)
            launch_custody.bind_ready(ready)
            ready_admitted = True
            host.verify_aggregate_hard_resources(2, 1024 ** 3)
            write('PREBARRIER-READY.json', ready)
            host.verify_ready_and_resources_before_go(ready, clock)
            source.verify()
            host.release_exact_held_child(child, ready)
            while child.poll() is None:
                rows = host.current_exact_owned_tree(child, ready)
                for r in rows.values():
                    identities_seen[f"{r['pid']}:{r['start']}"] = describe(r)
                rss = sum((r['rss_bytes'] for r in rows.values()))
                peak = max(peak, rss)
                samples += 1
                host.verify_aggregate_hard_resources(2, 1024 ** 3)
                if rss > 1024 ** 3:
                    resource_stop = {'reason': 'aggregate_RSS_over_budget'}
                    break
                if time.time() >= useful_end:
                    resource_stop = {'reason': 'original120_cleanup_reserve'}
                    break
                time.sleep(0.025)
            if not resource_stop:
                child.wait(timeout=max(0.001, hard_end - time.time()))
        finally:
            try:
                if child is not None:
                    closure = b.cleanup_returned_child(host, child, launch_custody,
                        primary=sys.exc_info()[1], hard_deadline=hard_end)
                else:
                    closure = {'closed': False, 'prebarrier_unstarted': True}
            finally:
                if launch_custody is not None:launch_custody.close()
    validated, receipt = host.read_fresh_result_and_genuine_receipt(OUT, ready, CLOCK)
    finished = time.time()
    observation = {'actual_exit0': type(child.returncode) is int and child.returncode == 0, 'worker_returncode': child.returncode, 'worker_reaped': closure.get('worker_reaped') is True, 'ready_validated': ready is not None, 'inventory_before_go': host.inventory_before_go is True, 'pid_birth_validated': host.pid_birth_validated is True, 'host_custody_admitted': True, 'affinity_validated': host.all_actual_affinities_within_budget is True, 'resources_within_budget': host.hard_resource_boundary_validated is True and peak <= 1024 ** 3, 'useful_deadline_met': validated['actual_finish_unix'] <= useful_end, 'final_deadline_met': finished <= hard_end, 'cleanup_within_original120': b.finite_cleanup_within_original120(closure.get('cleanup_elapsed_seconds')), 'process_closure_closed': closure.get('closed') is True, 'fresh_receipt_validated': receipt is not None, 'fresh_result_validated': validated.get('fresh_binding_validated') is True, 'exact_final_process_absence': closure.get('process_absence') is True, 'exact_final_path_absence': closure.get('path_absence') is True, 'exact_final_endpoint_absence': closure.get('endpoint_absence') is True, 'validator_verdict': validated.get('verdict'), 'resource_stop': resource_stop, 'cleanup_escalation_needed': closure.get('escalation_needed')}
    result = {'schema': 'friday.native-send.r2-staged-compatibility.v2', 'assignment': CLOCK['assignment'], 'generation': CLOCK['generation'], 'verdict': 'PASS' if b.compatibility_pass(observation) else 'FAIL', 'status': 'COMPATIBILITY_PREPARATION_ONLY', 'actual_observation': observation, 'validator': validated, 'fresh_receipt_ref': receipt, 'process_closure': closure, 'peak_RSS_bytes': peak, 'samples': samples, 'original_parent_clock': CLOCK, 'finished_msk': now(), 'installed': False, 'activated': False, 'peer_settlement': False, 'Friday_runtime_acceptance': False, 'original_unknown_preserved': True}
    write('RESULT.json', result)
    return 0 if result['verdict'] == 'PASS' else 1
if __name__ == '__main__':
    sys.exit(worker() if '--worker' in sys.argv else supervisor())
