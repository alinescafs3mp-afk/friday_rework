# Deferred source: native retry history and ingress

This source-only S429 patch is not installed and does not gate the current first worker result. No live retry or old user task was executed for this package.

Plain-text retry now uses the existing durable rewind/archive operation with lease and payload/CAS checks. Replay clones the current native command event, preserving source, update, reply and hidden ingress identity; its outer attachment-receipt mapping is copied so later cache additions cannot mutate the original event. Composite and missing/unsafe proof guards remain in force.

Validation: 20 final focused contracts; 59 unchanged controls reused. Two old test expectations were adapted to archival behavior. Independent source review passed; Root integration and actual runtime acceptance remain pending. The initial receipt-map alias finding and checker setup failures are retained in private evidence; the corrected source was checked without replaying a live effect.

Patch SHA-256: `0f4d77cefbd3d32d2c3c691c1cfb4b8f8c1d36479c8008a5504ece4d0411f12f`.
