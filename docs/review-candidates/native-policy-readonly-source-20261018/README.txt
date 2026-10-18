Read-only native policy Source — 18 October 2026

Policy reads previously reached the normal configuration loader, whose current-file
refresh could create a retained last-good backup before a foreign user binding was
refused. This patch routes policy and onboarding reads through the existing
write-free effective-configuration reader. Missing or empty first-run policy layers
remain an explicit opt-in; malformed input refuses. The strict diagnostic contract,
managed precedence and native gateway defaults are retained.

stopped-worker-policy-readonly.patch contains the exact three-file delta recorded
in STATUS.json. The selected preimage hashes are already represented in public
Source manifests or review extracts; that does not establish a complete supported
public prerequisite composition. The active predecessor graph contains unpublished
manifest layers. Its private manifest and fingerprints are excluded. This archive
is inert and the installer does not reference it. Do not apply it to plain upstream
or treat the selected hashes as a replacement for the complete prerequisites.

The accompanying project test changes use the real installer-created completion
marker, native plugin loader and registered provider identity, and native-created
private plugin metadata. The additive regression module checks complete retained
file inventories across valid reads and meaningful refusal paths. These are test
Sources. The existing 350- and 222-case suite memberships are not reduced.

STATUS.json separates Source availability from actual execution. This publication
contains no new runtime or release acceptance. Focused regressions, the complete
canonical suites, package-manager/native gates, supported installation and live
user journeys require evidence for their exact final composition.

Native code derives from NousResearch/hermes-agent revision
781334eea4b9225a3e194faf0c241d9afe218634 in sources.lock.json. The accompanying
MIT LICENSE retains the upstream attribution. Project test sources retain their
existing repository provenance; no new repository-wide license is assigned.
Private control packages, runtime configuration and raw observations are excluded.
