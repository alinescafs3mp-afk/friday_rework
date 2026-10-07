"""Finite driver controls; synthetic native/host seams are explicitly labeled."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

Q = Path(__file__).resolve().parents[1]
M = runpy.run_path(str(Q / "validation/web_runtime.py"))
OriginalTask, Refused = M["OriginalTask"], M["Refused"]


def pin(p): return {"path":str(p), "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
def digest(plan): return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "source";root.mkdir()
    files = ["run_agent.py","agent/agent_init.py","agent/prompt_builder.py","agent/system_prompt.py",
             "agent/secret_scope.py","hermes_cli/runtime_provider.py","tools/web_tools.py",
             "tools/web_result_cache.py","plugins/web/exa/provider.py","plugins/web/keyless_mcp.py","hermes_cli/config_defaults.py",
             "agent/session_persistence.py","agent/tool_executor.py","tools/web_tools_truncate.py",
             "tools/tool_result_storage.py","hermes_logging.py","agent/redact.py","agent/agent_runtime_helpers.py",
             "agent/stream_delivery.py", "agent/chat_completion_helpers.py", "agent/conversation_loop.py", "agent/turn_context.py", "agent/turn_finalizer.py", "agent/turn_facade.py", "agent/turn_tool_round.py",
          "agent/message_sanitization.py", "agent/turn_recovery.py", "agent/turn_api_error.py", "agent/client_lifecycle.py", "agent/credential_pool.py", "hermes_cli/runtime_provider_custom.py", "agent/turn_truncation.py", "agent/bounded_context.py", "agent/coding_context.py", "tools/env_probe.py"]
    source_files = {}
    for rel in files:
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("# synthetic source pin\n");source_files[rel]=pin(p)["sha256"]
    home=tmp_path/"home";home.mkdir(mode=0o700)
    (home/"config.yaml").write_text("synthetic profile\n");(home/"SOUL.md").write_text("Friday fixture\n")
    workspace=tmp_path/"workspace";workspace.mkdir(mode=0o700)
    output=tmp_path/"output";output.mkdir(mode=0o700)
    plan={"task_id":"source-fixture", "mode":"ordinary", "source":str(root),"source_files":source_files,
          "profile":pin(home/"config.yaml"),"soul":pin(home/"SOUL.md"),"policy":pin(Q/"config/RESEARCH.md"),
          "driver":pin(Q/"validation/web_runtime.py"),"web_profile_source":pin(Q/"tools/web_profile.py"),
          "inference_endpoint":"http://127.0.0.1:8011/v1","web_profile":"exa-keyless","max_iterations":4,
          "workspace":str(workspace),"output":str(output)}
    return plan, OriginalTask("source-fixture",100.,1000.,90.,"fixture-boot",digest(plan))


class FakeBoundary:
    def __init__(self):self.admits=0;self.settles=0;self.quiet=True;self.consumed=False
    def admit(self, *args):self.admits+=1;return {"FRIDAY_FIXTURE_KEY":"SYNTHETIC_SCOPED_CREDENTIAL"}
    def consume(self,*args):
        if self.consumed:raise Refused('original_admission_consumed')
        self.consumed=True
    def settle(self, *args):self.settles+=1;return self.quiet


class FakeNative:
    def __init__(self):self.opens=0;self.runs=[];self.closed=0;self.fail=None
    def open(self, plan, secrets, remaining):
        self.opens+=1;self.remaining=remaining;self.env=dict(os.environ)
        if self.fail=="open":raise RuntimeError("synthetic native constructor failure")
    def run(self,prompt):
        self.runs.append(prompt)
        if self.fail=="run":raise RuntimeError("SYNTHETIC_SCOPED_CREDENTIAL")
        return {"completed":True,"api_calls":3,"messages":[
            {"role":"assistant","tool_calls":[{"function":{"name":"web_search","arguments":"{}"}}]},
            {"role":"tool","content":"synthetic source SYNTHETIC_SCOPED_CREDENTIAL"}],
            "final_response":"synthetic answer SYNTHETIC_SCOPED_CREDENTIAL"}
    def close(self):
        self.closed+=1
        if self.fail=="close":raise RuntimeError("synthetic cleanup failure")


def execute(prepared,native,boundary, **kw):
    plan,task=prepared
    return M["execute"](plan,task,boundary,native=native,mono=lambda:110.,wall=lambda:1010.,boot="fixture-boot",**kw)


@pytest.mark.parametrize("mode",["ordinary","explicit"])
def test_reaches_open_execution_close_and_settlement(prepared,mode,monkeypatch):
    plan,task=prepared;plan["mode"]=mode;task=OriginalTask(task.task_id,100.,1000.,90.,task.boot_id,digest(plan))
    monkeypatch.setenv("HERMES_ENVIRONMENT_HINT","POISON_POLICY_OVERRIDE")
    monkeypatch.setenv("OPENAI_BASE_URL","https://cloud.example/v1")
    monkeypatch.setenv("HTTPS_PROXY","https://proxy.example")
    before=dict(os.environ);n=FakeNative();b=FakeBoundary();record=execute((plan,task),n,b)
    assert n.opens==n.closed==b.admits==b.settles==1 and len(n.runs)==1
    assert n.remaining==75 and n.runs[0]==M["PROMPTS"][mode]
    assert "HERMES_ENVIRONMENT_HINT" not in n.env and "OPENAI_BASE_URL" not in n.env and "HTTPS_PROXY" not in n.env
    assert os.environ==before and record["journey_acceptance"]=="NOT_CLAIMED"
    assert record["owned_boundary"]=="REMOTE_SETTLED_PARENT_CGROUP_OBSERVATION_REQUIRED"
    text=(Path(plan["output"])/"observation.json").read_text()
    assert "SYNTHETIC_SCOPED_CREDENTIAL" not in text and "[REDACTED]" in text
    assert "tool_source_observations" in record and "final_response" in record


@pytest.mark.parametrize("where",["open","run","close","settle"])
def test_failure_retains_evidence_and_cleanup(prepared,where):
    n=FakeNative();b=FakeBoundary()
    if where=="settle":b.quiet=False
    else:n.fail=where
    with pytest.raises(Refused):execute(prepared,n,b)
    assert n.closed==b.settles==1
    record=json.loads((Path(prepared[0]["output"])/"observation.json").read_text())
    assert record["status"] in {"FAILED_OR_UNCERTAIN","CLEANUP_UNCONFIRMED","STOP_UNCONFIRMED"}
    assert "SYNTHETIC_SCOPED_CREDENTIAL" not in json.dumps(record)


def test_existing_observation_prevents_replay(prepared):
    n=FakeNative();b=FakeBoundary();execute(prepared,n,b)
    with pytest.raises(Refused,match="observation_already_exists_no_replay"):execute(prepared,n,b)
    assert n.opens==n.closed==b.admits==1


@pytest.mark.parametrize("mutate",["plan","profile","source","soul","policy"])
def test_exact_drift_refuses_before_admission(prepared,mutate):
    plan,task=prepared
    if mutate=="plan":plan["max_iterations"]=5
    elif mutate=="source":(Path(plan["source"])/"run_agent.py").write_text("# drift\n")
    elif mutate in {"profile","soul"}:Path(plan[mutate]["path"]).write_text("drift\n")
    else:plan["policy"]["sha256"]="0"*64;task=OriginalTask(task.task_id,100.,1000.,90.,task.boot_id,digest(plan))
    b=FakeBoundary();n=FakeNative()
    with pytest.raises(Refused):execute((plan,task),n,b)
    assert n.opens==b.admits==0


@pytest.mark.parametrize("endpoint",["https://api.openai.com/v1","http://localhost:8011/v1", "http://127.0.0.1/v1",
                                     "http://key@127.0.0.1:8011/v1","http://127.0.0.1:8011/v1?token=x"])
def test_cloud_or_ambiguous_endpoint_refused(prepared,endpoint):
    plan,task=prepared;plan["inference_endpoint"]=endpoint;task=OriginalTask(task.task_id,100.,1000.,90.,task.boot_id,digest(plan))
    with pytest.raises(Refused):execute((plan,task),FakeNative(),FakeBoundary())


@pytest.mark.parametrize("mono,wall,boot",[(186.,1010.,"fixture-boot"),(110.,1086.,"fixture-boot"),
                                          (110.,1010.,"different-boot"),(99.,1010.,"fixture-boot"),
                                          (110.,999.,"fixture-boot")])
def test_original_clocks_boot_no_budget_reset(prepared,mono,wall,boot):
    with pytest.raises(Refused):prepared[1].remaining(mono=lambda:mono,wall=lambda:wall,boot=boot)


def test_terminal_text_cannot_selfdeclare_acceptance(prepared):
    n=FakeNative();b=FakeBoundary()
    n.run=lambda prompt:{"completed":False,"messages":[],"final_response":"PASS all journeys"}
    with pytest.raises(Refused):execute(prepared,n,b)
    record=M['recover'](*prepared)
    assert record["model_completed"] is False and record["journey_acceptance"]=="NOT_CLAIMED"
    assert record['status']=='FAILED_OR_UNCERTAIN'


def test_existing_native_boundary_and_private_inherited_lease(prepared,tmp_path,monkeypatch):
    plan,task=prepared
    row={"existing_task_id":task.task_id,"stop_intent":None,"budget_seconds":90.,"created_at_unix":1000.,"deadline_unix":1090.}
    class Supervisor:
        # Synthetic systemd observation; actual parser separately reused below.
        def observe(self,row):return SimpleNamespace(quiescent=False,main_pid=os.getpid(),active_state="active",invocation_id="fixture",control_group=Path('/proc/self/cgroup').read_text().strip()[3:],unit="fixture.service")
        def _command(self,argv,timeout):return SimpleNamespace(returncode=0,stdout="RuntimeMaxUSec=1min 30s\nActiveEnterTimestampMonotonic=100000000\n")
    p=tmp_path/"existing-private-lock";fd=os.open(p,os.O_CREAT|os.O_RDWR|os.O_EXCL,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);s=os.fstat(fd)
        boundary=M["ExistingBoundary"](current_association=lambda:copy.deepcopy(row),supervisor=Supervisor(),lock_fd=fd,
            associations=None, association_owner=None,
            lock_pin={"device":s.st_dev,"inode":s.st_ino,"path":str(p)},scoped_credentials=lambda p:{"FRIDAY_FIXTURE_KEY":"synthetic"},
            verify_network_admission=lambda p,t:True,confirm_remote_quiescence=lambda p,t:True)
        assert boundary.admit(plan,task,75)=={"FRIDAY_FIXTURE_KEY":"synthetic"}
        assert boundary.settle(plan,task)
        fcntl.flock(fd,fcntl.LOCK_UN)
        with pytest.raises(Refused,match="inherited_exclusive_lock_not_held"):boundary.admit(plan,task,75)
        row["stop_intent"]="cancel"
        with pytest.raises(Refused,match="original_association"):boundary.admit(plan,task,75)
    finally:os.close(fd)


@pytest.mark.parametrize('value',['RuntimeMaxUSec=5min\nActiveEnterTimestampMonotonic=100000000\n',
                                 'RuntimeMaxUSec=infinity\nActiveEnterTimestampMonotonic=100000000\n',
                                 'RuntimeMaxUSec=90s\nActiveEnterTimestampMonotonic=200000000\n',
                                 'RuntimeMaxUSec=90s\nRuntimeMaxUSec=1s\nActiveEnterTimestampMonotonic=100000000\n'])
def test_native_deadline_cannot_extend_or_guess_original(prepared,value):
    plan,task=prepared
    row={'existing_task_id':task.task_id,'stop_intent':None,'budget_seconds':90.,'created_at_unix':1000.,'deadline_unix':1090.}
    group=Path('/proc/self/cgroup').read_text().strip()[3:]
    supervisor=SimpleNamespace(observe=lambda r:SimpleNamespace(quiescent=False,main_pid=os.getpid(),active_state='active',
                               invocation_id='fixture',control_group=group,unit='fixture.service'),
                               _command=lambda a,t:SimpleNamespace(returncode=0,stdout=value))
    boundary=M['ExistingBoundary'](current_association=lambda:row,supervisor=supervisor,lock_fd=-1,lock_pin={},
        associations=None, association_owner=None,
        scoped_credentials=lambda p:pytest.fail('credentials before native deadline proof'),verify_network_admission=lambda p,t:False,
        confirm_remote_quiescence=lambda p,t:False)
    with pytest.raises(Refused):boundary.admit(plan,task,75)


def test_admission_drift_rechecked_before_native_open(prepared):
    class Boundary(FakeBoundary):
        def admit(self,*args):
            Path(prepared[0]['profile']['path']).write_text('admission race\n')
            return super().admit(*args)
    n=FakeNative();b=Boundary()
    with pytest.raises(Refused):execute(prepared,n,b)
    assert n.opens==0 and n.closed==b.settles==1


def test_escaped_credentials_redacted_without_corrupting_json(prepared):
    value='synthetic-quote"-slash\\-credential'
    b=FakeBoundary();b.admit=lambda *a:{'FRIDAY_FIXTURE_KEY':value}
    n=FakeNative();n.run=lambda p:{'completed':True,'messages':[{'role':'tool','content':json.dumps({'value':value})}],
                                  'final_response':value}
    record=execute(prepared,n,b)
    assert value not in json.dumps(record) and value not in record['final_response']
    assert record['final_response']=='[REDACTED]' and '[REDACTED]' in record['tool_source_observations'][0]['content']


def test_profile_delta_pins_actual_native_auxiliary_rows_without_mutating_input():
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    build=runpy.run_path(str(Q/'tools/configure_local_test.py'))['build_config']
    initial=build(base_url='http://127.0.0.1:8011/v1',model='fixture-model',key_env='FRIDAY_FIXTURE_KEY',context=40960,
                  max_input=40954,main_output=4096,summary_output=2048,margin=1024,template_overhead=2048,web_profile='exa-keyless')
    before=copy.deepcopy(initial);result=M['validation_profile'](initial,DEFAULT_CONFIG)
    assert before==initial and result['model']==initial['model'] and result['web']==initial['web']
    assert result['agent']['environment_probe'] is False and result['agent']['coding_context']=='off'
    assert initial['agent'].get('environment_probe') is not False
    assert initial['agent'].get('coding_context') != 'off'
    for key,row in DEFAULT_CONFIG['auxiliary'].items():
        if isinstance(row,dict) and 'provider' in row:
            assert result['auxiliary'][key]['provider']=='custom:friday-local'
            assert result['auxiliary'][key]['base_url']==result['model']['base_url']
            assert result['auxiliary'][key]['model']=='fixture-model' and result['auxiliary'][key]['fallback_chain']==[]
            assert result['auxiliary'][key]['api_key']==''


def test_native_defaults_allowed_explicit_emitted_selection_cannot_drift():
    expected={'web':{'search_backend':'exa','cache_enabled':False},'toolsets':['web']}
    assert M['_emitted_options'](expected,{'web':{'search_backend':'exa','cache_enabled':False,'cache_ttl_minutes':20},'toolsets':['web']})
    assert not M['_emitted_options'](expected,{'web':{'search_backend':'auto','cache_enabled':False},'toolsets':['web']})
    assert not M['_emitted_options'](expected,{'web':{'search_backend':'exa','cache_enabled':True},'toolsets':['web']})
    assert not M['_emitted_options'](expected,{'web':expected['web'],'toolsets':['web','terminal']})


@pytest.mark.parametrize('missing', ['agent/turn_truncation.py','agent/bounded_context.py','agent/coding_context.py','tools/env_probe.py'])
def test_continuation_and_final_guard_pins_required_before_admission(prepared, missing):
    plan, task = prepared
    plan['source_files'].pop(missing)
    task=OriginalTask(task.task_id,100.,1000.,90.,task.boot_id,digest(plan))
    native=FakeNative();boundary=FakeBoundary()
    with pytest.raises(Refused,match='native_candidate_pins_incomplete'):
        execute((plan,task),native,boundary)
    assert native.opens == boundary.admits == boundary.consumed == 0
