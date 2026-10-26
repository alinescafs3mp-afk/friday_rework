# Ordinary file-task consumer: documentation delta only

S371 accepted source compatibility of the existing materializer → tester → peer path for the corrected generation. No executable file or original task/scenario template changed. Accepted prior source/control evidence was reused; no oracle body, model, Telegram task or native scenario was run for this check.

## Distinct reference shapes

These are format descriptions with symbolic values, not operational evidence or executable templates.

| Consumer role | Exact reference fields |
| --- | --- |
| External proof, initial plan or semantic-review material | `path`, `bytes`, `sha256` |
| Tester's protected predecessor admission reference | `basename`, `bytes`, `sha256` |
| Compact current proof | `path`, `sha256` |
| Separate full compact material | `path`, `bytes`, `sha256` |

The predecessor basename is interpreted under the existing protected state directory. These shapes are not interchangeable. The initial plan retains its existing closed set of 15 top-level keys. No source-basis extension or authority field is added to that plan. Tester JSON uses `ensure_ascii=True`, sorted keys, default separators and one trailing newline; peer canonical JSON uses `ensure_ascii=False`, sorted keys, compact separators and one trailing newline. A bound hash authenticates those exact serialized bytes, not a template's hash.

## Flat semantic review

The real tester constructs its review object by merging the capture fields into the top level. The previous prose notation `capture_binding {...}` was shorthand, not an accepted nested field. Exactly 14 top-level keys are required:

```text
run_id, scenario_sha256, step, sent_message_id, sent_ids,
request_body_sha256, schema, run_record_sha256, artifacts,
verdict, operator_checked, reviewer, checks, diagnostic_reference
```

The schema is `frw.bot-tester.reply-semantic-review.v1`; the verdict is `ACCEPTED_FOR_CONTEXTUAL_FOLLOWUP`. `operator_checked` must be true and `reviewer` must be Root. The artifact entry identifies an actual complete received document by `sha256`, `bytes`, `message_id` and `update_id`. Checks and the diagnostic reference must carry the genuine semantic evaluation. This description is not a receipt and supplies no artifact, message, request, nonce or run values.

## Source evidence is not operational admission

The unchanged peer's basic assignment checks do not independently attest the 13 Root operational binding facts. Current custody/CAS, access and cancellation, source and installation evidence, service ownership, worker qualification, predecessor/cursor, actual plan, original clocks and effect authority must be established by Root at the real boundary. Future bindings remained null in S371. Its old installation snapshot cannot be relabeled as acceptance of corrected source; the later actual installation stage is recorded separately in this checkpoint.

The tester tuple's `native=0` describes its runtime-effect counter. It does not mean Native API version zero. The same numeric source/build/layer/project tuple can cover different exact project bytes. The real source-120/project-316 predecessor and raw admission history stay unchanged; they are not renamed to the new generation.

Durable authorization writes assignment state; the subsequent native prompt is a distinct once-only effect. The existing tester continuation entry validates, locks, records admission, creates a run, sends and observes immediately. It is not a dry-run or offline preparation command. A contextual followup requires the actual completed capture, artifact and semantic receipt from that same conversation. The second worker task retains its own later compact/admission boundary. This package grants no execution, resets no clock and claims no Telegram or worker acceptance.
