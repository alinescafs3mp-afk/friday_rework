# Friday administration foundation

This candidate is **source/offline only**, awaiting independent review. It is not a product installation or live acceptance. The six mandatory journeys in `mandatory-web-admin.md` remain required and NOT_RUN.

The plugin adds one tab to the intact Hermes Dashboard using its native manifest, React SDK, authenticated fetch client and supported Python router importer. It does not replace the TUI, copy transcripts, create an account database, launch a WorkerHost or add a scheduler. No build is required for the plain JavaScript plugin entry. `hermes dashboard` serves the UI; `hermes serve` is the separate headless surface.

## Native connection and trust

`patches/hermes/product-access.patch` is an additive patch against the exact accepted composed Hermes source `native-result-health/source`, upstream `781334eea4b9225a3e194faf0c241d9afe218634`, candidate tree `d51f3df83bb0bb468842b77682484e8974b0a825`. It adds the native policy reader and narrow checks in gateway authorization, authenticated REST continuation and the existing WS credential verifier. Existing authentication, native signing, cookie refresh, CSRF/origin checks and once-only WS tickets remain in their native paths. This does not upgrade the donor or change its supervisor.

The Friday plugin must be installed as an explicitly enabled, trusted **user or bundled** plugin. Project plugins cannot auto-import Python dashboard APIs. Its `dashboard/manifest.json` connects `index.js` to `api.py`; supported importer mounting provides `/api/plugins/friday_rework/*` and the existing native profile/secret dependency. Dashboard imports package definitions without calling the gateway's `register(ctx)`.

The policy's Dashboard authority always comes from the launch home, even while a request is scoped to another product profile. Every direct Friday API checks a verified native interactive `Session`, expiration, provider, user id and organization id against explicit configured operators. Display names, Telegram ids, channel roles, frontend flags and service-token principals are insufficient. Unconfigured/ordinary/foreign identities are refused. Profile query checks precede native downstream routing; routes also check the explicit configured profile set.

In the product administration profile unaudited native data/config/files/env-reveal routes are refused, including for operators; the scoped Friday APIs provide the first connected surfaces. Native public schema/theme/liveness/login paths keep their original protections. The native global profile switcher and other configuration pages have not been promoted to audited Friday controls; this plugin provides its own curated selector. WS tickets authenticate with the existing native verifier, then require the configured operator and a permitted profile before accept. Native tickets omit organization id, so this version supports ticket-based WS for explicitly organization-less operators; others are refused.

## Explicit native policy

Configure protected native Dashboard authentication first. These are plugin settings under `plugins.entries.friday_rework.settings`; they contain identity metadata, not passwords, tokens or a second set of credentials:

```json
{
  "admin": {
    "enabled": true,
    "operators": [{"provider": "basic", "user_id": "configured-operator", "org_id": ""}],
    "profiles": ["default", "engineering"]
  },
  "product_access": {
    "enabled": true,
    "accounts": [{"platform": "telegram", "transport_profile": "default", "account_id": "actual-bot-id", "runtime_profiles": ["default", "engineering"]}]
  }
}
```

Use actual native profile names and the actual receiving account identity. The configured account is uniquely identified by platform plus transport profile; the platform/account/user tuple remains separate from chat/topic, runtime profile, session id/key and parent lineage. Place access policy and metadata in the **transport authorization home**. A routed runtime cannot override its receiving transport's disable record. Other transports/platforms with equal user ids remain distinct. Historical rows without sufficient origin/transport evidence stay UNKNOWN.

Product access is an **intersection** with the original native grants, never a replacement grant. A current native `PluginState("friday_rework")` record under `product_access.v1` must explicitly enable the exact principal before native authorization can succeed. Pairing, wildcard, platform/global allow-all, groups, adapter roles and upstream relay grants cannot override disable. Missing/corrupt state or malformed policy denies product admission. With no enabled Friday policy, valid non-Friday native grant behavior remains unchanged.

The console edits the existing plugin metadata with the existing association metadata lock and native atomic state write, then a directory barrier and fresh read. A failed/uncertain write is not reported as effective success. Approval uses native PairingStore request ids, confirms its persisted native grant, then writes product access; partial approval retains uncertainty and does not replay. A channel `admin` role is metadata, **not** an implicit Dashboard operator grant; the Dashboard operator mapping is the actual privileged authorization boundary.

## Connected projections

- Users/accounts and pairing come from native policy, plugin metadata and PairingStore. Native request ids are used without returning pairing codes.
- Conversation metadata and paged messages come from read-only SessionDB calls. Title/id and indexed message search use native implementations. Exact platform/user/account/chat/topic filters apply to each bounded native page; an empty filtered page does not prove no later matches. Native raw session ids and lineage stay separate.
- Tasks come from the checked Friday association snapshot. Session/task joining requires exact native session id/key, bot/user/chat/topic/profile. Execution, submission, goal and delivery remain separate retained observations, with freshness explicitly marked. No new process-status or cessation claim is made.
- Received attachments require the complete admitted media/input mapping, exact bot/chat/topic/message or admitted reply origin, received size/hash and stable private staged bytes. Outputs use the existing verified result/artifact reader. APIs take a checked task reference and integer index; they accept no filesystem path. Missing, ambiguous, changed, hardlinked, symlinked or foreign ownership refuses download. Downloads are attachment-only octet streams with `nosniff` and no-store; native configuration/key filenames are excluded from output downloads.
- JSON responses use the native structural/text redactors plus password/credential-field coverage. Effective settings are masked **read projections**, not config changes. There is no credential reveal route or raw environment response.

The interface uses native SDK text nodes rather than HTML injection, explicit loads rather than polling, real API results rather than canned data, and authenticated downloads of the checked bytes. Browser/rendering and complete startup are NOT_RUN in this source assignment.

## Remaining mandatory integration

Ordinary channel admission is demonstrated; **ordinary-user recall/memory/file/tool isolation is not complete**. Native `session_search` can request other profile history, shared memory and generic terminal/file access retain their native policies, and an already admitted task is not cancelled by disabling a new-message principal. These are concrete release blockers, not proof supplied by DM separation or a hidden UI.

Task stop/cancel controls are explicitly unavailable. The next seam is an authenticated admin capability into the **existing owning gateway/WorkerHost**, retaining each actual owner, native identity, original deadline, stop intent and confirmed descendant cessation. Do not synthesize a Telegram command receipt, instantiate another WorkerHost or mutate task status to claim cancellation. A0 repair `14732d5` remains a separately reviewed parent input; this package does not integrate it or change its files.

Persisted operational config controls, tools/skills/cron/health pages, runtime model/endpoint rebind, normal protected installation/startup and complete two-user WebUI journeys still need parent integration and acceptance. Current inference endpoints/capacities remain temporary test backends; authorized web retrieval is a separate concern. Both real Harness and A0 must demonstrate retrieval during a running task, source application and honest unavailable/hostile-source behavior. All six owner journeys remain mandatory. Source tests, a manifest, a mounted router or a signed synthetic test session do not complete them.

## Evidence boundary

Tests run actual accepted native libraries plus the exact own patch against isolated synthetic native state: signed BasicAuth verification through the native REST stack, supported trusted router mounting, native once-only WS tickets, two users and wildcard/shared grants, persisted reload/enable/disable, native SessionDB/topic/message/search joins, native PairingStore, original association checks and actual received-byte staging. OS services, network sockets, models, workers, browser, real credentials and native/live journeys are not run. Final collection, JUnit, snapshot pins, resource observations, patch applicability and limitations are in the assignment's private evidence manifest. Parent review and changed native acceptance are still required.
