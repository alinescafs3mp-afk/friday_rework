# Managed context and memory readers: Source candidate

The managed prompt and memory readers previously checked a pathname and then
opened it again. This candidate reads through the validated descriptor, checks
its identity and the admitted directory chain before returning, and propagates
scope refusals through the real prompt and memory consumers.

Apply `private-context-readers.patch` to the already assembled native Source
candidate **after**
`../core-office-intake-20261018/core-office-native-intake-guards.patch`. The
Office patch is one prerequisite, rather than a complete native candidate.
`native-source-manifest.json` records the required exact before and after
SHA-256 values; refuse application to a different base.
`reader_cases.py` is the portable test source for
`tests/test_owned_context_memory_reads.py`; its fixture comes from the project
`tests/test_user_isolation.py`. This review directory is outside automatic test
discovery and the active native patch/install pipeline. Installation must use a
new coherent candidate and the normal required checks.

Managed reads retain the current principal and generation, open the admitted
home and each directory by descriptor, reject links and invalid file types or
permissions, bound the input to 1,000,000 bytes, and validate the final descriptor
and named identity. Exact SOUL/workspace and native memory target restrictions
remain. Strict UTF-8/BOM and newline handling is preserved. Missing allowed
leaves retain normal empty behavior; revoked, foreign or changed objects cannot
be converted to trusted empty content. Owned descriptors close on normal,
refusal, decode, deadline and caller cancellation exits.

The managed deadline is cooperative between filesystem calls. A regular
filesystem syscall can block beyond that deadline; this candidate does not
claim forcible syscall cancellation. Managed reads use the caller thread and
leave no managed background reader. Unmanaged profiles retain their native
threaded timeout behavior with copied context.

Offline validation used real dependencies and synthetic owned text files:
49 focused tests and one coherent 303-test affected pass (the prior 254 tests
plus those 49), with no failures, errors or skipped cases. The original 254 were
retained. An independent review approved the exact three native files and the
new test source. This is Source evidence only: target-interpreter execution,
installation, runtime isolation, live Telegram journeys and release acceptance
remain unverified. Private acceptance checklists and oracles are not included.
