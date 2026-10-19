# Current compression counter — reviewed candidate

This directory preserves an inert source candidate and its focused regressions. The candidate is not connected to the installed product by this archive.

The replacement compression deployment has a changed tokenizer and chat template. Some Hindi and Arabic text receives different token counts. The counter adds an explicit v2 binding for the exact current five assets while retaining the previous v1 binding. Asset selection remains strict; there is no automatic adoption of unknown data.

The v2 contract records the server startup `trust_remote_code=true` separately from local `trust_remote_code=false`. Local loading remains offline and rejects remote-code mappings or a mismatched tokenizer class/backend. Prompt normalization, request construction and capacity accounting retain their existing behavior.

`SOURCE.patch` changes only the renderer. The two test files cover legacy and current assets, selection refusal, exact counts, tokenizer-ID roundtrip, and isolation of the supported renderer-add and capacity-change transactions. All 21 cases and 59 subtests passed on the exact private isolated candidate in 11.571 seconds under the original 120-second operation limit. The test sources and patch are byte-identical here; they use synthetic deployment documents and establish no installed or live acceptance.

The earlier test assertion that decoded text must equal raw input was incorrect for the changed tokenizer. The corrected test verifies token-ID roundtrip, includes a meaningful decoder-drift refusal, and passed in the new candidate run. The earlier failure remains historical evidence.

Current model asset bytes are excluded: their upstream revision and redistribution license are not established. Their exact local provenance is retained privately; previous asset attribution is not transferred to different bytes. No credentials, private acceptance inputs or handoff documents are included.

The candidate must be integrated with the reviewed 65,536/65,530 capacity migration, pass the coherent source gates and use the supported stopped installation and two distinct configuration transactions. Main inference remains 262,144. Timeout and multipass budgets are unchanged. Live inference and product acceptance remain outstanding.

`LICENSE` retains the existing Hermes MIT attribution for the patch context.
