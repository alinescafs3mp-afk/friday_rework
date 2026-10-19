# Compact-model capacity migration — reviewed candidate

This is an inert review copy of code and regression sources. It is not connected to the installed product. No configuration, source receipt, credentials, running service or model deployment is changed by this directory.

The candidate supports increasing the separate compression role from context 40,960 / input ceiling 40,954 to context 65,536 / input ceiling 65,530. Main inference remains 262,144. Output reservations, safety margin, template overhead, request timing and multipass limits are preserved. The exact inactive legacy Agent Zero declaration remains unchanged.

`PROJECT.patch` extends the existing stopped inference transaction with a separate capacity-only request schema. It derives the complete managed-profile inventory, renews every native profile proof, publishes the root marker last and retains existing compare-and-swap, custody and rollback checks. It also handles the preserved inactive legacy declaration in the product compiler and restart-input validator.

`NATIVE.patch` extends the two existing native request guards to accept the exact 65,536 envelope while retaining the 40,960 route. No serving configuration is changed.

The four files under `tests/` cover the capacity transaction, native envelope and inactive legacy declaration, previous renderer migration, drift/refusal and rollback. Test identities are synthetic; existing public legacy sample endpoints remain fixtures. These are engineering regressions, not the private user-journey acceptance checklist.

Validation: 163 offline cases passed on the private isolated fixture package; independent code review reported no actionable defect. One fixture identity was anonymized for publication and all 36 affected tests passed again. The other 127 cases and production code were unchanged. These tests execute native validators and transactions against synthetic private homes; renderer transaction fixtures use a synthetic renderer object. They establish no live serving, installed-state or product acceptance.

One separate tiny request against the changed compression deployment returned HTTP 200 and matched the unchanged local prompt count. That observation covers that body and time only. It does not establish universal tokenizer equivalence, multipass correctness or a general speed improvement.

Before application, the five production afterimages must belong to a coherent reviewed source/project successor, pass its mandatory qualification and be installed through the supported stopped update. The real capacity transaction must then renew both managed profiles and the ordinary configuration binding together. Full runtime, Telegram, worker and user-journey acceptance remain outstanding. Historical snapshots and consumed attempts must not be rewritten or replayed.

Patch baselines and afterimage digests are recorded in `FACTS.json`. `LICENSE` retains the existing Hermes MIT attribution for native patch context.
