# Parent result inspection and delivery

This source candidate extends the existing Friday association and native Hermes
plugin APIs. It adds no task engine, transport, polling loop or worker replay.
The operator must explicitly enable `settings.results: {enabled: true}` in the
Friday plugin entry, as well as the existing native injection/work/delivery
capabilities. No deployed profile is changed by this source package.

After independently observed worker quiescence, one notification is reserved
durably before it is scheduled through native `PluginContext.inject_message`.
The added optional `expected_session_id` parameter pins the original parent.
Native dispatch refuses a replacement session after `/new`; the existing strict
turn fence also checks a reset after queuing. `SCHEDULED` means only accepted by
the scheduler. Only an authenticated parent inspection records `OBSERVED`.
An uncertain notification is retained without automatic resend.

The `friday_result` tool derives ownership from the actual native call and
session/profile context. Its reference and paths select owned content, not
authority. `list` enumerates bounded regular files in the quiescent DSH workspace;
`inspect` freezes a selected manifest into private staging and reads the checked
bytes. Absolute, hidden, escaping, linked, duplicate and oversized inputs are
refused. Files have stable names, lengths and hashes; later delivery rereads
those exact staged bytes. A retained manifest cannot be silently replaced.

`assess` records the original parent's judgment together with references to its
actual file reads. Its method is explicitly `parent_file_review`. Text previews
are limited to 4096 bytes; incomplete or binary previews cannot support PASS.
Execution completion or worker prose does not establish the goal. If the goal
requires a test or environment check the parent has not observed, it must record
UNKNOWN. This candidate does not yet capture executed-test evidence and does
not claim to complete coding/engineering goal verification. An assessment is
retained once before delivery; there is no automatic later upgrade.

`deliver` runs on the existing owned gateway-work API and uses the original
bot/chat/topic/reply binding. Each artifact is reserved as UNKNOWN before an
external await. Only a matching native acknowledgement establishes DELIVERED.
Explicit retries are allowed only after a proven pre-send rejection. A timeout,
cancellation, post-send exception or lost acknowledgement stays UNKNOWN; reload
or another call cannot silently resend it. Partial/stopped output and absent
goal checks remain explicit in the caption. Retrying delivery never starts DSH.

The paired native deltas distinguish preflight refusal from an exception after
entering document delivery, and preserve pending Telegram updates on a polling
conflict when `drop_pending_on_cold_boot: false` is configured. That policy stops
the conflicting consumer instead of entering a queue-dropping recovery path.
Default upstream behavior remains unchanged when the opt-in is absent.

Validation uses the real plugin manager, middleware, state, injection scheduler
and document API with explicit offline worker/Telegram fixtures. Actual Telegram
delivery, real model consumption, executed goal checks, A0 output binding,
restart/runtime gates and complete release acceptance remain NOT_RUN.
