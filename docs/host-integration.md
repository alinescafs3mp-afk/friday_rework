# Hermes host integration candidate

The source component passed independent review on 2026-10-07. The final ownership
correction passed 118 affected checks, including a real retired-thread ID reuse
case; the earlier 488-check review remains evidence for unchanged dependencies.
All eleven native repository checks passed, and seven overlays reconstruct the
58 affected Hermes files exactly. The integrated repository's 380 checks passed.
The upstream report checks use an owned host temporary directory: an unmapped
namespace ancestor and a shared writable runner directory were correctly refused.
No production guard was relaxed. These are component checks; runtime admission,
actual host-to-worker execution and product acceptance remain separate.

On 2026-10-07 at 02:49 MSK, the first actual local Hermes → Harness coding
scenario completed in 26.76 seconds. The native agent admitted one worker,
Harness read the supplied bytes through `/job-input/verified`, repaired the
calculator and returned a diff. The host staged the returned files and ran the
unchanged owner tests in a separate read-only sandbox. An independent check
confirmed the original failed and the actual returned file passed. Ninety-three
live worker samples were retained; all four sampled worker process identities
and the outer process ceased. This used the temporary local test profile
(context 40960, output 4096) and synthetic Telegram ingress. Actual Telegram
delivery, the production goal-verification consumer and release acceptance
remain unverified. The reproducible input and checker are in
[`fixtures/host-repair`](../fixtures/host-repair/README.md).

`register(ctx)` registers the same three-field `friday_work` tool, the existing
post-admission hook and native tool middleware. It adds native registered
`/friday-stop [reference]`, `/friday-pause [reference]` and
`/friday-status [reference]` when the admitted command API exists. There are no
load-time workers, threads, timers, network calls or workspace writes. A0 remains
unconfigured. Older Hermes without authenticated command context refuses worker
admission. In-process plugin loading is required by these native capabilities.

## Explicit runtime configuration

An operator supplies `plugins.entries.friday_rework.settings.runtime`, and
separately opts in to native `allow_gateway_work` and `allow_gateway_control`.
No config or readiness evidence is shipped enabled. `host_runtime.check_runtime`
checks the complete mapping; `dsh_binding` constructs the accepted `DshAdapter`
and `NativeSupervisor` directly. There is no dynamically selected callback,
command, executor or alternative adapter. The model sees only worker, brief and
goal_check. It cannot select a runtime profile, key name, path, budget or unit.

The runtime object has exactly these fields:

| Field | Operator-owned value |
|---|---|
| `enabled` | Explicit `true` only after parent admission. |
| `runtime_profile` | Native owning profile, matched to ingress. |
| `runtime_home` | Exact canonical owning Hermes home, compared to both native home and secret-scope provenance. |
| `workspace_root`, `staging_root` | Existing canonical private mode-0700 directories with disjoint worker/state/staging boundaries. |
| `cache_roots` | Exact native received-file cache directories. |
| `budget_seconds` | Original host grant, positive integer, at most 86400. |
| `max_file_bytes`, `max_total_bytes` | Actual configured input limits; adapter file limit remains at most 16 MiB. |
| `dsh` | Exact `DshHostConfig` mapping below. |
| `runtime_receipt` | `{path, sha256}` of operator-reviewed runtime evidence binding. |

`dsh` requires `payload_root`, `toolchain_root`, `node`, `cli`, `patch`,
`native_files`, `key_name`, `profile`, `memory_bytes`, `cpu_percent`, `tasks`,
`shutdown_seconds`, `tmp_bytes`. `node`, `cli`, `patch` and each nonempty
`native_files` entry are `{path, sha256}` pins. The profile is `headless`;
resource maxima are unchanged from the accepted adapter. `key_name` selects only
that named key through Hermes's scope-aware secret getter. Key values are never
persisted. A missing scope, foreign scope home or missing scoped key refuses
submission even when an ambient process key exists. The factory preserves native
environment context across the existing executor boundary.

The readiness receipt is a small operator-authored admission record, not a new
test runner or a self-certified worker result. Its exact fields are `schema`
(`friday-rework.dsh-runtime.v1`), `ready` (`true` after review),
`runtime_sha256` (host_record.digest of the complete runtime except
`runtime_receipt`), `adapter_sha256` (exact accepted dsh.py) and `evidence`
(nonempty array of `{path, sha256}` references to actual reviewed runtime
evidence). Every reference is read and checked before new admission. The parent
must establish the semantics of that evidence; a matching hash alone is not
proof of readiness. Test receipts explicitly identify offline fixtures.

## Owned dispatch and recovery

The existing PluginState association holds the full native
task/session/turn/API-request/tool-call tuple, original matched ingress, complete
brief, selected runtime and original grant. The `native-<sha256>` address is a
deterministic reference to that tuple plus ingress; it is not a separate task ID
system. Native task_id remains equal to session_id. Original native receipts and
delivery routes are never replaced with a later message.

The existing association lock serializes admission and reserves one effectful
worker. Legacy associations without quiescence proof also hold capacity. Job and
staging directories use that deterministic address. Actual stamped input bytes
pass through `stage_inputs`, and the complete size/hash/host/worker mapping is
retained before scheduling. A changed, missing or unproved input refuses the
dependent work, leaving the failed admission inspectable and non-replayable.

Hermes `schedule_gateway_work` owns the finite coroutine. Blocking controller
and adapter calls use the existing loop executor; no pool or daemon is added.
Controller preparation and durable UNKNOWN still precede native effects. The
native adapter's systemd RuntimeMax enforces the original deadline independently
of this coroutine. The coroutine only reconciles actual native observations,
with at most one observation per second until the original deadline. It never
relaunches work. Worker completion is distinct from host goal verification and
delivery, which remain `NOT_RUN`.

Exact duplicates return the retained association. Restart/status reads the
retained config and reconciles only: it never restages, prepares or submits.
Unsubmitted interrupted setup needs explicit cancellation; it is not silently
resumed. Auxiliary receipt loss retains the one-way preparation marker and
uncertainty. A submitted UNKNOWN with no observed native session conservatively
holds capacity even if its planned unit is absent; it cannot prove that a
concurrent launch RPC has settled. No automatic uncertain replay is provided.

Stop/pause is persisted before worker control. Pending stop succeeds without
creating a preparation receipt or unit. Cancellation dominates pause. Native
quiescence is retained separately from immutable first-terminal execution truth
and the worker's untrusted final text. Removing launch files cannot prevent
the fallback exact-owned native supervisor stop. Unload registers explicit
worker cleanup in addition to owned-coroutine cancellation; a cancelled Future
alone is never considered proof of stop. Cleanup uses the existing executor
when unload runs on its loop, and logs `STOP_UNCONFIRMED` on failure. Native
deadline remains the independent final bound during gateway shutdown.

Threads using the same owned association store serialize short metadata sections
before its existing nonblocking flock. Unload and coroutine cancellation therefore
cannot mistake their own metadata contention for a competing writer. The flock
still refuses another store/writer; neither lock covers native worker calls.
There is no lock retry or scheduler delay to make cancellation pass.

After an authenticated recovered status call checks ownership, a failed read or
settlement commit attempts exact-owned emergency stop using the checked invocation,
even with no scheduled coroutine. Cleanup annotates and preserves the initiating
exception; failure is explicitly `STOP_UNCONFIRMED` in the control response.
A failed durable outcome commit retains capacity and uncertainty, even when the
emergency native stop reports quiescence. Foreign control/runtime ownership cannot
be adopted through the cached cleanup rows.

## Control authority and remaining gates

Each registered command consumes its invocation-local native admitted receipt.
It matches bot, user, chat, topic, runtime and transport profile to the original
task. An explicit reference can address an old owned task after a new session;
without one, exactly one unresolved matching association must exist. Native
policy remains upstream of the command. Missing, foreign, revoked or absent
command context refuses control. The original result destination stays intact.

Built-in `/stop`, `/new` and reset aliases publish authenticated plugin control
receipts for idle/pending/active cases and are wired by this candidate. Ordinary
`on_session_end` is a turn-finalizer event and is not treated as cancellation.
Explicit continuation,
DSH↔A0 workspace handoff, A0 readiness, repository seeding, goal verification,
artifact selection and delivery are also separate product gates.

The native tests load the actual plugin with PluginManager, persist PluginState,
run real middleware and admitted ingress/control APIs, and schedule owned work
on the native gateway loop. The exact DSH implementation performs preparation,
submission-receipt ordering and native event reduction with an offline systemd
fixture. These controls do not claim a live DSH run, real descendant termination,
native deadline during gateway absence, remote inference cancellation, Telegram
delivery or end-to-end acceptance. Parent review and a real host run on the final
artifact remain mandatory.

Metadata lock acquisition uses one cumulative 250 ms budget, shared by association
thread locking, the native PluginState registry guard, per-path RLock, process
flock, and nested preparation/ingress reads and writes. This requires the native
`get/set(..., lock_budget=...)` extension; there is no legacy blocking fallback.
Timeout keeps durable capacity and the original error. Authenticated controls can
use an already checked cached row for emergency stop when metadata is unavailable;
foreign profile/transport/principal and expired command leases cannot use it.
Only acquisition intervals consume the allowance; native adapter/supervisor work
and filesystem I/O do not. Nested locks never replenish it. Its object refuses
cross-thread sharing and overlapping acquisition scopes without another lock.
The existing absolute `lock_deadline` and default blocking API remain supported.
Filesystem I/O itself is not made preemptible, and the job's original deadline
and grant are never extended.

The existing `friday-stop` registration binds native `stop` and `new` (including
native reset aliases). Original command, canonical native operation and registered
control command must agree. Builtin callback arguments are empty. No owned job
returns `None`, preserving the ordinary native reply; callback completion alone
never proves quiescence. Custom pause/status still use their existing handlers.
