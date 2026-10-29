# CORE administrator and settings delta — source checkpoint

This extends the earlier source checkpoint from `1676955354ee10604cdde106982492dc73638310` to `0d1167e7cf54b183f8d6795550a14b1110ddafda`. Apply these two patches after the original checkpoint patches; they are review material, not an installer.

The delta gives administrator metadata reads an explicit, request-scoped authority lifetime, checks the same native scope through retained-store operations, and connects onboarding and Dashboard consumers to that contract. It also preserves supported private-lock modes and uses typed settings values in the UI. The original operator-scope failure and subsequent local corrections remain recorded; a source fix is not a live acceptance result.

Focused final-delta observations: 62 operator/retained controls, 3 skills/revocation controls and 25 shared association regressions passed. These are separate affected checks, not a complete user baseline. Earlier observations and failures remain described in the parent checkpoint. Publication itself reruns no product tests.

This CORE candidate has not been installed. The running system still uses the separately accepted Source95 build. Real Telegram document acceptance and the full existing KIMI-B00 user baseline remain pending. Existing DSH results and contracts are retained; A0 remains deferred. No model, endpoint or infrastructure changes are part of this delta.

The patches contain only repository sources and synthetic test fixtures. Private task records, runtime identities, credentials and owner-only oracles are excluded. Parent Hermes license and attribution notices continue to apply.
