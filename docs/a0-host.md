# Dedicated A0 host core — source/offline candidate

This candidate connects existing WorkerHost, Associations, A0Controller,
A0Adapter and NativeSupervisor to a scoped extension of the complete existing
runtime (`836c5753a2a2a0832a595c0fb678c1a35e6b6b32295a9d94b6805fbabfab1a7f`).
It does not install or enable A0. Source acceptance of launcher repair
`9b2a996ef3525d49798b8b082e4376b40aa4d0580682ade59f2038c082699214`
does not establish current native networking, deadlines or engineering readiness.

## Admission and original ownership

The DSH configuration and execution path remain supported. A separate strict
A0 runtime configuration contains the existing common runtime/home/workspace/
staging/cache/size/budget fields, `runtime_receipt`, and an `a0` object with
`runtime`, `launcher`, `docker`, `daemon_unit`, `policy` pins; the original
`git_metadata` descriptor (`source`, `manifest_sha256`); `owner_slot` (`astra` or
`sol`); a fixed list of at most sixteen safe `logical_name`/`media_type` output
pairs; and `capability: null` in immutable deployment configuration. A0
reserves its exact association and original clocks before an authorized host
producer supplies a capability. Missing current capability or ordinary DSH
readiness receipt cannot permit native preparation. Budget is an integer 30..1800 seconds.
The factory also verifies exact runtime-produced Docker/daemon/launcher paths.

A0 deployment receipt schema is `friday-rework.a0-runtime.v2`, with exact
configuration hash, current host/host-runtime/host-record/association/adapter/
native/config source hashes and pinned reusable independent deployment review.
Its evidence covers the reviewed native egress/deadline/stop/pre-UI-key mechanics;
it never pretends that this new job was already started and stopped. Current
capability schema is `friday.a0.host-capability.v2`: exact already reserved
immutable association, ORIGINAL acceptance triple, network descriptor and pinned
`friday.a0.host-current-route.v2` evidence. Each current-route proof binds
association, acceptance, network and runtime-source hashes with explicit current
route and namespace recheck observations. Every native preparation/API admission
still performs the existing current route/ownership check; receipt booleans are
not a replacement. The permanent product requires authorized web during BOTH
workers, separate from local inference. This temporary local-route descriptor
is the currently reviewed boundary, not a permanent web exclusion or permission
to loosen guards. Future provider access requires the parent's authorized donor/
host-mediated integration and actual complete-journey acceptance.

The ordinary `handle` path calls the trusted `WorkerHost.produce_a0_capability`
after retaining the row and verifying input bytes. `A0HostSession` first calls
the existing runtime's `prepare_route` under the original stop/budget callback.
It then observes
the pinned launcher's exact original request, current unit/invocation, daemon
PID/start/executable, held and reopened namespace identities, and nft semantic
readback. It inspects the expected bridge, obtains its actual immutable Docker
ID, refuses foreign members, and repeats the existing `Runtime.check_network`
consumer with the same original clocks. Only successful native observations
produce the private, once-written evidence and capability files. The producer
then calls `WorkerHost.attach_a0_capability(task_id, owner, pin)`. It reads that exact
row from the EXISTING Associations store; clocks cannot be predicted or changed.
The attachment validates under the existing admission lock, persists once, then
calls existing `schedule_gateway_work`. Duplicate same attachment does not
schedule again; conflicting attachment, foreign owner, stop, expiry, changed
config and restored host cannot dispatch. A lost persistence/scheduling
acknowledgement leaves the row reserved; no retry/recovery launch. Host status,
duplicate admission, stop and administrative reads use the same authoritative
row, never a new management database. No public model/worker tool exposes this
producer method. Old preclaim configuration, v1 receipt and v1 A0 row are
explicitly invalid; this candidate does not rewrite historical records.

The retained A0 artifacts now use the shared [result consumer](result-consumer.md)
for list, inspect, assessment and delivery; the join has offline verification.
**Per-row preparation/cleanup is a source candidate; qualification remains
NOT_RUN and `startup_health` retains its A0 refusal.** Preparation checks the
registered pinned dedicated unit, no active/foreign daemon or worker unit,
no old request/guard/rootless namespace, and the existing nonblocking runtime
lock. Before publishing or starting anything, the existing unit must report a
finite native RuntimeMax of at most the existing 120-second cap, bounded start
and stop timeouts, and the same unchanged resource/kill boundary. Their sum plus
the native submission allowance must fit the original remaining work time
with the existing 25-second cleanup reserve. The checked active-enter monotonic
timestamp must also fit that original deadline. The daemon's own native unit
therefore supplies pre-container expiry even if the gateway disappears.

The pinned development unit source does not declare RuntimeMax. An effective
unit reporting infinity is refused with `a0_route_native_deadline_unavailable`
before route publication or daemon start; actual native properties were NOT_RUN
in this source assignment.
This implementation does not set properties, replace/reload a unit, borrow a
historical permit or supply a coroutine as deadline proof. Qualification of an
actual supported native admission primitive remains an operator/integration
dependency, followed by independent gateway-down/deadline/stop controls.

For an admitted existing boundary, the host publishes one private exclusive
request with the real row's owner/nonce, original wall/monotonic/boot clocks,
association and deployment hashes, exact launcher/tools and separated endpoint
policy. Unsupported configured endpoint policy is refused; legacy addresses and
40960 capacities remain temporary test profile data. The existing launcher
still performs its native pre-dockerd policy checks. The runtime starts that
dedicated daemon once, retains its actual guard/invocation/PID-start/namespaces
and descendant sample, then creates one exact named/labelled bridge and retains
its immutable ID. The unchanged current-network/check-network/attach-once/
scheduler/result consumers follow. No keys, UI or model admission precedes them.
Independent source review and current native positive/negative/deadline/stop
gates, worker web and complete user journeys are still required. This source
change is not runtime acceptance or permission to repeat an earlier stopped phase.
Offline proof inputs and native interfaces are explicitly fabricated controls;
they never constitute production evidence or an enabled deployment.

The host samples wall time, monotonic nanoseconds and boot once before claim.
The producer passes that same stop/deadline check through Runtime construction
and the existing Git metadata reader. Each read-only Git command uses the
remaining time, with checks between commands and file-hash chunks. Stop-only
reconstruction remains available after the work deadline. Final Docker network
readback is followed by another guard/namespace/daemon observation before the
producer may publish current-route evidence.
The store persists that triple and the exact original wall deadline; claim
rejects future acceptance/current-boot mismatch. Duplicate admission returns the
original row. Runtime remaining time uses both original clocks and current boot.
Full plan identity/hash, association admission hash and Docker network immutable
ID are distinct fields. Actual create labels, unit Description/name and native
mapping use the association identity; no identity is fabricated from an intended
launch. Generation remains the single non-replayable attempt.

New `host.a0` v3 rows retain required route custody in the same locked document;
v2 records remain readable without migration and cannot acquire new route
custody. Deleting the route field from a v3 row is invalid. Acceptance, fixed output
selection, once-only current capability, one-way launch/created/key-timestamp/grant metadata and separate key
cleanup state. No second task store, scheduler, supervisor, queue or secret store
is added. The complete runtime plan and exact serialized plan pin are validated
when the row is read. One cached controller/session wins concurrent construction;
construction itself cannot launch. Input staging retains original ingress byte
checks and remaps only worker paths to indexed A0 upload names. Aggregate
input/output bounds honor the smaller configured file/total limit.

Route intent is durable before request publication, daemon start, sampling or
bridge create. Immutable observations and descendant history cannot be replaced.
Lost start/create acknowledgements may reconcile only the actually submitted
original request/guard and exact owned name/nonce/ID, never retry or adopt an old
route. An absent guard, interrupted sample, changed invocation, foreign network
member or remaining sampled process leaves STOP_UNCONFIRMED and capacity held.
Even an expired native daemon with a retained unremoved bridge needs explicit
reconciliation; stop never restarts it to erase evidence.

Pre-container stop is separate from never_submitted: cancel/pause, producer,
proof, attach or scheduler failure and restarted/expired rows use the same owned
route cleanup. It removes only the checked owned network/endpoint and stops only
the recorded exact daemon invocation, proving its cgroup and every retained
PID-start ceased before removing the exact request/guard. Private checked copies
of the original runtime/launcher retain stop authority after launch-only source
or policy drift. The Docker executable pin and native ownership still apply;
labels/hashes alone cannot create that authority. Cached actual ownership can
attempt stop after metadata damage, but cannot release a damaged store. All
quiescence variants require route cessation when route custody exists.

## Launch, keys and cessation

Only the existing Controller.prepare invokes launch. Bootstrap is effectful, so
A0Controller and the cached session handle errors even while NOT_SUBMITTED.
After private usr materialization, a trusted in-process hook resolves only
FRIDAY_LLM_API_KEY and FRIDAY_EMBEDDINGS_API_KEY from the active scope with the
same runtime home, prepares the original KeyMaterial before create/UI, retains
only its timestamp, and verifies ready. Keys never enter argv, Docker Env,
JSON records, hashes or logs. The bound runtime CLI cannot start without those
in-process hooks. RuntimeMax/stop reserve and the existing 120-second cap remain.

The created immutable ID is checked/cached before dependent metadata writes;
original stop intent is checked again before unit start. A checked NativeGrant
comes from actual container/unit/cgroup/daemon observations, not planned values.
Every bootstrap/task/log/file admission repeats the actual pinned existing route
check with original owner/wall/monotonic/boot equality and immutable network
membership. Historical phase evidence or a network boolean cannot authorize
another association.

After the Type=exec acknowledgement, finite checked native observations wait for
container Running/PID>0 under original wall/monotonic time and the existing
25-second cleanup reserve. Every startup command is capped by the remaining
original startup allowance. Keys, exact capability and fresh route are checked;
loss of the original unit/identity is an error. Each initial cgroup/PID-start
sample is cached in runtime ownership and the host BEFORE receipt I/O or daemon
observation, then carried into grant-based stop. Empty descendant checks cannot
erase earlier known samples. Creation/cancellation reconciliation retains the
checked actual CID even after startup allowance is withdrawn; stop is not
blocked by an expired launch budget.

Before the single bootstrap POST, the boundary performs a fixed bounded GET
`/api/health` using the original key material and native admission. Only an
observed connection-refused or HTTP503 is NOT_READY; key/route/native/parse/error
uncertainty stops. Git health body must be valid and error-free. This GET never
submits work or calls a model. Delayed readiness can succeed; never-ready,
cancel/route/key/parent errors use original stop, without another create/start/
bootstrap. Finite startup observation is distinct from model polling.

Combined stop checks exact container/unit identity, stopped/PID0, cgroup and
PID-start cessation before original KeyMaterial removal. Unit absence alone
cannot release an A0 launch reservation. Quiescence kinds distinguish an actual
combined grant stop, an in-process completed no-create attempt, and an exact
cached pre-grant container stop. Pending/uncertain create and incomplete sampling
retain reservation. Foreign ownership cannot acquire cached stop authority.
Native cessation and key cleanup are separate claims.

After restart, a valid retained grant yields a structurally checked stop-only
boundary: no HTTP, admission, new keys, fresh clock or POST replay. Docker binary
pin and actual container/unit/mount/image/invocation checks remain mandatory;
changed launch-only policy/readiness inputs cannot withhold owned stop. Lost
original KeyMaterial yields KEY_CLEANUP_RECONCILIATION_REQUIRED unless its earlier
removal was already retained. Invalid/missing grant descriptors, including an
unresolved pre-grant crash, yield STOP_UNCONFIRMED; the existing native timeout/
ExecStopPost is the external cleanup authority, not a reconstructed grant.

All host-owned PID/start observations, including later native boundary samples
and pre-grant cleanup samples, are retained in the same locked association row.
The host saves a pending marker before sampling and the complete sample before
acknowledging it. Restart restores this full history into the stop-only boundary;
a stopped container and missing cgroup cannot erase a still-live sampled process.
Missing legacy history, an empty history with a grant, or an interrupted sample
remain unknown. A fresh stop sample cannot replace missing earlier evidence.
These cases still attempt the owned container and unit stops, while retaining
capacity and keys until cessation can be confirmed. A damaged association store
likewise permits cached stop attempts but cannot yield a positive cessation claim.
No new store, keys, process launch, clock reset or automatic migration is added.

## Retained outputs and remaining join

`read_retained_result` is pure: exact association/preparation/context/container/
invocation/grant; fixed complete unique ordered selection; original
worker-response provenance plus byte hash; stable staged artifact hashes,
completeness and size limits. No keys, current network, worker restart or API is
needed. New result receipts include `worker_response_sha256`; missing fields in
old receipts are refused, never silently rewritten. Retained valid finished
output can reconcile after restart; expired/cancelled work still follows stop
intent. Worker response, model completion and exit status do not prove goal or
delivery.

The later `results.py`/`result_tool.py` restaging/fixture/assessment/delivery join
is explicitly outside this package. Those files and native overlays are unchanged.
Fixture candidate c3f7bdd remains PARTIAL and unaccepted. This core cannot claim
FRW-014 engineering acceptance, full result delivery or release readiness.

## Verification

New tests execute the real PluginManager/host/controller, real generated runtime
plan/create/unit argv, actual ownership/schema/native-container validators,
private synthetic KeyMaterial transaction, staging and pure reader. OS/native
route/kernel/container/unit/API observations are explicitly fake; original donor
API and native/DSH/store/control regressions are preserved. Tests cover producer-
consumer roundtrip, zero/one input and multiple outputs, original fractional
clocks/replay, cache construction race, status during submit, bootstrap/pre-UI/
post-create cancellation, stop-only restart/key loss, config/store damage,
foreign ownership, container stop uncertainty, route refusal and retained byte/
provenance/order/coverage mutations.

The bounded offline runner denies network, shell and external workloads; only
finite allowlisted Git commands in disposable private fixture repositories run.
Affinity is four CPUs, per-process AS 4 GiB/CPU 180 seconds/core 0; no aggregate
quota is claimed. The recovery extension uses two CPUs and a 2 GiB address-space
limit. Its damaged-store control retains the actual stop assertions and now also
requires unknown cessation, retained keys and no quiescence. New controls cover
initial and later live process observations, process-start mismatch, interrupted
writes before/after persistence, absent/empty/pending history and foreign or
malformed samples. Failed runner setup
attempts and corrected test errors are retained in evidence, not converted to
acceptance. Final full-gate source/test pins, process cleanup and exact local
commit are recorded in the protected manifest. Independent review and separately
authorized current native/negative/engineering/delivery gates remain required.
