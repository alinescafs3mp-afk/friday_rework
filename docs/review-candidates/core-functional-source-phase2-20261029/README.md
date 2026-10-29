# CORE functional source, phase 2: analysis only

This is an inert source checkpoint for review. It contains the exact 19-file CORE delta from the actual Source95 **H source baseline**, plus the changed offline test/checker source. The candidate is not installed. Existing runtime remains unchanged; no installed, service, Telegram, worker or full-product acceptance is claimed.

The changes cover scoped original-history recovery and pagination, web-only cancellation and final input fencing, preservation of original Telegram ingress, complete atomic text publication with nested-directory custody checks, durable ordinary document outcome delivery, and typed Dashboard settings. The administrator/settings repairs under independent review are still pending and are not included in this pinned snapshot.

## Exact source boundaries

- Product before: `f14c64c91c553206f1c817dee3e5ddc603e072b4` (Source95 H).
- Candidate after: `1676955354ee10604cdde106982492dc73638310`.
- `patches/core-from-source95.patch`: only the 19 product files listed in `SOURCE-HASHES.json`.
- `patches/native-checks-from-source95.patch`: 12 changed native test/checker files against the same Source95 baseline.
- `patches/project-checks-from-public-main.patch`: 9 changed project test files against public main `334fa8eb525dd4f5c16423e5d040e5b6f7e3cfcd`. Their before bytes were checked against the candidate support staging commit `5efc11f77d6c75fcb9de28d588ef4a2713591374` and are identical. These project test files are absent from the Source95 tree; the two test patches therefore have distinct before baselines.

The product patch was generated using Git diff on the two pinned objects, with full blob IDs and repository-relative paths. The file manifest records before/after SHA-256, byte counts and Git blob IDs, including absence at Source95. No source bytes came from parallel working edits. Copied, unchanged project support files are omitted; the patches require their existing source and canonical test infrastructure and are not a standalone checkout or installer.

The running bootstrap imports the H source surface. The separately accepted N98 workspace dependency surface has six different before files; those are not transplanted into this H map or changed by this package. Neither N98 after-images nor a new H provenance successor/current worker bridge compatibility have been accepted here. DSH/A0 implementation changes and their tests are excluded.

## What the observations establish

`STATUS.json` separates focused observations from final-candidate acceptance. Existing observations include positive and negative controls for history recovery, local web transport and retained custody, text publication and filesystem races, ordinary document delivery, and file/checker compatibility. They were made during implementation on the affected bytes or disposable overlays, not as one final gate on this entire snapshot. Packaging performed only source/object, hash and privacy checks; it reran no product tests.

The original failures remain part of the result. Recovery hints initially missed tool-only originals; nested directory permissions could change before publication; ordinary document failures used suppressible warning delivery. These produced real local fixes. Other failures exposed obsolete test assumptions, descriptor alias tracking gaps, missing test dependencies, incorrect import/config loading and a relative-workspace-path checker error. Focused corrected runs do not erase their original observations or establish a green full suite. Earlier privacy/skills and routing runs also had failures and collection errors; their aggregate is not reported as PASS.

Early offline checks were insufficiently isolated from the real baseline admission coordinator and reached its metadata. Those observations are not a clean baseline result. The corrected canonical fixture redirects both the bridge constant and matching environment variable before collection and per test, and guards Python I/O to the real coordinator. Two focused isolation controls passed. The original observations and reconciliation remain separate; this package neither resumes the baseline nor declares it repaired.

No private receipts, request inputs, handoffs, raw logs, real runtime identities, local paths/endpoints or owner-only task oracles are copied here. Synthetic unit-test principals, `offline-test` tokens and reserved `example.test` URLs are test values, not live credentials or destinations. Source was not redacted or altered to produce this publication.

Hermes-derived portions retain their MIT terms; the complete pinned upstream notice is in `LICENSE-Hermes.txt`. `THIRD_PARTY_NOTICES.md` states the attribution boundary.
