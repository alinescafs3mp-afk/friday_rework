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
