# Accepted registration-family allowlist source correction

This source package adds the already published registration source identity `1356a9d23d24163690c82920281ff8ee067bcd6143e5d69d5ad85630f1f39dc0` to the two existing source-family checks: the canonical ordinary module and its private install-validation counterpart. The registration import correction and external tester patch were published previously; this package does not duplicate them.

`canonical-budget-source-family.patch` targets `scripts/friday_ordinary_install.py`. `private-companion-budget-source-family.patch` archives the delta of the existing private companion under the relative label `_friday_history_source/friday_ordinary_install.py`; it is not an instruction to rewrite historical records or execute a carrier.

The private equality check becomes an exact two-identity membership check; the canonical membership check gains one identity. The only behavioral change in each module is acceptance of this exact registration source identity alongside the previously accepted identities. The 600-second budget, clock, phase, compare-and-swap and once-only guards remain unchanged. The native121 source has no delta.

| Source module | Before SHA-256 | After SHA-256 |
| --- | --- | --- |
| Canonical ordinary module | `d617fb10f93b2a0e4d5c00b85798b21f75a4ab3abea03a6c996aa6bae0f98fe6` | `b1c08a4ad62f06599e6870be87824f1fe8cf3fc16632ff0a2b322ba76e4af752` |
| Private install-validation counterpart | `88479daf0d669c057ee28f82f2d09148b73054bfc6e4708f2d5243081fa514d9` | `9fffabcbeae3c2da6b6684b18f578b7b9aceea331b760e254d46084c7fba5fab` |

Previously accepted observations are reused without execution for publication:

- R350 source acceptance and AST comparison established that both modules only add the exact registration identity to their membership checks. Its source evidence includes 52 isolated extracted guard controls; these are not full operational acceptance.
- S257 independently accepted the narrow source delta with zero open HIGH/MEDIUM findings.
- A prior fresh-process observation accepted the exact 600-second bound at the guard, before updater or journal execution. That limited observation does not establish an updater or installation result.

The R350 source-acceptance record is identified by SHA-256 `7832d1ac1f7c24f9c93ff07d1075c9efc4ee727dc3f1f047af42f7c41765008e`; the S257 review record by `c2caa1523f5ef5b1f6bd375fd2dd544ba30f103f9e1a34a77b5ba890e7f5784c`. Private evidence and operational inputs are not part of this publication. `MANIFEST.json` records the exact source identities and publication scope.

This package establishes a source correction only. Installation, current runtime and services, actual worker execution, Telegram artifact delivery, continuation in the same conversation and semantic user acceptance are separate facts and are not established here. No execution or test campaign is performed for this publication.

The patches are archives against the accepted beforeimages listed above. At publication base `6b45c080cbcd0dad256fddbb5f8465a00749fe50`, the repository canonical module has SHA-256 `02ca38730d892978e5a7cd7908825420f6b446601a5a4a4ac1fd2b03c2d95842`; it is not this patch baseline. Do not apply these archived deltas as an unreviewed overlay onto that file. Root owns integration and publication.
