# Accepted A0 network JSON roundtrip source correction

The protected worker preparer compared a newly derived endpoint tuple with a list restored from its JSON attachment. The values matched, but the strict equality check rejected preparation after the DSH input staging phase.

This patch converts endpoint URLs to a list at their producer, before persistence. Endpoint values, order and deduplication stay unchanged; the strict attachment, identity, policy and network checks remain. Models, endpoints, credentials, isolation and runtime limits are unchanged.

The accepted beforeimage SHA-256 is `63e5e502906183d5b035e2721ae720b67311b7a2026181d9f51a9e5841a62289`; the afterimage is `c0b731a8983f47f430a8135c0a91c9a65d04002e54872305996d6c4d83cf9894`. The complete candidate contains318project/47plugin files, with this single file change and no Native121 source delta.

Seventeen focused controls passed: the original tuple/list rejection, corrected roundtrip, endpoint order/deduplication, strict mismatch rejection and retained endpoint guards were checked. Existing evidence was reused; no full gate was repeated for this publication. The installed failure was separately diagnosed against actual current inputs and inert partial staging. The partial output and original refusal remain preserved privately.

This is a source archive against the exact beforeimage above. The repository file at publication base `7a303c0226524b1da7b3176195d74d2257458c64` has SHA-256 `ad10ba044308a0bcdf1697998a37fb33a8d3737025ea2a6e4e244dd3122a9cf2`; do not apply the archive as an unreviewed overlay. Installation, current services, worker execution, Telegram artifact delivery and contextual continuation remain separate facts. This publication claims no user result or full release.
