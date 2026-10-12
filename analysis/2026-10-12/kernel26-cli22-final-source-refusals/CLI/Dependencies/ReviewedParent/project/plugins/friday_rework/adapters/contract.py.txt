"""Small host/worker seam. These values are observations, not launch grants.

The host owns admission, original budgets, workspace selection, durable intent
and native supervision. Adapters do not authorize model-supplied paths or IDs.
No scheduler, executor, persistence layer or retry policy is defined here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol

from ..boundary import WorkBrief


@dataclass(frozen=True)
class VerifiedInput:
    """Host-staged immutable bytes, after provenance/path/size/hash checks.

    host_path and worker_path name the same verified bytes through the explicit
    job mount mapping. receipt_reference retains the original ingress identity.
    Constructing this value alone does not verify an input.
    """
    host_path: str
    worker_path: str
    size_bytes: int
    sha256: str
    receipt_reference: str


@dataclass(frozen=True)
class PreparedNative:
    """Harmless preparation, retained durably before an effectful submission.

    DSH: an owned DSH_HOME/workspace reference, never an invented session ID.
    A0: the actual pre-established context, with verified native persistence.
    The receipt also binds this reference to the original association/budget.
    """
    reference: str
    receipt_reference: str


@dataclass(frozen=True)
class NativeObservation:
    invocation_id: str
    worker_reference: str
    evidence_reference: str
    elapsed_seconds: float
    state: Literal["running", "completed", "failed", "stopped", "unknown"]


# The callback persists actual identity immediately, before waiting for output.
# A failed callback or retained stop intent requires native stop, never replay.
NativeObserved = Callable[[NativeObservation], None]


class WorkerAdapter(Protocol):
    """Calls run off the gateway event loop under the existing native boundary.

    association is the checked Associations row, not a tool argument. submit
    occurs once, after durable UNKNOWN. Disconnection/exception stays UNKNOWN
    until observe reconciles it; neither method may resubmit. None of these
    observations certifies goal verification, artifact integrity or delivery.
    """

    def prepare(self, association: Mapping, brief: WorkBrief,
                inputs: tuple[VerifiedInput, ...]) -> PreparedNative: ...

    def submit(self, association: Mapping, brief: WorkBrief,
               inputs: tuple[VerifiedInput, ...], prepared: PreparedNative,
               on_native_observed: NativeObserved) -> NativeObservation: ...

    def observe(self, association: Mapping,
                prepared: PreparedNative) -> NativeObservation: ...

    def stop(self, association: Mapping, prepared: PreparedNative,
             intent: Literal["cancel", "pause", "deadline"]) -> NativeObservation: ...
