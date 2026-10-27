# Retained DSH inputs: accepted source, installation pending

The ordinary `friday_work` request can explicitly select complete files from an owned, quiescent earlier DSH job. The host retains the current authenticated original input and selected immutable output files, then passes the existing verified-input tuple to DSH. This closes the gap where textual previews were truncated and complete files did not enter the next sandbox.

The selector carries task content only. Current native admission, canonical owner, principal, generation, home, session, source identity, quiescence, path/link, content hash and byte limits remain checked. Existing records and requests without a selector remain valid. Exact duplicate requests reuse their existing association; changed selectors cannot restage or launch again. First output-manifest collection is a bounded state change; later identical selection reuses it.

Validation: 32 helper tests, 38 host integration/regression tests, plus four focused independent consumer checks. These include complete retained bytes, the original reply attachment, canonical owners without invented fields, stale/foreign/active-job rejection and duplicate non-replay. Isolated checks replace external authorization I/O, native supervisor observation, and secret lookup; they do not establish live runtime or Telegram acceptance.

Status: the five-file patch is installed and the services were verified in fresh processes. The separate conversation-compression failure has also been repaired and passed a real compression without discarding original rows. A genuine DSH file continuation is running. No completed worker result or full-product readiness is claimed.
