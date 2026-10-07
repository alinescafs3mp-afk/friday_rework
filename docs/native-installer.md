# Native Friday installation candidate

`scripts/friday_install.py {plan,install,check,dashboard-check,start} --input <private JSON>`
is a finite composition of existing preparers, native PM and build APIs. It
does not run a service manager, keep a worker daemon or create an account store.
The current candidate installs a template and **refuses startup**. It is not
normal-install/start acceptance or a release. Installation/download/build are
future explicitly invoked effects; this implementation task executes none.

Input fields are `home`, `bootstrap_python`, `hermes_donor`, `hermes_prepare`,
`sources_lock`, `dsh_donor`, `a0_donor`, `product`, `project_files`, `seconds`.
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
homes/config/plugins are refused. An interrupted install retains its PARTIAL
claim and work and requires reconciliation; it is never silently replayed,
deleted or adopted. Completed installation with identical input may be inspected
idempotently; it does not rerun PM or copy user history. The one install receipt
is provenance of this output, not a task database or an admission authority.

The future install order is complete source preparation; native PM
`install --tools-only`; `install --extra all --extra telegram --extra web --extra exa`;
native selected Python; existing Node dependency preparation and TUI/Dashboard
builders/freshness; installation-local `ensure_install_launchers`; truthful
external install stamp containing upstream base and overlays; private trusted
Friday plugin; native atomic additive configuration and actual SOUL; existing
Harness source/toolchain/build/smoke; A0 source inventory. OS account HOME stays
unchanged. Ambient credentials, PYTHONPATH, profile/runtime and host-lock
overrides are stripped. No global launcher or user PATH is published. The
original finite invocation budget bounds all commands via the existing preparer
process-group runner; it is not reset between phases.

Harness writes a new `home/harness` donor checkout and retains its intact native
source/build machinery. It never builds over the frozen donor. A0 inventory is
read-only source preparation, not image provision, daemon start or kernel
acceptance. Its existing fixed deployment remains explicit in `a0_runtime.py`;
this entry does not substitute a portable deployment, retry G3, invent a useful
web contract or change the stopped kernel grant.

Generated gateway and Dashboard argv are the actual native parsers:
`hermes -p default gateway install --no-start-now --no-start-on-login`, then
`gateway start` and `dashboard --host … --port … --no-open`. They are plans only:
none is invoked in this candidate. No `--force`, `--replace`, `--all`, isolated
lock partition, upstream install.sh or update is used. Native gateway units,
token locks and host-wide Dashboard rendezvous remain the intended owners.

The native profile consumer verifies real auth engagement, the explicit Basic
operator, mandatory Exa and absent cloud fallback. Before future native build,
existing live host records with foreign home/profile/authority or uncertain
process incarnation refuse installation. Matching records are policy inputs,
not proof of HTTP/auth/source ownership. The Dashboard overlay below closes
the native pre-bind/attach boundary at source level. This task does not verify
a gateway unit, read live credentials, validate channel account/token ownership
or admit workers. A receipt marked READY cannot bypass
the entry's startup refusal.

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
