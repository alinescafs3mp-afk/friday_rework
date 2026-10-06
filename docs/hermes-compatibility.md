# Temporary local context compatibility

`patches/hermes/bounded-local-context.patch` applies to Hermes commit
`781334eea4b9225a3e194faf0c241d9afe218634`. Its SHA-256 is
`a13d7b4fc469597cdaa5c4bd9c7139eade5adaca908b196288fa3aac0a61d465`.
`patches/hermes/manifest.json` also records every resulting changed file.
Upstream MIT and adapted Friday fixture notices are in `THIRD_PARTY_NOTICES.md`.

The change adds an explicit local TEST policy for a server whose real context
is smaller than the native 64K minimum. Without that opt-in, native defaults
remain unchanged. Routes and reservations come from the selected profile;
the patch does not install a model or enable cloud fallback. Main and summary
requests are checked against their final envelopes. Unsupported auxiliary
consumers fail closed under this temporary policy.

The current accounting uses conservative UTF-8 JSON bytes plus a template
reserve. It does not claim access to the server tokenizer. Current test
capacity is 40,960 tokens, with 4,096 main-output and 4,096 summary-output
reservations. These are temporary measured-environment choices, not future
hardware defaults. See `docs/local-test-profile.md` for profile preparation.

Apply only to a fresh, separately owned checkout at the exact base above.
Do not apply to the preserved legacy tree or mutate the pristine donor copy.
After checking the base commit, clean status and patch SHA, run
`git apply --check /absolute/path/to/bounded-local-context.patch`, then
`git apply /absolute/path/to/bounded-local-context.patch` from that owned
checkout. Compare all changed-file hashes and sizes against the manifest
before running it. An upstream update requires a new applicability check
and affected verification; the update observer never applies this patch.

Independent review accepted the repaired component after 452 affected and
dependent tests plus eleven repository checks. An earlier, unchanged scope
retains its separate test evidence. On 2026-10-06, the exact repaired source
and explicit test profile completed a native compression/tool scenario in
75.733 seconds: two compressions, two main calls, a real `session_search`
lookup by session ID, the correct final answer, and preservation of all 50
original persisted messages. Provider usage and conservative byte pressure
are separate observations.

The original failed runs are retained privately. Broad session search can
return oversized spillover that requires read tools absent from the minimal
test profile; this remains unresolved. Some operational logs/telemetry label
conservative accounting units as tokens, so those fields are excluded from
token-usage acceptance. Full host, worker, Telegram and release acceptance
have not run. These component results do not transfer automatically to a
different profile, tool set, model or source revision.

## Admitted message provenance

`patches/hermes/admitted-ingress.patch` is a separate delta against the same
pinned Hermes commit. Its exact hash and resulting files are recorded in
`patches/hermes/admitted-ingress-manifest.json`. It uses the same owned-checkout,
base/SHA/applicability and changed-file verification procedure above. Its files
are separate from the context patch; neither patch updates the other.

The existing post-authorization hook gains an optional plain ingress snapshot.
The native Telegram builder retains the original update ID; source identity,
receiving bot and current update must agree before the snapshot is supplied.
Unresolved or merged provenance produces no worker admission. Ordinary hooks,
including callbacks with the old argument list, retain their native behavior.
The existing message builder and channel prompt lookup are extracted into small
modules to respect the donor's code-health limits; no routing resolver or agent
loop is replaced. `docs/plugin-boundary.md` describes the consumer and the
remaining attachment, control, supervision and product gates.

The subsequent `bounded-file-transfer.patch` overlay adds bounded file receive,
received-byte identity and truthful document acknowledgement. Its manifest
specifies the prerequisite ingress patch and before/after hashes. Apply and
verify the ingress layer before this overlay. See `docs/file-transport.md` for
the input-staging contract and remaining live integration requirements.

## Authenticated plugin controls

`patches/hermes/gateway-controls.patch` follows the context, ingress, bounded
file-transfer and gateway work/delivery overlays in that order. Its manifest
pins every prerequisite and changed file. Apply only in a separately owned
checkout; compare before/after hashes as described above.

An in-process plugin may register a command with `gateway_control=True` after
its own profile explicitly grants `allow_gateway_control: true`. Both native
busy guards dispatch the control through the existing gateway executor.
`ctx.get_command_context()` exposes a detached, invocation-scoped snapshot of
the authorized originating bot, user, chat, topic and canonical profile. The
consumer must still match this proof against the original owned task. A valid
control does not grant a new worker, deadline, destination or workspace.

Missing provenance, revoked consent, shutdown, draining, handler failures and
unloaded registrations refuse recognized controls without passing their text
to the model or interrupting an unrelated agent. The native emergency-pause
policy remains in force. Retired names stay reserved in their owning profile;
another profile's ordinary command retains its meaning. The invocation proof
expires on completion, cancellation or unload. Process-isolated plugin hosts
cannot claim this gateway capability.

Independent component review verified 123 controls and the exact cumulative
five-overlay result: 47 affected files. The parent ran 155 affected native tests
and all eleven repository checks. These are offline component observations.
The concrete Friday consumer, built-in `/stop` and `/new` forwarding, live
Telegram authorization and actual worker cessation remain separate integration
and release gates. Registration or a control reply alone proves no stop.
