"""Source adapter joining runner obligations to a future existing-host attachment.

There is currently NO supported gate-worker attachment in WorkerHost/Controller.
ExistingHostBoundary below is an explicit missing source interface, not an
installed native API. No fallback to DSH/A0, Popen, JSON, systemd, or native RPC.
Default refusal precedes all writes/launch/configuration. Even an implementation
of this interface is not authenticated by its Python type; only the integration
owner's out-of-band existing controlled host wiring can supply authority.
"""
from abc import ABC, abstractmethod
import json
import math
import os
from pathlib import Path

class AdapterRefusal(ValueError):
    pass

def need(ok, cause):
    if not ok:
        raise AdapterRefusal(cause)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

class ExistingHostBoundary(ABC):
    """Missing gate counterpart under existing host; methods are obligations.

    Must preserve actual association/slot, kernel scopes/exec/resource/child
    fences, original deadlines and exact-owned stop through reap; no creation
    from runtime input. Implementing these methods does not authenticate them.
    All observations must come from retained live host state, independently of
    worker-authored JSON. No implementation/factory/CLI binding is supplied here.
    """
    @abstractmethod
    def observe_retained(self, context):
        """Actual lock/fences/original-budget/owner/resource observations."""
    @abstractmethod
    def launch_retained(self, admission, job_ref, loader):
        """Fixed pinned worker only; retained loader/custody handoff BEFORE GO."""
    @abstractmethod
    def observe_closed(self, worker, job_ref):
        """Independent final resources/owned exact absence/reap/closure bytes."""
    @abstractmethod
    def stop_owned(self, worker, job_ref, original_hard_epoch):
        """Exact owned kernel subtree, original cleanup deadline, no general kill."""

class GateHostAdapter:
    """Original immutable admission joins; single launch and closure, no retries."""
    def __init__(self, *, contract, admission, loader=None, boundary=None):
        need(type(admission) is bytes, 'immutable_host_admission_required')
        self.contract = contract
        self._token = admission
        self._admission = contract.parse(admission)
        self.loader = loader
        self.boundary = boundary
        self._original_boundary = boundary
        self._retained_boundary = None
        self._job = None
        self._worker = None
        self._child = None
        self._launch_attempted = False
        self._closure = None
        self._closure_attempted = False
        self._stop_attempted = False
        self._failure = None

    def _attached(self):
        # A strict type rejects duck-typed JSON while retaining explicit warning:
        # source fixtures also implement it, and are NEVER real host authority.
        need(isinstance(self.boundary, ExistingHostBoundary), 'existing_gate_host_counterpart_UNBOUND')
        need(self.boundary is self._original_boundary, 'existing_host_boundary_replaced')
        self.contract.require_loader(self.loader)
        need(callable(getattr(self.loader,'verify_original_attachment',None)), 'concrete_retained_loader_attachment_required')
        need(self.loader.verify_original_attachment(implementation=self._admission['implementation'],
             binding={'binding_sha256':self._admission['binding_sha256'],'grant':self._admission['pins']['grant']}) is True,
             'original_retained_loader_attachment_changed')

    def _context(self, phase, worker=None, job=None):
        self._attached()
        self.contract.revalidate_inputs(self._admission)
        return self.contract.custody_context(self._admission,phase,worker,job)

    def _join_context(self, context):
        need(type(context) is dict, 'host_context_schema')
        phase = context.get('phase')
        need(phase in {'before_launch','before_materialize','immediately_before_launch','before_barrier',
                       'after_reap','worker_before_configure','worker_before_ready','worker_after_barrier',
                       'worker_before_closure','parent_cancel','parent_cleanup'}, 'host_phase_not_admitted')
        expected = self._context(phase,context.get('worker'),context.get('job'))
        need(canonical(context) == canonical(expected), 'host_original_admission_context_changed')
        worker,job = context['worker'],context['job']
        if worker is not None:
            need(type(worker) is dict and set(worker)=={'pid','start_ticks'} and
                 all(type(v) is int and v>0 for v in worker.values()), 'host_worker_type')
            need(self._worker is not None and canonical(worker)==canonical(self._worker), 'host_unowned_worker')
        if job is not None:
            if self._job is None and not self._launch_attempted and phase=='immediately_before_launch':
                self.contract.verify_job(job,Path(self._admission['output_root']),self.contract.digest(self._token))
                self._job=json.loads(canonical(job))
            need(self._job is not None and canonical(job)==canonical(self._job), 'host_original_JOB_changed')
        if phase in {'before_barrier','after_reap','worker_before_configure','worker_before_ready',
                     'worker_after_barrier','worker_before_closure'}:
            need(worker is not None and job is not None, 'host_worker_JOB_required')
        return expected

    def verify_retained(self, context):
        self._attached()
        need(self._failure is None, 'host_session_failed_no_replay')
        joined = self._join_context(context)
        value = self.boundary.observe_retained(json.loads(canonical(joined)))
        need(type(value) is dict and canonical(value.get('context'))==canonical(joined), 'host_observer_context_changed')
        for key in ('actual_exclusive_lock','kernel_read_scope','kernel_write_scope','kernel_exec_pins',
                    'kernel_child_fence','kernel_resource_limits','original_budget_enforced','retained_until_reap'):
            need(value.get(key) is True, 'host_obligation_unavailable:'+key)
        slot = self._admission['exclusive_slot']
        need(canonical(value.get('owner'))==canonical({'pid':slot['owner_pid'],'start_ticks':slot['owner_start_ticks']}),
             'host_original_owner_changed')
        need(self.contract.pid_start(slot['owner_pid'])==slot['owner_start_ticks'], 'host_owner_birth_absent')
        self.contract.resource_observation(value.get('resource_observation'),self._admission['resources'],
            joined['worker'],joined['job'],self._admission['approved_affinity'],
            configured=joined['phase']!='worker_before_configure')
        # Keep the checked actual owner available for emergency cleanup even
        # when later source, loader, grant or auxiliary reads fail.
        self._retained_boundary = self.boundary
        return json.loads(canonical(value))

    def launch_owned_source_worker(self, *, admission, job_ref):
        self._attached()
        need(getattr(self.loader,'actor',None)=='parent', 'host_parent_loader_required')
        need(self._failure is None and not self._launch_attempted, 'host_launch_consumed_no_replay')
        need(type(admission) is bytes and admission==self._token, 'host_original_admission_changed')
        c=self.contract; a=self._admission
        c.verify_job(job_ref,Path(a['output_root']),c.digest(admission))
        need(self._job is None or canonical(self._job)==canonical(job_ref), 'host_original_JOB_changed')
        self._job=json.loads(c.canonical(job_ref))
        self.verify_retained(self._context('immediately_before_launch',job=self._job))
        # One-way reservation BEFORE actual launch: exception/unknown never retries.
        self._launch_attempted=True
        try:
            result=self.boundary.launch_retained(admission,self._job,self.loader)
            need(type(result) is tuple and len(result)==2, 'retained_host_launch_identity_required')
            child,worker=result
            need(type(worker) is dict and set(worker)=={'pid','start_ticks'} and
                 all(type(v) is int and v>0 for v in worker.values()), 'host_worker_type')
            need(type(child.pid) is int and child.pid==worker['pid'] and
                 c.pid_start(child.pid)==worker['start_ticks'], 'host_actual_launch_birth_mismatch')
            need(callable(getattr(child,'poll',None)) and callable(getattr(child,'wait',None)), 'host_owned_child_handle_required')
            self._worker=json.loads(c.canonical(worker));self._child=child
            return child
        except BaseException as error:
            self._failure=type(error).__name__+':'+str(error)
            # Boundary retains launch ownership even when return is unknown.
            # No guessed PID/JSON/default process launch, and no repeated attempt.
            raise

    def attach_worker(self, *, worker, job_ref):
        """Controlled worker's original retained launch attachment; source-only.

        Existing host must transfer the actual capability; this method only joins
        it. A worker-created call cannot manufacture authority without boundary.
        """
        self._attached()
        need(getattr(self.loader,'actor',None)=='worker', 'host_worker_loader_required')
        need(not self._launch_attempted and self._worker is None, 'worker_attachment_consumed')
        c=self.contract;a=self._admission
        need(canonical(worker)==canonical({'pid':os.getpid(),'start_ticks':c.pid_start(os.getpid())}),
             'worker_attachment_actual_birth_mismatch')
        c.verify_job(job_ref,Path(a['output_root']),c.digest(self._token))
        self._job=json.loads(c.canonical(job_ref));self._worker=json.loads(c.canonical(worker))
        self._launch_attempted=True
        try:self.verify_retained(self._context('worker_before_configure',self._worker,self._job))
        except BaseException as error:
            self._failure=type(error).__name__+':'+str(error);raise

    def capture_worker_closure(self, *, worker, job_ref):
        self._attached()
        need(getattr(self.loader,'actor',None)=='parent', 'host_parent_loader_required')
        need(not self._closure_attempted and self._failure is None, 'host_closure_consumed_no_replay')
        context=self._context('after_reap',worker,job_ref);self._join_context(context)
        need(self._child is not None and self._child.poll() is not None and self.contract.pid_start(worker['pid']) is None,
             'host_exact_worker_not_reaped_absent')
        self._closure_attempted=True
        try:
            value=self.boundary.observe_closed(json.loads(canonical(worker)),json.loads(canonical(job_ref)))
            need(type(value) is dict and canonical(value.get('worker'))==canonical(worker) and
                 canonical(value.get('job'))==canonical(job_ref) and value.get('owned_obligations_observed') is True,
                 'host_actual_closure_observation_required')
            need(value.get('retained_until_reap') is True and value.get('exact_worker_absent') is True and
                 value.get('worker_reaped') is True and value.get('owned_children')==[], 'host_closure_unclosed')
            c=self.contract;a=self._admission
            c.resource_observation(value.get('resource_observation'),a['resources'],worker,job_ref,a['approved_affinity'])
            ref=value.get('closure_ref');need(type(ref) is dict and ref.get('path')==str(Path(a['output_root'])/'WORKER-CLOSURE.json'),
                                             'host_foreign_closure')
            closure=c.document(ref,'host_captured_closure')
            c.completion({'exit_code':self._child.returncode,'worker_reaped':True},closure,job_ref,worker,
                a['budget'],a['resources'],__import__('time').time(),True,[],
                trusted_resources=value['resource_observation'],approved_affinity=a['approved_affinity'])
            self._closure=canonical(value)
            return json.loads(self._closure)
        except BaseException as error:
            self._failure=type(error).__name__+':'+str(error);raise

    def stop_owned(self, *, worker, job_ref):
        """One retained exact stop, including uncertain launch; never replay."""
        # Exact-owned stop must not be withheld by a damaged loader/receipt,
        # expired useful deadline or failed admission revalidation. The original
        # already checked live owner retains custody, including UNKNOWN launch.
        need(self._retained_boundary is not None, 'retained_owned_cleanup_unavailable')
        need(not self._stop_attempted, 'host_stop_consumed_no_replay')
        if worker is not None:
            need(self._worker is not None and canonical(worker)==canonical(self._worker), 'host_unowned_stop_worker')
        need(self._job is not None and canonical(job_ref)==canonical(self._job), 'host_unowned_stop_JOB')
        self._stop_attempted=True
        value=self._retained_boundary.stop_owned(worker,self._job,self._admission['budget']['hard_epoch'])
        need(type(value) is dict and value.get('status')=='STOP_CONFIRMED' and
             canonical(value.get('worker'))==canonical(worker) and canonical(value.get('job'))==canonical(self._job) and
             canonical(value.get('original_hard_epoch'))==canonical(self._admission['budget']['hard_epoch']) and
             value.get('exact_owned_only') is True and value.get('pending_launch_settled') is True and
             value.get('owned_children')==[] and value.get('retained_until_reap') is True and
             value.get('exact_worker_absent') is True and value.get('worker_reaped') is True,
             'STOP_UNCONFIRMED')
        return json.loads(canonical(value))

def bind_existing_controller(controller, *, task_id, owner):
    """Concrete read-only mapping to existing public Associations.get.

    No prepare/submit/reconcile/stop/service call. Current Controller supports
    DSH/A0 only: using their existing launch for a gate checker would substitute
    a different worker topology, loader and trust boundary. Refuse explicitly.
    This function does not add or discover a new native method or auto-register
    a worker. A future reviewed controlled host change must replace this refusal
    with its real gate attachment before runtime use can be accepted.
    """
    owner_fields={'bot_id','user_id','chat_id','thread_id','message_id','session_id','session_key','profile'}
    need(type(task_id) is str and task_id and type(owner) is dict and set(owner)==owner_fields and
         all(type(v) is str and (v or k in {'thread_id','profile'}) for k,v in owner.items()),
         'existing_association_identity_required')
    need(controller is not None and not isinstance(controller,dict) and
         callable(getattr(getattr(controller,'associations',None),'get',None)), 'existing_controller_UNBOUND')
    original_owner=canonical(owner)
    row=controller.associations.get(task_id,json.loads(original_owner))
    need(type(row) is dict and row.get('existing_task_id')==task_id and canonical(row.get('owner'))==original_owner,
         'existing_association_owner_changed')
    need(row.get('stop_intent') is None, 'existing_association_stopped')
    deadline=row.get('deadline_unix')
    need(type(deadline) in (int,float) and math.isfinite(deadline) and __import__('time').time()<deadline,
         'existing_association_original_deadline')
    raise AdapterRefusal('existing_gate_host_counterpart_UNBOUND:Controller supports DSH/A0; no gate loaded-buffer/kernel/worker handoff')

def existing_host_source_status():
    return {'status':'UNBOUND','actual_existing_gate_attachment':False,'runtime_grant':False,
            'cause':'WorkerHost/Controller accept DSH/A0 only; retained gate boundary and interpreter handoff missing'}
