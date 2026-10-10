# Catalog R2 source findings — rejected candidate

This inactive analysis packet preserves five exact R2 modules, three changed predecessor bodies and the original patch. Delta: **3 changed, 0 added, 2 unchanged**. No product routing, source acceptance, runtime admission or release readiness is claimed.

Independent review found **141 logical controls: 131 PASS, 10 SOURCE_FAIL**, comprising 108 boundary, 25 async/retry and 8 cookie/helper controls. The final actual execution count is 142 because one fixture signal was classified and corrected; preliminary 108 controls are not added again. The separate replay of the author's 328 controls passed and remains reproduction evidence only.

Two causes remain. Nine native connect/send/header-encoding controls place Authorization bytes into an inert memory socket after revoke, capability replacement or secret mutation; the subsequent ScopeDenied is too late. A normal installed instrumentation handler also shares its nested mutable state with the secured clone. Earlier cookiejar isolation is closed, while generic handler-state isolation is still open.

[COUNTEREXAMPLES.json](COUNTEREXAMPLES.json) contains only synthetic fixture values and exact failed observations. These are real selected-source and stdlib execution with memory socket seams; they do not prove an actual network/TLS handshake or installed runtime behavior. [REPORT.json](REPORT.json) records causal source lines, exact source hashes, original clocks, deduplicated counts, closure and remaining qualification boundaries. All 18 started fixture threads were joined; open owned responses/sockets, live threads and FD delta were zero.

R2 remains rejected. A successor needs fresh independent final-source review and the required combined/native/installed end-to-end gates. Real Telegram, the seven normally installed journeys, four web-retrieval paths and the administrative WebUI with two-user isolation remain mandatory. G7 is not replayable; G8 needs its genuine owner foreground terminal; kernel120 is not granted, normal3600 remains unstarted, old Friday and Pandora remain off.

Original source and patch bytes are retained, including any archival whitespace. This packet is an intermediate publication after main 1c0111c14c029cca925db380359e3a3b1ed2cc1e. It does not replace the daily 21:00 MSK checkpoint or advance its baseline 653f86105e5bd33bcf5fd28b983c57b9b1639116.
