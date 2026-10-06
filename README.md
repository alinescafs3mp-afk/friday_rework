# Friday_rework

Separate Hermes-based Friday implementation. Foundation preparation only; no product acceptance or deployment is claimed.

Composition: pinned Hermes host, intact DeepSeek Harness coding worker, intact dedicated Agent Zero engineering worker, and verified Friday personality/Telegram deltas. Production inference uses explicitly configured existing local endpoints, with no automatic cloud fallback.

The legacy Friday checkout, runtime, data and Telegram consumer stay preserved. This repository has no configured publication remote. Secrets, donor checkouts, runtime state and evidence are excluded from source control.

See `sources.lock.json` for the selected upstream identities and `docs/integration-boundary.md` for the implementation boundary. The existing owner task register remains authoritative; this repository adds no dispatcher or second backlog.
