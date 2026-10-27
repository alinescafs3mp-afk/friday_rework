# Historical nested native-input reader — 27 October 2026

Source-only analysis export of the accepted S411 private adapter correction.
[reader.patch](reader.patch) targets a private historical reader absent from this
public repository. Its four private reference constants contain symbolic path
and digest placeholders: it is not applicable as a public runtime installer.
No private paths, account identifiers or saved native-file contents are included.

## Exact retained-file mapping

After the accepted R476 repair, a historical preparation still named the original
A0 native-input manifest by its old path and digest. R477 followed that reference
to the repaired current file and rejected its changed digest before worker startup.

The correction validates the accepted repair with its pinned strict validator,
checks the original and retained-copy references against that proof, and requires
the historical preparation to contain the exact original reference once. It adds
one reserved alias keyed by the original path **and** digest; caller-supplied
aliases and unrelated historical references remain rejected. The inventory reader
requires that exact retained row before admitting it into the cloned preparation
reader. Native custody and digest checks still apply to the retained bytes.
The current preparation and manifest remain separately checked. There is no
wildcard path trust and no reuse of the historical digest for the current file.

All code changes are preserved in the patch; only the four added private
reference constants are redacted. The original and retained manifest use the
same symbolic digest because the accepted beforeimage is byte-identical.
Placeholders are explanatory, not values to resolve from an arbitrary host.

## Reused evidence and limits

The accepted source package records 12 positive checks and 9 negative checks,
including genuine cached historical and current preparation consumers. Negative
controls cover changed paths/digests, extra reference keys, foreign aliases and
the original reader's reproduced failure. Independent review accepted the exact
reader below, followed by Root source-only acceptance.

These checks used bounded cached IO mappings and a documented `private_check`
test seam for exact logical membership and physical custody. They did not execute
the full live inventory. This export reuses the accepted evidence; it does not
repeat source tests, read live native-file contents or perform runtime effects.

R476 was actually installed and accepted by a fresh installed deployment-contract
consumer. At this export's checkpoint, the following R478 qualification was
running and not yet accepted. Neither new DSH/A0 Telegram file task had succeeded;
source acceptance does not establish worker or end-to-end readiness. The R477
failure remains recorded in the
[operational observations](../../worker-web-service-source.md#subsequent-installed-state).

## SHA-256 provenance

The original sources and evidence remain private. These hashes identify the
accepted bytes; the redacted patch has its own distinct hash.

| Material | SHA-256 |
| --- | --- |
| Original private reader | `3e43acf1fe2edec8490cd0425951c8e1818bff4c0eb68d34ec054dbcc77c0e30` |
| Accepted private reader | `8ed2e9cff88217b016f99bff1d47b07f154a68196b01e0f4dd27d4f1bd745eb9` |
| Exported redacted `reader.patch` | `850e5b8626d13b62becdf22857cdb9946d52ca791da0ebb5a1ad7b431562b3aa` |
| S411 source result | `096136707475004028c43f31c25cce28d2f853e73c5ff3379ec6bdb22e0be26a` |
| Independent reader review | `a4e0eaf697396541087e3d9cbe09d8c33d49ede0a5ef96ac2cb83d3e7f098180` |
| Cached preparation checks | `f969919497728de44e670f60555fa187cb17c8c44a1dfa5d0057a6f8ac17416f` |
| Root source-only acceptance | `a2038627ca4b328e9e9af3c598ea0e24b0577c3a9185f5dcc3cdb72626a95efb` |
