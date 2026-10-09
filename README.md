# Friday_rework

Separate Hermes-based Friday implementation. Integration is under validation; no product acceptance or deployment is claimed.

Composition: pinned Hermes host, intact DeepSeek Harness coding worker, intact dedicated Agent Zero engineering worker, and verified Friday personality/Telegram deltas. Production inference uses explicitly configured existing local endpoints, with no automatic cloud fallback. Autonomous web retrieval, web access during both worker paths, and a working administrative WebUI are mandatory release capabilities; authorized web connectivity is separate from model routing.

The legacy Friday checkout, runtime, data and Telegram consumer stay preserved. Publication target: `alinescafs3mp-afk/friday_rework`, branch `main`. Secrets, private handoffs, donor checkouts, live runtime state and raw private evidence are excluded from source control. Sanitized, inert source snapshots and selected result extracts are published separately for analysis with their validation status.

See `docs/foundation-status.md` for verified progress and current gaps. See `sources.lock.json` for the selected upstream identities and `docs/integration-boundary.md` for the implementation boundary. The existing owner task register remains authoritative; this repository adds no dispatcher or second backlog.

See `docs/mandatory-web-admin.md` and `validation/acceptance-web-admin.json` for the owner's cumulative web/admin requirements and complete user journeys. These capabilities are not yet accepted.

[Donor capabilities and integration status](docs/donor-capabilities.md) distinguish planned, implemented, connected and verified functionality, including the mandatory web and administration journeys.

[Work log and intermediate analysis — 9 October](analysis/2026-10-09/incremental-01/README.md) record completed work, failed attempts, remaining gaps and next steps. This is a partial publication; the daily checkpoint is still due.

[Expanded source, outcomes and process analysis](analysis/2026-10-09/incremental-02/README.md) adds 349 historical result summaries, 40 design/control plans, source snapshots and explicit remaining coverage gaps. It is an intermediate publication, not the completed daily checkpoint or a release.
