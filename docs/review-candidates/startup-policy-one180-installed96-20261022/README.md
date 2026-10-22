# Temporary ONE180 startup policy — source review candidate

This inert review package proposes an explicitly selected 180-second startup experiment on the Source96 baseline. The ordinary absent-policy path remains 90 seconds. The owner authorized one test, not a permanent default. The setting itself does not enforce one-shot custody or grant launch authority.

`native.patch` changes only the unit renderer and managed credential bootstrap. The exact string `HERMES_FRIDAY_STARTUP_TEST_SECONDS=180` adds `TimeoutStartSec=180s` and the matching unit environment. Absent policy preserves the original renderer; all other values are rejected. Managed profile dotenv may not persist or override this key. Type, notify behavior, watchdog30, stop70 and restart policy are preserved.

`project.patch` changes only ordinary start and containment. Explicit180 selects command210 plus proof60. A strict caller floor271 and a second check after binary verification refuse an insufficient full command window before pipe/manager effects. The proof deadline stays capped by the inherited absolute deadline. The original root600 budget and child438 binding remain required; outer162 is reserved once. No clipped210 command or fresh outer clock is introduced. Default waiter90 and existing clipping remain unchanged.

`native-manifest.json` contains only the two source-file identities and patch digest. It is a review manifest, not a complete install/composer manifest. Apply native.patch to the exact composed Source96 files named by their before hashes; the upstream base_commit alone is insufficient. Apply project.patch to the exact project265 files named in validation.json. Full native bodies and operational receipts are excluded.

The four-file candidate has 31 previously passing author scenarios and four additional independent Sol controls, with source-only acceptance and zero open high/medium findings for those four paths. Existing composition checks verified the 17,710-file native and 267-file project trees. This publication preparation reuses those results and performs static packaging checks; it does not rerun them. Source95 flush fixes and Source96 observations remain intact. S115 owner optimization is excluded and is not a gate. Historical Source96 FAIL3 remains separate from this candidate. No deeper startup cause is established as solved.

As of this package, actual installation, startup, loaded-unit verification and genuine Telegram/persistence/followup are all **NOT_RUN**. Source review is not runtime acceptance. Any actual attempt still needs the existing exact request, stopped-unit install, original budgets, once-intent custody, loaded180/type/watchdog/stop/restart/fragment/drop-in/Exec checks, and owned stop/cleanup. Reversal regenerates the admitted unit with the knob absent under stopped custody, reloads it, and verifies baseline unit identity and loaded90.

## Portable focused tests

`focused_tests.py` retains the author's 31 tests and finite fixtures. Only input/output path handling is adapted. It extracts selected source functions with AST and supplies explicit collaborators; it does not import product modules or launch services. The portable copy was parsed but **not executed** during this packaging task.

Prepare copies of the exact baseline and candidate files outside a live installation. Copy `harness-inputs.example.json` to a local input manifest and set its relative paths accordingly. The baseline native directory must additionally contain `hermes_cli/friday_ordinary_gateway.py` (SHA256 `140ea75cb19f3537da619bb213d1fa02ce3233dc614e7f7598a615e2598b0920`), which the unchanged restart-input tests read. The harness verifies baseline hashes; candidate before/after identities are in validation.json. Use a writable, separate scratch output directory:

```sh
python3 focused_tests.py --inputs harness-inputs.example.json --output-dir /tmp/one180-focused-output
```

The example input files are intentionally not bundled. The Linux harness retains its original two-CPU affinity, 1GiB address-space, CPU240 and file64MiB limits. Its JSON result records fixture execution only. No unchanged full suite, actual installed renderer, live startup or Telegram result is implied.
