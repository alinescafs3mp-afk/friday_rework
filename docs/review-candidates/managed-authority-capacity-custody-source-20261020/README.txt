Reviewed Source candidates: managed configuration authority and ordinary capacity/custody

These patches are review material. They are not connected to the installer or installed runtime.

The native patch keeps user configuration references aware of profile scope while resolving administrator-managed references only from the process environment. Separate cache dependencies preserve both authorities when they use the same variable name. Failed-read recovery retains its existing refusal-to-write behavior and refreshes the managed process layer.

The ordinary installer patch contains the previously reviewed compression-capacity rebind support and monotonic retained-reference custody fix. A protected-reference proof failure after publication prevents a later observation from certifying rollback. This file is based on the public main version recorded in SOURCE.json.

Source review and synthetic controls passed. Native changes have 74 author assertions and 39 independent assertions; the reused custody fix has 14 additional extracted controls. These are not runtime or final-candidate acceptance.

The previous frozen candidate actually ran the original 163 capacity cases successfully. Its focused checks had 32 passes and 3 failures, and the separate custody checks had 1 pass and 4 failures. Those failures remain recorded; no result transfers to these changed bytes. Coherent successor construction, final real regressions, full mandatory gates, supported installation and live acceptance remain pending.

The native patch requires the exact three preimages in SOURCE.json. Its dependency is the prior weighted configuration Source candidate. The installer patch requires its own declared public-main preimage. Patches use zero context; apply checks require git apply --unidiff-zero. Private acceptance definitions, fixture corrections, personal data and runtime credentials are excluded.
