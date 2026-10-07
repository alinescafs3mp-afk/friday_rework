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

The worker source connection is described in [worker-web.md](worker-web.md):
Harness explicitly forwards receiving-scope Exa/local credentials with pinned
DNS/TLS inputs, refusing absent current network admission. A0's native retrieval
configuration and narrow bounded-search overlay are prepared. Its existing
startup/kernel guard still blocks native service/external-egress integration.
Both need the documented checked installation and live admission prerequisites.
Hermes tool registration is not a worker web broker; `mcp_serve.py` exposes messaging
and history, not arbitrary web tools. Browser interaction, actual provider
availability, mid-task retrieval for both workers, original deadline/stop behavior,
hostile-page behavior with a real model, admin journeys and normal packaged startup
are **NOT_RUN** here. Normal Friday installation must deliver the working selected
web path; these component commands do not shift that assembly work to the owner.
