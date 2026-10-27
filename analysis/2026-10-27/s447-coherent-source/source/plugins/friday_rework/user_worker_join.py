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


def own_a0_inputs(home, runtime, network, config, launcher):
    """Pure own-profile plan using the caller's exact pinned launcher namespace."""
    from .adapters.a0_profile import checked_profile, endpoint_urls, network_endpoints
    from .adapters.a0_web import route_web
    deployment = checked_profile(config.get('a0_deployment'))
    c = copy.deepcopy(runtime)
    c['a0']['deployment'] = deployment
    raw = launcher['policy'](route_web(c['a0']['web']), network_endpoints(deployment)).encode()
    path = home / 'workers/a0/inputs/a0-policy.nft'
    reference = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    c['a0']['policy'] = reference
    own_network = copy.deepcopy(network)
    own_network.update(endpoints=list(endpoint_urls(deployment)), policy=copy.deepcopy(reference))
    return c, own_network, (path, raw)


def _preparation_web_policy(dsh, source_scope, reference=None):
    """Explicit current-boot declaration; never renew or widen source policy."""
    from .host_runtime import _dsh_web
    from .worker_web import web_policy
    now = time.time()
    original = web_policy(_dsh_web(dsh), source_scope['home'], source_scope['profile'], now)
    policy = original
    if reference is not None:
        selected = copy.deepcopy(dsh)
        selected['web']['egress_evidence'] = reference
        policy = web_policy(_dsh_web(selected), source_scope['home'], source_scope['profile'], now)
        # Only the explicitly declared boot/namespace may differ. Preserve the
        # original finite expiry and every other value, including JSON types.
        if any(type(policy[k]) is not type(original[k]) or policy[k] != original[k]
               for k in original if k not in ('boot_id', 'net_namespace')):
            raise HostUnavailable('worker_source_web_policy_changed')
    ns = Path('/proc/self/ns/net').stat()
    if (policy['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            or policy['net_namespace'] != [ns.st_dev, ns.st_ino]):
        raise HostUnavailable('worker_source_namespace_changed')
    return policy


def derive_inputs(home, profile, value, config, *, web_policy=None):
    """New identity/roots and scoped declaration; original policy expiry stays."""
    validate_installation_inputs(value)
    if not value['workers']: raise HostUnavailable('installation_worker_inputs_missing')
    runtimes = {kind: _runtime(home, profile, kind, row) for kind, row in value['workers'].items()}
    # Reviewed installation sources/resources stay explicit. Each receiving
    # profile owns its model slots and the exact policy for those routes.
    from .host_runtime import a0_runtime_module
    from .adapters.a0_profile import checked_profile
    checked_profile(config.get('a0_deployment'))
    a = runtimes['a0']['a0']
    launcher = a0_runtime_module(runtimes['a0']).checked_launcher(a['launcher']['sha256'])
    runtimes['a0'], network, a0_policy = own_a0_inputs(home, runtimes['a0'], value['a0_network'], config, launcher)
    d = runtimes['dsh']['dsh']
    from .worker_provision import source_module
    build_patch = source_module('tools.render_dsh_local').build_patch
    # Protected prepare-only input; the installation template stays untouched.
    policy = _preparation_web_policy(d, value['source_scope'], web_policy)
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
    return runtimes, network, {'dsh': {policy_path: policy_bytes}, 'a0': {a0_policy[0]: a0_policy[1]}}


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
        from .worker_provision import source_module
        helper = source_module('tools.web_profile')
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


def _failure_location(exc):
    """Private causal metadata from fixed types/sites; never values or locals."""
    import sys
    known = {HostUnavailable: 'host_unavailable', OSError: 'os_error',
        PermissionError: 'permission_error', FileNotFoundError: 'file_not_found',
        RuntimeError: 'runtime_error', TypeError: 'type_error', ValueError: 'value_error',
        KeyError: 'key_error', IndexError: 'index_error', AssertionError: 'assertion_error',
        TimeoutError: 'timeout_error', json.JSONDecodeError: 'json_decode_error'}
    # Do not import new native modules while handling an existing failure.
    for module, name, label in (
        ('runtime_process', 'StopUnconfirmed', 'stop_unconfirmed'),
        ('runtime_process', 'CommandFailed', 'command_failed'),
        ('runtime_primitives', 'Refused', 'source_refused'),
        ('adapters.dsh', 'AdapterError', 'dsh_adapter_error')):
        loaded = sys.modules.get(__package__ + '.' + module)
        cls = vars(loaded).get(name) if loaded is not None else None
        if isinstance(cls, type): known[cls] = label
    # The existing projection facade re-exports this already-loaded canonical
    # class. Accept only that exact identity and installed path; never import a
    # native module or trust an exception's class name to find its origin.
    supervisor_name = 'hermes_cli.friday_native_supervision'
    supervisor_path = ('<INSTALL_HOME>/hermes-agent/hermes_cli/friday_native_supervision.py')
    supervisor = sys.modules.get(supervisor_name)
    facade = sys.modules.get(__package__ + '.supervision')
    supervisor_class = None
    if type(supervisor) is type(sys) and type(facade) is type(sys):
        cls = vars(supervisor).get('SupervisorError')
        if (vars(supervisor).get('__name__') == supervisor_name
                and vars(supervisor).get('__file__') == supervisor_path
                and type(cls) is type and cls.__module__ == supervisor_name
                and vars(facade).get('SupervisorError') is cls):
            supervisor_class = cls
            known[cls] = 'native_supervisor_error'
    control_name = 'hermes_cli.friday_native_control'
    control_path = ('<INSTALL_HOME>/hermes-agent/hermes_cli/friday_native_control.py')
    control = sys.modules.get(control_name)
    control_class = None
    if type(control) is type(sys):
        cls = vars(control).get('ControlUnconfirmed')
        if (vars(control).get('__name__') == control_name
                and vars(control).get('__file__') == control_path
                and type(cls) is type and cls.__module__ == control_name):
            control_class = cls
            known[cls] = 'native_control_unconfirmed'
    # Unknown exception names may themselves contain private input.
    label = next((label for cls, label in known.items() if type(exc) is cls), 'other')
    result = {'exception_type': label, 'source_frames': []}
    root = os.path.dirname(os.path.abspath(__file__))
    modules = ('user_worker_join.py', 'runtime_observers.py', 'runtime_process.py',
        'runtime_primitives.py', 'runtime_containment.py', 'host_runtime.py',
        'worker_provision.py', 'a0_bootstrap.py', 'onboarding.py',
        'adapters/dsh.py', 'adapters/a0_native.py', 'adapters/a0_profile.py')
    allowed = {os.path.join(root, name): name for name in modules}
    if supervisor_class is not None:
        allowed[supervisor_path] = 'native/friday_native_supervision.py'
    if control_class is not None:
        allowed[control_path] = 'native/friday_native_control.py'
    # Location metadata only: source identity remains the existing loader's job.
    # Exact current/target source trees and the reviewed private helper family.
    # Retarget these fixed roots with the existing update carriers; no basename
    # or cache-prefix trust, imports, file reads, or authority from this mapping.
    scripts = ('friday_install.py', 'friday_ordinary_install.py',
        'friday_ordinary_a0_registration.py', 'friday_worker_declarations.py',
        'install_containment.py')
    source_roots = (
        '<PRIVATE_CACHE>/PRIVATE_REF_dd3c6edc9fb65625/candidate',
        '<PRIVATE_CACHE>/PRIVATE_REF_0c2f108844526c99/candidate',
        '<PRIVATE_CACHE>/PRIVATE_REF_7ba6ff1a47952da0/candidate')
    for source in source_roots:
        allowed.update({os.path.join(source, 'scripts', name): 'scripts/' + name
                        for name in scripts})
    private_roots = (
        '<PRIVATE_CACHE>/PRIVATE_REF_f02249a931643cea/private/_friday_history_source',
        '<PRIVATE_CACHE>/PRIVATE_REF_d5aeb7e29a18462b/binding/_friday_history_source',
        '<PRIVATE_CACHE>/PRIVATE_REF_f9893bd5dc4e37d9/binding/_friday_history_source',
        '<PRIVATE_CACHE>/PRIVATE_REF_1a81c2ccc8b0d68b/binding/_friday_history_source')
    for source in private_roots:
        allowed.update({os.path.join(source, name): 'private/' + name for name in
            ('friday_ordinary_install.py', 'friday_ordinary_a0_registration.py',
             'friday_worker_declarations.py')})
    tb = BaseException.__traceback__.__get__(exc)
    for _ in range(64):
        if tb is None: break
        module = allowed.get(tb.tb_frame.f_code.co_filename)
        if module is not None and 0 < tb.tb_lineno < 2**31:
            result['source_frames'].append({'module': module, 'line': tb.tb_lineno})
            result['source_frames'] = result['source_frames'][-8:]
        tb = tb.tb_next
    result['trace_truncated'] = tb is not None
    return result


def _failure_diagnostic(exc):
    """Fixed error identity and bounded metadata, never arbitrary error text."""
    import math
    from .runtime_process import StopUnconfirmed, CommandFailed, safe_observation
    from .runtime_primitives import Refused
    result = {'failure_location': _failure_location(exc)}
    if isinstance(exc, StopUnconfirmed): return dict(result, error_kind='stop_unconfirmed')
    if isinstance(exc, Refused): return dict(result, error_kind='source_refused')
    if not isinstance(exc, CommandFailed): return dict(result, error_kind='internal_error')
    result.update(error_kind='command_failed', command_observation={})
    observation = getattr(exc, 'observation', None)
    if type(observation) is not dict: return result
    for key, value in safe_observation(observation).items():
        valid = False
        if key in ('timeout', 'reaped', 'namespace_init_exit_verified'):
            valid = type(value) is bool
        elif key == 'returncode':
            valid = type(value) is int and -(2**31) <= value < 2**31
        elif key in ('stdout_bytes', 'stderr_bytes', 'starttime_ticks'):
            valid = type(value) is int and 0 <= value < 2**63
        elif key == 'pid':
            valid = type(value) is int and 0 < value < 2**31
        elif key == 'elapsed_seconds':
            valid = type(value) in (int, float) and 0 <= value <= 86400 and math.isfinite(value)
        elif key in ('stdout_sha256', 'stderr_sha256'):
            valid = type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
        # Refused.reason and observation.reason can contain arbitrary identifiers.
        if valid: result['command_observation'][key] = value
    return result


def qualify(home, binding, generation, prepared, *, verify, accepted_monotonic=None, _source_target=None):
    """One explicit owning-host action, reusing both complete native observers."""
    from .onboarding import _new_file
    from .runtime_containment import Budget
    from .runtime_observers import dsh_observe, dsh_safety_observe, a0_observe
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
        current_main = None
        if _source_target is not None:
            verify()
            current_main = _source_target()
        for kind,c in runtimes.items():
            prepare_inputs(home,binding['runtime_profile'],kind,c,config,
                a0_network=network if kind=='a0' else None, tools=binding['tools'],
                _current_main=current_main)
    sources()
    folder = home / FOLDER
    if folder.exists() or folder.is_symlink(): raise HostUnavailable('qualification_attempt_requires_inspection')
    for p in (home / '.env', home / scope.ONBOARDING): scope._private(p)
    verify()
    seconds = min(600, *(c['budget_seconds'] for c in runtimes.values()))
    budget = Budget(seconds, started=accepted_monotonic); boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    claim = {'boot_id':boot, 'started_mono':budget.deadline-seconds, 'deadline_mono':budget.deadline, 'budget_seconds':seconds}
    from .a0_bootstrap import InitialProbe, own_probe, checked_custody
    # A copied live/per-job plan is not authority to adopt an existing probe.
    if (home / PLAN).exists() or (home / PLAN).is_symlink(): checked_plan(home,binding,runtimes)
    folder.mkdir(mode=0o700)
    def observe_and_preserve(kind, observer, *args, **kwargs):
        observation = observer(*args, **kwargs)
        name = {'dsh_safety':'dsh-safety-observation.json',
            'a0':'a0-observation.json', 'dsh':'dsh-observation.json'}[kind]
        partial = {'schema':'friday.user-worker-stage-observation.v1','home':str(home),
            'profile':binding['runtime_profile'],'binding_sha256':scope._fingerprint(binding),'generation':generation,
            'kind':kind,'original_attempt':claim,'preparations':prepared,'observation':observation,
            'effects':'OBSERVATION_ONLY','per_job_authority':'NOT_GRANTED'}
        _new_file(folder / name,(json.dumps(partial,sort_keys=True)+'\n').encode())
        return observation
    stage = 'dsh_safety'
    try:
        scratch = folder / 'dsh-safety'; scratch.mkdir(mode=0o700)
        safety = budget.call(observe_and_preserve,'dsh_safety',dsh_safety_observe,runtimes['dsh'],home,scratch,budget)
        stage = 'post_safety_verify'
        verify()
        stage = 'post_safety_credentials'
        credentials = {n: pin(home / n)['sha256'] if (home / n).exists() else None for n in ('.env','auth.json')}
        stage = 'a0_probe_prepare'
        probe = InitialProbe(runtimes['a0'], binding, generation, prepared, budget, verify, original_seconds=seconds)
        stage = 'a0_probe_start'
        with own_probe(probe) as plan:
            stage = 'a0_probe_plan'
            checked_plan(home, binding, runtimes)
            original = {'schema':'friday.user-worker-qualification.v1','home':str(home),
                'profile':binding['runtime_profile'],'binding_sha256':scope._fingerprint(binding),'generation':generation,
                'original_attempt':claim,'preparations':prepared,'credentials':credentials,'plan':plan,
                'bootstrap_original':pin(home / 'workers/a0/bootstrap/original.json'),'binding':binding}
            verify()
            _new_file(home / INTENT, (json.dumps(original,sort_keys=True)+'\n').encode())
            stage = 'a0_observe'
            a0 = budget.call(observe_and_preserve,'a0',a0_observe, runtimes['a0'], plan, budget, probe_owner=probe)
            verify()
            stage = 'a0_probe_cleanup'
        stage = 'a0_custody'
        custody = checked_custody(home, binding, generation, prepared, plan)
        # Native cessation precedes Harness observations/readiness publication;
        # both observations still consume the SAME original setup deadline.
        stage = 'dsh_observe'
        scratch = folder / 'dsh-probe'; scratch.mkdir(mode=0o700)
        dsh = budget.call(observe_and_preserve,'dsh',dsh_observe, runtimes['dsh'], home, scratch, budget)
        dsh['safety'] = safety
        stage = 'post_observation_verify'
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
        stage = 'deployment_proof'
        for c in runtimes.values(): budget.call(deployment_observations,c,proof,claim,folder)
        verify(); budget.call(_new_file,home / PROOF,(json.dumps(proof,sort_keys=True)+'\n').encode())
        stage = 'readiness_receipts'
        for kind,c in runtimes.items():
            verify(); receipt=readiness_receipt(c,[prepared[kind],pin(home / PROOF)])
            budget.call(_new_file,Path(c['runtime_receipt']['path']),(json.dumps(receipt,sort_keys=True)+'\n').encode())
            c['runtime_receipt']=pin(Path(c['runtime_receipt']['path']))
        return runtimes
    except BaseException as exc:
        from .runtime_process import StopUnconfirmed
        failure={'state':'STOP_UNCONFIRMED' if isinstance(exc,StopUnconfirmed) else 'REFUSED_OR_UNCERTAIN',
            'original_attempt':claim,'retry_authorized':False,'a0_probe_cleanup':'OWN_INITIAL_PROBE_CUSTODY',
            'qualification_stage':stage}
        try: failure.update(_failure_diagnostic(exc))
        except Exception:
            failure['error_kind'] = 'diagnostic_unavailable'
        try: _new_file(folder / 'failure.json',(json.dumps(failure,sort_keys=True)+'\n').encode())
        except OSError: pass
        raise


def deployment_health(c, *, binding=None, generation=None):
    """Own producer/proof/inputs/clock, followed by the shared native consumer."""
    from hermes_cli import friday_user_scope as scope
    from .host_runtime import deployment_observations, a0_deployment_contract, _dsh_web
    from .worker_web import web_policy
    c=validate_runtime(c)
    postboot = _postboot_dsh_health_if_present(c, binding=binding, generation=generation)
    if postboot is not None: return postboot
    a0_postboot = _postboot_a0_health_if_present(c, binding=binding, generation=generation)
    if a0_postboot is not None: return a0_postboot
    qualified_c = _s436_qualified_runtime(c)
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
    completion = proof.get('post_a0_completion')
    completion_claim = None
    if completion is not None:
        checked_completion = _r481_completion.checked
        completion_document = _r481_completion.document
        completion_claim = completion_document(completion['original'])['original_attempt']
        checked_completion(c,proof,completion_claim,folder)
        if (folder/'completion-failure.json').exists() or (folder/'completion-failure.json').is_symlink():
            raise HostUnavailable('incomplete_post_a0_completion')
    if (original.get('schema')!='friday.user-worker-qualification.v1' or original.get('home')!=str(home)
            or original.get('profile')!=c['runtime_profile'] or original.get('binding_sha256')!=setup['binding_sha256']
            or (binding is not None and original['binding_sha256']!=scope._fingerprint(binding))
            or (generation is not None and original['generation']!=generation)
            or (completion is None and ((folder / 'failure.json').exists() or (folder / 'failure.json').is_symlink()))):
        raise HostUnavailable('foreign_or_incomplete_user_qualification')
    claim=original['original_attempt'] if completion is None else completion_claim
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
            or expected!={k:v for k,v in qualified_c.items() if k!='runtime_receipt'}
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
    if completion is not None:
        checked_custody = _r481_completion.custody
    custody = checked_custody(home,original['binding'],original['generation'],original['preparations'],original['plan'])
    if (proof.get('bootstrap_custody')!=custody or custody['original']!=original['bootstrap_original']
            or scope._fingerprint(original['binding'])!=original['binding_sha256']):
        raise HostUnavailable('user_worker_bootstrap_custody_changed')
    return deployment_observations(c,proof,claim,folder)


# Exact R481 missing-publication implementation; existing module inventory retained.
import ast as _r481_ast
import copy as _r481_copy
import hashlib as _r481_hashlib
import json as _r481_json
import math as _r481_math
import os as _r481_os
from pathlib import Path as _r481_Path
import stat as _r481_stat
import time as _r481_time
_r481_H = _r481_Path('<INSTALL_HOME>')
_r481_HOME = _r481_H / 'profiles/telegram-bot-9000000001'
_r481_FIXED = {'original': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/qualification/original.json', 'sha256': 'PRIVATE_REF_bd592b7897e03291'}, 'a0_stage': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/qualification/a0-observation.json', 'sha256': 'PRIVATE_REF_8ff81e395f7ee6a4'}, 'safety_stage': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/qualification/dsh-safety-observation.json', 'sha256': 'PRIVATE_REF_22000d625ee13032'}, 'local_failure': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/qualification/failure.json', 'sha256': 'PRIVATE_REF_5e457d6d4e3cab48'}, 'plan': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/a0/probe-plan.json', 'sha256': 'PRIVATE_REF_b79094bf9180ee61'}, 'bootstrap_original': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/a0/bootstrap/original.json', 'sha256': 'PRIVATE_REF_250f951a6c1e3989'}, 'state': {'path': '<INSTALL_HOME>/profiles/telegram-bot-9000000001/workers/a0/bootstrap/state.json', 'sha256': 'PRIVATE_REF_f1c6476ec89a7f31'}, 'failure': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/FAILURE.private.json', 'sha256': 'PRIVATE_REF_0ddcbe86e6c2b63a'}, 'returned': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/QUALIFICATION-PROCESS-RETURNED.json', 'sha256': 'PRIVATE_REF_8517fbcb0691f6ed'}, 'worker_clock': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/STAGE-worker_clock.private.json', 'sha256': 'PRIVATE_REF_97db8fae347965ce'}, 'outer_clock': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/ORIGINAL-CLOCK.json', 'sha256': 'PRIVATE_REF_0f1f9aae1eedb1d9'}, 'stage_a0': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/STAGE-a0.private.json', 'sha256': 'PRIVATE_REF_c433362c819d4140'}, 'stage_safety': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/STAGE-dsh_safety_reused.private.json', 'sha256': 'PRIVATE_REF_15d5b8e0fb156801'}, 'cleanup_control': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8491b39e1d38f08a/ACTUAL-CLEANUP-CONTROL.json', 'sha256': 'PRIVATE_REF_84026347b38d60ff'}, 'cleanup': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0b47e912bda1a7d3/actual-maintenance/complete.json', 'sha256': 'PRIVATE_REF_a8e2e6aff4696ce9'}, 'postcheck': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0b47e912bda1a7d3/POSTCHECK.json', 'sha256': 'PRIVATE_REF_a6c625ac36e1ea36'}, 'postcheck_review': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0b47e912bda1a7d3/POSTCHECK-IDENTITY-REVIEW.json', 'sha256': 'PRIVATE_REF_ef1505fecef227e7'}, 'cleanup_returned': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0b47e912bda1a7d3/RETURNED.json', 'sha256': 'PRIVATE_REF_e6c209881eae0dcf'}, 'reconcile': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0b47e912bda1a7d3/reconcile_r481.py', 'sha256': 'PRIVATE_REF_0bbede6f8675ed58'}, 'reconcile_refs': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0b47e912bda1a7d3/REFS.json', 'sha256': 'PRIVATE_REF_ae3d2ff5ef235017'}, 'user_worker_join': {'path': '<INSTALL_HOME>/plugins/friday_rework/user_worker_join.py', 'sha256': 'PRIVATE_REF_cea5a3341a28c48a'}, 'host_runtime': {'path': '<INSTALL_HOME>/plugins/friday_rework/host_runtime.py', 'sha256': 'PRIVATE_REF_3575e20db5522ff3'}, 'a0_bootstrap': {'path': '<INSTALL_HOME>/plugins/friday_rework/a0_bootstrap.py', 'sha256': 'PRIVATE_REF_fbf8ffa5d8d216aa'}, 'onboarding': {'path': '<INSTALL_HOME>/plugins/friday_rework/onboarding.py', 'sha256': 'PRIVATE_REF_641c2e88ad91e9f8'}, 'runtime_observers': {'path': '<INSTALL_HOME>/plugins/friday_rework/runtime_observers.py', 'sha256': 'PRIVATE_REF_b9e4436f6f9c0105'}, 'worker_provision': {'path': '<INSTALL_HOME>/plugins/friday_rework/worker_provision.py', 'sha256': 'PRIVATE_REF_40add33516caa85d'}, 'safety_inputs': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_321bff396096f309/STAGE-remaining_inputs.private.json', 'sha256': 'PRIVATE_REF_6a10dca036f6cf1c'}, 'prior_helper': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_c440b4c181437c1f/final-chain/bound-chain-s414-actual/maintenance_remaining.py', 'sha256': 'PRIVATE_REF_5fcd6987351c8911'}, 'historical_dsh': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_06dbe6e5a39508c9/preserved-baseline/PRIVATE_REF_39dc7afaaf0f0a17.json', 'sha256': 'PRIVATE_REF_1977d8c0ffe8b789'}, 'dsh_observation': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8fea5ab2e81f6c3c/OBSERVATION.json', 'sha256': 'PRIVATE_REF_24dbdd928c0be4e7'}, 'dsh_returned': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8fea5ab2e81f6c3c/RETURNED.json', 'sha256': 'PRIVATE_REF_7a10918aff771944'}, 'dsh_clock': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8fea5ab2e81f6c3c/ORIGINAL-CLOCK.json', 'sha256': 'PRIVATE_REF_aa482191d5a256fe'}, 'dsh_accepted': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8fea5ab2e81f6c3c/ROOT-OBSERVATION-ACCEPTED.json', 'sha256': 'PRIVATE_REF_dc625bed56c1b6a7'}, 'dsh_control': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8491b39e1d38f08a/ACTUAL-DSH-CONTROL.json', 'sha256': 'PRIVATE_REF_c4d3564935461c35'}, 'current_safety_observation': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_59d322e7239b0e48/OBSERVATION.json', 'sha256': 'PRIVATE_REF_3c438f2948c8adda'}, 'current_safety_returned': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_59d322e7239b0e48/RETURNED.json', 'sha256': 'PRIVATE_REF_cd791b5d95b5bd67'}, 'current_safety_clock': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_59d322e7239b0e48/ORIGINAL-CLOCK.json', 'sha256': 'PRIVATE_REF_23aa46f62d202593'}, 'current_safety_acceptance': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_59d322e7239b0e48/ROOT-OBSERVATION-ACCEPTED.json', 'sha256': 'PRIVATE_REF_f68e126b16647a28'}, 'current_safety_native_return': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_59d322e7239b0e48/NATIVE-RETURN.json', 'sha256': 'PRIVATE_REF_a2b7d19a0d6291cc'}, 'current_safety_control': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8491b39e1d38f08a/ACTUAL-SAFETY-CONTROL.json', 'sha256': 'PRIVATE_REF_54fad0378cc83421'}}
_r481_SCHEMA = 'friday.r481.post-a0-completion.v1'

def _r481_need(value, reason):
    if not value:
        raise RuntimeError(reason)

def _r481_read(reference):
    _r481_need(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'exact_reference_required')
    path = _r481_Path(reference['path'])
    _r481_need(path.is_absolute() and path.resolve() == path and (len(reference['sha256']) == 64) and all((c in '0123456789abcdef' for c in reference['sha256'])), 'exact_reference_required')
    for parent in path.parents:
        info = parent.lstat()
        _r481_need(_r481_stat.S_ISDIR(info.st_mode) and info.st_uid in (0, _r481_os.getuid()) and (not info.st_mode & 18), 'protected_parent_required')
    fd = _r481_os.open(path, _r481_os.O_RDONLY | _r481_os.O_NOFOLLOW | _r481_os.O_NONBLOCK)
    try:
        before = _r481_os.fstat(fd)
        _r481_need(_r481_stat.S_ISREG(before.st_mode) and before.st_uid == _r481_os.getuid() and (before.st_nlink == 1) and (not before.st_mode & 2) and (not before.st_mode & 16 or any((p.stat().st_uid == _r481_os.getuid() and _r481_stat.S_IMODE(p.stat().st_mode) == 448 for p in path.parents))), 'protected_file_required')
        raw = _r481_os.pread(fd, 16 * 1024 * 1024 + 1, 0)
        fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        after = _r481_os.fstat(fd)
        named = path.lstat()
        _r481_need(all((getattr(before, k) == getattr(after, k) == getattr(named, k) for k in fields)) and len(raw) <= 16 * 1024 * 1024 and (_r481_hashlib.sha256(raw).hexdigest() == reference['sha256']), 'reference_changed')
        return raw
    finally:
        _r481_os.close(fd)

def _r481_document(reference):

    def unique(pairs):
        result = {}
        for key, value in pairs:
            _r481_need(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    return _r481_json.loads(_r481_read(reference), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))

def _r481_claim_checked(claim):
    _r481_need(type(claim) is dict and set(claim) == {'boot_id', 'started_mono', 'deadline_mono', 'budget_seconds'} and (type(claim['boot_id']) is str) and (type(claim['budget_seconds']) is int) and (30 <= claim['budget_seconds'] <= 1800) and all((type(claim[k]) in (int, float) and _r481_math.isfinite(claim[k]) for k in ('started_mono', 'deadline_mono'))) and (0 < claim['started_mono'] < claim['deadline_mono']) and (claim['deadline_mono'] == claim['started_mono'] + claim['budget_seconds']), 'finite_original_claim_required')
    return claim

def _r481_retained():
    """Bounded immutable read, not a history walk or a live effect."""
    d = {k: _r481_document(_r481_FIXED[k]) for k in ('original', 'a0_stage', 'safety_stage', 'local_failure', 'plan', 'bootstrap_original', 'state', 'failure', 'returned', 'worker_clock', 'outer_clock', 'stage_a0', 'stage_safety', 'cleanup_control', 'cleanup', 'postcheck', 'postcheck_review', 'cleanup_returned')}
    old = d['original']
    stage = d['a0_stage']
    plan = d['plan']
    state = d['state']
    claim = _r481_claim_checked(old['original_attempt'])
    _r481_need(old['home'] == str(_r481_HOME) and old['profile'] == 'telegram-bot-9000000001' and (old['schema'] == 'friday.user-worker-qualification.v1') and (old['plan'] == _r481_FIXED['plan']) and (old['bootstrap_original'] == _r481_FIXED['bootstrap_original']) and (stage['schema'] == 'friday.user-worker-stage-observation.v1') and (stage['kind'] == 'a0') and (stage['effects'] == 'OBSERVATION_ONLY') and (stage['per_job_authority'] == 'NOT_GRANTED') and all((stage[k] == old[k] for k in ('home', 'profile', 'binding_sha256', 'generation', 'preparations', 'original_attempt'))) and (stage['observation']['plan'] == _r481_FIXED['plan']) and (d['stage_a0'] == {'fresh_stage': True, 'observation': _r481_FIXED['a0_stage']}) and (d['worker_clock']['worker'] == claim), 'exact_R481_stage_required')
    result = d['returned']
    _r481_need(result['reaped'] is True and result['exit_code'] == 1 and (result['qualification_accepted'] is False) and (claim['started_mono'] <= result['process_ended_monotonic'] < claim['deadline_mono']) and (result['original_clock'] == d['outer_clock']), 'bounded_original_completion_witness_required')
    from datetime import datetime
    upper_unix = datetime.fromisoformat(result['at_moscow']).timestamp()
    _r481_need(plan['boot_id'] == claim['boot_id'] and plan['accepted_monotonic_ns'] / 1000000000.0 == claim['started_mono'] and (plan['original_budget_seconds'] == claim['budget_seconds']) and (plan['accepted_unix'] <= upper_unix < plan['deadline_unix']), 'A0_completion_interval_required')
    _r481_need(d['local_failure']['qualification_stage'] == 'a0_probe_cleanup' and d['local_failure']['retry_authorized'] is False and (d['local_failure']['original_attempt'] == claim) and (state['phase'] == 'STOP_UNCONFIRMED') and (state['settlement'] is None) and (state['pending_sample'] is False) and (state['sampling_uncertainty'] is False) and (state['route']['settlement']['status'] == 'STOP_CONFIRMED'), 'preserved_failed_cleanup_required')
    ctl = d['cleanup_control']
    clean = d['cleanup']
    post = d['postcheck']
    _r481_need(ctl['completed_maintenance'] == _r481_FIXED['cleanup'] and ctl['postcheck'] == _r481_FIXED['postcheck'] and (ctl['postcheck_identity_review'] == _r481_FIXED['postcheck_review']) and (clean['schema'] == 'frw.Root.R481.separate-reconciliation.v1') and (clean['old_attempt_closed'] is True) and (clean['old_stop_replayed'] is False) and (clean['original_failure_rewritten'] is False) and (clean['original_a0_observation'] == _r481_FIXED['a0_stage']) and (clean['original_failure'] == _r481_FIXED['failure']) and (clean['keys'] == 'REMOVED') and (clean['retirement']['status'] == 'INITIAL_PROBE_RETIRED') and (clean['container_id'] == stage['observation']['container_id']) and (clean['retirement']['container_id'] == clean['container_id']) and (clean['new_route']['status'] == 'STOP_CONFIRMED') and (post['phase'] == 'CURRENT_INPUTS_VERIFIED') and (post['retirement'] is True) and (post['keys_removed'] is True) and (post['original_success_reusable'] is True) and (post['maintenance_completion'] == _r481_FIXED['cleanup']), 'accepted_exact_cleanup_required')
    safety = d['safety_stage']
    _r481_claim_checked(safety['original_attempt'])
    _r481_need(safety['kind'] == 'dsh_safety' and safety['effects'] == 'OBSERVATION_ONLY' and (safety['per_job_authority'] == 'NOT_GRANTED') and all((safety[k] == old[k] for k in ('home', 'profile', 'binding_sha256', 'generation'))) and (safety['original_attempt'] == old['maintenance_continuation']['historical_attempt']) and (d['stage_safety']['canonical_copy'] == _r481_FIXED['safety_stage']), 'preserved_safety_binding_required')
    return d

def _r481_metadata(original_ref):
    return {'schema': _r481_SCHEMA, 'original': original_ref, 'retained': {k: _r481_FIXED[k] for k in ('original', 'a0_stage', 'safety_stage', 'local_failure', 'returned', 'cleanup', 'postcheck', 'cleanup_control')}, 'A0_time': 'BOUNDED_BY_ORIGINAL_WORKER_CLAIM_AND_RETURN_NOT_EXACT_TIMESTAMP'}

def _r481_safety_checked(refs, old, runtime):
    """Require actual CURRENT-BOOT native safety; old report remains provenance only."""
    from .runtime_observers import checked_dsh_safety, DSH_NATIVE_SAFETY
    base = _r481_Path('<PRIVATE_CACHE>/PRIVATE_REF_59d322e7239b0e48')
    _r481_need(refs == {k: _r481_FIXED['current_safety_' + k] for k in ('observation', 'returned', 'clock', 'acceptance')}, 'actual_current_safety_refs_required')
    for key, name in (('observation', 'OBSERVATION.json'), ('returned', 'RETURNED.json'), ('clock', 'ORIGINAL-CLOCK.json'), ('acceptance', 'ROOT-OBSERVATION-ACCEPTED.json')):
        _r481_need(refs[key]['path'] == str(base / name), 'actual_current_safety_path_required')
    stage = _r481_document(refs['observation'])
    returned = _r481_document(refs['returned'])
    clock = _r481_document(refs['clock'])
    accepted = _r481_document(refs['acceptance'])
    _r481_need(not _r481_os.path.lexists(base / 'FAILURE.json'), 'current_safety_failure_requires_reconciliation')
    claim = _r481_claim_checked(stage['original_attempt'])
    current = old['original_attempt']['boot_id']
    _r481_need(claim['boot_id'] == current and stage['kind'] == 'dsh_safety' and (stage['schema'] == 'friday.user-worker-stage-observation.v1') and (stage['effects'] == 'OBSERVATION_ONLY') and (stage['per_job_authority'] == 'NOT_GRANTED') and all((stage[k] == old[k] for k in ('home', 'profile', 'binding_sha256', 'generation', 'preparations'))) and (claim['started_mono'] <= stage['observed']['monotonic'] < claim['deadline_mono']) and (clock['boot_id'] == current) and (clock['started_mono'] == claim['started_mono']) and (clock['deadline_mono'] >= claim['deadline_mono']) and (type(clock['budget_seconds']) is int) and (30 <= clock['budget_seconds'] <= 300) and (clock['deadline_mono'] == clock['started_mono'] + clock['budget_seconds']) and (type(clock['reserve_seconds']) is int) and (0 < clock['reserve_seconds'] < clock['budget_seconds']) and (claim['deadline_mono'] <= clock['deadline_mono'] - clock['reserve_seconds']) and (returned['observation'] == refs['observation']) and (returned['clock'] == refs['clock']) and (returned['services_preserved'] is True) and (accepted['observation'] == refs['observation']) and (accepted['clock'] == refs['clock']) and (accepted['return'] == refs['returned']) and (accepted['schema'] == 'frw.Root.R483.actual-safety-acceptance.v1') and (accepted['accepted'] is True) and (accepted['process_completed_reaped'] is True) and (type(accepted['exit_code']) is int) and (accepted['exit_code'] == 0) and (accepted['A0_and_R482_not_replayed'] is True) and (accepted['services_preserved'] is True) and (accepted['full_BOTH_qualification'] is False) and (accepted['native_return'] == stage['native_return'] == _r481_FIXED['current_safety_native_return']) and (stage['root_operation_clock'] == refs['clock']) and (stage['stage_folder'] == str(_r481_HOME / 'workers/qualification/dsh-safety')), 'actual_current_safety_join_changed')
    control = _r481_document(_r481_FIXED['current_safety_control'])
    _r481_need(control['accepted'] == refs['acceptance'] and control['safety'] == refs['observation'] and (control['clock'] == refs['clock']), 'Root_actual_safety_control_changed')
    _r481_document(_r481_FIXED['current_safety_native_return'])
    observation = stage['observation']
    checked_dsh_safety(observation['report'], runtime, _r481_HOME)
    _r481_need(observation['specimen_sha256'] == _r481_hashlib.sha256(DSH_NATIVE_SAFETY.encode()).hexdigest(), 'current_safety_specimen_changed')
    execution = observation['execution']
    env = execution['resource_envelope']
    expected = 'friday-qualify-dsh-' + _r481_hashlib.sha256(str(_r481_HOME / 'workers/qualification/dsh-safety').encode()).hexdigest()[:24] + '-1.scope'
    _r481_need(execution['returncode'] == 0 and type(execution['returncode']) is int and (execution['reaped'] is True) and (execution['timeout'] is False) and (set(env) == {'unit', 'memory_bytes', 'cpu_percent', 'tasks', 'boot_id', 'deadline'}) and (env['unit'] == expected) and (env['boot_id'] == current) and all((type(env[k]) is type(runtime['dsh'][k]) and env[k] == runtime['dsh'][k] for k in ('memory_bytes', 'cpu_percent', 'tasks'))) and (type(env['deadline']) in (int, float)) and _r481_math.isfinite(env['deadline']) and (claim['started_mono'] <= env['deadline'] <= claim['deadline_mono']), 'current_safety_resources_changed')
    return stage

def _r481_dsh_checked(refs, old):
    """Actual Root R482 output with its original300 clock, never a future flag."""
    base = _r481_Path('<PRIVATE_CACHE>/PRIVATE_REF_8fea5ab2e81f6c3c')
    _r481_need(refs == {k: _r481_FIXED['dsh_' + k] for k in ('observation', 'returned', 'clock')}, 'actual_Root_DSH_refs_required')
    for key, name in (('observation', 'OBSERVATION.json'), ('returned', 'RETURNED.json'), ('clock', 'ORIGINAL-CLOCK.json')):
        _r481_need(refs[key]['path'] == str(base / name), 'actual_Root_DSH_path_required')
    stage = _r481_document(refs['observation'])
    returned = _r481_document(refs['returned'])
    clock = _r481_document(refs['clock'])
    accepted = _r481_document(_r481_FIXED['dsh_accepted'])
    control = _r481_document(_r481_FIXED['dsh_control'])
    _r481_need(control['accepted_DSH_observation'] == _r481_FIXED['dsh_accepted'] and accepted['observation'] == refs['observation'] and (accepted['return'] == refs['returned']) and (accepted['clock'] == refs['clock']) and (accepted['accepted_observation_only'] is True) and (accepted['commands_reaped'] == 5) and (accepted['smoke_passed'] == 4) and (accepted['network_passed'] is True) and (accepted['no_A0_replay'] is True) and (accepted['services_preserved'] is True) and (accepted['full_BOTH_or_user_acceptance'] is False), 'actual_Root_DSH_acceptance_required')
    _r481_need(not _r481_os.path.lexists(base / 'FAILURE.json'), 'Root_DSH_failure_requires_reconciliation')
    claim = _r481_claim_checked(stage['original_attempt'])
    _r481_need(clock['schema'] == 'frw.Root.R482.remaining-dsh-clock.v1' and clock['budget_seconds'] == 300 and (clock['reserve_seconds'] == 30) and (clock['old_R481_clock_reset'] is False) and (claim == {'boot_id': clock['boot_id'], 'started_mono': clock['started_mono'], 'deadline_mono': clock['deadline_mono'] - 30, 'budget_seconds': 270}) and (stage['root_operation_clock'] == refs['clock']) and (claim['boot_id'] == old['original_attempt']['boot_id']) and (stage['kind'] == 'dsh') and (stage['effects'] == 'OBSERVATION_ONLY') and (stage['per_job_authority'] == 'NOT_GRANTED') and (stage['separate_remaining_stage'] is True) and all((stage[k] == old[k] for k in ('home', 'profile', 'binding_sha256', 'generation', 'preparations'))) and (claim['started_mono'] <= stage['observed']['monotonic'] < claim['deadline_mono']) and (returned['observation'] == refs['observation']) and (returned['clock'] == refs['clock']) and (returned['services_preserved'] is True) and (returned['A0_replayed'] is False) and (returned['BOTH_qualified'] is False) and (returned['user_task'] is False), 'actual_Root_DSH_join_changed')
    return stage

def _r481_completion_source(name, reference):
    """Keep qualification source facts exact across the exact bounded source updates."""
    from .worker_provision import pin as raw_quota_pin
    source_snapshot = _s436_source_snapshot()
    def quota_pin(path):
        return dict(raw_quota_pin(_r481_Path(source_snapshot.get(str(path), str(path)))), path=str(path))
    # The one exact quota successor preserves the existing completion chain.
    raw_quota_read = globals()['_r481_read']
    def quota_read(reference):
        return raw_quota_read(dict(reference,path=source_snapshot.get(reference['path'],reference['path'])))
    def quota_document(reference):
        return globals()['_r481_document'](dict(reference,path=source_snapshot.get(reference['path'],reference['path'])))
    quota_snapshot = {}
    quota_baseline = quota_document({'path': '<PRIVATE_CACHE>/PRIVATE_REF_1d654b5ec556da58/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_93619d7991a4a18d'})
    quota_input = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_8814e013e5401b96/integrated-source-runtime/INPUT-DSH-ADMISSION.NEXT.json', 'sha256': 'PRIVATE_REF_bcfaceaf5af3251c'}
    quota_marker_ref = quota_pin(_r481_H / 'FRIDAY-INSTALL.json')
    quota_marker = quota_document(quota_marker_ref)
    _r481_need(quota_baseline.get('accepted') is True
        and quota_baseline.get('accepted_source_only') is True
        and quota_baseline.get('runtime_or_user_semantics_accepted') is False
        and quota_baseline.get('current_input') == quota_input,
        'completion_quota_baseline_required')
    if quota_marker_ref != quota_baseline['marker']:
        quota_tx = _r481_H / ('preparation/ordinary-source-update-' + quota_input['sha256'])
        quota_commit_ref = quota_pin(quota_tx / 'committed.json')
        quota_intent_ref = quota_pin(quota_tx / 'intent.json')
        quota_commit = quota_document(quota_commit_ref)
        quota_intent = quota_document(quota_intent_ref)
        quota_plan = quota_document(quota_commit['plan'])
        quota_request = quota_document(quota_plan['request'])
        quota_previous = quota_document(quota_input)
        quota_current = quota_document(quota_commit['current_input'])
        quota_native = 'hermes-agent/hermes_cli/plugins_state.py'
        quota_join = 'plugins/friday_rework/user_worker_join.py'
        quota_metadata = {'FRIDAY-INSTALL.json', 'hermes-agent.source.json', 'hermes-agent/install-stamp.json'}
        quota_names = quota_metadata | {quota_native, quota_join}
        quota_additions = {'patches/hermes/friday-worker-state-quota.patch': 'PRIVATE_REF_f926e74b64322890',
            'patches/hermes/friday-worker-state-quota-manifest.json': 'PRIVATE_REF_c6de1272b452c1d5'}
        _r481_need(quota_intent['schema'] == 'friday.ordinary-telegram-source-update-transaction.v1'
            and quota_intent['state'] == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and quota_commit['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and quota_plan['schema'] == 'friday.worker-state-quota-native-plugin-plan.v1'
            and quota_request['schema'] == 'friday.ordinary-telegram-source92-feature-update.v1'
            and quota_request['home'] == str(_r481_H)
            and quota_intent['plan'] == quota_commit['plan']
            and quota_intent['request_sha256'] == quota_plan['request']['sha256']
            and quota_request['previous_input'] == quota_commit['previous_input'] == quota_input
            and quota_request['current_input'] == quota_commit['current_input']
            and quota_marker['ordinary_source_update_request'] == quota_plan['request']
            and quota_marker['input_sha256'] == quota_commit['current_input']['sha256']
            and quota_marker_ref['sha256'] == quota_commit['after']['FRIDAY-INSTALL.json']['sha256']
            and set(quota_plan['before']) == set(quota_plan['after']) == set(quota_intent['before']) == set(quota_commit['after']) == quota_names
            and set(quota_current['project_files']) == set(quota_previous['project_files']) | set(quota_additions)
            and not (set(quota_previous['project_files']) & set(quota_additions))
            and {k: quota_current['project_files'][k] for k in quota_additions} == quota_additions
            and {k:v for k,v in quota_previous.items() if k != 'project_files'} == {k:v for k,v in quota_current.items() if k != 'project_files'}
            and {k for k in quota_previous['project_files'] if quota_previous['project_files'][k] != quota_current['project_files'][k]} == {quota_join}
            and quota_marker['plugin_files'] == {k:v for k,v in quota_current['project_files'].items() if k.startswith('plugins/friday_rework/')}
            and quota_commit['source_receipt_sha256'] == quota_marker['source_receipt_sha256'] == 'PRIVATE_REF_0b2edba82b83b89f',
            'completion_exact_quota_transaction_required')
        quota_expected_before = {
            quota_native: {'mode': 0o600, 'sha256': 'PRIVATE_REF_0213b97ea903251f'},
            quota_join: {'mode': 0o600, 'sha256': 'PRIVATE_REF_526c0d505f1566f9'},
            'FRIDAY-INSTALL.json': {'mode': 0o600, 'sha256': quota_baseline['marker']['sha256']},
            'hermes-agent.source.json': {'mode': 0o600, 'sha256': 'PRIVATE_REF_81e360373bafbd78'},
            'hermes-agent/install-stamp.json': {'mode': 0o600, 'sha256': 'PRIVATE_REF_afa76fb8eaf16d6e'}}
        quota_expected_after = {
            quota_native: {'mode': 0o600, 'sha256': 'PRIVATE_REF_8d0f8e18931baf21'},
            quota_join: {'mode': 0o600, 'sha256': quota_current['project_files'][quota_join]},
            'FRIDAY-INSTALL.json': {'mode': 0o600, 'sha256': quota_marker_ref['sha256']},
            'hermes-agent.source.json': {'mode': 0o600, 'sha256': 'PRIVATE_REF_0b2edba82b83b89f'},
            'hermes-agent/install-stamp.json': {'mode': 0o600, 'sha256': 'PRIVATE_REF_29800c802189ddf1'}}
        _r481_need(quota_intent['before'] == quota_expected_before
            and quota_commit['after'] == quota_expected_after,
            'completion_quota_images_changed')
        for item in quota_names:
            before, after = quota_expected_before[item], quota_expected_after[item]
            _r481_need(quota_plan['before'][item]['sha256'] == before['sha256']
                and quota_plan['before'][item]['mode'] == before['mode']
                and quota_plan['after'][item]['sha256'] == after['sha256'],
                'completion_quota_plan_image_changed')
            quota_read({'path': str(quota_tx / 'before' / item), 'sha256': before['sha256']})
            quota_read({'path': str(_r481_H / item), 'sha256': after['sha256']})
            quota_snapshot[str(_r481_H / item)] = str(quota_tx / 'before' / item)
        _r481_need(quota_pin(quota_tx / 'committed.json') == quota_commit_ref
            and quota_pin(quota_tx / 'intent.json') == quota_intent_ref
            and quota_pin(_r481_H / 'FRIDAY-INSTALL.json') == quota_marker_ref,
            'completion_quota_transaction_changed')
    def admission_read(reference):
        return quota_read(dict(reference, path=quota_snapshot.get(reference['path'], reference['path'])))
    def admission_document(reference):
        return quota_document(dict(reference, path=quota_snapshot.get(reference['path'], reference['path'])))
    def admission_pin(path):
        return dict(quota_pin(_r481_Path(quota_snapshot.get(str(path), str(path)))), path=str(path))
    # One bounded admission-diagnostic successor of the accepted S435 source.
    # Keep all historical receipts unchanged and peel only its checked images.
    admission_snapshot = {}
    admission_baseline_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_30befb28a016b8d3/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_bcb190e55f206986'}
    admission_baseline = admission_document(admission_baseline_ref)
    admission_input_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_a8955b5869595b96/source-runtime/INPUT-DSH-COMBINED.NEXT.json', 'sha256': 'PRIVATE_REF_a2f57e55b1a5c7dd'}
    admission_marker_ref = admission_pin(_r481_H / 'FRIDAY-INSTALL.json')
    admission_marker = admission_document(admission_marker_ref)
    _r481_need(admission_baseline.get('accepted') is True
        and admission_baseline.get('accepted_source_only') is True
        and admission_baseline.get('runtime_or_user_semantics_accepted') is False
        and admission_baseline.get('current_input') == admission_input_ref,
        'completion_admission_baseline_required')
    if admission_marker_ref != admission_baseline['marker']:
        admission_tx = _r481_H / ('preparation/ordinary-source-update-' + admission_input_ref['sha256'])
        admission_commit_ref = admission_pin(admission_tx / 'committed.json')
        admission_intent_ref = admission_pin(admission_tx / 'intent.json')
        admission_commit = admission_document(admission_commit_ref)
        admission_intent = admission_document(admission_intent_ref)
        admission_plan = admission_document(admission_commit['plan'])
        admission_request = admission_document(admission_plan['request'])
        admission_previous = admission_document(admission_input_ref)
        admission_current = admission_document(admission_commit['current_input'])
        admission_changed = {'plugins/friday_rework/host.py', 'plugins/friday_rework/user_worker_join.py'}
        admission_metadata = {'FRIDAY-INSTALL.json', 'hermes-agent.source.json', 'hermes-agent/install-stamp.json'}
        admission_names = admission_changed | admission_metadata
        _r481_need(admission_intent['schema'] == 'friday.ordinary-telegram-source-update-transaction.v1'
            and admission_intent['state'] == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and admission_commit['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and admission_plan['schema'] == 'friday.dsh-retained-existing-plugin-overlay-plan.v1'
            and admission_request['schema'] == 'friday.ordinary-telegram-source92-feature-update.v1'
            and admission_request['home'] == str(_r481_H)
            and admission_intent['plan'] == admission_commit['plan']
            and admission_intent['request_sha256'] == admission_plan['request']['sha256']
            and admission_request['previous_input'] == admission_commit['previous_input'] == admission_input_ref
            and admission_request['current_input'] == admission_commit['current_input']
            and admission_marker['ordinary_source_update_request'] == admission_plan['request']
            and admission_marker['input_sha256'] == admission_commit['current_input']['sha256']
            and admission_marker_ref['sha256'] == admission_commit['after']['FRIDAY-INSTALL.json']['sha256']
            and set(admission_plan['before']) == set(admission_plan['after']) == set(admission_intent['before']) == set(admission_commit['after']) == admission_names
            and set(admission_previous['project_files']) == set(admission_current['project_files'])
            and {k:v for k,v in admission_previous.items() if k != 'project_files'} == {k:v for k,v in admission_current.items() if k != 'project_files'}
            and {k for k in admission_previous['project_files'] if admission_previous['project_files'][k] != admission_current['project_files'][k]} == admission_changed
            and admission_current['project_files']['plugins/friday_rework/host.py'] == 'PRIVATE_REF_5066374c9cae0c03'
            and admission_marker['plugin_files'] == {k:v for k,v in admission_current['project_files'].items() if k.startswith('plugins/friday_rework/')}
            and admission_commit['source_receipt_sha256'] == admission_marker['source_receipt_sha256'] == admission_baseline['source_receipt']['sha256'],
            'completion_exact_admission_transaction_required')
        for item in admission_names:
            before = admission_intent['before'][item]
            expected_before = (admission_previous['project_files'][item] if item in admission_changed
                else admission_baseline['marker']['sha256'] if item == 'FRIDAY-INSTALL.json'
                else {'FRIDAY-INSTALL.json': 'PRIVATE_REF_f695e4e84f3341c5', 'hermes-agent.source.json': 'PRIVATE_REF_81e360373bafbd78', 'hermes-agent/install-stamp.json': 'PRIVATE_REF_afa76fb8eaf16d6e'}[item])
            after = admission_commit['after'][item]
            _r481_need(before == {'mode': 0o600, 'sha256': expected_before}
                and admission_plan['before'][item]['sha256'] == expected_before
                and admission_plan['before'][item]['mode'] == 0o600
                and after['mode'] == 0o600
                and admission_plan['after'][item]['sha256'] == after['sha256']
                and (item not in admission_changed or after['sha256'] == admission_current['project_files'][item])
                and (item not in admission_metadata - {'FRIDAY-INSTALL.json'} or after == before),
                'completion_admission_image_changed')
            admission_read({'path': str(admission_tx / 'before' / item), 'sha256': expected_before})
            admission_read({'path': str(_r481_H / item), 'sha256': after['sha256']})
            admission_snapshot[str(_r481_H / item)] = str(admission_tx / 'before' / item)
        _r481_need(admission_pin(admission_tx / 'committed.json') == admission_commit_ref
            and admission_pin(admission_tx / 'intent.json') == admission_intent_ref
            and admission_pin(_r481_H / 'FRIDAY-INSTALL.json') == admission_marker_ref,
            'completion_admission_transaction_changed')
    def actual_read(reference):
        return admission_read(dict(reference, path=admission_snapshot.get(reference['path'], reference['path'])))
    def actual_document(reference):
        return admission_document(dict(reference, path=admission_snapshot.get(reference['path'], reference['path'])))
    def actual_pin(path):
        return dict(admission_pin(_r481_Path(admission_snapshot.get(str(path), str(path)))), path=str(path))
    # Peel only the next exact DSH+qualification source transaction. Historical
    # receipts stay byte-identical; older checks read protected beforeimages.
    outer_snapshot = {}
    current_marker_ref = actual_pin(_r481_H / 'FRIDAY-INSTALL.json')
    current_marker = actual_document(current_marker_ref)
    baseline_input_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_82ed488f2ab40c08/INPUT-A0-SAMPLE-PAIR.NEXT.json', 'sha256': 'PRIVATE_REF_f2e403f89b6dd02b'}
    baseline_acceptance_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_82ed488f2ab40c08/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_644c67a2edb14da3'}
    baseline_acceptance = actual_document(baseline_acceptance_ref)
    _r481_need(baseline_acceptance.get('accepted') is True
        and baseline_acceptance.get('accepted_source_only') is True
        and baseline_acceptance.get('runtime_or_user_semantics_accepted') is False
        and baseline_acceptance.get('current_input') == baseline_input_ref,
        'completion_dsh_baseline_acceptance_required')
    if current_marker_ref != baseline_acceptance['marker']:
        tx = _r481_H / ('preparation/ordinary-source-update-' + baseline_input_ref['sha256'])
        commit_ref = actual_pin(tx / 'committed.json')
        intent_ref = actual_pin(tx / 'intent.json')
        commit = actual_document(commit_ref)
        intent = actual_document(intent_ref)
        plan = actual_document(commit['plan'])
        request = actual_document(plan['request'])
        previous = actual_document(baseline_input_ref)
        current = actual_document(commit['current_input'])
        changed = {'plugins/friday_rework/adapters/dsh.py', 'plugins/friday_rework/user_worker_join.py'}
        metadata = {'FRIDAY-INSTALL.json', 'hermes-agent.source.json', 'hermes-agent/install-stamp.json'}
        names = changed | metadata
        _r481_need(intent['schema'] == 'friday.ordinary-telegram-source-update-transaction.v1'
            and intent['state'] == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and commit['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and plan['schema'] == 'friday.dsh-retained-existing-plugin-overlay-plan.v1'
            and request['schema'] == 'friday.ordinary-telegram-source92-feature-update.v1'
            and request['home'] == str(_r481_H)
            and intent['plan'] == commit['plan']
            and intent['request_sha256'] == plan['request']['sha256']
            and request['previous_input'] == commit['previous_input'] == baseline_input_ref
            and request['current_input'] == commit['current_input']
            and current_marker['ordinary_source_update_request'] == plan['request']
            and current_marker['input_sha256'] == commit['current_input']['sha256']
            and current_marker_ref['sha256'] == commit['after']['FRIDAY-INSTALL.json']['sha256']
            and set(plan['before']) == set(plan['after']) == set(intent['before']) == set(commit['after']) == names
            and set(previous['project_files']) == set(current['project_files'])
            and {k:v for k,v in previous.items() if k != 'project_files'} == {k:v for k,v in current.items() if k != 'project_files'}
            and {k for k in previous['project_files'] if previous['project_files'][k] != current['project_files'][k]} == changed
            and current['project_files']['plugins/friday_rework/adapters/dsh.py'] == 'PRIVATE_REF_ba9a5bc2d2e98875'
            and current_marker['plugin_files'] == {k:v for k,v in current['project_files'].items() if k.startswith('plugins/friday_rework/')}
            and commit['source_receipt_sha256'] == current_marker['source_receipt_sha256'] == baseline_acceptance['source_receipt']['sha256'],
            'completion_exact_dsh_transaction_required')
        for item in names:
            before = intent['before'][item]
            expected_before = (previous['project_files'][item] if item in changed
                else baseline_acceptance['marker']['sha256'] if item == 'FRIDAY-INSTALL.json'
                else {'FRIDAY-INSTALL.json': 'PRIVATE_REF_67cb454c09ac20a3', 'hermes-agent.source.json': 'PRIVATE_REF_81e360373bafbd78', 'hermes-agent/install-stamp.json': 'PRIVATE_REF_afa76fb8eaf16d6e'}[item])
            after = commit['after'][item]
            _r481_need(before == {'mode': 0o600, 'sha256': expected_before}
                and plan['before'][item]['sha256'] == expected_before
                and plan['before'][item]['mode'] == 0o600
                and after['mode'] == 0o600
                and plan['after'][item]['sha256'] == after['sha256']
                and (item not in changed or after['sha256'] == current['project_files'][item])
                and (item not in metadata - {'FRIDAY-INSTALL.json'} or after == before),
                'completion_dsh_image_changed')
            actual_read({'path': str(tx / 'before' / item), 'sha256': expected_before})
            actual_read({'path': str(_r481_H / item), 'sha256': after['sha256']})
            outer_snapshot[str(_r481_H / item)] = str(tx / 'before' / item)
        _r481_need(actual_pin(tx / 'committed.json') == commit_ref
            and actual_pin(tx / 'intent.json') == intent_ref
            and actual_pin(_r481_H / 'FRIDAY-INSTALL.json') == current_marker_ref,
            'completion_dsh_transaction_changed')
    def _r481_read(reference):
        return actual_read(dict(reference, path=outer_snapshot.get(reference['path'], reference['path'])))
    def _r481_document(reference):
        return actual_document(dict(reference, path=outer_snapshot.get(reference['path'], reference['path'])))
    def pin(path):
        return dict(actual_pin(_r481_Path(outer_snapshot.get(str(path), str(path)))), path=str(path))
    # One exact paired source update may follow the accepted qualification fix.
    # Validate its current afterimages first; historical assertions below then
    # read its protected beforeimages without changing any historical receipt.
    snapshot = {}
    live_marker_ref = pin(_r481_H / 'FRIDAY-INSTALL.json')
    live_marker = _r481_document(live_marker_ref)
    host_name = 'plugins/friday_rework/host_runtime.py'
    join_name = 'plugins/friday_rework/user_worker_join.py'
    host_before = 'PRIVATE_REF_75613baa57d6c81d'
    host_next = 'PRIVATE_REF_48c5bdc40f0c8c66'
    if live_marker['plugin_files'][host_name] == host_next:
        accepted_next_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_e2f7a17223e22560/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json',
            'sha256': 'PRIVATE_REF_a21fd032cef0c4c4'}
        accepted_next = _r481_document(accepted_next_ref)
        prior_tx = _r481_H / 'preparation/ordinary-source-update-PRIVATE_REF_847ea81e9e24d965'
        prior_commit_ref = {'path': str(prior_tx / 'committed.json'),
            'sha256': 'PRIVATE_REF_5aaaa551ec2bb9df'}
        prior_commit = _r481_document(prior_commit_ref)
        previous_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_e2f7a17223e22560/INPUT-QUAL-COMPAT.NEXT.json',
            'sha256': 'PRIVATE_REF_565268d5aa641ce9'}
        expected = {'FRIDAY-INSTALL.json', 'hermes-agent.source.json', 'hermes-agent/install-stamp.json', host_name, join_name}
        join_before = 'PRIVATE_REF_6b206acaf0ecdc35'
        _r481_need(accepted_next.get('accepted') is True and accepted_next.get('accepted_source_only') is True
            and accepted_next.get('runtime_or_user_semantics_accepted') is False
            and accepted_next['committed'] == prior_commit_ref and accepted_next['current_input'] == previous_ref
            and prior_commit['current_input'] == previous_ref and accepted_next['plan'] == prior_commit['plan']
            and accepted_next['changed_plugin_files'] == [{'path': str(_r481_H / join_name), 'sha256': join_before}]
            and prior_commit['after'][join_name] == {'mode': 0o600, 'sha256': join_before},
            'completion_paired_predecessor_required')
        next_tx = _r481_H / 'preparation/ordinary-source-update-PRIVATE_REF_565268d5aa641ce9'
        next_commit_ref = pin(next_tx / 'committed.json')
        next_intent_ref = pin(next_tx / 'intent.json')
        next_commit = _r481_document(next_commit_ref)
        next_intent = _r481_document(next_intent_ref)
        next_plan = _r481_document(next_commit['plan'])
        next_request = _r481_document(next_plan['request'])
        next_input = _r481_document(next_commit['current_input'])
        previous_input = _r481_document(previous_ref)
        before_states = dict(prior_commit['after'], **{host_name: {'mode': 0o600, 'sha256': host_before}})
        _r481_need(set(before_states) == expected
            and next_intent['schema'] == 'friday.ordinary-telegram-source-update-transaction.v1'
            and next_intent['state'] == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and next_plan['schema'] == 'friday.dsh-retained-existing-plugin-overlay-plan.v1'
            and next_commit['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and next_commit['previous_input'] == next_request['previous_input'] == previous_ref
            and next_commit['current_input'] == next_request['current_input']
            and next_request['schema'] == 'friday.ordinary-telegram-source92-feature-update.v1'
            and next_request['home'] == str(_r481_H)
            and next_intent['plan'] == next_commit['plan']
            and next_intent['request_sha256'] == next_plan['request']['sha256']
            and live_marker['ordinary_source_update_request'] == next_plan['request']
            and live_marker['input_sha256'] == next_commit['current_input']['sha256']
            and set(next_intent['before']) == set(next_plan['before']) == set(next_plan['after']) == set(next_commit['after']) == expected
            and next_intent['before'] == before_states
            and next_commit['after'][host_name] == {'mode': 0o600, 'sha256': host_next}
            and next_commit['after'][join_name] == {'mode': 0o600, 'sha256': live_marker['plugin_files'][join_name]}
            and live_marker['plugin_files'][join_name] != join_before
            and next_commit['source_receipt_sha256'] == live_marker['source_receipt_sha256']
            and all(next_commit['after'][k] == before_states[k] for k in ('hermes-agent.source.json', 'hermes-agent/install-stamp.json'))
            and accepted_next['marker']['sha256'] == before_states['FRIDAY-INSTALL.json']['sha256']
            and {k:v for k,v in next_input.items() if k != 'project_files'} == {k:v for k,v in previous_input.items() if k != 'project_files'}
            and set(next_input['project_files']) == set(previous_input['project_files'])
            and {k for k in previous_input['project_files'] if previous_input['project_files'][k] != next_input['project_files'][k]} == {host_name, join_name}
            and live_marker['plugin_files'] == {k:v for k,v in next_input['project_files'].items() if k.startswith('plugins/friday_rework/')},
            'completion_exact_paired_transaction_required')
        for item in expected:
            state = before_states[item]
            _r481_need(next_plan['before'][item]['sha256'] == state['sha256']
                and next_plan['before'][item]['mode'] == state['mode']
                and next_plan['after'][item]['sha256'] == next_commit['after'][item]['sha256']
                and next_commit['after'][item]['mode'] == 0o600,
                'completion_paired_image_changed')
            _r481_read({'path': str(next_tx / 'before' / item), 'sha256': state['sha256']})
            _r481_read({'path': str(_r481_H / item), 'sha256': next_commit['after'][item]['sha256']})
            snapshot[str(_r481_H / item)] = str(next_tx / 'before' / item)
        _r481_need(live_marker_ref['sha256'] == next_commit['after']['FRIDAY-INSTALL.json']['sha256']
            and pin(next_tx / 'committed.json') == next_commit_ref and pin(next_tx / 'intent.json') == next_intent_ref
            and pin(_r481_H / 'FRIDAY-INSTALL.json') == live_marker_ref,
            'completion_paired_transaction_changed')

    def source_ref(ref):
        return dict(ref, path=snapshot.get(ref['path'], ref['path']))

    def source_read(ref):
        return _r481_read(source_ref(ref))

    def source_document(ref):
        return _r481_document(source_ref(ref))

    def source_pin(path):
        return dict(pin(_r481_Path(snapshot.get(str(path), str(path)))), path=str(path))

    relative = 'plugins/friday_rework/' + name + '.py'
    old_hashes = {'host_runtime': 'PRIVATE_REF_ee665d26afddf6f8',
                  'user_worker_join': 'PRIVATE_REF_176ad95fc19cd922'}
    _r481_need(name in old_hashes and reference == {'path': str(_r481_H / relative),
                 'sha256': old_hashes[name]}, 'completion_source_origin_changed')
    accepted_ref = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_f92a0f9e7cad96d7/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json',
                    'sha256': 'PRIVATE_REF_20eb1e702b9260d6'}
    accepted = source_document(accepted_ref)
    host_tx = _r481_H / 'preparation/ordinary-source-update-PRIVATE_REF_13283bc5afa7b057'
    host_commit_ref = {'path': str(host_tx / 'committed.json'),
                       'sha256': 'PRIVATE_REF_97871f5d65493ef6'}
    host_commit = source_document(host_commit_ref)
    _r481_need(accepted.get('accepted') is True and accepted.get('accepted_source_only') is True
        and accepted.get('runtime_or_user_semantics_accepted') is False
        and accepted.get('committed') == host_commit_ref
        and accepted.get('current_input') == host_commit['current_input']
        and accepted.get('plan') == host_commit['plan']
        and host_commit['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
        'completion_exact_source_acceptance_required')
    host_after = {'path': str(_r481_H / 'plugins/friday_rework/host_runtime.py'),
                  'sha256': 'PRIVATE_REF_75613baa57d6c81d'}
    _r481_need(accepted['changed_plugin_files'] == [host_after]
        and host_commit['after']['plugins/friday_rework/host_runtime.py'] ==
            {'mode': 0o600, 'sha256': host_after['sha256']}, 'completion_host_afterimage_required')
    source_read(host_after)
    if name == 'host_runtime':
        intent = source_document({'path': str(host_tx / 'intent.json'),
            'sha256': 'PRIVATE_REF_542ab91450b3f5a9'})
        _r481_need(intent['plan'] == host_commit['plan']
            and intent['before'][relative] == {'mode': 0o600, 'sha256': reference['sha256']},
            'completion_host_beforeimage_required')
        return source_read({'path': str(host_tx / 'before' / relative), 'sha256': reference['sha256']})

    # Before this correction is installed, the original module is still current.
    # Afterwards ONLY its next ordinary-source transaction may preserve that fact.
    marker_ref = source_pin(_r481_H / 'FRIDAY-INSTALL.json')
    marker = source_document(marker_ref)
    if marker['plugin_files'][relative] == reference['sha256']:
        _r481_need(marker_ref == accepted['marker'], 'completion_source_marker_changed')
        return source_read(reference)
    tx = _r481_H / 'preparation/ordinary-source-update-PRIVATE_REF_847ea81e9e24d965'
    committed_ref = source_pin(tx / 'committed.json')
    committed = source_document(committed_ref)
    intent_ref = source_pin(tx / 'intent.json')
    intent = source_document(intent_ref)
    plan = source_document(committed['plan'])
    expected_names = {'FRIDAY-INSTALL.json', 'hermes-agent.source.json', 'hermes-agent/install-stamp.json', relative}
    _r481_need(intent['schema'] == 'friday.ordinary-telegram-source-update-transaction.v1'
        and intent['state'] == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
        and plan['schema'] == 'friday.dsh-retained-existing-plugin-overlay-plan.v1'
        and committed['state'] == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
        and committed['previous_input'] == accepted['current_input']
        and committed['current_input']['sha256'] == marker['input_sha256']
        and intent['plan'] == committed['plan']
        and intent['request_sha256'] == plan['request']['sha256']
        and marker['ordinary_source_update_request'] == plan['request']
        and set(intent['before']) == set(plan['before']) == set(plan['after']) == set(committed['after']) == expected_names
        and intent['before'][relative] == {'mode': 0o600, 'sha256': reference['sha256']}
        and plan['before'][relative]['sha256'] == reference['sha256']
        and plan['before'][relative]['mode'] == 0o600
        and committed['after'][relative] == {'mode': 0o600, 'sha256': marker['plugin_files'][relative]}
        and marker_ref == {'path': str(_r481_H / 'FRIDAY-INSTALL.json'),
                           'sha256': committed['after']['FRIDAY-INSTALL.json']['sha256']}
        and committed['source_receipt_sha256'] == marker['source_receipt_sha256'],
        'completion_exact_successor_transaction_required')
    for item in expected_names - {relative}:
        expected_before = host_commit['after'][item]
        _r481_need(intent['before'][item] == expected_before
            and plan['before'][item]['sha256'] == expected_before['sha256']
            and plan['before'][item]['mode'] == expected_before['mode'],
            'completion_successor_beforeimage_changed')
        source_read({'path': str(tx / 'before' / item), 'sha256': expected_before['sha256']})
    for item in expected_names:
        after_ref = {'path': str(_r481_H / item), 'sha256': committed['after'][item]['sha256']}
        _r481_need(plan['after'][item]['sha256'] == after_ref['sha256'], 'completion_successor_afterimage_changed')
        source_read(after_ref)
    historical = source_read({'path': str(tx / 'before' / relative), 'sha256': reference['sha256']})
    _r481_need(pin(tx / 'committed.json') == committed_ref and source_pin(tx / 'intent.json') == intent_ref
        and source_pin(_r481_H / 'FRIDAY-INSTALL.json') == marker_ref, 'completion_source_transaction_changed')
    return historical


def _r481_checked(c, proof, original_attempt, folder):
    """Every fresh consumer checks the same exact retained facts and new intent."""
    from .worker_provision import pin, preparation
    from .host_record import digest
    d = _r481_retained()
    old = d['original']
    meta = proof.get('post_a0_completion')
    _r481_need(_r481_Path(c['runtime_home']) == _r481_HOME and _r481_Path(folder) == _r481_HOME / 'workers/qualification' and (type(meta) is dict) and (meta == _r481_metadata(meta.get('original'))), 'exact_post_A0_completion_metadata_required')
    path = _r481_HOME / 'workers/qualification/completion-original.json'
    _r481_need(meta['original'] == pin(path), 'exact_completion_intent_required')
    new = _r481_document(meta['original'])
    claim = _r481_claim_checked(new['original_attempt'])
    _r481_need(new['schema'] == _r481_SCHEMA and new['retained'] == _r481_metadata(meta['original'])['retained'] and (new['old_attempt_reopened'] is False) and (new['A0_start_repeated'] is False) and (new['binding'] == old['binding']) and (new['generation'] == old['generation']) and (new['preparations'] == old['preparations']) and (new['credentials'] == old['credentials']) and (new['binding_sha256'] == old['binding_sha256']) and (claim == original_attempt) and (claim['boot_id'] == old['original_attempt']['boot_id']) and (claim['started_mono'] > d['returned']['process_ended_monotonic']) and (proof['original'] == _r481_FIXED['original']) and (proof['observed']['boot_id'] == claim['boot_id']) and (claim['started_mono'] <= proof['observed']['monotonic'] < claim['deadline_mono']) and (proof['workers']['a0'] == dict(d['a0_stage']['observation'], runtime_sha256=digest({k: v for k, v in preparation(_r481_HOME, old['profile'], 'a0', old['preparations']['a0'])[1].items() if k != 'runtime_receipt'}))) and (type(new['safety_refs']) is dict), 'post_A0_completion_join_changed')
    stage = _r481_dsh_checked(new['dsh_refs'], old)
    runtime = preparation(_r481_HOME, old['profile'], 'dsh', old['preparations']['dsh'])[1]
    safety = _r481_safety_checked(new['safety_refs'], old, runtime)
    _r481_need(proof['workers']['dsh'] == dict(stage['observation'], safety=safety['observation'], runtime_sha256=digest({k: v for k, v in preparation(_r481_HOME, old['profile'], 'dsh', old['preparations']['dsh'])[1].items() if k != 'runtime_receipt'})) and stage['observed']['monotonic'] < claim['started_mono'] and (safety['observed']['monotonic'] < claim['started_mono']) and (claim['started_mono'] <= proof['observed']['monotonic'] < claim['deadline_mono']), 'actual_DSH_proof_join_changed')
    for name, reference in new['installed_sources'].items():
        _r481_need(name in ('host_runtime', 'user_worker_join') and reference['path'] == str(_r481_H / 'plugins/friday_rework' / (name + '.py')), 'completion_source_origin_changed')
        _r481_completion_source(name, reference)
    _r481_need(set(new['installed_sources']) == {'host_runtime', 'user_worker_join'}, 'completion_sources_incomplete')
    return (d, dict(new, dsh_claim=stage['original_attempt'], safety_claim=safety['original_attempt']))

def _r481_custody(home, binding, generation, preparations, plan_ref):
    """Reuse every pinned native ownership clause; replace only settled-state evidence."""
    from . import a0_bootstrap as b
    _r481_need(_r481_Path(home) == _r481_HOME, 'exact_R481_home_required')
    raw = _r481_read(_r481_FIXED['a0_bootstrap'])
    text = raw.decode()
    node = next((n for n in _r481_ast.parse(text).body if isinstance(n, _r481_ast.FunctionDef) and n.name == 'checked_custody'))
    source = _r481_ast.get_source_segment(text, node)
    start = source.index("            or state['phase'] != 'STOPPED'")
    end = source.index("):\n        raise HostUnavailable('foreign_or_unsettled_a0_bootstrap')", start)
    removed = source[start:end]
    _r481_need(removed.startswith("            or state['phase'] != 'STOPPED'") and removed.endswith("or state['settlement']['route']['status'] != 'STOP_CONFIRMED'"), 'exact_custody_shape_required')
    source = source[:start] + '            or not _settlement(home,state,plan)' + source[end:]
    ns = dict(b.__dict__)

    def settlement(h, s, p):
        d = _r481_retained()
        return h == _r481_HOME and s == d['state'] and (p == d['plan'])
    ns['_settlement'] = settlement
    exec(compile(source, '<R481-exact-retained-custody>', 'exec'), ns)
    result = ns['checked_custody'](home, binding, generation, preparations, plan_ref)
    result['reconciliation'] = _r481_FIXED['cleanup_control']
    return result

def _r481_current_cleanup():
    """Actual read-only native/resource checks under existing runtime lock."""
    refs = _r481_document(_r481_FIXED['reconcile_refs'])
    raw = _r481_read(_r481_FIXED['reconcile'])
    ns = {'__name__': 'r481_checked_missing_cleanup', '__file__': _r481_FIXED['reconcile']['path']}
    exec(compile(raw, _r481_FIXED['reconcile']['path'], 'exec'), ns)
    helpers, m, b, keys = ns['load'](refs)
    with m.Runtime.__new__(m.Runtime).locked():
        ns['current'](refs, helpers, m, b, keys, retired=True)

def _r481_complete(home, binding, generation, prepared, *, verify, accepted_monotonic=None, _source_target=None, parent, authority_ref, source_binding, stage_sink, dsh_refs, safety_refs):
    """Publish only already completed observations; NEVER runs DSH or A0.

    Root owns R482. Its actual durable output/return/clock must be supplied;
    missing or uncertain evidence refuses before canonical publication.
    """
    from .runtime_containment import Budget
    from .worker_provision import pin, preparation, prepare_inputs
    from .host_runtime import a0_deployment_contract, deployment_observations
    from .host_record import digest
    from . import user_worker_join as join
    from .onboarding import _new_file
    from hermes_cli import friday_user_scope as scope
    from hermes_cli.config import require_readable_config_before_write
    _r481_need(_r481_Path(home) == _r481_HOME and scope._CURRENT.get() is None, 'genuine_operator_scope_required')
    _r481_need(type(parent) is Budget and parent.seconds == 300 and (parent.started == accepted_monotonic) and (parent.deadline == parent.original_deadline == accepted_monotonic + 300), 'distinct_publication300_required')
    parent.check(reserve=30)
    verify()
    _r481_document(authority_ref)
    _r481_need(type(source_binding) is dict and set(source_binding) == {'host_runtime', 'user_worker_join'}, 'installed_delta_binding_required')
    for name, ref in source_binding.items():
        _r481_need(ref['path'] == str(_r481_H / 'plugins/friday_rework' / (name + '.py')), 'installed_delta_path_required')
        _r481_read(ref)
    d = _r481_retained()
    old = d['original']
    completed_dsh = _r481_dsh_checked(dsh_refs, old)
    _r481_need(parent.started > completed_dsh['observed']['monotonic'], 'separate_publication_after_DSH_required')
    _r481_need(binding == old['binding'] and generation == old['generation'] and (prepared == old['preparations']), 'original_owner_required')
    _r481_need(_r481_Path('/proc/sys/kernel/random/boot_id').read_text().strip() == old['original_attempt']['boot_id'], 'original_boot_required')
    _r481_need(callable(stage_sink), 'durable_stage_sink_required')
    _r481_current_cleanup()
    verify()
    _r481_need(callable(_source_target) and _source_target() == {'home': str(_r481_HOME), 'profile': old['profile'], 'binding_sha256': old['binding_sha256']}, 'current_main_source_target_required')
    runtimes = {k: preparation(home, binding['runtime_profile'], k, v)[1] for k, v in prepared.items()}
    a0_deployment_contract(runtimes['a0'])
    completed_safety = _r481_safety_checked(safety_refs, old, runtimes['dsh'])
    _r481_need(parent.started > completed_safety['observed']['monotonic'], 'publication_after_actual_safety_required')
    config = require_readable_config_before_write(home / 'config.yaml')
    prepare_inputs(home, binding['runtime_profile'], 'dsh', runtimes['dsh'], config, tools=binding['tools'])
    _r481_need(old['credentials'] == {n: pin(home / n)['sha256'] if (home / n).exists() else None for n in old['credentials']}, 'credentials_changed')
    folder = home / 'workers/qualification'
    for path in (folder / 'completion-original.json', folder / 'completion-failure.json', folder / 'dsh-observation.json', folder / 'observation.json', *(_r481_Path(c['runtime_receipt']['path']) for c in runtimes.values())):
        _r481_need(not _r481_os.path.lexists(path), 'existing_missing_stage_requires_reconciliation')
    claim = {'boot_id': old['original_attempt']['boot_id'], 'started_mono': parent.started, 'deadline_mono': parent.deadline, 'budget_seconds': 300}
    new = {'schema': _r481_SCHEMA, 'binding': binding, 'binding_sha256': old['binding_sha256'], 'generation': generation, 'preparations': prepared, 'credentials': old['credentials'], 'original_attempt': claim, 'retained': _r481_metadata(None)['retained'], 'old_attempt_reopened': False, 'A0_start_repeated': False, 'authority': authority_ref, 'installed_sources': source_binding, 'dsh_refs': dsh_refs, 'safety_refs': safety_refs}
    _new_file(folder / 'completion-original.json', (_r481_json.dumps(new, sort_keys=True, allow_nan=False) + '\n').encode())
    stage_sink('completion_intent', {'intent': pin(folder / 'completion-original.json'), 'publication_clock': claim})
    try:
        verify()
        _new_file(folder / 'dsh-observation.json', _r481_read(dsh_refs['observation']))
        stage_sink('dsh_preserved', {'observation': pin(folder / 'dsh-observation.json'), 'actual_Root_observation': dsh_refs['observation'], 'native_execution_repeated': False})
        observation = _r481_copy.deepcopy(completed_dsh['observation'])
        observation['safety'] = _r481_copy.deepcopy(completed_safety['observation'])
        obs = {'dsh': observation, 'a0': _r481_copy.deepcopy(d['a0_stage']['observation'])}
        for kind, c in runtimes.items():
            obs[kind]['runtime_sha256'] = digest({k: v for k, v in c.items() if k != 'runtime_receipt'})
        proof = {'schema': 'friday.worker-deployment-observation.v1', 'home': str(home), 'profile': binding['runtime_profile'], 'original': _r481_FIXED['original'], 'workers': obs, 'credentials': old['credentials'], 'bootstrap_custody': _r481_custody(home, binding, generation, prepared, old['plan']), 'effects': 'OBSERVATION_ONLY', 'per_job_authority': 'NOT_GRANTED', 'observed': {'boot_id': claim['boot_id'], 'monotonic': _r481_time.monotonic(), 'unix': _r481_time.time()}, 'post_a0_completion': _r481_metadata(pin(folder / 'completion-original.json'))}
        verify()
        _r481_current_cleanup()
        for kind, c in runtimes.items():
            preparation(home, binding['runtime_profile'], kind, prepared[kind])
        _r481_need(old['credentials'] == {n: pin(home / n)['sha256'] if (home / n).exists() else None for n in old['credentials']}, 'credentials_changed')
        for c in runtimes.values():
            parent.call(deployment_observations, c, proof, claim, folder)
        verify()
        parent.call(_new_file, folder / 'observation.json', (_r481_json.dumps(proof, sort_keys=True) + '\n').encode())
        for kind, c in runtimes.items():
            verify()
            receipt = join.readiness_receipt(c, [prepared[kind], pin(folder / 'observation.json')])
            parent.call(_new_file, _r481_Path(c['runtime_receipt']['path']), (_r481_json.dumps(receipt, sort_keys=True) + '\n').encode())
            c['runtime_receipt'] = pin(_r481_Path(c['runtime_receipt']['path']))
        return runtimes
    except BaseException:
        try:
            _new_file(folder / 'completion-failure.json', b'{"retry_authorized":false,"effects":"RECONCILE_EXACT_PUBLICATION"}\n')
        except OSError:
            pass
        raise

def _r481_run(onboarding, *, parent, authority_ref, source_binding, stage_sink, dsh_refs, safety_refs, **arguments):
    """Reuse genuine existing authenticated Onboarding entry and final commit.

    Root runner must load trusted Dashboard graph, mint/verify a scoped native
    session and revoke that exact session in finally (existing auth-entry recipe).
    Source integration of the two existing candidates precedes this operation.
    """
    import sys, textwrap
    from .onboarding import Onboarding
    from . import user_worker_join as join
    from .runtime_containment import Budget
    _r481_need(type(onboarding) is Onboarding and type(parent) is Budget and (arguments.get('accepted_monotonic') == parent.started), 'genuine_current_Onboarding_and_parent_required')
    raw = _r481_read(_r481_FIXED['onboarding'])
    text = raw.decode()
    cls = next((n for n in _r481_ast.parse(text).body if isinstance(n, _r481_ast.ClassDef) and n.name == 'Onboarding'))
    node = next((n for n in cls.body if isinstance(n, _r481_ast.FunctionDef) and n.name == '_qualify_workers'))
    method = textwrap.dedent(_r481_ast.get_source_segment(text, node))
    before = "budget = Budget(min(600, *(c['budget_seconds'] for c in runtimes.values())),\n                    started=accepted_monotonic)"
    _r481_need(method.count(before) == 1, 'exact_original_commit_parent_shape_required')
    method = method.replace(before, 'budget = _completion_parent', 1)
    ns = dict(sys.modules[Onboarding.__module__].__dict__)
    ns['_completion_parent'] = parent
    exec(compile(method, '<R481-post-A0-original-Onboarding-commit>', 'exec'), ns)
    previous = join.qualify
    old_method = Onboarding._qualify_workers

    def remaining(*args, **kwargs):
        return _r481_complete(*args, **kwargs, parent=parent, authority_ref=authority_ref, source_binding=source_binding, stage_sink=stage_sink, dsh_refs=dsh_refs, safety_refs=safety_refs)
    try:
        join.qualify = remaining
        Onboarding._qualify_workers = ns['_qualify_workers']
        return onboarding._qualify_workers(**arguments)
    finally:
        same = join.qualify is remaining and Onboarding._qualify_workers is ns['_qualify_workers']
        if join.qualify is remaining:
            join.qualify = previous
        if Onboarding._qualify_workers is ns['_qualify_workers']:
            Onboarding._qualify_workers = old_method
        _r481_need(same, 'completion_consumer_changed_no_overwrite')

from types import SimpleNamespace as _r481_SimpleNamespace
_r481_completion = _r481_SimpleNamespace(checked=_r481_checked, document=_r481_document, custody=_r481_custody, run=_r481_run, complete=_r481_complete, __file__=__file__)

# S436: exact source/native successor compatibility, no historical rewrite,
# observation rerun, new grant, or claimed runtime/user acceptance.
_S436_BASE_INPUT = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_e1c170eb550488d9/package-prep/INPUT-WORKER-STATE-QUOTA.NEXT.json', 'sha256': 'PRIVATE_REF_cf8ead935851abe4'}
_S436_BASE_ACCEPTANCE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_0966be9ea88cfc47/service/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_f5fbd7f5c354b79d'}
_S436_NATIVE_ANCHOR = {'path': '<INSTALL_HOME>/preparation/worker-declarations-successor-PRIVATE_REF_a21dfc94e577a247/service-source-receipt.json', 'sha256': 'PRIVATE_REF_7963c495355645d5'}
_S436_OLD_RUNTIME = 'PRIVATE_REF_6155f4bda62ac687'
_S436_NEW_RUNTIME = 'PRIVATE_REF_10996c17f165e4f5'
_S436_NEW_WEB = 'PRIVATE_REF_f47e85394635403d'
_S436_PLUGINS = {'plugins/friday_rework/adapters/a0_web.py', 'plugins/friday_rework/host.py', 'plugins/friday_rework/host_runtime.py', 'plugins/friday_rework/runtime_observers.py', 'plugins/friday_rework/user_worker_join.py', 'plugins/friday_rework/worker_declarations.py'}

_S436_NATIVE_VERIFIER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/verify_native.py', 'sha256': 'PRIVATE_REF_7ca4b2793c514fe4'}
_S443_NATIVE480_VERIFIER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/verify480.py', 'sha256': 'PRIVATE_REF_8140e0cd6deb0e06'}

def _s443_native_call(namespace, name, request_ref, receipt_ref):
    # Separate native480 custody never replaces the historical4ad marker.
    receipt_path = _r481_H/'preparation/root-future-a0-daemon480-20261027.receipt.json'
    if os.path.lexists(receipt_path):
        current = _postboot_a0_bridge()['current480']()
        return namespace['verify_native_historical' if name=='verify_native_maintenance' else name+'_historical'](request_ref,receipt_ref,
                                               current['request'],current['receipt'])
    return namespace[name](request_ref,receipt_ref)


def _s436_native_successor(request_ref=None, receipt_ref=None):
    from .worker_provision import pin
    marker = _r481_document(pin(_r481_H/'FRIDAY-INSTALL.json'))
    actual_ref = marker.get('a0_service_source_successor')
    _r481_need(actual_ref != _S436_NATIVE_ANCHOR and (receipt_ref is None or receipt_ref == actual_ref), 's436_native_successor_required')
    receipt = _r481_document(actual_ref)
    raw = _r481_read(_S436_NATIVE_VERIFIER)
    namespace = {'__file__':_S436_NATIVE_VERIFIER['path'],'__name__':'_s436_exact_native_proof'}
    exec(compile(raw,_S436_NATIVE_VERIFIER['path'],'exec'),namespace)
    _s443_native_call(namespace,'verify_native_maintenance',
        receipt['request'] if request_ref is None else request_ref,actual_ref)
    return receipt


def _s436_qualified_runtime(c):
    """Keep retained observation identity after this exact source-only edge."""
    if 'a0' not in c: return c
    current = c['a0']['runtime']
    if current['sha256'] == _S436_OLD_RUNTIME: return c
    _r481_need(current == {'path':str(_r481_H/'worker-runtime-source/scripts/a0_runtime.py'),'sha256':_S436_NEW_RUNTIME}, 's436_qualified_runtime_edge_required')
    _s436_native_successor()
    historical = _r481_copy.deepcopy(c)
    historical['a0']['runtime']['sha256'] = _S436_OLD_RUNTIME
    return historical

def _s436_source_snapshot():
    """Peel exact S436 source/native journals to accepted S435 beforeimages."""
    from .worker_provision import pin
    accepted = _r481_document(_S436_BASE_ACCEPTANCE)
    _r481_need(accepted.get('accepted') is True and accepted.get('accepted_source_only') is True
        and accepted.get('current_input') == _S436_BASE_INPUT, 's436_source_baseline_required')
    marker_ref = pin(_r481_H/'FRIDAY-INSTALL.json'); marker = _r481_document(marker_ref)
    if marker_ref == accepted['marker']: return {}
    source_marker_ref = marker_ref
    source_marker = marker
    if marker.get('a0_service_source_successor') != _S436_NATIVE_ANCHOR:
        native = _s436_native_successor()
        source_marker_ref = pin(_r481_Path(native['transaction'])/'before/FRIDAY-INSTALL.json')
        source_marker = _r481_document(source_marker_ref)
    tx = _r481_H/('preparation/ordinary-source-update-'+_S436_BASE_INPUT['sha256'])
    commit_ref = pin(tx/'committed.json'); intent_ref = pin(tx/'intent.json')
    commit = _r481_document(commit_ref); intent = _r481_document(intent_ref)
    plan = _r481_document(commit['plan']); request = _r481_document(plan['request'])
    previous = _r481_document(_S436_BASE_INPUT); current = _r481_document(commit['current_input'])
    metadata = {'FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json'}
    names = _S436_PLUGINS | metadata
    _r481_need(intent.get('schema') == 'friday.ordinary-telegram-source-update-transaction.v1'
        and intent.get('state') == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
        and commit.get('state') == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
        and plan.get('schema') == 'friday.dsh-retained-existing-plugin-overlay-plan.v1'
        and request.get('schema') == 'friday.ordinary-telegram-source92-feature-update.v1'
        and request.get('home') == str(_r481_H) and intent['plan'] == commit['plan']
        and intent['request_sha256'] == plan['request']['sha256']
        and request['previous_input'] == commit['previous_input'] == _S436_BASE_INPUT
        and request['current_input'] == commit['current_input']
        and source_marker['ordinary_source_update_request'] == plan['request']
        and source_marker['input_sha256'] == current_input_sha(commit)
        and source_marker_ref['sha256'] == commit['after']['FRIDAY-INSTALL.json']['sha256']
        and set(plan['before']) == set(plan['after']) == set(intent['before']) == set(commit['after']) == names
        and set(previous['project_files']) == set(current['project_files'])
        and {k:v for k,v in previous.items() if k!='project_files'} == {k:v for k,v in current.items() if k!='project_files'}
        and {k for k in previous['project_files'] if previous['project_files'][k] != current['project_files'][k]} == _S436_PLUGINS | {'scripts/a0_runtime.py'}
        and current['project_files']['scripts/a0_runtime.py'] == _S436_NEW_RUNTIME
        and current['project_files']['plugins/friday_rework/adapters/a0_web.py'] == _S436_NEW_WEB
        and current['project_files']['plugins/friday_rework/adapters/dsh.py'] == 'PRIVATE_REF_ba9a5bc2d2e98875'
        and commit['source_receipt_sha256'] == accepted['source_receipt']['sha256'], 's436_exact_source_transaction_required')
    snapshot = {}
    for item in names:
        before = intent['before'][item]; after = commit['after'][item]
        expected = previous['project_files'][item] if item in _S436_PLUGINS else accepted['marker']['sha256'] if item=='FRIDAY-INSTALL.json' else after['sha256']
        _r481_need(before == {'sha256':expected,'mode':0o600}
            and plan['before'][item]['sha256'] == expected and plan['before'][item]['mode'] == 0o600
            and after['mode'] == 0o600 and plan['after'][item]['sha256'] == after['sha256']
            and (item not in _S436_PLUGINS or after['sha256'] == current['project_files'][item])
            and (item not in metadata-{'FRIDAY-INSTALL.json'} or after==before), 's436_source_image_changed')
        _r481_read({'path':str(tx/'before'/item),'sha256':expected})
        if item!='FRIDAY-INSTALL.json': _r481_read({'path':str(_r481_H/item),'sha256':after['sha256']})
        snapshot[str(_r481_H/item)] = str(tx/'before'/item)
    _r481_need(pin(tx/'committed.json') == commit_ref and pin(tx/'intent.json') == intent_ref and pin(_r481_H/'FRIDAY-INSTALL.json') == marker_ref, 's436_source_changed_during_check')
    return snapshot

def current_input_sha(commit):
    return commit['current_input']['sha256']


_POSTBOOT_DSH_MEMO = {
    'path': '<PRIVATE_CACHE>/PRIVATE_REF_74e2a96dafdf18ad/R481-RETAINED-REUSE-FINAL/RETAINED-REUSE.json',
    'sha256': 'PRIVATE_REF_2a56035e05e034cb'}
_POSTBOOT_DSH_SCHEMA = 'friday.dsh-postboot-revalidation.v1'
_POSTBOOT_DSH_POLICY_SCHEMA = 'friday.worker-declarations.secondary-policy-successor.postboot-current.v1'
_POSTBOOT_DSH_SOURCES = ('user_worker_join.py', 'host_runtime.py', 'runtime_observers.py',
    'worker_web.py', 'worker_provision.py', 'host_record.py', 'runtime_containment.py',
    'runtime_process.py', 'runtime_primitives.py', 'adapters/dsh.py')


def _postboot_dsh_need(value, code):
    if value is not True:
        raise HostUnavailable(code)


def _postboot_dsh_same(left, right):
    return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=False) == \
        json.dumps(right, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _postboot_dsh_document(reference):
    from hermes_cli import friday_user_scope as scope
    scope._private(Path(reference['path']))
    return _r481_document(reference)


def _postboot_dsh_sources():
    marker = _postboot_dsh_document(pin(_r481_H / 'FRIDAY-INSTALL.json'))
    result = {}
    retained = {}
    if marker.get('a0_service_source_successor') != _S436_NATIVE_ANCHOR:
        actual = _r481_document(marker['a0_service_source_successor'])
        raw = _r481_read(_S436_NATIVE_VERIFIER)
        namespace = {'__file__':_S436_NATIVE_VERIFIER['path'],'__name__':'_s442_dsh_source_compat'}
        exec(compile(raw,_S436_NATIVE_VERIFIER['path'],'exec'),namespace)
        retained = _s443_native_call(namespace,'retained_dsh_sources',actual['request'],marker['a0_service_source_successor'])
    for name in _POSTBOOT_DSH_SOURCES:
        relative = 'plugins/friday_rework/' + name
        reference = {'path': str(_r481_H / relative), 'sha256': marker['plugin_files'][relative]}
        if relative in retained:
            reference = retained[relative]  # Exact Source92 beforeimage authenticated above.
        else:
            _r481_read(reference)
        result[relative] = reference
    return result


def _postboot_dsh_inputs(c, value, *, binding=None, generation=None):
    """Check unchanged history and the exact committed four-file policy delta."""
    from hermes_cli import friday_user_scope as scope
    from .host_runtime import _dsh_web
    from .worker_web import web_policy
    _postboot_dsh_need('dsh' in c and 'a0' not in c
        and c['runtime_home'] == str(_r481_HOME)
        and c['runtime_profile'] == 'telegram-bot-9000000001', 'postboot_dsh_exact_home_required')
    home = Path(c['runtime_home'])
    _postboot_dsh_need(type(value) is dict and set(value) == {
        'schema', 'home', 'profile', 'generation', 'memo', 'policy_transaction',
        'runtime_sha256', 'sources', 'stage_folder', 'observation'}
        and value['schema'] == _POSTBOOT_DSH_SCHEMA and value['home'] == str(home)
        and value['profile'] == c['runtime_profile'] and value['generation'] == 2
        and value['memo'] == _POSTBOOT_DSH_MEMO
        and value['runtime_sha256'] == digest({k: v for k, v in c.items() if k != 'runtime_receipt'}),
        'postboot_dsh_sidecar_binding_changed')
    _postboot_dsh_need(value['sources'] == _postboot_dsh_sources(), 'postboot_dsh_sources_changed')
    memo = _postboot_dsh_document(_POSTBOOT_DSH_MEMO)
    _postboot_dsh_need(memo['schema'] == 'friday.r481.retained-postboot-reuse.v1'
        and memo['home'] == str(home) and memo['profile'] == c['runtime_profile']
        and memo['historical_completion_checked'] is True
        and memo['checked_workers'] == ['dsh', 'a0']
        and memo['old_claim_reopened'] is False and memo['worker_effects'] is False
        and memo['A0_live_proof'] is False and memo['current_boot_runtime_accepted'] is False,
        'postboot_dsh_historical_memo_changed')
    snapshots = memo['snapshots']
    _postboot_dsh_need(set(snapshots) == {'original', 'proof', 'completion', 'attachment', 'policy',
        'dsh-preparation', 'a0-preparation', 'dsh-receipt', 'a0-receipt'}, 'postboot_dsh_snapshot_inventory_changed')
    old = {}
    for name, refs in snapshots.items():
        _postboot_dsh_need(type(refs) is dict and set(refs) == {'original', 'snapshot'}
            and refs['snapshot']['sha256'] == refs['original']['sha256'], 'postboot_dsh_snapshot_pin_changed')
        old[name] = _postboot_dsh_document(refs['snapshot'])
    # Immutable live originals remain bound; changed preparation bytes come only
    # from the separately committed policy transaction and its exact archives.
    for name in ('original', 'proof', 'completion', 'policy', 'dsh-receipt'):
        _postboot_dsh_need(_postboot_dsh_same(_postboot_dsh_document(snapshots[name]['original']), old[name]),
                          'postboot_dsh_retained_document_changed')
    original = old['original']; proof = old['proof']; completion = old['completion']
    _postboot_dsh_need(original['binding']['runtime_profile'] == c['runtime_profile']
        and original['generation'] == value['generation'] == completion['generation']
        and original['preparations'] == completion['preparations'] == {
            k: snapshots[k + '-preparation']['original'] for k in ('dsh', 'a0')}
        and completion['original_attempt'] == memo['original_claim']
        and proof['original'] == snapshots['original']['original']
        and proof['post_a0_completion']['original'] == snapshots['completion']['original']
        and original['binding_sha256'] == scope._fingerprint(original['binding'])
        and (binding is None or original['binding_sha256'] == scope._fingerprint(binding))
        and (generation is None or generation == original['generation']), 'postboot_dsh_original_identity_changed')
    setup = _postboot_dsh_document(pin(home / scope.ONBOARDING))
    _postboot_dsh_need(setup['binding_sha256'] == original['binding_sha256'], 'postboot_dsh_onboarding_changed')
    _postboot_dsh_need(set(original['credentials']) == {'.env', 'auth.json'}, 'postboot_dsh_credentials_inventory_changed')
    for name, sha in original['credentials'].items():
        path = home / name
        _postboot_dsh_need((sha is None and not os.path.lexists(path))
            or (sha is not None and pin(path)['sha256'] == sha), 'postboot_dsh_credentials_changed')
    txrefs = value['policy_transaction']
    _postboot_dsh_need(type(txrefs) is dict and set(txrefs) == {'intent', 'committed'},
                      'postboot_dsh_transaction_refs_required')
    intent = _postboot_dsh_document(txrefs['intent']); committed = _postboot_dsh_document(txrefs['committed'])
    request = intent['request']; tx = Path(txrefs['intent']['path']).parent
    semantic = {'prior_derivative': request['prior_derivative'], 'profile': str(home),
        'identity': request['identity'], 'expired_policy': request['before']['policy'],
        'checkpoint': request['checkpoint'], 'current_boot': memo['captured_boot']}
    semantic_raw = (json.dumps(semantic, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    _postboot_dsh_need(tx == _r481_H / 'preparation' / ('worker-policy-successor-' + hashlib.sha256(semantic_raw).hexdigest())
        and txrefs['intent']['path'] == str(tx / 'intent.json')
        and txrefs['committed']['path'] == str(tx / 'committed.json')
        and intent['schema'] == committed['schema'] == request['schema'] == _POSTBOOT_DSH_POLICY_SCHEMA
        and intent['state'] == 'CONSUMED_NO_RETRY' and intent['resume_allowed'] is False
        and committed['state'] == 'POLICY_ONLY_SUCCESSOR_COMMITTED'
        and intent['clock'] == committed['clock']
        and request['home'] == str(_r481_H) and request['profile'] == c['runtime_profile']
        and request['identity'] == {'binding': original['binding'], 'generation': original['generation']}
        and committed['prior_derivative'] == request['prior_derivative']
        and committed['current_scope'] == request['current_scope']
        and committed['runtime_acceptance'] == 'NOT_GRANTED'
        and all(committed[k] is False for k in ('ready', 'workers_enabled', 'qualification_started', 'consumers_started', 'resume_allowed')),
        'postboot_dsh_exact_committed_policy_required')
    for name in ('failure.json', 'rolled-back.json', 'rollback.json'):
        _postboot_dsh_need(not os.path.lexists(tx / name), 'postboot_dsh_policy_uncertain')
    clock = _postboot_dsh_document(request['original_clock'])
    _postboot_dsh_need(_postboot_dsh_same(clock, intent['clock'])
        and clock['boot_id'] == memo['captured_boot'], 'postboot_dsh_policy_clock_changed')
    grant = _postboot_dsh_document(request['once_grant'])
    request_body = {k: v for k, v in request.items() if k != 'once_grant'}
    request_raw = (json.dumps(request_body, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    _postboot_dsh_need(grant == {'schema': request['schema'] + '.once-grant',
        'request_body_sha256': hashlib.sha256(request_raw).hexdigest(),
        'workers_enabled': False, 'consumers_started': False, 'resume_allowed': False},
        'postboot_dsh_policy_grant_changed')
    mapping = {'policy': 'policy', 'attachment': 'attachment', 'dsh': 'dsh-preparation', 'a0': 'a0-preparation'}
    _postboot_dsh_need(set(committed['beforeimages']) == set(mapping)
        and committed['preserved_policy'] == snapshots['policy']['original']
        and committed['preserved_policy_archive'] == committed['beforeimages']['policy'],
        'postboot_dsh_policy_archives_changed')
    for name, snapshot in mapping.items():
        before = committed['beforeimages'][name]
        _postboot_dsh_need(request['before'][name] == snapshots[snapshot]['original']
            and before == {'path': str(tx / 'before' / (name + '.json')),
                           'sha256': snapshots[snapshot]['original']['sha256']}
            and _postboot_dsh_same(_postboot_dsh_document(before), old[snapshot]),
            'postboot_dsh_policy_beforeimage_changed')
    checkpoint = _postboot_dsh_document(request['checkpoint'])
    _postboot_dsh_need(checkpoint['before'] == request['before']
        and checkpoint['old_boot'] == memo['old_boot'] and checkpoint['current_boot'] == memo['captured_boot'],
        'postboot_dsh_policy_checkpoint_changed')
    _postboot_dsh_need(set(committed['preparations']) == {'dsh', 'a0'}, 'postboot_dsh_current_preparations_changed')
    current_attachment = _postboot_dsh_document(committed['attachment'])
    expected_attachment = copy.deepcopy(old['attachment'])
    expected_attachment['runtimes']['dsh']['dsh']['web']['egress_evidence'] = committed['policy']
    _postboot_dsh_need(committed['attachment']['path'] == str(home / 'workers/attachment.json')
        and _postboot_dsh_same(current_attachment, expected_attachment), 'postboot_dsh_only_policy_attachment_delta_required')
    for kind in ('dsh', 'a0'):
        reference = committed['preparations'][kind]
        _postboot_dsh_need(reference['path'] == str(home / 'workers' / kind / 'runtime-input.json'),
                          'postboot_dsh_preparation_path_changed')
        prepared = _postboot_dsh_document(reference)
        expected = copy.deepcopy(old[kind + '-preparation'])
        expected['attachment'] = committed['attachment']
        if kind == 'dsh':
            prior = snapshots['policy']['original']
            _postboot_dsh_need(expected['inputs'].count(prior) == 1, 'postboot_dsh_original_policy_input_changed')
            expected['inputs'] = [committed['policy'] if ref == prior else ref for ref in expected['inputs']]
            expected['runtime']['dsh']['web']['egress_evidence'] = committed['policy']
        _postboot_dsh_need(_postboot_dsh_same(prepared, expected), 'postboot_dsh_only_policy_preparation_delta_required')
    _, current = preparation(home, c['runtime_profile'], 'dsh', committed['preparations']['dsh'])
    _postboot_dsh_need(_postboot_dsh_same({k: v for k, v in current.items() if k != 'runtime_receipt'},
        {k: v for k, v in c.items() if k != 'runtime_receipt'})
        and c['runtime_receipt'] == snapshots['dsh-receipt']['original'], 'postboot_dsh_current_runtime_changed')
    old_runtime = old['dsh-preparation']['runtime']
    _postboot_dsh_need(_postboot_dsh_same(old['dsh-receipt'], _postboot_dsh_retained_receipt(old_runtime,
        [snapshots['dsh-preparation']['original'], snapshots['proof']['original']])), 'postboot_dsh_old_receipt_changed')
    # Execute the unchanged expiry consumer; the new policy may change only boot
    # and netns from the genuine effective old declaration, never its expiry.
    old_web = _dsh_web(old_runtime['dsh'])
    effective = web_policy(old_web, str(home), c['runtime_profile'], time.time())
    _postboot_dsh_need(_postboot_dsh_same(effective, _postboot_dsh_document(checkpoint['effective_policy']))
        and effective['boot_id'] == memo['old_boot'], 'postboot_dsh_effective_policy_changed')
    web = _dsh_web(c['dsh']); policy = web_policy(web, str(home), c['runtime_profile'], time.time())
    ns = Path('/proc/self/ns/net').stat(); boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    _postboot_dsh_need(boot == memo['captured_boot']
        and committed['policy'] == c['dsh']['web']['egress_evidence']
        and committed['policy']['path'] == str(home / 'workers/dsh/inputs' / ('web-policy-successor-' + committed['policy']['sha256'] + '.json'))
        and _postboot_dsh_same(policy, dict(effective, boot_id=boot, net_namespace=[ns.st_dev, ns.st_ino])),
        'postboot_dsh_only_current_scope_delta_required')
    for ref in (c['dsh']['node'], c['dsh']['cli'], c['dsh']['patch'], *c['dsh']['native_files']):
        _pin(ref).read()
    web.checked_patch(_pin(c['dsh']['patch']).read())
    # Preserve all four source/native smoke results; only the new boot's safety
    # and network observations replace their stale environmental observations.
    smoke = proof['workers']['dsh']['smoke']
    _postboot_dsh_need([row['kind'] for row in smoke] == ['version', 'help', 'headless-config', 'headless-help']
        and all(row['observation']['returncode'] == 0 and row['observation']['reaped'] is True
                and row['observation']['timeout'] is False for row in smoke), 'postboot_dsh_retained_smoke_changed')
    folder = Path(value['stage_folder'])
    _postboot_dsh_need(folder.resolve() == folder and folder.parent == home / FOLDER
        and folder.name == 'dsh-postboot-' + boot, 'postboot_dsh_stage_path_changed')
    scope._private(folder, directory=True)
    return folder


def _postboot_dsh_validate(c, value, *, binding=None, generation=None):
    try:
        folder = _postboot_dsh_inputs(c, value, binding=binding, generation=generation)
        from .runtime_observers import checked_dsh_postboot
        checked_dsh_postboot(value['observation'], c, Path(c['runtime_home']), folder)
        return c
    except HostUnavailable:
        raise
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        raise HostUnavailable('postboot_dsh_revalidation_invalid') from None


def _postboot_dsh_health_if_present(c, *, binding=None, generation=None):
    if ('dsh' not in c or 'a0' in c or c['runtime_home'] != str(_r481_HOME)
            or c['runtime_profile'] != 'telegram-bot-9000000001'):
        return None
    path = Path(c['runtime_home']) / 'workers/dsh/postboot-revalidation.json'
    if not os.path.lexists(path):
        return None
    return _postboot_dsh_validate(c, _postboot_dsh_document(pin(path)), binding=binding, generation=generation)


def observe_postboot_dsh(c, policy_intent, policy_committed, budget, *, verify):
    """Root produces a proposed sidecar; publication remains the caller's step."""
    from .runtime_observers import dsh_postboot_observe
    c = validate_runtime(c)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    folder = Path(c['runtime_home']) / FOLDER / ('dsh-postboot-' + boot)
    from hermes_cli import friday_user_scope as scope
    _postboot_dsh_need(os.path.lexists(folder), 'postboot_dsh_owned_stage_required')
    scope._private(folder, directory=True)
    value = {'schema': _POSTBOOT_DSH_SCHEMA, 'home': c['runtime_home'], 'profile': c['runtime_profile'],
        'generation': 2, 'memo': _POSTBOOT_DSH_MEMO,
        'policy_transaction': {'intent': policy_intent, 'committed': policy_committed},
        'runtime_sha256': digest({k: v for k, v in c.items() if k != 'runtime_receipt'}),
        'sources': _postboot_dsh_sources(), 'stage_folder': str(folder), 'observation': None}
    verify(); _postboot_dsh_inputs(c, value)
    value['observation'] = dsh_postboot_observe(c, Path(c['runtime_home']), folder, budget, verify=verify)
    verify(); _postboot_dsh_validate(c, value)
    return value


def publish_postboot_dsh(c, value, *, verify):
    """Publish one checked sidecar; never overwrite or repeat the observation."""
    from .onboarding import _new_file
    c = validate_runtime(c)
    _postboot_dsh_need(callable(verify), 'postboot_dsh_owner_verification_required')
    verify(); _postboot_dsh_validate(c, value)
    path = Path(c['runtime_home']) / 'workers/dsh/postboot-revalidation.json'
    _postboot_dsh_need(not os.path.lexists(path), 'postboot_dsh_sidecar_exists_requires_inspection')
    _new_file(path, (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode())
    verify(); _postboot_dsh_health_if_present(c)
    return pin(path)


# S442 current-boot A0 cold qualification. Old attempts stay immutable.
from .a0_bootstrap import InitialProbe as _PostbootA0InitialProbe, PrerequisitePending
from .a0_bootstrap import credentials
from .host_runtime import a0_deployment_contract, a0_runtime_module

_POSTBOOT_A0_SCHEMA = 'friday.a0-postboot-revalidation.v1'
_POSTBOOT_A0_SIDECAR = 'workers/a0/postboot-revalidation.json'
_POSTBOOT_A0_FOLDER = 'workers/a0/postboot'
_POSTBOOT_A0_SOURCES = ('user_worker_join.py','host_runtime.py','runtime_observers.py','worker_provision.py',
    'a0_bootstrap.py','host_record.py','runtime_process.py','runtime_primitives.py',
    'adapters/a0.py','adapters/a0_native.py','adapters/a0_config.py',
    'adapters/a0_profile.py','adapters/a0_web.py')

def _postboot_a0_bridge():
    """Load only the fixed private bridge bytes."""
    raw = _r481_read(_S443_NATIVE480_VERIFIER)
    ns = {'__file__':_S443_NATIVE480_VERIFIER['path'], '__name__':'_s443_exact_native480'}
    exec(compile(raw,_S443_NATIVE480_VERIFIER['path'],'exec'),ns)
    return ns


def _postboot_a0_native480(c=None, request_ref=None, receipt_ref=None):
    """Authenticate the separate installed native480 operation; never relabel4ad."""
    ns = _postboot_a0_bridge()
    if request_ref is None and receipt_ref is None:
        current = ns['current480']()
        request_ref, receipt_ref = current['request'], current['receipt']
    _postboot_a0_need(request_ref is not None and receipt_ref is not None,
                      'postboot_a0_exact_native480_refs_required')
    return ns, ns['verify480'](request_ref,receipt_ref,config=c)


def _postboot_a0_runtime480(c, request_ref, receipt_ref):
    return _postboot_a0_bridge()['runtime480'](c,request_ref,receipt_ref)


def _postboot_a0_need(value, reason):
    if value is not True: raise HostUnavailable(reason)

def _postboot_a0_producer_ref():
    return pin(Path(__file__).resolve())

def _postboot_a0_sources():
    marker = _postboot_dsh_document(pin(_r481_H/'FRIDAY-INSTALL.json'))
    result = {}
    for name in _POSTBOOT_A0_SOURCES:
        relative = 'plugins/friday_rework/' + name
        ref = {'path':str(_r481_H/relative),'sha256':marker['plugin_files'][relative]}
        _r481_read(ref); result[relative] = ref
    _postboot_a0_need(result['plugins/friday_rework/user_worker_join.py']==_postboot_a0_producer_ref(),
                      'postboot_a0_installed_producer_required')
    return result

class _CurrentBootA0Probe(_PostbootA0InitialProbe):
    def __init__(self, runtime, binding, generation, preparations, budget, verify, *,
                 original_seconds=None, inherited_attempt=None, _closed_predecessor=None):
        from hermes_cli import friday_user_scope as scope
        if scope._CURRENT.get() is not None:
            raise PermissionError('operator_source_scope_required')
        self.c = a0_deployment_contract(runtime)
        self.home = Path(self.c['runtime_home'])
        self.binding, self.generation = copy.deepcopy(binding), generation
        self.preparations = copy.deepcopy(preparations)
        self.budget, self.verify = budget, verify
        self.closed_predecessor=copy.deepcopy(_closed_predecessor)
        stage=self.home/_POSTBOOT_A0_FOLDER
        if self.closed_predecessor is not None:
            _postboot_a0_need(type(self.closed_predecessor) is dict
                and set(self.closed_predecessor)=={'closure','request'}
                and self.closed_predecessor['closure']==_S447_COLD_CLOSURE,
                's447_exact_predecessor_marker_required')
            _s447_cold_request(self.closed_predecessor['request'],c=self.c,budget=budget)
            stage=self.home/_S447_COLD_FOLDER
        self.folder = stage/'bootstrap'
        self.plan_path = stage/'probe-plan.json'
        self.runtime = self.route = self.keys = self.created = None
        self.route_module = None
        self.pending_sample = False
        self.sampling_uncertainty = False
        self.sample_attempts = []
        self.samples = []
        self.claimed = self.start_attempted = False
        self.state = {'phase': 'CLAIMED', 'route': None, 'created': None, 'samples': [],
                      'pending_sample': False, 'sampling_uncertainty': False,
                      'sample_attempts': [], 'keys': 'NOT_PREPARED', 'settlement': None}
        from hermes_cli import friday_user_scope as scope
        from hermes_cli.friday_credential_admission import owned_values
        scope._private(self.home, directory=True)
        if (self.folder.exists() or self.folder.is_symlink()
                or self.plan_path.exists() or self.plan_path.is_symlink()):
            raise HostUnavailable('own_a0_bootstrap_requires_reconciliation')
        if (binding['runtime_profile'] != self.c['runtime_profile']
                or type(generation) is not int or generation < 1):
            raise HostUnavailable('foreign_a0_bootstrap_binding')
        self.config_pin = pin(self.home / 'config.yaml')
        self.credential_pins = credentials(self.home)
        self.values = owned_values(self.home)
        from .adapters.a0_config import KEY_REFERENCES
        names = {*KEY_REFERENCES.values(), 'SEARXNG_SECRET'}
        if not names.issubset(self.values):
            raise PrerequisitePending('own_a0_scoped_credentials_missing')
        try: self.m = a0_runtime_module(self.c)
        except (OSError, ValueError, RuntimeError, AttributeError, SyntaxError) as exc:
            raise PrerequisitePending('own_a0_reviewed_native_source_unavailable') from exc
        a = self.c['a0']; m = self.m
        if (str(m.DOCKER) != a['docker']['path'] or str(m.LAUNCHER) != a['launcher']['path']
                or str(m.PROJECT / '.runtime/rootless-docker/supervisor' / m.DAEMON) != a['daemon_unit']['path']):
            raise HostUnavailable('a0_runtime_native_pin_mismatch')
        # This phase inherits setup's entry clock. Installation keeps its own
        # original installer clock; neither operation receives another 3600s.
        seconds = min(600, self.c['budget_seconds']) if original_seconds is None else original_seconds
        if type(seconds) is not int or not 30 <= seconds <= min(600,self.c['budget_seconds']):
            raise HostUnavailable('original_a0_bootstrap_clock_required')
        started = budget.deadline - seconds
        now = time.monotonic()
        if not 0 < started <= now < budget.deadline:
            raise HostUnavailable('original_a0_bootstrap_clock_required')
        accepted_unix = time.time() - (now - started)
        acceptance = {'accepted_unix': accepted_unix,
                      'accepted_monotonic_ns': int(started * 10**9),
                      'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
        phase = {'purpose': 'CURRENT_BOOT_DEPLOYMENT_PROBE', 'home': str(self.home),
                 'binding': self.binding, 'generation': generation,
                 'preparations': self.preparations, 'runtime_sha256': digest({k:v for k,v in self.c.items() if k!='runtime_receipt'}),
                 'config': self.config_pin, 'credentials': self.credential_pins,
                 'producer': _postboot_a0_producer_ref(), 'acceptance': acceptance, 'seconds': seconds}
        if inherited_attempt is not None:
            if (inherited_attempt['boot_id'] != acceptance['boot_id']
                    or budget.deadline > inherited_attempt['deadline_mono']):
                raise HostUnavailable('inherited_a0_bootstrap_deadline_changed')
            phase['inherited_attempt'] = copy.deepcopy(inherited_attempt)
        if self.closed_predecessor is not None:
            phase['closed_predecessor']=copy.deepcopy(self.closed_predecessor)
        task = 'native-' + digest(phase)
        workspace = Path(self.c['workspace_root']) / task
        self.identity = {'existing_task_id': task, 'admission_hash': hashlib.sha256(task.encode()).hexdigest(),
            'owner': {'bot_id': binding['account_id'], 'user_id': binding['user_id'],
                      'profile': binding['runtime_profile'], 'chat_id': '', 'thread_id': '',
                      'message_id': '', 'session_key': 'own-profile-initial-probe', 'session_id': digest(phase)},
            'worker_kind': 'a0', 'brief_sha256': digest({'purpose': 'CURRENT_BOOT_DEPLOYMENT_PROBE'}),
            'workspace_reference': str(workspace),
            'supervisor': {'scope': 'user', 'unit': 'friday-rework-worker-' + task[7:39] + '.service'},
            'created_at_unix': accepted_unix, 'budget_seconds': seconds,
            'deadline_unix': accepted_unix + seconds}
        self.acceptance = acceptance
        self.original = dict(phase, schema='friday.a0.currentboot-probe.v1', association=self.identity,
                             deadline_monotonic=budget.deadline, retry_authorized=False)
        self.current()
        # Native registration, inactive/exclusive daemon, real deadlines and
        # source/network/kernel readback are the existing admission mechanism.
        # No ready flag, static template or operator-provided plan substitutes.
        if not callable(getattr(m, 'route_preflight', None)):
            raise PrerequisitePending('own_a0_reviewed_bootstrap_runtime_missing')
        try:
            m.route_preflight(self.identity, acceptance, a, budget=self.left)
        except (OSError, ValueError, RuntimeError) as exc:
            raise PrerequisitePending('own_a0_native_prerequisites_pending') from exc
        self.current()


    def _record_cleanup_failures(self, failures):
        """Protected bounded causal metadata; never error messages or locals."""
        from .onboarding import _new_file
        extra = {self.c['a0']['runtime']['path']: 'native/a0_runtime.py'}
        if self.route is not None:
            extra[self.route['stop_source']['path']] = 'native/a0_route_stop.py'
        rows = []
        for stage, error in failures[:8]:
            chain = []; seen = set()
            for _ in range(4):
                if error is None or id(error) in seen: break
                seen.add(id(error)); item = _failure_location(error)
                # The code objects were loaded from these existing pinned refs.
                # Static labels only; no exception-provided path/name is emitted.
                for name, label in (('RuntimeStopUnconfirmed', 'native_stop_unconfirmed'),
                                    ('RuntimeErrorBoundary', 'native_runtime_boundary')):
                    if type(error) is vars(self.m).get(name): item['exception_type'] = label
                tb = BaseException.__traceback__.__get__(error)
                for _ in range(64):
                    if tb is None: break
                    module = extra.get(tb.tb_frame.f_code.co_filename)
                    if module is not None and 0 < tb.tb_lineno < 2**31:
                        item['source_frames'].append({'module': module, 'line': tb.tb_lineno})
                        item['source_frames'] = item['source_frames'][-8:]
                    tb = tb.tb_next
                chain.append(item)
                cause = BaseException.__cause__.__get__(error)
                error = cause if cause is not None else (
                    None if BaseException.__suppress_context__.__get__(error)
                    else BaseException.__context__.__get__(error))
            rows.append({'stage': stage, 'causes': chain, 'chain_truncated': error is not None})
        folder = self.folder.parent
        evidence = {'schema': 'friday.a0-postboot-cleanup-diagnostic.v1',
            'state': 'STOP_UNCONFIRMED', 'readiness': 'NOT_READY', 'retry_authorized': False,
            'original': pin(folder/'original.json'),
            'bootstrap_original': pin(self.folder/'original.json'),
            'failures': rows, 'failures_truncated': len(failures)>8}
        _new_file(folder/'cleanup-diagnostic.json',
            (json.dumps(evidence,sort_keys=True,allow_nan=False)+'\n').encode())



def _postboot_a0_config(c,value):
    """Admit prepublication CAS or the exact later A0-only runtime projection."""
    import yaml
    home=Path(c['runtime_home']); reference=value['config']
    _postboot_a0_need(reference['path']==str(home/'config.yaml'),'postboot_a0_config_path_changed')
    archive={'path':str(_postboot_a0_folder(c,value)/'config.before.yaml'),'sha256':reference['sha256']}
    before_raw=_r481_read(archive)
    current_ref=pin(home/'config.yaml')
    if current_ref==reference: return
    before=yaml.safe_load(before_raw); current=yaml.safe_load(_r481_read(current_ref))
    expected=copy.deepcopy(before)
    old=expected['plugins']['entries']['friday_rework']['settings']['runtime']
    rows=configured_runtimes(old)
    _postboot_a0_need('dsh' in rows and 'a0' in rows and old.get('enabled') is True
        and 'workers' in old,'postboot_a0_fourlink_prior_runtime_changed')
    # Preserve the whole original document and DSH subtree byte-semantically.
    old['workers']['a0']=copy.deepcopy(c)
    _postboot_a0_need(_postboot_dsh_same(current,expected),'postboot_a0_fourlink_runtime_projection_changed')


def _postboot_a0_inputs(c, value, *, binding=None, generation=None):
    """Current mutable owner/CAS plus exact native successor, no clock renewal."""
    from hermes_cli import friday_user_scope as scope
    home = Path(c['runtime_home'])
    _postboot_a0_need('a0' in c and c['runtime_home']==str(_r481_HOME)
        and c['runtime_profile']=='telegram-bot-9000000001', 'postboot_a0_exact_home_required')
    keys = {'schema','home','profile','generation','binding','preparations','native_successor',
        'runtime_sha256','sources','original_attempt','config','credentials','plan',
        'bootstrap_original','custody','observation','observed','effects','per_job_authority'}
    _postboot_a0_need(type(value) is dict and set(value) in (keys,keys|{'closed_predecessor'}) and value['schema']==_POSTBOOT_A0_SCHEMA
        and value['home']==str(home) and value['profile']==c['runtime_profile']
        and type(value['generation']) is int and value['generation']>=1
        and (generation is None or value['generation']==generation)
        and (binding is None or value['binding']==binding)
        and value['binding']['runtime_profile']==c['runtime_profile']
        and value['runtime_sha256']==digest({k:v for k,v in c.items() if k!='runtime_receipt'})
        and value['effects']=='OBSERVATION_ONLY' and value['per_job_authority']=='NOT_GRANTED',
        'postboot_a0_identity_changed')
    scope._private(home,directory=True)
    setup = _postboot_dsh_document(pin(home/scope.ONBOARDING))
    _postboot_a0_need(setup['binding_sha256']==scope._fingerprint(value['binding']),
                      'postboot_a0_current_binding_changed')
    _postboot_a0_need((value['sources']==_postboot_a0_sources() or _s446_source_compat()['retained_a0_observation'](c,value,_postboot_a0_sources())), 'postboot_a0_sources_changed')
    successor = value['native_successor']
    _postboot_a0_need(type(successor) is dict and set(successor)=={'request','receipt'},
                      'postboot_a0_exact_native_receipt_required')
    _postboot_a0_native480(c,successor['request'],successor['receipt'])
    for kind,ref in value['preparations'].items():
        _postboot_a0_need(kind in ('a0','dsh'),'postboot_a0_preparations_changed')
        v,before = preparation(home,c['runtime_profile'],kind,ref)
        _postboot_a0_need(v['generation']==value['generation']
            and v['principal_binding_sha256']==setup['binding_sha256'], 'postboot_a0_preparation_owner_changed')
        if kind=='a0':
            expected = _postboot_a0_runtime480(before,successor['request'],successor['receipt'])
            _postboot_a0_need({k:v for k,v in c.items() if k!='runtime_receipt'}==
                {k:v for k,v in expected.items() if k!='runtime_receipt'}, 'postboot_a0_preparation_changed')
    _postboot_a0_need(set(value['preparations'])=={'a0','dsh'}, 'postboot_a0_preparations_changed')
    _postboot_a0_config(c,value)
    _postboot_a0_need(value['credentials']==credentials(home), 'postboot_a0_owner_inputs_changed')
    claim = _r481_claim_checked(value['original_attempt'])
    _postboot_a0_need(claim['budget_seconds']==600==c['budget_seconds']
        and claim['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'postboot_a0_genuine_current_boot_required')
    _postboot_a0_folder(c,value)
    a0_deployment_contract(c)
    return home,claim


def _postboot_a0_custody(c, value):
    """The unchanged cold owner's durable identities, in its new fixed namespace."""
    home=Path(c['runtime_home']); folder=_postboot_a0_folder(c,value)
    _postboot_a0_need(value['plan']==pin(folder/'probe-plan.json')
        and value['bootstrap_original']==pin(folder/'bootstrap/original.json'),
        'postboot_a0_exact_plan_required')
    stage=_postboot_dsh_document(pin(folder/'original.json'))
    expected=copy.deepcopy(value)
    for name in ('plan','bootstrap_original','custody','observation','observed'): expected[name]=None
    _postboot_a0_need(stage==expected,'postboot_a0_original_stage_changed')
    _postboot_a0_need(not os.path.lexists(folder/'failure.json'),'postboot_a0_failed_attempt_no_replay')
    original=_postboot_dsh_document(value['bootstrap_original'])
    state_ref=pin(folder/'bootstrap/state.json'); state=_postboot_dsh_document(state_ref)
    plan=_postboot_dsh_document(value['plan'])
    phase={k:v for k,v in original.items() if k not in
        ('schema','association','deadline_monotonic','retry_authorized')}
    identity=original['association']; task='native-'+digest(phase); owner=identity['owner']
    claim=value['original_attempt']; acceptance=original['acceptance']
    _postboot_a0_need(original['schema']=='friday.a0.currentboot-probe.v1'
        and original['purpose']=='CURRENT_BOOT_DEPLOYMENT_PROBE'
        and original['home']==str(home) and original['binding']==value['binding']
        and original['generation']==value['generation']
        and original['preparations']==value['preparations']
        and original['runtime_sha256']==value['runtime_sha256']
        and original['config']==value['config'] and original['credentials']==value['credentials']
        and original.get('closed_predecessor')==value.get('closed_predecessor')
        and (original['producer']==_postboot_a0_producer_ref() or _s446_source_compat()['retained_a0_producer'](c,value,original)) and original['retry_authorized'] is False
        and original['seconds']==claim['budget_seconds']
        and original['deadline_monotonic']==claim['deadline_mono']
        and acceptance['boot_id']==claim['boot_id']
        and acceptance['accepted_monotonic_ns']==int(claim['started_mono']*10**9)
        and identity['existing_task_id']==task and identity['admission_hash']==hashlib.sha256(task.encode()).hexdigest()
        and owner['profile']==value['profile'] and owner['user_id']==value['binding']['user_id']
        and owner['bot_id']==value['binding']['account_id']
        and owner['session_key']=='own-profile-initial-probe' and owner['session_id']==digest(phase)
        and identity['workspace_reference']==str(Path(c['workspace_root'])/task)
        and identity['supervisor']=={'scope':'user','unit':'friday-rework-worker-'+task[7:39]+'.service'}
        and identity['budget_seconds']==claim['budget_seconds']
        and identity['created_at_unix']==acceptance['accepted_unix']
        and identity['deadline_unix']==identity['created_at_unix']+claim['budget_seconds']
        and state['plan']==value['plan'] and plan['association_binding']==identity
        and plan['accepted_monotonic_ns']==acceptance['accepted_monotonic_ns']
        and plan['boot_id']==claim['boot_id'] and plan['original_budget_seconds']==claim['budget_seconds']
        and plan['accepted_unix']==acceptance['accepted_unix']
        and plan['deadline_unix']==identity['deadline_unix']
        and state['route']['association']==identity and state['route']['acceptance']==acceptance
        and state['route']['network']==plan['network'], 'postboot_a0_cold_owner_changed')
    settlement=state['settlement']; obs=value['observation']
    _postboot_a0_need(state['phase']=='STOPPED' and state['pending_sample'] is False
        and state['sampling_uncertainty'] is False and state['sample_attempts']
        and all(s['phase']=='OBSERVED' for s in state['sample_attempts'])
        and settlement['status']=='STOP_CONFIRMED' and settlement['keys']=='REMOVED'
        and settlement['container']['status']=='STOP_CONFIRMED'
        and settlement['container']['native_container_stopped'] is True
        and settlement['container'].get('current_sampling')!='UNKNOWN'
        and settlement['container']['container_id']==state['created']['container_id']==obs['container_id']
        and state['created']['invocation_id']==obs['invocation_id']
        and settlement['retirement']['status']=='INITIAL_PROBE_RETIRED'
        and settlement['retirement']['container_id']==obs['container_id']
        and settlement['route']['status']=='STOP_CONFIRMED', 'postboot_a0_cleanup_unconfirmed')
    from hermes_cli import friday_user_scope as scope
    scope._private(folder/'bootstrap',directory=True)
    _postboot_a0_need({p.name for p in (folder/'bootstrap').iterdir()}=={'original.json','state.json'},
                      'postboot_a0_custody_inventory_changed')
    return {'original':value['bootstrap_original'],'settlement':state_ref}


def _postboot_a0_observations(c,value):
    """Same native result requirements, with the actual fresh runtime pin."""
    import re
    from .adapters.a0_web import checked_web
    m=a0_runtime_module(c); obs=value['observation']; claim=value['original_attempt']
    plan=_postboot_dsh_document(value['plan']); m.validate(plan,check_files=False)
    _postboot_a0_need(set(obs)=={'plan','container_id','invocation_id','native_probe','web','route','native_resources'}
        and obs['plan']==value['plan'] and plan.get('deployment')==c['a0']['deployment']
        and plan.get('web')==c['a0']['web'] and plan.get('git_metadata')==c['a0']['git_metadata']
        and type(plan['network']) is dict and plan['code_sha256']==c['a0']['runtime']['sha256']
        and plan['docker_sha256']==c['a0']['docker']['sha256']
        and plan['daemon_unit_sha256']==c['a0']['daemon_unit']['sha256']
        and plan['network']['launcher_sha256']==c['a0']['launcher']['sha256']
        and plan['network']['policy_sha256']==c['a0']['policy']['sha256']
        and obs['route'].get('id')==plan['network']['id']
        and value['observed']['boot_id']==claim['boot_id']
        and claim['started_mono']<=value['observed']['monotonic']<claim['deadline_mono']
        and plan['accepted_unix']<=value['observed']['unix']<plan['deadline_unix'],
        'postboot_a0_native_observation_changed')
    from .host_runtime import deployment_observations
    deployment_observations(c,{'schema':_POSTBOOT_A0_SCHEMA,'workers':{'a0':obs},
        'observed':value['observed']},claim,_postboot_a0_folder(c,value))
    m.probe_report_checked(obs['native_probe'],c['a0']['deployment']); checked_web(c['a0']['web'])
    resources=obs['native_resources']; caps=resources.get('caps',{})
    _postboot_a0_need(obs['web'].get('status')=='CURRENT_NATIVE_WEB_SERVICE_CHECKED'
        and obs['web'].get('version')==c['a0']['web']['version']
        and obs['route'].get('status')=='CURRENT_LOCAL_NETWORK_CHECKED'
        and bool(re.fullmatch('[0-9a-f]{64}',obs['container_id']))
        and bool(re.fullmatch('[0-9a-f]{32}',obs['invocation_id']))
        and resources.get('running') is True and resources.get('unit_quiescent') is False
        and caps=={'memory.max':str(m.MEMORY),'memory.swap.max':'0','pids.max':str(m.PIDS),
                   'cpu.max':caps.get('cpu.max')}, 'postboot_a0_native_resources_changed')
    quota,period=caps['cpu.max'].split()
    _postboot_a0_need(quota.isdecimal() and period.isdecimal() and int(period)>0
        and int(quota)==2*int(period), 'postboot_a0_native_resources_changed')
    processes=obs['web'].get('processes')
    _postboot_a0_need(type(processes) is list and len(processes)==2
        and {p.get('name') for p in processes}=={'run_ui','run_searxng'}
        and all(set(p)=={'name','pid','start','statename'} and p['statename']=='RUNNING'
            and type(p['pid']) is int and p['pid']>0 and type(p['start']) is int and p['start']>0
            for p in processes), 'postboot_a0_native_web_processes_changed')


def _postboot_a0_validate(c,value,*,binding=None,generation=None):
    try:
        c=validate_runtime(c)
        _postboot_a0_inputs(c,value,binding=binding,generation=generation)
        _postboot_a0_observations(c,value)
        _postboot_a0_need(value['custody']==_postboot_a0_custody(c,value), 'postboot_a0_custody_changed')
        return c
    except HostUnavailable: raise
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,AttributeError):
        raise HostUnavailable('postboot_a0_revalidation_invalid') from None


def checked_postboot_a0(c,proof_ref,*,binding=None,generation=None):
    c=validate_runtime(c)
    _postboot_a0_need(proof_ref['path']==str(Path(c['runtime_home'])/_POSTBOOT_A0_SIDECAR),
                      'postboot_a0_fixed_sidecar_required')
    value=_postboot_dsh_document(proof_ref)
    _postboot_a0_validate(c,value,binding=binding,generation=generation)
    expected=readiness_receipt(c,[value['preparations']['a0'],proof_ref])
    _postboot_a0_need(_postboot_dsh_document(c['runtime_receipt'])==expected,
                      'postboot_a0_readiness_not_produced')
    return c


def _postboot_a0_health_if_present(c,*,binding=None,generation=None):
    if 'a0' not in c: return None
    path=Path(c['runtime_home'])/_POSTBOOT_A0_SIDECAR
    if not os.path.lexists(path): return None
    return checked_postboot_a0(c,pin(path),binding=binding,generation=generation)


def observe_postboot_a0(c,binding,generation,preparations,native_request_ref,native_receipt_ref,budget,*,verify,
        _closed_predecessor=None):
    """New future cold diagnostic, genuine owner, one original budget, no jobs."""
    from .a0_bootstrap import own_probe
    from .runtime_observers import a0_observe
    from .onboarding import _new_file
    _postboot_a0_need(callable(verify),'postboot_a0_owner_verification_required')
    c=validate_runtime(c); home=Path(c['runtime_home']); folder=home/_POSTBOOT_A0_FOLDER
    if _closed_predecessor is not None:
        _postboot_a0_need(type(_closed_predecessor) is dict
            and set(_closed_predecessor)=={'closure','request'}
            and _closed_predecessor['closure']==_S447_COLD_CLOSURE,
            's447_exact_predecessor_marker_required')
        request=_s447_cold_request(_closed_predecessor['request'],c=c,budget=budget)
        _postboot_a0_need(request['native_request']==native_request_ref
            and request['native_receipt']==native_receipt_ref
            and not os.path.lexists(home/_POSTBOOT_A0_SIDECAR),
            's447_exact_missing_cold_scope_required')
        folder=home/_S447_COLD_FOLDER
    _postboot_a0_need(type(budget.seconds) is int and budget.seconds==600==c['budget_seconds']
        and budget.deadline==budget.original_deadline==budget.started+600,
        'postboot_a0_original600_required')
    verify(); budget.check(reserve=30)
    _postboot_a0_native480(c,native_request_ref,native_receipt_ref)
    # O_EXCL namespace is the no-replay claim, before route or native effects.
    folder.mkdir(mode=0o700)
    claim={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'started_mono':budget.started,'deadline_mono':budget.deadline,'budget_seconds':600}
    value={'schema':_POSTBOOT_A0_SCHEMA,'home':str(home),'profile':c['runtime_profile'],
        'generation':generation,'binding':copy.deepcopy(binding),'preparations':copy.deepcopy(preparations),
        'native_successor':{'request':native_request_ref,'receipt':native_receipt_ref},
        'runtime_sha256':digest({k:v for k,v in c.items() if k!='runtime_receipt'}),
        'sources':_postboot_a0_sources(),'original_attempt':claim,'config':pin(home/'config.yaml'),
        'credentials':credentials(home),'plan':None,'bootstrap_original':None,'custody':None,
        'observation':None,'observed':None,'effects':'OBSERVATION_ONLY','per_job_authority':'NOT_GRANTED'}
    if _closed_predecessor is not None:
        value['closed_predecessor']=copy.deepcopy(_closed_predecessor)
    _new_file(folder/'config.before.yaml',(home/'config.yaml').read_bytes())
    _postboot_a0_inputs(c,value,binding=binding,generation=generation)
    _new_file(folder/'original.json',(json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode())
    try:
        probe=_CurrentBootA0Probe(c,binding,generation,preparations,budget,verify,original_seconds=600,
            _closed_predecessor=_closed_predecessor)
        with own_probe(probe) as plan:
            value['plan']=plan
            value['observation']=budget.call(a0_observe,c,plan,budget,probe_owner=probe)
            value['observed']={'boot_id':claim['boot_id'],'monotonic':time.monotonic(),'unix':time.time()}
            verify()
            # The full completed observation survives a later cleanup refusal.
            # This is evidence only; custody is still absent and cannot publish.
            try:
                checkpoint={'schema':'friday.a0-postboot-unsettled-observation.v1',
                    'state':'UNSETTLED','readiness':'NOT_READY','retry_authorized':False,
                    'original':pin(folder/'original.json'),
                    'bootstrap_original':pin(folder/'bootstrap/original.json'),
                    'value':value}
                raw=(json.dumps(checkpoint,sort_keys=True,allow_nan=False)+'\n').encode()
                if len(raw)<=min(c['max_file_bytes'],16*1024*1024):
                    _new_file(folder/'observation.unsettled.json',raw)
            except Exception:
                pass  # Best-effort evidence never prevents the owner's cleanup.
        value['bootstrap_original']=pin(folder/'bootstrap/original.json')
        value['custody']=_postboot_a0_custody(c,value)
        verify(); budget.call(_postboot_a0_validate,c,value,binding=binding,generation=generation)
        return value
    except BaseException as exc:
        from .runtime_process import StopUnconfirmed
        failure={'state':'STOP_UNCONFIRMED' if isinstance(exc,StopUnconfirmed) else 'REFUSED_OR_UNCERTAIN',
            'original_attempt':claim,'retry_authorized':False}
        try: failure['diagnostic']=_failure_diagnostic(exc)
        except Exception: failure['diagnostic']={'error_kind':'diagnostic_unavailable'}
        try: _new_file(folder/'failure.json',(json.dumps(failure,sort_keys=True,allow_nan=False)+'\n').encode())
        except OSError: pass
        raise


def publish_postboot_a0(c,value,*,verify):
    """Publish the same settled observation once; no observation/effect replay."""
    from .onboarding import _new_file
    verify(); _postboot_a0_validate(c,value)
    folder=_postboot_a0_folder(c,value)
    _postboot_a0_need(not os.path.lexists(folder/'failure.json'),'postboot_a0_failed_attempt_no_replay')
    path=Path(c['runtime_home'])/_POSTBOOT_A0_SIDECAR
    _new_file(path,(json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode())
    verify(); return pin(path)


def observe_postboot_a0_onboarding(onboarding,*,profile,session,expected_config_sha256,generation,
        platform,transport_profile,account_id,user_id,native_request_ref,native_receipt_ref,budget,
        _closed_predecessor=None):
    """Root-only normal Onboarding/session bridge; no profile/config publication."""
    from hermes_cli import friday_user_scope as scope
    from hermes_cli.config import config_write_transaction,require_readable_config_before_write
    from hermes_cli.plugins_state import PluginState
    from .associations import Associations
    _postboot_a0_need(profile==transport_profile,'postboot_a0_receiving_transport_required')
    # Require the supplied operation's already accepted original600 clock.
    _postboot_a0_need(budget.seconds==600 and budget.started<=time.monotonic(),
                      'postboot_a0_original_clock_required')
    with onboarding.transaction(profile,expected_config_sha256,session) as (root,access,config):
        home,binding,row,setup=onboarding._prepared(root,access.state,platform,transport_profile,
                                                  account_id,user_id,generation)
        _postboot_a0_need(root==_r481_H and home==_r481_HOME and row['enabled'] is True,
                          'postboot_a0_current_admitted_home_required')
        with scope.authority(home),config_write_transaction(home/'config.yaml'):
            own=require_readable_config_before_write(home/'config.yaml')
            selected=configured_runtimes(own['plugins']['entries']['friday_rework']['settings']['runtime'])
            # Read both current preparations once; only A0 is proposed for attach.
            prepared={k:pin(home/'workers'/k/'runtime-input.json') for k in ('dsh','a0')}
            c=preparation(home,binding['runtime_profile'],'a0',prepared['a0'])[1]
            c=_postboot_a0_runtime480(c,native_request_ref,native_receipt_ref)
            config_ref=pin(home/'config.yaml'); marker_ref=pin(root/'FRIDAY-INSTALL.json')
            def verify():
                budget.check()
                with scope.authority(root):
                    onboarding._verify_operator(profile,session)
                    current=onboarding._prepared(root,access.state,platform,transport_profile,
                                                  account_id,user_id,generation)
                    _postboot_a0_need(current[:3]==(home,binding,row)
                        and pin(root/'config.yaml')['sha256']==expected_config_sha256
                        and pin(root/'FRIDAY-INSTALL.json')==marker_ref
                        and pin(home/'config.yaml')==config_ref,
                        'postboot_a0_current_owner_or_cas_changed')
                    _postboot_a0_need(onboarding._native_grant(root,binding,
                        storage_readonly=onboarding._storage_readonly) is True,'postboot_a0_native_grant_revoked')
            verify()
            store=Associations(PluginState('friday_rework'))
            with store._locked() as data:
                from .supervision import NativeSupervisor
                _postboot_a0_quiet(data['jobs'],NativeSupervisor(),budget)
                value=observe_postboot_a0(c,binding,generation,prepared,native_request_ref,
                                          native_receipt_ref,budget,verify=verify,_closed_predecessor=_closed_predecessor)
                proof=publish_postboot_a0(c,value,verify=verify)
                _postboot_a0_need(configured_runtimes(require_readable_config_before_write(home/'config.yaml')
                    ['plugins']['entries']['friday_rework']['settings']['runtime'])==selected,
                    'postboot_a0_preserved_runtime_changed')
                return {'runtime':c,'proof':proof,'state':'CURRENT_BOOT_A0_OBSERVED_STOPPED_UNPUBLISHED',
                        'per_job_authority':'NOT_GRANTED'}


def _postboot_a0_quiet(jobs,supervisor,budget):
    """Current native unit/cgroup observations under the existing admission lock."""
    for row in jobs.values():
        _postboot_a0_need(row.get('host',{}).get('terminal') is not None
            and row.get('host',{}).get('quiescence') is not None, 'postboot_a0_workers_not_quiet')
        unit=budget.call(supervisor.observe,row,deadline=budget.deadline)
        expected=(row.get('native') or {}).get('invocation_id','')
        _postboot_a0_need(unit.quiescent and (unit.missing or unit.invocation_id==expected),
                          'postboot_a0_native_unit_not_quiet_or_replaced')


# This exact parser-only successor changes no launch, safety, network or CLI
# source. Its old readiness receipt remains a historical observation, not a
# newly produced receipt for a different source.
_POSTBOOT_DSH_STATUS_BEFORE = 'PRIVATE_REF_ba9a5bc2d2e98875'
_POSTBOOT_DSH_STATUS_AFTER = 'PRIVATE_REF_dcc359067ceba06f'
_POSTBOOT_DSH_STATUS_SIDECAR = 'PRIVATE_REF_04b184bd1ba42ca1'
_POSTBOOT_DSH_STATUS_JOIN_BEFORE = 'PRIVATE_REF_3536717c481ab1ef'


def _postboot_dsh_retained_receipt(c, evidence):
    result = readiness_receipt(c, evidence)
    _postboot_dsh_need(result.get('adapter_sha256') in {
        _POSTBOOT_DSH_STATUS_BEFORE, _POSTBOOT_DSH_STATUS_AFTER},
        'postboot_dsh_unreviewed_native_event_parser')
    # Every other generated receipt field still compares exactly with the
    # protected old receipt; never rewrite it or manufacture new observation.
    result['adapter_sha256'] = _POSTBOOT_DSH_STATUS_BEFORE
    return result


def proposed_postboot_dsh_native_event_status(c, previous, *, verify):
    """Root-only source successor proposal; this function has no write/effects.

    Root must preserve the original sidecar and use its existing source-update
    writer/CAS boundary to publish this proposal, then run the real consumer.
    The original observation and its clocks are preserved byte-for-byte as data.
    """
    c = validate_runtime(c)
    _postboot_dsh_need(callable(verify), 'postboot_dsh_owner_verification_required')
    path = Path(c['runtime_home']) / 'workers/dsh/postboot-revalidation.json'
    _postboot_dsh_need(previous == {'path': str(path), 'sha256': _POSTBOOT_DSH_STATUS_SIDECAR},
        'postboot_dsh_native_event_previous_required')
    verify()
    old = _postboot_dsh_document(previous)
    current = _postboot_dsh_sources()
    before = copy.deepcopy(current)
    adapter = 'plugins/friday_rework/adapters/dsh.py'
    join = 'plugins/friday_rework/user_worker_join.py'
    _postboot_dsh_need(current[adapter]['sha256'] == _POSTBOOT_DSH_STATUS_AFTER,
        'postboot_dsh_exact_native_event_parser_required')
    before[adapter]['sha256'] = _POSTBOOT_DSH_STATUS_BEFORE
    before[join]['sha256'] = _POSTBOOT_DSH_STATUS_JOIN_BEFORE
    _postboot_dsh_need(old['sources'] == before,
        'postboot_dsh_only_native_event_status_sources_required')
    proposal = copy.deepcopy(old)
    proposal['sources'] = current
    verify(); _postboot_dsh_validate(c, proposal)
    _postboot_dsh_need(_postboot_dsh_document(previous) == old,
        'postboot_dsh_native_event_previous_changed')
    verify()
    return proposal


# S446: authenticate one unchanged, already published current-boot observation.
def _s446_source_compat():
    reference = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/compat.py', 'sha256': 'PRIVATE_REF_02fcb1106bb4b088'}
    raw = _r481_read(reference)
    namespace = {'__file__':reference['path'],'__name__':'_s446_installed_source_compat'}
    exec(compile(raw,reference['path'],'exec'),namespace)
    return namespace


# S447: one missing observation after the exact fully settled failed S443 attempt.
# The old namespace, clock and failure remain immutable; no generic retry exists.
_S447_COLD_FOLDER = 'workers/a0/postboot-closed-s443-successor'
_S447_COLD_OPERATION = '<PRIVATE_CACHE>/PRIVATE_REF_79d2ca6c48dd51a8'
_S447_COLD_CLOSURE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_9f6e31f92f236f29/ROOT-FAILED-COLD-RESOURCES-CLOSED.json', 'sha256': 'PRIVATE_REF_4dc06622712e604a'}


def _s447_cold_predecessor():
    """Exact historical custody and actual Root closure, never fresh authority."""
    closed = _r481_document(_S447_COLD_CLOSURE)
    _postboot_a0_need(closed['schema']=='frw.Root.S443.failed-cold-resource-closure.v1'
        and closed['state']=='RESOURCES_SETTLED_QUALIFICATION_INCOMPLETE_NO_REPLAY'
        and all(closed[k] is True for k in ('old_container_retired','old_introduced_keys_removed',
            'old_owned_worker_daemon_network_request_guard_and_original_processes_ceased',
            'old_namespace_failure_clock_history_preserved','healthy_permanent_services_preserved',
            'source_credentials_unchanged'))
        and all(closed[k] is False for k in ('qualification_accepted',
            'complete_usable_old_observation_durable','old_effect_or_clock_replay_authorized')),
        's447_exact_settled_failed_predecessor_required')
    # Exact file refs are themselves covered by the fixed Root closure digest.
    old = {k:_r481_document(closed[k]) for k in ('original_request','original_native_return',
        'original_bootstrap','original_bootstrap_state','original_failure','original_clock',
        'original_root_intent','exact_retirement','key_cleanup')}
    _r481_read(closed['prior_readonly_cessation'])
    native = _r481_document(closed['exact_retirement_native_receipt'])
    retirement = old['exact_retirement']; keys = old['key_cleanup']
    _postboot_a0_need(retirement['schema']=='frw.Root.S443.exact-retirement-accepted.v1'
        and retirement['accepted'] is True and retirement['actual_exit_code']==0
        and retirement['container_absent'] is True
        and retirement['maintenance_stopped_and_receipts_removed'] is True
        and retirement['images_volumes_binds_sources_preserved'] is True
        and retirement['old_worker_unchanged'] is True
        and retirement['original_qualification_accepted'] is False
        and retirement['container_id']==closed['old_container_id']
        and retirement['evidence']==closed['exact_retirement_native_receipt']
        and native['schema']=='friday.a0.exact-retained-container-cleanup.v1'
        and native['status']=='EXACT_CONTAINER_REMOVED_AND_MAINTENANCE_STOPPED'
        and keys['schema']=='frw.Root.exact-existing-key-removal.v1'
        and all(keys[k] is True for k in ('accepted','existing_key_consumer_used',
            'two_introduced_scoped_keys_removed','native_web_secret_cleared',
            'original_failed_state_unchanged','services_preserved','source_credentials_unchanged'))
        and keys['old_clock_reset'] is False and keys['old_qualification_accepted'] is False
        and keys['old_container_id']==closed['old_container_id']
        and keys['retirement']==closed['exact_retirement_native_receipt'],
        's447_actual_retirement_and_keys_required')
    clock=old['original_clock']; original=old['original_bootstrap']; failure=old['original_failure']
    _postboot_a0_need(old['original_request']['original_clock']==closed['original_clock']
        and old['original_native_return']['clock']==closed['original_clock']
        and old['original_native_return']['result'] is None
        and old['original_native_return']['failure'] is not None
        and old['original_native_return']['retry_authorized'] is False
        and original['home']==str(_r481_HOME) and original['purpose']=='CURRENT_BOOT_DEPLOYMENT_PROBE'
        and original['schema']=='friday.a0.currentboot-probe.v1'
        and original['retry_authorized'] is False
        and original['seconds']==clock['budget_seconds']==600
        and original['deadline_monotonic']==clock['deadline_monotonic']
        and original['acceptance']['boot_id']==clock['boot_id']==closed['boot_id']
        and old['original_bootstrap_state']['phase']=='STOP_UNCONFIRMED'
        and old['original_bootstrap_state']['settlement'] is None
        and old['original_bootstrap_state']['created']['container_id']==closed['old_container_id']
        and native['reference']==original['association']['existing_task_id']
        and failure['state']=='STOP_UNCONFIRMED' and failure['retry_authorized'] is False
        and failure['original_attempt']=={'boot_id':clock['boot_id'],
            'started_mono':clock['started_monotonic'],'deadline_mono':clock['deadline_monotonic'],
            'budget_seconds':600}, 's447_old_failure_and_clock_must_remain_unchanged')
    _postboot_a0_need(not os.path.lexists(_r481_HOME/_POSTBOOT_A0_FOLDER/'observation.unsettled.json'),
        's447_missing_old_durable_observation_required')
    return closed


def _s447_cold_request(reference, *, c=None, budget=None):
    """Protected exact future Root request; clocks are fresh only at admission."""
    import math
    request = _r481_document(reference)
    fields={'schema','native_source','python','launch_home','dashboard_api','installed_join',
        'native_refs','marker','credential_ref','credential_keys','original_clock','once_grant',
        'operation_directory','target','native_request','native_receipt',
        'predecessor_closure','source_acceptance'}
    _postboot_a0_need(type(request) is dict and set(request)==fields
        and request['schema']=='friday.a0-closed-s443-successor-root-once.v1'
        and request['predecessor_closure']==_S447_COLD_CLOSURE
        and request['operation_directory']==_S447_COLD_OPERATION
        and request['launch_home']==str(_r481_H)
        and request['native_source']==str(_r481_H/'hermes-agent')
        and request['installed_join']==_postboot_a0_producer_ref()
        and request['marker']==pin(_r481_H/'FRIDAY-INSTALL.json')
        and request['dashboard_api']['path']==str(_r481_H/'plugins/friday_rework/dashboard/api.py')
        and type(request['target']) is dict and set(request['target'])=={
            'profile','expected_config_sha256','generation','platform','transport_profile','account_id','user_id'}
        and request['target']['platform']=='telegram'
        and request['target']['profile']==request['target']['transport_profile']=='default'
        and request['target']['account_id']=='9000000002'
        and request['target']['user_id']=='9000000001'
        and type(request['target']['generation']) is int and request['target']['generation']>=1,
        's447_exact_successor_request_required')
    closed=_s447_cold_predecessor()
    old_request=_r481_document(closed['original_request'])
    _postboot_a0_need(request['native_refs']==old_request['native_refs']
        and request['python']==old_request['python']
        and request['credential_keys']=={'username':'username','password':'password'},
        's447_unchanged_native_graph_required')
    clock=_r481_document(request['original_clock'])
    _postboot_a0_need(set(clock)=={'schema','boot_id','started_monotonic','deadline_monotonic',
        'budget_seconds','reserve_seconds'}
        and clock['schema']=='friday.a0-closed-s443-successor-clock.v1'
        and type(clock['budget_seconds']) is int and clock['budget_seconds']==600
        and type(clock['reserve_seconds']) is int and clock['reserve_seconds']==30
        and all(type(clock[k]) in (int,float) and math.isfinite(clock[k])
            for k in ('started_monotonic','deadline_monotonic'))
        and clock['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()==closed['boot_id']
        and closed['observed_monotonic']<clock['started_monotonic']
        and clock['deadline_monotonic']==clock['started_monotonic']+600,
        's447_distinct_explicit600_clock_required')
    body={k:v for k,v in request.items() if k!='once_grant'}
    _postboot_a0_need(_r481_document(request['once_grant'])=={
        'schema':'friday.a0-closed-s443-successor-root-once-grant.v1',
        'request_body_sha256':hashlib.sha256((json.dumps(body,sort_keys=True,allow_nan=False)+'\n').encode()).hexdigest(),
        'operation':'MISSING_COLD_AFTER_CLOSED_S443','retry_authorized':False},
        's447_exact_successor_once_grant_required')
    compat=_s446_source_compat(); proof,transaction=compat['source_proof']()
    _postboot_a0_need(request['source_acceptance']==compat['pin'](compat['ACCEPTANCE']),
        's447_canonical_fresh_source_acceptance_required')
    accepted=_r481_document(request['source_acceptance'])
    _postboot_a0_need(accepted['schema']=='frw.Root.dsh_source.installed-source-accepted.v1'
        and all(accepted[k] is True for k in ('accepted','accepted_source_only','source_only','fresh_process'))
        and accepted['runtime_or_user_semantics_accepted'] is False
        and accepted['boot_id']==clock['boot_id']
        and all(accepted[k]==proof[v] for k,v in (('current_input','current_input'),
            ('committed','commit'),('marker','current_marker'),('plan','plan'),('source_receipt','source_receipt')))
        and request['marker']==proof['current_marker'], 's447_actual_current_source_lineage_required')
    _postboot_a0_native480(c,request['native_request'],request['native_receipt'])
    if budget is not None:
        _postboot_a0_need(type(budget.seconds) is int and budget.seconds==600
            and budget.started==clock['started_monotonic']
            and budget.deadline==budget.original_deadline==clock['deadline_monotonic']
            and budget.started<=time.monotonic()<budget.deadline-30,
            's447_original_clock_exhausted_or_replaced')
    return request


def _postboot_a0_folder(c, value):
    """A single explicit successor, while the canonical sidecar remains unchanged."""
    marker=value.get('closed_predecessor')
    if marker is None:
        _postboot_a0_need('closed_predecessor' not in value,'s447_absent_or_exact_marker_required')
        return Path(c['runtime_home'])/_POSTBOOT_A0_FOLDER
    _postboot_a0_need(type(marker) is dict and set(marker)=={'closure','request'}
        and marker['closure']==_S447_COLD_CLOSURE,'s447_exact_predecessor_marker_required')
    request=_s447_cold_request(marker['request'],c=c)
    clock=_r481_document(request['original_clock'])
    _postboot_a0_need(value['original_attempt']=={
        'boot_id':clock['boot_id'],
        'started_mono':clock['started_monotonic'],
        'deadline_mono':clock['deadline_monotonic'],
        'budget_seconds':600},'s447_successor_claim_changed')
    return Path(c['runtime_home'])/_S447_COLD_FOLDER


def observe_closed_s443_a0_onboarding(onboarding, *, successor_request_ref, **arguments):
    """Genuine current Onboarding/session and existing locks own the sole new stage."""
    from .onboarding import Onboarding
    from hermes_cli import friday_user_scope as scope
    _postboot_a0_need(type(onboarding) is Onboarding and scope._CURRENT.get() is None,
        's447_genuine_operator_onboarding_required')
    request=_s447_cold_request(successor_request_ref,budget=arguments['budget'])
    target={k:arguments[k] for k in ('profile','expected_config_sha256','generation',
        'platform','transport_profile','account_id','user_id')}
    _postboot_a0_need(target==request['target']
        and arguments['native_request_ref']==request['native_request']
        and arguments['native_receipt_ref']==request['native_receipt']
        and not os.path.lexists(_r481_HOME/_POSTBOOT_A0_SIDECAR),
        's447_exact_missing_scope_and_target_required')
    marker={'closure':copy.deepcopy(_S447_COLD_CLOSURE),'request':copy.deepcopy(successor_request_ref)}
    return observe_postboot_a0_onboarding(onboarding,_closed_predecessor=marker,**arguments)
