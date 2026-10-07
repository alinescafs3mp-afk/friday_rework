# Native Friday installation candidate

`scripts/friday_install.py {plan,install,check,dashboard-check,start,reconcile} --input <private JSON>`
is a finite composition of existing preparers, native PM and build APIs. It
does not run a service manager, keep a worker daemon or create an account store.
The current candidate installs a template and connects conditional native
startup. The pinned composition still **refuses startup** at missing mandatory
admission. This is source wiring, not normal-install/start acceptance or a release. Installation/download/build are
future explicitly invoked effects; this implementation task executes none.

Input fields are `home`, `bootstrap_python`, `hermes_donor`, `hermes_prepare`,
`sources_lock`, `dsh_donor`, `a0_donor`, `product`, `project_files`, `seconds`,
`containment`. The latter is the exact `{ "path": "/usr/bin/bwrap", "sha256":
"<reviewed system binary SHA-256>" }` pin.
Pins have exactly `path` and `sha256`; JSON is private, owner-only, single-link,
canonical and duplicate-field-free. `project_files` maps reviewed repository
relative paths to SHA-256, including the installer/helpers, profile compiler,
complete Friday plugin/persona/research and Hermes overlay inputs. `product`
uses the explicit [normal profile schema](product-profile.md), currently with
the `default` receiving profile. Model, endpoint, capacity, output reservations,
web limits, Dashboard public authority and operator are actual supplied inputs.
No secrets belong in this JSON, command arguments or preparation receipts.

The parent integrates its final reviewed `scripts/hermes_prepare.py` and supplies
its exact pin. The installer invokes that actual stable CLI, consumes its complete
source receipt and checks all exported/overlaid file bytes, modes, commit/tree
and absence of hidden source dotenv or unexpected source files. It supports a
full patched Hermes export without `.git`; it never resets an upstream checkout.
Inputs missing that reviewed preparer are refused. This branch does not merge
or copy the concurrently reviewed preparer.

A fresh private home is claimed exclusively before effects. Existing foreign
homes/config/plugins are refused. An interrupted install retains its work;
a PARTIAL claim requires reconciliation and is never silently replayed or
deleted. An admitted final filesystem operation may publish the complete
template before the invocation then exceeds its deadline. That receipt retains
the original claim, deadline and boot ID as provenance; it cannot prove a
successful invocation exit. Identical complete output may be inspected
idempotently: every byte is checked again, without PM, build or runtime effects.
The receipt describes output, not a task database or an admission authority.

The future install order is complete source preparation; native PM
`install --tools-only`; `install --extra all --extra telegram --extra web --extra exa`;
native selected Python; existing Node dependency preparation and TUI/Dashboard
builders/freshness; installation-local `ensure_install_launchers`; truthful
external install stamp containing upstream base and overlays; private trusted
Friday plugin; native atomic additive configuration and actual SOUL; existing
Harness source/toolchain/build/smoke; A0 source inventory. OS account HOME stays
unchanged. Ambient credentials, PYTHONPATH, profile/runtime and host-lock
overrides are stripped. No global launcher or user PATH is published. The
original monotonic budget starts before input intake, includes verification,
serialization, publication, fsync and final success admission, and is inherited
by native completion. The private PARTIAL claim binds that deadline and the
Linux boot ID; a newly supplied deadline cannot restart internal completion. Long admitted filesystem IO can leave an observation
before expiry is detected; that invocation fails and never grants runtime or
successful completion. Incomplete claims/work remain for explicit reconciliation.
There is no reset or per-phase cleanup allowance. Every command reserves cleanup
inside this same deadline; unconfirmed closure is `STOP_UNCONFIRMED`.
The CLI preserves this typed condition with fixed, secret-free stderr and exit
code 3. Ordinary refusals use exit code 2. An unconfirmed stop never authorizes
a retry or release of process ownership.

Normal installer packaging now requires the distribution's **bubblewrap** OS
package at `/usr/bin/bwrap` and working unprivileged PID namespaces. Supply the
reviewed binary hash as `containment`; the installer neither downloads nor
installs this dependency, and refuses changed/unprotected binaries. Before
claiming a fresh home, it runs a harmless actual namespace capability check.
Every complete source-preparer, PM, native build, Harness and A0 family then runs
inside `bwrap --unshare-pid --die-with-parent --new-session`, including descendants
that call `setsid`. Linux namespace teardown closes these detached descendants
when the outer command/parent exits or times out. There is no process-group-only
fallback, new service manager or independent lifetime budget. This namespace
adds lifetime custody; it does not change the original filesystem/network grant.
The namespace uses `--dev /dev` for bubblewrap's private standard devices;
it never binds host hardware devices. A root bind alone is mounted without
device access and made Git's `/dev/null` open fail in the first normal attempt.
The required pre-claim probe now verifies read/write access to `/dev/null` as
well as the distinct PID namespace, so that defect refuses before home creation.
The host verifies the root-owned binary and exact SHA before planning/admission
and again before every contained launch. The pure input/source consumer does
not repeat host UID ownership checks inside the user namespace, where UID 0 is
unmapped; no weaker binary check, alternate launcher or fallback is introduced.
Cold source validation imports `importlib.machinery` explicitly rather than
depending on a previous caller's imports.
A machine that cannot create it must obtain the normal supported OS dependency
and namespace policy before a separately authorized install can proceed.

Failures report a fixed phase/reason, child exit/timeout/reap facts where
observed, and the original input hash. Child argv, raw stdout/stderr, environment,
credential values and credential paths are not printed. Protected
`FRIDAY-INSTALL.failure.json` retains bounded status/hash/byte-count metadata,
process incarnation when observed, and the original boot/deadline/input claim.
Failure-receipt publication can fail; that never converts uncertain custody to
a normal refusal. Native helper exit 3 remains `STOP_UNCONFIRMED` even after its
wrapper is reaped, because external native units can have separate lifetimes.

Finite installer commands run as the bubblewrap PID namespace's PID 1. On a
normal monitor exit, bubblewrap has waited for that init and the kernel has
drained its descendants. This changes command signal handling and orphan
reaping compared with bubblewrap's separate init, so actual preparer/PM
compatibility is required before runtime acceptance. A monitor timeout, signal,
missing status or internal exit 3 remains `STOP_UNCONFIRMED`; pipe EOF and
reaping only the monitor are insufficient to release custody.

`reconcile` is read-only. It verifies an exact original PARTIAL claim, the same
boot, original input bytes and any bound failure receipt, and reports the
remaining original clock (including exhaustion). It reads no referenced TLS
or credentials, performs no native commands, and preserves work and stop intent.
It **never admits resume** or resets the budget. Legacy claims did not retain a
native child receipt; an empty home, absent parent or available lock cannot prove
current cessation. Repairing source pins also requires the lead's independent
review. No `resume` command, automatic replay, renamed/deleted home or alternate
installation route is introduced. A separately reviewed continuation still needs
current native cessation and sufficient original budget; this source package
does not authorize or execute one.

Pure pre-source validation uses a distinct project module namespace. After every
native source byte is verified, completion loads the native `tools` and `plugins`
regular packages, verifies their source paths, and then appends project modules.
Profile identity uses the official validator before any effectful native config
import. Cold entry tests must not preload packages that hide this ordering.

Harness writes a new `home/harness` donor checkout and retains its intact native
source/build machinery. It never builds over the frozen donor. A0 inventory is
read-only source preparation, not image provision, daemon start or kernel
acceptance. Its existing fixed deployment remains explicit in `a0_runtime.py`;
this entry does not substitute a portable deployment, retry G3, invent a useful
web contract or change the stopped kernel grant.

Generated gateway and Dashboard argv are the actual native parsers:
`hermes -p default gateway install --no-start-now --no-start-on-login`, then
`gateway start` and `dashboard --host … --port … --no-open`. They are generated plans; conditional start uses these exact donor operations
only after the checks below. None was invoked in this source-only assignment. No `--force`, `--replace`, `--all`, isolated
lock partition, upstream install.sh or update is used. Native gateway units,
token locks and host-wide Dashboard rendezvous remain the intended owners.

The native profile consumer verifies real auth engagement, the explicit Basic
operator, mandatory Exa and absent cloud fallback. Before future native build,
existing live host records with foreign home/profile/authority or uncertain
process incarnation refuse installation. Matching records are policy inputs,
not proof of HTTP/auth/source ownership. The Dashboard overlay below closes
the native pre-bind/attach boundary at source level. This task does not verify
a gateway unit, read live credentials, validate channel account/token ownership
or admit workers. A receipt marked READY cannot bypass the original runtime, source, credential,
web, ownership or original-deadline checks.

Remaining integration requirements are concrete: portable A0 image/toolchain
preparation or separately admitted exact fixed deployment; useful web for A0 and
both workers in the normal compiler; independent review and actual authenticated
Dashboard startup/attach acceptance; protected launch credentials and scoped pool/channel ownership;
native gateway exact-home unit installation/readiness; final PM/build realization
and independent acceptance of all six mandatory web/admin journeys. Ordinary
SAFE-tool and text-only capacity compatibility limitations remain as documented
in the normal profile. None is removed by this source candidate.


The `dashboard-owner` donor overlay extends existing native CLI attachment,
`gateway.host_rendezvous`, server startup and the existing identity route. It
adds no supervisor, lock directory, account store, service flags or token gate.
For a Friday installation, native CLI validates the actual complete Hermes
source receipt/file bytes/modes and dirty external install stamp, the complete
installed Friday plugin, exact home/default profile/public authority, configured
admin operator and native Basic settings. The initial source check is mandatory
before Desktop/isolation/headless shortcuts. Missing installation/profile markers
refuse; ordinary unmarked Hermes retains its native behavior.

Native startup validates the registered real Basic provider and active auth gate,
then claims the existing per-OS-user `serve` lock before uvicorn configuration,
port probe or bind. Contention refuses; this path never binds as observe-only or
reaps another owner. The same lock remains held until shutdown, including a
post-bind identity/publication failure; shutdown runs before lock release and
before uvicorn re-raises a captured termination signal. Friday does not register
the native signal pre-handler that would release before shutdown. An unknown
startup or failed shutdown retains the native host lock until OS-process exit or
explicit reconciliation by its existing owner; it never frees a slot on an
unconfirmed stop. Native
publication must succeed with a process-start fingerprint. The record carries
computed source/home/operator/auth binding; it is never accepted on label alone.

Attachment requires native positive `(pid,startTime)` liveness, exact record
source/home/profile/authority, consistent private rendezvous token, a matching
live identity and an unchanged record/incarnation/token after the probe. The
Basic signing secret HMAC-binds the native credential selection to the declared
identity; neither passwords, signing keys nor password hashes are published.
Ambient Basic credential values must match the selected home's private native
`.env`; native protected config credentials are also supported. Native plaintext
password and password-hash selection remain supported. A stable configured
signing key is necessary for reattachment; native random per-process keys are
explicitly unprovable.

The native role token cannot pass the general Basic cookie/bearer gate. Friday
therefore extends the existing native gate for only `GET /api/host/identity`:
the private native role token establishes same-OS-user authority, a real
registered Basic provider supplies a local request principal and the unchanged
Friday admin policy validates it. No operator cookie/bearer is sent to an
unproved port, returned to this caller or persisted. All other routes retain
normal Basic authentication; a role token alone cannot enter administration.
The identity response HMAC-binds a fresh per-probe nonce, actual PID/start
fingerprint, role-token fingerprint and computed source/home/auth policy to the
actual Basic signing key. Client verification uses its original nonce; replay,
foreign listeners and caller-written identity labels cannot substitute a proof.

`GET /api/host/identity` is the sole added read route in the existing Friday admin
allowlist. Source/config/provider drift refuses, and Basic-authenticated foreign
principals remain denied. OS-user control of private installation files/signing
keys remains the native trust boundary; this does not defend against an attacker
already controlling that OS account.

`dashboard-check` consumes the installed native source checker after ordinary
pinned installation inspection. It verifies source/install metadata only and
returns `SOURCE_OWNERSHIP_VERIFIED_RUNTIME_NOT_RUN`, `ready=false`, credentials
unchecked. Whole `start` still refuses absent A0/web/kernel admission. Successful
source fixtures or this narrow check do not authorize native units, workers,
channel login, model calls or all-six release acceptance.

Validation uses the actual composed donor, private synthetic source/config and
Basic keys, native lock/record/parser/CLI/auth middleware and ASGI identity route.
Network transports and bind/main-loop boundaries remain intercepted. The record
policy cases reuse a once-verified complete source identity; byte-drift cases and
full-source positives use the uncached native consumer. Actual authenticated
HTTP/socket startup, race under independently scheduled real processes and all
six live journeys still require parent integration and independent acceptance.


## Protected local Dashboard profile

Normal configuration always selects the native `dashboard.require_auth: true`
policy and existing Basic provider. A loopback HTTP authority is supported with
a loopback bind; external authority still requires HTTPS. Both installer input
validation and the native profile compiler enforce the same distinction. The
native startup gate remains mandatory even under Desktop or `--insecure`, and
Friday refuses effective configuration that removes its required-auth policy.
This adds no alternate login, credential store or public listener.

The changed source passed 16 new local-policy/password controls, 132 existing
profile/installer checks, 75 Dashboard ownership checks and all eleven complete
native source checks. Password checks use synthetic private profiles and the
real native provider without sockets. Independent review and actual browser,
credential, runtime and complete product journeys remain required.

## Direct TLS for the owner LAN

The `dashboard-tls` overlay follows the complete preceding fifteen layers and
uses the existing Uvicorn listener, native Basic login, host lock and ownership
proof. It adds no proxy, certificate issuer, listener or supervisor. The normal
product `dashboard` object accepts an optional `tls` object:

```json
{"certfile":"dashboard-tls/server.pem", "keyfile":"dashboard-tls/server.key", "cafile":"dashboard-tls/ca.pem"}
```

For the declared VMware route, select guest bind `192.168.12.128`, port `9119`,
and `https://<owner VMware host LAN IP>:9119` as `public_url`. The actual host
address is still a deployment input. The owner configures TCP host 9119 to guest
192.168.12.128:9119. The guest DHCP address must remain consistent with this
configuration; the unrelated listener on 8443 is never touched. No wildcard
bind, HTTP on LAN or certificate verification bypass is supported by this mode.

Normal installation additionally requires `dashboard_tls`, mapping each of the
three TLS keys to the existing `{path, sha256}` input-pin shape. Supply files
named `server.pem`, `server.key`, `ca.pem` in one real, private operator input
directory outside the fresh product home. All files must be owned, regular,
single-link and private; symlinks and public permissions refuse. The installer
copies these exact pinned bytes once into the product's private `dashboard-tls`
directory, then the actual native profile/start consumer loads those paths.
Existing or partial TLS destinations refuse adoption; originals remain intact.
The installer does not generate certificates, read an unrelated credential home
or install browser/system trust. Rendering configuration never validates a live
certificate or grants readiness.

Provide an unencrypted PEM key and a valid server chain signed by the supplied
CA bundle. The certificate must include **both** the public host IP/hostname
and the literal guest bind IP in its SAN. Native identity clients dial the guest
with normal hostname verification against that guest IP, while sending the
exact public HTTP Host. A bounded in-memory OpenSSL handshake checks key/chain,
expiry and both identities before startup; it is not a LAN/browser test. The
client uses only the explicit CA and ignores ambient proxy variables. Redirects
refuse before another request can receive a role token. The original nonce/HMAC,
source/profile/incarnation/token proof remains mandatory after HTTPS.

Direct TLS disables forwarded-header interpretation. HTTP and WebSocket guards
require the exact public authority including port, HTTPS/WSS and, when supplied,
the exact public Origin. Native Basic/session/CSRF policy remains unchanged.
Existing protected loopback HTTP and externally terminated HTTPS profiles without
`tls` retain their original transport. CLI attachment, browser links and native
plugin notification choose the declared public/guest routes consistently.
Plugin activation remains subject to the existing native authentication and
Friday route allowlist; transport configuration does not authorize that route.

The owner must trust the appropriate CA in the intended browser separately and
verify the real NAT route, authenticated browser use, actual startup/reattachment,
service/PM ownership and complete product journeys after independent review.
Whole-product `start` retains its existing A0/kernel/web admission refusal.
No service, network, firewall, VMware, trust-store or model effect is performed
by this source candidate.


Normal `start` now keeps the initial invocation deadline while it verifies the
completed installation and selects the existing PM Python, then re-execs the
internal native helper in that exact generation. The helper revalidates original
input/composition/profile/plugin identity. It checks actual PM ownership and
both frontend freshness stamps, invokes the separately reviewed native
credential bootstrap/route/channel consumers, validates the Dashboard's actual
source/home/Basic/TLS identity, and reads original per-profile worker receipts.
Inputs, full source/plugin inventory, generated native launcher, protected
credentials/pool and TLS files are snapshotted **before** admission and compared
again before service operations. New credential files also count as drift.
No new READY switch, permission receipt, daemon or job store is introduced.

The present TLS-only base lacks `hermes_cli.friday_credential_admission` and the
original normal compiler cannot supply an accepted A0 useful-web runtime or both
workers. The separate credential/onboarding repairs must join at the canonical
root. Missing or stopped A0/kernel admission remains a mandatory blocker; no
G2/G3/G4 attempt/grant is reused. Positive service fixtures intercept that effect
boundary explicitly; they do not establish a valid complete product admission.

When admission genuinely becomes available, normal startup discovers the
trusted installed Friday, native Basic and native `web-exa` plugins synchronously
through `discover_plugins`. It configures the actual native auth gate and checks
the registered Basic provider before service effects. Native Dashboard startup
also performs ordinary discovery. The optional existing activation POST remains
denied by the original Friday admin/role-token policy; no HTTP activation or
localhost privilege escalation is required for this bootstrap path.

Only the existing Linux **user** gateway unit is supported by this candidate.
Foreign/changed units, system-scope duplicates, legacy units, drop-ins,
unprovable process incarnation or a running unit without its rendezvous refuse.
There is no unit adoption, refresh, forced replacement or legacy cleanup.
Installation retains `--no-start-now --no-start-on-login`; startup uses the
original bounded PID namespace/command custody and original deadline. Exit 0
is followed by actual native unit PID/InvocationID, process-start/token and
native `running` status checks. A proved existing receiver is attached without
another start. Command or observation ambiguity retains `STOP_UNCONFIRMED` and
requires native ownership reconciliation; it never retries or claims cessation.

The last step transfers the same foreground process to the existing native
Dashboard launcher in the operator's terminal. The gateway's durable owner is
its native unit; the Dashboard retains native pre-bind host locking,
publication, authenticated nonce proof, exact owner URL and shutdown lifecycle.
The finite clock governs verification and dispatch, not a new daemon lifetime.
A failed handoff after gateway startup is `STOP_UNCONFIRMED`, not a successful
startup or cleanup receipt. No service, Dashboard, socket, key, PM/build/install,
model, worker, browser trust or VMware forwarding was executed by this task.

`GET /api/plugins/friday_rework/health` uses the existing native Basic/operator
and Friday admin route authority. Its installed plugin module reads effective
configuration without seeding homes and calls the original runtime receipt
checks in each allowed native profile scope. It exposes missing/disabled/
unverified workers and `execution: NOT_OBSERVED`; `runtime_ready` remains false
and live journeys remain NOT_RUN. The existing "Worker health" tab loads this
view only on an explicit administrator action through the native Dashboard SDK.
It writes no native state or grant. This view
can be used through an independently admissible **existing** native Dashboard;
there is no alternative admin launch mode to bypass product or A0 admission.

The owner supplied public authority is `https://192.168.1.78:9119`, distinct from
guest bind `192.168.12.128:9119`. Input remains configurable and exact. No actual
certificate, browser trust, host route, authenticated LAN/attach, startup,
service/PM realization or all-six-journey acceptance is inferred from these
parameters or the source controls. Independent review and final root join/gate
remain required.

The seventeenth overlay adds `read_user_config_effective_readonly` to the native
effective-config module. It reuses the same normalization pipeline and refuses
malformed/non-mapping input without default recovery, cache publication, home
seeding or `.good` backup writes. The ordinary native loader is unchanged.

The running gateway must answer the existing native `identify` control verb with
its PID/start identity and the exact Friday source receipt, plugin files and
protected configuration captured before the control server starts. The native
consumer revalidates those inputs for each identification; changing them cannot
adopt another generation into an already running process. Upstream Git SHA and
a retained `gateway_state.json` alone are insufficient. Missing live proof, a
stale/foreign status, or changed configuration refuses attachment without retry.
Every interruption after a new gateway service handoff retains
`STOP_UNCONFIRMED`, including interruption at the Dashboard foreground transfer.

Worker health preserves administrator/scope admission failures. Inside an
already authorized profile, missing or malformed configuration produces a
redacted unverified row while the other authorized profiles remain inspectable.
This diagnostic never grants worker readiness or clears the A0 acceptance stops.
