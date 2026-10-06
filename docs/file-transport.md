# File transfer component

`patches/hermes/bounded-file-transfer.patch` layers onto the pinned Hermes
checkout **after** `admitted-ingress.patch`. Apply the earlier patch and verify
its manifest first; then check and apply this overlay and verify
`bounded-file-transfer-manifest.json`. The context patch remains independent.
Only separately owned development checkouts are eligible for these changes.
The pristine donor and preserved Friday checkout are not installation targets.

Telegram downloads use the existing SDK request slot, HTTPX client, proxy,
transport and timeout configuration. File GET responses are read in bounded
chunks; normal API POST and polling retain the SDK implementation. Local Bot
API files use bounded reads too. The effective ceiling is the smaller of the
adapter limit and the active positive inbound-media limit. A zero global limit
still leaves the adapter limit. Declared lengths must agree with actual bytes;
encoded file bodies are refused. Limits remain configuration values, not
permanent assumptions about Telegram or future hardware.

The native receive path records size and SHA-256 before consumers can change
the cache. A path-specific receipt ties those bytes to the original bot,
message and attachment. Own and replied attachments can retain distinct
receipts despite identical filenames. Ambiguous, merged and legacy paths
without content proof cannot authorize worker inputs.

`inputs.stage_inputs` consumes an already matched admission, permitted native
cache roots and a host-selected mount mapping. It copies actual files to
private stable storage, compares received and staged hashes, and returns the
complete mapping only if every input passes. A changed cache, traversal,
symlink, unproved origin or exceeded budget refuses the dependent task. A
partial failed staging operation may retain private evidence; it returns no
worker grant. The adapter must still verify bytes through its actual mount.

`artifacts.stage_file` and `read_staged` provide bounded, descriptor-based copies
and exact verified bytes for delivery. Stable files use unique names and
read-only permissions in a private directory outside worker write grants.
They preserve the source and existing artifacts. Callers establish workspace
ownership and producer quiescence separately; these helpers do not prove
provenance or select a destination.

A successful Telegram warning after a failed document upload now leaves the
document result unsuccessful. Only an actual upload acknowledgement supplies
a document message ID. A failed or uncertain upload must not be recorded as
delivered or automatically replayed.

Current checks use the actual installed SDK with offline transports and real
filesystem/cache/PluginState operations. Live bot cutover, asynchronous host
delivery, durable per-artifact delivery outcomes, large-file streaming and
final product acceptance remain separate work. Per-file bounds do not impose
a total memory budget on concurrent downloads; the SDK can hold multiple
bounded copies. Worker execution remains disabled in the registered tool.

## Original delivery route

The admitted ingress receipt retains the actual native `chat_type` alongside
its original bot, chat, topic, message and transport/runtime profile. The
plugin constructs its delivery route from that persisted receipt. A later
message or `/new` does not supply a replacement route. Hermes must still check
current authorization, profile ownership and the receiving bot before sending.
Historical receipts without `chat_type` remain readable for inspection but
cannot silently assume a direct message or authorize delivery.

`patches/hermes/gateway-work-delivery.patch` adds two supported in-process
PluginContext methods: `schedule_gateway_work` uses the existing gateway loop
and plugin ownership ledger; `deliver_gateway_document` sends verified bytes
through the original receiving adapter. The owning profile must separately
enable `allow_gateway_work` and `allow_gateway_delivery` in its plugin entry.
Revocation, profile/bot changes and unload refuse work. The isolated plugin
host and its audit explicitly reject both methods before RPC.

Document delivery submits once, checks the native acknowledgement against
the original chat/topic and byte length, and records the supplied bytes' hash.
Timeouts remain UNKNOWN, without automatic resend or destination fallback.
The host must persist delivery intent and its outcome around this call; that
integration and live Telegram acceptance remain unimplemented.

Apply this overlay after the context, ingress and bounded-file overlays,
using the exact hashes and before/after files in its manifest. Independent
review verified canonical application and all 39 cumulative output files;
the repaired host boundary and existing gateway paths passed 40 native tests.
The earlier route/byte transfer review also exercised the installed Telegram
SDK against an offline transport. These are component results, not a live
Telegram or release claim.
