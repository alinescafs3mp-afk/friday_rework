# Ordinary CLI restart admission: reviewed source candidate

The existing CLI restart-admission check rendered its expected systemd unit by loading full gateway configuration before channel secret scope existed. That path could re-enter restart admission. This candidate reads and validates the deployment configuration, binds its hash and existing configuration contract, and passes the validated watchdog value to the existing unit renderer. The normal renderer path remains available to its other callers.

The four repair hunks were already present in the prepared Source100 composition. This patch reproduces them against the exact Source90 beforeimages recorded in [MANIFEST.json](MANIFEST.json). Independent review confirmed the exact hunks, preservation of unrelated syntax trees and all 37 existing require checks, with 75 isolated controls. The author recorded 49 connected controls and eight source-corruption controls. These counts overlap in purpose and are not a combined coverage total.

This is source preparation only. It is not installed, and no live CLI restart-admission pass is claimed. The separately observed native graceful exit succeeded, but its replacement exceeded the notify-startup deadline. The actual startup cause remains unproved; this CLI repair is not evidence of a startup cure. The prepared Source100 files have different beforeimages and must continue through their existing coherent composition and deployment path.

No private test oracle, acceptance definition, operational identity, credential, raw transcript or deployment command is included.
