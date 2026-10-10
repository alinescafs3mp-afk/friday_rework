# Connected daily-use checker source coverage

This publication adds retained checker source bodies to the existing [setup and soak evidence](../soak-setup/README.md). It is a source export, with no new checker run, runtime admission or acceptance. The [source index](source-index.json) records exact executed-source hashes, exported hashes, byte lengths, literal transformations, reused public bodies, and source-provenance gaps. The [manifest](manifest.json) pins this package.

Original author R1 has88 controls; corrected R2 has133 (88 retained +45 new). Original Sol review has248 passes and six missed required refusals: it rejected R1. Corrected independent Astra acceptance has413 controls, split into375 main controls plus38 supplemental controls. Initial author setup9 and independent byte-consumer21 remain separate; the private demonstration has eight separate controls and was never integrated or accepted. None of these counts are summed or promoted by this export.

The retained [failed accounting observation](retained-harness-failure.json) records a private reviewer harness attempt that stopped at an incorrect unique-name assertion after its controls. Its repair uses occurrence-aware Counter accounting for two existing duplicate labels with distinct mutations. The final repaired checker and any separately retained original attempt are identified individually in the index; the observation is not erased and the failure is not represented as a product defect.

New programs are non-importable `.py.txt` analysis artifacts. They have not been executed here. Only concrete private path literals are replaced with explicit `/PUBLIC_LABEL/` names, with exact transforms recorded. Algorithms, assertions, budgets and counts remain unchanged. Existing published source bodies are reused by exact hash. A source unavailable in the exact evidence package is explicitly a provenance gap; no reconstruction is passed off as the executed program. Synthetic receipt values are test data, not credentials. Raw archives, input payloads, owner handoffs and private installation documents are excluded.

The exact original failed reviewer attempt and supplemental38 source were recovered from retained literal tool-command bodies, without reconstruction or execution. The original [packaging failure](retained-packaging-failure.json) is also retained: the exact-six author checks passed, then the same invocation exited1 because its import created private bytecode. Its separate packaging correction removed that captured bytecode and produced the unchanged reviewed package. Sol's exploratory probes remain excluded from independent totals. These original source-command bodies are separate rows in the index.

| Program | Source coverage | Original role |
| --- | --- | --- |
| r1-test_daily_planning | [REUSE_EXACT_PUBLISHED_BODY](../soak-setup/rejected-source/test_daily_planning.py.txt) | author88 rejected-candidate controls |
| r1-validate_daily_data | [REUSE_EXACT_PUBLISHED_BODY](../soak-setup/rejected-source/validate_daily_data.py.txt) | rejected validator |
| r2-test_daily_planning | [REUSE_EXACT_PUBLISHED_BODY](../../../validation/test_daily_planning.py) | author133 controls (88 retained +45 new) |
| r2-validate_daily_data | [REUSE_EXACT_PUBLISHED_BODY](../../../validation/validate_daily_data.py) | accepted corrected source validator |
| normal-consumer-inputs.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/inputs.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-artifacts.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/artifacts.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-admission.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/admission.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-adapters-contract.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/adapters/contract.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-adapters-dsh.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/adapters/dsh.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-boundary.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/boundary.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-host.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/host.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-host_runtime.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/host_runtime.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-__init__.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/__init__.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-associations.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/associations.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-supervision.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/supervision.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| normal-consumer-worker_web.py | [REUSE_EXACT_PUBLISHED_BODY](../../../plugins/friday_rework/worker_web.py) | exact frozen input-consumer implementation/dependency; byte staging and pure brief/content only |
| sol-independent-r1 | [NEW_INERT_SOURCE_EXPORT](sources/sol-independent-r1.py.txt) | independent rejected R1: 248 passes and six missed required refusals |
| sol-minimal-correction-demonstrator | [NEW_INERT_SOURCE_EXPORT](sources/sol-minimal-correction-demonstrator.py.txt) | private demonstration driver, eight separate controls; never integrated or accepted |
| sol-demonstration-validator | [NEW_INERT_SOURCE_EXPORT](sources/sol-demonstration-validator.py.txt) | generated private demonstration validator imported by the eight-control driver; not corrected accepted product |
| astra-independent-r2-main | [NEW_INERT_SOURCE_EXPORT](sources/astra-independent-r2-main.py.txt) | 375 main independent controls; part of original413 =375+38, repaired accounting body |
| author-initial-setup9 | [NEW_INERT_SOURCE_EXPORT](sources/author-initial-setup9.py.txt) | nine original author initial setup checks; no runtime isolation or worker acceptance |
| independent-input-consumer21 | [NEW_INERT_SOURCE_EXPORT](sources/independent-input-consumer21.py.txt) | 21 original independent byte-consumer checks; setup gap retained, synthetic inputs only |
| r2-failed-accounting-attempt | [NEW_INERT_SOURCE_EXPORT](sources/astra-original-failed-accounting.py.txt) | original failed private accounting attempt; exit1 at unique-name assertion; no completed result |
| r2-supplement38 | [NEW_INERT_SOURCE_EXPORT](sources/astra-independent-r2-supplement38.py.txt) | 38 exact original supplemental independent controls; accepted413 comprises375+38 |
| root-exact6-invocation | [NEW_INERT_SOURCE_EXPORT](sources/astra-root-exact6-and-failed-packaging.py.txt) | six exact author regressions passed; same original invocation then exited1 on generated bytecode in packaging |
| root-packaging-correction | [NEW_INERT_SOURCE_EXPORT](sources/astra-root-packaging-correction.py.txt) | original packaging correction removes only captured private bytecode and freezes unchanged reviewed package; no checker controls |
| sol-exploratory-invocation | [NEW_INERT_SOURCE_EXPORT](sources/sol-exploratory-probes.py.txt) | original exploratory probes; duplicated cases excluded from independent totals |

The original pre-soak validator is already published in ancestor commit `66e57c147649979a7794c5c323c409a385cb79f7`, path `validation/validate_daily_data.py`; its exact hash is in the index. This historical body is not equated with the corrected current validator.

G7 remains consumed FAIL; G8 is prepared with the owner terminal still pending. Kernel120 is NOT_GRANTED; normal3600 is UNSTARTED. Original budgets, stop exclusions, FAILs, null runtime observations and the existing UNKNOWN preview-index drift remain unchanged. Same-UID setup modes do not establish kernel write isolation.
