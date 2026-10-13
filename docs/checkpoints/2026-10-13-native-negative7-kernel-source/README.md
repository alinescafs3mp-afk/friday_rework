# Immutable native negative7 baseline and incomplete kernel Source audit

This is an inert Source/data snapshot for external analysis. Native baseline status: **NOT_ACCEPTED_7_SOURCE_DEFECTS**. Kernel audit status: **INCOMPLETE_LATE602.933_USEFUL540_TOTAL600**. Coverage is **0**; SourceSafety **NO_GO**; ResourceGo **NO_GO**; live **NOT_RUN**. No qualification or release acceptance is claimed.

The native directory contains all11 immutable baseline Source files (149998 bytes), all10 exact diffs, all41 dependency references, the complete original independent Source review with7 blocking causes and29 adjudications, and12 static negative controls. Files ending `.public.txt` preserve the original bytes and are inert review data; they were not imported or run. The corrected native Source proposal completed on13Oct at13:37MSK (11 files/167071 bytes,8 diffs,41 dependencies,51 Source/AST/data controls). Its first independent final Source review is pending. The corrected code is outside this immutable rejected-baseline package. The kernel audit refers to24 client declarations in this baseline; the new proposal removes obsolete retain_child and declares23. Both lack a real qualified native provider. The publication preparer neither read nor bound the corrected candidate; this current status was added by the integrator from the exact completion evidence.

The original native review completed in1048.466 seconds within its original1080 useful seconds. That completed review rejected connected Source correctness. Its positive data-fidelity and static guard observations do not accept the whole baseline.

## Seven blocking Source causes

### S1 — Reducer allocation failure does not enter irreversible refusal

feed catches only HistoryRefusal and KeyError/TypeError/ValueError/OverflowError/struct.error. MemoryError at frame dict creation or a dictionary/set/Slot insertion escapes without failure being set. Sequence can already advance and alias counts/generation state can already mutate. A later feed is gated only by failure, permitting continuation of incomplete state. Native bridge sticky allocation handling cannot certify this separate Python reducer path.

Required change: Make every decoder/data allocation failure after accepting the original epoch irreversibly set a fixed refusal reason before it escapes; no continuation/replay/reconnect may rehabilitate that epoch. Preserve original error and loss propagation into genuine authenticated delivery acceptance when it exists. Add static current-body controls for dict, set and Slot allocation sites; future actual controls require separate authorized execution.

### S2 — Private copied files-table can be assigned to multiple independent births

After one completed copy source_table2 -> destination3, table_origins[3]=2. TASK_BIRTH(task4,parent1,src2,table3,flags0) and TASK_BIRTH(task5,parent1,src2,table3,flags0) use distinct generations, but both pass the current private-fork lineage predicates: no owner/assignment/consumption mark on destination3. C checks only ft origin and also never consumes destination assignment. Two non-CLONE_FILES births now share one table. SHARE can also reuse an already assigned destination based only on origin. No frames were issued or fed.

Required change: Bind each private copy to its exact creating task/operation and one permitted destination assignment, consume that assignment once on private birth/switch, and require an explicit supported CLONE_FILES lineage for any intentional sharing. Keep Python/C producer and decoder owner/assignment semantics identical; do not change coverage or admit a fabricated provider.

### S3 — Ring retirement becomes unreachable after task exit or files-table switch

Ring records store birth task/table. SHARE changes that task current table without migrating or retaining an authorized historical ring-custody action. TASK_EXIT marks task dead without refusing surviving ring references. _ring then requires an alive task currently owning the old table; C ring slot/end impose the same live/current table match. Retirement after either transition is refused, while TABLE_END/OFD_END continue to reject the surviving ring/alias. This is a Source state-machine counterexample, not a captured kernel order.

Required change: Define and implement supported original-epoch ring ownership transfer or retained teardown semantics through unshare/exec/exit. Require teardown before TASK_EXIT when that is the only supported order, and reject a transition that would make recorded custody unreachable; retain a finite authenticated disposal route after original task death. Apply the same policy to both C and decoder before claiming those paths covered.

### S4 — C birth producer lacks decoder parent/table liveness completion guards

C task_birth checks parent live and table ready, but not parent born_complete, parent executing, table live or copy_active. Decoder rejects an executing/incomplete parent and dead table. A ready retired table retains ready=true until pointer disposal, so the C predicate does not reject it. Missing insertion-map promises do not repair this concrete producer/decoder mismatch.

Required change: Add exact original parent born-complete/non-executing, table live, atomic-copy exclusion and non-null/new child reference checks in the C body, and maintain source policy symmetry with TASK_BIRTH decoding. Use genuine site locks only; no provider stub or loaded execution is authorized here.

### S5 — Retained-capacity meaning differs across producer and decoder

C retained_n monotonically counts every lifetime record and never reuses/decrements it; the33rd retain is refused even after all32 releases. Decoder deletes released retained entries and checks len(retained)<32, so it accepts the33rd distinct retain generation until the global8192 cap. Both are individually count bounded, but the connected fixed retained policy is not identical.

Required change: Specify lifetime vs simultaneous retained capacity explicitly and enforce the same fixed meaning in both bodies. If lifetime32 is intended, keep capped release tombstones or an exact total allocation counter in the reducer; no native resource bound may be silently widened. Actual allocator/charge proof remains a separate missing facility.

### S6 — Exported legacy retain_child bypasses local sticky-current/owner admission

Unlike reserve_birth, retain_descriptor and reopen_descriptor, the exported retain_child calls frw_client_retain_child immediately after pair. pair validates adoption identity but does not test history_failed or invoke current_handles; it also does not enforce owner role. A refused original adoption or child-role adoption can reach this alternate post-birth acquisition interface. No genuine provider implements it now; a future provider may refuse it, but that is not a guard in the reviewed bridge body.

Required change: Remove the obsolete alternate acquisition ABI from the method table, fixed-module method list and header if all consumers use preclone reserve+bind. Otherwise enforce local irreversible refusal/current/owner checks and bind only a previously reserved true-birth capability, with no second acquisition route. A declaration that a future provider will reject misuse is not a present source implementation.

### S7 — Descriptor reader custody has fallible untracked publication interval

A native reopened retained-reader capability returns at129, then allocating the row dict and appending it to reader_custody occur before the try at132. MemoryError in either step leaves no self-owned custody row and no explicit authenticated release or sticky descriptor failure. The C finalizer only calls the missing put-retained reference-disposal contract and expressly does not claim deadline-bounded successful cleanup. Existing failure release controls begin after this interval.

Required change: Prepare and reserve bounded Python custody bookkeeping before the native acquisition, or wrap the entire return-to-publication interval with guaranteed one-shot tracked release and irreversible uncertainty retention. Never treat dropping a local Python reference as a confirmed native close. Apply original deadline and genuine held-reference semantics when the missing provider is implemented.

## Kernel data and its limits

The kernel directory preserves all43 actual upstream Source sites with anchored source text, all25 wire event mappings,41 preparation obligations,24 missing client implementation declarations, ABI/custody/refusal requirements and10 exact missing-input/action rows. Six available primary Source files total142434 bytes. Two header matches are bit exact; header equality gives no whole-kernel proof. Official upstream URLs plus length/SHA identify the external bodies; full external kernel Source bodies are not redistributed.

The available upstream v7.0 Source is **not exact Ubuntu7.0.0-34.34**. The exact patched Ubuntu tree, DSC signature, loaded-code pins, remaining bodies/callgraph and actual adapter qualification are missing. Retrieval failures (403/404/429) describe unavailable inputs in this audit, and do not prove host facilities impossible.

Original kernel closure began at396.408 seconds, missing its300-second requirement. Original RESULT was sealed at602.933 seconds, beyond useful540 and total600. This package retains the useful observations and the missed boundaries honestly; it does not retroactively accept that audit.

Material upstream findings:

- Lockless fd_install prevents treating file_lock as complete copy/mutation serialization.
- dup_fd punch_hole may omit occupied source aliases; immutable full-copy protocol needs reconciliation.
- Direct fixed-file providers can produce files without source process fd; immutable source-fd-only protocol needs reconciliation.
- Observer-held refs alter final fput/files count; semantic retirement and actual final disposal need distinct proofs.
- Failed/partial ring update and user-copy rollback mutate aliases; syscall-success-only hooks lose history.

Critical adapter constraints:

- fd_install fast path is lockless with respect to file_lock; copy source races expressly documented.
- dup_fd punch_hole truncates source aliases while current COPY protocol requires full occupied-source count.
- Direct fixed-file producers may supply a held new file without a process source fd; current RING_INSTALL requires source-fd lineage.
- Retained observer file/files references defer physical final puts; define semantic retirement and last external-reference tracking.
- Failed or partial ring updates and put_user rollback can mutate; syscall-success-only observation loses history.
- Same-object A→B→A and FD/CLOEXEC/status changes require fresh generations even if final visible equality restored.

## Remaining required work

Real provider/hooks, all24 client bodies, authenticated transport, independent issuer, loaded-code bootstrap, atomic adoption, original resource qualification, seconds/ns conversion and complete live/loss reference disposal remain missing. Full547, native67, full150+28, full32, all7 journeys and all mandatory final gates remain required and unbound/not run. Canonical entrypoint15ce and C89a50f80d1 are unchanged; C89 remains UNBUILT. G7/G8 NO_REPLAY and denied C/ELF NO_RETRY_NO_SUBSTITUTE remain in force.

## Reading the data

- [Component statuses](COMPONENT-STATUSES.json)
- [Exact Source, diffs and dependency manifest](native/SOURCE-DIFF-DEPENDENCY-MANIFEST.json)
- [All7 blocking causes and source locations](native/BLOCKING-SOURCE-FIXES.json)
- [All29 adjudications](native/ALL29-CURRENT-SOURCE-ADJUDICATION.json)
- [All12 static negative controls](native/INDEPENDENT-STATIC-NEGATIVE-CONTROLS.json)
- [Kernel primary URLs, lengths and SHA](kernel/PRIMARY-SOURCE-REFERENCES.json)
- [43-site matrix and pages](kernel/ACTUAL-SOURCE-HOOK-MATRIX.json)
- [25 event kinds](kernel/ALL25-NATIVE-EVENT-TO-SOURCE-MAP.json)
- [41 preparation obligations](kernel/REQUIRED41-SEMANTICS-ANCHORS.json)
- [24 missing client definitions and bootstrap requirements](kernel/NEXT-IMPLEMENTABLE-CLIENT-BOOTSTRAP-REQUIREMENTS.json)
- [Exact missing-input/action map](kernel/CLOSED-MISSING-INPUT-AND-PROOF-ACTION-MAP.json)

This publication candidate itself has **independent review NOT DONE**. It does not change the product or authorize Source execution.
