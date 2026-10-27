# Complete tool exchanges in multipass compression

The previous planner treated an entire user span as one indivisible tool envelope. In the observed conversation, a span with 51 rows and 28 calls remained too large even after eligible payload strings were replaced with references. Its empty envelope needed 32,054 conservative accounting units against a 31,744 input budget. These are conservative UTF-8 JSON byte estimates, not tokenizer counts.

The patch changes only `_source_units`: each complete assistant tool call and all of its results remain together; other rows become individual ordered units. The existing packer combines them when they fit. Existing payload segmentation, source hashes/order, protected boundaries, finite budgets, cancellation, leases, checkpoint binding and atomic publication stay in place. No model, endpoint, context capacity or history reset is involved.

Validation used the actual saved gateway projection and current policy. The candidate packed it into seven initial chunks and one reduction. Thirty-six applicable tests passed; independent review ran overlapping controls, so their counts are not additive. Twelve unrelated baseline usage-anchor fixture failures were retained and excluded rather than reported as passes.

The patch is installed. A real Telegram compression completed: active messages fell from 82 to 7, with every original row retained unchanged and a stored summary. Gateway and Dashboard were restored under their existing permanent management. This establishes live compression for the observed conversation, not general semantic memory acceptance or whole-product readiness. The next DSH file continuation is running; no worker result is claimed here.
