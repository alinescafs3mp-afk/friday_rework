"""Host fields in the existing association document, not a second job store."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import math
import re

from .associations import AssociationError, _number, _text
from .boundary import parse_brief
from .supervision import UnitObservation


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def association_address(correlation, ingress):
    # Reference derived from native identity; never a new independent task ID.
    return "native-" + digest({"correlation": correlation, "ingress": ingress})


def owner_from_ingress(correlation, ingress):
    message = ingress["message"]
    return {**{k: message[k] for k in ("bot_id", "user_id", "chat_id", "thread_id", "message_id")},
            "session_id": correlation["session_id"], "session_key": ingress["session_key"],
            "profile": ingress["runtime_profile"]}


def validate_acceptance(value):
    if (not isinstance(value, dict) or set(value) != {'accepted_unix', 'accepted_monotonic_ns', 'boot_id'}
            or type(value['accepted_unix']) not in (int, float)
            or not math.isfinite(value['accepted_unix']) or value['accepted_unix'] <= 0
            or type(value['accepted_monotonic_ns']) is not int or value['accepted_monotonic_ns'] <= 0
            or not isinstance(value['boot_id'], str) or not re.fullmatch('[0-9a-f-]{36}', value['boot_id'])):
        raise AssociationError('invalid_original_acceptance')


def validate_a0_observations(value, container_id=None):
    """Nonsecret original process identities in the existing association store."""
    if (not isinstance(value, dict) or set(value) != {'pending', 'samples'}
            or type(value['pending']) is not bool or not isinstance(value['samples'], list)):
        raise ValueError()
    for sample in value['samples']:
        if (not isinstance(sample, dict) or set(sample) != {'group', 'populated', 'processes'}
                or sample['populated'] is not True or not isinstance(sample['group'], str)
                or not sample['group'].startswith('/user.slice/')
                or str(Path(sample['group'])) != sample['group'] or '..' in Path(sample['group']).parts
                or not re.search(r'/docker-[0-9a-f]{64}\.scope$', sample['group'])
                or (container_id is not None and not sample['group'].endswith('/docker-'+container_id+'.scope'))
                or not isinstance(sample['processes'], list) or not sample['processes']):
            raise ValueError()
        for process in sample['processes']:
            if (not isinstance(process, dict) or set(process) != {'pid', 'start_ticks'}
                    or type(process['pid']) is not int or process['pid'] <= 0
                    or not isinstance(process['start_ticks'], str)
                    or not re.fullmatch('[0-9]{1,32}', process['start_ticks'])):
                raise ValueError()


def validate_a0_record(row):
    from .adapters.a0_native import NativeGrant
    from .adapters.dsh import _identity
    a = row['host']['a0']
    required = {'schema', 'acceptance', 'expected_files', 'launch', 'grant', 'key_cleanup', 'capability'}
    if (not isinstance(a, dict) or not required <= set(a) <= required | {'observations', 'route'}
            or a['schema'] not in {'friday.a0.host.v2','friday.a0.host.v3'}
            or a['schema']=='friday.a0.host.v3' and 'route' not in a
            or a['schema']=='friday.a0.host.v2' and a.get('route') is not None):
        raise ValueError()
    validate_acceptance(a['acceptance'])
    if a.get('route') is not None:
        validate_a0_route(row, a['route'])
    if (a['acceptance']['accepted_unix'] != row['created_at_unix']
            or type(row['budget_seconds']) is not int
            or row['deadline_unix'] != row['created_at_unix'] + row['budget_seconds']
            or a['expected_files'] != row['host']['binding']['runtime']['a0']['expected_files']
            or a['key_cleanup'] not in {'NOT_PREPARED', 'PREPARED', 'REMOVED', 'RECONCILIATION_REQUIRED'}):
        raise ValueError()
    if a['capability'] is not None:
        from .host_runtime import _pin
        _pin(a['capability']) # structure only; stop/recovery cannot depend on drifted source
    launch = a['launch']
    if 'observations' in a:
        created = (launch or {}).get('created')
        validate_a0_observations(a['observations'], None if created is None else created['container_id'])
    if launch is not None and a['capability'] is None: raise ValueError()
    if launch is not None:
        if not isinstance(launch, dict) or set(launch) != {'plan', 'plan_pin', 'keys_prepared_monotonic', 'created'}:
            raise ValueError()
        p = launch['plan']
        runtime = row['host']['binding']['runtime']['a0']
        owner = runtime['owner_slot'] + ':' + row['existing_task_id'] + '#1'
        identity_input = {'owner':owner,'assignment':row['existing_task_id'],'generation':1,
            'accepted_unix':row['created_at_unix'],'mode':'runtime','association_binding':_identity(row),
            'accepted_monotonic_ns':a['acceptance']['accepted_monotonic_ns'],'boot_id':a['acceptance']['boot_id'],
            'local_network':p['network'],'git_metadata':runtime['git_metadata']}
        compact_hash = lambda v: hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        plan_bytes = (json.dumps(p,sort_keys=True,indent=2)+'\n').encode()
        if (p['identity'] != compact_hash(identity_input)
                or p['schema'] != 'friday.a0.runtime-plan.v2' or p['mode'] != 'runtime'
                or p['owner'] != owner or p['owner_slot'] != runtime['owner_slot']
                or p['assignment'] != row['existing_task_id'] or type(p['generation']) is not int or p['generation'] != 1
                or p['accepted_unix'] != row['created_at_unix'] or p['deadline_unix'] != row['deadline_unix']
                or p['original_budget_seconds'] != row['budget_seconds']
                or p['unit'] != row['supervisor']['unit'] or p['container_name'] != 'frw-a0-'+row['existing_task_id'][7:39]
                or not isinstance(p['network'],dict) or p['network']['owner'] != owner
                or not re.fullmatch('[0-9a-f]{64}',p['network']['id'])
                or p['git_metadata'] != runtime['git_metadata']
                or p['docker_sha256'] != runtime['docker']['sha256']
                or p['daemon_unit_sha256'] != runtime['daemon_unit']['sha256']
                or p['ports'] != [] or p['memory_bytes'] != 2*1024**3 or p['cpus'] != 2 or p['pids'] != 256
                or p['startup_seconds'] != 120 or p['stop_seconds'] != 2
                or not Path(p['runtime_root']).is_absolute() or '..' in Path(p['runtime_root']).parts
                or p['state_dir'] != str(Path(p['runtime_root'])/p['identity']/'usr')
                or hashlib.sha256(plan_bytes).hexdigest() != launch['plan_pin']['sha256']):
            raise ValueError()
        if (p['association_binding'] != _identity(row)
                or p['accepted_monotonic_ns'] != a['acceptance']['accepted_monotonic_ns']
                or p['boot_id'] != a['acceptance']['boot_id']
                or p['code_sha256'] != row['host']['binding']['runtime']['a0']['runtime']['sha256']
                or launch['plan_pin']['path'] != str(Path(row['workspace_reference'])/'a0-plan.json')
                or set(launch['plan_pin']) != {'path', 'sha256'}
                or not re.fullmatch('[0-9a-f]{64}', launch['plan_pin']['sha256'])):
            raise ValueError()
        t = launch['keys_prepared_monotonic']
        if t is not None and (type(t) not in (int, float) or not math.isfinite(t)
                             or t < a['acceptance']['accepted_monotonic_ns']/1e9):
            raise ValueError()
        c = launch['created']
        if c is not None:
            if (not isinstance(c,dict) or set(c) != {'container_id','plan_sha256'}
                    or not re.fullmatch('[0-9a-f]{64}',c['container_id'])
                    or c['plan_sha256'] != hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()):
                raise ValueError()
    if a['grant'] is not None:
        g = NativeGrant(**a['grant'])
        if (launch is None or launch['keys_prepared_monotonic'] != g.keys_prepared_monotonic
                or launch['created'] is None or launch['created']['container_id'] != g.container_id
                or g.accepted_monotonic != a['acceptance']['accepted_monotonic_ns']/1e9
                or g.accepted_unix != row['created_at_unix'] or g.deadline_unix != row['deadline_unix']
                or g.boot_id != a['acceptance']['boot_id']
                or g.container_name != launch['plan']['container_name']
                or g.labels != {'friday.rework.owner': launch['plan']['owner'],
                    'friday.rework.assignment': row['existing_task_id'], 'friday.rework.generation': '1',
                    'friday.rework.plan': row['admission_hash']}
                or not re.fullmatch('[0-9a-f]{64}', g.container_id)
                or not re.fullmatch('[0-9a-f]{32}', g.invocation_id)
                or not re.fullmatch('[0-9a-f]{32}', g.daemon_invocation_id)
                or not isinstance(g.container_cgroup,str) or not g.container_cgroup.startswith('/user.slice/')
                or '..' in Path(g.container_cgroup).parts
                or not g.container_cgroup.endswith('/docker-'+g.container_id+'.scope')
                or g.network_verified is not True):
            raise ValueError()


def validate_a0_route(row, route):
    """Validate recorded custody, without reopening launch files or minting it.

    Absence on old rows is preserved. Hashes bind evidence; they do not by
    themselves authorize a daemon stop or manufacture native observations.
    """
    from .adapters.dsh import _identity
    from .host_runtime import _pin
    a = row['host']['a0']; native = row['host']['binding']['runtime']['a0']
    keys = {'schema', 'association', 'acceptance', 'request', 'request_sha256',
            'stop_source', 'stop_launcher', 'daemon_limits', 'pending', 'daemon',
            'network', 'samples', 'request_published', 'daemon_attempted',
            'network_attempted', 'network_removed', 'docker', 'settlement'}
    if (not isinstance(route, dict) or set(route) != keys
            or route['schema'] != 'friday.a0.host-route.v1'
            or route['association'] != _identity(row) or route['acceptance'] != a['acceptance']
            or route['pending'] not in {None, 'request', 'daemon', 'sample', 'network'}):
        raise ValueError('invalid_a0_route')
    for key in ('request_published', 'daemon_attempted', 'network_attempted', 'network_removed'):
        if type(route[key]) is not bool: raise ValueError('invalid_a0_route')
    if route['docker'] != native['docker']:raise ValueError('invalid_a0_route_docker')
    for key, name, original in [('stop_source', 'a0-route-stop.py', 'runtime'),
                                ('stop_launcher', 'a0-route-launcher.py', 'launcher')]:
        _pin(route[key])
        if (route[key]['path'] != str(Path(row['workspace_reference'])/name)
                or route[key]['sha256'] != native[original]['sha256']):
            raise ValueError('invalid_a0_route_stop_source')
    request = route['request']
    compact = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    request_keys = {'schema', 'owner', 'nonce', 'accepted_unix', 'deadline_unix',
                    'original_budget_seconds', 'accepted_monotonic_ns', 'launcher_sha256',
                    'policy_sha256', 'tools', 'endpoints', 'host'}
    if (not isinstance(request, dict) or set(request) != request_keys | ({'web'} if 'web' in native else set())
            or request['schema'] != 'friday.a0.local-route-request.v1'
            or request['owner'] != native['owner_slot'] + ':' + row['existing_task_id'] + '#1'
            or not isinstance(request['nonce'], str) or not re.fullmatch('[0-9a-f]{32}', request['nonce'])
            or request['accepted_unix'] != row['created_at_unix']
            or request['deadline_unix'] != row['deadline_unix']
            or request['original_budget_seconds'] != row['budget_seconds']
            or request['accepted_monotonic_ns'] != a['acceptance']['accepted_monotonic_ns']
            or request['launcher_sha256'] != native['launcher']['sha256']
            or request['host'] != {'association_sha256': compact(_identity(row)),
                                   'boot_id': a['acceptance']['boot_id'],
                                   'deployment_sha256': compact(native.get('deployment'))}
            or route['request_sha256'] != hashlib.sha256((json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()).hexdigest()
            or not isinstance(request['tools'],dict)
            or set(request['tools']) != {'dockerd', 'rootlesskit', 'slirp4netns', 'nft', 'nsenter'}
            or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in request['tools'].values())
            or not isinstance(request['policy_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',request['policy_sha256'])):
        raise ValueError('invalid_a0_route_request')
    limits = route['daemon_limits']
    if (not isinstance(limits,dict) or set(limits) != {'runtime_seconds', 'start_seconds', 'stop_seconds', 'admitted_remaining_seconds'}
            or any(type(v) not in (int,float) or not math.isfinite(v) or v <= 0 for v in limits.values())
            or limits['admitted_remaining_seconds'] > row['budget_seconds']-25
            or limits['runtime_seconds'] > 120 or limits['start_seconds'] > 45 or limits['stop_seconds'] > 20
            or sum(limits[k] for k in ('runtime_seconds','start_seconds','stop_seconds')) + 5 > limits['admitted_remaining_seconds']):
        raise ValueError('invalid_a0_route_deadline')
    daemon = route['daemon']
    group = '/user.slice/user-1000.slice/user@1000.service/app.slice/friday-rework-docker.service'
    if daemon is not None:
        if not route['daemon_attempted'] or not isinstance(daemon,dict) or set(daemon) != {'receipt'}:
            raise ValueError('invalid_a0_route_daemon')
        g = daemon['receipt'];context=g['context']
        if (g['request'] != request or g['schema'] != 'friday.a0.local-route-guard.v1'
                or g['status'] != 'GUARDED_BEFORE_DOCKERD'
                or g['policy_sha256'] != request['policy_sha256']
                or context['request_sha256'] != route['request_sha256']
                or not re.fullmatch('[0-9a-f]{32}',context['invocation_id'])
                or context['parent_pid'] != context['parent']['pid']):
            raise ValueError('invalid_a0_route_daemon')
        for process in (g['daemon'],context['parent']):
            if (set(process) != {'pid','start','ppid','cgroup','boot'}
                    or type(process['pid']) is not int or process['pid'] <= 0
                    or type(process['ppid']) is not int or process['ppid'] <= 0
                    or not isinstance(process['start'],str) or not process['start'].isdecimal()
                    or process['cgroup'] != '0::'+group+'/dockerd'
                    or process['boot'] != a['acceptance']['boot_id']):
                raise ValueError('invalid_a0_route_process')
        for field in ('namespaces',):
            ns=g[field]
            if (not isinstance(ns,dict) or set(ns) != {'user','mnt','net'}
                    or any(not isinstance(v,list) or len(v)!=2 or any(type(x)is not int or x<=0 for x in v) for v in ns.values())):
                raise ValueError('invalid_a0_route_namespace')
    samples = route['samples']
    if not isinstance(samples,list) or samples and daemon is None:raise ValueError('invalid_a0_route_samples')
    for sample in samples:
        if (not isinstance(sample,dict) or set(sample) != {'group','populated','processes'}
                or sample['group'] != group or type(sample['populated']) is not bool
                or not isinstance(sample['processes'],list)):
            raise ValueError('invalid_a0_route_sample')
        for p in sample['processes']:
            if (set(p) != {'pid','start_ticks','state'} or type(p['pid']) is not int or p['pid']<=0
                    or type(p['start_ticks']) is not int or p['start_ticks']<=0
                    or not isinstance(p['state'],str) or len(p['state'])!=1):
                raise ValueError('invalid_a0_route_sample')
    n=route['network']
    if n is not None:
        if (not route['network_attempted'] or daemon is None
                or n['owner'] != request['owner'] or n['nonce'] != request['nonce']
                or n['name'] != 'frw-a0-local-'+request['nonce'][:12]
                or n['bridge'] != 'br-frwa0local' or n['endpoints'] != request['endpoints']
                or n['request_sha256'] != route['request_sha256']
                or n['invocation_id'] != daemon['receipt']['context']['invocation_id']
                or n['namespaces'] != daemon['receipt']['namespaces']
                or not re.fullmatch('[0-9a-f]{64}',n['id'])):
            raise ValueError('invalid_a0_route_network')
        if (n['launcher_sha256'] != request['launcher_sha256']
                or n['policy_sha256'] != request['policy_sha256']
                or n['labels'] != {'friday.rework.owner':request['owner'],'friday.rework.route':request['nonce']}
                or n.get('web') != request.get('web')
                or not re.fullmatch('[0-9a-f]{64}',n['guard_receipt_sha256'])):
            raise ValueError('invalid_a0_route_network')
    settlement=route['settlement']
    if settlement is not None:
        if (not isinstance(settlement,dict) or set(settlement) != {'status','request_removed','guard_removed','network_removed','daemon_checks'}
                or settlement['status'] != 'STOP_CONFIRMED' or route['pending'] is not None
                or any(settlement[k] is not True for k in ('request_removed','guard_removed','network_removed'))
                or not isinstance(settlement['daemon_checks'],list)
                or route['daemon_attempted'] and (daemon is None or not samples or len(settlement['daemon_checks']) < len(samples)+1)
                or any(x.get('confirmed') is not True for x in settlement['daemon_checks'])):
            raise ValueError('invalid_a0_route_cessation')
        expected=[]
        if daemon is not None:
            g=daemon['receipt']
            expected=[*samples,{'group':group,'populated':True,'processes':[
                {'pid':p['pid'],'start_ticks':int(p['start']),'state':'S'}
                for p in (g['daemon'],g['context']['parent'])]}]
        if len(settlement['daemon_checks']) != len(expected):raise ValueError('invalid_a0_route_cessation')
        for check,before in zip(settlement['daemon_checks'],expected):
            if (set(check) != {'confirmed','before','survivors','after'} or check['before'] != before
                    or check['survivors'] != [] or check['after'] != {'group':group,'populated':False,'processes':[]}):
                raise ValueError('invalid_a0_route_cessation')


def validate_host_record(row):
    # Local import avoids the admission/store dependency cycle.
    from .admission import CALL_FIELDS, _snapshot
    from .controller import _inputs_digest
    from .adapters.contract import VerifiedInput
    from .host_runtime import validate_runtime
    try:
        host = row["host"]
        expected_host = {"binding", "inputs", "observation", "terminal", "quiescence"}
        if row['worker_kind'] == 'a0':
            expected_host.add('a0')
        if not isinstance(host, dict) or set(host) != expected_host:
            raise ValueError()
        binding = host["binding"]
        fields = {"correlation", "ingress", "brief", "runtime"}
        if not isinstance(binding, dict) or set(binding) not in (fields, fields | {"user_authority"}):
            raise ValueError()
        call = binding["correlation"]
        if not isinstance(call, dict) or set(call) != set(CALL_FIELDS):
            raise ValueError()
        for value in call.values():
            _text(value)
        if call["task_id"] != call["session_id"]:
            raise ValueError()
        ingress = _snapshot(binding["ingress"])
        if "user_authority" in binding:
            authority = binding["user_authority"]
            from hermes_cli.friday_product_access import principal_id
            if (not isinstance(authority, dict) or set(authority) != {"principal_id", "generation"}
                    or type(authority["generation"]) is not int or authority["generation"] < 1
                    or authority["principal_id"] != principal_id(ingress["platform"], ingress["transport_profile"],
                        ingress["message"]["bot_id"], ingress["message"]["user_id"])):
                raise ValueError()
        brief = parse_brief(binding["brief"])
        runtime = validate_runtime(binding["runtime"])
        if row['worker_kind'] == 'a0':
            if 'a0' not in runtime:
                raise ValueError()
            validate_a0_record(row)
        elif 'a0' in runtime:
            raise ValueError()
        address = association_address(call, ingress)
        if (row["existing_task_id"] != address or row["owner"] != owner_from_ingress(call, ingress)
                or row["admission_hash"] != hashlib.sha256(address.encode()).hexdigest()
                or row["brief_sha256"] != digest(vars(brief)) or row["worker_kind"] != brief.worker
                or row["workspace_reference"] != str(Path(runtime["workspace_root"]) / address)
                or row["supervisor"] != {"scope": "user", "unit": "friday-rework-worker-" + address[7:39] + ".service"}
                or runtime["runtime_profile"] != ingress["runtime_profile"]
                or row["budget_seconds"] != runtime["budget_seconds"]):
            raise ValueError()
        if host["inputs"] is not None:
            if not isinstance(host["inputs"], list):
                raise ValueError()
            inputs = tuple(VerifiedInput(**item) for item in host["inputs"])
            _inputs_digest(inputs)
            staging = Path(runtime["staging_root"]) / address
            from .adapters.a0 import input_path
            for index, item in enumerate(inputs):
                if (Path(item.host_path).parent != staging
                        or item.worker_path != (input_path(row, index) if row['worker_kind'] == 'a0'
                                               else "/job-input/verified/" + Path(item.host_path).name)
                        or item.receipt_reference != "association:" + address + "#ingress"):
                    raise ValueError()
        observation = host["observation"]
        if observation is not None:
            from .adapters.contract import NativeObservation
            value = NativeObservation(**observation)
            if value.state not in {"running", "completed", "failed", "stopped", "unknown"}:
                raise ValueError()
            _text(value.evidence_reference, 2048)
            _number(value.elapsed_seconds)
            if row["native"] and (value.invocation_id != row["native"]["invocation_id"]
                                  or value.worker_reference != row["native"]["worker_reference"]):
                raise ValueError()
        terminal = host["terminal"]
        if terminal is not None:
            if (not isinstance(terminal, dict) or set(terminal) != {"state", "evidence_reference", "at_unix"}
                    or terminal["state"] not in {"completed", "failed", "stopped"}):
                raise ValueError()
            _text(terminal["evidence_reference"], 2048)
            _number(terminal["at_unix"])
        quiet = host["quiescence"]
        if quiet is not None:
            if not isinstance(quiet, dict) or set(quiet) != {"kind", "at_unix", "observation"}:
                raise ValueError()
            _number(quiet["at_unix"])
            route = host.get('a0', {}).get('route')
            if route is not None and route['settlement'] is None:
                raise ValueError('a0_route_cessation_missing')
            if quiet["kind"] == "never_submitted":
                if (quiet["observation"] is not None or row["submission_observation"] != "NOT_SUBMITTED"
                        or row["stop_intent"] is None
                        or row['worker_kind'] == 'a0' and (host['a0']['launch'] is not None or route is not None)):
                    raise ValueError()
            elif quiet["kind"] == "native":
                if row['worker_kind'] == 'a0':
                    raise ValueError()
                observed = UnitObservation(**quiet["observation"])
                if (type(observed.missing) is not bool or type(observed.main_pid) is not int
                        or not observed.quiescent or observed.unit != row["supervisor"]["unit"]
                        or row["native"] and observed.invocation_id not in {"", row["native"]["invocation_id"]}):
                    raise ValueError()
            elif quiet['kind'] == 'a0':
                v = quiet['observation']; g = host['a0']['grant']
                if (row['worker_kind'] != 'a0' or g is None
                        or not isinstance(v, dict) or set(v) != {'unit', 'container_id', 'grant_sha256', 'native_cessation', 'key_cleanup'}
                        or v['container_id'] != g['container_id'] or v['grant_sha256'] != digest(g)
                        or v['native_cessation'] is not True
                        or v['key_cleanup'] != host['a0']['key_cleanup']
                        or v['key_cleanup'] not in {'REMOVED', 'RECONCILIATION_REQUIRED'}):
                    raise ValueError()
                observed = UnitObservation(**v['unit'])
                if (not observed.quiescent or observed.unit != row['supervisor']['unit']
                        or observed.invocation_id not in {'', g['invocation_id']}):
                    raise ValueError()
            elif quiet['kind'] == 'a0_no_create':
                v = quiet['observation']; a = host['a0']
                if (row['worker_kind'] != 'a0' or a['launch'] is None or a['grant'] is not None
                        or row['native'] is not None
                        or not isinstance(v,dict) or set(v) != {'unit','plan_sha256','create_attempted','pending','key_cleanup'}
                        or v['plan_sha256'] != a['launch']['plan']['identity']
                        or v['create_attempted'] is not False or v['pending'] is not False
                        or v['key_cleanup'] != a['key_cleanup']):
                    raise ValueError()
                observed = UnitObservation(**v['unit'])
                if not observed.missing or not observed.quiescent or observed.unit != row['supervisor']['unit']:
                    raise ValueError()
            elif quiet['kind'] == 'a0_pre_grant':
                a = host['a0'];v=quiet['observation'];c=(a['launch'] or {}).get('created')
                if (row['worker_kind'] != 'a0' or a['grant'] is not None or c is None
                        or row['native'] is not None or not isinstance(v,dict)
                        or set(v) != {'unit','container_id','plan_sha256','native_cessation','key_cleanup'}
                        or v['container_id'] != c['container_id'] or v['plan_sha256'] != c['plan_sha256']
                        or v['native_cessation'] is not True or v['key_cleanup'] != a['key_cleanup']):
                    raise ValueError()
                observed=UnitObservation(**v['unit'])
                if not observed.quiescent or observed.unit != row['supervisor']['unit']:
                    raise ValueError()
            elif quiet['kind'] == 'a0_route':
                if (row['worker_kind'] != 'a0' or route is None or host['a0']['launch'] is not None
                        or row['native'] is not None or quiet['observation'] != {'route_sha256': digest(route)}):
                    raise ValueError()
            else:
                raise ValueError()
        if terminal is not None:
            if quiet is None or observation is None or observation["state"] != terminal["state"]:
                raise ValueError()
            if terminal["state"] == "completed" and (row["native"] is None or quiet["kind"] not in {"native", 'a0'}):
                raise ValueError()
    except Exception as exc:
        raise AssociationError("invalid_host_association") from exc


def quiescence_record(observed, clock):
    if not isinstance(observed, UnitObservation) or not observed.quiescent:
        raise AssociationError("STOP_UNCONFIRMED")
    return {"kind": "native", "at_unix": clock(), "observation": asdict(observed)}
