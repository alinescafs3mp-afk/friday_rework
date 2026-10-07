# Friday_rework

Separate Hermes-based Friday implementation. Integration is under validation; no product acceptance or deployment is claimed.

Composition: pinned Hermes host, intact DeepSeek Harness coding worker, intact dedicated Agent Zero engineering worker, and verified Friday personality/Telegram deltas. Production inference uses explicitly configured existing local endpoints, with no automatic cloud fallback.

The legacy Friday checkout, runtime, data and Telegram consumer stay preserved. Publication target: `alinescafs3mp-afk/friday_rework`, branch `main`. Secrets, donor checkouts, runtime state and evidence are excluded from source control.

See `docs/foundation-status.md` for verified progress and current gaps. See `sources.lock.json` for the selected upstream identities and `docs/integration-boundary.md` for the implementation boundary. The existing owner task register remains authoritative; this repository adds no dispatcher or second backlog.
