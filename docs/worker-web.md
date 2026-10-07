# Web inside intact workers

Source/offline candidate for FRW036-WORKER-WEB. This is required normal Friday
installation input, with explicit pending dependencies below. It is not an
installed or accepted product. Hermes web registration does not supply these
worker paths. No real model, search service or worker has run in this package.

## Harness: Exa and native public HTTP fetch

Reuse the pinned complete Harness `5badb15009ae1756c3afe0ae0cef1faafc290ccc`.
The existing `exa-paid` renderer selects `web.searchProvider: exa`,
`fetchProvider: http`, inserts native Exa and enables native `tool-web`.
Its local model routes and temporary capacities remain unchanged.

Add `dsh.web` to the existing receiving host runtime config:

```json
{"profile":"exa-paid",
 "resolver":{"path":"/private/approved/resolv.conf","sha256":"<exact hash>"},
 "trust_bundle":{"path":"/private/approved/ca.pem","sha256":"<exact hash>"},
 "egress_evidence":{"path":"/private/approved/network-evidence.json","sha256":"<exact hash>"},
 "research_policy":{"path":"/private/approved/RESEARCH.md","sha256":"<exact hash>"}}
```

These are explicit private operator files; placeholders grant nothing. The
normal readiness receipt must bind the current config, adapter and three
`web_source_pins`: `plugins/friday_rework/worker_web.py`, `tools/web_profile.py`
and `config/RESEARCH.md`. Existing readiness cannot transfer to changed bytes.
The installer ships the exact existing `tools/web_profile.py` helper under the
native tools package and the pinned research policy with the product; it is not
resolved from another home. Source pins cover the actual loaded helper/module
and the policy bytes rather than assuming a repository-relative installation.
Only the published JSON renderer format is admitted for this connection; native
YAML expressions or inline Exa credentials are rejected. Retrieval bounds must
match the actual native rows. Native provider failure never chooses another
provider or cloud model.

`dsh_binding(..., web_network_check=existing_trusted_current_check)` accepts the
existing host's current exact-association network check. The default is absent;
enabled web then fails before resolving credentials or launching. The pinned
evidence file is an integrity input, not an admission producer. No complete
production check is supplied or asserted here. A trusted parent must verify
approved Exa HTTPS and public-document DNS/TLS egress against the current owned
boundary, task identity, original remaining budget and stop intent. It must
repeat that verification immediately before launch; failure is not rerouted.

The receiving Hermes home/scope must explicitly contain both its selected local
inference credential and `EXA_API_KEY`. Missing/foreign/home-mismatched/changed
values refuse. No ambient environment or credential file fallback is read.
Systemd receives names only in argv; the private bootstrap forwards only these
two values. It strips ambient proxy and unrelated provider variables, mounts a
pinned resolver and uses the copied pinned CA bundle through native
`NODE_EXTRA_CA_CERTS`. Neither Exa key values nor hashes enter receipts. The
native process/whole-job deadline, ownership, stop and uncertain-delivery rules
remain unchanged. The trusted research policy joins the bounded job brief;
native tools label external text as data and retain source links.

Next live Harness journey: start one original-budget admitted coding task,
inspect its own source, discover an unfamiliar `asyncio.timeout` API, call native
`web_search` then `web_fetch` inside the same session, apply the documented fix
and pass its real test. Capture actual native events/source URLs and effective
scope, then confirm whole-job/remote inference settlement before releasing the
exclusive slot. This requires independent source review, an actual current web
network producer, protected Exa key, DNS/TLS inputs and the existing checked
native/exclusive admission. All are prerequisites, not an offline grant.

## A0: native SearXNG and document_query

The intact pinned A0 `e3051fb584b1a36be2b0a0c90606f1c2c2d356ec` already owns
`SearchEngine.execute → helpers.searxng.search → runtime.call_development_function
→ aiohttp POST http://localhost:55510/search`. Intact Docker provides
`/exe/run_searxng.sh` and its existing supervisor declaration. Native
`document_query` reads public source documents through its existing network
validation, parser and intervention path. No Hermes broker or substitute worker
is added.

`a0_web_files('searxng-google', timeout_seconds=15)` prepares a single explicit
Google engine and bounded native document-query configuration. SearXNG's
documented `keep_only` setting retains the full defaults while excluding other
engines; there is no automatic vendor/model fallback. This profile requires no
external search API key. The service still needs a separately protected native
`SEARXNG_SECRET`; the template leaves `server.secret_key` unset rather than
overriding the native default with an empty value. Empty secrets are accepted
by the observed native settings validator, so an empty value is **not** a
fail-closed startup mechanism. The normal installation must explicitly refuse
missing, empty or default secrets and verify the protected effective value
before admission. This source template does not provide that installation
check or grant startup. Do not insert a shared or placeholder secret.
The native service source/version in the built image must be observed before
accepting its effective settings. See the official
[SearXNG settings](https://docs.searxng.org/admin/settings/settings.html) and
[outgoing limits](https://docs.searxng.org/admin/settings/settings_outgoing.html).

The four-file MIT donor overlay in `patches/a0/worker-web.patch` bounds the
existing search transport to one 15-second, 1,000,000-byte attempt, checks HTTP
status, excludes ambient proxy credentials and labels its native source text as
untrusted. It preserves URL, content and intervention/Tool Response semantics.
Native search offers no supported timeout/response-bound configuration surface,
which is why this narrow overlay is needed; it does not replace the pipeline.
The two corresponding donor DOX files accompany the behavioral delta. Raw donor
bytes/pins and the intact image remain unchanged; the overlay is not installed.
Native document fetching is configured for one attempt, bounded bytes/time and
the same caller intervention/original task deadline.

**Connection blocked at the existing live guard:** the current exact
`START_SCRIPT` permits only `run_ui.py`, and its checked container command/env
and local kernel network allow only inference ports 8001/8002. It does not start
SearXNG or admit its DNS/TLS/search and subsequent document traffic. Adding the
native service/mount/secret/startup or extending external egress requires the
parent's coherent checked deployment/guard revision. This package does not
rewrite those accepted guards, replace the command, or activate the OFF daemon.
The required normal installer must supply those inputs and prove actual service
readiness/effective single-engine selection before admitting a real A0 task.
The existing original-budget capability/current producer, whole-environment
stop/history and remote settlement requirements remain in force.

Next live A0 journey: admit one engineering context under that reviewed service
and network composition, encounter an API/configuration gap after initial work,
use native `search_engine` and `document_query`, apply the findings, run the real
verification and return byte-checked artifacts through the existing host. Observe
owned environment/children quiescence and key cleanup before release. No retry
of the frozen probe, renamed run, source-only model substitution or self-grant
is authorized.

## Evidence boundaries

Offline tests execute actual native Cordis `ToolRuntime` dispatch, Exa provider
request serialization and native HTTP parsing/rendering against synthetic
transports. The A0 tests execute exact isolated native agent dispatch/runtime
methods, full native Tool/SearchEngine and document fetch/network functions.
Framework construction, type/presentation/extension hooks are explicitly
fixtures; the full A0 worker/model loop is not run. Initial work, gap, retrieval,
read and continued output belong to one deterministic synthetic task in each
case. Outage/missing-key/foreign scope/oversized response/hostile data controls
retain original permissions and budgets. This demonstrates native interface
connection, not real model reasoning or resistance to prompt injection.

Complete live ordinary/explicit research, BOTH worker mid-task journeys,
unavailable/hostile-page model behavior, two-user administration, real stop/config
effects and normal installation/startup remain mandatory **NOT_RUN_NOT_READY**.
The source package cannot close any of those six product acceptance journeys.
