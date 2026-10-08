Ordinary registered `web_search` and `web_extract` now launch a fixed Python
entry through the existing ProcessRegistry. Model arguments and approved web
credentials are stdin data. They are absent from argv, the process environment
and the native checkpoint. Providers, schemas, explicit paid/keyless selection,
extract/cache/spill bodies and the full prepared donor remain native.

The sequential executor creates its original clock before submission. Parallel
calls share their original batch clock. Configured native `run_budget_seconds`
additionally caps web execution; disabling it does not invent an overall run
limit. Completed native approval wait exclusions are included at admission. After
admission the clock is fixed: later approval waits in the batch cannot extend
an already running service, so that case may time out earlier than the legacy
shared approval clock. Search,
SSRF DNS, headers, extraction, URL redispatch and settlement use that bound.
Four seconds are reserved for cessation, and startup has a separate three-second
reserve inside the same original budget. Less than eight seconds remaining
refuses admission. Results above the two-megabyte protocol cap or inputs above
64 KiB refuse explicitly instead of silently truncating native content.

A mandatory transient user service has an initial RuntimeMaxSec, a one-second
TimeoutStopSec, KillMode=control-group and SendSIGKILL=yes, with restart,
RemainAfterExit, delegation and runtime randomization disabled. Its invocation,
cgroup identity, activation time and effective policy are checked before input.
NoNewPrivileges and ProtectControlGroups are required. RuntimeMaxSec is set at
creation: systemd v259 accepts that service property only while the unit is a
stub, so changing it after activation cannot establish this deadline. See the
[upstream property setter](https://github.com/systemd/systemd/blob/v259/src/core/dbus-service.c)
and [runtime timer](https://github.com/systemd/systemd/blob/v259/src/core/service.c).
Actual deployment must qualify these observed properties and clock on its host;
version strings and source fixtures do not establish runtime admission.

Each existing checkpoint retains task, session, tool-call, turn, boot, original
clock, exact unit/invocation and cgroup identity. A child receives input only
after checkpoint readback and the turn/interrupt launch fence. Stop intent is
sticky across clear_interrupt. Success needs real exit zero and an empty or
removed original cgroup; parent EOF, wrapper death, Future cancellation and a
successful systemctl return alone are insufficient. Unknown cessation retains
custody, blocks subsequent web admission for that profile and returns
STOP_UNCONFIRMED. Gateway /stop and /new, CLI /stop and process.stop consume the
settlement status. Startup recovers retained handles without replay, including
intent with no live wrapper PID. An expired handle can close through read-only
observations of its pinned empty cgroup and positively gone/reused wrapper.

The child receives only declared web keys/endpoints from the active scope.
Callers require a retained explicit active scope, including an empty scope for
keyless operation. Native Friday scoped hosts already install it. Legacy
unscoped callers currently refuse; extending their admission requires binding
the existing native loader before the call, without unowned credential-command
effects inside the web adapter. This compatibility gap remains unresolved.
Ambient and sibling credentials are excluded. An env-only
legacy key is therefore not admitted as a profile credential. The benign
Parallel search-mode option retains its existing allowed values. Dynamic custom
providers must declare their credentials and be discoverable in the prepared
child; opaque parent-only provider objects are not transported.

SearchMemo remains in the parent across execs with profile/provider/query/bucket
identity, original TTL and bounded single-flight. Extract disk cache and spill
remain native. The dedicated child uses native scoped redaction before keyless
normalization, cache/spill persistence and result/cache transfer.

The offline fixture runs actual native handlers, ProcessRegistry, sequential and
parallel executors, and a scripted AIAgent SDK loop in real isolated children.
Only systemd unit/clock/cgroup metadata, DNS and HTTP/SDK responses are synthetic.
Its bwrap monitor reports namespace init and final exit; stop signals the owned
init through pidfd and verifies the complete monitor protocol. That establishes
fixture child cessation, not actual service/cgroup or provider acceptance.
Host service timers, gateway-down behavior, restart recovery across a real
process outage and installed live providers require separate runtime review and
qualification. Existing live/owner gates remain mandatory.

The source repair for independent review R01–R07 propagates retained custody
through ordinary, pending, chat/thread fallback and idle gateway stop paths.
Reset checks the same native handles before changing the durable conversation
or releasing its owner. Native process/CLI stop latches the existing call events
before settlement, including intent, Popen and checkpoint interleavings; the
checkpoint also retains that stop intent. Web handles carry the native routing
session key separately from the durable parent conversation ID. Recovered
handles are selected by profile and those identities, never by a global stop.
A successful web settlement counts once in native bulk-stop results; unknown
settlement counts zero. Approved managed endpoint readers use native profile
scope, and parent SearchMemo transfers sweep expired entries without renewing
TTL or replacing a held single-flight lock.

The source changes have passed Astra's independent acceptance. The ordinary
unbound CLI/direct-call, custom-provider, protocol-cap and later approval-clock
gaps above remain product gaps; they are not accepted exclusions.

The follow-up ordinary-stop closure includes retained caller custody together
with every authorized fallback run. Detached delegations are interrupted before
web cessation is observed, including pending sessions whose older delegations
carry only the durable conversation ID. An unknown receipt still retains the
session and owner. Concurrent settlement between a bulk-stop snapshot and its
native kill call contributes zero; a newly settled handle contributes one, and
unknown custody contributes zero without turning pending status into success.

On 2026-10-08, the prepared native21 source from repository commit
`5ffd614c99c5542c967d6c8f5b651cf1d99a5863` completed one real registered
`web_search` call using an empty explicit credential scope and the native free
Exa/keyless profile with cache and provider failover retained. The ordinary
ProcessRegistry launched the actual transient user service, verified its native
policy and clock, consumed a successful result linking to the official Python
asyncio documentation, and observed exit zero plus removal of the recorded
cgroup. The complete launcher took 3.75 seconds; separate observations confirmed
that the launcher, wrapper and service process had ended and the exclusive
execution lock was released. Active service observations showed a 1 GiB memory
limit, 64 tasks and RuntimeMax within the original call deadline. No model or
Telegram credentials were used.

This is live evidence for that registered search and its natural cessation. It
does not establish a normally installed candidate, autonomous model decisions,
delegated DSH/A0 research, extraction, outage/hostile-source behavior, explicit
stop, gateway loss or restart recovery. Those complete runtime journeys remain
required; existing offline controls and this observation do not replace them.
