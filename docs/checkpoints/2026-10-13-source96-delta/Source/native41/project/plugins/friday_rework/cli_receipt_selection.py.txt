"""Immutable actual UNKNOWN selection, native candidate commit and consumers.

Durable association remains UNKNOWN forever for each original CLI attempt.
Immutable native journals retain the original UNKNOWN and checked candidate.
DELIVERED is a current LIVE acceptance projection after actual direct boundary
return, actual durable method returns and closure. Restart never remints it.
"""
import copy
import hashlib
import json
import time

from hermes_cli.friday_native_state import require_commit_return


class ReceiptSelectionUnconfirmed(RuntimeError):
    pass


def _canonical(value):
    body=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
    if len(body)>65536:
        raise ReceiptSelectionUnconfirmed("immutable_original_receipt_page_quota")
    return body


def _selection(row,reference,number):
    result=row.get("result",{})
    matches=[a for a in result.get("artifacts",[]) if a.get("reference")==reference]
    attempts=result.get("deliveries",{}).get(reference,[])
    if len(matches)!=1 or not attempts or type(number) is not int or attempts[-1].get("number")!=number:
        raise ReceiptSelectionUnconfirmed("original_delivery_selection_not_current")
    if attempts[-1].get("state")!="UNKNOWN" or attempts[-1].get("receipt") is not None:
        raise ReceiptSelectionUnconfirmed("original_unknown_history_changed")
    return _canonical({"existing_task_id":row["existing_task_id"],"owner":row["owner"],
        "admission_hash":row["admission_hash"],"worker_kind":row["worker_kind"],
        "workspace_reference":row["workspace_reference"],"supervisor":row["supervisor"],
        "native":row["native"],"deadline_unix":row["deadline_unix"],"binding":row["host"]["binding"],
        "source_paths":result["source_paths"],"artifacts":result["artifacts"],
        "reference":reference,"attempts":attempts})


class OriginalReceiptSelection:
    def __init__(self,store,span,row,reference,number):
        if row["owner"].get("platform")!="cli":
            raise ReceiptSelectionUnconfirmed("not_original_cli_delivery")
        self.store=store;self.state_object=store.state
        self.directory=store._cli_directory;self.namespace=store._cli_namespace
        self.span=span;self.task_id=row["existing_task_id"];self.reference=reference;self.number=number
        self.body=_selection(row,reference,number)
        self.sha256=hashlib.sha256(self.body).hexdigest()
        self.unknown_history=_canonical({"schema":"friday.original-cli-unknown.v1",
                                        "selection_sha256":self.sha256,"selection":json.loads(self.body)})
        self.phase="UNKNOWN_SAVE_NOT_YET_RETURNED"
        self.unknown_return=None;self.commit_return=None
        self.candidate_body=None;self.candidate_journal=None;self.finished_at=None
        self.accepted=None

    def unknown_save_returned(self,returned):
        if self.phase!="UNKNOWN_SAVE_NOT_YET_RETURNED":
            raise ReceiptSelectionUnconfirmed("duplicate_unknown_save_return")
        commit=require_commit_return(self.state_object,returned,cutoff=self.span.end)
        expected=hashlib.sha256(self.unknown_history).hexdigest()
        if not any(x[0]=="unknown" and x[3]==expected for x in commit.journal):
            raise ReceiptSelectionUnconfirmed("immutable_unknown_history_not_durable")
        self.unknown_return=returned
        self.phase="UNKNOWN_SAVE_RETURNED"

    def observe_unknown_boundary_return(self):
        if self.phase!="UNKNOWN_SAVE_RETURNED" or time.monotonic()>=self.span.useful:
            raise ReceiptSelectionUnconfirmed("original_unknown_boundary_not_returned_before_send")
        self.phase="UNKNOWN_BOUNDARY_RETURNED"

    def begin_commit(self,store,span,row,reference,number):
        if (store is not self.store or span is not self.span or store.state is not self.state_object
                or store._cli_directory!=self.directory or store._cli_namespace!=self.namespace
                or self.phase!="UNKNOWN_BOUNDARY_RETURNED" or row["existing_task_id"]!=self.task_id
                or reference!=self.reference or number!=self.number
                or _selection(row,reference,number)!=self.body):
            raise ReceiptSelectionUnconfirmed("late_foreign_or_changed_original_receipt")
        self.phase="COMMIT_ENTERED"

    def prepare_candidate(self,receipt):
        if self.phase!="COMMIT_ENTERED":
            raise ReceiptSelectionUnconfirmed("candidate_without_actual_original_return")
        self.candidate_body=_canonical(receipt)
        self.candidate_journal=_canonical({"schema":"friday.original-cli-receipt-candidate.v1",
            "selection_sha256":self.sha256,"unknown_history_sha256":hashlib.sha256(self.unknown_history).hexdigest(),
            "receipt":receipt,"original_entry":self.span.entry,"original_deadline":self.span.end})
        return self.candidate_journal

    def save_returned(self,returned):
        if self.phase!="COMMIT_ENTERED" or self.candidate_journal is None:
            raise ReceiptSelectionUnconfirmed("receipt_save_return_without_candidate")
        commit=require_commit_return(self.state_object,returned,cutoff=self.span.end)
        old=require_commit_return(self.state_object,self.unknown_return,cutoff=self.span.end)
        if (commit.directory!=old.directory or commit.lock_inode!=old.lock_inode
                or commit.generation<=old.generation
                or not any(x[0]=="candidate" and x[3]==hashlib.sha256(self.candidate_journal).hexdigest() for x in commit.journal)):
            raise ReceiptSelectionUnconfirmed("native_candidate_generation_custody_or_history_changed")
        self.commit_return=returned
        self.phase="SAVE_RETURNED_NOT_WHOLE_ACCEPTED"

    def observe_finish_boundary_return(self):
        if self.phase!="SAVE_RETURNED_NOT_WHOLE_ACCEPTED" or time.monotonic()>=self.span.end:
            raise ReceiptSelectionUnconfirmed("candidate_store_boundary_closure_UNCONFIRMED")
        self.finished_at=time.monotonic()
        self.phase="CANDIDATE_BOUNDARY_RETURNED"

    def validate_accept(self,lease,final,at):
        from hermes_cli.friday_cli_return import require_final_boundary_return
        if (lease is not self.span.guard or self.phase!="CANDIDATE_BOUNDARY_RETURNED"
                or require_final_boundary_return(self.span,final) is not final
                or not self.finished_at<=final.returned_at<=at<self.span.end
                or self.span.stop.is_set() or self.span.errors):
            raise ReceiptSelectionUnconfirmed("original_final_return_commit_closure_not_accepted")
        require_commit_return(self.state_object,self.commit_return,cutoff=self.span.end)

    def accept(self,lease,final,at):
        from hermes_cli.friday_cli_guardian import AcceptedDelivery
        self.validate_accept(lease,final,at)
        accepted=AcceptedDelivery(lease,self,self.candidate_body,self.commit_return,final,at)
        registry=getattr(self.state_object,"_native_cli_acceptances",None)
        if registry is None:
            registry={};self.state_object._native_cli_acceptances=registry
        key=(self.task_id,self.reference,self.number)
        if key in registry:
            raise ReceiptSelectionUnconfirmed("duplicate_native_delivery_acceptance")
        registry[key]=accepted
        self.accepted=accepted;self.phase="LIVE_ACCEPTANCE_PENDING_LOCAL_CLOSE"


def project_row(store,row):
    result=copy.deepcopy(row)
    if row.get("owner",{}).get("platform")!="cli" or "result" not in row:
        return result
    registry=getattr(store.state,"_native_cli_acceptances",{})
    for reference,attempts in result["result"]["deliveries"].items():
        if not attempts:
            continue
        number=attempts[-1]["number"]
        accepted=registry.get((row["existing_task_id"],reference,number))
        from hermes_cli.friday_cli_guardian import AcceptedDelivery, OriginalGuardianLease
        if type(accepted) is not AcceptedDelivery or type(accepted.lease) is not OriginalGuardianLease:
            continue
        try:
            accepted.lease.provider.binding.require("current_native_receipt_consumer")
        except Exception:
            continue  # current qualification loss never yields delivered credit
        selection=accepted.selection;span=selection.span
        if (selection.store is not store or selection.state_object is not store.state
                or accepted.lease is not span.guard or accepted.lease.phase!="CLOSED"
                or not span.completed or span.stop.is_set() or span.errors
                or span.owner.record_poison is not None):
            continue
        try:
            if _selection(row,reference,number)!=selection.body:
                continue
            receipt=json.loads(accepted.receipt_body)
            if receipt["state"] not in {"DELIVERED", "FAILED"}:
                continue
        except (KeyError,ValueError,ReceiptSelectionUnconfirmed):
            continue
        attempts[-1].update(state=receipt["state"],receipt=receipt)
    from .results import delivery_state
    result["delivery"]=delivery_state(result["result"]["deliveries"])
    return result
