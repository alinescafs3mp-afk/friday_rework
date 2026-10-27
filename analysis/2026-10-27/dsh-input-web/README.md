# DSH input paths and web-module visibility

A live coding task received five verified input files, but its prompt contained only host-facing filenames. The worker spent tool calls discovering the opaque paths under `/job-input/verified`. The source candidate now appends a deterministic inventory of worker paths, sizes and hashes. File content, host paths and ingress receipts are excluded. Preparation and its consumer verify the same rendered brief. Existing prepared tasks are not rewritten.

The same live task reported that the keyless web module failed to import. The renderer names `/payload/friday-web-keyless.mjs`, while the sandbox exposed its payload only at the original absolute path. A conditional read-only alias exposes the already pinned module at the required path. Other web profiles and existing mounts are unchanged.

The combined source passed 55 focused adapter/web tests. The real module loader reproduced `ERR_MODULE_NOT_FOUND` before the alias and loaded/registered the provider after it in a read-only, network-denied diagnostic. That is import validation, not live web-retrieval acceptance.

The coding attempt subsequently reached its configured per-request output limit. Native execution emitted `turn_end` with `max-tokens`, followed by its normal `final` record. The adapter accepted the failed turn but rejected that final record as malformed, preventing the existing parent notification path from running. The parser now records the end of a turn independently of success, accepts exactly one valid final record, and preserves `failed=true` and `completed=false`. It still refuses unmatched tool results, invalid text, duplicate finals and reopened turns.

The parser change passed 45 adapter checks, including three regressions. An independent replay of the actual 49-record stream and nine related controls passed. An isolated check of the existing host and notification consumer confirmed one notification for a failed, quiescent result and deduplication of the second attempt. No new notification mechanism was added.

These changes are published source and are not installed. The original attempt remains stopped and its failure evidence is retained. It produced no workspace files; Telegram received only text claiming an attachment, without the attachment itself. No user artifact or complete DSH, web or product readiness is accepted by this checkpoint. Permanent services remain running.
