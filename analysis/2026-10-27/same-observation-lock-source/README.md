# Same-observation completion and native-lock compatibility

This is an analysis-only source checkpoint following the existing after-profile
checkpoint. It adds eleven Source3 source layers and three external lock-family
layers, with no edits to active product files. Existing public sources are reused
as patch or replacement beforeimages. Two files are full sanitized replacements
because removed diff lines would repeat old private invocation IDs. The exact payload list, original/exported hashes and byte
counts are in EXPORT-PROVENANCE.json; SHA256SUMS covers this entire directory.

Source3 adds an exact completion path for an already saved A0 observation after
its resources have genuinely settled. It validates the original request/value,
failure, source ancestry and cleanup evidence, retains the failure, then advances
only the permitted metadata phase and settlement. The original observation and
clock remain intact. Two existing plugins change; plugin membership is retained.
Current-source, retained-native and fresh-source consumers are updated together.
This path does not run the worker or model again.

The external lock-family publisher retains nofollow readonly descriptors and
immutable owner/device/inode/group/mode/link and parent custody for all six
existing native config/auth/environment locks before native acquisition. Native
acquisition stamps its PID. After all locks are held, the publisher seals the
exact held PID newline, content hash and full identity and checks this seal while
held. Native acquisition is admitted at that boundary; later rewrite, release,
substitution or metadata drift still refuses. The trusted same-owner native a+
open boundary remains; no new adversarial swap-back defense is claimed.
The native entry also records phase, exception class and traceback code location
without exception text, source lines or frame locals.

## Verified facts and limits at the supplied task snapshot

The selected Source3 was actually installed and accepted by a fresh native source
process. Root then completed the same retained observation, published the real
canonical proof and committed all four metadata links. A fresh installed host
consumer passed for A0 and DSH. These are separate source, completion, publication
and readiness facts. No cold/model/worker replay was needed. Existing permanent
services were reported healthy. The earlier DSH user artifact and follow-up remain
accepted. The ordinary A0 Telegram task was still NOT_SENT at this snapshot;
readiness is not A0 user-result or conversational follow-up acceptance.

The earlier failed metadata operation and opaque exception remain historical
failures with their original clocks. The native acquisition stamp mismatch was
independently reproduced, but is not asserted as the cause of that opaque failure.
Original source and lock-family reviews and their bounded local controls are
reused. New checks here cover export privacy, reconstruction and exact patch
membership only. Counts from overlapping controls are not added together.
The separate native-stop patch and its integration preparation remain uninstalled
source candidates and are excluded from this checkpoint.

## Privacy and reproduction

All code copies are intentionally UNBOUND analysis. Only declared string/comment
substitutions and the deployment GID synthetic substitution differ in their ASTs.
Private paths, invocation IDs, literal digests and deployment identities are
replaced consistently; original and exported file hashes are distinct provenance.
These substituted references cannot authenticate or reproduce the installed
environment. The code/diffs illustrate the implementation; they are not a runnable
distribution or a claim of runtime equivalence. No private raw evidence, receipts,
clock/auth/config/session data, user attachments, oracle, handoff or value mapping
is included. Duplicate templates, generated adapters, operational bind/prefill
scripts and the task-specific ordinary user harness are explicitly omitted.
Unchanged primitive and source ancestry template reuse the prior public copies.

Run `python3 -I -B verify_export.py` from a checkout containing the two preceding
sibling analysis directories. The checker reconstructs the prior snapshot and
these exact ordered patches in temporary storage, validates hashes and Python
syntax without importing reconstructed code, and removes scratch. This verifies
the export; it does not execute product qualification or send a user task.
