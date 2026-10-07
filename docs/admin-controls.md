# Native Friday administrative controls

This package prepares source/offline connections, without installation or live
product acceptance. Apply the exact `patches/hermes/admin-controls.patch` after
the published b44be05 composition, then install the trusted native Friday plugin
through the normal installation workflow. Its manifest binds the eleven changed
native source/test files. Older unpatched hosts retain ordinary workers and refuse the
unavailable administrative control capability.

The Dashboard exposes task status/pause/cancel, typed operational settings and
existing schedule pause/resume. Reviewed user access, pairing, history and
downloads retain their APIs. General environment, file, source, shell, PTY,
unaudited WebSocket and arbitrary RPC surfaces remain refused.

## Owning task control

The verified interactive native Session and opaque access token pass through the
existing protected local `gateway.sock`. One native verb invokes an owner-leased
callback in the existing PluginManager pointing to its already loaded WorkerHost.
It is not a slash command, new host, queue or task store. Native lease/unload
cleanup removes it. The native remote-plugin context explicitly refuses this
owning-process callback; unsupported host isolation cannot bypass the boundary.
Registration and each action require existing explicit
`allow_gateway_control: true` consent.

The existing gateway loop/executor dispatches into the callback's captured owner
context. The gateway's registered auth provider independently verifies the token
against launch-home operators, exact provider/user/org, expiry and configured
profiles. A Basic provider needs the same protected signing secret in both
processes; its random per-process secret cannot authenticate across them.
Missing/incompatible providers refuse. Caller-supplied identity strings are not
authority. Tokens stay in this local request, never task records/results/logs.

The current association supplies actual owner, native invocation, task/workspace
and original budget. The host's separate admin entry uses the existing `_stop`,
`_reconcile` and Controller paths; no Telegram receipt is fabricated. A retained
terminal row stays retained, pause never resumes execution, and cancel intent
cannot be cleared. Only actual cessation observation establishes quiescence.

Socket/executor-future deadlines are separate from stop completion. Unavailable
gateway, lost/malformed response or pending future returns `accepted: false`,
`execution: UNKNOWN`; stop may still be in flight. The UI sends one control call,
displays uncertainty and offers an explicit retained-state reload. It never
automatically repeats control, replays work, resets deadlines or claims cessation
from a timeout. Task rows expose the source capability; actual service authority
and availability are verified when acting.

## Protected typed settings

The settings API accepts current raw config SHA, a known kind and closed field
schema. Writes use native raw reads, managed-key refusals, the native cross-process
config/cache locks and `atomic_config_write`, then reread persisted data. Native
write/replace and administrative transactions share the existing reentrant file
lock implementation; the raw revision is rechecked immediately before commit.
An unrelated intervening native write causes refusal instead of replacement.
Arbitrary editors outside these native operations do not participate in the lock.
Private
ownership/mode, hardlink/symlink, stale SHA and session revocation/expiry are
checked. Existing unexpanded config/secret references survive; responses use
native structural/text masking. There is no credential reveal route.

- Models select an existing declared literal local `/v1` endpoint/model with
  compatible current capacity. Cloud/auto/fallback, unobserved model, inline key,
  arbitrary endpoint or invented context declarations refuse. New capacity or
  endpoint not already declared requires a reviewed native rebind. Inference is
  separate from web settings; active worker bindings/deadlines stay fixed.
- Web uses explicit Exa paid/keyless, bounded extraction, no provider rescue and
  no cache. It grants neither worker egress nor keys; mandatory retrieval cannot
  be disabled as a settings shortcut.
- Toolsets resolve native composites and disabled-set subtraction, including
  actual mandatory search/extract availability. Installed skills use native
  declared/load names, categories and duplicates; essential skills cannot be
  disabled. Enabling a duplicate preserves its peers' global/platform exclusions.
  No path/installation/inline shell/env input is accepted.
- Operational changes expose bounded `agent.max_turns` and boolean
  `streaming.enabled`, preserving the native streaming map and its precedence.
- Schedules use actual native cron list/get/pause/resume and exact existing ID,
  retaining native scope and rechecking authority inside the locked mutation.
  This does not stop/resume a running worker.

Effective model validation includes native defaults, environment expansion and
managed overrides; only raw references are saved. The temporary local profile
renderer explicitly routes every pinned donor auxiliary role locally. Existing
request/output guards and active execution budgets remain unchanged.

Responses say `PERSISTED_NEXT_NATIVE_SESSION_OR_RELOAD`, never claim a live reload
or alter active worker grants. The UI uses typed actual JSON APIs and rereads
after confirmed writes. Lost write acknowledgement remains unconfirmed without
auto retry. No restart, install, build or live effect occurs in this package.

## Evidence and remaining acceptance

Offline checks run actual native trusted router mounting, signed Basic/ASGI auth,
local-control protocol, owning loop, existing host/Controller, native persisted
config/cron readers/writers. Socket/ACL transport and native worker execution are
explicit synthetic fixtures. A joined API path discards an observed successful
stop response and verifies UNKNOWN, retained stop and no relaunch. UI checks run
shipped JavaScript and exact native fetchJSON bodies in finite Node VMs; React
hooks/elements and fetch responses are synthetic. No browser, real model/network,
socket bind, service, native worker or real key was used.

Independent review, final composition, normal installation/startup, current
production admissions and real two-user browser/worker/config application remain
required. Ordinary cross-user recall/memory/files/tools isolation is a linked
prerequisite; profile routing alone does not provide it. Both intact workers need
mid-task web retrieval. All six journeys in `mandatory-web-admin.md` remain
mandatory and NOT_RUN here. Historical stopped trials stay stopped.


The native configuration transaction now spans `save_config`'s raw read, merge
and commit. Plugin settings use that same path, preserving unrelated concurrent
administrative edits. Complete-state replacement APIs still mean an intentional
replacement; callers computing changes must hold the transaction across their
read and write.

Administrative schedule writes require the actual native cross-process lock;
timeout, missing backend or a nested degraded lock refuse before mutation. The
ordinary scheduler keeps its existing fallback behavior and API defaults.
Current administrator authority is checked inside the locked mutation.

Skill enable checks the effective global and platform denials. The native skill
catalog also reads the existing managed overlay, so its policy applies outside
the WebUI. Typed edits use the native deny-name normalization and display/load
matching, preserving essential-skill exemptions and disabled duplicate peers.
The reader retains its prior tolerance for nonmapping `skills` sections while
applying managed policy; enabling cannot acknowledge a remaining effective deny.
Delegation config inherits the validated local parent route or names a declared
local route; remote, undeclared, command and fallback routes are refused before
config persistence. This validates configuration; it does not establish live
worker execution or final product acceptance.

Actual native `skill_view` now uses the catalog's effective normalized deny reader,
including managed/platform policy and the essential declared-name exemption.
Specific duplicate load-name denies remain effective; a directory alias for a
unique copy does not invent a load-name deny. Names and wildcard-looking values
retain native literal matching. The qualified plugin registry uses the same
reader and refuses before reading the registered skill or its linked files.
Local copy resolution retains its metadata reads; denial precedes content
serving, linked-file reads and preprocessing. Reader errors do not fail open.

Source fixtures cover actual catalog, aliases, typed enables, registry loads and
useful allowed content. The previously reported 34 loader failures are retained
as regressions. This repair still requires Astra's independent review and does
not establish installation, live policy application or six-journey acceptance.

The registered tool's native repeat-view cache also fingerprints the effective
normalized skill denial set. A global, platform or managed policy change evicts
that entry and re-enters the real loader; unchanged allowed policy retains the
existing useful dedup behavior. Eight actual registered-handler witnesses first
failed after disable and now form policy-change regressions. This cache change
does not erase content already delivered or change active worker budgets.

Repeat-view success now follows the real loader's copy resolution and current
policy/platform checks. Entries identify the owning profile, actual skill file
and qualified plugin registration. Short names and suffixes cannot alias a
different duplicate or plugin copy. Local category aliases retain dedup when
they resolve to the same authorized copy; each linked file has its own entry
after traversal and containment checks. Policy changes invalidate old entries
even when a denied request exits before lookup, so enabling reloads useful
content. Resolution retains the native local metadata reads; a denied plugin
is refused before its body is read. Source/offline collision, alias, reload and
task-boundary regressions do not establish live acceptance.
