# CLI primary cleanup and renderer composition — 2026-10-11

This new whole19-file source candidate combines explicit primary-exception cleanup fixes with the exact previously accepted renderer change. **Independent candidate acceptance: PASS_SOURCE_ONLY,151 valid property observations. Strict consumer30 remains SOURCE_FAIL_UNESTABLISHED; installed behavior, full gate and release are NOT_RUN.**

`sol-metadata-exception-source/` preserves Sol’s whole19-file attempt. Independent review reproduced two causes across nine observations: cleanup can inherit an unrelated handled exception, and native copy-fallback close can mask cancellation or the original fsync failure. `composed-cleanup-renderer-source/` contains the next whole19 snapshot, with four changes: the three native metadata repairs and the exact prior renderer. Original failed observations remain history.

The new candidate captures only an exception raised by the current operation body and passes it explicitly to cleanup. Native default and strict copy/read handles now preserve their primary exception through secondary close failure. Author controls:43 PASS; independent source review:151 valid properties PASS. These selected-body controls do not establish actual host custody, preemption, terminal restoration or installed execution. Observed destination publication does not confirm directory durability.

The two relative-path patches chain from the previously published [metadata source](../cli-renderer-metadata-source-findings/metadata-source/) through Sol’s attempt to the composed candidate. [REPORT.json](REPORT.json) separates source availability, failed review, author observations and the completed independent source acceptance. [MANIFEST.json](MANIFEST.json) pins the publication. Hermes retains its [MIT notice](LICENSE.Hermes).

G7 is consumed and cannot be replayed. G8 awaits the genuine owner terminal/sudo step; kernel120 is not granted and normal3600 has not started. Old Friday and Pandora remain OFF. This intermediate block does not replace the daily21:00MSK full-period checkpoint.
