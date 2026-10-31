# Source113: bounded XLSX structure extraction

This analysis checkpoint publishes the exact `tools/read_extract.py` product code installed as part of Source113, its exact Source112 preimage, the original B146 candidate, and both transformation patches. The files remain under `docs/`; this publication does not change the active product or installer inputs.

The extractor now exposes hidden row and column declarations, declared filters and merged-cell structure in a bounded preview. It records stored merge-anchor values and inherited display separately from formula evaluation. Filters are declarations: they do not establish which rows would be visible after spreadsheet evaluation. Missing or empty formula caches remain distinct from actual cached `FALSE`, errors and numeric zero. Truncated filter text, children, depth and merge materialization are explicitly reported.

## Exact code and reconstruction

| Snapshot | SHA-256 |
| --- | --- |
| Source112 `tools/read_extract.py` | `cd7c578834272b9d982213e7d1d99c6373fb1d94733cb02f7af5530cdf2dcb87` |
| Original B146 candidate | `d568b4f41fb301b89a9c41ab5f0c9d77fbe4344a4d77c913aa073b4118236646` |
| Corrected Source113 `tools/read_extract.py` | `67fe706b5fd0bea92bb112949ee32c8695715bff6dd441512e6674c5998172dc` |

`native/source113/tools/read_extract.py` is the complete, byte-identical after-image, not a redacted excerpt. The matching Source112 and original-candidate snapshots make both transitions inspectable without a private checkout. `patches/hermes/xlsx-hidden-filter-merge-structure-after-source112.patch` maps the supplied Source112 file to Source113. `patches/reviewer-fix.patch` maps the original B146 candidate to the same corrected file. The existing integration manifest is copied byte-for-byte and retains all 139 accepted-prefix patch pins, including the three restored missing prerequisites.

The public Source113 block is incremental. A complete project/runtime snapshot is deliberately excluded because other files embed private principal identities, bridge bindings, custody records and historical handoff locations. In particular, `user_worker_join.py` changed only its private bridge path/hash between Source112 and Source113; that file is not published or replaced here. Its before/after product hashes are recorded in `SOURCE-HASHES.json` to describe the omission without exposing those bindings. This directory does not reconstruct a complete runnable Source113 installation.

## Checks and original observations

Run `python3 -B check_xlsx_structure.py` from this directory. The checker uses only the standard library, the exact copied source and an in-memory synthetic XLSX. It validates cache states, preservation of real values, the original fabricated-value defect, five truncation cases, the four-method reviewer correction, both exact patch transitions, whole-file preimage rejection and the manifest's leaf/prerequisite pins. It prints JSON and writes no files. The committed synthetic result contains 14 passing checks. These packaging checks establish offline extraction behavior and source integrity, not Telegram or spreadsheet-application semantics.

The checker was also run against the same retained original workbook used by the earlier controls: 14 checks passed without resending, regenerating or delivering anything. The workbook, user request, oracle and raw results remain private. `OBSERVATIONS.json` preserves digest-bound summaries of the earlier original failures, corrected controls, actual pure installer-consumer checks and the independent integrator review. Those saved observations were reused, not rerun by packaging. They include the genuine two-tail sequential acceptance/reversed-order rejection; an earlier nested graph-cycle negative was masked by inherited stale pins, and its named tail-order negative only corrupted a hash. Neither is described as proving the intended negative.

At the saved installation checkpoint, Source113 source/native verification succeeded and permanent gateway/Dashboard service readiness was separately accepted. The native dependency lock remained unchanged; a fresh source generation was verified. Source installation, service readiness and user semantic acceptance are distinct. Original S11 semantic FAIL and S12 failure/unknown observations remain retained. This publication does not repeat those consumed operations or claim a corrected user result. The full 170/120/all-variant scope remains unaccepted.

Full fresh composition is still unproven because eight inherited prerequisite pins are stale. The accepted Source112 incremental base was used for this installed update; this publication neither repairs those old pins nor claims a clean fresh installation. `STATUS.json` states these limits and records the separate saved maintenance/service intervals without adding nested durations together.

No private controllers, runtime receipts, request inputs, handoffs, raw logs, real principal IDs or local runtime paths are included. Exact product source and exact patch/manifest bytes were screened and copied without editing. The source is Hermes-derived; see `LICENSE-Hermes.txt` and `THIRD_PARTY_NOTICES.md`.
