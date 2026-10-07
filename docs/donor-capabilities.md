# Donor capability inventory — 2026-10-07

This is a source and integration checkpoint, not a second task register. It reflects published source `f80e187` plus the reviewed Hermes overlays. The donor commits remain pinned in [sources.lock.json](../sources.lock.json). All six mandatory web/admin product journeys are **NOT_RUN**. Source presence, implementation, connection and verified behavior are distinct below. Historical component evidence is not promoted to new candidate acceptance.

The selected product surface is Hermes Dashboard, using its authentication, native state and APIs. Keep intact Harness and dedicated A0, including A0’s native WebUI. The smallest missing integration consists of effective product identity/access checks, views over existing conversations/tasks/attachments, a real control path to their owner, and worker web connectivity. Ordinary users can remain on authorized messaging channels; the administration console is administrator-only. No ordinary dashboard account is required to provide product access.

## Planned integration and acceptance

| Existing scope | Required change and dependency | Demonstration |
| --- | --- | --- |
| FRW-003 / FRW-009 / FRW-011 | Configurable local inference profiles and separate web transport/provider inputs for Hermes, Harness and A0; complete current A0 readiness/ownership repairs first for dependent live work. | AC053–056, both AC055 worker parameters. |
| FRW-015 / FRW-016 / FRW-026 | Explicit product user, channel-account, chat/topic and session links; effective access/revocation and scoped recall/memory/tools. Reuse native grants/state. | Two real users, administrator visibility, ordinary-user refusals and next-channel-request revocation. |
| FRW-017 / FRW-025 / FRW-034 | Real admin control bridge, health/config views and normal protected Dashboard installation/startup. Preserve native supervision and original task bounds. | AC058 native cessation and persistent effective configuration change. |
| FRW-029 / FRW-036 | Native tools/skills and autonomous research behavior become required; prior optional AC043 classification superseded. | AC053–056, source references, retrieval outage and hostile-page controls. |
| FRW-022 / final acceptance | Extend existing final journeys without dropping earlier controls. | Cumulative AC001–052 plus AC053–058 on final product bytes. |

The temporary FRW041 inventory assignment is preparation for these existing scopes, not a replacement backlog. Sol’s current FRW014 core repair preserves integration seams; web/UI work must not weaken its ownership or readiness checks.

## Reused capabilities and actual stage

### C01. Product administrative WebUI

Hermes React Dashboard already has sessions, profiles, pairing, channels, config, model, keys, files, tools, skills, MCP, cron, logs/health and plugin pages; its chat embeds the real TUI.

**Selected reuse:** Use the existing Dashboard shell and native routers; add Friday inspector/control pages through dashboard/manifest.json + plugin_api router. Keep chat/TUI intact.

- **Planned:** Mandatory now; former alternate-WebUI deferral superseded.
- **Implemented:** Donor implemented. Friday plugin has no dashboard directory or admin router at public snapshot.
- **Connected:** Not connected as Friday administration.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Install trusted explicitly enabled user/bundled plugin, admin authorization, read projections and gateway control bridge; project plugins cannot mount Python API.

Sources: [H_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/web/src/App.tsx), [H_UI_POLICY](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/web/AGENTS.md), [H_PLUGIN_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_server_dashboard.py), [F_PLUGIN](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/__init__.py).

### C02. Administrator authentication and roles

Shared REST/WS auth: loopback session token; non-loopback auth-provider gate, cookies, tickets. Basic provider has one configured username and signed stateless tokens; revoke_session does nothing server-side.

**Selected reuse:** Reuse native auth. Fastest scope is an administrator-only Dashboard, ordinary users on authorized channels. Explicit principal-to-role mapping belongs in native Friday plugin configuration, not a second account database.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Authentication exists; Session has identity/provider fields but no role/permission fields.
- **Connected:** No product-role binding found in inspected Friday source.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Enforce admin capability on every privileged REST/WS/PTY/plugin path and live control. If ordinary dashboard logins are enabled, add per-resource policy before exposing routes. Define effective disable/revocation, not cookie logout only.

Sources: [H_AUTH](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/dashboard_auth/base.py), [H_BASIC](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/plugins/dashboard_auth/basic/__init__.py), [H_AUTH_GATE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/dashboard_auth/middleware.py), [H_WEB_SERVER](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_server.py).

### C03. User admission, onboarding, enable/disable

/api/pairing lists pending/approved users; approve by request_id or user code; revoke and clear-pending call PairingStore. Channel cards edit native credentials/allowlists; Telegram bot onboarding is a distinct external pairing service.

**Selected reuse:** Use PairingPage for code onboarding and ChannelsPage native allowlist editing for explicit admission. Present grant sources; preserve platform/user/profile tuple.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Donor API and persistence implemented; no independent Friday users CRUD exists.
- **Connected:** Native gateway checks PairingStore OR other grants; Friday UI not connected.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Revoke returns false/404 for allowlist-only users. It removes paired grant and matching configured platform allowlist mirror, not global/group/wildcard/adapter-role grants; native write is best-effort. Verify effective admission and report partial failure. Bind roles to actual policy; do not call revoke universal disable.

Sources: [H_PAIR_API](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/ops.py), [H_PAIR_STORE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/gateway/pairing.py), [H_AUTHZ](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/gateway/authz_mixin.py), [H_CHANNELS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/messaging.py).

### C04. User/account/channel/topic/session relationships

Hermes state.db sessions/messages + origin_json and gateway_routing; SessionSource carries platform, user/chat/thread/scope/profile; Friday admission/association retains bot_id, transport/runtime profile and original message/attachment IDs.

**Selected reuse:** Read these authoritative records in one view. Account identity includes platform + bot/transport profile + user ID; chat/topic and session/lineage remain separate. Explicit verified cross-account links only.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Existing native records contain most links; no global product-person/role registry found.
- **Connected:** Friday worker records are Telegram-specific; global cross-channel projection absent.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Add identity/permission links only to existing native config/PluginState as required; do not merge by name, equal numeric IDs, profile name, or compression lineage. Missing historical origin/account evidence stays unknown.

Sources: [H_STATE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_state_common.py), [H_ROUTING](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/gateway/session.py), [F_ASSOC](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/associations.py), [F_INPUT](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/admission.py).

### C05. All-conversation archive, filters, messages, attachments

Native session listing/search, cross-profile listing, detail, timeline, paged messages, export and file/media routes; Friday has received-byte provenance and staged artifact metadata.

**Selected reuse:** Reuse SessionsPage/SessionDB; admin may inspect all authorized product profiles/channels. Join associations and verified attachment refs without mirroring transcripts.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Donor implemented; Friday task/attachment association UI absent.
- **Connected:** Profile-based archive exists in donor, no product-wide policy/enrichment connection.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Filter by native user/account/channel/chat/topic/session/task. Native file path/profile checks are not per-user authorization. Serve checked origin/staged artifact references and truthful missing/ambiguous attachment state, never arbitrary worker/host paths.

Sources: [H_SESSIONS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/sessions.py), [H_PROFILE_SESSIONS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/profiles.py), [H_FILES](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/files.py), [H_STATE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_state_common.py), [F_INPUT](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/admission.py), [F_ARTIFACT](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/artifacts.py).

### C06. Ordinary-user isolation and recall

DM session keys isolate chats; group/thread sharing is configurable. Worker controls enforce exact owner tuple. session_search can explicitly open another named profile DB.

**Selected reuse:** Preserve native session routing and per-owner task authorization; enforce user permission at all history, memory, files, search tools and controls.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Conversation separation exists; product data confidentiality/RBAC is not established by it.
- **Connected:** No complete cross-user policy connected.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Test user A against user B via search/profile parameter/session ID/media URL/tool result, group topics and shared memory. Separate profiles alone do not stop explicit cross-profile search. Restrict or scope recall and shared memory; do not rely on frontend hiding.

Sources: [H_ROUTING](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/gateway/session.py), [H_RECALL](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/tools/session_search_tool.py), [H_AUTHZ](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/gateway/authz_mixin.py), [H_SESSIONS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/sessions.py), [F_ASSOC](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/associations.py).

### C07. Task status, running/completed tasks and real stop

Friday native PluginState association already separates submission, stop intent, execution, quiescence, goal check and delivery; real systemd/container supervision. Hermes has native session interrupt/API-run stop and gateway lifecycle actions.

**Selected reuse:** Dashboard reads existing associations/native observations; administration calls existing Controller/WorkerHost in the owning host through a narrow authenticated control capability.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** DSH owner-command control implemented; native health source accepted per task. Public WorkerHost._controller binds only DSH.
- **Connected:** No admin REST control path; command receipt requires original bot/user/chat/topic/profile; dashboard and gateway are independent processes.
- **Verified:** Existing docs report bounded DSH component/live stop checks; this source inventory does not revalidate them or prove admin control.

**Remaining integration:** Do not forge Telegram receipts, spawn a second WorkerHost, mutate status, or equate gateway restart with job cancel. Add explicit admin authority bridge retaining original owner/destination/deadline; confirm descendants quiescent. A0 host binding remains required.

Sources: [F_HOST](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/host.py), [F_ASSOC](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/associations.py), [F_CONTROLLER](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/controller.py), [F_SUPERVISOR](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/supervision.py), `hermes_cli/plugin_command_context.py` in the [reviewed Hermes overlays](../patches/hermes/), `hermes_cli/plugins_gateway_work.py` in the [reviewed Hermes overlays](../patches/hermes/), [H_ACTIONS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/actions.py).

### C08. Configuration, profiles, local inference

Native config schema/GET/PUT with locked merge and persistent save, main/aux/custom model endpoints, profiles, tool/provider selection.

**Selected reuse:** Use native per-runtime configs and selected deployment profiles; production inference remains on owner local endpoints. Web-service connectivity is separate.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Hermes config UI implemented. DSH temporary patch renderer configurable. A0 helper hardcodes temporary 8001/8002 slots and dispatcher/40960/4096.
- **Connected:** Hermes writes do not automatically update pinned DSH patch/readiness or A0 consumed presets.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Expose intended/effective config and restart/new-session requirements. Controlled render/rebind of native worker configs and readiness hashes; no mutation under an active job. Parameterize A0 production slots/capacities. Preserve old test profile label.

Sources: [H_CONFIG](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/config_env.py), [H_MODELS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/models.py), [H_TOOLS_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/tools.py), [F_RUNTIME](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/host_runtime.py), [F_DSH_PROFILE](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/tools/render_dsh_local.py), [F_A0_CONFIG](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/a0_config.py).

### C09. Protected credentials and effective settings

/api/env and custom-endpoint cards mask values and reject masked writebacks; native A0 convert_out masks secrets. Hermes also has authenticated /api/env/reveal.

**Selected reuse:** Reuse secret storage and masked native cards; project effective settings with protected fields redacted.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Masking helpers exist; GET /api/config only flattens model and drops underscore keys, not general nested secret redaction.
- **Connected:** No Friday comprehensive admin response masking gate.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Reuse native redact_config_value for structural masking, explicitly cover protected fields it does not classify (for example password_hash), and verify config/custom-providers/dashboard-auth/API/log/file/plugin paths with synthetic secrets; restrict reveal independently or omit it from product role. Never serialize source credentials into artifact/logs/URLs.

Sources: [H_CONFIG](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/config_env.py), [H_NORMALIZE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_server_config.py), [H_REDACTOR](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/config.py), [H_FILES](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/files.py), [A_SETTINGS](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/settings.py).

### C10. Autonomous host search and source reading

Hermes native web_search/web_extract with plugin providers incl. SearXNG, DDGS, Brave, Exa, Tavily, Firecrawl; native browser tools separately selectable.

**Selected reuse:** Use Hermes native providers/tools and procedural skills; authoritative workspace evidence first, external retrieval when uncertain/current/version dependent.

- **Planned:** Mandatory; not an optional research command.
- **Implemented:** Donor capability implemented; owner retrieval trigger policy not demonstrated by current Friday SOUL.
- **Connected:** Selected deployment providers/reachability were not inspected (credentials forbidden).
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Enable supported provider and toolset in normal profile; add task-level retrieval/citation/uncertainty/prompt-injection rules and bounded failure behavior. Verify actual source retrieval applied to original task.

Sources: [H_WEB](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/tools/web_tools.py), [H_TOOLS_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/tools.py), [F_SOUL](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/config/SOUL.md).

### C11. Harness retrieval during a running job

Native web_search/web_fetch over ctx.web; shipped public anonymous HTTP fetch with public-address/connection validation, bounded reads and same-origin redirects. Search providers DeepSeek/Exa/Perplexity are separate from chat.

**Selected reuse:** Retain intact Harness; enable native tool-web and approved retrieval provider (Exa is a non-chat-search option if configured). Use native HTTP fetch for documentation. No donor upgrade or prefetch-only substitute.

- **Planned:** Mandatory for mid-job documentation gaps.
- **Implemented:** Native implementation exists; Friday DISABLED_ROWS explicitly disables web-search-deepseek and tool-web.
- **Connected:** Current temporary worker configuration disconnects tools. Bootstrap only forwards one model key and minimal env; bwrap shares network but omits /etc and proxy/DNS configuration.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Scoped search secret/provider references plus DNS/TLS/proxy readiness in bounded worker. Keep local inference mapping and filesystem/cgroup restrictions. Do not re-enable DeepSeek auxiliary model-backed search blindly under local-inference policy; classify approved retrieval service separately. Re-pin affected launch/readiness bytes.

Sources: [D_BASE](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/bundle/base/cordis.patch.yml), [D_WEB](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/tool-web/src/index.ts), [D_FETCH](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/web-fetch-http/src/provider.ts), [D_EXA](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/web-search-exa/src/index.ts), [D_SEARCH_MODEL](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/web-search-deepseek/src/provider.ts), [D_TRUST](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/tool-web/src/trust.ts), [F_DSH_PROFILE](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/tools/render_dsh_local.py), [F_DSH](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/dsh.py).

### C12. A0 retrieval during engineering

search_engine calls native SearXNG at localhost:55510; Docker supervisor normally starts it. document_query fetches public resources via native network helper. Development RFC forwards functions to configured A0 runtime, not a general Friday host web bridge.

**Selected reuse:** Retain whole A0. Reuse its search_engine/document_query and owned SearXNG startup, with approved public web egress/provider path.

- **Planned:** Mandatory; Hermes search alone does not satisfy A0 reachability.
- **Implemented:** Donor tools implemented. LocalNetwork contract admits only two private /v1 endpoints, fixed ports 8001/8002; actual policy must be separately verified.
- **Connected:** Public A0 host binding absent and current authorized network excludes web. Exact startup command is caller-owned; SearXNG running is unproved.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Separate local-model and approved public retrieval connectivity, include search service in bounded startup, prove DNS/TLS/fetch and original deadline/stop coverage. Change narrow deployment policy after review, never disable guard/allow host network globally.

Sources: [A_SEARCH](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/tools/search_engine.py), [A_SEARX](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/searxng.py), [A_SEARCH_START](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/docker/run/fs/etc/supervisor/conf.d/supervisord.conf), [A_DOCUMENT](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/plugins/_document_query/tools/document_query.py), [A_FETCH](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/plugins/_document_query/helpers/fetch.py), [A_DEV_RPC](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/runtime.py), [F_A0_CONFIG](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/a0_config.py), [F_A0_NATIVE](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/a0_native.py).

### C13. Interactive browser and host mediation

Hermes browser providers; Harness experimental Playwright/Chrome MCP or Stagehand packages; A0 built-in browser with container/host_required backend, per_context tabs and proxy configuration.

**Selected reuse:** Use native Hermes/A0 browsers; if Harness job needs interaction, native Playwright MCP scoped launch is available at pin. Prefer owned isolated browser, not owner personal profile.

- **Planned:** Mandatory when a task requires browser interaction; extra alternative engines remain selectable, not prerequisites.
- **Implemented:** Source implementation present; Harness browser not in selected base; no mid-job Friday retrieval bridge in existing plugin. Hermes mcp_serve is messaging tools, not a ready web-tool server.
- **Connected:** Browser installation/provider/egress and job cleanup are unverified.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Choose configured native backend, retain per-job context and cleanup/budget. Stagehand has separate model settings and must stay local if selected. Any host-mediated bridge is new glue unless a concrete existing broker is identified; do not claim one from tool presence.

Sources: [H_BROWSER](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/tools/browser_tool.py), [D_BROWSER](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/experimental/browser-use-playwright-mcp/src/index.ts), [D_BROWSER_STAGEHAND](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/experimental/browser-use-stagehand-native/src/index.ts), [A_BROWSER](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/plugins/_browser/tools/browser.py), [A_BROWSER_CONFIG](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/plugins/_browser/helpers/config.py), [H_MCP_SERVE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/mcp_serve.py), [F_PLUGIN](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/__init__.py).

### C14. Memory, session continuity and learning skills

Hermes persistent memory/session search/skills; Harness context/compaction/skill packages; A0 memory/skills/chat-compaction/context-doctor plugins.

**Selected reuse:** Hermes owns product memory/procedural learning; keep native worker context/history inside intact runtime and explicit job scope.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Donor capabilities and limited local memory evidence reported; privacy and cancelled-output truth require product checks.
- **Connected:** Source presence does not establish all features enabled.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Store verified retrieval procedures with sources/version and proper user scope; disable or scope worker global memory, never copy private chat histories into a second store.

Sources: [H_RECALL](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/tools/session_search_tool.py), [H_SKILLS_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/skills.py), [H_STATE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_state_common.py), [F_FOUNDATION](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/docs/foundation-status.md).

### C15. Schedules, reminders, cron and runs

Dashboard cron CRUD/pause/resume/trigger/run history and native scheduler ownership.

**Selected reuse:** Hermes is product scheduler; retain worker-native local job execution without a second global scheduler.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Donor implemented; Friday task join not present.
- **Connected:** Normal product schedule activation/delivery and disable semantics not accepted here.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Show real scheduler owner/status and verified delivery; test disabled task does not revive on restart. Do not translate paused cron metadata into stopped worker execution.

Sources: [H_CRON_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/cron.py), [H_STATE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_state_common.py), [F_HOST](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/host.py).

### C16. Coding, shell/files, subjobs and context

Whole Harness: read/search/edit, shell, jobs, subprocess, native sandbox, context, compaction/spill, sessions/checkpoints, skill/instructions, subagents, plan/todo and deliverables.

**Selected reuse:** Preserve complete headless runtime. Hermes terminal/files for small host tasks; do not copy Harness engine into plugin.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** DSH adapter connected at source with original budget, identity and outputs.
- **Connected:** Historical host-to-Harness fixture used synthetic Telegram ingress, not production channel.
- **Verified:** F_HOST_DOC reports 2026-10-07 02:49 real local code repair and independent fixture check; no new run here.

**Remaining integration:** Add web config/permissions without losing native coding semantics; retest changed path and relevant failure controls.

Sources: [D_BASE](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/bundle/base/cordis.patch.yml), [F_DSH](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/dsh.py), [F_SUPERVISOR](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/supervision.py), [F_HOST_DOC](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/docs/host-integration.md).

### C17. Engineering, stateful environment, repair and A0 UI

Whole A0 loop/extensions/tools, stateful code execution, document/browser/office/editor/time-travel, projects and intact Alpine UI. API-key REST differs from UI credential hash auth; absent UI credentials disable that native UI gate.

**Selected reuse:** Keep intact dedicated A0 and UI behind protected administrator access. Hermes remains product admin; A0 UI is engineering inspection/control, not product user authority.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Native source and REST adapter exist. Current public host binds DSH only; rejected A0core8ce is not accepted.
- **Connected:** A0 UI/API component startup evidence exists in foundation docs; engineering/host integration not accepted.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Accept repaired A0 candidate, bind host, preserve UI/API auth and resource limits. api_terminate_chat deletes context/history; use dedicated environment supervisor for real cancel and retain staged results.

Sources: [A_START](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/run_ui.py), [A_UI_AUTH](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/ui_server.py), [A_API_AUTH](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/api.py), [A_MESSAGE](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/api/api_message.py), [A_TERMINATE](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/api/api_terminate_chat.py), [A_SETTINGS](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/settings.py), [F_A0_NATIVE](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/a0_native.py), [F_RUNTIME](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/host_runtime.py).

### C18. Attachments, verified transfer and delivery

Friday admission retains exact Telegram origin and file IDs; stage helpers verify bytes; A0 accepts attachment base64; Hermes files/media handlers.

**Selected reuse:** Reuse verified staging and native delivery receipts; admin attachment links point to retained metadata and authorized byte streams.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Component implementation exists.
- **Connected:** All-channel attachment projection and ordinary-user download enforcement absent.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Keep bot/chat/topic/message/file_unique_id/size/hash/native session/task association. Do not equate a cache pathname or an ambiguous old record with ownership.

Sources: [F_INPUT](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/admission.py), [F_ARTIFACT](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/artifacts.py), [F_ASSOC](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/associations.py), [H_FILES](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/files.py), [A_MESSAGE](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/api/api_message.py).

### C19. Health, failures, logs, usage and observability

Native status/health, logs, system stats, analytics/token/cost fields, action status and scheduler run history; Friday status retains separate execution/goal/delivery states.

**Selected reuse:** Reuse dashboard panels plus small Friday task projection; do not create an observability database.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Donor/API fields implemented, accepted native source gate recorded.
- **Connected:** Friday comprehensive health/tasks view not connected.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Link real native failure/receipt IDs, masked settings and unavailable capability reasons. Source gate or PID presence cannot display product journey PASS.

Sources: [H_HEALTH](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/status.py), [H_ACTIONS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/actions.py), [H_STATE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_state_common.py), [F_HOST](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/host.py), [native source evidence limits](foundation-status.md).

### C20. MCP, plugins, connectors, APIs and channels

Hermes native plugins/MCP and platform adapters; Harness SDK/ACP/API/MCP/extensions; A0 REST/MCP/A2A/ACP/connectors plus email/Telegram/WhatsApp plugins.

**Selected reuse:** Hermes owns configured product channels and integrations; intact worker protocols stay internal. Avoid duplicate messaging consumer and autonomous orchestration authority.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Catalog/source presence; enabled integrations vary by deployment.
- **Connected:** No claim all optional connectors are configured or verified.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Expose useful available/disabled/unconfigured capabilities and selected equivalent. Existing credentials/providers only through native configured permissions; no automatic connector installation.

Sources: [H_PLUGIN_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_server_dashboard.py), [H_MCP_SERVE](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/mcp_serve.py), [H_TOOLS_UI](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/tools.py), [H_CHANNELS](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_routers/messaging.py), [D_BASE](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/bundle/base/cordis.patch.yml), [A_API_AUTH](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/helpers/api.py).

### C21. Native approvals, permissions and safety

Hermes tool approvals/secret scopes; Harness file-effect sandbox and web trust labeling; A0 tool-access execution policy and protected APIs.

**Selected reuse:** Keep existing controls and public-URL validation. External pages are untrusted evidence; retrieval never grants execution/credential access.

- **Planned:** Retain/reuse in product; no donor upgrade.
- **Implemented:** Mechanisms implemented; complete owner negative journey not run.
- **Connected:** New web/admin access must join these actual enforcement points.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** Keep original retries/deadline, size/redirect/cancellation limits and narrow egress. Test unavailable retrieval and malicious page credential/command requests through real task flow.

Sources: [H_AUTHZ](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/gateway/authz_mixin.py), [H_WEB_SERVER](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/web_server.py), [D_FETCH](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/web-fetch-http/src/provider.ts), [D_TRUST](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/web/tool-web/src/trust.ts), [F_DSH](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/dsh.py), [F_A0_CONFIG](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/adapters/a0_config.py).

### C22. Normal packaging and startup

hermes dashboard resolves/builds web assets; hermes serve is a separate headless backend and does not serve SPA. A0 run_ui serves intact UI/API; normal Docker supervisor separately includes SearXNG.

**Selected reuse:** Install/start the selected Dashboard, trusted Friday dashboard plugin, gateway and dedicated workers using existing native commands and supervisor. Include built assets/config/auth/approved web providers.

- **Planned:** Mandatory release scope.
- **Implemented:** Pinned donors/builds and component scripts exist; current deploy directory only contains upstream-observation service templates.
- **Connected:** No complete packaged web/admin startup proof in inspected snapshot.
- **Verified:** Source inspected only; no live check in this assignment.

**Remaining integration:** One tested normal install/start entrypoint with working admin URL/auth/assets, local inference and approved web routes; persist config/state; one channel consumer; preserve disabled legacy services. No manual owner assembly.

Sources: [H_START](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/hermes_cli/main_dashboard.py), [H_UI_POLICY](https://github.com/NousResearch/hermes-agent/blob/781334eea4b9225a3e194faf0c241d9afe218634/web/AGENTS.md), [A_START](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/run_ui.py), [A_SEARCH_START](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/docker/run/fs/etc/supervisor/conf.d/supervisord.conf), [F_RUNTIME](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/plugins/friday_rework/host_runtime.py), [F_FOUNDATION](https://github.com/alinescafs3mp-afk/friday_rework/blob/f80e187e25090427581fb696070d104ef4748ab3/docs/foundation-status.md).

## Overlap and proposed optional surfaces

These are explicit selection proposals and current configuration limits, not approved removal of intact donor code. Mandatory web, worker retrieval and product administration are not deferred. Additional provider-dependent functions remain visibly unconfigured until their actual dependencies and acceptance are available. No automatic cloud inference or duplicate channel consumer is introduced.

| Capability family | Retained equivalent / proposed scope |
| --- | --- |
| LSP/specialized repository navigation | Retain native opt-in LSP; select when repository requires an installed language server. Not a substitute for required web. |
| Voice/STT/TTS, vision, images/video | Visible optional capability with actual configured local/approved provider status; no cloud inference fallback or unsupported readiness claim. |
| Desktop/computer use, previews, native desktop GUIs | Preserve intact donor code; host desktop control and alternative product GUI remain proposed non-core surfaces. Required Hermes admin and intact A0 UI are not deferred. |
| Extra global goals/workflows/teams/kanban/schedulers | Use existing Hermes owner/task lifecycle. Preserve worker local plan/todo/subagents; keep independent global planners/schedulers disabled unless an explicit bounded role is selected. |
| Worker projects/editors/time travel/document/office | Preserve in intact worker/UI; available per actual image/tool policy. Product admin references native state; no parallel workspace engine. |
| Optional external platforms/services and extra memory engines | Keep complete source catalog visible and enabled/configured truth explicit. Hermes selected channel/provider is canonical equivalent; no duplicate worker channel consumers. |
| Updates, export/import, backup, telemetry and diagnostics | Preserve native mechanisms; changes to pins remain explicit reviewed operations. No automatic donor upgrade, bulk legacy import, second telemetry service, or unrequested external telemetry. |

## Complete native module-family catalog

The lists below preserve the full inspected donor family catalogs, including overlapping and optional modules. They establish source availability only, not installation, enablement or successful operation. The selected useful behaviors and missing integration are described above.

### hermes — `781334eea4b9225a3e194faf0c241d9afe218634`

`browser`, `computer_use`, `context_engine`, `cron_providers`, `dashboard_auth`, `disk-cleanup`, `google_meet`, `hermes-achievements`, `image_gen`, `kanban`, `memory`, `model-providers`, `observability`, `platforms`, `security-guidance`, `spotify`, `teams_pipeline`, `video_gen`, `web`.

### dsh — `5badb15009ae1756c3afe0ae0cef1faafc290ccc`

`acp`, `api`, `attachment`, `boot`, `browser-use`, `bundle`, `client`, `compaction`, `computer-use`, `context`, `core`, `credentials`, `deliverables`, `document`, `experimental`, `extensions`, `feedback`, `fs`, `goal`, `guard`, `hooks`, `host`, `identity`, `interaction`, `jobs`, `llm`, `lsp`, `mcp`, `plan`, `preset`, `ptc-runtime`, `sandbox`, `schedule`, `sdk`, `session`, `session-query`, `settings`, `shell`, `skill`, `spill`, `ssh`, `storage`, `subagent`, `subprocess`, `telemetry`, `terminal`, `test-support`, `todo`, `typert`, `util`, `web`, `webhook`, `workflow`, `workspace`.

### a0 — `e3051fb584b1a36be2b0a0c90606f1c2c2d356ec`

`_a0_acp`, `_a0_connector`, `_agent_editor`, `_browser`, `_chat_branching`, `_chat_compaction`, `_chat_naming`, `_code_execution`, `_commands`, `_context_doctor`, `_context_window`, `_desktop`, `_discovery`, `_document_query`, `_editor`, `_email_integration`, `_error_retry`, `_goal`, `_infection_check`, `_kokoro_tts`, `_memory`, `_migrate_agents`, `_model_config`, `_oauth`, `_office`, `_onboarding`, `_orchestrator`, `_pin_to_top`, `_plugin_installer`, `_plugin_scan`, `_plugin_validator`, `_promptinclude`, `_sidebar_folders`, `_skills`, `_telegram_integration`, `_text_editor`, `_time_travel`, `_tool_access`, `_whats_new`, `_whatsapp_integration`, `_whisper_stt`.

## Evidence boundary

The read-only inventory checked 76 referenced file hashes against the pinned source or exact reviewed overlay, without starting services, models, browsers or workers, reading credentials, changing donors or applying updates. Actual provider availability, browser/search installation, active effective settings, final A0 integration and normal packaged startup remain unverified. [The acceptance delta](../validation/acceptance-web-admin.json) defines the required complete journeys.
