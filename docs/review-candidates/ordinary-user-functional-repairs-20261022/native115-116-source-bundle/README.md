# Source115 and Source116: accepted source bundle

These are accepted source changes over the published Source114 chain. The installed version at this checkpoint remains Source114/project303. Installation, runtime behavior and feature acceptance of this bundle are pending.

Source115 adds the scoped native route for a hosted shared room with two to six distinct local profiles. Every member must explicitly opt in and approve its own membership. The route is model-only and uses shared room context; private tools, history, memory and context stay outside it. Revoke/restart and source policy boundaries have 51 scoped controls and independent review. This is source acceptance, not a live group-chat result.

Source116 fixes the actual origin-metadata regression found after the Source114 official reset. The reset already created the new row from its validated admitted source, but published a route that inherited the prior conversation's source. A subsequent ordinary metadata refresh wrote that stale origin back. The one-file fix publishes the same validated creation origin in the new route. Resume and unmanaged inheritance, parent lineage, authority checks and refusal paths stay in the existing lifecycle.

A real isolated native fixture reproduced the unmodified failure through reset, route persistence/reload and ordinary metadata refresh. The final candidate passed 15 selected native controls. An independent reviewer checked the exact delta and ran seven source-isolated checks; the reviewer did not rerun the native 15-case fixture. Failed initial fixture invocations and corrected expectations are retained locally. The actual Source114 failure remains preserved and unaccepted for origin integrity.

The Source116 patch is disjoint from Source115's changed files and preserves its full source chain. One combined ordinary installation package is being prepared for current Source114 directly to Source116, without an intermediate live installation. This document grants no operational authority.

- [Source115 exact patch](source115.patch) and [existing-schema manifest](source115-manifest.json)
- [Source116 exact patch](source116.patch) and [existing-schema manifest](source116-manifest.json)
- [Exact source hashes, checks and limits](facts.json)
- [Actual Source114 runtime and remaining failure](../native114-runtime-reset-memory/README.md)

Apply patches in 115 then 116 order over the accepted Source114 chain at the manifests' upstream base. Public filenames are shorter aliases of their manifest-declared paths; preserve the declared paths when staging an actual source bundle. Existing upstream provenance and license obligations remain. Private operational inputs and conversation evidence are excluded.
