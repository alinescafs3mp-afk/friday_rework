# Basic dashboard session revocation - source candidate

Installed Source117 leaves retained Basic access/refresh tokens usable after logout. This candidate adds a durable private session-family ledger, checks it during verification/refresh, disables Basic refresh-result caching, and connects durable revocation to the existing logout handler. Other session families remain usable. Persistence failure returns a non-success response.

This is a source candidate, not an installed fix or full admin acceptance. Fifteen isolated cases imported real native modules and exercised login, native refresh/logout handlers, restart, concurrency and filesystem failures. Final source and observations received independent review. The full HTTP middleware/browser/service journey was not run.

The patch targets the exact Source117 beforeimages in OBSERVATIONS.json and adds one native module. The fixture is the exact executed source. Its CLI needs the pinned dependency context in its preparation inputs; it is provided for review, not advertised as a standalone installed-product test.

Limits: Linux/POSIX only. New SID families have durable family revocation. Legacy sid-less tokens preserve signing compatibility; only the exact observed pair and linked descendants can be revoked together. Unobserved legacy tokens require deliberate migration or expiry. No blanket logout or credential/configuration change is included. Coherent old backups can undo revocations. Integrity or store/anchor loss requires explicit reconciliation. See OBSERVATIONS.json for remaining untested conditions.
