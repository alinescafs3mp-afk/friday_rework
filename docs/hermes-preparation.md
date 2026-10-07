# Reproducible Hermes source preparation

`scripts/hermes_prepare.py` is the source stage of the normal installer. It
exports every tracked file from the pinned Hermes donor, preserving executable
modes and using canonical Git bytes for declared CRLF checkouts. Donor source,
index, history and owner changes are never replaced. Dirty tracked files refuse
preparation; ignored/untracked runtime files and credentials are not exported.

The preparer discovers every shipped Hermes patch manifest, validates its hash
and prerequisites, and applies the complete dependency order. Each declared
output hash and file inventory is checked. A missing manifest, unlisted patch
target, incompatible input or wrong final bytes refuses completion. This avoids
maintaining a second manual list that can omit the web or access-control layer.

Call it with a new destination below an existing private mode-0700 directory:

```sh
python3 scripts/hermes_prepare.py --donor /absolute/pinned/hermes \
  --destination /absolute/private-directory/hermes-source --seconds 120
```

The sibling `hermes-source.source.json` records the original pin, all overlays
and every composed file. Existing destinations are never adopted or overwritten.
On failure, partial output remains inspectable and cannot be resumed by rerunning
the same command. The allowance covers the whole preparation, not each patch.

This command does not install dependencies, activate a profile or start a
service. Its result is **SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED**. Native PM,
Dashboard build and launchers can consume the complete source export without
Git history. The normal installer must still connect protected product profiles,
native authentication, both worker environments and startup ownership; those
steps and the six complete product journeys remain unaccepted.
