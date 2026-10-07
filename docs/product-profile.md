# Normal Friday product profile

`tools/configure_product.py` is the nonsecret renderer/fresh materializer for the
reviewed, patched Hermes installation. The installation composer and native
launcher remain integration responsibilities. Rendering returns
`TEMPLATE_INCOMPLETE`, `ready: false`; it neither installs nor starts Hermes,
creates grants, checks worker receipts, loads credentials or runs inference.

Run with the Hermes-owned interpreter and its exact patched source/plugin
composition on the Python path. Supply an owned private JSON input, with each
field exactly once. YAML/callable values and credential values are refused.
`--input PATH` renders the bundle to stdout. Adding `--home PATH` creates a new
private home under an existing real private parent, using native configuration
locks and the atomic writer. It writes only `config.yaml`, the actual shipped
`SOUL.md`, and `FRIDAY-PROFILE.json` (plus the native lock). Existing homes are
never adopted or overwritten. An interrupted fresh write stays partial for
reconciliation; repeating the command cannot silently adopt it.

Required input fields:

| Field | Explicit operator values |
|---|---|
| `profile` | Actual native receiving/administrative profile name |
| `inference` | `base_url`, exact served `model`, `key_env`, `context`, `max_input`, `main_output`, `summary_output`, `margin`, `template_overhead` |
| `web` | `profile: exa-paid`, integer `extract_char_limit`, integer `extract_timeout` |
| `dashboard` | Literal bind `host`, integer `port`, exact `public_url`, `operator` with `provider`, `user_id`, `org_id` |
| `accounts` | Nonempty list of exact `platform`, `transport_profile`, `account_id`; transport must equal the receiving profile |
| `runtime` | Explicit `{"enabled": false}` while unavailable, or the unchanged native validated worker configuration with exact receipt/source references |

Inference endpoints must be credential-free local literal `/v1` endpoints.
There are no model, context, output-reservation, endpoint or credential defaults.
The accepted bounded-context extension retains its compatibility label
`local_test`; that internal label does not make this product profile a test
profile. The input ceilings/reservations are still explicit operator values,
including for larger profiles. All built-in model-capable auxiliary tasks and
native delegation receive the explicit local route and empty fallback chains.
Credential-dependent provider discovery is not selected. Inference and Exa
retrieval remain separate connections; no cloud inference fallback is added.

The currently accepted compatibility guard is text-only and refuses multimodal
requests. Selecting a local model with vision support does not by itself extend
that reviewed boundary. Full media/capacity compatibility remains explicit
integration work; the renderer does not disable native vision or claim its
acceptance.

The normal operator profile preserves native agent, approvals, tools, memory,
skills and delegation settings. Its ordinary toolset is `hermes-cli` plus
mandatory web and Friday workers/results. Every configured channel and CLI
receives the same selection. Native scheduling remains under its existing
operator policy. Web caching retains the native useful default while retrieval
is explicitly Exa paid, with keyless rescue disabled. Research guidance is the
actual shipped `RESEARCH.md`, and persona is the actual matching shipped
`SOUL.md`; no history/personality from a developer or owner home is copied.

Declared token-based native channels are explicitly enabled; other known
channels are explicitly disabled, including against environment-driven enable.
The contract records each selected channel's actual native token variable.
Channel-specific non-token transports require their own reviewed input contract
and are refused here. Actual native account identity, token ownership and
profile-home routing still require launcher verification.

Dashboard authentication is mandatory. This implementation supports the native
BasicAuth identity: `provider: basic`, `user_id` equal to the actual configured
username, and explicit `org_id: ""`. Other native auth providers need their own
reviewed settings; display names cannot stand in for an identity. The renderer
uses the actual native auth-gate predicate and refuses loopback plus loopback
public URL. A loopback backend with an explicit non-loopback HTTPS public URL
engages the native gate. Alternatively, an explicit non-loopback bind engages
it. The port in the declared public authority currently must match the listener;
proxy prefix/port translation requires a separate reviewed launcher contract.

Only `dashboard_auth/basic` is selected; alternative bundled auth backends are
explicitly disabled. The contract names the native username, password-hash and
signing-secret references. The native launcher must load these from the owned
protected scope, verify the exact operator, actual `app.state.auth_required`,
controlled Host/Origin/public URL and reject ambient username/password/public
URL overrides. It must not use the Desktop SSH auth exemption. Merely writing
the config or binding to loopback does not establish authenticated readiness.

The bundled BasicAuth resolver reads raw process environment, **not** the
context-local model `secret_scope`. Its dedicated native launch environment
must therefore contain only explicitly loaded protected values, with unrelated
ambient auth settings excluded. No auth key is embedded in this profile.

The protected `friday-local` onboarding template has nonsecret settings and the
existing SAFE tool policy. The exact existing native API prepares each fresh
home, keeps it disabled, captures scoped credentials separately, checks native
grants and applies its original activation conditions. No owner keys, history,
memory files or skills are cloned. Receiving/admin policy stays in the
authorization home; the template contains neither Dashboard nor gateway
authority. User skill discovery does not borrow owner/project directories.
Native numeric budget metadata is accepted only at five exact count paths;
strings, booleans, negative counts and similarly named credentials are refused.

Ordinary users still have the accepted memory/history/file/web/worker/result
SAFE set. Direct skill/cron/terminal expansion remains a concrete policy gap,
not a grant from this composer. A reusable user template cannot safely share
the operator's worker home/receipt, so its worker runtime remains explicitly
disabled until a profile-specific reviewed runtime is supplied. Existing
onboarding runtime/receipt/source-hash checks remain intact, including the A0
reconciliation refusal. Root integration must resolve this missing capability
before claiming a complete normal installation.

The credential admission overlay runs from native `load_hermes_dotenv` before
project, ambient or managed fallback. It checks the installed source through
the existing dashboard-owner verifier, the declared receiving home/config and
private native `.env`. It uses native secret context variables and the existing
`auth.json` credential-pool schema; it creates no second credential store.
The native pool still has priority, but only owned, explicitly local entries
are admitted. Missing local credentials are refused, including the donor's
`no-key-required` placeholder. This candidate supports keyed local routes;
unauthenticated routes and external secret managers have no admission contract.

The actual main and auxiliary resolvers and direct auxiliary client factory
require the declared local endpoint/model and owned key. Cloud routes, alternate
credentials, OAuth pool entries, ambient inference proxies and fallback routes
are refused before client creation. Exa, native channel tokens and BasicAuth
operator settings keep separate protected references. Native secret misses
cannot borrow process, project, global-root or another user's credentials.
Ordinary user resolution also requires its existing current native capability;
an operator's receipt cannot activate a user or expand the accepted SAFE tools.

Gateway configuration admits only declared channels and owned tokens before
native weak-token diagnostics. The native Telegram adapter checks its actual
initialized bot identity after `getMe` and before starting message consumption.
A mismatch closes that adapter with a static, non-retryable refusal. The guarded
fixture exercises the actual initialization against synthetic transport data;
no live account, socket or exclusive channel consumption was observed. Other
platforms have token-scope checks here; actual account proof remains unaccepted.

These are source and offline consumer results. Product admission still requires
its native grants. Independent review, canonical installer integration, portable
runtime preparation, real authenticated cold startup, channel exclusivity,
useful autonomous web for both intact workers, full administration and all six
live product journeys remain required. The separate stopped A0 work is not
restarted by this overlay.
