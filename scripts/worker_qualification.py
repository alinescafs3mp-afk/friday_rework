"""One ordinary installed deployment transition, never per-job authority.

The host invokes fixed native observers against an already owned A0 probe.
No caller-supplied readiness report, capability, start or installation is used.
Original preparation and the original install deadline remain immutable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time

from scripts.friday_install import digest, owned_file, pin, publish, read_json, require

FOLDER = 'preparation/worker-qualification'
PROOF = FOLDER + '/observation.json'
ORIGINAL = FOLDER + '/original.json'

# A scope moves this already owned foreground PID into native resource control;
# unlike a service it cannot execute a queued command after this client dies.
# The fixed guard checks the effective cgroup before exec of the existing PID
# namespace. Its descriptor custody and original timeout remain with run().
DSH_SCOPE_GUARD = '''import json,os,sys,time
from pathlib import Path
p=json.loads(sys.argv[1])
assert time.monotonic()<p['deadline']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==p['boot_id']
line=Path('/proc/self/cgroup').read_text().strip()
assert line.startswith('0::/') and '\\n' not in line
group=line[3:]; assert group.endswith('/'+p['unit'])
root=Path('/sys/fs/cgroup')/group.lstrip('/')
assert root.resolve()==root
caps={k:(root/k).read_text().strip() for k in ('memory.max','memory.swap.max','cpu.max','pids.max')}
assert caps['memory.max']==str(p['memory_bytes']) and caps['memory.swap.max']=='0'
assert caps['pids.max']==str(p['tasks'])
q,t=caps['cpu.max'].split()
assert q.isdecimal() and t.isdecimal() and int(t)>0 and int(q)*100==p['cpu_percent']*int(t)
assert time.monotonic()<p['deadline']
os.execve(sys.argv[2],sys.argv[2:],dict(os.environ))
'''


def original(home, marker):
    """Check the archived pending inventory; never substitute expected hashes."""
    ref = marker.get('worker_qualification')
    require(isinstance(ref, dict) and ref.get('path') == str(home / PROOF),
            'ordinary_worker_qualification_missing')
    pin(ref)
    proof = read_json(home / PROOF)
    require(proof.get('schema') == 'friday.worker-deployment-observation.v1'
            and proof.get('home') == str(home) and proof.get('effects') == 'OBSERVATION_ONLY'
            and proof.get('per_job_authority') == 'NOT_GRANTED'
            and set(proof.get('workers', {})) == {'dsh', 'a0'}, 'worker_observation_not_bound')
    observed = proof['observed']
    require(observed['boot_id'] == marker['original_attempt']['boot_id']
            and type(observed['monotonic']) in (int,float)
            and 0 < observed['monotonic'] <= marker['original_attempt']['deadline_mono'],
            'qualification_original_observation_clock_changed')
    archive = proof['original']
    require(archive['path'] == str(home / ORIGINAL), 'foreign_original_install_archive')
    pin(archive)
    before = read_json(home / ORIGINAL)
    require(before['marker']['original_attempt'] == marker['original_attempt']
            and before['marker']['home'] == str(home)
            and before['marker']['input_sha256'] == marker['input_sha256']
            and before['marker']['worker_state'] == 'BOTH_CONFIGURED_QUALIFICATION_PENDING',
            'original_install_ownership_changed')
    expected = {name: sha for name, sha in before['marker']['profile_files'].items()}
    expected.update({name: sha for name, sha in before['marker']['worker_files'].items()
                     if name.endswith('/runtime-receipt.json')})
    require(before['files'] == expected, 'original_preparation_archive_incomplete')
    for name, sha in expected.items():
        require(digest(owned_file(home / FOLDER / 'original' / name, private=True)) == sha,
                'original_preparation_archive_changed')
    # All original worker inputs/preparation stay at their original paths.
    for name, sha in before['marker']['worker_files'].items():
        if not name.endswith('/runtime-receipt.json'):
            require(digest(owned_file(home / name, private=True)) == sha,
                    'original_worker_input_changed')
    return proof, before['marker']


def original_receipt(home, worker, runtime, marker):
    if marker.get('worker_state') == 'BOTH_DEPLOYMENTS_QUALIFIED':
        original(home, marker)
        path = home / FOLDER / 'original/workers' / worker / 'runtime-receipt.json'
    else:
        path = Path(runtime['runtime_receipt']['path'])
    raw = owned_file(path, private=True)
    require(digest(raw) == runtime['runtime_receipt']['sha256'], 'original_pending_receipt_changed')
    return json.loads(raw)


def checked_product(value, home, product, marker):
    """Qualified receipts must match the single bound observation transaction."""
    proof, before = original(home, marker)
    require(proof['input_sha256'] == marker['input_sha256']
            and proof['profile'] == product['profile'], 'foreign_worker_qualification')
    from plugins.friday_rework.host_record import digest as record_digest
    for worker, runtime in product['runtime']['workers'].items():
        observation = proof['workers'][worker]
        require(observation['runtime_sha256'] == record_digest(
                    {k:v for k,v in runtime.items() if k != 'runtime_receipt'}),
                'qualified_runtime_changed')
        pending = original_receipt(home, worker, runtime, marker)
        expected = dict(pending, ready=True, evidence=[*pending['evidence'], marker['worker_qualification']])
        path = home / 'workers' / worker / 'runtime-receipt.json'
        require(read_json(path) == expected, 'qualified_worker_receipt_changed')
        runtime['runtime_receipt'] = {'path': str(path), 'sha256': digest(owned_file(path, private=True))}
        pin(runtime['runtime_receipt'])
    # Public bootstrap inspection stays dependency-free. Native startup checks
    # the effective config/runtime against this exact returned package before
    # any launch. Static identity remains the original immutable generation.
    require(all(marker['profile_files'][name] == before['profile_files'][name]
                for name in ('SOUL.md','FRIDAY-PROFILE.json')), 'qualified_identity_changed')
    for name in ('.env', 'auth.json'):
        path = home / name
        sha = digest(owned_file(path, private=True)) if path.exists() or path.is_symlink() else None
        require(proof['credentials'][name] == sha, 'qualified_credential_store_changed')
    from plugins.friday_rework.host_runtime import deployment_health
    for runtime in product['runtime']['workers'].values(): deployment_health(runtime)
    return product


def a0_observe(runtime, plan_ref, budget):
    """Observe an existing exact native plan; no create/start/route or grant."""
    from plugins.friday_rework.host_runtime import a0_runtime_module, a0_deployment_contract
    a0_deployment_contract(runtime)
    native = runtime['a0']; pin(plan_ref)
    m = a0_runtime_module(runtime)
    plan = budget.call(m.validate, read_json(plan_ref['path']), budget=budget.check)
    require(plan['owner_slot'] == native['owner_slot'] and plan['mode'] == 'runtime'
            and plan.get('deployment') == native['deployment'] and plan.get('web') == native['web']
            and plan.get('git_metadata') == native['git_metadata']
            and plan['code_sha256'] == native['runtime']['sha256']
            and plan['docker_sha256'] == native['docker']['sha256']
            and plan['daemon_unit_sha256'] == native['daemon_unit']['sha256']
            and str(m.LAUNCHER) == native['launcher']['path']
            and str(m.DOCKER) == native['docker']['path']
            and str(m.PROJECT / '.runtime/rootless-docker/supervisor' / m.DAEMON) == native['daemon_unit']['path']
            and plan['network'] != 'none'
            and plan['network']['launcher_sha256'] == native['launcher']['sha256']
            and plan['network']['policy_sha256'] == native['policy']['sha256'],
            'foreign_a0_qualification_plan')
    if 'association_binding' in plan:
        row = plan['association_binding']
        require(row['owner']['profile'] == runtime['runtime_profile']
                and Path(row['workspace_reference']).is_relative_to(Path(runtime['workspace_root'])),
                'foreign_a0_qualification_home')
    m.remaining(plan)
    boundary = budget.call(m.Runtime, plan, budget=budget.check)
    # Exact recorded native ID, pinned plan, live supervisor and current route.
    # Read-only probes use the existing bounded control runner and native locks.
    with boundary.locked():
        receipt = boundary.receipt()
        obj = budget.call(boundary.inspect, receipt, timeout=min(5, budget.check()))
        unit = budget.call(boundary.supervisor.observe, boundary.association(receipt))
        require(obj['State']['Running'] and obj['State']['Pid'] > 0
                and not unit.missing and not unit.quiescent
                and unit.invocation_id == receipt.get('invocation_id'), 'current_a0_probe_not_running')
    try:
        probe = budget.call(boundary.probe)
        sample = budget.call(boundary.observe)
    except m.RuntimeStopUnconfirmed as exc:
        # Native cleanup uncertainty is a typed custody condition, never an
        # ordinary refusal merely because the observer process can exit.
        from scripts.dsh_prepare import StopUnconfirmed
        raise StopUnconfirmed('A0 qualification cessation unconfirmed') from exc
    require(sample['running'] and not sample['unit_quiescent'] and sample.get('caps') is not None,
            'current_a0_native_resources_required')
    web = budget.call(boundary.check_web, receipt['container_id'])
    require(web is not None, 'current_a0_web_observation_required')
    route = budget.call(boundary.check_network, container_id=receipt['container_id'], budget=budget.check)
    # Repeat identity after probe execution; a replaced worker cannot qualify.
    with boundary.locked():
        after = boundary.receipt()
        budget.call(boundary.inspect, after, timeout=min(5, budget.check()))
        current = budget.call(boundary.supervisor.observe, boundary.association(after))
        require(after['container_id'] == receipt['container_id']
                and current.invocation_id == unit.invocation_id and not current.quiescent,
                'a0_probe_replaced_during_qualification')
    m.remaining(plan); pin(plan_ref)
    return {'plan': plan_ref, 'container_id': receipt['container_id'],
            'invocation_id': unit.invocation_id, 'native_probe': probe, 'web': web, 'route': route,
            'native_resources':sample}


def dsh_observe(runtime, home, folder, budget):
    """No-model smoke and DNS/TLS inside the actual native adapter boundary."""
    from plugins.friday_rework.adapters.dsh import DshAdapter, DshHostConfig
    from plugins.friday_rework.host_runtime import _pin, _dsh_web
    from plugins.friday_rework.worker_web import web_policy, DSH_NETWORK_PROBE, checked_network_observation
    from scripts.install_containment import namespace_exit, checked_binary
    from scripts.dsh_prepare import run, StopUnconfirmed
    d = runtime['dsh']; web = _dsh_web(d)
    require(web is not None, 'mandatory_dsh_web_required')
    web.checked_patch(_pin(d['patch']).read())
    policy = web_policy(web, str(home), runtime['runtime_profile'], time.time())
    st = Path('/proc/self/ns/net').stat()
    identity = (Path('/proc/sys/kernel/random/boot_id').read_text().strip(), [st.st_dev, st.st_ino])
    require(identity == (policy['boot_id'], policy['net_namespace']), 'dsh_web_namespace_changed')
    for name in ('home', 'workspace', 'inputs'): (folder / name).mkdir(mode=0o700)
    # Same adapter mounts/bootstrap layout, explicitly without any credential.
    for name, raw in {'web-ca.pem': web.trust_bundle.read(), 'web-network.mjs': DSH_NETWORK_PROBE.encode(),
        'bootstrap.py': ('import os,sys\nenv={"PATH":sys.argv[1]+":/usr/bin:/bin","HOME":"/job-home",'
            '"DSH_HOME":"/job-home/dsh","LANG":"C.UTF-8","DSH_TELEMETRY_DISABLED":"1",'
            '"NODE_EXTRA_CA_CERTS":"/job-input/web-ca.pem"}\nos.execve(sys.argv[2],sys.argv[2:],env)\n').encode()}.items():
        path = folder / 'inputs' / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    cfg = DshHostConfig(workspace_root=Path(runtime['workspace_root']), payload_root=Path(d['payload_root']),
        toolchain_root=Path(d['toolchain_root']), node=_pin(d['node']), cli=_pin(d['cli']), patch=_pin(d['patch']),
        native_files=tuple(_pin(p) for p in d['native_files']), environment=lambda: {},
        current_association=lambda row: None, key_name=d['key_name'], web=web,
        **{k:d[k] for k in ('profile','memory_bytes','cpu_percent','tasks','shutdown_seconds','tmp_bytes')})
    adapter = DshAdapter(cfg)
    adapter._pins()
    count = 0
    def observe(command):
        nonlocal count
        count += 1
        budget.check(reserve=1)
        r, w = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        observation = {}; failure = None; output = ''
        try:
            argv = adapter._boundary(folder, command)
            argv[1:1] = ['--json-status-fd', str(w), '--as-pid-1']
            limit = min(5, budget.check(reserve=1))
            envelope = {'unit': 'friday-qualify-dsh-' + hashlib.sha256(str(folder).encode()).hexdigest()[:24]
                         + '-' + str(count) + '.scope',
                        'memory_bytes': cfg.memory_bytes, 'cpu_percent': cfg.cpu_percent, 'tasks': cfg.tasks,
                        'boot_id': identity[0], 'deadline': min(budget.deadline - 1, time.monotonic() + limit)}
            argv = ['/usr/bin/systemd-run', '--user', '--scope', '--quiet', '--no-ask-password',
                    '--expand-environment=no', '--unit=' + envelope['unit'],
                    '--property=MemoryMax=' + str(cfg.memory_bytes), '--property=MemorySwapMax=0',
                    '--property=CPUQuota=' + str(cfg.cpu_percent) + '%',
                    '--property=TasksMax=' + str(cfg.tasks), '--property=KillMode=control-group',
                    '--property=SendSIGKILL=yes', '--property=RuntimeMaxSec=' + str(limit) + 's',
                    '/usr/bin/python3', '-I', '-c', DSH_SCOPE_GUARD, json.dumps(envelope), *argv]
            try:
                output, observation = run(argv, folder, env=adapter._environment(),
                    timeout=limit, deadline=budget.deadline, pass_fds=(w,))
            except BaseException as exc:
                failure = exc; observation = getattr(exc, 'observation', {})
            os.close(w); w = None
            try: status = os.read(r, 4097)
            except BlockingIOError: status = b''
            if not namespace_exit(status, observation):
                raise StopUnconfirmed('qualification namespace cessation unconfirmed') from failure
            if failure: raise failure
            budget.check()
            observation['resource_envelope'] = envelope
            return output, observation
        finally:
            if w is not None: os.close(w)
            os.close(r)
    smoke = []
    for kind, args in [('version', ['--version']), ('help', ['--help']),
                       ('headless-config', ['--profile','headless','--dump-default-config']),
                       ('headless-help', ['--profile','headless','--help'])]:
        _, observed = observe([str(cfg.node.path), str(cfg.cli.path), *args])
        smoke.append({'kind': kind, 'observation': observed})
    urls = [('https://mcp.exa.ai/' if web.profile == 'exa-keyless' else 'https://api.exa.ai/'), *policy['document_probes']]
    out, network_execution = observe([str(cfg.node.path), '/job-input/web-network.mjs', json.dumps(urls)])
    network = checked_network_observation(out, urls)
    adapter._pins()
    st = Path('/proc/self/ns/net').stat()
    require(identity == (Path('/proc/sys/kernel/random/boot_id').read_text().strip(), [st.st_dev,st.st_ino])
            and policy == web_policy(web,str(home),runtime['runtime_profile'],time.time()),
            'dsh_web_changed_during_qualification')
    return {'smoke': smoke, 'network': network, 'network_execution': network_execution,
            'policy_sha256': web.egress_evidence.sha256}


def qualify(value, input_hash, plan_ref, budget):
    """Archive first, observe once, publish profile then commit marker last.

    Interrupted publication is fail-closed and cannot be automatically replayed.
    The existing config write transaction is held through observation/publication.
    The native A0 probe remains under its original owner, not this installer.
    """
    from scripts.friday_install import inspect, MARKER, directory
    from scripts.dsh_prepare import StopUnconfirmed
    from scripts.worker_install import installed_product
    from hermes_constants import get_hermes_home
    from hermes_cli.config import config_write_transaction, atomic_config_write
    from tools.configure_product import compose_product
    home = Path(value['home'])
    require(get_hermes_home() == home and 'worker_install' in value, 'ordinary_native_qualification_required')
    budget.call(inspect, value, input_hash)
    marker = read_json(home / MARKER)
    require(marker.get('worker_state') == 'BOTH_CONFIGURED_QUALIFICATION_PENDING', 'worker_transition_not_pending')
    claim = marker['original_attempt']
    require(claim['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and budget.deadline == claim['deadline_mono'], 'original_qualification_clock_required')
    folder = home / FOLDER
    require(not folder.exists() and not folder.is_symlink(), 'partial_qualification_requires_reconciliation')
    product = budget.call(installed_product, value, home)
    with config_write_transaction(home / 'config.yaml'):
        # No live probes before the unchanged installed ownership is checked.
        budget.call(inspect, value, input_hash)
        folder.mkdir(mode=0o700); directory(folder)
        files = dict(marker['profile_files'])
        files.update({p:h for p,h in marker['worker_files'].items() if p.endswith('/runtime-receipt.json')})
        for name, sha in files.items():
            target = folder / 'original' / name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw = budget.call(owned_file, home / name, private=True)
            require(digest(raw) == sha, 'original_qualification_input_changed')
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(fd, 'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        publish(home / ORIGINAL, {'marker': marker, 'files': files}, budget=budget)
        credentials = {name: digest(owned_file(home / name, private=True))
            if (home / name).exists() or (home / name).is_symlink() else None for name in ('.env','auth.json')}
        scratch = folder / 'dsh-probe'; scratch.mkdir(mode=0o700)
        dsh = budget.call(dsh_observe, product['runtime']['workers']['dsh'], home, scratch, budget)
        try:
            a0 = budget.call(a0_observe, product['runtime']['workers']['a0'], plan_ref, budget)
        except StopUnconfirmed:
            # This finite private record grants no retry or fresh cleanup time.
            # Preserve the typed condition even if evidence storage fails.
            try:
                publish(folder / 'failure.json', {'state': 'STOP_UNCONFIRMED',
                    'original_attempt': claim, 'plan': plan_ref, 'retry_authorized': False})
            except (OSError, ValueError, RuntimeError):
                pass
            raise
        # Observations cannot conceal a source/config/credential change.
        budget.call(inspect, value, input_hash)
        require(credentials == {name: digest(owned_file(home / name, private=True))
            if (home / name).exists() or (home / name).is_symlink() else None for name in credentials},
            'qualification_credentials_changed')
        from plugins.friday_rework.host_record import digest as record_digest
        observed = {'dsh': dsh, 'a0': a0}
        for kind, runtime in product['runtime']['workers'].items():
            observed[kind]['runtime_sha256'] = record_digest({k:v for k,v in runtime.items() if k != 'runtime_receipt'})
        proof = {'schema':'friday.worker-deployment-observation.v1','home':str(home), 'profile':product['profile'],
            'input_sha256':input_hash,'original':{'path':str(home / ORIGINAL),'sha256':digest(owned_file(home / ORIGINAL,private=True))},
            'workers':observed,'credentials':credentials,'effects':'OBSERVATION_ONLY','per_job_authority':'NOT_GRANTED',
            'observed':{'boot_id':claim['boot_id'],'monotonic':time.monotonic(),'unix':time.time()}}
        publish(home / PROOF, proof, budget=budget)
        ref = {'path':str(home / PROOF),'sha256':digest(owned_file(home / PROOF,private=True))}
        for kind, runtime in product['runtime']['workers'].items():
            path = Path(runtime['runtime_receipt']['path']); pending = read_json(path)
            staged = folder / (kind + '-receipt.json')
            publish(staged, dict(pending,ready=True,evidence=[*pending['evidence'],ref]), budget=budget)
            budget.call(os.replace, staged, path)
            runtime['runtime_receipt']['sha256'] = digest(owned_file(path,private=True))
        bundle = compose_product(product)
        # Write only the runtime-dependent config. Friday identity remains exact.
        require(owned_file(home / 'SOUL.md',private=True) == bundle['soul'].encode()
                and read_json(home / 'FRIDAY-PROFILE.json') == bundle['contract'], 'qualification_identity_changed')
        budget.call(atomic_config_write, home / 'config.yaml', bundle['config'])
        final = copy.deepcopy(marker)
        final['worker_state'] = 'BOTH_DEPLOYMENTS_QUALIFIED'
        final['worker_qualification'] = ref
        final['profile_files']['config.yaml'] = digest(owned_file(home / 'config.yaml',private=True))
        final['worker_files'] = {name: digest(owned_file(home / name,private=True)) for name in marker['worker_files']}
        staged = folder / 'installed.json'; publish(staged,final,budget=budget)
        budget.call(os.replace, staged, home / MARKER)
        fd = os.open(home,os.O_RDONLY | os.O_DIRECTORY)
        try: budget.call(os.fsync,fd)
        finally: os.close(fd)
        budget.call(inspect,value,input_hash)
    return {'state':'DEPLOYMENTS_QUALIFIED','ready':False,'per_job_authority':'NOT_GRANTED',
            'live_journeys':'NOT_RUN','a0_probe_cleanup':'ORIGINAL_NATIVE_OWNER'}
