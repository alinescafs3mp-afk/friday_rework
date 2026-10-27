# Worker web-policy expiry: installed narrow correction

The ordinary DSH request reached `friday_work`, which refused before reserving a new worker job. The configured policy had expired at 10:00 MSK; the call occurred at 10:20:12. The original catch did not preserve its exception traceback. The unchanged source/configuration and a read-only replay of the real consumer establish the expired-policy barrier; an original traceback is not claimed.

The attached single-file patch adds one explicitly published, protected expiry successor. The predecessor path/hash, policy content and types, runtime identity, boot and network namespace remain fixed. Only the expiry may advance, for a finite grant of at most 24 hours. Missing, revoked, future-issued, changed, linked or unprotected grants refuse. There is no automatic renewal or new service.

The patch is installed. The existing DSH readiness receipt now pins the changed module; the A0 receipt also restores its two stale host-source pins. Original preparation/qualification evidence remains intact. Fresh installed-process checks of both consumers passed. Gateway and Dashboard were restored under existing permanent management.

Validation: 20 focused producer/consumer checks, including real DSH/A0 read-only replay, plus seven independent delta checks. Counts are reported separately. A checker initially omitted the existing AdapterError from a negative expectation; its observed refusal was preserved and the checker corrected, with no product change.

The old DSH request closed after its original 600-second capture. It produced a text reply, no verified artifact and no new DSH execution. Its partial archive remains unaccepted. A distinct, authorized missing-stage continuation is in progress with the preserved full sources; actual worker completion, verified delivery and contextual continuation remain pending. Source installation and service readiness are not product acceptance.

Patch SHA-256: `3512660641a33e491bca4062c25a30f44a90ac03d56954c810d91684729af2c5`.
