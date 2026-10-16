"""Native worker observations; no installer orchestration or per-job authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from .runtime_primitives import pin, read_json, require


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



def a0_observe(runtime, plan_ref, budget, *, probe_owner=None):
    """Observe an existing exact native plan; no create/start/route or grant."""
    from .host_runtime import a0_runtime_module, a0_deployment_contract
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
        from .runtime_process import StopUnconfirmed
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
    from .adapters.dsh import DshAdapter, DshHostConfig
    from .host_runtime import _pin, _dsh_web
    from .worker_web import web_policy, DSH_NETWORK_PROBE, checked_network_observation
    from .runtime_containment import namespace_exit, checked_binary
    from .runtime_process import run, StopUnconfirmed
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
            from .adapters.dsh import _APPARMOR_ENTRY
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

