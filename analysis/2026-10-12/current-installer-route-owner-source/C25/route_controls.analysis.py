"""INERT affected route controls. No candidate import, auto-run, or authority issuer.

Root must admit exact stock caller/guard BEFORE loading these bytes or candidate.
The injected four-process cohort is a distinct already owned isolated fixture,
with genuine before-GO identity/resource/closure observation supplied OUTSIDE.
No new process, live TUI constructor, native RPC, install, or rollback occurs.
Synthetic descriptor/review data exercises Source consistency only.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import types

CASES=(
    'current_births_historical_binding_positive', 'historical_binding_pids_missing_positive',
    'missing_birth', 'reused_pid_birth', 'birth_key_integer', 'birth_value_integer',
    'birth_key_leading_zero', 'birth_value_zero', 'extra_birth', 'missing_current_birth',
    'foreign_writer', 'second_TUI', 'second_backend', 'unloaded_backend',
    'writer_mismatch', 'slot_pid_reuse', 'missing_slot_state_field', 'invalid_slot_pid_type',
    'home_drift', 'thread_drift', 'epoch_drift', 'endpoint_drift', 'binding_endpoint_drift',
    'same_thread', 'four_process_coverage', 'dependency_change_before_capture',
    'dependency_change_after_capture', 'binding_change_during_observation',
    'lock_inode_change', 'recheck_calls_fresh_slot_state',
)


def write(path, value):
    raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True)+'\n').encode()
    assert len(raw)<=1048576
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def replace(path, raw):
    path.chmod(0o600);path.write_bytes(raw);path.chmod(0o400)


def fixture(M, root, cohort):
    """Producer of the SAME v1 route schema; no historical binding PID lookup.

    cohort={slot:{'tui':{'pid':int,'birth':str},'backend':same}} must come from
    the independently admitted caller's exact already owned fixture processes.
    They remain running under that existing outside owner through observation.
    It is identity input, not an authorization capability or a default issuer.
    """
    if set(cohort)!={'sol','astra'}:raise ValueError('fixture cohort coverage')
    all_pids=[]
    for group in cohort.values():
        if set(group)!={'tui','backend'}:raise ValueError('fixture role coverage')
        for p in group.values():
            if set(p)!={'pid','birth'} or type(p['pid']) is not int or p['pid']<=0:
                raise ValueError('fixture identity')
            actual=Path('/proc/'+str(p['pid'])+'/stat').read_text().rsplit(')',1)[1].split()[19]
            if actual!=p['birth']:raise ValueError('fixture birth not current')
            all_pids.append(p['pid'])
    if len(set(all_pids))!=4:raise ValueError('distinct fixture four-process cohort required')
    root.mkdir(mode=0o700);routes={};projection={};states={}
    for slot in ('sol','astra'):
        home=str(root/(slot+'-account'));thread='PRIVATE-SYNTHETIC-'+slot
        epoch='PRIVATE-SYNTHETIC-EPOCH-'+slot
        endpoint=str(Path(home)/'app-server-control/app-server-control.sock')
        b={'role':'Sol' if slot=='sol' else 'Astra','account_home':home,'thread_id':thread,
           'generation':epoch,'backend_endpoint':'unix://'+endpoint,
           'pid':99999997 if slot=='sol' else 99999995,
           'backend_pid':99999996 if slot=='sol' else 99999994}
        bp=root/('sol-link-'+slot+'.binding.json');write(bp,b)
        births={str(p['pid']):p['birth'] for p in cohort[slot].values()}
        routes[slot]={'binding':M.reference(bp),'home':home,'thread':thread,
                      'generation':epoch,'endpoint':endpoint,'births':births}
        projection[slot]=(home,thread,endpoint)
        tui=cohort[slot]['tui']['pid'];backend=cohort[slot]['backend']['pid']
        states[(home,thread)]={'active_tui_pids':[tui],'backend_pids':[backend],
                             'active_writer_pids':[backend],'foreign_writer_pids':[]}
    reconnect=("STATES="+repr(states)+"\nCALLS=[]\n"
               "def slot_state(home,thread,endpoint):\n"
               " CALLS.append((home,thread,str(endpoint)))\n"
               " return STATES[(home,thread)]\n").encode()
    control=("from pathlib import Path\nclass NativeControl:\n"
             " def __init__(self,slot):\n"
             "  self.home,self.thread,endpoint="+repr(projection)+"[slot]\n"
             "  self.endpoint=Path(endpoint)\n").encode()
    deps={}
    for name,rel in M.DEPENDENCIES.items():
        raw=control if name=='control' else reconnect if name=='reconnect' else b'INERT_FIXTURE=True\n'
        path=root/rel;write(path,raw);deps[name]=M.reference(path)
    # Actual fixture advisory locks are held by the injected caller, no fake fd.
    held=M.acquire()
    return {'routes':routes,'dependencies':deps,'_held_locks':held}


def execute(case, M, fixture_root, cohort):
    """One Source-author observation. OUTSIDE caller owns genuine admission.

    This function cannot authenticate its caller. Root must retain the exact
    pre-effect stock invocation and verify actual outside stop/exit/closure.
    It deliberately has no __main__, loader, JSON grant, or invented owner.
    """
    if case not in CASES:raise ValueError('case')
    root=Path(fixture_root)
    package=Path(__file__).absolute().parent.parent
    if not root.is_absolute() or '..' in root.parts or not root.is_relative_to(package/'execution'):
        raise ValueError('fixture outside this exact private output')
    original_R=M.R;M.R=root;held=[];changes=[]
    try:
        d=fixture(M,root,cohort);held=d['_held_locks']
        routes=d['routes'];r=routes['sol'];births=r['births'];keys=list(births)
        want_refusal=case not in ('current_births_historical_binding_positive',
                                  'historical_binding_pids_missing_positive',
                                  'dependency_change_after_capture', 'recheck_calls_fresh_slot_state')
        if case=='historical_binding_pids_missing_positive':
            for route in routes.values():
                bp=Path(route['binding']['path']);b=M.loads(bp.read_bytes());b.pop('pid');b.pop('backend_pid')
                replace(bp,M.encode(b));route['binding']=M.reference(bp)
        if case=='missing_birth':births[keys[0]]='99999999999999999999'
        if case=='reused_pid_birth':births[keys[0]]=str(int(births[keys[0]])+1)
        if case=='birth_key_integer':births[int(keys[0])]=births.pop(keys[0])
        if case=='birth_value_integer':births[keys[0]]=int(births[keys[0]])
        if case=='birth_key_leading_zero':births['0'+keys[0]]=births.pop(keys[0])
        if case=='birth_value_zero':births[keys[0]]='0'
        if case=='extra_birth':births['99999993']='1'
        if case=='missing_current_birth':births.pop(keys[0])
        if case=='home_drift':r['home']+='/drift'
        if case=='thread_drift':r['thread']+='-drift'
        if case=='epoch_drift':r['generation']+='-drift'
        if case=='endpoint_drift':r['endpoint']+='.drift'
        if case=='binding_endpoint_drift':
            bp=Path(r['binding']['path']);b=M.loads(bp.read_bytes());b['backend_endpoint']+='.drift'
            replace(bp,M.encode(b));r['binding']=M.reference(bp)
        if case=='same_thread':routes['astra']['thread']=r['thread']
        if case=='four_process_coverage':routes['astra']['births']=dict(births)
        if case in ('foreign_writer','second_TUI','second_backend','unloaded_backend',
                    'writer_mismatch','slot_pid_reuse','missing_slot_state_field','invalid_slot_pid_type'):
            path=Path(d['dependencies']['reconnect']['path']);raw=path.read_bytes()
            extra='\nORIGINAL=slot_state\ndef slot_state(home,thread,endpoint):\n v={k:list(x) for k,x in ORIGINAL(home,thread,endpoint).items()}\n'
            actions={'foreign_writer':"v['foreign_writer_pids']=[99999993]",
                     'second_TUI':"v['active_tui_pids'].append(99999993)",
                     'second_backend':"v['backend_pids'].append(99999993)",
                     'unloaded_backend':"v['active_writer_pids']=[]",
                     'writer_mismatch':"v['active_writer_pids']=[99999993]",
                     'slot_pid_reuse':"v['active_tui_pids']=[v['backend_pids'][0]]",
                     'missing_slot_state_field':"v.pop('foreign_writer_pids')",
                     'invalid_slot_pid_type':"v['active_tui_pids']=[True]"}
            replace(path,raw+(extra+' '+actions[case]+'\n return v\n').encode())
            d['dependencies']['reconnect']=M.reference(path)
        if case in ('dependency_change_before_capture','dependency_change_after_capture'):
            bad=Path(d['dependencies']['reconnect']['path'])
            evil=("from pathlib import Path\nPath("+repr(str(root/'UNREVIEWED-EXECUTED'))+") .write_text('bad')\n").encode()
            if case=='dependency_change_before_capture':replace(bad,evil)
            else:
                old=M.CapturedDependencies.__init__;changes.append((M.CapturedDependencies,'__init__',old))
                def capture(self,desc):old(self,desc);replace(bad,evil)
                M.CapturedDependencies.__init__=capture
        if case=='binding_change_during_observation':
            old=M.CapturedDependencies.module;changes.append((M.CapturedDependencies,'module',old));changed=False
            def module(self,name):
                nonlocal changed
                result=old(self,name)
                if name=='reconnect' and not changed:
                    bp=Path(r['binding']['path']);replace(bp,bp.read_bytes()+b' ');changed=True
                return result
            M.CapturedDependencies.module=module
        if case=='lock_inode_change':
            path=root/M.LOCK_NAMES[0];path.rename(root/'retained-lock');write(path,b'')
        if case=='recheck_calls_fresh_slot_state':
            # recheck must invoke the route validator at EVERY per-file effect.
            # Use the route code unchanged; intercept only unrelated fixed pins.
            old=M.pin;changes.append((M,'pin',old));clock_ref={'private':'clock'}
            d.update(source=clock_ref,review=clock_ref,clock=clock_ref,files=[])
            def pins(ref,*args):return (M.encode({'synthetic':True}),None) if ref is clock_ref else old(ref,*args)
            M.pin=pins
            oldclock=M.clock;changes.append((M,'clock',oldclock));M.clock=lambda value:None
            oldcap=M.CapturedDependencies.__init__;changes.append((M.CapturedDependencies,'__init__',oldcap))
            captures=[]
            def cap(self,desc):oldcap(self,desc);captures.append(self)
            M.CapturedDependencies.__init__=cap
            M.recheck(d);M.recheck(d)
            assert len(captures)==2
            assert all(len(c.module('reconnect').CALLS)==2 for c in captures)
            return {'author_observation':'two rechecks used two fresh actual captured route observations',
                    'unrelated_clock_authentication_mocked_for_route_coverage_ONLY':True,
                    'runtime_admission_proof':False}
        try:
            M.validate_routes(d)
        except (M.Refusal,OSError):
            if not want_refusal:raise
            outcome='REFUSED_EXPECTED'
        else:
            if want_refusal:raise AssertionError('route unexpectedly accepted')
            outcome='ACCEPTED_SYNTHETIC_CURRENT_FIXTURE'
        assert not (root/'UNREVIEWED-EXECUTED').exists()
        if case=='dependency_change_after_capture':
            try:M.pin(d['dependencies']['reconnect'])
            except M.Refusal:pass
            else:raise AssertionError('changed dependency next pre-effect pin accepted')
        return {'case':case,'author_observation':outcome,'actual_live_native_calls':0,
                'historical_binding_pid_read_as_target':False,'Source_independent_acceptance':False}
    finally:
        for obj,name,value in reversed(changes):setattr(obj,name,value)
        for fd in reversed(held):os.close(fd)
        M.R=original_R
