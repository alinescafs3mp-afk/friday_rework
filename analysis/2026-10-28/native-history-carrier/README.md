# Native history API and GNU carrier corrections

This is a minimal diagnostic source export for the 2026-10-28 installed Source72 → Source73 sequence. Both source versions were actually installed and accepted in fresh native processes. Source73 changes the two worker plugins; its native tree is unchanged. Source acceptance does not establish A0 runtime qualification or a returned engineering file.

`native-history-api.UNBOUND.patch` preserves two API contracts in the authenticated history join:

- Load the exact selected native verifier outside the historical source projection. Its public `module()` factory takes zero arguments; the historical wrapper had treated it as a two-argument loader.
- Preserve `source_proof(current_acceptance=None)`. The retained wrapper accepts only `None` or the exact authenticated parent acceptance; proof, transaction and digest checks remain active.

The patch comes from the tested repair against Source72. Source73 carries the same two fixes in a newly bound parent chain. Its complete file therefore has a different digest. This exported patch is diagnostic source material, not an installation plan or an assertion that it applies directly to the current repository or installed tree. Only the two diff headers were changed; hunk bytes match the private source patch.

`gnu-carrier.UNBOUND.patch` changes the qualification carrier's fixed executable from `/usr/bin/timeout` to `/usr/bin/gnutimeout`. On this host the former resolved to Rust uutils; the latter was the actual GNU binary. Exact parent executable, ownership/mode, arguments, birth time, 600-second budget and 30-second reserve checks remain. The preparer and native entry were rebound to this support file; unrelated tester and publisher consumers retained their original support reference. No full carrier, private binding or runnable command is exported.

Existing narrow checks covered the real retained Source72 consumer, wrong-acceptance and changed-verifier-digest rejection, nearest loader/plugin consumers, and an actual GNU parent plus short-lived owned signal probes. Those results keep their original scope. No product test, model call or worker operation was run to make this publication.

The successive failures are distinct. The first carrier refusal occurred before any operation, clock, intent, authentication or worker. The corrected carrier reached native preflight with preparation files and an original clock, then failed on the API contract. After Source73 installation a fresh actual `current480` read rejected the retained Source71 acceptance because its allowed set contained only the immediate Source72 parent and current Source73. Source73's installed source acceptance remains valid, but this actual preflight did **not** pass. Source74 is being developed for that authenticated ancestry gap; it is not reported as ready, installed or accepted here.

Original failures, clocks and closed effects are retained; none were reset or replayed. The accepted DSH file and continuation were not repeated. No A0 engineering artifact or contextual continuation has been accepted. Permanent gateway and Dashboard service readiness was verified separately after Source73 maintenance; it is not worker readiness or a new baseline certification.

`PROVENANCE.json` records selected source and evidence digests. Private originals are intentionally omitted. The exported patch digests identify these exact exported bytes, not the original full files or any sanitized substitute. Source custody and deployment-specific bindings remain private technical debt.
