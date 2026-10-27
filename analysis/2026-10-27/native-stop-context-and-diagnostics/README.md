# Native stop context and bounded diagnostics

The native control callback now retains the same admitted user capability when cloning its source and explicitly enters that scope while invoking an existing plugin handler. This closes the demonstrated busy-control context gap; it does not mint new authority or relax ownership, consent, revocation, lease or transport checks.

Control failures now retain a bounded private diagnostic: phase, allowlisted exception class/source locations, and a request correlation digest. A missing receipt is explicitly marked `local_only`. Exception messages, arbitrary names, user text and credentials are excluded. The original cleanup attempt runs before diagnostic I/O; existing DSH asynchronous diagnostic behavior is preserved.

The earlier real idle `/stop` refusal remains unexplained: its exception details were not captured. The observed reservation remained unsubmitted and unchanged. These source changes do not establish that its cancellation or a Telegram worker result succeeded.

## Validation and installation

- Native context change: 17 grouped offline checks, including six native-capability checks, exact patch verification and independent source review. Fixtures are not live authentication acceptance.
- Control diagnostics: 103 isolated checks through the installed native interpreter. Two review findings were corrected: cleanup ordering and preservation of DSH exception classification; the correction was independently checked.
- One protected source update installed the two native files and the plugin change. Fresh installed consumers accepted the A0 source lineage and the complete 324-file DSH project graph. The isolated physical preflight and the real installation are distinct evidence.
- Gateway and Dashboard were restored in fresh processes under their existing permanent management; HTTPS verification passed. No successful cancellation, worker execution, delivered artifact or full product readiness is claimed.

These patches are published analysis material. The runtime is maintained from the checked private source generation; this directory is not an automatically applied layer. Private task data, receipts, session references and admission records are intentionally absent.
