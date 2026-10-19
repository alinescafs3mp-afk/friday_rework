# Weighted configuration reconstruction: source candidate

Status: reviewed source proposal; not integrated or installed. It does not apply the requested compressor context increase. The current full qualification remains failed, and runtime/release acceptance remains outstanding.

This complete replacement patch extends the literal fast path published in `../readonly-config-and-provider-slow-source-20261019/`. Apply it to its recorded original baseline, rather than stacking the two patches. The policy-admission and slow-provider proposals in that earlier packet are separate.

The reader still opens and reads the current file before lookup. Safe parsing precedes an internal bounded reconstruction plan; no external data is passed directly to `marshal.loads`. Supported plain containers are reconstructed independently, and environment expansion, managed overlays and normalization remain current on every read. Unsupported values, including NaN and recursive structures, take the original cloning path.

The weighted LRU admits at most four entries and at most 4 MiB of source bytes in total. The preceding cache admitted at most four entries of 1 MiB each. The new contract permits a single larger document within the same aggregate source-byte ceiling. Parsed objects consume additional memory; the source-byte limit is not an RSS limit. Each reconstruction plan has a separate 1 MiB encoded limit, traversal and depth bounds, and bounded environment paths.

Author checks passed 125 synthetic reconstruction checks and 31 checks of the weighted delta; independent checks passed 59 and 37 respectively. These counts describe separate snapshots and scopes, not 252 tests of the final integrated candidate. The checks used extracted functions and parser spies. They do not establish real parser, native admission, installation or product acceptance.

A five-pair synthetic microbenchmark measured median clone/expansion time of 0.277631 seconds versus 0.100890 seconds for reconstruction/expansion over 3,082 iterations. It excluded file I/O, parsing, admission, managed overlays, normalization and full setup; it is not a forecast of the timed full gate.

Before execution, the fixture regression that previously required all files above 1 MiB to bypass retention must be updated to the new 4 MiB bound while preserving its currentness and bypass assertions. Real focused regressions, meaningful negative controls, the full mandatory gates and supported stopped installation are still required on the final coherent candidate. No earlier PASS is transferred to these bytes.
