# XLSX structure source and admission observations

This is an analysis checkpoint, prepared on 2026-10-31. The corrected source is accepted at its reviewed source boundary and reviewed for this publication. These files do not activate an overlay or establish installation, runtime behavior, or semantic acceptance.

## Corrected source

The patch adds bounded, inert previews of hidden row/column declarations, AutoFilter declarations, and merged-cell structure to the existing XLSX extraction carrier. It does not evaluate filters, infer the current visible subset, or recalculate formulas. Existing value, formula-source, and generic extraction lanes are preserved.

Reviewer fixes distinguish missing and blank formula caches from stored values. Missing/blank formula and nonformula caches do not fabricate `FALSE` or `#ERROR`; actual stored boolean, error, numeric zero, and inline text values remain explicit. Truncation is reported for long text, bounded children, depth, omitted records, and bounded materialization of merged cells. Three omitted prerequisite pins were added.

The accepted source checks include 19 independent final-source/nearest-consumer controls and 19 integrator delta/API controls. The original 21 author controls were reused at their unchanged source snapshot. The real incremental Source92 receipt validator accepted the corrected target; missing-prerequisite and wrong-preimage controls rejected their altered inputs. These are source checks. Full fresh composition remains unproven because eight inherited Source112 prerequisite hash mismatches remain unchanged.

`overlay.patch` and `overlay-manifest.json` are byte-for-byte copies of the reviewed corrected artifacts. The overlay manifest retains its original relative projection paths and exact pins, including all 139 prerequisites and 139 installed-prefix entries. Its `patch` field names the logical source-tree location; the published copy is called `overlay.patch`. This directory is an analysis location, outside product overlay discovery.

## Preserved user-case observations

- **S11:** the original full 180-second observation reached a normal native terminal with zero owned resources and semantic **FAIL**. The observer tool did not expose its exit status; no exit 0 is asserted. It is preserved and was not repeated by this preparation. Corrected source does not turn that observation into acceptance.
- **S12:** the original ordinary layout caller's first invocation was refused by the historical input-collision guard before credential loading, API access, admission, or run creation. There were zero new Telegram sends and zero model calls; no canonical run or admission was created. At this checkpoint the admission source fix remained pending. This is an admission refusal, with no product verdict and no case acceptance.

## Saved Office comparison

A changed diagnostic trace captured a successful synthetic save with engine exit 0. The output was structurally valid and contained zero formulas, so it does not establish genuine formula or cached-value behavior. Reassembly of unfinished/resumed trace calls counts 42 failed `mmap` calls with `ENOMEM` during that successful save; the historical single-line count of 40 remains preserved in its original observation. Allocation failures can coexist with a successful save. The prior failure's cause remains **UNKNOWN**; no deterministic Office repair is established.

Genuine formula behavior, the full scope of 170 cases, 120 formats, and all mandatory variants remain **UNACCEPTED**. This preparation performed no installation, runtime execution, user-case replay, Telegram/model call, service change, or baseline change.
