Source90 installation and portable artifact checks, 2026-10-17.

The previously published Source90 source was actually installed. The successful
native command had completed when its exit was observed at 18:37:50 MSK.
The combined stop, capture, unchanged
resource proof and Source command used 594.454 of the original 600 seconds.
The Source command had its own preserved 180-second limit; its exact standalone
elapsed time was not recorded here. These limits must not be conflated.

The installed receipt contains 90 layers and 17710 files. Its canonical complete
files fingerprint equals the fingerprint already published in the Source90
checkpoint. A later finite observation reread all canonical source bytes and
checked their modes. The source commit journal explicitly reports
SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED. The gateway and workers were not started by
the source transaction. PM completion, live model/network/Telegram behavior,
UI acceptance and full product acceptance are outside this checkpoint.

The subsequent PM preparation parent refused before publishing its dispatch
intent. No public source refresh or manager-import command was dispatched.
Its exact cause is still under diagnosis; the source installation remains
committed, and consumers remain stopped. A separate read-only full warm
preflight passed, which does not establish the cause of that earlier refusal.

Two original portable validation functions capture problems found during this
work. The inventory check preserves the observed permission mode and checks the
Git executable bit: 100644 permits a preserved 0600 file as well as 0644. It still
refuses mode changes, byte changes and missing inventory entries. The cache-body
check compares the entire payload to exact-source compile serializations,
including an explicit owning-reference form needed by CPython 3.14. It never
loads untrusted marshal data or executes compiled source. Filename provenance,
PYC headers, ownership, links and race protection remain caller obligations.

These helpers are an observational source proposal. They are not connected to
installation or PM and confer no runtime admission. Eleven disposable regression
tests passed on both CPython 3.14.4 and the installed SDK CPython 3.14.7.
Ten existing public
Source89/90 identity tests also passed. Historical private SDK results are not
claimed for this newly extracted implementation. Root review and any additional
version-specific checks are required before adopting it in a production path.

Reproduce the portable regression suite from the repository root:
  python3 -B -m unittest discover -s tests -p test_source90_artifact_checks.py
  python3 -B -m unittest discover -s tests -p test_ordinary_source89_90_identity.py

The raw installation evidence and host-bound control scripts are withheld.
This report retains only source-level fingerprints, finite timing and explicit
scope. No private account, session or filesystem identity is published.
