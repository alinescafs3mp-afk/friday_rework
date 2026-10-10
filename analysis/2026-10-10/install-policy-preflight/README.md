# Refuse unusable web policy before installation work

The previous installer checked the DSH declaration's file hash but deferred its
contents and expiry to worker qualification, after preparation and builds. The
retained installation input contained an expired declaration. Updating source
hashes alone would therefore have allowed avoidable work before refusal.

The [ordinary worker settings validator](../../../scripts/worker_install.py)
now calls the existing protected web-policy parser during initial installation
validation. Home/profile mismatch, expiry, malformed input and nonprivate policy
files refuse before command planning or installation-home effects. Pin drift
continues to use the existing diagnostic. The declaration remains permission
data; real namespace and DNS/TLS checks still establish connectivity.

Ten author checks exercised the actual pure consumers. Independent review passed
33 product checks and found a regression in eight new test bodies: they expected
an absent installation marker although their existing fixture creates it. The
repair preserves the full before/after byte comparison and removes that false
expectation. All eight repaired bodies then passed without repeating the 33
checks of unchanged product code. The full native fixture suite was not run.

The first author fixture also needed its synthetic Harness destination adjusted
after moving its synthetic home. The first reviewer fixture attempted to
overwrite its own read-only policy. Both refusals and their corrections are
retained privately; neither involved native installation or worker execution.

| Stage | Evidence in this checkpoint |
| --- | --- |
| Source | Validator and regression tests integrated |
| Configuration | Existing profile, endpoints and limits preserved; old expired policy unchanged |
| Wiring | Existing `spec_checked` calls the validator before install effects |
| Offline verification | 10 author checks; 33 independent product checks plus 8 repaired test bodies |
| Live execution | Not run; original runtime admission requirements remain |
| Release acceptance | Unaccepted; all seven journeys and four web contexts remain required |

The clean 103-file input snapshot must be rebound to the changed validator.
A fresh protected declaration and actual execution admission are still needed.
No old installation attempt, deadline or receipt was reset.
