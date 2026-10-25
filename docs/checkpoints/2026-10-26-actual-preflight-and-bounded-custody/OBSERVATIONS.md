# Completed observations and limits

## Preserved installed state and maintenance

Installed S332 and canonical 318 remain preserved; no new runtime target is represented as published. Exact executable maintenance archived two files totaling 33,483 bytes, left its state empty, and confirmed its target absent. Before the later preflight, all ten publication-beforeimage byte sequences and the identities and hashes of five backup files were reconciled, with no transaction present and executable-maintenance state empty. No private filenames or bindings are included here.

## Failed and successful preflight boundaries

R434 full native APPLY failed after 71.153968 seconds with a protected `ValueError` in `_HistoryWalk._merge`, before a transaction. All ten before files and five backup file byte sequences remained unchanged. The earlier cause remains UNKNOWN; later results do not retroactively explain it.

A separately closed standalone diagnostic ran for 150.084 seconds, timed out, and produced no witness. Its old merge failure was not reproduced. Whether the discrepancy arose at the first observation, the locked check, or a later stage remains UNKNOWN. An older diagnostic used `frames[-8:]`, retaining only the last eight authenticated frames and omitting outer call sites while `trace_truncated` was false; this limits the explanatory value of that output. No unfinished replacement diagnostic is included.

The cheap input guard initially reported 54 false failures: 53 concerned owned 0775 parent directories beneath a private 0700 home with matching file hashes, and one treated a future runtime proposal as a current file. The repaired guard preserves owner, path, link, identity, and hash checks, admits the historical permission case only under the private anchor, and maps the future proposal to the existing canonical source. The repair required no chmod or history writes.

R435 then passed a genuine `_apply_inputs` check and postchecks; native exit was 0 and its process was reaped. This does not reproduce or explain the older merge failure. The full consumer must still perform its locked and later checks.

## Timing without double counting

The entire original R435 phase lasted 511.314240795 seconds, including preparation, the initial cheap-check failure, and its repair. Actual native execution was approximately 276.267974 seconds, derived from process birth with 0.01-second tick resolution. The native interval is contained in the phase interval; they must not be added. Preparation, installation, returned response, and observation remain separate facts.

Gateway and Dashboard were restored under existing permanent native management; signed same-owner checks passed. Observed cold completion had an upper bound of 64.355 seconds, below the separate 180-second cold limit. A test expiry was not used to stop these healthy permanent services. Kimi was unchanged.

## Source algorithms and pending user result

The independently reviewed carrier and capture changes protect ownership through process birth, defer cancellation across custody and cleanup, retain original deadlines, and preserve a failed cleanup as `STOP_UNCONFIRMED` rather than claiming success. Their inclusion here is source-only. The preflight excerpts show input authentication and future-output classification; missing imports and constants are not substitutes for the actual consumer.

No actual current6 execution, qualification, or Telegram worker acceptance is established by these source excerpts or the preflight. The two planned initial user tasks remain unsent. Real coding and engineering file tasks, returned artifacts, and a short continuation in the same conversation remain required. No user task or model effect was repeated to build this package.
