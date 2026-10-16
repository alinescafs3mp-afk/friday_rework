import ast, copy, hashlib, json, types
from pathlib import Path
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/worker_qualification.py'
tree=ast.parse(SOURCE.read_text())
names={'DSH_NATIVE_SAFETY','DSH_SAFETY_CONTROLS','checked_dsh_safety'}
nodes=[n for n in tree.body if getattr(n,'name',None) in names or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
def require(ok,reason):
    if not ok:raise ValueError(reason)
q=types.SimpleNamespace()
q.__dict__.update(hashlib=hashlib,require=require)
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),q.__dict__)
fixture_source=Path(__file__).with_name('test_worker_qualification.py')
f=next(n for n in ast.parse(fixture_source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='safety_observation')
ns={'q':q};exec(compile(ast.Module(body=[f],type_ignores=[]),str(fixture_source),'exec'),ns)

@pytest.fixture
def evidence():
    runtime={'runtime_profile':'fixture','dsh':{'payload_root':'/fixture/harness','node':{'path':'/fixture/node'},'memory_bytes':1,'cpu_percent':1,'tasks':1}}
    report=ns['safety_observation'](runtime,Path('/fixture/home'),Path('/fixture/safety'),types.SimpleNamespace(deadline=100))['report']
    return runtime,report

def test_observed_nonzero_bounding_mask_is_not_current_privilege(evidence):
    runtime,report=evidence
    assert q.checked_dsh_safety(report,runtime,Path('/fixture/home')) is report

@pytest.mark.parametrize('bad',['missing','opaque','wrong-home','wrong-profile','wrong-node','wrong-payload','wrong-artifact','missing-control','outer-label','extra-command-stack','nnp','inh','prm','eff','amb','missing-bnd','outer-user','outer-pid','outer-mnt','nested-pid','nested-user','nested-mnt','maps','wrapper','shell-result','proc-mount'])
def test_native_safety_negative_controls(evidence,bad):
    runtime,r=evidence;r=copy.deepcopy(r)
    if bad=='missing':r=None
    elif bad=='opaque':r={'ready':True}
    elif bad.startswith('wrong-'):
        key={'home':'runtime_home','profile':'runtime_profile','node':'node','payload':'payload_root','artifact':'artifact_sha256'}[bad[6:]];r[key]='foreign'
    elif bad=='missing-control':r['controls'].pop()
    elif bad=='outer-label':r['outer']['label']='unconfined'
    elif bad=='extra-command-stack':r['nested']['bash-label']='unconfined//&'+r['nested']['bash-label']
    elif bad in ('nnp','inh','prm','eff','amb','missing-bnd'):
        key={'nnp':'NoNewPrivs','inh':'CapInh','prm':'CapPrm','eff':'CapEff','amb':'CapAmb','missing-bnd':'CapBnd'}[bad]
        r['nested']['bash-status']='\n'.join(line if not line.startswith(key+':') else (key+(': 0' if bad=='nnp' else ': 1') if bad!='missing-bnd' else '') for line in r['nested']['bash-status'].splitlines())
    elif bad.startswith('outer-'):key=bad[6:];r['outer']['ns'][key]=r['host']['namespaces'][key]
    elif bad.startswith('nested-'):key=bad[7:];r['nested']['bash-'+key+'ns']=r['outer']['ns'][key]
    elif bad=='maps':r['outer']['uid_map']='unobserved'
    elif bad=='wrapper':r['wrap']['argv']=['/bin/bash']
    elif bad=='shell-result':r['shell_result']={'exitCode':1}
    elif bad=='proc-mount':r['nested']['bash-mountinfo']='unobserved'
    with pytest.raises((ValueError,KeyError,TypeError)):q.checked_dsh_safety(r,runtime,Path('/fixture/home'))

@pytest.mark.parametrize('bad',['pid-as-namespace','namespace-as-pid','bool-pid','missing-namespaces',
                               'unobserved-pid','wrong-prefix','nested-host-pid'])
def test_distinct_host_process_and_namespace_identities(evidence,bad):
    runtime,r=evidence;r=copy.deepcopy(r)
    if bad=='pid-as-namespace':r['host']['namespaces']['pid']=r['host']['pid']
    elif bad=='namespace-as-pid':r['host']['pid']=r['host']['namespaces']['pid']
    elif bad=='bool-pid':r['host']['pid']=True
    elif bad=='missing-namespaces':r['host'].pop('namespaces')
    elif bad=='unobserved-pid':r['outer']['ns']['pid']='unobserved'
    elif bad=='wrong-prefix':r['outer']['ns']['pid']='user:[2]'
    elif bad=='nested-host-pid':r['nested']['bash-pidns']=r['host']['namespaces']['pid']
    with pytest.raises((ValueError,KeyError,TypeError)):
        q.checked_dsh_safety(r,runtime,Path('/fixture/home'))

def test_safety_precedes_credentials_and_initial_native_owner_in_both_entrypoints():
    for path,credential,producer in [(SOURCE,"credentials =",'installation_probe(product'),(SOURCE.parents[1]/'plugins/friday_rework/user_worker_join.py',"credentials =",'probe = InitialProbe(')]:
        text=path.read_text();text=text[text.index('def qualify('):]
        assert text.index('budget.call(dsh_safety_observe')<text.index(credential)<text.index(producer)
        assert "retry_authorized" in text and "failure.json" in text

def test_unique_adapter_launch_preserves_foreground_namespace_custody():
    text=SOURCE.read_text();text=text[text.index('def dsh_observe('):text.index('def qualify(')]
    assert 'adapter._launch_argv(' in text and 'adapter._boundary(' not in text
    assert "launch.count(_APPARMOR_ENTRY) == 1" in text
    assert 'namespace_exit(status, observation)' in text
    assert 'deadline=budget.deadline' in text and 'pass_fds=(w,)' in text
    assert '20 if safety_only else 5' in text

@pytest.mark.parametrize('namespace_ok',[True,False])
def test_actual_safety_observer_uses_no_key_unique_entry_and_original_custody(tmp_path,monkeypatch,evidence,namespace_ok):
    import os, sys, time
    runtime,report=evidence
    home=tmp_path/'home';home.mkdir();folder=tmp_path/'dsh-safety';folder.mkdir()
    runtime=copy.deepcopy(runtime);runtime.update(workspace_root=str(tmp_path/'jobs'))
    runtime['dsh'].update(toolchain_root='/fixture/toolchain',cli={},patch={},native_files=[],key_name='FRIDAY_LLM_API_KEY',profile='headless',shutdown_seconds=2,tmp_bytes=100)
    runtime['dsh']['node']={'path':'/fixture/node'}
    report=copy.deepcopy(report);report['runtime_home']=str(home)
    boot=tmp_path/'boot';boot.write_text('fixtureboot')
    net=tmp_path/'net';net.touch();st=net.stat()
    def fake_path(path):
        return boot if str(path)=='/proc/sys/kernel/random/boot_id' else net if str(path)=='/proc/self/ns/net' else Path(path)
    pins=types.SimpleNamespace(read=lambda:b'fixture',path=Path('/fixture/node'))
    web=types.SimpleNamespace(profile='exa-keyless',trust_bundle=pins,checked_patch=lambda _:None)
    policy={'boot_id':'fixtureboot','net_namespace':[st.st_dev,st.st_ino],'document_probes':[]}
    calls=[]
    class Adapter:
        def __init__(self,cfg):self.config=cfg
        def _pins(self):calls.append('pins')
        def _launch_argv(self,row,root,control,limit,grant,command):
            assert grant=={} and root==folder and limit<=20
            calls.append('unique-launch')
            return ['/usr/bin/systemd-run','unused','/usr/local/libexec/friday-dsh-bwrap','--clearenv','--unshare-pid',*command]
        def _environment(self):return {'PATH':'/usr/bin:/bin'}
    def run(argv,cwd,**kw):
        calls.append('run')
        host=json.loads((folder/'inputs/host.json').read_text())
        assert type(host['pid']) is int and host['pid']==os.getpid()
        assert host['namespaces']=={k:'fixture-ns:/proc/self/ns/'+k for k in ('user','pid','mnt')}
        assert cwd==folder and kw['deadline']==budget.deadline and kw['timeout']<=20
        assert not any('KEY' in key for key in kw['env'])
        assert '/usr/local/libexec/friday-dsh-bwrap' in argv and '--clearenv' in argv
        assert all(any(x.startswith('--property='+key+'=') for x in argv) for key in ['MemoryMax','MemorySwapMax','TasksMax','CPUQuota','RuntimeMaxSec'])
        if namespace_ok:os.write(kw['pass_fds'][0],b'{"child-pid":77}\n{"exit-code":0}\n')
        return json.dumps(report),{'returncode':0,'reaped':True,'timeout':False}
    class StopUnconfirmed(RuntimeError):pass
    modules={
      'plugins.friday_rework.adapters.dsh':dict(DshAdapter=Adapter,DshHostConfig=lambda **kw:types.SimpleNamespace(**kw),_APPARMOR_ENTRY='/usr/local/libexec/friday-dsh-bwrap'),
      'plugins.friday_rework.host_runtime':dict(_pin=lambda _:pins,_dsh_web=lambda _:web),
      'plugins.friday_rework.worker_web':dict(web_policy=lambda *a:policy,DSH_NETWORK_PROBE='',checked_network_observation=lambda *a:None),
      'scripts.install_containment':dict(namespace_exit=lambda status,obs:namespace_ok and status.endswith(b'{"exit-code":0}\n'),checked_binary=lambda _:None),
      'scripts.dsh_prepare':dict(run=run,StopUnconfirmed=StopUnconfirmed)}
    for name,values in modules.items():
        module=types.ModuleType(name);module.__dict__.update(values);monkeypatch.setitem(sys.modules,name,module)
    fake_os=types.SimpleNamespace(**{key:getattr(os,key) for key in ['open','fdopen','fsync','pipe2','close','read','urandom','getpid','O_WRONLY','O_CREAT','O_EXCL','O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK']})
    fake_os.readlink=lambda path:'fixture-ns:'+str(path)
    ns=dict(q.__dict__,Path=fake_path,os=fake_os,time=time,json=json,DSH_SCOPE_GUARD='fixture-only-never-executed')
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('dsh_observe','dsh_safety_observe')]
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(SOURCE),'exec'),ns)
    deadline=time.monotonic()+100
    budget=types.SimpleNamespace(deadline=deadline,check=lambda **kw:deadline-time.monotonic()-kw.get('reserve',0))
    if namespace_ok:
        result=ns['dsh_safety_observe'](runtime,home,folder,budget)
        assert result['report']==report and result['execution']['resource_envelope']['deadline']<=deadline
    else:
        with pytest.raises(StopUnconfirmed):ns['dsh_safety_observe'](runtime,home,folder,budget)
    assert calls.count('unique-launch')==1 and calls.count('run')==1
