# Accepted worker source corrections

This package contains two exact patches against the accepted base identified in
`SOURCE-MANIFEST.json`:

- Worker preparation recognizes an authenticated fresh secondary profile in a
  shared source bundle. Existing replacement rules remain in force. Native
  admission, exact profile binding and generation, source provenance, current
  configuration, and absent worker/transaction state are checked before creation.
- Ordinary history reading tolerates only modification/change timestamp changes
  on the exact shared home root during active custody. Device, inode, ownership,
  mode, link count and size remain checked through held, named and path proofs.
  Private descendants retain all nine identity fields; leaf hash, link, path and
  cancellation checks remain unchanged.

The target has 318 project files, including 47 plugin files: two changed files,
316 unchanged files and no added files. Native source remains version/layer 121
with 17,717 files and the unchanged receipt hash recorded in the manifest.

Source review was accepted with zero open HIGH/MEDIUM findings. Existing source
review and controls were reused; this packaging step applied each patch to an
authenticated disposable base and checked the exact accepted output bytes. It
did not rerun the historical test suites.

Apply each patch from the matching project root using `patch --batch --forward
--fuzz=0 -p1 -i <patch-file>`, then verify the two after hashes in the manifest.
`SHA256SUMS` covers every other public file in this package.

Installation status: not asserted by this source package; current physical
acceptance is recorded separately.
Runtime status: not asserted by this source package; it requires separate
current observations.
Telegram worker tasks and same-conversation continuations: `NOT_RUN` by this
package; actual returned artifacts and execution evidence remain required.
The full product scope remains open. Publication alone does not activate workers
or authorize an updater.
