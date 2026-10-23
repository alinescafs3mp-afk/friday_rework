# Product API Origin guard — source120 / project316

Source-only S220 successor to the [coherent project316 package](../coherent-memory-guard-project316-20261024/README.md). The S219 synthetic fixture showed an authenticated unsafe cross-origin product API write could mutate synthetic state. The final patch rejects explicit foreign Origin and browser cross-site intent for writes. Trusted dashboard authority comes from the native configured launch origin, never the selected target profile URL. Launch-home context is reset in `finally`. Native clients omitting Origin remain compatible unless they declare cross-site intent. This is scoped evidence, not a complete CORS/CSRF audit.

`product-api-origin.patch` is the exact 1,534-byte accepted S219 v4 patch (SHA-256 `e8822f19ad6f070ba8e64b49528765d4cc98f293001e3cf041e7a0dc1bd4dc58`). Apply with `patch --batch --forward --fuzz=0 -p1` only against the exact API preimage. Packaging replay used a cache-only temporary API copy and removed it afterward; no functional suites were rerun.

| `plugins/friday_rework/dashboard/api.py` | SHA-256 |
| --- | --- |
| Before | `da5e980b4aec953beca5ddb7b1188bf757021cca3b6ba0481e1d51851b608398` |
| After | `ba2084c206827957a25111d13867547ac725f7670fe7964b8c711abd038250a9` |

The coherent source composition has 316 project files: one changed, 315 unchanged, zero added; 47 plugin files. All 26 API route contracts, 57 compiled UI assets and native source120 (120 layers, 17,717 files) remain unchanged. All nonproject maintenance-input fields and the native receipt/stamp are preserved. These are source-composition facts, not installed-tree verification.

Evidence scopes remain separate:

- S219: 28 backend direct controls; 30 combined compiled React/UI, SDK, ASGI and tooling checks; six independent changed-area controls. These covered synthetic state and genuine native ASGI routes without entering lifespan.
- S216: 22 retirement-browser assertions and five direct groups reused without rerun; not added to S219 counts.
- S220: source metadata and selected pure production-function checks only. These do not establish installation, full ASGI lifespan, a new UI run, native TCP/TLS deployment or a full admin pass.

At preparation, the separately recorded installed R169 project316 still contains the old API preimage. The S220 API successor is **not installed**. This package changes no service and claims no user READY status. Installation, runtime and semantic user acceptance remain separate facts.

Known limits remain: eight optional bundled-plugin asset 404 responses; sequential Basic-login controls do not establish a concurrent multiaccount host; profiles API is read-only and there is no arbitrary user-create UI. Product metadata writes do not replace native grants or complete onboarding. Full admin, TLS and live-user acceptance remain open.

Source evidence SHA-256 pins: S219 recipe `c8b9abd0f859bd026e0f5ea9fba25add664696ddfd6a7b9fb3f7a09f03997594`; S220 recipe `da56158099cb29c1b6c3d29fab552f6199edbf4c87b5c28c606cd18b8ee9728d`; S220 accepted-result record `d0cd70f0445767aa6efb92f6e5a040ee0634700c0de5aa93150a99a2d6ca2b8b`.

Verify this folder with `sha256sum -c SHA256SUMS`.
