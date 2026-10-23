# Frozen source observations

The three patches reproduce these complete before/after file identities (SHA-256), using the logical paths in their headers. Each was applied in a small disposable copy of its immutable before-file with zero fuzz and zero offset, then compared byte for byte with the complete expected after-file. The copies were removed. These full-file hashes identify the original source files, not redacted replacements.

| Logical source | Before | After |
| --- | --- | --- |
| `scripts/friday_ordinary_a0_registration.py` | `aa7025096dadc03db30470db1bddf2db32a107d7434e5de018172089f2fa3a6a` | `cc3089a3df9849e29955b151c400edf2f8c4973d1535fcc70f8663b791559fba` |
| `install/binding/root_binding.py` | `9747e9d256d152bd60156f9c6ad69a2b51cd4f915340e68efec3733d13ff259a` | `a35e4654f5358f6474ba67a556ec58b09deaf2c54a999609f585435c0d5e4629` |
| `install/port/capture_bind_existing_stopped.py` | `f70c30941a0263bcd167118f6f75dfd0cdc5dc73797abdc686178df66d70abc6` | `4ed9fec251d8604bf263898110f2645de636443a62619a453bbc7d7b968b36a0` |

Only `_checked_source_maintenance_current` changes in canonical registration. Only `load_consumer` changes in the R148 helper; every other helper definition, including `bind_root_data`, retains the same AST. The caller changes only `feature_binding=b` to `capture_binding=b`. The helper hashes above identify the accepted R148 files before the separate C5 registration-pin retarget.

Previously accepted evidence, reused without new functional execution:

| Evidence | Result and scope |
| --- | --- |
| Current lineage | 56 passing controls: 50 independent canonical/private controls plus 6 committed-drift/foreign-service/anchor negatives. Full original changed-function and archived descendant AST executes in synthetic isolated homes. Covers exact pending/current/future edges, strict default activation, explicit/stale input, missing/repeated/reverse/split transition, old mirrors, launcher and unit identity. |
| C5 routes | 15 passing metadata/helper/adapter/verifier/gateway/DOCX predicate controls, including stale pins and null operative slots. These are source/predicate checks, not dispatched operations. |
| Retargeted budget | 15 passing controls on the actual private 600-second budget guard, including deadline clipping/drift, expiry and mismatches. No installed-home execution. |
| C5 genuine loader | 5 cases: original unbound receiver bootstraps with source custody intact; stale target, operative slot, mixed modes and installed-capture mode refuse. Positive identity reaches the deliberate `fresh_capture_required` boundary. |
| Normal imports | 8 actual canonical/private module origins and API identities pass under isolated imports and enforced audit; no application-history validation is called. |
| Composition | 472 reference joins; all 311 project-file hashes recomputed; only canonical registration changes from C4. The 118 native layers / 17,716 native files and nonproject inputs remain unchanged, with operative slots null. |
| R148 identity correction | Old None/concrete binding mismatch and prep-bound clone are refused. Corrected original unbound consumer preserves canonical API/ROOT/package identity and source stability across context mutation, passes the final receiver identity check, and reaches the intentional empty-fresh-capture refusal. Missing/stale receipt, extra context, stale feature, mixed/installed modes and operative slots refuse. |

The lineage fixtures use genuine old service bytes and SHA-256 values. Native unit-registration and ordinary bridge joins are bounded stubs; fixture native source-layer deltas are empty. The full original archived descendant verification remains in the exercised source AST. This is partial isolated source evidence: full native history against the actual installed home, physical installation, service/model execution and semantic/user acceptance were NOT_RUN in R148/R149 and in this publication. No proof that an entire future operation fits in 600 seconds is asserted.

Frozen acceptance identities (private evidence contents are not exported):

| Record | SHA-256 |
| --- | --- |
| R149 Root C5 source acceptance | `ffb1b918d0c0a266b0663febcef3acc9f61445a7bf60cd1a49d3e669c6e740ea` |
| R149 Root source-use record | `d3300e9276508e54fc873d0e5aa59a54bf0feb992fea8552393dfb395189e99f` |
| R149 registration-context delta | `3cf9c9213960135dfb9ebab73f1a00fad26bf2224de0cf11b7deb22d68de2e0c` |
| R149 independent source review | `f87f45bdd2cd19f26735db0d71a09f013a6acc5fdaacc01538f55c46d419f6cf` |
| R148 Root independent acceptance of reviewer fix | `9a2e5c9c994ec117455425653786969179a443bc1acc801f6d5ee2c66fe5c69f` |

Source-only acceptance does not supersede R146 capture refusal/no-install or reopen any previous clock, budget, stopped operation or consumed effect. Current installed-version/runtime state requires separate fresh integration evidence.
