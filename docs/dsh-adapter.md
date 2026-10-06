# Supervised Harness adapter

`DshAdapter` implements the existing `WorkerAdapter` seam. The host still owns
authenticated admission, original task identity and budget, workspace staging,
goal verification, artifact validation and delivery. These synchronous methods
run in the host's existing execution boundary off its gateway event loop.

The host constructs `DshHostConfig` in trusted code. It supplies an immutable
complete Harness payload, pinned Node/native files, a pinned reviewed headless
profile patch, private job root, explicit local key environment accessor and
an accessor that re-reads the checked durable association. Model arguments are
only `WorkBrief` content. There are no embedded deployment paths, model routes,
credential values or production defaults. Temporary inference test caps belong
to the supplied test profile, not the adapter.

Each checked association's workspace contains `workspace/`, `home/`, `inputs/`
and host-only `.dsh-adapter/`. The outer boundary maps only the first three to
`/workspace`, `/job-home`, `/job-input`; the controller's association store and
adapter control receipts are outside worker mounts. Inputs map explicitly to
`/job-input/verified/<name>`, with original ingress receipt, size and SHA checked
again. Source payload, toolchain and inputs are read-only. The complete native
automatic sandbox remains `workspace-write` / `ask`; no alternate runner,
backend selection or native policy patch is installed by this adapter.

The call sequence is:

1. `prepare(row, brief, inputs)` writes and fsyncs the brief, copied immutable
   inputs/profile, environment bootstrap and preparation receipt. It returns
   the actual owned DSH home, without launching work or choosing a session ID.
   A partial preparation failure requires reconciliation; it is not repaired
   silently. Repeated complete preparation returns the same checked receipt.
2. The controller persists `UNKNOWN` with `Associations.begin_submission`.
3. `submit` validates that durable row and retained intent again, then creates
   an exclusive fsynced per-job submission handoff before its one native launch.
   Replays and uncertain attempts never launch again. Actual InvocationID is
   retained immediately; the native opening session invokes the controller's
   callback before output waiting. The callback must persist actual native
   identity. Callback/storage failure stops the exact owned boundary and
   propagates failure while leaving the handoff uncertain.
4. `observe` reconciles the planned unit, actual invocation and retained native
   NDJSON; it never submits. Before the opening event it returns `unknown`
   with an empty worker reference until a real session is observed. A previously
   recorded actual native session is retained; preparation is never a session. The manager's
   host-only `ExecStopPost` receipt preserves actual invocation/exit fields
   after successful unit collection or a crash before identity persistence.
5. Persist cancel/pause first, then call `stop`. Cancel dominates a concurrent
   pause. A deadline stop requires the original deadline or retained consumed budget
   to have elapsed, including after wall-clock rollback.
   `NativeSupervisor` checks exact admission description, transient unit,
   invocation and cgroup boundary before stop and confirms quiescence after it.
   Mutable worker output or payload drift does not prevent the explicit stop.

The user-systemd unit uses the caller's existing exact unit identity, no restart,
`KillMode=control-group`, SIGKILL after at most two seconds, NoNewPrivileges,
at most 2 GiB / 400% CPU / 64 tasks, and the accepted 64 MiB temporary mount.
Native RuntimeMax is the smaller of remaining original deadline and unconsumed
original budget, minus the bounded five-second
launch RPC and shutdown allowance. Those allowances never replenish a budget.
Host networking is retained as in the accepted native component. Stopping the
client proves no remote inference cancellation; that remains explicitly unknown.

The reducer requires an actual opening session, correctly ordered native turn,
matched tool results, completed native turn and final record, together with
native successful exit and quiescence. Duplicate/malformed/truncated records,
disconnects and incomplete turns cannot become successful completion. A worker
completion observation still certifies neither goal nor delivery.

The finite verification package covers harmless full native sandbox controls,
actual native stop/deadline with detached descendants, ownership/invocation
refusals, durable UNKNOWN, callback failure, replay, expired/retained stop and
one real adapter coding fixture with an unchanged test failing then passing.
The private evidence binds exact source hashes and scopes of each observation.
Independent parent review of the new adapter and Hermes/Telegram integration
remain separate gates; this module does not enable the product handler.

Actual checked invocation identity is kept in memory before receipt writes.
Auxiliary receipts publish complete fsynced bytes with an atomic exclusive hard
link, followed by a directory barrier; existing files are never replaced. An
error after publication retains the original failure and uncertainty. All
post-launch/recovery persistence and callback failures attempt exact-owned stop
without first persisting or trusting damaged storage. The initiating exception
retains `stop_confirmed` and either `stop_observation` or `stop_error`; failed
cleanup adds `STOP_UNCONFIRMED` and never claims the boundary settled.

Stop recovery uses the checked association, private host control directory and
supervisor's exact planned-unit/admission/invocation checks. Missing or malformed
auxiliary/preparation receipts and changed launch pins cannot block retained
cancel, pause or expiry. Valid contradictory invocation identities, foreign
owners and foreign preparations remain refused. Stop recovery is read-only and
never repairs receipts or relaunches. Normal observation with corrupt storage
reports that error after attempting stop; UNKNOWN remains retained.

Every public call still requires a readable checked current association.
If Associations becomes unreadable during a call, cleanup uses its last checked
row. After a process restart with an unreadable store, the controller must keep
its own last checked association and use `NativeSupervisor.stop` as the existing
emergency boundary. The adapter cannot invent durable ownership or turn unreadable
state into admission. No shared storage API is changed.
