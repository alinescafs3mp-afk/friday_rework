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


def a0_observe(runtime, plan_ref, budget, *, probe_owner=None):
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
    if probe_owner is not None:
        budget.call(probe_owner.track_runtime, boundary)
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


DSH_NATIVE_SAFETY = r'''const fs=await import('node:fs'),assert=(await import('node:assert/strict')).default;
const {pathToFileURL}=await import('node:url');
const m=JSON.parse(fs.readFileSync('/job-input/manifest.json','utf8'));
const host=JSON.parse(fs.readFileSync('/job-input/host.json','utf8'));
assert.equal(process.execPath,m.node);
const label=fs.readFileSync('/proc/self/attr/current','utf8').trim();
assert.equal(label,'friday-dsh-native-v1 (enforce)','initial attachment must have no unconfined/global bwrap stack');
const status=fs.readFileSync('/proc/self/status','utf8');
assert.match(status,/^NoNewPrivs:\s+1$/m);
for(const k of ['CapInh','CapPrm','CapEff','CapAmb'])assert.match(status,new RegExp('^'+k+':\\s+0+$','m'));
const outer={label,status:status.split('\n').filter(x=>/^(Cap|NoNewPrivs|NSpid|Uid|Gid)/.test(x)),
 uid_map:fs.readFileSync('/proc/self/uid_map','utf8'),gid_map:fs.readFileSync('/proc/self/gid_map','utf8'),
 ns:Object.fromEntries(['user','pid','mnt'].map(k=>[k,fs.readlinkSync('/proc/self/ns/'+k)]))};
assert(Number.isSafeInteger(host.pid) && host.pid>1);
for(const key of ['user','pid','mnt']) {
 assert.equal(typeof host.namespaces[key],'string');
 assert.notEqual(outer.ns[key],host.namespaces[key]);
}
assert.equal(process.ppid,0,'native process must be namespace init');
for(const key of ['FRIDAY_LLM_API_KEY','OPENAI_API_KEY','EXA_API_KEY','TELEGRAM_BOT_TOKEN','ANTHROPIC_API_KEY','FRIDAY_DSH_PARENT_SECRET']) assert.equal(process.env[key],undefined);
for(const path of [host.secret_path,host.home+'/.env',host.home+'/auth.json']) assert.equal(fs.existsSync(path),false,path);
assert.throws(()=>fs.readFileSync('/proc/'+host.pid+'/environ'),{code:'ENOENT'});
assert.throws(()=>fs.readFileSync('/proc/'+host.pid+'/root'+host.secret_path),{code:'ENOENT'});
// Zero bits are observed in this outer child user namespace. No host initial-userns membership is asserted.
const imp=p=>import(pathToFileURL(m.harness+'/'+p).href);
const {Context}=await imp('vendor/cordis/lib/index.js');
const {LocalSandboxProvider}=await imp('packages/sandbox/sandbox-local/lib/index.js');
const {default:SessionProjectionRegistry}=await imp('packages/session/session-projection/lib/index.js');
const {SandboxPolicyService}=await imp('packages/sandbox/sandbox-policy/lib/index.js');
const {default:LocalSubprocessRuntime}=await imp('packages/subprocess/subprocess-local/lib/index.js');
const {SandboxBashExecutor}=await imp('packages/shell/bash-sandbox/lib/index.js');
const ctx=new Context();let wrapped;
try {
 await ctx.plugin(LocalSandboxProvider,{runnerCommand:['/usr/bin/bwrap'],runnerFailureSignatures:['bwrap: ']});
 await ctx.plugin(SessionProjectionRegistry);await ctx.plugin(SandboxPolicyService,{mode:'workspace-write',workspaceRoot:'/workspace'});
 await ctx.plugin(LocalSubprocessRuntime);await ctx.plugin(SandboxBashExecutor,{cwd:'/workspace',timeoutMs:15000,maxTimeoutMs:15000,graceMs:200});
 assert(ctx.shell instanceof SandboxBashExecutor);
 const native=ctx.sandbox.confine.bind(ctx.sandbox);
 ctx.sandbox.confine=async(...a)=>{wrapped=await native(...a);return wrapped;};
 const command=`set -eu
for key in FRIDAY_LLM_API_KEY OPENAI_API_KEY EXA_API_KEY TELEGRAM_BOT_TOKEN ANTHROPIC_API_KEY FRIDAY_DSH_PARENT_SECRET; do
 if /usr/bin/printenv \"$key\" >/dev/null; then exit 74; fi
done
IFS= read -r label </proc/self/attr/current
printf '%s\\n' "$label" > /workspace/bash-label
while IFS= read -r line; do case "$line" in Cap*|NoNewPrivs*|NSpid*|Uid*|Gid*) printf '%s\\n' "$line";; esac; done </proc/self/status > /workspace/bash-status
/usr/bin/readlink /proc/self/ns/pid > /workspace/bash-pidns
/usr/bin/readlink /proc/self/ns/user > /workspace/bash-userns
/usr/bin/readlink /proc/self/ns/mnt > /workspace/bash-mntns
while IFS= read -r line; do printf '%s\\n' "$line"; done </proc/self/uid_map > /workspace/bash-uid-map
while IFS= read -r line; do printf '%s\\n' "$line"; done </proc/self/gid_map > /workspace/bash-gid-map
while IFS= read -r line; do printf '%s\\n' "$line"; done </proc/self/mountinfo > /workspace/bash-mountinfo
# Fixed zero-payload attempts: success is a qualification failure; no host mounts or grants.
for tool in /usr/bin/bwrap /usr/local/libexec/friday-dsh-bwrap; do
 if "$tool" --unshare-user --ro-bind / / -- /usr/bin/true > /dev/null 2>/workspace/denial-\${tool##*/}; then exit 71; fi
done
if /usr/bin/unshare --user /usr/bin/true >/dev/null 2>/workspace/userns-denial; then exit 72; fi
if /usr/bin/unshare --mount /usr/bin/true >/dev/null 2>/workspace/cap-denial; then exit 73; fi
/usr/bin/python3 -I -c 'import pathlib; print(pathlib.Path("/proc/self/attr/current").read_text().strip())' > /workspace/python-label
${m.node} -e 'console.log(require("node:fs").readFileSync("/proc/self/attr/current","utf8").trim())' > /workspace/node-label
printf 'R2-NATIVE-BASH-OK\\n' > /workspace/artifact
`;
 const run=await ctx.shell.execute(ctx.shell.resolve({command,env:{PATH:'/usr/bin:/bin',HOME:'/job-home',LANG:'C.UTF-8'},timeoutMs:15000}));
 const result=await run.result();assert.equal(result.exitCode,0,JSON.stringify(result));
 assert.equal(wrapped.argv[0],'/usr/bin/bwrap');assert(wrapped.argv.includes('--unshare-pid'));assert(wrapped.argv.includes('--proc'));
 const nested=Object.fromEntries(['bash-label','bash-status','bash-pidns','bash-userns','bash-mntns','bash-uid-map','bash-gid-map','bash-mountinfo','python-label','node-label'].map(k=>[k,fs.readFileSync('/workspace/'+k,'utf8').trim()]));
 // Kernel stack component ordering is not an observation contract. Exact names,
 // enforce suffix, cardinality and distinctness are; no extra stack is accepted.
 const expectedComponents=['friday-dsh-command-v1','friday-dsh-native-v1'];
 for(const k of ['bash-label','python-label','node-label']){
  const label=nested[k],suffix=' (enforce)';assert(label.endsWith(suffix),k);
  const components=label.slice(0,-suffix.length).split('//&');
  assert.equal(components.length,2,k);assert.equal(new Set(components).size,2,k);
  assert.deepEqual(components.sort(),expectedComponents,k);
 }
 assert.notEqual(nested['bash-pidns'],outer.ns.pid);assert.notEqual(nested['bash-mntns'],outer.ns.mnt);
 // Native rootless bwrap implicitly creates NEWUSER on this host; argv remains intact.
 assert.notEqual(nested['bash-userns'],outer.ns.user);
 for(const k of ['bash-uid-map','bash-gid-map'])assert.match(nested[k],/^\d+\s+\d+\s+\d+/);
 assert.match(nested['bash-status'],/^NoNewPrivs:\s+1$/m);
 // CapBnd can reset across userns creation; it is recorded, never assumed zero here.
 for(const k of ['CapInh','CapPrm','CapEff','CapAmb'])assert.match(nested['bash-status'],new RegExp('^'+k+':\\s+0+$','m'));
 assert.match(fs.readFileSync('/workspace/bash-mountinfo','utf8'),/ \/proc .* - proc /m);
 for(const name of ['denial-bwrap','denial-friday-dsh-bwrap','userns-denial','cap-denial'])assert.match(fs.readFileSync('/workspace/'+name,'utf8'),/Operation not permitted|Permission denied/i);
 assert.equal(fs.readFileSync('/workspace/artifact','utf8'),'R2-NATIVE-BASH-OK\n');
 console.log(JSON.stringify({schema:'friday.dsh-native-safety.v1',status:'NATIVE_SAFETY_PASS',runtime_home:m.runtime_home,runtime_profile:m.runtime_profile,payload_root:m.harness,node:m.node,outer,nested,host,shell_result:{exitCode:result.exitCode},wrap:{argv:wrapped.argv},artifact_sha256:(await import('node:crypto')).createHash('sha256').update(fs.readFileSync('/workspace/artifact')).digest('hex'),controls:["exact-labels", "nnp-and-current-caps", "namespace-ancestry", "fresh-proc", "parent-secret-exclusion", "strict-reexec-denials", "native-context-bash", "native-artifact"]}));
} finally { await ctx.fiber.dispose(); }
'''
DSH_SAFETY_CONTROLS = ['exact-labels', 'nnp-and-current-caps', 'namespace-ancestry', 'fresh-proc', 'parent-secret-exclusion', 'strict-reexec-denials', 'native-context-bash', 'native-artifact']


def checked_dsh_safety(report, runtime, home):
    """Validate native evidence, never an opaque ready/success assertion."""
    import re
    d = runtime['dsh']
    require(isinstance(report, dict) and report.get('schema') == 'friday.dsh-native-safety.v1'
            and report.get('status') == 'NATIVE_SAFETY_PASS'
            and report.get('runtime_home') == str(home)
            and report.get('runtime_profile') == runtime['runtime_profile']
            and report.get('payload_root') == d['payload_root'] and report.get('node') == d['node']['path']
            and report.get('controls') == DSH_SAFETY_CONTROLS
            and report.get('shell_result') == {'exitCode':0}
            and report.get('artifact_sha256') == hashlib.sha256(b'R2-NATIVE-BASH-OK\n').hexdigest(),
            'dsh_native_safety_unverified')
    outer = report['outer']; nested = report['nested']; host = report['host']
    require(outer['label'] == 'friday-dsh-native-v1 (enforce)', 'dsh_native_label_unverified')
    for label in (nested[k] for k in ('bash-label','python-label','node-label')):
        require(label.endswith(' (enforce)') and sorted(label[:-10].split('//&')) ==
                ['friday-dsh-command-v1','friday-dsh-native-v1'], 'dsh_command_label_unverified')
    for status in ('\n'.join(outer['status']), nested['bash-status']):
        require(re.search(r'^NoNewPrivs:\s+1$',status,re.M) is not None, 'dsh_nnp_unverified')
        for key in ('CapInh','CapPrm','CapEff','CapAmb'):
            require(re.search(r'^'+key+r':\s+0+$',status,re.M) is not None, 'dsh_current_capability_present')
        require(re.search(r'^CapBnd:\s+[0-9a-fA-F]+$',status,re.M) is not None, 'dsh_capbnd_observation_missing')
    require(type(host.get('pid')) is int and host['pid'] > 1
            and isinstance(host.get('namespaces'), dict)
            and set(host['namespaces']) == {'user','pid','mnt'},
            'dsh_host_namespace_identity_unverified')
    for key in ('user','pid','mnt'):
        values = (host['namespaces'][key], outer['ns'][key], nested['bash-'+key+'ns'])
        require(all(isinstance(value, str) and re.fullmatch(key+r':\[[0-9]+\]', value)
                    is not None for value in values), 'dsh_namespace_identity_unverified')
        require(nested['bash-'+key+'ns'] != host['namespaces'][key],
                'dsh_namespace_separation_unverified')
    require(all(outer['ns'][key] != host['namespaces'][key] for key in ('user','pid','mnt'))
            and nested['bash-pidns'] != outer['ns']['pid'] and nested['bash-userns'] != outer['ns']['user']
            and nested['bash-mntns'] != outer['ns']['mnt'],
            'dsh_namespace_separation_unverified')
    for maps in (outer['uid_map'],outer['gid_map'],nested['bash-uid-map'],nested['bash-gid-map']):
        require(re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s*',maps) is not None, 'dsh_namespace_map_unverified')
    require(re.search(r' /proc .* - proc ',nested['bash-mountinfo'],re.M) is not None,
            'dsh_fresh_proc_unverified')
    argv = report['wrap']['argv']
    require(isinstance(argv,list) and argv and argv[0] == '/usr/bin/bwrap'
            and '--unshare-pid' in argv and '--proc' in argv, 'dsh_native_bash_wrapper_unverified')
    return report


def dsh_safety_observe(runtime, home, folder, budget):
    return dsh_observe(runtime, home, folder, budget, safety_only=True)


def dsh_observe(runtime, home, folder, budget, *, safety_only=False):
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
    if safety_only:
        control = folder / 'control'; control.mkdir(mode=0o700)
        parent_secret = os.urandom(32).hex()
        secret = control / 'parent-secret'; secret.write_text(parent_secret); secret.chmod(0o400)
        host = {'namespaces': {k: os.readlink('/proc/self/ns/' + k)
                              for k in ('user','pid','mnt')},
                'pid': os.getpid(), 'home': str(home), 'secret_path': str(secret)}
        manifests = {'manifest.json': {'harness':str(cfg.payload_root),'node':str(cfg.node.path),
                    'runtime_home':str(home),'runtime_profile':runtime['runtime_profile']}, 'host.json':host}
        for name,value in manifests.items():
            path = folder / 'inputs' / name
            path.write_text(json.dumps(value)); path.chmod(0o400)
        path = folder / 'inputs' / 'native-safety.mjs'
        path.write_text(DSH_NATIVE_SAFETY); path.chmod(0o400)
    count = 0
    def observe(command):
        nonlocal count
        count += 1
        budget.check(reserve=1)
        r, w = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        observation = {}; failure = None; output = ''
        try:
            limit = min(20 if safety_only else 5, budget.check(reserve=1))
            row = {'admission_hash':hashlib.sha256(str(folder).encode()).hexdigest(),
                   'supervisor':{'unit':'friday-qualification-construction-only.service'}}
            # Use the exact installed adapter selector. Only its foreground
            # boundary is run: the existing scope/PID custody remains the owner.
            launch = adapter._launch_argv(row,folder,folder,limit,{},command)
            from plugins.friday_rework.adapters.dsh import _APPARMOR_ENTRY
            require(launch.count(_APPARMOR_ENTRY) == 1, 'dsh_unique_entry_required')
            argv = launch[launch.index(_APPARMOR_ENTRY):]
            argv[1:1] = ['--json-status-fd', str(w), '--as-pid-1']
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
                execution_env = adapter._environment()
                if safety_only: execution_env = dict(execution_env,FRIDAY_DSH_PARENT_SECRET=parent_secret)
                output, observation = run(argv, folder, env=execution_env,
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
    if safety_only:
        out, execution = observe([str(cfg.node.path), '--max-old-space-size=128', '/job-input/native-safety.mjs'])
        report = checked_dsh_safety(json.loads(out),runtime,home)
        adapter._pins()
        return {'report':report,'execution':execution,
                'specimen_sha256':hashlib.sha256(DSH_NATIVE_SAFETY.encode()).hexdigest()}
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
    An explicit existing probe retains its original owner. The ordinary path
    uses the same protected initial producer as user setup and settles its
    native custody before publishing qualified receipts.
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
        from plugins.friday_rework.a0_bootstrap import installation_probe, own_probe, checked_custody
        probe_owner = None
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
        custody = None
        try:
            safety_scratch = folder / 'dsh-safety'; safety_scratch.mkdir(mode=0o700)
            safety = budget.call(dsh_safety_observe,product['runtime']['workers']['dsh'],home,safety_scratch,budget)
            budget.call(inspect,value,input_hash)
            credentials = {name: digest(owned_file(home / name, private=True))
                if (home / name).exists() or (home / name).is_symlink() else None for name in ('.env','auth.json')}
            probe_owner = None if plan_ref is not None else installation_probe(product,home,claim,budget,
                verify=lambda:budget.call(inspect,value,input_hash))
            if probe_owner is not None:
                with own_probe(probe_owner) as plan_ref:
                    a0 = budget.call(a0_observe, product['runtime']['workers']['a0'], plan_ref, budget, probe_owner=probe_owner)
                    budget.call(inspect,value,input_hash)
                custody = checked_custody(home,probe_owner.binding,1,probe_owner.preparations,plan_ref)
            scratch = folder / 'dsh-probe'; scratch.mkdir(mode=0o700)
            dsh = budget.call(dsh_observe, product['runtime']['workers']['dsh'], home, scratch, budget)
            dsh['safety'] = safety
            if probe_owner is None:
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
        except BaseException:
            try:
                publish(folder / 'failure.json', {'state':'REFUSED_OR_UNCERTAIN',
                    'original_attempt':claim,'plan':plan_ref,'retry_authorized':False})
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
        if custody is not None: proof['bootstrap_custody'] = custody
        # Whole native observation validation precedes ready receipt publication.
        from plugins.friday_rework.host_runtime import deployment_observations
        for runtime in product['runtime']['workers'].values():
            budget.call(deployment_observations,runtime,proof,claim,folder)
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
