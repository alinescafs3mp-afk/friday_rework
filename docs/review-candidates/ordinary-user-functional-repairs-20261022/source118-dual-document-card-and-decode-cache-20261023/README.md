# Source118: document discovery and JSON decode cost — source only

This reviewed candidate is **not installed**. It targets 118 native layers, 17,716 native files and 311 project files. Source117 remains installed with its permanent gateway running. No new live DOCX acceptance is claimed.

Two native description strings now expose structured Word creation in the actual 60-character catalog summary and 500-character shared card. The same card retains the XLSX mode, all five required JSON keys, preservation and no-recalculation contract. Full previous descriptions, schema fields, arguments and renderers are retained. The already installed Source117 structured renderer is not applied a second time. [native-presentation.patch](native-presentation.patch) and its [manifest](native-source118-manifest.json) preserve the exact source delta.

[json-decode-cache.patch](json-decode-cache.patch) reduces repeated decoding of identical freshly read JSON. Every call still performs the private stable owned-file read, and all pin, source, history, pre/postcheck and commit requirements remain. Cached results are not acceptance results; returned mutable containers are independent. Iterative copying preserves deep JSON, and locked accounting handles concurrent misses. Limits cover 2,048 entries and 32 MiB of raw input, not decoded process memory.

Independent source checks: 98 for the shared DOCX/XLSX cards; 35 isolated actual controls for decoding; 5 combined metadata-consumer checks. The unchanged 52 renderer controls were reused. The measured decode microbenchmark is **not evidence that the complete native update fits 180 seconds**. That complete timing and actual installation/user semantics remain open.

[OBSERVATIONS.json](OBSERVATIONS.json) separates source proof, historical failures and remaining integration requirements. [SHA256SUMS](SHA256SUMS) authenticates the public payloads.
