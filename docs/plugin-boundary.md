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
not authorization: the gateway's admitted message and actual bot/update/media
identity still need a trusted join. CLI/cron and unbound contexts currently
fail closed. No destination, credential or brief is echoed in error results.

This source establishes registration and input validation. Every valid request
currently returns `accepted: false`, `worker_not_admitted`. It does not create
a task ID, queued receipt, workspace, state record or pretend execution. Enable
the plugin only for component checks until the following integration is verified.

## Shared adapter seam

Hermes remains the conversation/Telegram owner. Its profile-scoped `ctx.state`
is the selected existing durable store for small worker associations. Its
individual writes are atomic; a get/set pair is not a transaction or admission
lock. FRW-010 must serialize admission using the existing owned execution
boundary and record launch intent before effects. No parallel job database,
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
delivery complete. Exact callable signatures will be added with the native
supervision implementation before adapter assignments, not inferred from
this descriptive contract.

No worker is admitted until its actual file boundary, deadline without the
gateway, descendant stop and recovery have passed. The observed user-systemd
mount-protection failure is therefore material to live admission. `/stop`,
idle/pending cancellation, attachment staging and Telegram delivery remain
separate integration work. Plugin discovery is not AC005/AC008 or release
acceptance on its own.
