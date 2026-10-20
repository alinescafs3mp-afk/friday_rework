# DOCX paragraph ownership — source review candidate

Status: **UNCONNECTED / NOT_RUNTIME_ACCEPTED**. This archive preserves a completed source-only fix for `tools/read_extract.py`. It does not connect the change to the installer or installed product.

The pinned current source enumerates every DOCX paragraph, then reads all descendants of each paragraph. A nested paragraph's text can therefore appear in its containing paragraph and again in its own output. The patch gives each paragraph ownership of its own nodes: an iterative document-order traversal prunes nested paragraph and ruby-guide subtrees before descending. Nested paragraphs remain separately emitted in paragraph order; ruby-base text and ordinary text, tabs and breaks retain their existing handling. Ownership is structural and does not deduplicate equal text values.

The exact patch is preserved byte for byte. `SOURCE.json` records the original source, final source and patch hashes. The changed traversal avoids recursive Python calls and repeated traversal of nested paragraph contents. Paragraph order does not establish rendered page-layout fidelity.

Independent SOURCE review accepted the exact final source with no new high/medium finding. Separately, the integrator recorded 16 actual focused checks passing and a bounded depth-800 comparison of the original and changed source on the same input passing. These are focused source observations, not installed-product execution, a performance SLA or release acceptance. The private review and execution evidence are identified by hash; their contents and test materials are not included.

Integration and ordinary post-install retesting remain pending. The frozen product source was reported unchanged. Source and focused-check completion do not establish runtime or release acceptance.

`LICENSE` retains the existing Hermes MIT attribution for the code patch context.
