# Telegram integration boundary

Observed against Hermes `781334eea4b9225a3e194faf0c241d9afe218634` on 2026-10-06. These are native offline component observations and read-only route metadata, not Telegram product acceptance.

| Required behavior | Observed native support | Remaining work |
| --- | --- | --- |
| Russian text, fenced/inline code, angle brackets and ampersands, links with balanced parentheses, lists, table values, quotes | Eight finite renderer cases preserve the intended content | Verify actual Telegram display; no formatter port is currently justified |
| Uploaded or replied-to text file | Native cache returns matching bytes; identical filenames receive different paths | Bind authorized source identity and stage checked bytes into the actual worker workspace |
| Attachment size | Native document path checks declared metadata size | Check actual byte length: an offline case declaring 4 bytes with an 8-byte limit still cached 20 bytes |
| Chat/topic and sender | Native session context and authorization gates provide routing fields | Preserve the original authorized binding across worker completion, `/new` and delivery retry |
| External worker stop/reset | Native hooks cover some active agent transitions | Prove owned-worker stop for active, pending and idle associations; a host loop stop alone is insufficient |
| Result files and failed sends | Native delivery APIs and ledger exist | Stage verified immutable bytes; retry delivery without repeating execution |

Use `ctx.register_tool` and native session context. Model-provided chat IDs, paths and file identifiers are not authorization. `post_gateway_admission` runs after authorization, but this pin's payload does not contain media, bot ID, file ID or Telegram update ID. Those fields exist at the native Telegram handler boundary; any necessary join must retain their actual provenance. A plugin callback must use a narrow Friday prefix and validate the actual sender and original destination.

The existing `ctx.state` API persists profile-scoped plugin JSON using process/thread locking and atomic writes. Individual `get` and `set` calls do not form a compare-and-set transaction. Worker admission must retain a single owner and an atomic claim across the relevant association transition; do not infer that guarantee from a successful state round trip.

## Prepared bot cutover

The owner chose switching the existing bot after candidate verification and explicitly requires old Friday's backend and bridge to remain disabled and off. Read-only `getMe` and `getWebhookInfo` succeeded; at that observation there was no configured webhook and the pending-update count was zero. No updates were fetched or acknowledged, no messages were sent, and no consumer was started. These observations must be refreshed at the actual cutover boundary.

Before starting the candidate consumer, verify its reviewed profile and required component gates, the exact authorized bot/chat binding, and absence of a competing consumer. Inspect the pending-update count before selecting the native cold-boot policy. Preserve and reconcile pending input if present; do not silently replay uncertain old work or discard messages. Preserve stop intent and original task budgets independently of Telegram backlog handling.

Rollback stops the candidate and leaves old Friday off. Restarting the old services requires a new owner instruction. Actual inbound upload/reply, worker-visible bytes, real artifact delivery, stop/recovery and privacy scenarios remain **NOT_RUN**.

## Deployment debt recorded 22 October

The standard180 cold-start policy uses the existing explicit setting at each final configuration/start entry. Plain Hermes may regenerate90, and the outer ordinary-install start wrapper strips that setting. Use the documented [supported final-entry recipe](review-candidates/startup-policy-one180-installed96-20261022/README.md#standard-configuration-and-startup-path). Unifying those entry points remains deferred debt. The installed S120 handoff repair now has a supported ordinary start with exit0, generation **PASS** and `Type=notify` READY/active at 92.917672 seconds from process birth to active, with standard180/watchdog30. Source95 flush fixes, Source96 observations and the 267-file project identity remain intact. Configuration changes use the supported renderer; normal cleanup does not automatically restore90.

The authorized installed initial smoke produced persisted replies in 33.690 seconds initially, 5.026 seconds on a warm repeat and 4.069 seconds for a distinct contextual follow-up, measured from stored user input to durable assistant record in the same pre-restart conversation. The first and final observers were **EVIDENCE_READY**; the warm observer remained **STOPPED** at its 90-second cutoff (`poll_http`, `TRANSPORT_OUTCOME_UNKNOWN`) while raw-reply custody and persistence passed. A separate pre-send refusal is closed **STOPPED** with zero attempts and no reset/replay. Preserve the original READY92.135/generation **FAIL3** and recovery as closed historical evidence; no unique root cause is proved. Sol S123 independently accepted the observed initial native/reply/persistence/context smoke with zero open high/medium findings, checking answers against the original revised document. Full B00 and release remain **not accepted**; accepted web/incoming-document/public-caption work and B26 remain uninstalled, with next work unchanged.
