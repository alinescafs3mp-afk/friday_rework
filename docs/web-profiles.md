# Explicit native web profiles

These options extend the existing **temporary local component-test renderers**.
They configure native retrieval separately from local inference; they do not
connect a worker to the internet or constitute the normal product installation.
The mandatory scope in [mandatory-web-admin.md](mandatory-web-admin.md) and the
remaining integration in [donor-capabilities.md](donor-capabilities.md) still apply.
All six web/admin product journeys remain **NOT_RUN**.

## Selection

Keep the existing required model, endpoint, capacity and output arguments. Add
`--web-profile` to `tools/configure_local_test.py` (Hermes) or
`tools/render_dsh_local.py` (Harness). Omission means `disabled`, preserving the
previous generated configuration, including the disabled Harness `tool-web` row.
Web options supplied with `disabled` are rejected. Profiles are fresh, independent
values; renderers never read credentials or select providers from the environment.

| Explicit profile | Hermes search / extraction | Harness search / fetch |
| --- | --- | --- |
| `disabled` | Existing empty component-test toolset | Existing disabled native tool row |
| `exa-paid` | Native Exa SDK index search and extraction, paid tier | Native Exa index search and native public HTTP fetch |
| `exa-keyless` | Native anonymous Exa MCP search and extraction, free tier | Rejected: this pinned Harness provider requires a key |

Both enabled Hermes profiles set `web.backend`, `search_backend` and
`extract_backend` to `exa`. They select the native `web` toolset (`web_search` and
`web_extract`) through both the top-level toolset list and explicit CLI/Telegram
`platform_toolsets`. These are intentionally narrow component profiles, not a
complete Friday tool composition. Other gateway platforms retain their own
native selection rules; the product installer must configure every served surface.

Paid Exa requires the deployment's protected `EXA_API_KEY`. The renderers neither
check nor copy its value. Hermes uses its native profile-scoped secret resolver;
Harness's Exa plugin uses `launchEnvironmentOf(ctx).get('EXA_API_KEY')`, **not** an
`apiKeyEnv` configuration field. The latter field belongs to other providers.
The selected inference credential reference stays independent and unchanged.

The keyless profile explicitly sets Exa's tier to `free`, even if an Exa key is
present at runtime. Native keyless requests ordinarily traverse a four-vendor
ring. This profile sets Parallel, Firecrawl and Keenable tiers to `paid`, excluding
their anonymous endpoints: the ring contains **only Exa**, with one attempt per
operation/URL. `keyless_fallback` is true only for this profile and
`keyless_rescue` is false for both. Paid mode disables keyless fallback too.
Neither profile selects Nous, OpenAI-native, xAI or Perplexity model-backed search;
their corresponding bundled model-backed web plugins are explicitly disabled.
Paid failure never silently switches to free service; keyless failure never
silently switches vendors. Selecting another profile is an explicit deployment
decision, not an automatic response to a failed request.

Harness replaces the base `web.searchProvider: deepseek-official` with `exa`, pins
`fetchProvider: http`, inserts the previously absent `web-search-exa` plugin through
Cordis's native `insert` operation, and enables `tool-web` and `web-fetch-http`.
An ordinary `id/config` patch cannot create an absent plugin; Cordis warns and skips
it. All existing DeepSeek inference/account/search rows stay disabled. Local model
routes, compaction configuration, capacity declarations and deployment persona
remain unchanged. The Exa endpoint is the native `https://api.exa.ai`; no arbitrary
URL, inline credential, executable YAML or provider expression is accepted.

## Native bounds

Enabled profiles have the following defaults and accepted rendering ranges. These
are retrieval limits; the real job still owns its overall deadline/retry budget.

| Renderer option | Default | Range and actual native consumer |
| --- | --- | --- |
| Hermes `--web-extract-char-limit` | 15000 | 2000–500000; `web.extract_char_limit` |
| Hermes `--web-extract-timeout` | 30 seconds | 1–120; `web.extract_timeout` |
| Harness `--web-search-max-results` | 5 | 1–20; `tool-web.searchMaxResults`, Exa `numResults` |
| Harness `--web-search-max-queries` | 2 | 1–4; `tool-web.searchMaxQueries` |
| Harness `--web-timeout-ms` | 30000 | 1–120000; tool search/fetch budgets and HTTP fetch timeout |
| Harness `--web-fetch-max-chars` | 15000 | 2000–200000; HTTP body and tool output caps |
| Harness `--web-fetch-max-bytes` | 1000000 | 1–5000000; HTTP response byte cap |

Harness HTTP fetch allows at most three same-origin redirect hops and retains its
native public-address/connection validation. The tool timeout is cooperative and
requires the existing native timeout-policy composition. Hermes's character option
is a **default per-page presentation budget**, not an immutable cap: the tool's
`char_limit` argument can override it within native bounds; full text may be cached
to disk by native truncation. Profile caching is explicitly disabled. Native Hermes
`web_search` bounds its argument to 1–100 results and the registered extraction tool
accepts at most five URLs. No invented profile-level global search timeout or result
cap is emitted. Anonymous Exa uses native 30-second HTTP request timeouts; paid SDK
search transport limits are SDK-owned. Request deadlines and cancellation must be
validated in the actual job. These settings do not provide an egress firewall.

## Research policy and instruction ownership

The Hermes renderer reads the shipped [RESEARCH.md](../config/RESEARCH.md) and places
it in the native `agent.environment_hint` field. `prompt_builder` reads that field
and `system_prompt` appends the resulting environment block. This adds operating
guidance without using or replacing `agent.system_prompt`, `display.personality`
or SOUL. The policy covers current/version-dependent facts, unfamiliar APIs and
tools, insufficient evidence, errors/conflicting information, explicit research,
primary sources, applying findings, citation, uncertainty, hostile pages and the
original task budget. It does not grant new permissions or implement a security
boundary. Harness retains its native tool guidance, untrusted-content notice and
citation instructions; propagation of the complete Friday policy into worker
tasks remains part of host integration.

The native `HERMES_ENVIRONMENT_HINT` environment variable overrides this config
field. That precedence was demonstrated offline; do not call the policy mandatory
at runtime merely because the file exists. Product startup must control that
override and verify the actual rendered prompt. A selected personality takes
precedence over `agent.system_prompt`, which is why this policy does not use the
manual overlay field. New profiles do not import another home's instructions or
secrets. As before, the Hermes CLI renderer deliberately replaces a complete
temporary configuration only with the expected hash and a verified private backup;
it is not a general merge/editor for an existing personal/product home. The web
helper does not edit SOUL or personality files. Harness still publishes only a new
private file and refuses existing destinations and unsafe parents.

## Evidence and remaining connection work

Pins: Hermes `781334eea4b9225a3e194faf0c241d9afe218634`, Harness
`5badb15009ae1756c3afe0ae0cef1faafc290ccc`. Relevant native consumers:

- Hermes `tools/web_tools.py`, `tools/web_tools_extract.py`,
  `tools/web_tools_truncate.py`, `tools/web_tools_rescue.py`,
  `tools/tool_backend_helpers.py`, `plugins/web/exa/provider.py`,
  `plugins/web/keyless_mcp.py`, `hermes_cli/tools_config.py`,
  `agent/prompt_builder.py` and `agent/system_prompt.py`.
- Harness `vendor/include/src/index.ts::applyEntryPatches`,
  `packages/bundle/base/cordis.patch.yml`, `packages/web/web/src/index.ts`,
  `packages/web/web-search-exa/src/{index,provider}.ts`,
  `packages/web/web-fetch-http/src/index.ts` and `packages/web/tool-web/src/`.

Offline checks exercised the actual Hermes atomic writer, CLI/effective config
loaders, provider/tier selection, missing-key refusal, extract budgets, credential
URL refusal and additive policy reader with a selected personality. Full agent
construction was not run. Optional model-provider discovery tried seven Git
version-metadata subprocess probes; an audit hook refused them before execution.
This is constrained native
configuration evidence, not complete model-provider discovery or runtime acceptance.
Native Cordis YAML parsing, patch composition and plugin schemas accepted the
Harness output with no warnings. A negative control proved that omitting `insert`
fails to create Exa; native Exa reported unavailable without a key. Query bounds and
untrusted output labeling were exercised without making provider requests. Unit
controls cover malformed/injected inputs, redacted CLI errors, independent configs,
synthetic credential canaries, unchanged inference and protected publication/backup.

The current Harness launcher still needs approved provider environment forwarding
and DNS/TLS/proxy/trust-store integration inside its restricted namespace. A0 still
needs its separate approved egress, native search service and host integration.
Hermes tool registration is not a worker web broker; `mcp_serve.py` exposes messaging
and history, not arbitrary web tools. Browser interaction, actual provider
availability, mid-task retrieval for both workers, original deadline/stop behavior,
hostile-page behavior with a real model, admin journeys and normal packaged startup
are **NOT_RUN** here. Normal Friday installation must deliver the working selected
web path; these component commands do not shift that assembly work to the owner.

## Exact no-cache search and the prepared native research runner

`patches/hermes/web-exact-limit.patch` changes only the native search fetch count:
with `web.cache_enabled=false`, the provider receives the existing validated
native limit (including clamping/coercion). Limit 3 therefore serializes as Exa
MCP `numResults=3`. Default/cache-enabled behavior keeps bucket 10, memo hits,
single-flight, slicing and non-caching of failures. Provider selection, keyless
ring, rescue policy, extraction and inference are unchanged. Apply only to the
exact file hash in its separate manifest, after the existing canonical overlays;
verify the resulting hash and patch roundtrip. The prior refused native probe is
immutable and must not be retried or have its protected receipt enlarged.

`validation/web_runtime.py` is an inert, source-only preparation for a **new**
parent-authorized ordinary/explicit research task. It uses the real Hermes
`AIAgent`, native local runtime resolver, in-memory profile secret scope, native
web tools with the supported `session_db=None` mode. It adds no scheduler, service launcher, task database or
authorization command. The small `validation_profile` delta takes task names
from the pinned native defaults and pins every model-capable auxiliary row to the
same explicit configured local route. Models and capacities remain renderer
inputs. Publish a new private home through the native atomic writer, preserve
Friday SOUL, then pin its actual config/SOUL bytes; do not edit an installed home.

The driver binds the original task and a canonical JSON plan hash, exact candidate
files, profile, SOUL, RESEARCH, driver, web helper and inference endpoint. It clears
ambient policy/provider/proxy overrides before native imports, requires the
effective native tool set to be exactly search/extract, verifies the actual native
rendered SOUL/policy and allows no main/auxiliary cloud fallback. The trusted parent
supplies the existing current durable association and scoped credentials. Admission
checks the native transient unit owner/invocation/cgroup and current MainPID,
original boot/monotonic/wall clocks, a native RuntimeMax deadline that cannot extend
the original task, the already held inherited exclusive-lock FD and a separately
reviewed original network admission. It never acquires a free lease or creates one.

Before `Native.open`, the driver consumes the **original research admission**
through the existing `Associations.begin_submission` transition from
`NOT_SUBMITTED` to `UNKNOWN`. `ExistingBoundary` requires that association store
and its original owner, and compares the exact original row before and after the
durable transition. The already supervised wrapper is distinct from the research
submission it is about to execute: an already submitted worker row is refused.
No controller or association schema is changed. A crash, lost acknowledgment or
failed publication never clears consumption, even if all output files are removed.
The missing trusted producer must supply this original row; the driver cannot
create or retrofit it.

**The complete trusted live admission producer is missing and NOT ACCEPTED.**
The historical smoke/preflight records do not provide it. The parent still needs
an exact new scope and current reviewed egress (local inference separately from
selected web), the existing supervised/exclusive boundary, protected scoped
credential delivery and independent proof of remote inference settlement. After
driver exit it must observe the entire cgroup quiescent before releasing the
lease. An in-process `agent.close` or callback cannot attest the driver's own
terminal cgroup. Refusal/uncertain stop must retain the original budget, process
identity, partial observations and ownership; no automatic retry.

The private `partial-observation.json` is atomically replaced and fsynced before
execution, at native tool-complete callbacks, at bounded visible-stream snapshots,
on native return and after cleanup.
Returned observations are stored before checking the original deadline; failures,
incomplete model turns and unknown cleanup remain failed/uncertain. Text is
redacted before truncation (64 Ki characters in aggregate, 16 Ki per field, bounded
collections/depth, with a hard 1 MiB serialized-file cap). `observation.json` remains an exclusive final publication.
`recover(plan, task)` reads these retained observations with the original identity,
even after expiry/reboot or a failed final publication. It does not admit, settle,
execute or reset any budget. An interrupted capture may leave only the preceding
durable partial; it remains uncertain. Native complete tool callbacks provide
incremental source evidence. The supported native `run_conversation(stream_callback=...)` consumes
real visible deltas after native thinking/context scrubbers and writer fencing.
Its accumulator survives native retry/reset. The first delta is fsynced immediately;
later writes coalesce at 512 input characters or 250 ms on an incoming callback,
with no timer or new thread. Caps are 64 Ki input characters, 16 Ki retained text,
4,096 callbacks and 256 stream publications within the original remaining deadline.
Crossing a cap or failing persistence requests native interruption and prevents
success. Native continuation/retry policy and request/iteration budgets are unchanged.
A streaming trie conceals full credentials of any length and incomplete known-secret
prefixes containing at least eight original credential characters. Escaping does
not count as additional characters; the same threshold follows three nested JSON
serialization boundaries and all chunk splits. Meaningful prefixes stay concealed
on mismatch/reset. Shorter incidental matches (including `s`, `sk-`, `local-` and
`friday-`) are preserved literally, including at natural end of text; they alone
are not evidence of a credential. At artificial input truncation even a one-character
pending match is concealed and the observation is marked truncated. No policy can
distinguish ordinary text identical to a known full credential or its meaningful
prefix; those exact spans remain redacted. Schema, tool names and nonsecret URLs
otherwise remain intact. The capped trie buffers only the short undecided prefix,
never a growing raw stream. Tool/final observations and spill/debug sinks use the
same policy so meaningful partial native stubs cannot escape through a later 4xx dump.

No native SQLite transcript or trajectory is enabled. During the dedicated run,
native console output is discarded and logging is suppressed, including native
construction and cleanup; only the redacted observation sink is public. Actual
native full-page and tool-result spill writers receive redacted text and filenames
before writing. Native API-error request dumps use the existing profile-scoped
exact-value redaction registry, including escaped credential forms. These scoped
bindings, including the native request-debug JSON sink, are restored at close. This policy requires the new private profile and
dedicated process; it is not suitable for a concurrent gateway. Pinned persistence,
redaction, spill and logging sources are mandatory inputs. Offline regressions scan
every actual profile/workspace/output artifact and captured console for synthetic
credential echoes on success, SDK failure, deadline and uncertain remote stop.

Observations keep input, effective native metadata, tool calls, source responses,
final response and uncertainty separate, and never accept a model's claim of
success. Real native SDK/stream/relay/tool
execution with **synthetic** HTTP/model responses is an offline control, not proof
of autonomous research, provider availability or normal product startup. Known
provider registration and denied optional metadata probes are recorded fixture
limitations. Use [web-runtime-recipe.json](../validation/web-runtime-recipe.json)
for the next independent actual-source/configuration check and negative controls.
Both worker mid-job retrieval, normal discovery/install/start and all six complete
web/admin journeys remain mandatory and **NOT_RUN**, pending their own admission.

The prepared urllib3 example explicitly requests GET503 and header-driven GET413/429,
with Retry-After respected and no POST/other status retries. The prompt and recipe
are statically aligned with these branches in pinned source. Header delay, status/
method cases and total exhaustion remain **NOT_RUN** pending an admissible normal
verification boundary; no supplemental Retry semantic execution is authorized here.
