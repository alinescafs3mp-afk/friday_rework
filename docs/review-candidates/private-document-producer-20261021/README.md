# Private document cache producer: cumulative B17 + B18 source repair

`SOURCE.patch` changes only `cache_document_from_bytes` in
`gateway/platforms/base.py`, against the exact Source90 original identified in
`MANIFEST.json`. It includes both accepted steps, rather than only the final B18
increment. Apply with `patch -p1 < SOURCE.patch` in an exact matching source copy;
the resulting file must match the candidate size and SHA-256 in the manifest.

The original producer used `Path.write_bytes`, so a permissive umask could create
a document with mode `0664`. The unchanged strict re-home consumer refuses such a
file. The intermediate B17 repair created files with `0600`, but an `os.open`
failure still fell back to the original write and could return false success.
The cumulative repair creates new files with owner-only mode `0600` from creation
and propagates a secure-open failure instead of using that fallback. It preserves
the existing `O_TRUNC` behavior and leaves the strict consumer unchanged.

## Evidence and limits

This packet summarizes existing accepted source-only evidence. Packaging reran
only hash, lineage, patch reconstruction and publication-content checks; it did
not rerun the behavioral controls or execute the product.

- **Author controls:** 21/21 candidate expectations met, including private
  creation, fail-closed secure-open behavior and unchanged consumer checks.
  The intermediate-source run also met 21 descriptive expectations, including
  reproduction of the unsafe fallback; this is not a product pass.
- **Independent controls:** 29/29 candidate synthetic expectations met using
  independently authored controls. These cover producer/routing, full synthetic
  re-home/publication and idempotence, four secure-open fault cases, tampering,
  provenance and file/directory restrictions. Capability admission was stubbed;
  this does not establish genuine admission or live delivery. The independent
  original/intermediate runs had 20/28 descriptive expectations, respectively,
  and are not added to the candidate result.
- **Original live failure:** its first inner exception is
  `NOT_CAPTURED_MASKED`. The `0664` incompatibility was deterministically
  reconstructed; it is not a captured original inner trace or proof of the
  first or only live cause.
- **Failure phases:** no newly created artifact is guaranteed only when secure
  open fails before creation. A mid-write `ENOSPC` can leave partial private
  bytes and raises without success; this patch does not provide atomic cleanup.
- **Inherited INFO:** forced-name collisions and same-UID alias/exchange writes
  remain. Existing file permissions are not repaired by passing a creation mode.
  Consumer refusal cannot undo earlier producer writes. No remote exploit was
  established by these mechanical controls.

The 21 author and 29 independent expectations are separate evidence sets. They
are not a combined 50-test result, and synthetic controls are not live checks.
No fixtures, private oracles, raw traces or private event identifiers are shipped.

## Source100 overlap and integration boundary

Frozen Source100 already contains a different implementation:
`open(filepath, "xb", opener=lambda p, f: os.open(p, f, 0o600))`. It uses exclusive
creation and propagates errors, so it overlaps this repair while additionally
refusing existing-file collisions. This Source90 patch is a source-only
alternative; do not blindly transplant it over that implementation or replace a
Source100 module with this different Source90 module. Exact Source100 hashes and
the limited comparison scope are recorded in `VERIFICATION.json`.

The existing independent Source100 comparison exercised 28 expectations for the
selected producer with matching selected Source90 dependencies and the Source90
consumer. It was not full Source100 construction, admission, startup or live
execution. Source100 has additional module/lifecycle and consumer owner-binding
differences; that comparison grants no whole-tree integration approval.

This packet installs nothing and claims no live cure, startup repair, genuine
capability acceptance or release acceptance. Integration needs its own coherent
source/receipt checks and actual runtime validation. The Kimi caption candidate
and B07 findings remain unresolved by this patch.
