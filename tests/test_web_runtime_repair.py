"""R1/R2 regressions. Actual native PluginState + Associations, synthetic host.

No service/model/network grant is manufactured by these fixtures.
"""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_web_runtime_runner import prepared, M, OriginalTask, Refused, FakeNative, FakeBoundary, execute
from test_associations import Associations, AssociationError, OWNER, WorkBrief


def durable_boundary(plan, task, directory):
    from hermes_cli.plugins_state import PluginState
    class State(PluginState):
        @property
        def data_dir(self): return directory
    store=Associations(State('web-runtime-offline'), clock=lambda:1010.)
    if not directory.exists():
        original=Associations(State('web-runtime-offline'), clock=lambda:1000.)
        original.claim(task_id=task.task_id,admission_key='offline-original-research',owner=OWNER,
            brief=WorkBrief('dsh','synthetic research admission','offline regression only'),
            workspace_reference='offline-private-workspace',
            supervisor={'scope':'user','unit':'friday-rework-worker-'+'a'*32+'.service'},
            budget_seconds=task.budget_seconds,deadline_unix=task.accepted_wall+task.budget_seconds)
    class Boundary(FakeBoundary):
        consume=M['ExistingBoundary'].consume
        def __init__(self):
            super().__init__();self.associations=store;self.association_owner=OWNER
            self.current_association=lambda:store.get(task.task_id,OWNER)
        def admit(self,*args):
            self.row=self.current_association()
            return super().admit(*args)
    return Boundary()


def test_failed_publication_durable_consumption_and_read_only_redelivery(prepared,tmp_path,monkeypatch):
    plan,task=prepared;b=durable_boundary(plan,task,tmp_path/'admission');n=FakeNative()
    original_open=n.open
    def checked_open(*args):
        assert b.current_association()['submission_observation']=='UNKNOWN'
        original_open(*args)
    n.open=checked_open
    original=os.open;target=Path(plan['output'])/'observation.json'
    def fail_final(path,*a,**kw):
        if str(path)==str(target):raise OSError('synthetic final publication failure')
        return original(path,*a,**kw)
    monkeypatch.setattr(os,'open',fail_final)
    with pytest.raises(OSError,match='publication'):execute(prepared,n,b)
    assert n.opens==n.closed==len(n.runs)==1 and b.settles==1
    monkeypatch.setattr(os,'open',original)
    rec=M['recover'](plan,task)
    assert rec['final_response']=='synthetic answer [REDACTED]'
    assert rec['original_admission']['budget_seconds']==90.
    assert b.current_association()['submission_observation']=='UNKNOWN'
    assert M['recover'](plan,task)==rec
    # Deleting every delivery artifact does not recreate original authority.
    for p in Path(plan['output']).iterdir():p.unlink()
    reopened=durable_boundary(plan,task,tmp_path/'admission')
    with pytest.raises(AssociationError,match='reconciliation'):execute(prepared,n,reopened)
    assert n.opens==len(n.runs)==1
    with pytest.raises(Refused,match='no_stored'):M['recover'](plan,task)


def test_death_after_durable_consume_before_native_does_not_replay(prepared,tmp_path):
    plan,task=prepared;b=durable_boundary(plan,task,tmp_path/'admission');n=FakeNative()
    class Crash(BaseException):pass
    consume=b.consume
    def crash(*args):consume(*args);raise Crash()
    b.consume=crash
    with pytest.raises(Crash):execute(prepared,n,b)
    assert n.opens==0 and b.current_association()['submission_observation']=='UNKNOWN'
    with pytest.raises(AssociationError,match='reconciliation'):
        execute(prepared,n,durable_boundary(plan,task,tmp_path/'admission'))
    assert n.opens==0


def test_consumption_write_failure_never_opens_native(prepared,tmp_path,monkeypatch):
    plan,task=prepared;b=durable_boundary(plan,task,tmp_path/'admission');n=FakeNative()
    monkeypatch.setattr(b.associations.state,'set',lambda *a,**k:(_ for _ in ()).throw(OSError('synthetic write refused')))
    with pytest.raises(OSError):execute(prepared,n,b)
    assert n.opens==0


def test_existing_boundary_rejects_changed_original_row(prepared,tmp_path):
    plan,task=prepared;b=durable_boundary(plan,task,tmp_path/'admission')
    b.admit(plan,task,75)
    b.associations.request_stop(task.task_id,OWNER,'cancel')
    with pytest.raises(Refused,match='association_changed'):b.consume(plan,task)
    assert b.current_association()['submission_observation']=='NOT_SUBMITTED'


def test_deadline_crossing_retains_returned_tool_and_answer(prepared):
    plan,task=prepared;n=FakeNative();b=FakeBoundary();values=iter([110.,110.,186.])
    with pytest.raises(Refused):
        M['execute'](plan,task,b,native=n,mono=lambda:next(values),wall=lambda:1010.,boot='fixture-boot')
    record=M['recover'](plan,task)
    assert record['status']=='FAILED_OR_UNCERTAIN' and record['model_completed'] is True
    assert record['final_response']=='synthetic answer [REDACTED]'
    assert record['tool_source_observations'][0]['content']=='synthetic source [REDACTED]'
    assert n.closed==b.settles==1 and record['journey_acceptance']=='NOT_CLAIMED'


@pytest.mark.parametrize('failure',['exception','interrupt','close','settle'])
def test_durable_partial_during_run_and_uncertain_cleanup(prepared,failure):
    plan,task=prepared;b=FakeBoundary()
    class Partial(FakeNative):
        def observe(self,cb):self.cb=cb
        def run(self,prompt):
            self.runs.append(prompt)
            self.cb({'messages':[{'role':'tool','tool_call_id':'partial1','content':'observed SYNTHETIC_SCOPED_CREDENTIAL'}]})
            partial=M['recover'](plan,task)
            assert partial['status']=='RUNNING_OR_UNCERTAIN'
            assert partial['tool_source_observations'][0]['content']=='observed [REDACTED]'
            if failure=='interrupt':raise KeyboardInterrupt()
            if failure=='exception':raise RuntimeError('SYNTHETIC_SCOPED_CREDENTIAL')
            return {'completed':True,'messages':[],'final_response':'retained final'}
    n=Partial()
    if failure=='close':n.fail='close'
    if failure=='settle':b.quiet=False
    with pytest.raises(Refused):execute(prepared,n,b)
    record=M['recover'](plan,task)
    assert record['status'] in {'FAILED_OR_UNCERTAIN','CLEANUP_UNCONFIRMED','STOP_UNCONFIRMED'}
    assert n.closed==b.settles==1
    if failure in {'exception','interrupt'}:assert record['tool_source_observations'][0]['content']=='observed [REDACTED]'


def test_bounded_partial_redacts_before_truncation_and_valid_recovery(prepared):
    plan,task=prepared
    class Partial(FakeNative):
        def observe(self,cb):self.cb=cb
        def run(self,prompt):
            for i in range(40):
                self.cb({'messages':[{'role':'tool','content':'Я'*16000+'SYNTHETIC_SCOPED_CREDENTIAL'+'Z'*20000}]})
            raise RuntimeError('fixture')
    with pytest.raises(Refused):execute(prepared,Partial(),FakeBoundary())
    rec=M['recover'](plan,task)
    assert len((Path(plan['output'])/'observation.json').read_bytes())<1024*1024
    assert rec['observation_truncated'] and 'SYNTHETIC_SCOPED_CREDENTIAL' not in json.dumps(rec)
    assert rec['tool_source_observations']


def test_recovery_uses_original_identity_without_rechecking_expired_execution(prepared):
    plan,task=prepared;execute(prepared,FakeNative(),FakeBoundary())
    Path(plan['profile']['path']).write_text('profile no longer used after original run')
    assert M['recover'](plan,task)['model_completed'] is True
    changed=OriginalTask(task.task_id,task.accepted_monotonic,task.accepted_wall,900.,task.boot_id,task.plan_sha256)
    with pytest.raises(Refused,match='identity'):M['recover'](plan,changed)
    (Path(plan['output'])/'observation.json').write_text('{')
    assert M['recover'](plan,task)['model_completed'] is True


def test_native_callback_failure_requests_existing_interrupt_and_retains_failure():
    native=M['Native']();interrupts=[]
    native.agent=SimpleNamespace(interrupt=lambda reason:interrupts.append(reason))
    native.observe(lambda result:(_ for _ in ()).throw(OSError('synthetic disk failure')))
    with pytest.raises(OSError):native._tool_complete('call','web_search',{},'source observed')
    assert native.observation_failed and interrupts==['observation_persistence_failed']


def test_visible_native_partial_requires_real_consumer_evidence():
    native=M['Native']();native.secrets=('SYNTHETIC_SCOPED_CREDENTIAL',)
    native.agent=SimpleNamespace(_session_messages=[],_current_streamed_assistant_text='unobserved namespace')
    assert native.partial()['partial_response']==''
