# B138 whole-source review: changes required

The independent B138 review completed on 2026-10-31 at 11:38:11 Moscow with **CHANGES_REQUIRED**: five verifier defects and seven caller or nearest-consumer defects. This is a completed source-only rejection, not a product failure run or an accepted deployment. The subsequent B139 coherent source repair was actually started; its completion and acceptance are outside this checkpoint.

The review read the whole changed verifier, all eight listed caller modules and both control programs, then checked the changed graph against the nearest canonical material, output, receive-chain, ancestry and lower native-correlation consumers. It did not execute the whole historical runtime graph or qualify a new mutable live boundary.

| Finding | Confirmed cause | Evidence and required correction |
| --- | --- | --- |
| B138-V1 | Consumed worksheet content type is not enforced. | Missing and wrong worksheet types both returned CLI PASS; require the exact consumed worksheet type. |
| B138-V2 | Raw-byte DTD/entity scan can be bypassed by UTF-16 XML. | A harmless internal entity expanded and returned PASS; reject declarations independently of encoding. |
| B138-V3 | Array-formula followers look like constant proof. | Mapped cached outputs in the anchor's array range returned PASS despite formula-derived values; reject mapped formula output coverage. |
| B138-V4 | Shared strings are consumed by familiar ZIP filename alone. | An unrelated, untyped part returned PASS; require the workbook relationship and exact part type. |
| B138-V5 | Oversized shared-string index escapes structured refusal. | A 5,000-digit index caused exit 1 with no report; bound conversion and return a structured rejection. |
| B138-C1 | FIRST_FILE still consumes the old P03 frontier. | Source uses the already consumed historical predecessor rather than the current closed currency QUESTION; retain ancestry and once-slot history while selecting the correct frontier. |
| B138-C2 | Preparation90 begins after authenticated loads and setup. | Source places the timer after package/provider, memo, setup and history work; start the same finite deadline at entry. |
| B138-C3 | Runtime-plan hook does not update the exact material consumer. | Both new stage plans were refused by the unchanged canonical currency-only admission method in offline calls; add narrow exact units admission. |
| B138-C4 | Artifact map is not bound to the semantic PASS report. | Caller accepted an invalid replacement map with an old PASS report for the same artifact; the real verifier rejected that map. |
| B138-C5 | Terminal JSON is not joined to the canonical committed receive chain. | Minimal unrelated terminal data was accepted; source calls receive inventory without requiring terminal drain completion. |
| B138-C6 | FIRST_FILE declares zero outputs while capturing one document. | The canonical output consumer returned an empty list; declared count 0 differs from observation maximum 1. |
| B138-C7 | Text-only QUESTION fails lower native correlation. | A direct offline call refused source_reference=None; adopt exact text correlation while retaining protected first-artifact custody. |

The eight new actual CLI checks comprised one valid positive, five false PASS results, one unstructured crash and one correct rejection of the invalid map used to expose the caller/report mismatch. The crash is a defect, not a successful negative control. The separate caller checks used explicit offline seams; they establish neither canonical Store admission nor actual Telegram/native execution. The exact observed outcomes are retained in CONTROL-TRANSCRIPT.json.

Earlier results were authenticated and reused, not rerun: 26 original verifier controls, 28 independent actual-CLI controls, and 27 caller controls. Their passing results remain limited evidence. The caller controls are inert seams, compilation or generic validators; they do not prove whole-runtime admission. No model or artifact-creation effect was repeated for publication.

At the supplied boundary, Source112 and tester81 were already installed and tester81 had fresh-process qualification. The B138 rejection does not undo those distinct facts or require reinstalling unchanged bytes. B139 accepted its original 3,600-second budget including a 360-second reserve at 11:40:40 Moscow; the correlated actual-start record was written at 11:41:59. This records source repair in progress only, with no completion, installation or live authority claim. The unchanged original baseline was running under its uncapped idle policy; Root's 11:42 observation was 377/673. Those counts are a historical observation, not a new run, pause, acceptance or current progress claim.

No new S06 physical-units or S03 user-task effect was executed by this review or publication preparation. No units artifact was received through a new user task, no new full180 observation occurred, and no units runtime or semantic acceptance is claimed. The full 170-case / 120-format scope and all applicable variants remain **UNACCEPTED**. A0 remains deferred and Sol remains in reserve.

The original S05 was already SENT and CLOSED, with a genuine semantically checked XLSX delivered after 498 seconds against the required 180: the timing result remains FAIL. Its incomplete canonical capture remains UNKNOWN; no historical effect is replayed or relabelled NOT_RUN. The old currency QUESTION is closed with canonical UNKNOWN and full180=false; its separately saved reply's semantic PASS does not rewrite that record.

SOURCE-TRANSCRIPT.md contains line-numbered excerpts of the rejected implementation, not fixes. Generic source names and one explicit private-constant placeholder replace host-specific identification. These are incomplete inert review excerpts, not installable files, source acceptance, a release or execution instructions. Private input and oracle bytes, expected values/cells, captions, requests, credentials, accounts, endpoints, pairing records, proof paths and raw handoff reports are omitted. Exact private provenance remains with the integrator.
