# Durable native-worker associations

`plugins/friday_rework/associations.py` stores a small `associations.v1` document
through the real profile-scoped Hermes `PluginState.get/set` API. It starts no
process and provides no queue, scheduler, RPC transport or transcript mirror.
It is a metadata component, not a working supervisor or product acceptance.

All inputs come from the trusted host controller after gateway authorization,
workspace ownership and budget selection. The model's tool arguments remain
only the validated worker/brief/goal-check content. ContextVars alone do not
authorize any operation. No worker is yet admitted by `friday_work`.

The concrete metadata methods are:

| Method | Meaning |
| --- | --- |
| `claim(...)` | Associate the existing task/admission identity, original owner/destination, brief hash, workspace receipt, planned unique systemd unit and original budget/deadline. Returns the stored row and whether it was newly created. |
| `get(task_id, owner)` | Read only under the exact original owner/destination binding. |
| `get_for_control(task_id, principal)` | Resolve an authenticated new control message in the same bot/user/chat/topic/profile to the original record. The controller then uses its original owner binding; no destination/session is rewritten. |
| `begin_submission(task_id, owner)` | Persist `UNKNOWN` before the native external submission. Refuse stopped, expired or previously submitted work. |
| `attach_native(task_id, owner, native)` | Attach the observed systemd invocation ID and native worker session/context reference, retaining a concurrent stop intent. |
| `request_stop(task_id, owner, intent)` | Retain `cancel` or `pause`; cancellation cannot be downgraded. This records intent and does not acknowledge actual cessation. |
| `observe(...)` | Record a checked observation reference against the exact native identity and monotonic accumulated elapsed time; infer neither goal verification nor delivery. |

The planned unit identity is persisted before submission, so a crash before
the returned native session/invocation has been attached still has a resource
to investigate. Unit names are unique `friday-rework-worker-<32 hex>.service`
under an explicit `user` or `system` manager. They cannot be shared by distinct
tasks. The controller must verify the actual invocation, descendants and file
boundary before using it; a string in this store is not that proof.

One nonblocking OS file lock serializes compound read/modify/write operations
around the native atomic state API. Its directory must be private, owned and
not a symlink. Lock and existing native state aliases/hardlinks are refused.
The lock retains a tiny initialization marker: if the native document later
disappears, admission fails rather than treating the profile as an empty store.
Malformed state and native write failures propagate; no metadata is silently
discarded. Operators must reconcile lost state with actual owned resources.

The native writer fsyncs its temporary JSON file before replacement but does
not fsync the target directory. The component completes that directory fsync
after every native `set`, while the admission lock remains held, before returning
any mutation result. On opening the store it fsyncs the initialization marker
and then the data directory and all ancestors bottom-up. Repeating these
barriers also covers an earlier failed initialization whose directories or
marker now exist. Unsupported or failed fsync, a short marker write, native
file-write failure or rename failure raises; no returned external submission
grant is issued. A failure after replacement is uncertain: retain the actual
native document and reconcile it, never roll it back to `NOT_SUBMITTED`.

Every access validates the entire decoded `associations.v1` document before
reading, admitting or mutating a task. Its top-level and row fields are exact;
each map key must equal the retained existing task ID. Owner, workspace,
supervisor and native identity shapes are validated, and hashes must be 64
lowercase hex characters. Times and budgets must be finite nonnegative numbers,
not booleans; the original budget is positive and
`created_at_unix < deadline_unix <= created_at_unix + budget_seconds`.
Observed elapsed time may exceed the budget so late cessation evidence is not
erased. It cannot exist without a native observation reference.

`NOT_SUBMITTED` and `UNKNOWN` have no attached native identity or execution
observation. `OBSERVED` requires a valid native identity. Stop intent is only
absent, `pause` or `cancel`; it may coexist with any submission state so a late
identity cannot clear a stop. This component can only retain `NOT_RUN` for goal
verification and delivery. Admission hashes and scoped supervisor units are
unique across all rows, as are scoped invocation IDs and worker-kind/native
references. One malformed or conflicting old row blocks the whole document,
including unrelated new work. No field is repaired, coerced, discarded or
silently upgraded.

A duplicate admission returns the old task and grant, even if the caller offers
a fresh task ID or a larger budget. Conflicting content, owner or supervisor
under the same admission is rejected. The original deadline is never extended;
observed elapsed time never decreases. Deadline enforcement still belongs to
the native supervisor and must survive gateway loss. No clock-based check in
this component substitutes for that facility.

There is no automatic reset of `UNKNOWN`, pause or cancellation. If identity
arrives after cancellation, the host must immediately stop that real boundary.
If persisting stop intent fails, the host must still issue native stop from its
known identity, block further admission and retain evidence through the existing
recovery path. The store alone cannot make that guarantee. Explicit continuation,
quiescent handoff, final verification, staging, delivery and retention remain
controller integration work; no new resume semantics are invented here.

Focused controls include the two original P1 reproductions, whole-document
schema corruption, identity collisions, real native fsync/replace ordering and
injected marker/file/rename/directory failures. They trace and retain the real
writer's effects rather than replacing it with a successful stub. To run the
native controls, put the pinned Hermes checkout on `PYTHONPATH` and use its
prepared dependency environment with:

```sh
python -B -m unittest discover -s tests -p test_associations.py -v
```

The native cases explicitly skip if Hermes is unavailable; a skipped run is not
native acceptance. An existing private owned 0700 `FRW_ASSOC_EVIDENCE_DIR`
retains fresh fixture directories, failed native state and ordering receipts
for review; otherwise normal test cleanup applies. Fixtures use synthetic
clocks and metadata-only native identities. Real two-process admission/reopen
controls additionally verify original grants, `UNKNOWN`, cancellation, profile
and topic separation, and fail-closed deleted state.

No physical power-loss experiment or integrated product/worker/live admission
gate is claimed by these controls. Filesystem durability depends on the host's
successful fsync contract. Loss or deletion of the complete profile/marker
still requires external retained reconciliation evidence; a local sentinel
cannot prove a missing whole directory was previously initialized. Real
deadline execution, descendant stop, product crash recovery and Telegram gates
remain `NOT_RUN`.
