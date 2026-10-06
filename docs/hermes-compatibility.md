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
