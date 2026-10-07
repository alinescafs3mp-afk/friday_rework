"""Explicit operator configuration -> exact accepted DSH adapter.

No deployment defaults, environment routing, dynamic imports or model grants.
An operator's pinned readiness receipt binds this config to actual reviewed
runtime evidence. This code cannot manufacture that evidence or enable A0.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .adapters.dsh import DshAdapter, DshHostConfig, PinnedFile
from .controller import WorkerBinding
from .supervision import NativeSupervisor


class HostUnavailable(RuntimeError):
    pass


def _path(value):
    if (not isinstance(value, str) or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value)
            or str(Path(value)) != value or ".." in Path(value).parts or value == "/"):
        raise HostUnavailable("invalid_runtime_path")
    return value


def _pin(value):
    if (not isinstance(value, dict) or set(value) != {"path", "sha256"}
            or not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise HostUnavailable("invalid_runtime_pin")
    return PinnedFile(Path(_path(value["path"])), value["sha256"])


def validate_runtime(value):
    if isinstance(value, dict) and "a0" in value:
        return validate_a0_runtime(value)
    required = {"enabled", "runtime_profile", "runtime_home", "workspace_root", "staging_root", "cache_roots",
                "budget_seconds", "max_file_bytes", "max_total_bytes", "dsh", "runtime_receipt"}
    if (not isinstance(value, dict) or set(value) != required or value["enabled"] is not True
            or not isinstance(value["runtime_profile"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value["runtime_profile"])):
        raise HostUnavailable("worker_not_configured")
    for key in ("runtime_home", "workspace_root", "staging_root"):
        _path(value[key])
    if not isinstance(value["cache_roots"], list) or not value["cache_roots"]:
        raise HostUnavailable("missing_cache_roots")
    for root in value["cache_roots"]:
        _path(root)
    for key, ceiling in (("budget_seconds", 86400), ("max_file_bytes", 16*1024**2),
                         ("max_total_bytes", 64*16*1024**2)):
        if type(value[key]) is not int or not 0 < value[key] <= ceiling:
            raise HostUnavailable("invalid_runtime_limits")
    dsh = value["dsh"]
    required_dsh = {"payload_root", "toolchain_root", "node", "cli", "patch", "native_files", "key_name",
                    "profile", "memory_bytes", "cpu_percent", "tasks", "shutdown_seconds", "tmp_bytes"}
    if not isinstance(dsh, dict) or set(dsh) != required_dsh or dsh["profile"] != "headless":
        raise HostUnavailable("invalid_dsh_config")
    for key in ("payload_root", "toolchain_root"):
        _path(dsh[key])
    for key in ("node", "cli", "patch"):
        _pin(dsh[key])
    if not isinstance(dsh["native_files"], list) or not dsh["native_files"]:
        raise HostUnavailable("missing_native_pins")
    for pin in dsh["native_files"]:
        _pin(pin)
    for key, maximum in (("memory_bytes", 2*1024**3), ("cpu_percent", 400), ("tasks", 64),
                         ("shutdown_seconds", 2), ("tmp_bytes", 64*1024**2)):
        if type(dsh[key]) is not int or not 0 < dsh[key] <= maximum:
            raise HostUnavailable("invalid_resource_grant")
    if not isinstance(dsh["key_name"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", dsh["key_name"]):
        raise HostUnavailable("invalid_key_reference")
    _pin(value["runtime_receipt"])
    return copy.deepcopy(value)


def private_directory(path):
    path = Path(path)
    info = path.stat()
    if (not path.is_absolute() or path.resolve() != path or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise HostUnavailable("nonprivate_runtime_root")
    return path


def check_runtime(value, associations):
    if isinstance(value, dict) and "a0" in value:
        return check_a0_runtime(value, associations)
    from .host_record import digest
    from hermes_constants import get_hermes_home
    config = validate_runtime(value)
    if Path(config["runtime_home"]) != get_hermes_home():
        raise HostUnavailable("foreign_runtime_home")
    workspace = private_directory(config["workspace_root"])
    staging = private_directory(config["staging_root"])
    # No worker writable mount contains the store or staged originals.
    protected = [staging, Path(associations.state.data_dir),
                 Path(config["dsh"]["payload_root"]), Path(config["dsh"]["toolchain_root"])]
    if any(p.is_relative_to(workspace) or workspace.is_relative_to(p) for p in protected):
        raise HostUnavailable("overlapping_runtime_roots")
    for root in config["cache_roots"]:
        p = Path(root)
        if not p.is_dir() or p.resolve() != p:
            raise HostUnavailable("unsafe_cache_root")
    dsh = config["dsh"]
    for pin in (dsh["node"], dsh["cli"], dsh["patch"], *dsh["native_files"]):
        _pin(pin).read()
    receipt = json.loads(_pin(config["runtime_receipt"]).read())
    adapter_hash = hashlib.sha256(Path(__file__).with_name("adapters").joinpath("dsh.py").read_bytes()).hexdigest()
    if (not isinstance(receipt, dict) or set(receipt) != {"schema", "ready", "runtime_sha256", "adapter_sha256", "evidence"}
            or receipt["schema"] != "friday-rework.dsh-runtime.v1" or receipt["ready"] is not True
            or receipt["adapter_sha256"] != adapter_hash
            or receipt["runtime_sha256"] != digest({k: v for k, v in config.items() if k != "runtime_receipt"})
            or not isinstance(receipt["evidence"], list) or not receipt["evidence"]):
        raise HostUnavailable("runtime_not_verified")
    for pin in receipt["evidence"]:
        _pin(pin).read()
    return config


def dsh_binding(value, associations):
    """Concrete config factory; recovery preserves retained config and budgets.

    Stop does not re-read readiness or launch pins. DSH's own stop and emergency
    native supervisor remain authoritative when those launch files drift.
    """
    config = validate_runtime(value)
    dsh = config["dsh"]
    def environment():
        from agent.secret_scope import current_secret_scope, current_secret_scope_home
        from gateway.platforms._shared import get_scoped_secret
        from hermes_constants import get_hermes_home
        scope = current_secret_scope()
        if (scope is None or current_secret_scope_home() != config["runtime_home"]
                or get_hermes_home() != Path(config["runtime_home"]) or dsh["key_name"] not in scope):
            raise HostUnavailable("runtime_key_unavailable")
        value = get_scoped_secret(dsh["key_name"])
        if (not isinstance(value, str) or not value or "\x00" in value
                or value != scope[dsh["key_name"]]):
            raise HostUnavailable("runtime_key_unavailable")
        return {dsh["key_name"]: value}
    supervisor = NativeSupervisor()
    native = DshHostConfig(
        workspace_root=Path(config["workspace_root"]), payload_root=Path(dsh["payload_root"]),
        toolchain_root=Path(dsh["toolchain_root"]), node=_pin(dsh["node"]), cli=_pin(dsh["cli"]),
        patch=_pin(dsh["patch"]), native_files=tuple(_pin(p) for p in dsh["native_files"]),
        environment=environment, key_name=dsh["key_name"],
        current_association=lambda row: associations.get(row["existing_task_id"], row["owner"]),
        **{k: dsh[k] for k in ("profile", "memory_bytes", "cpu_percent", "tasks", "shutdown_seconds", "tmp_bytes")})
    return WorkerBinding(DshAdapter(native, supervisor=supervisor, clock=associations.clock), supervisor.stop)


def validate_a0_runtime(value):
    common = {'enabled','runtime_profile','runtime_home','workspace_root','staging_root','cache_roots',
              'budget_seconds','max_file_bytes','max_total_bytes','a0','runtime_receipt'}
    if (not isinstance(value, dict) or set(value) != common or value['enabled'] is not True
            or not re.fullmatch('[A-Za-z0-9_-]{1,64}', value['runtime_profile'])):
        raise HostUnavailable('a0_not_configured')
    for k in ('runtime_home','workspace_root','staging_root'): _path(value[k])
    if not isinstance(value['cache_roots'], list) or not value['cache_roots']:
        raise HostUnavailable('missing_cache_roots')
    for p in value['cache_roots']: _path(p)
    for k, low, high in (('budget_seconds',30,1800),('max_file_bytes',1,16*1024**2),
                         ('max_total_bytes',1,16*1024**2)):
        if type(value[k]) is not int or not low <= value[k] <= high:
            raise HostUnavailable('invalid_a0_bounds')
    a = value['a0']
    if (not isinstance(a,dict) or set(a) != {'runtime','launcher','docker','daemon_unit','git_metadata','expected_files','capability','policy','owner_slot'}):
        raise HostUnavailable('invalid_a0_config')
    if a['owner_slot'] not in {'astra','sol'}:raise HostUnavailable('invalid_a0_operator_slot')
    for k in ('runtime','launcher','docker','daemon_unit','policy'): _pin(a[k])
    _pin(value['runtime_receipt'])
    # Fresh capability is attached to the reserved row, never static config.
    if a['capability'] is not None: raise HostUnavailable('obsolete_preclaim_a0_capability')
    files = a['expected_files']
    if (not isinstance(files,list) or not 0 < len(files) <= 16
            or any(not isinstance(x,dict) or set(x) != {'logical_name','media_type'}
                   or not isinstance(x['logical_name'],str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',x['logical_name'])
                   or not isinstance(x['media_type'],str) or not re.fullmatch('[A-Za-z0-9.+_-]+/[A-Za-z0-9.+_-]+',x['media_type']) for x in files)
            or len({x['logical_name'] for x in files}) != len(files)):
        raise HostUnavailable('invalid_a0_expected_files')
    g = a['git_metadata']
    if not isinstance(g,dict) or set(g) != {'source','manifest_sha256'}:
        raise HostUnavailable('invalid_a0_git_metadata')
    _path(g['source'])
    return copy.deepcopy(value)


def check_a0_runtime(value, associations):
    from .host_record import digest
    from .adapters.a0_native import strict_json
    from hermes_constants import get_hermes_home
    c = validate_a0_runtime(value)
    if get_hermes_home() != Path(c['runtime_home']): raise HostUnavailable('foreign_runtime_home')
    workspace, staging = private_directory(c['workspace_root']), private_directory(c['staging_root'])
    protected = [staging,Path(associations.state.data_dir),Path(c['a0']['git_metadata']['source'])]
    if any(p.is_relative_to(workspace) or workspace.is_relative_to(p) for p in protected):
        raise HostUnavailable('overlapping_runtime_roots')
    for root in c['cache_roots']:
        if Path(root).resolve() != Path(root) or not Path(root).is_dir(): raise HostUnavailable('unsafe_cache_root')
    for k in ('runtime','launcher','docker','daemon_unit','policy'): _pin(c['a0'][k]).read()
    receipt = strict_json(_pin(c['runtime_receipt']).read())
    source = Path(__file__).parent
    actual = {k: hashlib.sha256((source/p).read_bytes()).hexdigest() for k,p in {
        'host':'host.py','host_runtime':'host_runtime.py','host_record':'host_record.py',
        'associations':'associations.py','adapter':'adapters/a0.py','native':'adapters/a0_native.py',
        'config':'adapters/a0_config.py'}.items()}
    if (not isinstance(receipt,dict) or set(receipt) != {'schema','ready','runtime_sha256','source_pins','evidence'}
            or receipt['schema'] != 'friday-rework.a0-runtime.v2' or receipt['ready'] is not True
            or receipt['runtime_sha256'] != digest({k:v for k,v in c.items() if k != 'runtime_receipt'})
            or receipt['source_pins'] != actual or not isinstance(receipt['evidence'],list) or not receipt['evidence']):
        raise HostUnavailable('a0_readiness_not_verified')
    for p in receipt['evidence']: _pin(p).read()
    # Reusable reviewed deployment evidence; this grants no per-job effects.
    # The producer attaches the exact freshly reserved row below.
    return c


def a0_binding(value, associations, row):
    from .controller import WorkerBinding
    session = A0HostSession(validate_a0_runtime(value), associations, row)
    return WorkerBinding(session, session.emergency_stop)


class A0HostSession:
    """One association's cached ownership, original KeyMaterial and boundary.

    Construction/recovery are pure. Only Controller.prepare calls launch.
    A restarted session has stop-only authority and never recovers secrets.
    """
    def __init__(self, config, store, row):
        from .adapters.dsh import _identity
        from .associations import _validate_store
        _validate_store({'schema_version':1,'jobs':{row['existing_task_id']:row}})
        if config != row['host']['binding']['runtime']:
            raise HostUnavailable('foreign_a0_runtime_binding')
        self.config, self.store, self.identity = config, store, copy.deepcopy(_identity(row))
        self.state_home = Path(store.state.data_dir)
        self.runtime = self.adapter = self.boundary = self.keys = None
        self.cancelled = False
        self.launching = False
        self.unit = None
        self.startup_active = False
        self.native_cessation = False
        self.no_create_confirmed = False
        self.pre_grant_confirmed = False
        self.created = copy.deepcopy((row['host']['a0']['launch'] or {}).get('created'))
        observations = row['host']['a0'].get('observations')
        # Legacy/missing observation evidence is unknown, not proof of no
        # descendants. Construction remains pure and never restores secrets.
        self.observation_pending = (observations is None or observations['pending']
                                    or (row['host']['a0']['grant'] is not None and not observations['samples']))
        self.retained_samples = copy.deepcopy([] if observations is None else observations['samples'])
        self.key_preparation_attempted = False
        self.key_cleanup = row['host']['a0']['key_cleanup']
        self.preparing = False
        self.plan = copy.deepcopy((row['host']['a0']['launch'] or {}).get('plan'))
        self.grant = copy.deepcopy(row['host']['a0']['grant'])

    def _same(self, row):
        from .adapters.dsh import _identity
        from hermes_constants import get_hermes_home
        if (_identity(row) != self.identity or Path(self.store.state.data_dir) != self.state_home
                or get_hermes_home() != Path(self.config['runtime_home'])):
            raise HostUnavailable('foreign_a0_binding')

    def _current(self, row):
        self._same(row)
        return self._eligible(self.store.get(row['existing_task_id'],row['owner']))

    def _eligible(self, r):
        # The locked producer seam supplies the actual durable row directly;
        # it must not recursively acquire the existing admission flock.
        self._same(r)
        a = r['host']['a0']['acceptance']
        import time
        if (self.cancelled or r['stop_intent'] or self.store.clock() < a['accepted_unix']
                or self.store.clock() >= r['deadline_unix']
                or a['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                or not 0 <= (time.monotonic_ns()-a['accepted_monotonic_ns'])/1e9 < r['budget_seconds']):
            raise HostUnavailable('a0_stopped_or_original_budget_expired')
        return r

    def _module(self):
        import types
        pin = _pin(self.config['a0']['runtime']); data = pin.read()
        m = types.ModuleType('frw_pinned_a0_runtime');m.__file__=str(pin.path)
        exec(compile(data,str(pin.path),'exec'),m.__dict__)
        return m

    def _capability(self, row, pin=None):
        from .adapters.a0_native import strict_json
        from .adapters.dsh import _identity
        from .host_record import digest
        pin = row['host']['a0']['capability'] if pin is None else pin
        if pin is None: raise HostUnavailable('current_a0_capability_missing')
        v = strict_json(_pin(pin).read())
        if (not isinstance(v,dict) or set(v) != {'schema','association','acceptance','network','live_evidence'}
                or v['schema'] != 'friday.a0.host-capability.v2' or v['association'] != _identity(row)
                or v['acceptance'] != row['host']['a0']['acceptance']
                or not isinstance(v['live_evidence'],list) or not v['live_evidence']
                or v['network']['launcher_sha256'] != self.config['a0']['launcher']['sha256']):
            raise HostUnavailable('foreign_or_stale_a0_capability')
        checks = {'namespace_recheck','current_route'}
        for p in v['live_evidence']:
            proof = strict_json(_pin(p).read())
            if (not isinstance(proof,dict) or set(proof) != {'schema','accepted','association_sha256',
                    'acceptance_sha256','network_sha256','runtime_source_sha256','checks'}
                    or proof['schema'] != 'friday.a0.host-current-route.v2' or proof['accepted'] is not True
                    or proof['association_sha256'] != digest(_identity(row))
                    or proof['acceptance_sha256'] != digest(row['host']['a0']['acceptance'])
                    or proof['network_sha256'] != digest(v['network'])
                    or proof['runtime_source_sha256'] != self.config['a0']['runtime']['sha256']
                    or not isinstance(proof['checks'],dict) or set(proof['checks']) != checks
                    or any(x is not True for x in proof['checks'].values())):
                raise HostUnavailable('current_live_a0_readiness_missing')
        return v

    def validate_capability(self, row, pin):
        """Trusted host producer seam; no user/model handler or launch authority."""
        self._eligible(row)
        check_a0_runtime(self.config, self.store)
        return self._capability(row, pin)

    def _startup_left(self, row):
        import time
        current = self._current(row)
        a = current['host']['a0']['acceptance']
        left = min(current['deadline_unix'] - self.store.clock(),
                   current['budget_seconds'] - (time.monotonic_ns()-a['accepted_monotonic_ns'])/1e9) - 25
        if left <= 1: raise HostUnavailable('a0_startup_original_budget_exhausted')
        return left

    def _begin_sample(self, row):
        if self.observation_pending:
            raise HostUnavailable('STOP_UNCONFIRMED; prior observation incomplete')
        self.observation_pending = True
        self.store.a0_observation(row['existing_task_id'], row['owner'])

    def _finish_sample(self, row, sample):
        # Keep the new identity in memory even if the durable write fails.
        self.retained_samples.append(copy.deepcopy(sample))
        self.store.a0_observation(row['existing_task_id'], row['owner'], sample)
        self.observation_pending = False

    def _retain_sample(self, m, r, sample):
        # Cache both owners before receipt I/O or any other fallible observation.
        r['observations'].append(copy.deepcopy(sample))
        self.runtime.known = r
        m.write_json(self.runtime.receipt_path, r, replace=True)

    def _boundary(self, row, *, stop_only=False):
        from .adapters.a0_native import A0NativeBoundary, NativeGrant
        session = self

        class RetainingBoundary(A0NativeBoundary):
            def admit(boundary, current):
                if boundary.stop_only:
                    return super().admit(current)
                session._current(current); session._capability(current)
                session.runtime.check_network(container_id=boundary.grant.container_id)
                return super().admit(current)

            def _sample(boundary, obj, *, caps):
                session._begin_sample(row)
                super()._sample(obj, caps=caps)
                root, processes = boundary.samples[-1]
                session._finish_sample(row, {
                    'group': '/' + str(root.relative_to('/sys/fs/cgroup')),
                    'populated': True,
                    'processes': [{'pid': pid, 'start_ticks': start} for pid, start in processes],
                })

        boundary = RetainingBoundary(self._deployment(self.plan), NativeGrant(**self.grant),
                                     clock=self.store.clock, stop_only=stop_only)
        boundary.samples.extend((Path('/sys/fs/cgroup') / s['group'].lstrip('/'),
                                 [(v['pid'], v['start_ticks']) for v in s['processes']])
                                for s in self.retained_samples)
        return boundary

    def _container_ready(self, m, row, r):
        import time
        # Finite native startup observations, never replaying create/start/POST.
        for _ in range(row['budget_seconds']*10+1):
            left = self._startup_left(row)
            self.keys.ready(); self._capability(self._current(row))
            obj = self.runtime.inspect(r, timeout=min(3, left))
            if obj['State']['Running'] and obj['State']['Pid'] > 0:
                sample = self.runtime.snapshot_container(obj)
                self._retain_sample(m, r, sample)
                return sample
            unit = self.runtime.supervisor.observe(self.runtime.association(r))
            if unit.quiescent or unit.invocation_id != r['invocation_id']:
                raise HostUnavailable('a0_startup_unit_lost')
            time.sleep(min(.1, self._startup_left(row)))
        raise HostUnavailable('a0_startup_observation_limit')

    def _api_ready(self, row):
        import time
        for _ in range(row['budget_seconds']*10+1):
            left = self._startup_left(row)
            # GuardedBoundary repeats current route, exact identity and keys.
            if self.boundary.readiness(self._current(row), min(3, left)):
                self._startup_left(row)
                return
            time.sleep(min(.1, self._startup_left(row)))
        raise HostUnavailable('a0_startup_observation_limit')

    def _deployment(self, plan):
        from .adapters.a0_config import A0Deployment, LocalNetwork
        # Exact reviewed startup and image are in the already checked bound plan.
        from .adapters.a0_native import NativeGrant
        a = self.config['a0'];n=plan['network']
        if not isinstance(n,dict): raise HostUnavailable('missing_a0_local_route')
        policy = _pin(a['policy'])
        return A0Deployment(_pin(a['docker']),_pin(a['daemon_unit']),
            'unix:///run/user/1000/friday-rework-docker/docker.sock',plan['image'],
            Path(plan['state_dir']),Path(plan['git_metadata']['source']),
            ('-ceu', 'umask 077; . /ins/setup_venv.sh; . /ins/copy_A0.sh; mkdir -p /a0/usr/uploads; cd /a0; exec python run_ui.py --dockerized=true --host=127.0.0.1 --port=5000'),
            LocalNetwork(n['id'],('http://192.168.1.78:8001/v1','http://192.168.1.78:8002/v1'),policy))

    def _launch(self, row):
        from dataclasses import asdict
        from .adapters.dsh import _identity
        from .adapters.a0_config import prepare_keys
        from .adapters.a0_native import A0NativeBoundary, NativeGrant
        from .adapters.a0 import A0Adapter, A0HostConfig, ExpectedFile, job_prefix
        from agent.secret_scope import current_secret_scope, current_secret_scope_home
        from gateway.platforms._shared import get_scoped_secret
        self._current(row)
        if row['host']['a0']['launch'] is not None or self.launching:
            raise HostUnavailable('a0_launch_requires_reconciliation')
        m = self._module();cap=self._capability(row);a=row['host']['a0']['acceptance']
        p=m.plan(row['created_at_unix'],row['deadline_unix'],assignment=row['existing_task_id'],generation=1,
            owner_slot=self.config['a0']['owner_slot'],original_budget_seconds=row['budget_seconds'],git_metadata=self.config['a0']['git_metadata'],
            network=cap['network'],association_binding=_identity(row),accepted_monotonic_ns=a['accepted_monotonic_ns'],boot_id=a['boot_id'])
        if (str(m.DOCKER) != self.config['a0']['docker']['path']
                or p['docker_sha256'] != self.config['a0']['docker']['sha256']
                or str(m.PROJECT/'.runtime/rootless-docker/supervisor/friday-rework-docker.service') != self.config['a0']['daemon_unit']['path']
                or p['daemon_unit_sha256'] != self.config['a0']['daemon_unit']['sha256']
                or str(m.LAUNCHER) != self.config['a0']['launcher']['path']):
            raise HostUnavailable('a0_runtime_native_pin_mismatch')
        self.plan=p
        plan_path=Path(row['workspace_reference'])/'a0-plan.json';m.write_json(plan_path,p)
        self.runtime=m.Runtime(p)
        native_snapshot = self.runtime.snapshot_container
        def retained_snapshot(obj):
            # Also covers pre-grant cleanup observations made by Runtime.
            self._begin_sample(row)
            sample = native_snapshot(obj)
            self._finish_sample(row, sample)
            return sample
        self.runtime.snapshot_container = retained_snapshot
        original_runner=self.runtime.runner
        def startup_runner(argv,timeout):
            if self.startup_active: timeout=min(timeout,self._startup_left(row))
            return original_runner(argv,timeout)
        self.runtime.runner=startup_runner
        self.store.retain_a0(row['existing_task_id'],row['owner'],'launch',
            {'plan':p,'plan_pin':{'path':str(plan_path),'sha256':m.sha(plan_path)},'keys_prepared_monotonic':None,'created':None})
        self.launching=True
        self.startup_active=True
        def before_ui(usr):
            self._current(row)
            scope=current_secret_scope();names={'FRIDAY_LLM_API_KEY','FRIDAY_EMBEDDINGS_API_KEY'}
            if scope is None or current_secret_scope_home() != self.config['runtime_home'] or not names.issubset(scope):
                raise HostUnavailable('a0_scoped_keys_unavailable')
            def resolve(name):
                value=get_scoped_secret(name)
                if value != scope[name]:raise HostUnavailable('a0_scoped_keys_changed')
                return value
            self.key_preparation_attempted=True
            self.keys=prepare_keys(usr,resolve)
            self.key_cleanup='PREPARED'
            self.store.retain_a0(row['existing_task_id'],row['owner'],'keys_prepared_monotonic',self.keys.prepared_monotonic)
            self.store.retain_a0(row['existing_task_id'],row['owner'],'key_cleanup','PREPARED')
            self.keys.ready();self._current(row)
        def on_created(known):
            # Creation already happened: cancellation/expiry cannot withhold
            # checked exact-ID caching and stop-only ownership reconciliation.
            self.startup_active=False
            self.runtime.inspect(known,stop_owned=True,timeout=3)
            self.created={'container_id':known['container_id'],'plan_sha256':m.digest(p)}
            self.store.retain_a0(row['existing_task_id'],row['owner'],'created',self.created)
            self._current(row)
            self.startup_active=True
        try:
            self.runtime.start(plan_path,m.sha(plan_path),before_ui=before_ui,on_created=on_created)
            self._current(row)
            r=self.runtime.receipt();sample=self._container_ready(m,row,r)
            # Dedicated daemon invocation is an actual independent observation.
            reply=self.runtime.runner(['/usr/bin/systemctl','--user','show',m.DAEMON,'--property=ActiveState,InvocationID'],3)
            fields=dict(x.split('=',1) for x in reply.splitlines())
            if set(fields) != {'ActiveState','InvocationID'} or fields['ActiveState'] != 'active':raise HostUnavailable('daemon_identity_unknown')
            self.runtime.check_network(container_id=r['container_id'])
            g=NativeGrant(r['container_id'],p['container_name'],r['invocation_id'],m.labels(p),row['created_at_unix'],row['deadline_unix'],
                sample['group'],a['boot_id'],True,self.keys.prepared_monotonic,fields['InvocationID'],a['accepted_monotonic_ns']/1e9)
            self.grant=asdict(g)
            self.boundary=self._boundary(row)
            native_runner=self.boundary.runner
            def bounded_api_runner(argv,data,timeout):
                if self.startup_active: timeout=min(timeout,self._startup_left(row))
                return native_runner(argv,data,timeout)
            self.boundary.runner=bounded_api_runner
            unit_command=getattr(self.boundary.supervisor,'_command',None)
            if callable(unit_command):
                def bounded_unit_command(arguments,timeout):
                    if self.startup_active: timeout=min(timeout,self._startup_left(row))
                    return unit_command(arguments,timeout)
                self.boundary.supervisor._command=bounded_unit_command
            self.store.retain_a0(row['existing_task_id'],row['owner'],'grant',self.grant)
            def expected(current):
                return tuple(ExpectedFile('/a0/usr/workdir/'+job_prefix(current)+'/'+job_prefix(current)+'-'+x['logical_name'],**x)
                             for x in current['host']['a0']['expected_files'])
            staging=Path(self.config['staging_root'])/row['existing_task_id'];outputs=staging/'a0-outputs'
            outputs.mkdir(mode=0o700)
            self.adapter=A0Adapter(A0HostConfig(Path(self.config['workspace_root']),staging,outputs,
                lambda current:self.store.get(current['existing_task_id'],current['owner']),expected,self.keys,
                max_file_bytes=min(self.config['max_file_bytes'],self.config['max_total_bytes'])),self.boundary,clock=self.store.clock)
            self._api_ready(row)
        except BaseException as error:
            try:self.emergency_stop(row)
            except BaseException:error.add_note('owned execution STOP_UNCONFIRMED')
            raise
        finally:
            self.startup_active=False
            self.launching=False

    def prepare(self,row,brief,inputs):
        self.preparing=True
        try:
            self._launch(row)
            return self.adapter.prepare(row,brief,inputs)
        finally:self.preparing=False

    def submit(self,*args):
        if self.adapter is None:raise HostUnavailable('a0_restart_stop_only')
        return self.adapter.submit(*args)

    def observe(self,row,prepared):
        self._same(row)
        if self.adapter is not None:return self.adapter.observe(row,prepared)
        self.emergency_stop(row)
        from .adapters.contract import NativeObservation
        n=row['native'] or {'invocation_id':'','worker_reference':''}
        if (Path(row['workspace_reference'])/'a0-result.json').exists():
            from .adapters.a0 import read_retained_result, ExpectedFile, job_prefix
            from .adapters.a0_native import NativeGrant
            expected=tuple(ExpectedFile('/a0/usr/workdir/'+job_prefix(row)+'/'+job_prefix(row)+'-'+x['logical_name'],**x)
                           for x in row['host']['a0']['expected_files'])
            read_retained_result(row,prepared,NativeGrant(**self.grant),expected,
                Path(self.config['staging_root'])/row['existing_task_id']/'a0-outputs',min(self.config['max_file_bytes'],self.config['max_total_bytes']))
            return NativeObservation(n['invocation_id'],n['worker_reference'],
                str(Path(row['workspace_reference'])/'a0-result.json'),row['elapsed_seconds'],'completed')
        return NativeObservation(n['invocation_id'],n['worker_reference'],'association:'+row['existing_task_id']+'#recovered-stop',row['elapsed_seconds'],'unknown')

    def stop(self,row,prepared,intent):
        self.emergency_stop(row)
        from .adapters.contract import NativeObservation
        n=row['native'] or {'invocation_id':'','worker_reference':''}
        return NativeObservation(n['invocation_id'],n['worker_reference'],'association:'+row['existing_task_id']+'#stop',row['elapsed_seconds'],'stopped')

    def emergency_stop(self,row):
        self._same(row);self.cancelled=True
        self.startup_active=False # Owned stop is never withheld by an expired launch budget.
        from .adapters.a0_native import A0NativeBoundary, NativeGrant
        if self.boundary is None:
            if self.grant is not None:
                self.boundary=self._boundary(row,stop_only=True)
            elif self.runtime is not None and self.runtime.known is not None:
                stopped=self.runtime.stop()
                unit=self.runtime.supervisor.observe(self.runtime.association(self.runtime.known))
                if (self.launching or self.preparing or self.created is None or not unit.quiescent
                        or self.observation_pending
                        or stopped.get('status') != 'STOP_CONFIRMED'
                        or stopped.get('container_id') != self.created['container_id']
                        or stopped.get('current_sampling') == 'UNKNOWN'
                        or len(stopped.get('descendant_checks',[])) < len(self.retained_samples)
                        or any(x.get('confirmed') is not True for x in stopped.get('descendant_checks',[]))):
                    raise HostUnavailable('STOP_UNCONFIRMED; pending or incomplete pre-grant cessation')
                self.unit=unit;self.pre_grant_confirmed=True;self.native_cessation=True
            elif (self.runtime is not None and not self.runtime.create_attempted
                    and not self.launching and not self.preparing):
                unit=self.runtime.supervisor.observe(self.runtime.association({}))
                if not unit.missing or not unit.quiescent:
                    raise HostUnavailable('STOP_UNCONFIRMED; unexpected native unit')
                self.unit=unit;self.no_create_confirmed=True;self.native_cessation=True
            else:raise HostUnavailable('STOP_UNCONFIRMED; pending or unknown create')
        if self.boundary is not None:
            unit=self.boundary.stop(row);self.unit=unit
            if self.observation_pending or not self.retained_samples:
                raise HostUnavailable('STOP_UNCONFIRMED; retained observations incomplete')
            self.native_cessation=True
        if self.keys is None:
            if self.key_cleanup != 'REMOVED' and (not self.no_create_confirmed or self.key_preparation_attempted):
                self.key_cleanup='RECONCILIATION_REQUIRED'
        else:
            try:self.keys.remove(cessation_confirmed=True);self.key_cleanup='REMOVED'
            except BaseException:self.key_cleanup='RECONCILIATION_REQUIRED'
        try:self.store.retain_a0(row['existing_task_id'],row['owner'],'key_cleanup',self.key_cleanup)
        except BaseException:pass # Native cessation truth is independent of damaged metadata.
        return unit

    def quiescence(self,row):
        from dataclasses import asdict
        from .host_record import digest
        if not self.native_cessation or self.unit is None:return None
        if self.no_create_confirmed:
            return {'kind':'a0_no_create','at_unix':self.store.clock(),'observation':{
                'unit':asdict(self.unit),'plan_sha256':self.runtime.p['identity'],
                'create_attempted':False,'pending':False,'key_cleanup':self.key_cleanup}}
        if self.pre_grant_confirmed:
            return {'kind':'a0_pre_grant','at_unix':self.store.clock(),'observation':{
                'unit':asdict(self.unit),**self.created,'native_cessation':True,'key_cleanup':self.key_cleanup}}
        if self.grant is None:return None
        return {'kind':'a0','at_unix':self.store.clock(),'observation':{'unit':asdict(self.unit),
            'container_id':self.grant['container_id'],'grant_sha256':digest(self.grant),
            'native_cessation':True,'key_cleanup':self.key_cleanup}}
