# Hermes plugin boundary — FRW-008 component

`plugins/friday_rework/` is a native Hermes plugin directory. Install a reviewed
copy under the isolated home's `plugins/friday_rework/`, then opt in using
`plugins.enabled: [friday_rework]`. Import and registration start no worker,
thread, model, service or network request. No private registry is patched.

The single `friday_work` tool takes `worker` (`dsh` or `a0`), `brief` and
`goal_check`. Unknown fields, owner/destination/path injection, invalid text
and excessive text are rejected. The serialized text limits bound the tool
contract; they do not declare model context capacity. Additive native handler
kwargs are tolerated, and a supplied session ID must match bound native context.

Routing observations come only from the current native session ContextVars,
not model arguments or process environment fallback. They are observations,
not authorization. The supported `post_gateway_admission` hook persists a
bounded ingress receipt only after native authorization. A small Hermes patch
adds plain receiving-bot/update/routing/media provenance, using its existing
RoutingIdentity and native Telegram adapter. No raw SDK object, secret, message
text or live host handle enters that receipt. The tool handler independently
joins this receipt to bound session observations and the full native
`task_id/session_id/turn_id/api_request_id/tool_call_id` tuple. Its supported
`tool_execution` middleware always calls the native policy/handler chain and
clears its context in `finally`. CLI/cron, missing provenance and foreign
message/profile/topic contexts fail closed. Error results contain no route,
credential or brief.

An optional provenance provider failure yields no proof and preserves ordinary
post-admission consumers. Its warning omits exception text and traceback because
SDK errors can contain credentials. Cancellation still propagates. Nested tool
calls mask their parent's correlation before validation; unexpected validation
failures reach the handler with no proof. Native downstream exceptions propagate
once and restore the outer scope, following Hermes' existing middleware contract.

This source establishes registration, input validation and the ingress join.
A verified request still returns `accepted: false`, `worker_not_admitted`; an
unproved request returns `unproved_admission`. Only ingress receipts and the
existing association store initialization are persisted: no worker association,
queued receipt, workspace or execution is created. Enable the plugin only for
component checks until supervision and adapters are integrated. Native policy
refusal remains authoritative and never reaches worker execution.

## Shared adapter seam

Hermes remains the conversation/Telegram owner. Its profile-scoped `ctx.state`
is the selected existing durable store for small worker associations. Its
individual writes are atomic; a get/set pair is not a transaction or admission
lock. The reviewed Associations component serializes metadata with its existing
private admission lock and completes file/directory durability barriers.
The controller must record launch intent before effects. No parallel job database,
queue daemon or transcript store is introduced by this component.

The association maps the existing task/admission ID and originating authorized
session/destination to worker kind, owned workspace/artifact root, original
budget/deadline, native supervisor identity and actual native worker session.
Pause/cancel intent, uncertain submission, execution observation, goal check,
artifact verification and delivery receipt retain separate meanings. The
audited association contract remains the semantic authority; its worksheet
is not evidence of a running worker.

Astra owns this directory, admission, supervision and delivery integration.
Sol will own separate `adapters/dsh.py` and `adapters/a0.py` modules after a
specific assignment. Each adapter receives an already admitted association
and a validated brief; it maps submit/observe/stop to the intact native worker.
Model text cannot provide a command, unit name, writable path, deadline or
delivery route. Existing native process/container state determines observed
status; adapter responses cannot independently mark the goal verified or
delivery complete. The callable signatures are in `adapters/contract.py`: `prepare`, `submit`,
`observe` and `stop`. Preparation returns an actual native reference and a
durable evidence receipt. Before effectful submission the controller persists
that preparation and the original association, then records UNKNOWN.
`on_native_observed` attaches the real supervisor invocation and worker
reference immediately, preserving concurrent stop intent. DSH obtains its
session ID from the native opening event; A0 must already have a persisted
harmless context before `api_message`. Exceptions and lost responses are
reconciled, never automatically replayed. These signatures do not establish
adapter readiness.

No worker is admitted until its actual file boundary, deadline without the
gateway, descendant stop and recovery have passed. The observed user-systemd
mount-protection failure is therefore material to live admission. `/stop`,
idle/pending cancellation, attachment staging and Telegram delivery remain
separate integration work. Plugin discovery is not AC005/AC008 or release
acceptance on its own.

## Current provenance limits

The receipt records attachment origins separately from local cache references.
A single own/replied attachment can have a proved origin; ambiguous media
carries no origin. Coalesced events are denied until their producer retains
each original source. Cached paths are not yet worker inputs: bounded download,
actual byte/hash staging and explicit host/worker mapping remain required.
Busy-session steering and idle control messages do not traverse this native
post-admission fire-site; they cannot inherit an earlier worker admission.
These incomplete product paths remain release gates, not supported fallbacks.

Exact repeated receipts are idempotent. Another bot/update cannot replace the
same routed message. Receipt persistence uses profile PluginState under the
existing admission lock; invalid/corrupt state and failed directory barriers
do not authorize a worker. The native call ID is only batch-local, so the
controller must retain the full tuple and ingress identity before creating a
compact association address. No new independent task identity is invented.
