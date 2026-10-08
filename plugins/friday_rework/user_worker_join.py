"""Normal private-profile provisioning through existing observers and consumers.

Preparation declares inputs, never readiness. Protected qualification invokes
the distinct initial A0 native probe owner, without granting ordinary jobs.
One durable original attempt prevents automatic resubmission after uncertainty.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import time

from .host_record import digest
from .host_runtime import HostUnavailable, _pin, configured_runtimes, validate_runtime
from .worker_provision import own_runtime, pin, preparation

FOLDER = 'workers/qualification'
PROOF = FOLDER + '/observation.json'
INTENT = FOLDER + '/original.json'
PLAN = 'workers/a0/probe-plan.json'
LIMITS = ('budget_seconds', 'max_file_bytes', 'max_total_bytes')


def installation_inputs(runtime):
    """Retain reviewed installation declarations, discard receipts/authority."""
    rows = configured_runtimes(runtime)
    result = {'required': ['dsh', 'a0'], 'workers': {}}
    if set(rows) != {'dsh', 'a0'}:
        return result
    for kind, c in rows.items():
        result['workers'][kind] = {k: copy.deepcopy(c[k]) for k in (*LIMITS, kind)}
    result['workers']['dsh']['dsh'].pop('patch')
    a = rows['a0']['a0']
    from .adapters.a0_profile import endpoint_urls
    if 'deployment' not in a or 'web' not in a:
        result['workers'] = {}
        return result
    result['a0_network'] = {'name': 'friday-onboarding',
        'endpoints': endpoint_urls(a['deployment']), 'policy': copy.deepcopy(a['policy'])}
    result['source_scope'] = {'home': rows['dsh']['runtime_home'], 'profile': rows['dsh']['runtime_profile']}
    return result


def _runtime(home, profile, kind, declaration):
    root = home / 'workers' / kind
    return {'enabled': True, 'runtime_home': str(home), 'runtime_profile': profile,
        'workspace_root': str(root / 'jobs'), 'staging_root': str(root / 'staging'),
        'cache_roots': [str(root / 'cache')],
        'runtime_receipt': {'path': str(root / 'runtime-receipt.json'), 'sha256': '0' * 64},
        **copy.deepcopy(declaration)}


def validate_installation_inputs(value):
    if (not isinstance(value, dict) or value.get('required') != ['dsh', 'a0']
            or set(value) not in ({'required', 'workers'}, {'required', 'workers', 'a0_network', 'source_scope'})
            or not isinstance(value['workers'], dict)):
        raise ValueError('invalid_normal_worker_inputs')
    if not value['workers']:
        if set(value) != {'required', 'workers'}: raise ValueError('partial_normal_worker_inputs')
        return value
    if set(value['workers']) != {'dsh', 'a0'} or 'source_scope' not in value:
        raise ValueError('both_normal_worker_inputs_required')
    if set(value['source_scope']) != {'home', 'profile'}:
        raise ValueError('invalid_worker_source_scope')
    for kind, row in value['workers'].items():
        if set(row) != set(LIMITS) | {kind}: raise ValueError('invalid_worker_declaration')
        c = _runtime(Path('/friday-input-check'), 'validation', kind, row)
        if kind == 'dsh':
            c['dsh']['patch'] = {'path': '/friday-input-check/patch.json', 'sha256': '0' * 64}
        validate_runtime(c)
    network = value['a0_network']
    if (set(network) != {'name', 'endpoints', 'policy'}
            or network['policy'] != value['workers']['a0']['a0']['policy']):
        raise ValueError('normal_worker_network_mismatch')
    from .adapters.a0_config import LocalNetwork
    LocalNetwork(network['name'], tuple(network['endpoints']), _pin(network['policy']),
                 value['workers']['a0']['a0']['deployment']).checked()
    return value


def required_workers(root_config, proof, home):
    # The protected fresh preparation fixes this contract. A later template
    # edit/name collision cannot silently migrate an existing valid home.
    from hermes_cli.config import require_readable_config_before_write
    path=home/'config.yaml'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=proof['config_sha256']:
        raise PermissionError('prepared_worker_contract_changed')
    own=require_readable_config_before_write(path)
    return own['plugins']['entries']['friday_rework']['settings'].get('worker_requirements')==['dsh','a0']


def derive_inputs(home, profile, value, config):
    """New identity/roots and scoped declaration; original policy expiry stays."""
    validate_installation_inputs(value)
    if not value['workers']: raise HostUnavailable('installation_worker_inputs_missing')
    runtimes = {kind: _runtime(home, profile, kind, row) for kind, row in value['workers'].items()}
    d = runtimes['dsh']['dsh']
    from .host_runtime import _dsh_web
    from .worker_web import web_policy
    from tools.render_dsh_local import build_patch
    # This is a protected operator declaration, NOT a cloned observation.
    policy = web_policy(_dsh_web(d), value['source_scope']['home'], value['source_scope']['profile'], time.time())
    ns = Path('/proc/self/ns/net').stat()
    if (policy['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            or policy['net_namespace'] != [ns.st_dev, ns.st_ino]):
        raise HostUnavailable('worker_source_namespace_changed')
    policy = dict(policy, runtime_home=str(home), runtime_profile=profile)
    policy_bytes = (json.dumps(policy, sort_keys=True) + '\n').encode()
    policy_path = home / 'workers/dsh/inputs/web-policy.json'
    d['web']['egress_evidence'] = {'path': str(policy_path), 'sha256': hashlib.sha256(policy_bytes).hexdigest()}
    provider = config['providers']['friday-local']; model = config['model']
    capacity = provider['models'][model['default']]; b = capacity['bounded_context']
    patch = build_patch(purpose='temporary-local-test', api='openai-completions',
        base_url=model['base_url'], model=model['default'], api_key_env=d['key_name'],
        context_window=capacity['context_length'], max_tokens=b['main_max_output_tokens'],
        summary_max_tokens=b['compression_max_output_tokens'],
        headroom_tokens=b['safety_margin_tokens'] + b['template_overhead_tokens'], web_profile=d['web']['profile'])
    data = (json.dumps(patch, ensure_ascii=False, indent=2) + '\n').encode()
    d['patch'] = {'path': str(home / 'workers/dsh/inputs/dsh-local.json'), 'sha256': hashlib.sha256(data).hexdigest()}
    for kind, c in runtimes.items(): own_runtime(home, profile, kind, c)
    return runtimes, copy.deepcopy(value['a0_network']), (policy_path, policy_bytes)


def readiness_receipt(c, evidence):
    """Same existing runtime receipt schema, produced only after observation."""
    source = Path(__file__).parent; kind = 'a0' if 'a0' in c else 'dsh'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = {'schema': 'friday-rework.' + ('a0-runtime.v2' if kind == 'a0' else 'dsh-runtime.v1'),
        'ready': True, 'runtime_sha256': digest({k:v for k,v in c.items() if k != 'runtime_receipt'}), 'evidence': evidence}
    if kind == 'a0':
        result['source_pins'] = {k: sha(source / p) for k,p in {
            'host':'host.py','host_runtime':'host_runtime.py','host_record':'host_record.py',
            'associations':'associations.py','adapter':'adapters/a0.py','native':'adapters/a0_native.py',
            'config':'adapters/a0_config.py','profile':'adapters/a0_profile.py','web':'adapters/a0_web.py'}.items()}
    else:
        import tools.web_profile as helper
        result['adapter_sha256'] = sha(source / 'adapters/dsh.py')
        result['web_source_pins'] = {'plugins/friday_rework/worker_web.py':sha(source / 'worker_web.py'),
            'tools/web_profile.py':sha(Path(helper.__file__)), 'config/RESEARCH.md':c['dsh']['web']['research_policy']['sha256']}
        if c['dsh']['web']['profile'] == 'exa-keyless':
            result['web_source_pins']['plugins/friday_rework/adapters/dsh_keyless_web.mjs'] = sha(source / 'adapters/dsh_keyless_web.mjs')
    return result


def checked_plan(home, binding, runtimes):
    """Fixed own-profile native producer output, never an HTTP-supplied report."""
    path = home / PLAN
    if not path.exists() and not path.is_symlink(): raise HostUnavailable('own_a0_native_probe_required')
    ref = pin(path)
    from .host_runtime import a0_runtime_module
    from .adapters.a0_native import strict_json
    m = a0_runtime_module(runtimes['a0']); plan = m.validate(strict_json(_pin(ref).read()))
    identity = plan.get('association_binding', {}); owner = identity.get('owner', {})
    workspace=Path(identity.get('workspace_reference','/'))
    if (owner.get('profile') != binding['runtime_profile'] or owner.get('user_id') != binding['user_id']
            or owner.get('bot_id') != binding['account_id']
            or workspace.resolve()!=workspace
            or not workspace.is_relative_to(Path(runtimes['a0']['workspace_root']))):
        raise HostUnavailable('foreign_a0_user_probe')
    m.remaining(plan)
    return ref


def qualify(home, binding, generation, prepared, *, verify, accepted_monotonic=None):
    """One explicit owning-host action, reusing both complete native observers."""
    from .onboarding import _new_file
    from scripts.install_containment import Budget
    from scripts.worker_qualification import dsh_observe, a0_observe
    from hermes_cli import friday_user_scope as scope
    from hermes_cli.config import require_readable_config_before_write
    from .worker_provision import prepare_inputs
    runtimes = {k: preparation(home, binding['runtime_profile'], k, ref)[1] for k,ref in prepared.items()}
    if set(runtimes) != {'dsh', 'a0'}: raise HostUnavailable('both_worker_preparations_required')
    config=require_readable_config_before_write(home / 'config.yaml')
    from .adapters.a0_profile import endpoint_urls
    a=runtimes['a0']['a0']
    network={'name':'friday-onboarding','endpoints':endpoint_urls(a['deployment']),'policy':a['policy']}
    def sources():
        for kind,c in runtimes.items():
            prepare_inputs(home,binding['runtime_profile'],kind,c,config,
                a0_network=network if kind=='a0' else None)
    sources()
    folder = home / FOLDER
    if folder.exists() or folder.is_symlink(): raise HostUnavailable('qualification_attempt_requires_inspection')
    for p in (home / '.env', home / scope.ONBOARDING): scope._private(p)
    verify()
    seconds = min(300, *(c['budget_seconds'] for c in runtimes.values()))
    budget = Budget(seconds, started=accepted_monotonic); boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    claim = {'boot_id':boot, 'started_mono':budget.deadline-seconds, 'deadline_mono':budget.deadline, 'budget_seconds':seconds}
    from .a0_bootstrap import InitialProbe, own_probe, checked_custody
    # A copied live/per-job plan is not authority to adopt an existing probe.
    probe = InitialProbe(runtimes['a0'], binding, generation, prepared, budget, verify, original_seconds=seconds)
    credentials = {n: pin(home / n)['sha256'] if (home / n).exists() else None for n in ('.env','auth.json')}
    try:
        with own_probe(probe) as plan:
            checked_plan(home, binding, runtimes)
            original = {'schema':'friday.user-worker-qualification.v1','home':str(home),
                'profile':binding['runtime_profile'],'binding_sha256':scope._fingerprint(binding),'generation':generation,
                'original_attempt':claim,'preparations':prepared,'credentials':credentials,'plan':plan,
                'bootstrap_original':pin(home / 'workers/a0/bootstrap/original.json'),'binding':binding}
            verify(); folder.mkdir(mode=0o700)
            _new_file(home / INTENT, (json.dumps(original,sort_keys=True)+'\n').encode())
            a0 = budget.call(a0_observe, runtimes['a0'], plan, budget, probe_owner=probe)
            verify()
        custody = checked_custody(home, binding, generation, prepared, plan)
        # Native cessation precedes Harness observations/readiness publication;
        # both observations still consume the SAME original setup deadline.
        scratch = folder / 'dsh-probe'; scratch.mkdir(mode=0o700)
        dsh = budget.call(dsh_observe, runtimes['dsh'], home, scratch, budget)
        verify()
        for kind, ref in prepared.items(): preparation(home,binding['runtime_profile'],kind,ref)
        budget.call(sources)
        if credentials != {n:pin(home/n)['sha256'] if (home/n).exists() else None for n in credentials}:
            raise HostUnavailable('qualification_credentials_changed')
        obs = {'dsh': dsh, 'a0': a0}
        for kind,c in runtimes.items(): obs[kind]['runtime_sha256']=digest({k:v for k,v in c.items() if k!='runtime_receipt'})
        proof = {'schema':'friday.worker-deployment-observation.v1','home':str(home),'profile':binding['runtime_profile'],
            'original':pin(home / INTENT),'workers':obs,'credentials':credentials,'bootstrap_custody':custody,
            'effects':'OBSERVATION_ONLY','per_job_authority':'NOT_GRANTED',
            'observed':{'boot_id':boot,'monotonic':time.monotonic(),'unix':time.time()}}
        from .host_runtime import deployment_observations
        for c in runtimes.values(): budget.call(deployment_observations,c,proof,claim,folder)
        verify(); budget.call(_new_file,home / PROOF,(json.dumps(proof,sort_keys=True)+'\n').encode())
        for kind,c in runtimes.items():
            verify(); receipt=readiness_receipt(c,[prepared[kind],pin(home / PROOF)])
            budget.call(_new_file,Path(c['runtime_receipt']['path']),(json.dumps(receipt,sort_keys=True)+'\n').encode())
            c['runtime_receipt']=pin(Path(c['runtime_receipt']['path']))
        return runtimes
    except BaseException as exc:
        from scripts.dsh_prepare import StopUnconfirmed
        failure={'state':'STOP_UNCONFIRMED' if isinstance(exc,StopUnconfirmed) else 'REFUSED_OR_UNCERTAIN',
            'original_attempt':claim,'retry_authorized':False,'a0_probe_cleanup':'OWN_INITIAL_PROBE_CUSTODY'}
        try: _new_file(folder / 'failure.json',(json.dumps(failure,sort_keys=True)+'\n').encode())
        except OSError: pass
        raise


def deployment_health(c, *, binding=None, generation=None):
    """Own producer/proof/inputs/clock, followed by the shared native consumer."""
    from hermes_cli import friday_user_scope as scope
    from .host_runtime import deployment_observations, a0_deployment_contract, _dsh_web
    from .worker_web import web_policy
    c=validate_runtime(c)
    if 'a0' in c: a0_deployment_contract(c)
    else:
        web=_dsh_web(c['dsh'])
        if web is None: raise HostUnavailable('mandatory_worker_web_contract_required')
        policy=web_policy(web,c['runtime_home'],c['runtime_profile'],time.time())
        ns=Path('/proc/self/ns/net').stat()
        if (policy['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                or policy['net_namespace']!=[ns.st_dev,ns.st_ino]):
            raise HostUnavailable('worker_web_namespace_changed')
    home=Path(c['runtime_home']); folder=home / FOLDER
    from .adapters.a0_native import strict_json
    def private_json(p): scope._private(p); return strict_json(p.read_bytes())
    original=private_json(home / INTENT); proof=private_json(home / PROOF)
    setup=private_json(home / scope.ONBOARDING)
    if (original.get('schema')!='friday.user-worker-qualification.v1' or original.get('home')!=str(home)
            or original.get('profile')!=c['runtime_profile'] or original.get('binding_sha256')!=setup['binding_sha256']
            or (binding is not None and original['binding_sha256']!=scope._fingerprint(binding))
            or (generation is not None and original['generation']!=generation)
            or (folder / 'failure.json').exists() or (folder / 'failure.json').is_symlink()):
        raise HostUnavailable('foreign_or_incomplete_user_qualification')
    claim=original['original_attempt']
    if (proof.get('schema')!='friday.worker-deployment-observation.v1' or proof.get('home')!=str(home)
            or proof.get('profile')!=c['runtime_profile'] or proof.get('original')!=pin(home / INTENT)
            or proof.get('effects')!='OBSERVATION_ONLY' or proof.get('per_job_authority')!='NOT_GRANTED'
            or set(proof.get('workers',{}))!={'dsh','a0'} or proof.get('credentials')!=original['credentials']
            or proof['observed']['boot_id']!=claim['boot_id']
            or claim['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            or not claim['started_mono']<=proof['observed']['monotonic']<claim['deadline_mono']):
        raise HostUnavailable('user_worker_observation_changed')
    kind='a0' if 'a0' in c else 'dsh'
    v,before=preparation(home,c['runtime_profile'],kind,original['preparations'][kind])
    expected={k:v for k,v in before.items() if k!='runtime_receipt'}
    if (v['principal_binding_sha256']!=original['binding_sha256'] or v['generation']!=original['generation']
            or expected!={k:v for k,v in c.items() if k!='runtime_receipt'}
            or proof['workers'][kind]['runtime_sha256']!=digest(expected)):
        raise HostUnavailable('user_worker_preparation_changed')
    for n,sha in original['credentials'].items():
        p=home/n
        if (sha is None and (p.exists() or p.is_symlink())) or (sha is not None and pin(p)['sha256']!=sha):
            raise HostUnavailable('user_worker_credentials_changed')
    receipt=private_json(Path(c['runtime_receipt']['path'])); _pin(c['runtime_receipt']).read()
    if receipt!=readiness_receipt(c,[original['preparations'][kind],pin(home / PROOF)]):
        raise HostUnavailable('user_worker_receipt_not_produced')
    if kind=='a0' and proof['workers'][kind]['plan']!=original['plan']:
        raise HostUnavailable('user_worker_native_plan_changed')
    from .a0_bootstrap import checked_custody
    custody = checked_custody(home,original['binding'],original['generation'],original['preparations'],original['plan'])
    if (proof.get('bootstrap_custody')!=custody or custody['original']!=original['bootstrap_original']
            or scope._fingerprint(original['binding'])!=original['binding_sha256']):
        raise HostUnavailable('user_worker_bootstrap_custody_changed')
    return deployment_observations(c,proof,claim,folder)
