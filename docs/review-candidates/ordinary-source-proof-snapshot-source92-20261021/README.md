# Source92 source-proof snapshot

This package preserves a source candidate. `SOURCE.patch` is the new native overlay for `hermes_cli/friday_dashboard_owner.py`; `project/scripts/friday_start.py` is its exact paired project helper. The helper requires the overlay's private `_source_snapshot_identity` API. Treat the two files as one candidate; this package performs no installation.

The candidate keeps each pending proof inside its exact synchronous Context, thread and process. It reuses parsing only for identical receipt bytes inside that unfinished proof, and gives the project snapshot comparison the named-byte digests from the same completed full proof. Pre-effect content, ownership, mode, inventory and receipt guards remain. There is no global cache, TTL or stat-only freshness shortcut.

The historical Source71 review rejected one MED finding: a caught interruption during probe rotation could bypass inner proof completion while eventual outer verification remained. Source72 independent review closed that finding with 90 current-candidate passes, zero failures and no open HIGH/MED findings. These are source review outcomes. Private tests, fixtures, oracles and reproduction material are excluded.

A small primitive speedup does not establish a runtime cure. All thirteen operator source-guard calls remain unchanged. The eleven service-internal guards describe conditional call-path scope, not an observed service count or an end-to-end performance claim.

At the recorded checkpoint, Source91 remained installed, its ordinary native90 start had timed out, a safe stop and separate admin TLS UI restoration had been recorded, and Jarvis was UNSENT. Runtime, full baseline and release were not accepted. Source92 is not installed by this package. Any later candidate or runtime work has its own scope; this snapshot remains source-only.

`MANIFEST.json` pins only the files included here. It contains no private receipt, input, handoff, installed-prefix or runtime-evidence references.
