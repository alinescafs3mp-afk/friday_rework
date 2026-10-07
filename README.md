# Friday_rework

Separate Hermes-based Friday implementation. Integration is under validation; no product acceptance or deployment is claimed.

Composition: pinned Hermes host, intact DeepSeek Harness coding worker, intact dedicated Agent Zero engineering worker, and verified Friday personality/Telegram deltas. Production inference uses explicitly configured existing local endpoints, with no automatic cloud fallback. Autonomous web retrieval, web access during both worker paths, and a working administrative WebUI are mandatory release capabilities; authorized web connectivity is separate from model routing.

The legacy Friday checkout, runtime, data and Telegram consumer stay preserved. Publication target: `alinescafs3mp-afk/friday_rework`, branch `main`. Secrets, donor checkouts, runtime state and evidence are excluded from source control.

See `docs/foundation-status.md` for verified progress and current gaps. See `sources.lock.json` for the selected upstream identities and `docs/integration-boundary.md` for the implementation boundary. The existing owner task register remains authoritative; this repository adds no dispatcher or second backlog.

See `docs/mandatory-web-admin.md` and `validation/acceptance-web-admin.json` for the owner's cumulative web/admin requirements and complete user journeys. These capabilities are not yet accepted.

[Donor capabilities and integration status](docs/donor-capabilities.md) distinguish planned, implemented, connected and verified functionality, including the mandatory web and administration journeys.
