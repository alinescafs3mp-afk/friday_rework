# Coherent production code — source review candidate

Status: **UNCONNECTED / NOT_RUNTIME_ACCEPTED**. This archive preserves five production-code diffs for review. It does not connect them to the installer or installed product.

The patch combines the current counter binding, weighted readonly configuration reconstruction, managed process-environment authority, and administrator-session policy evaluation. Its five diff sections are preserved byte for byte from the coherent source layer. Exact code preimages and afterimages are recorded in `SOURCE.json`.

The renderer repeats the source published in `../current-counter-v2-20261019/`. The configuration and managed-scope edits repeat `../managed-authority-capacity-custody-source-20261020/`. The configuration reader coalesces `../weighted-config-reconstruction-source-20261019/` with the managed-authority changes against its original preimage; these are alternative compositions, not patches to stack. The administrator-session afterimage was previously identified in `../readonly-config-and-provider-slow-source-20261019/FACTS.json`; its native source diff is retained here. Existing tests and installer patches are referenced rather than recopied.

All current model/tokenizer assets and their operational provenance are excluded. Their exact upstream revision and redistribution license remain unestablished; no legacy asset license is transferred. This is an incomplete source-only projection and cannot serve as a standalone installation bundle.

Current qualification is incomplete. Earlier preparation failed an input check; repaired preparation and all required current-candidate gates remain separate. This archive claims no installed, live, runtime, or release acceptance and transfers no earlier PASS to these bytes.

`LICENSE` retains the existing Hermes MIT attribution for the code patch context.
