# S209 observations — 23 October 2026

The accepted scope is isolated genuine-native functional validation of the unchanged S208 pairing caller/helper. The final contained fixture exited 0 with **7 top-level groups PASS, 0 FAIL**. Independent review accepted this scope with no open high or medium findings in the candidate, changed fixture, containment and observed cases. Physical runtime remains unproved.

| Group | Observed result |
| --- | --- |
| Exact request gate | Only the armed approval request passed. Generic POST remained denied. Wrong method, request, profile, account, foreign authority and an unarmed request were denied. |
| Genuine API negative controls | Wrong method returned 405; foreign account, foreign transport scope and missing session returned 403; wrong request returned 400. Pairing state was unchanged. |
| Ambiguous receiving account | Multiple accounts for the same receiving profile returned 400 before any grant. |
| Bound native pin drift | A deliberately incorrect binding hash was rejected during validation, with 0 API calls and no grant. Read-only source bytes remained unchanged. |
| Approval, readback and revocation | The exact armed request reached the genuine API once and created a real native grant. The helper read it back, used supported CLI revocation, then confirmed mandatory-grant denial for the same retained and a fresh Telegram event. The separately approved user's grant, account and product admission were preserved. |
| Lost acknowledgement after grant | The synthetic transport discarded the acknowledgement after genuine API success. Exactly 1 approval call occurred and the grant was confirmed present. The outcome remained `UNKNOWN_ISOLATED_PAIRING_CHAIN`; neither a second approval nor automatic rollback occurred. |
| Transport failure before dispatch | The synthetic transport failed before the API effect. Exactly 1 transport attempt and 0 API calls occurred; the request remained pending and no grant appeared. A new helper object could not retry because the durable approval marker already existed. |

The positive group also rejected repeated execution on the completed helper object and a new object for the same original request, without a second API call. The lost-acknowledgement group rejected both same-object and new-object retries. The pre-dispatch failure retained its UNKNOWN outcome despite the fixture's observation of zero API calls. These controls preserve durable one-attempt behavior across helper objects; they do not claim a process-restart or physical service recovery test. Fault injection affected only the external synthetic transport callback before or after the genuine in-process API, not the native API, provider, grant or provenance implementation.

The fixture imported genuine full native modules, including the native pairing store, authorization mixin, session/identity, ordinary gateway, product access and dashboard API. It used the exact pinned product plugin. This was not an extracted-function or fake-native test: the recorded 219 native/projection origin rows matched their pins, and the complete 4,985-file runtime source projection was verified. The shared source hashes and nine recorded metadata fields remained unchanged after execution.

Execution used direct containment with private PID and network namespaces. The actual authorization home and workspace were hidden before product imports. The exact dependency environment, base Python, native source, candidate and fixture were read-only; the writable receiving state was synthetic. Python ran isolated with site loading disabled and explicit module paths. Import and external socket/DNS/subprocess barriers were installed before first-party imports. No denial events were recorded by the audit barrier; that fact alone is not a negative-control exercise of every barrier. All three recorded process trees were reaped and synthetic receiving state was removed.

Earlier failures remain part of the result. The first S209 mount setup exited 1 because the product mount target could not be created under read-only source: product code did not execute and 0 cases ran. The corrected mount layout preceded the final passing fixture. The prior S208 package still has four attempts with exit code 1, 0 cases and 0 PASS. Its first installed middleware import remains `PROCESS_SCOPE_FAIL`, with imported side effects `UNKNOWN_SCOPED`. S209 does not clear, rewrite or resolve that earlier uncertainty. All original clocks and effects remain closed.

The identity boundary was synthetic: an already verified `Session` was injected into an in-process ASGI app. Genuine `SessionSource` objects and canonical identities were constructed directly. The caller's gate functions and ASGI handler bridge were exercised; the browser bridge and browser slot consumption remained source-reviewed only. No installed serving entry, supported native runner, genuine ordinary ingress, live thread or `ContextVar` custody was bound. Those physical bindings, current installed bytes and separately owned runtime authority remain required for a future finite integration step.

Browser, TLS, Basic login/provider authentication, real credential acceptance, real Telegram transport, services, models, network/live integration and physical runtime acceptance were **NOT_RUN**. Pairing revocation did not establish retained Basic-token or retained `UserScope` generation invalidation. The fixture seeded an unrelated approved user, not a separate unrelated pending request; it provides no independent unrelated-pending-row preservation result. No full admin or overall product acceptance follows from these seven groups.

Evidence identities for the accepted existing records, whose raw operational contents are not published here:

| Record | SHA-256 |
| --- | --- |
| Final functional observation | `8f8949704d1bfe1605c8667e6bec0093ad3cb6502a683793f25e3ef9d8c8e354` |
| Independent final scoped review | `746b9e8587c0774c1af7fe1610f57afc2509e5974df1500d11e6bcd6149c3423` |
| Accepted scoped result | `57b199a2210fd12a647b85505321cbce56fcd2c019f4a4ef78c266c1589f10ca` |

This documentation step checked those accepted references, factual coverage, relative links, publication privacy and its own checksums. It introduced no product delta or installation/runtime effects and repeated no functional execution or independent review.
