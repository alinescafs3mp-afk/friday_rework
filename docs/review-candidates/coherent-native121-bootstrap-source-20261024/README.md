# Coherent Native121 bootstrap — source-only review material

Date: 2026-10-24 (Moscow). This package publishes the accepted S243 source delta.
Installation, installed physical verification, runtime and user acceptance remain
separate facts. Root's subsequent pre-install capture refused legitimate historical
file metadata before any source update was dispatched; the finding is recorded below.

The combined [project patch](project-native121-bootstrap.SOURCE_ONLY.patch) changes
exactly five existing product files from the C287 normal composition to S243 final:
`associations.py`, `onboarding.py`, `runtime_process.py`, `friday_install.py` and
`friday_ordinary_install.py`. Full paths, byte counts and before/after SHA-256 pins
are in [PROJECT-DELTA-MANIFEST.json](PROJECT-DELTA-MANIFEST.json). The patch changes
content only. Authenticate all five complete preimages before considering it;
context matching or a successful fuzzy application does not prove the right base.

This combined project delta supersedes the earlier
[two-file project candidate](../readonly-native-policy-r301-r302-20261024/project-readonly-policy.SOURCE_ONLY.patch).
That earlier patch ends at intermediate associations/onboarding bytes. Do not
stack this C287-based delta after it. Earlier candidate documents preserve their
then-pending bootstrap result as history.

The new onboarding default uses strict Native121 read-only APIs. A separately
mutation-authorized source update can explicitly select `storage_readonly=False`
to use genuine Native120 APIs already imported in its current process. The flag
does not grant mutation authority and there is no fallback from a failed strict
read-only check. Replacing native files does not reload imported modules. Final
strict verification requires a fresh process importing genuine installed Native121.

The source ordinary installer shares authenticated history facts only within
one finite invocation, rechecking their exact byte and filesystem custody. Its
scoped deadline preserves the original operation clock, stop/reap and owned
restoration obligations. The existing physical route can retain an accepted
ancestor, a standard COMMITTED-only intermediate and a distinct new update with an
actual integer zero return. A COMMITTED intermediate is not fabricated acceptance.
No private operational bindings or snapshots are published.

The unchanged standard Native121
[manifest](native121/readonly-native-policy-source121-manifest.json) is included
byte for byte (SHA-256
`9d7cd4c7d2d9cf71e855b2d9c6265f9552eed3be3b6ab18eb4edf5c226ed83a3`).
Its exact [native patch is already public](../readonly-native-policy-r301-r302-20261024/native-readonly-policy.SOURCE_ONLY.patch)
(SHA-256 `e5afa4379cfd1981accba0080cf13c5d3f3d64306586aef281ca9c80aaee73e5`).
The manifest retains its canonical `patches/hermes/readonly-native-policy-source121.patch`
assembly reference and all 120 prerequisite patch pins; the link above is its
publication location. The two standard assets add layer121, changing eight native
files and adding none. The accepted normal source inventory contains 318 project
files / 47 plugin files and 17717 native receipt rows; the original donor export
count remains 17590. These are different counts with different meanings.

The accepted source review and unchanged controls are reused. Publication checks
only authenticate the five-file patch's exact forward/reverse result in owned
fixtures, bad preimage rejection, standard asset identity and public sanitization.
Source imports and implementation suites were not rerun. The original R289 `-15`,
R293 `1`, R294 FAILED and distinct R297 `0` COMMITTED-only observations remain
recorded in [SOURCE-FACTS.json](SOURCE-FACTS.json); no historical effect is replayed.

Optional warm support remains OFF: its 328/49 source map is distinct from this
normal candidate, and four future native proposals remain UNAPPLIED. No complete
warm candidate or full warm native acceptance is claimed.

A subsequent actual Root capture (R310) exited with code 1 and was reaped before
updater dispatch. The new HistoryWalk rejected 17 legitimate owned, single-link
regular history files with mode 0664 beneath the canonical private home (0700).
Every one of those 17 files still matched its original expected SHA-256. No history
file was changed to satisfy the reader. No new update transaction was created;
the installed Native120, source marker, selected configurations and existing
canonical commit remained unchanged. Native120 configuration initialization
metadata syscalls during import are not excluded by this observation.

This is a known compatibility defect in this source snapshot, missed by its cache
fixtures and source review. A scoped source correction is underway; no corrected
source or successful actual capture is claimed here. R310 is closed under its
original clock. A future corrected installation requires its own finite lifecycle.

This directory contains no installer request and gives no execution authority.
Actual Native121 installation, complete installed physical/read-only checks,
180-second operation fit, services, runtime and model/user semantics are pending
a future corrected operation. The R310 refusal above remains an actual failed
pre-install capture, not a source-update attempt or successful installation.
[SHA256SUMS](SHA256SUMS) covers the files in this directory except itself.
