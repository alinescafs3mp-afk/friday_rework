#!/usr/bin/python3
"""Isolated actual function execution; collaborators are finite explicit fixtures.

No product imports, service manager, network, credentials, process discovery,
model, git, DB, installed-source writes or live runtime acceptance occur.
"""
import ast
import contextlib
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import resource
import shlex
import stat
import sys
import time
import types
import unittest

# Portable input/output paths only; original test bodies and fixtures are retained.
import argparse
_path_parser = argparse.ArgumentParser(description=__doc__)
_path_parser.add_argument('--inputs', type=Path, required=True)
_path_parser.add_argument('--output-dir', type=Path, required=True)
_path_options = _path_parser.parse_args()
_input_manifest = _path_options.inputs.resolve()
BASE = _path_options.output_dir.resolve()
BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
MANIFEST = json.loads(_input_manifest.read_text())
for _row in MANIFEST:
    for _key in ('baseline', 'candidate'):
        _row[_key] = str((_input_manifest.parent / _row[_key]).resolve())
ROW = {r['relative']:r for r in MANIFEST}
GW = Path(ROW['hermes_cli/gateway.py']['candidate'])
START = Path(ROW['scripts/friday_start.py']['candidate'])
ADMISSION = Path(ROW['hermes_cli/friday_credential_admission.py']['candidate'])
CONTAIN = Path(ROW['plugins/friday_rework/runtime_containment.py']['candidate'])
ENV_NAME = 'HERMES_FRIDAY_STARTUP_TEST_SECONDS'
CPU_SET = sorted(os.sched_getaffinity(0))[:2]
os.sched_setaffinity(0, CPU_SET)
resource.setrlimit(resource.RLIMIT_AS, (1024**3,1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (240,240))
resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
FIX = BASE/'fixtures'; FIX.mkdir(mode=0o700,exist_ok=True)


def defs(path, names, namespace=None):
    namespace = dict(namespace or {})
    tree=ast.parse(Path(path).read_bytes())
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


def require(ok, reason):
    if not ok: raise ValueError(reason)


@contextlib.contextmanager
def environment(policy=None, extra=None):
    old=dict(os.environ)
    os.environ.clear(); os.environ.update({'HOME':str(FIX),'PATH':'/usr/bin:/bin'})
    if policy is not None: os.environ[ENV_NAME]=policy
    os.environ.update(extra or {})
    try: yield
    finally: os.environ.clear(); os.environ.update(old)


@contextlib.contextmanager
def modules(mapping):
    prior={k:sys.modules.get(k) for k in mapping}
    for name, attrs in mapping.items():
        if isinstance(attrs,types.ModuleType): module=attrs
        else:
            module=types.ModuleType(name)
            for k,v in attrs.items(): setattr(module,k,v)
        sys.modules[name]=module
    try: yield
    finally:
        for k,v in prior.items():
            if v is None: sys.modules.pop(k,None)
            else: sys.modules[k]=v


def render_namespace(path=GW):
    ns={'os':os,'Path':Path,'shlex':shlex,
        'PROJECT_ROOT':FIX/'hermes-agent','SERVICE_DESCRIPTION':'Hermes Gateway fixture',
        'GATEWAY_SERVICE_RESTART_EXIT_CODE':75,'GATEWAY_FATAL_CONFIG_EXIT_CODE':78,
        'get_python_path':lambda:'/fixture/python','_stable_service_working_dir':lambda:str(FIX),
        '_build_service_path_dirs':lambda:['/fixture/bin'],'_append_node_dir_for_service':lambda *a:None,
        'resolve_systemd_timeout_stop_sec':lambda *a:70,'_get_restart_drain_timeout':lambda:0,
        '_get_cron_drain_timeout':lambda:40,'_system_service_identity':lambda user:('fixture','fixture',str(FIX),123),
        '_hermes_home_for_target_user':lambda home:str(FIX), '_profile_arg':lambda *a,**k:'-p default',
        '_remap_path_for_user':lambda p,h:p,'_ld_library_path_line':lambda **k:'',
        'get_hermes_home':lambda:FIX,'_systemd_watchdog_seconds':lambda home:30,
        'coerce_systemd_watchdog_seconds':lambda value:value,
        '_build_user_local_paths':lambda *a:[], '_build_wsl_interop_paths':lambda *a:[],
        '_systemd_command':shlex.join}
    names=['generate_systemd_unit','_normalize_service_definition','_strip_optional_systemd_directives','systemd_unit_is_current']
    if path==GW: names.append('friday_startup_test_seconds')
    ns['_SYSTEMD_OPTIONAL_DIRECTIVES']=('RestartMaxDelaySec','RestartSteps')
    return defs(path,names,ns)


def installation_command(root, args=None, *, python, home, module=None):
    assert root == FIX/'hermes-agent'
    return [python,'-m',module,*list(args or [])] if module else [python,'-m','hermes_cli.main',*list(args or [])]


LAUNCHERS={'installation_command':installation_command}


def rendered(ns, *, system=False, watchdog=30):
    with modules({'hermes_cli._launchers':LAUNCHERS}):
        return ns['generate_systemd_unit'](system=system,watchdog_seconds=watchdog)


class PolicyRendererTests(unittest.TestCase):
    def test_resolver_default_and_exact_180(self):
        ns=render_namespace()
        with environment(): self.assertEqual(ns['friday_startup_test_seconds'](),90)
        with environment('180'): self.assertEqual(ns['friday_startup_test_seconds'](),180)

    def test_malformed_policies_refused_before_render_helpers(self):
        ns=render_namespace(); touched=[]
        ns['get_python_path']=lambda:touched.append(True)
        for value in ('','90','0180','180.0','181',' 180','180 ','+180','0','nan','180\n'):
            with self.subTest(value=value),environment(value),modules({'hermes_cli._launchers':LAUNCHERS}):
                with self.assertRaisesRegex(ValueError,'requires_exact_180'): ns['generate_systemd_unit']()
        self.assertEqual(touched,[])

    def test_default_bytes_equal_exact_original_renderer_all_branches(self):
        old=render_namespace(Path(ROW['hermes_cli/gateway.py']['baseline'])); new=render_namespace()
        for system in (False,True):
            for watchdog in (0,30):
                with self.subTest(system=system,watchdog=watchdog),environment():
                    before=rendered(old,system=system,watchdog=watchdog)
                    after=rendered(new,system=system,watchdog=watchdog)
                    self.assertEqual(after.encode(),before.encode())
                    self.assertNotIn('TimeoutStartSec=',after)
                    self.assertNotIn(ENV_NAME,after)

    def test_180_unit_only_two_added_lines_and_rollback_is_exact(self):
        ns=render_namespace()
        for system in (False,True):
            for watchdog in (0,30):
                with environment(): original=rendered(ns,system=system,watchdog=watchdog)
                with environment('180'): changed=rendered(ns,system=system,watchdog=watchdog)
                self.assertEqual(changed.count('TimeoutStartSec=180s\n'),1)
                self.assertEqual(changed.count(f'Environment="{ENV_NAME}=180"\n'),1)
                self.assertEqual(changed.replace('TimeoutStartSec=180s\n','').replace(f'Environment="{ENV_NAME}=180"\n',''),original)
                self.assertIn('TimeoutStopSec=70',changed)
                if watchdog:
                    self.assertIn('Type=notify\nNotifyAccess=main\nWatchdogSec=30s\n',changed)
                else:self.assertIn('Type=simple\n',changed)
                with environment(): self.assertEqual(rendered(ns,system=system,watchdog=watchdog),original)
        with environment(): (FIX/'baseline90.fixture.service').write_text(rendered(ns))
        with environment('180'): (FIX/'test180.fixture.service').write_text(rendered(ns))

    def test_existing_generic_comparator_retains_exact_policy_and_foreign_refusal(self):
        ns=render_namespace(); path=FIX/'comparison.service'
        ns['_sync_hermes_home_from_systemd_unit']=lambda **k:None
        ns['get_systemd_unit_path']=lambda **k:path
        with environment('180'):
            unit=rendered(ns);path.write_text(unit)
            with modules({'hermes_cli._launchers':LAUNCHERS}):
                self.assertTrue(ns['systemd_unit_is_current']())
                path.write_text(unit.replace('TimeoutStartSec=180s','TimeoutStartSec=181s'))
                self.assertFalse(ns['systemd_unit_is_current']())
                path.write_text(unit.replace('WatchdogSec=30s','WatchdogSec=0s'))
                self.assertFalse(ns['systemd_unit_is_current']())
                path.write_text(unit)
        with environment(),modules({'hermes_cli._launchers':LAUNCHERS}):
            self.assertFalse(ns['systemd_unit_is_current']())
            path.write_text(rendered(ns)); self.assertTrue(ns['systemd_unit_is_current']())


class Clock:
    def __init__(self):self.now=1000.0
    def monotonic(self):return self.now


def budget_type(clock):
    return defs(CONTAIN,['Budget'],{'time':clock,'math':math})['Budget']


class BootstrapTests(unittest.TestCase):
    def execute(self,path,*,policy=None,managed=True,values=None):
        home=FIX/'bootstrap-home'; values={} if values is None else values
        ns={'os':os,'SOURCE':home/'hermes-agent','require':require,
            'managed':lambda h:managed,'cli_host_phase':lambda h:None,
            'configuration':lambda h:{},'profile_policy':lambda h,c:{'required_scoped_names':{'web':[],'worker_service':[],'channels':{}},'native_dashboard':{'public_url':''}},
            'local_route':lambda c:('provider','model','https://fixture.invalid','PROVIDER_API_KEY'),
            'owned_values':lambda h:dict(values),'own_pool':lambda p:[{'access_token':'fixture','base_url':'https://fixture.invalid'}],
            'keyless':lambda c:True}
        ns=defs(path,['bootstrap'],ns)
        mapping={'hermes_constants':{'get_hermes_home':lambda:home},
            'hermes_cli.friday_cli_principal':{'current_cli':lambda:None},
            'hermes_cli.friday_dashboard_owner':{'source_identity':lambda *a,**k:None},
            'agent.secret_scope':{'_is_global_env':lambda n:n in ('HOME','PATH','HERMES_HOME'),
                'set_secret_scope':lambda *a,**k:None,'set_multiplex_context':lambda x:None}}
        with environment(policy,{'UNRELATED_SECRET_FIXTURE':'scrub-me','NOTIFY_SOCKET':'fixture-notify'}),modules(mapping):
            result=ns['bootstrap'](home)
            return result,dict(os.environ)

    def test_native_bootstrap_preserves_only_exact_optin_and_existing_native_facts(self):
        result,env=self.execute(ADMISSION,policy='180')
        self.assertEqual(env[ENV_NAME],'180');self.assertNotIn('UNRELATED_SECRET_FIXTURE',env)
        self.assertEqual(env['NOTIFY_SOCKET'],'fixture-notify')

    def test_bootstrap_default_equivalent_to_baseline(self):
        before=self.execute(Path(ROW['hermes_cli/friday_credential_admission.py']['baseline']))
        after=self.execute(ADMISSION)
        self.assertEqual(after,before)

    def test_bootstrap_invalid_values_rejected(self):
        for policy in ('','90','180.0',' 180','181'):
            with self.subTest(policy=policy),self.assertRaisesRegex(ValueError,'requires_exact_180'):
                self.execute(ADMISSION,policy=policy)

    def test_persistent_profile_policy_refused(self):
        for policy in (None,'180'):
            with self.subTest(policy=policy),self.assertRaisesRegex(ValueError,'requires_exact_180'):
                self.execute(ADMISSION,policy=policy,values={ENV_NAME:'180'})

    def test_unmanaged_branch_unchanged_including_unused_invalid_setting(self):
        for policy in (None,'180','invalid'):
            old=self.execute(Path(ROW['hermes_cli/friday_credential_admission.py']['baseline']),policy=policy,managed=False)
            new=self.execute(ADMISSION,policy=policy,managed=False)
            self.assertEqual(old,new)


class PreflightTests(unittest.TestCase):
    def execute(self, *, policy='180',foreign=False,dropin=False):
        home=FIX/'preflight-home';unit=FIX/'preflight-units'/'fixture.service';unit.parent.mkdir(exist_ok=True)
        d=unit.parent/(unit.name+'.d')
        if d.exists():
            for p in d.iterdir():p.unlink()
            d.rmdir()
        gw_ns=render_namespace();gw_ns['get_hermes_home']=lambda:home
        with environment(policy): unit.write_text(rendered(gw_ns).replace('TimeoutStartSec=180s','TimeoutStartSec=90s') if foreign else rendered(gw_ns))
        unit.chmod(0o600)
        if dropin:d.mkdir();(d/'foreign.conf').write_text('[Service]\nTimeoutStartSec=180\n')
        gw=types.ModuleType('hermes_cli.gateway')
        for key,value in gw_ns.items():setattr(gw,key,value)
        for key,value in dict(supports_systemd_services=lambda:True,has_legacy_hermes_units=lambda:False,
            has_conflicting_systemd_units=lambda:False,get_systemd_unit_path=lambda system=False:unit if not system else unit.parent/'absent-system.service',
            _hermes_home_pinned_by_unit=lambda u:str(home)).items():setattr(gw,key,value)
        hr=types.SimpleNamespace(ROLE_GATEWAY='gateway',read_record=lambda *a,**k:None)
        ns=defs(START,['gateway_preflight'],{'gateway_watchdog_seconds':lambda h:30})
        clock=Clock();budget=budget_type(clock)(600)
        mapping={'gateway':{'host_rendezvous':hr},'hermes_cli':{'gateway':gw},
            'hermes_constants':{'get_hermes_home':lambda:home},
            'scripts.friday_install':{'owned_file':lambda p:Path(p).read_bytes(),'require':require},
            'hermes_cli._launchers':LAUNCHERS}
        with environment(policy),modules(mapping):return ns['gateway_preflight'](home,'default',budget)

    def test_preflight_admits_exact_180(self):self.assertIsNone(self.execute()[1])
    def test_preflight_refuses_foreign_timeout(self):
        with self.assertRaisesRegex(ValueError,'foreign_or_changed_gateway_unit'):self.execute(foreign=True)
    def test_preflight_refuses_dropins_even_matching_policy(self):
        with self.assertRaisesRegex(ValueError,'gateway_dropin'):self.execute(dropin=True)


class StopUnconfirmed(Exception):pass


class RestartInputsTests(unittest.TestCase):
    def execute(self, *, policy='180',unit_policy='180',foreign=False):
        home=FIX/'restart-home';unit=FIX/'restart-units'/'fixture.service';unit.parent.mkdir(exist_ok=True)
        ns=render_namespace();ns['get_hermes_home']=lambda:home
        with environment(unit_policy):unit.write_text(rendered(ns))
        if foreign:unit.write_text(unit.read_text().replace('TimeoutStartSec=180s','TimeoutStartSec=181s'))
        unit.chmod(0o600)
        gw=types.ModuleType('hermes_cli.gateway')
        for key,value in ns.items():setattr(gw,key,value)
        for key,value in dict(supports_systemd_services=lambda:True,has_legacy_hermes_units=lambda:False,
            has_conflicting_systemd_units=lambda:False,get_systemd_unit_path=lambda system=False:unit if not system else unit.parent/'absent-system.service',
            _hermes_home_pinned_by_unit=lambda u:str(home),
            _read_systemd_unit_properties=lambda **k:{'ActiveState':'active','SubState':'running','MainPID':'123','InvocationID':'a'*32}).items():setattr(gw,key,value)
        record=types.SimpleNamespace(home=str(home),profiles=['default'],protocol_version=1,start_time=42,pid=123)
        hr=types.SimpleNamespace(ROLE_GATEWAY='gateway',read_record=lambda *a,**k:record,
            liveness_is_proven=lambda r:True,record_token_is_consistent=lambda r:True)
        original=Path(ROW['hermes_cli/gateway.py']['baseline']).parent/'friday_ordinary_gateway.py'
        call=defs(original,['restart_inputs'],{'require':require,'Path':Path,'re':__import__('re'),
            'check':lambda *a,**k:{'configuration_sha256':'fixture','baseline':{}},
            'normalized_configuration':lambda c:'fixture','configuration_contract':lambda *a:None})['restart_inputs']
        mapping={'gateway':{'host_rendezvous':hr},'hermes_cli':{'gateway':gw},
            'hermes_cli.friday_dashboard_owner':{'read_owned':lambda p:Path(p).read_bytes()},
            'hermes_cli.friday_credential_admission':{'configuration':lambda h:{'gateway':{'systemd_watchdog_seconds':30}}},
            'hermes_cli._launchers':LAUNCHERS}
        with environment(policy),modules(mapping):return call(home)

    def test_existing_restart_inputs_admits_exact_180_and_proved_owner(self):self.assertIsNone(self.execute())
    def test_existing_restart_inputs_refuses_foreign_timeout(self):
        with self.assertRaisesRegex(ValueError,'restart_foreign_unit_refused'):self.execute(foreign=True)
    def test_existing_restart_inputs_refuses_180_unit_without_policy(self):
        with self.assertRaisesRegex(ValueError,'restart_foreign_unit_refused'):self.execute(policy=None)


class Runtime:
    def __str__(self):return '/fixture/user-runtime'
    def __truediv__(self,name):
        assert name=='bus'
        return types.SimpleNamespace(lstat=lambda:types.SimpleNamespace(st_mode=stat.S_IFSOCK|0o600,st_uid=os.getuid(),st_nlink=1),__str__=lambda:'/fixture/user-runtime/bus')


class OrdinaryStartTests(unittest.TestCase):
    def execute(self,policy,*,remaining=600,proof_cost=0,run_cost=0,preflight_cost=0):
        home=FIX/'ordinary-home';source=home/'hermes-agent';launcher=source/'.hermes/bin/hermes'
        launcher.parent.mkdir(parents=True,exist_ok=True)
        python=Path(sys.executable)
        launch_script='fixture-installed-entry'
        launch_bytes=('#!/bin/sh\nexec '+shlex.join([str(python),'-I','-c',launch_script])+' "$@"\n').encode()
        launcher.write_bytes(launch_bytes);launcher.chmod(0o700)
        unit=FIX/'ordinary-unit.service';unit.write_text('fixture')
        clock=Clock();B=budget_type(clock);budget=B(600,started=1000,deadline=1000+remaining)
        runs=[];proof=[]
        class Custody:
            def __init__(self,pin,budget,env):self.budget=budget
            def probe(self,*a):pass
            def run(self,argv,cwd,**kwargs):
                runs.append((argv,cwd,kwargs));clock.now+=run_cost
        def observation(h,b):
            proof.append(b);clock.now+=proof_cost;b.check()
        def bootstrap(h):clock.now+=preflight_cost
        resolver=defs(GW,['friday_startup_test_seconds'],{'os':os})['friday_startup_test_seconds']
        gw=types.SimpleNamespace(friday_startup_test_seconds=resolver,
            get_systemd_linger_status=lambda:(True,None),_read_systemd_unit_properties=lambda **k:{'ActiveState':'inactive','MainPID':'0'},
            find_gateway_pids=lambda:[],get_service_name=lambda:'ordinary-unit')
        install={'clean_environment':lambda h:{'HERMES_HOME':str(h)},'require':require,
                 'owned_file':lambda p:Path(p).read_bytes(),'directory':lambda p:Runtime(),
                 'safe_diagnostic':lambda e,stage:{'stage':stage,'reason':str(e)},'remember_secondary':lambda e,s:None}
        mapping={'gateway':{'host_rendezvous':object()},'hermes_cli':{'gateway':gw},
            'hermes_cli.friday_ordinary_gateway':{'check':lambda h:None},
            'hermes_cli.friday_credential_admission':{'bootstrap':bootstrap,'scoped':lambda h:contextlib.nullcontext(),
                'route_inputs':lambda:None,'channel_inputs':lambda:({}, {})},
            'scripts.friday_install':install,'scripts.install_containment':{'Containment':Custody,'Budget':B},
            'scripts.dsh_prepare':{'StopUnconfirmed':StopUnconfirmed},
            'hermes_constants':{'get_hermes_home':lambda:home},'pm.paths':{'repo_root':lambda:source},
            'pm.environments':{'project_python':lambda s:python},
            'hermes_cli._launchers':{'_launcher_script':lambda *a:launch_script,'resolve_store_python':lambda *a,**k:python},
            'time':{'monotonic':clock.monotonic}}
        ns=defs(START,['ordinary_start'],{'Path':Path,'sys':sys,'os':os,'shlex':shlex,
            'snapshot':lambda h,b:{},'unchanged':lambda p,b:None,'gateway_preflight':lambda *a:(unit,None),
            'gateway_observation':observation})
        outcome=None;failure=None
        with environment(policy),modules(mapping):
            try:outcome=ns['ordinary_start']({'home':str(home),'containment':{},'bootstrap_python':{'path':str(python)}},budget)
            except BaseException as e:failure=e
        return outcome,failure,runs,proof,budget,clock

    def test_default_waiter90_and_original_budget_unchanged(self):
        outcome,failure,runs,proof,budget,clock=self.execute(None)
        self.assertIsNone(failure);self.assertEqual(runs[0][2],{'timeout':90})
        self.assertIs(proof[0],budget);self.assertFalse(outcome['ready']);self.assertFalse(outcome['workers_enabled'])

    def test_test_waiter210_fullflag_and_proof60_inside_original_deadline(self):
        outcome,failure,runs,proof,budget,clock=self.execute('180',run_cost=210)
        self.assertIsNone(failure);self.assertEqual(runs[0][2],{'timeout':210,'require_full_timeout':True,'timeout_reserve':60})
        self.assertEqual(proof[0].deadline,1270);self.assertLessEqual(proof[0].deadline,budget.deadline)
        self.assertFalse(outcome['ready']);self.assertIn('GENUINE_TELEGRAM',outcome['runtime_acceptance'])

    def test_insufficient_remaining_refused_before_single_start(self):
        for remaining in (270,271):
            outcome,failure,runs,proof,budget,clock=self.execute('180',remaining=remaining)
            self.assertIsInstance(failure,StopUnconfirmed);self.assertEqual(runs,[]);self.assertEqual(proof,[])
            self.assertEqual(failure.friday_diagnostic['stage'],'ordinary_native_unit_start')
            self.assertIsInstance(failure.friday_custody_primary,ValueError)
            self.assertEqual(failure.friday_custody_state,'UNCONFIRMED')

    def test_sufficient_floor_preserves_original_absolute_deadline(self):
        outcome,failure,runs,proof,budget,clock=self.execute('180',remaining=272,run_cost=210)
        self.assertIsNone(failure);self.assertEqual(budget.deadline,1272);self.assertEqual(proof[0].deadline,1270)

    def test_ready_proof_exhaustion_preserves_original_failure_and_no_retry(self):
        outcome,failure,runs,proof,budget,clock=self.execute('180',proof_cost=61)
        self.assertIsInstance(failure,StopUnconfirmed);self.assertEqual(len(runs),1)
        self.assertEqual(failure.friday_diagnostic['stage'],'ordinary_gateway_observation')
        self.assertEqual(str(failure.friday_custody_primary),'original_install_budget_exhausted')
        self.assertEqual(budget.deadline,1600)

    def test_invalid_policy_never_dispatches(self):
        outcome,failure,runs,proof,budget,clock=self.execute('90')
        self.assertIsInstance(failure,ValueError);self.assertEqual(runs,[])

    def test_pinned_outer_native438_preserves_stop_accounting_cleanup162(self):
        # The reviewed operation supplies this absolute deadline; Budget itself
        # does not infer or subtract root reserves a second time.
        external=90+70+.25+.25+1.5
        self.assertEqual(external,162)
        outcome,failure,runs,proof,budget,clock=self.execute('180',remaining=600-external,
            preflight_cost=166,run_cost=210,proof_cost=59)
        self.assertIsNone(failure);self.assertEqual(budget.deadline,1438)
        self.assertLessEqual(proof[0].deadline,1438);self.assertLess(clock.now,1438)
        outcome,failure,runs,proof,budget,clock=self.execute('180',remaining=438,preflight_cost=167)
        self.assertIsInstance(failure,StopUnconfirmed);self.assertEqual(runs,[])


class PipeReached(Exception):
    def __init__(self,limit):self.limit=limit


class DefaultStructuralTests(unittest.TestCase):
    def function(self,path,name):
        return next(n for n in ast.parse(Path(path).read_bytes()).body
                    if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)

    def test_renderer_absent_policy_specializes_to_exact_original_ast(self):
        old=self.function(ROW['hermes_cli/gateway.py']['baseline'],'generate_systemd_unit')
        new=self.function(GW,'generate_systemd_unit')
        class Specialize(ast.NodeTransformer):
            def visit_Assign(self,n):
                if any(isinstance(t,ast.Name) and t.id in ('startup_seconds','startup_directives','startup_environment') for t in n.targets):return None
                return self.generic_visit(n)
            def visit_JoinedStr(self,n):
                n.values=[v for v in n.values if not(isinstance(v,ast.FormattedValue) and isinstance(v.value,ast.Name) and v.value.id in ('startup_directives','startup_environment'))]
                return self.generic_visit(n)
        self.assertEqual(ast.dump(Specialize().visit(new)),ast.dump(old))

    def test_containment_default_body_and_signature_specialize_to_original_ast(self):
        old=self.function(ROW['plugins/friday_rework/runtime_containment.py']['baseline'],'Containment')
        new=self.function(CONTAIN,'Containment')
        old=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        new=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        new.args.kwonlyargs=new.args.kwonlyargs[:-2];new.args.kw_defaults=new.args.kw_defaults[:-2]
        new.body=[n for n in new.body if not(isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp)
            and any(isinstance(v,ast.Name) and v.id=='require_full_timeout' for v in n.test.values))]
        self.assertEqual(ast.dump(new),ast.dump(old))

    def test_bootstrap_existing_auth_and_scrub_ast_preserved(self):
        old=self.function(ROW['hermes_cli/friday_credential_admission.py']['baseline'],'bootstrap')
        new=self.function(ADMISSION,'bootstrap')
        new.body=[n for n in new.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='startup_test_env' for t in n.targets))
            and not(isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and any(isinstance(a,ast.Constant) and a.value=='friday_startup_test_seconds_requires_exact_180' for a in n.value.args))]
        for n in ast.walk(new):
            if isinstance(n,ast.Tuple):n.elts=[v for v in n.elts if not(isinstance(v,ast.Name) and v.id=='startup_test_env')]
        self.assertEqual(ast.dump(new),ast.dump(old))


class FullTimeoutTests(unittest.TestCase):
    def execute(self,*,remaining,flag=False,binary_cost=0,timeout_reserve=0):
        clock=Clock();B=budget_type(clock);budget=B(600,started=1000,deadline=1000+remaining);events=[]
        def checked(pin):events.append('checked_binary');clock.now+=binary_cost
        def pipe(flags):
            events.append('pipe_boundary');raise PipeReached(inspect.currentframe().f_back.f_locals['limit'])
        fake_os=types.SimpleNamespace(pipe2=pipe,O_CLOEXEC=1,O_NONBLOCK=2)
        ns=defs(CONTAIN,['Containment'],{'os':fake_os,'checked_binary':checked,'__package__':'isolated'})
        obj=ns['Containment'].__new__(ns['Containment']);obj.pin={};obj.budget=budget;obj.binary='fixture';obj.env={}
        mapping={'isolated.runtime_process':{'run':lambda *a,**k:None,'CommandFailed':RuntimeError,'StopUnconfirmed':StopUnconfirmed,'safe_observation':lambda *a:None}}
        with modules(mapping):
            try:obj.run(['fixture'],FIX,timeout=210,require_full_timeout=flag,timeout_reserve=timeout_reserve)
            except BaseException as exc:return exc,events,budget
        raise AssertionError('must stop before fake pipe or run')

    def test_full_timeout_rejects_clipped_window_before_pipe_and_manager_effect(self):
        for remaining in (200,210,210.99):
            failure,events,budget=self.execute(remaining=remaining,flag=True)
            self.assertIsInstance(failure,ValueError);self.assertEqual(str(failure),'original_install_full_command_window_required')
            self.assertEqual(events,['checked_binary'])

    def test_guard_is_after_binary_verification_even_if_time_is_consumed(self):
        failure,events,budget=self.execute(remaining=272,flag=True,binary_cost=62)
        self.assertIsInstance(failure,ValueError);self.assertEqual(events,['checked_binary'])

    def test_full_timeout_also_preserves_proof60_after_binary_check(self):
        failure,events,budget=self.execute(remaining=272,flag=True,binary_cost=2,timeout_reserve=60)
        self.assertIsInstance(failure,ValueError);self.assertEqual(events,['checked_binary'])
        failure,events,budget=self.execute(remaining=272,flag=True,binary_cost=1,timeout_reserve=60)
        self.assertIsInstance(failure,PipeReached);self.assertEqual(failure.limit,210)

    def test_210_full_window_accepted_with_cleanup_inside_absolute_deadline(self):
        failure,events,budget=self.execute(remaining=211,flag=True)
        self.assertIsInstance(failure,PipeReached);self.assertEqual(failure.limit,210)
        self.assertEqual(events,['checked_binary','pipe_boundary']);self.assertEqual(budget.deadline,1211)

    def test_default_clipping_preserved(self):
        failure,events,budget=self.execute(remaining=200,flag=False)
        self.assertIsInstance(failure,PipeReached);self.assertEqual(failure.limit,199)


if __name__=='__main__':
    for row in MANIFEST:
        assert hashlib.sha256(Path(row['baseline']).read_bytes()).hexdigest()==row['before_sha256']
        compile(Path(row['candidate']).read_bytes(),row['candidate'],'exec')
    started=time.monotonic();suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'schema':'frw.installed96.one180.focused-tests.v1','tests_run':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),
        'elapsed_seconds':time.monotonic()-started,'cpu_affinity':CPU_SET,'cpu_limit_seconds':240,
        'address_space_bytes':1024**3,'file_limit_bytes':64*1024**2,'no_children':True,
        'scope':'Actual selected functions executed through AST extraction; finite explicit fixture collaborators only. No product runtime imports or native/service/network/model/DB/Git effects. Unit generation is a controlled offline fixture, not actual installed render/runtime acceptance.'}
    (BASE/'TEST-RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    sys.exit(not result.wasSuccessful())
