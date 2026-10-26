# Diagnostic behavior and evidence limits

## Completed source change

The old diagnostic retained the last eight authenticated frames. A false `trace_truncated` value only meant that traceback traversal reached its end; it did not mean that outer authenticated call sites survived that slice. The completed source keeps that inner view and adds the first eight authenticated frames, walked/retained/omitted counts, overlap, slicing and traversal-cap indicators. Exception chains are bounded to four links and each traceback walk to 64 frames.

Merge observation requires the code object held from the genuinely authenticated ordinary module and the exact held receiver class. A matching function name or pathname alone does not qualify. The hook takes three diagnostic references while the unchanged loader holds that module; it performs no history reread. The state is reset before each use.

For file observations, the diagnostic reports changed identity field names, parent-proof differences and content-hash equality. It does not emit old or new hash values, metadata values or file contents. The nine-field identity orders mode before link count; parent identity uses five fields. At most four changed parents are emitted with truthful omission counts. Directory observation emits identity field names and a membership-equality boolean, without entry names. Paths are labeled lexically relative to the supplied home when bounded, or represented by a path digest; the diagnostic does not resolve or read them. Such bounded relative paths belong only in protected diagnostic output; no actual diagnostic output is included in this public package.

Extraction failure is recorded as `UNAVAILABLE` with a whitelisted exception class while the original exception remains authoritative. Diagnostic-only compact JSON has a 32,768-byte limit. Existing protected atomic publication, no-overwrite behavior, business encoding, admission, clocks, CPU limits, source authentication, current CAS and unwind checks remain unchanged.

## Reused validation

The completed S352 package had 33 producer diagnostic controls and 80 independent source assertions with zero final high or medium findings. These counts overlap and cover the broader coherent source package; they are not a total of distinct diagnostic tests or native executions. Its exact source and review evidence are reused here. No old process or history test is rerun to prepare these excerpts.

The new publication checks verify exact byte extraction and its private inverse mapping, parse/compile/tokenize the inert fragments in their stated lexical contexts, identify their host dependencies, and check the final allowlisted files for private bindings or content. They do not import or execute the adapter, a product module or any excerpt.

## Preserved uncertainty

The earlier R434 merge failure's stage and cause remain UNKNOWN. No history repair is inferred or implemented. The separate genuine first preflight PASS does not establish that the earlier failure occurred at the first check; the locked second check and later full-consumer checks remain distinct boundaries.

## Later observations reported by Root

A separate real full-API operation took 291.587 seconds. Its unsliced authenticated frames establish that the first preflight completed and the second, locked check refused a retained file pin. After unwind, no semantic transaction was present and the checked retained-source, launcher and unit bytes and expected absences matched their earlier state. The installed S332 version remained unchanged. This later refusal does not explain the older R434 failure.

A separate 6.256-second genuine native lock scan called neither history processing nor APPLY. Exactly six retained profile lock files failed their pins while the lock was held; all checked pins matched outside the lock and after unwind. The scan's locks were unwound. No private profile identifiers, paths, identities or diagnostic output are reproduced here.

Root separately restored the existing healthy gateway and Dashboard for permanent operation, without a test-window expiry. The observed restoration took 170.567 seconds. The cold gateway's observed upper bound was 114.694 seconds, below its 180-second allowance; that bound lies within restoration and is not added to its duration. A 30-second service-control client timeout was reconciled against the service that actually started. The gateway was running with its Telegram connection healthy; Dashboard identity was verified through the genuine signed CLI flow. These are observations from the completed restoration, not a new service-health check performed for publication.

At this observation boundary, primary/current6 was still uncommitted; shared qualification and Telegram file-task acceptance and continuation were still missing. Both pending worker tasks remained unsent. No source fix or native acceptance from subsequent lock-compatibility work is claimed. No user task, model invocation or artifact delivery was repeated to obtain a passing result. Source preparation, native execution, restoration, artifact return and semantic user acceptance remain separate facts; the operation durations above are not summed.
