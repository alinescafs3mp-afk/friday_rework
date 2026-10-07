# Native ordinary-user isolation candidate

This is an independently reviewed source/offline component for FRW026, not
installation or a complete two-user product journey. The final implicit-profile
repair passed 82 producer checks and 53 independent checks; earlier retained
grant and batch repairs remain separately pinned evidence. Apply the exact
`patches/hermes/user-isolation.patch` after main `6dc2eb0`; the manifest pins
every native input/output. Administrative execution controls remain a separate
candidate; their skill-loader/cache review is not accepted yet.

The capability is minted only after the original native principal admission
succeeds. It binds platform, receiving transport profile, configured account and
user to one exclusive runtime profile and its private native home. Chat, topic,
session, message and task identities remain separate. A channel `admin` role
does not become a signed Dashboard operator. The authoritative native admin API
keeps its intentional access to all configured conversations.

Native sync/async gateway profile scopes enter the capability before prompt,
history and tools. Cached memory/agents must retain the same principal, home and
binding; a new authenticated event from that same user remains useful. Memory
load/mutation/frozen prompt, history readers, native cwd/context files, agent
turn/API admission, registry, Tool Search, sequential/concurrent/inline tools,
and slash/quick/plugin command admission recheck it. Loss of execution context,
changed/disabled identities, copied capabilities, foreign profiles or changed
bindings refuse. Each admitted capability captures the user's durable native
PluginState generation. An enabled-to-disabled transition or product-role
change advances that generation under the existing cross-process write lock.
Later enable cannot revive idle memory, cached agents, copied contexts or
prepared dispatches, even when they did not check during disable. It does not
restart an old task, clear stop intent or reset a budget. No-op updates and
unrelated principals preserve their existing generations.

All Friday `product_access.v1` writes through native PluginState derive the
generation from the committed state; supplied stale generations cannot reset
it. Omitted users retain disabled tombstones, preventing delete/recreate from
reusing an old generation. Legacy six-field rows remain administratively
readable, but cannot mint retained authority until an explicit authoritative
native update assigns a generation. Missing or invalid retained generations
fail closed; deployment must reconcile existing jobs before that migration.
No extra user store, history mirror or task manager is added.

Scoped jobs retain the original principal and admission generation in their
existing association binding. Duplicate admission, actual start, active
reconciliation, A0 capability attachment and ordinary result access check that
retained authority. A fresh event cannot relabel an old job after re-enable.
Legacy ordinary jobs without that evidence fail closed for continuation/result
access, keeping their original rows, inputs, deadlines and stop intent for lead
reconciliation. Native administrative read-all and exact-owned stop remain
separate; no automatic task-budget reset or replay is introduced.

`tool_call` uses the actual advertised `calls` envelope and Hermes normalizer,
including legacy and tolerated JSON argument forms. The entire list is checked
before native expansion, then each real parser/dispatch rechecks the current
user and the retained agent. A mixed forbidden/nested/malformed batch cannot
execute its allowed prefix. Own deferred `friday_work` remains useful through
the original WorkerHost and native ingress/association boundary; source fixtures
queue an owned coding admission and close its coroutine before worker execution.

## Explicit native setup

Place protected policy and the existing `product_access.v1` PluginState in the
**receiving transport authorization home**. Add to Friday native plugin settings:

```json
{
  "user_isolation": {
    "enabled": true,
    "bindings": [
      {"platform":"telegram","transport_profile":"default","account_id":"actual-bot-A","user_id":"user-A","runtime_profile":"user-A","tools":["memory","session_search","read_file","write_file","web_search","web_extract","friday_work","friday_result"]},
      {"platform":"telegram","transport_profile":"default","account_id":"actual-bot-A","user_id":"user-B","runtime_profile":"user-B","tools":["memory","session_search","read_file","write_file","web_search","web_extract","friday_work","friday_result"]}
    ]
  }
}
```

Every runtime profile is unique; `default` cannot be a user runtime. Existing
native routing must resolve each authenticated principal to that exact profile.
The profile must also be explicitly admitted by the receiving account policy.
Missing/invalid bindings or a route to somebody else's profile deny admission.
Without `user_isolation`, the old source is still **unaccepted for ordinary-user
privacy**; it is not silently promoted by having `product_access` enabled.

`provision_new_home` is a trusted installation preparation primitive, never a
model tool or onboarding grant. It creates a **new** native profile with empty
memory/workspace and a private principal/binding marker. Existing homes refuse
adoption, so owner histories, secrets, arbitrary skills and context are never
cloned. Only explicit non-secret native model/tool settings are inputs; model
routes must be literal approved local addresses and `/v1`, with no cloud,
credentials in URLs or fallback. The product installer must supply the verified
Friday persona, explicitly scoped provider secrets and trusted plugin/worker
configuration through their existing protected paths. This source assignment
does not perform that installation or change any existing deployment profile.

## Data and useful actions

Native SessionDB remains the only history store. Before transcript/preview/FTS
access the exclusive home's native rows must all carry the same user, profile
and persisted receiving-account origin. Legacy, unknown, mixed or unreadable
stores refuse; current routing never relabels them. Inspection is bounded at
10,000 rows: a larger store is explicitly unaccepted until an indexed/budgeted
integrity join is reviewed, not partially searched. Own native profile links
remain usable; cross-profile links and caller-supplied foreign DBs refuse.

Memory uses the original MemoryStore and its native locking, limits, threat
scan, atomic writes and frozen prompt. Native profile/context and secret scopes
remain intact. Files use the existing `read_file`/`write_file` names with a small
descriptor-only local backend rooted in the user's private workspace. Relative
and absolute own-workspace paths work. Parent components, symlinks, hardlinks,
devices, loose/private foreign files, hidden paths and paths outside that root
refuse before reading or writing. Reads are bounded UTF-8 text; writes are
create-only and cannot replace an existing inode. No shell fallback is used.

Actual permitted functions are the explicit binding `tools` list, visible in
the existing administrator effective plugin settings. The intact donor catalog
is not erased: catalog visibility does not grant execution. Ordinary shell,
code execution, arbitrary MCP/connectors, native subagent/profile delegation,
config mutation and unreviewed file/skill/browser operations are refused. Safe
ordinary native commands are help/status/stop/cancel/new/reset/queue/memory.
This list is a declared **unaccepted capability gap**, not full donor acceptance
by feature exclusion. Coding/engineering stays on the existing `friday_work`
path into intact Harness/A0; result access uses the original checked
`friday_result`. Both joins additionally require the authenticated scope and
exact retained ingress account/user/runtime, preserving the original native
identity, inputs, budgets, stop and output checks. No new worker/queue/database
or unsupervised alternative terminal is created.

An authenticated native event may leave `SessionSource.profile` unset while
its pinned `RoutingIdentity` names the runtime profile. The native ingress
receipt keeps the serialized source profile (empty in that case); the existing
association owner keeps the runtime profile. Ambient-call ownership checks
the former and retained-job ownership checks the latter, while both retain
the same account, transport, user, native home and original grant generation.
Neither an implicit source profile nor the receiving `default` profile grants
another runtime. Original receipts, owners, deadlines and stop intents are
never rewritten to make the join pass. Source tests cover admission, original
start, duplicate, result inspection, notification and document delivery with
synthetic native-effect boundaries; they do not establish live acceptance.

## Required joins and remaining acceptance

The independent integrator must compose the minimal `host.py` insertion after
admin-controls' existing-host changes; this candidate does not import that
moving patch or change its worktree. `result_tool.py` adds the same scope check.
The native delta touches distinct files from the four generic admin-control
files. Apply against the manifest bytes, not a guessed donor version.

Remaining release blockers are explicit: normal protected per-user profile
onboarding/routing and plugin/secret/persona configuration; actual two-user
browser/channel/revocation journey; verified received-attachment staging into
ordinary read context (shared transport cache paths are not an ordinary grant);
indexed large-history integrity; reviewed existing-file CAS edits/search,
skill/provider/browser capabilities and any additional native inline surfaces;
full context/memory-provider and delegated-worker behavior on the final
candidate. Do not claim those from the bounded component tests. Activate policy
at a reconciled native boundary, keeping already admitted jobs on their original
owners/homes/budgets and preserving every pause/cancel/uncertain delivery.

Mandatory autonomous web remains required. Source tests exercise registry
dispatch with a clearly synthetic bounded transport, not retrieval acceptance.
Both real intact workers must discover a documentation gap mid-task, retrieve
through their scoped worker path, apply it and continue. All six complete owner
journeys remain NOT_RUN. Production inference stays on the configured local
endpoints with no cloud fallback; temporary test capacities are not deployment
limits. Astra owns independent review, final composition, installation and
release.


## Profile-specific worker preparation

The protected operator uses the existing signed dashboard API (same receiving
`profile`, exact identity, current native generation and config CAS) after
`/onboarding/prepare`. New endpoints are:

- `POST /onboarding/worker/prepare`: adds `worker` (`dsh` or `a0`), an explicit
  original `host_runtime.validate_runtime` configuration, and `a0_network` only
  for A0. This is a preparation input, never proof that its receipt exists.
- `POST /onboarding/worker/configure`: adds `worker`, the returned exact
  `preparation` pin, and the independently produced own `runtime_receipt` pin.
  This does not activate a user or launch a worker.

Both share `/api/plugins/friday_rework` and the original operator authentication.
No ordinary user/model tool can call either operation. The existing admin API
and config locks protect the receiving policy and private profile writes.
Templates remain nonsecret and cannot adopt an existing principal or home.

Use `runtime_home=<new user home>`, the same `runtime_profile`, and exact private
`<home>/workers/<worker>/{jobs,staging,cache}` roots. The own receipt path is
`<home>/workers/<worker>/runtime-receipt.json`; it is never created or copied by
preparation. Shared intact source/toolchain pins remain read-only; owner
receipts, writable homes, secrets, histories and capabilities are not shared.
All original runtime limit values are explicit and retained unchanged. The
Harness patch pin must describe the exact existing renderer output at
`<home>/workers/dsh/inputs/dsh-local.json`, using the profile's actual local
model/capacity and owned inference reference, with native paid Exa settings.
Wrong source/web pins or a different route/credential/receipt refuse.

For A0, `a0_network={name,endpoints,policy}` is explicit preparation data passed
to the original `LocalNetwork`/`local_profile` checker. Its current supported
contract still requires the original dispatcher and embedding routes on ports
8001/8002 and chat capacity40960/output4096. It is not a generic portable A0
installer. Native agent0/no-project settings and SearXNG/document-query contents
are retained as private preparation inputs, never installed into the worker.
The original native A0 key references are added to the same onboarding proof's
required names, so credential capture uses the existing protected writer. No
secret is read or copied during worker preparation. A0 live reconciliation and
per-job capability remain blocked and separate; kernel120 is not granted.

The returned `PREPARED_RUNTIME_UNOBSERVED` state has `enabled=false`. Partial
writes stay disabled and are not adopted on retry. For Harness, configuration
requires the exact own source/web/readiness receipt plus scoped keys and the
native grant. It remains disabled after `CONFIGURED_NATIVE_ACTIVATION_REQUIRED`;
only the original `/onboarding/activate` can admit the next authenticated native
request. The native WorkerHost and result tool recheck the user's retained
principal/generation, original budget, stop intent and ownership. Re-enable
cannot revive old jobs or grant access to their results.

This candidate is based on167154b842659ebd2da0bae0be036fb93a25f451, which includes
the exact prior product profile, user-isolation/onboarding/admin joins,
dashboard-owner and credential-admission overlays. Canonical integration must
compose these exact dependencies with Astra's separately moving native
installer/source manifest and independently verify the final bytes. No moving
installer, native launch module or host_runtime/adapter API is changed here.
Fixtures use actual native onboarding, grants, config, protected scopes,
PluginManager/middleware/WorkerHost/result admission and synthetic source/key/
review receipts. Worker scheduling is intercepted before execution. They are
not independent review, live acceptance or a runtime readiness producer. Both
workers' useful autonomous web, full authenticated admin and all six product
journeys still require their mandatory actual checks. Direct ordinary
skill/cron/terminal remains a separate explicit policy gap.
