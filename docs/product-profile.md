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

Profile IDs must already satisfy the native Hermes name validator. Mixed-case
and reserved names are refused before profile creation or product admission;
individual identity fields are never silently normalized. The compiler and
onboarding use the same validation as native routing.

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
sets the explicit native `dashboard.require_auth: true` policy. The existing
Hermes gate, password provider, sessions, CSRF and Host/Origin checks apply on
loopback as well. A local URL such as `http://127.0.0.1:9119` requires a loopback
bind; plain HTTP cannot expose the listener to the network. A real external
HTTPS authority remains supported. No fictional domain is needed for local
administration. The port in the declared authority must match the listener;
proxy prefix/port translation needs a separately reviewed launcher contract.

The native policy accepts only a boolean. An explicit required gate cannot be
bypassed by `--insecure` or the Desktop loopback exemption; absent providers
stop startup. Friday's source/owner proof additionally requires this policy to
remain true in the effective protected configuration. Donor deployments that
do not select the policy retain their existing behavior.

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

The native named-provider resolver checks credential pools before a configured
key reference, and a missing local key can yield `no-key-required`. Rendering
cannot prove those runtime ownership conditions. The launcher must verify fresh
scoped credential/pool ownership and key readiness before any model request.
Product admission still requires its own native grants; no ready receipt or
enabled user is fabricated. Offline synthetic consumer checks demonstrate
source wiring only. Independent review, actual installation, useful web for
both workers and all six live product journeys remain required.

The native Dashboard also has an explicit direct-TLS option for the declared
VMware owner LAN route (guest `192.168.12.128:9119`, host LAN IP supplied at
deployment). Set `dashboard.tls` to the three protected `dashboard-tls` file
paths documented in `native-installer.md`, and provide pinned certificate/key/CA
inputs to normal installation. Uvicorn loads them through the existing Dashboard
lifecycle; native attachment validates the actual guest certificate and existing
nonce/HMAC owner proof, and the public Host/Origin includes the exact host port.
No certificate issuer, proxy service or browser trust change is introduced.
Local protected HTTP and externally terminated HTTPS remain separate supported
configurations. Source checks cannot establish actual certificate provisioning,
NAT/browser trust or runtime readiness; original whole-product admission gaps
remain in force.
