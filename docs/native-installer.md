# Native Friday installation candidate

`scripts/friday_install.py {plan,install,check,start} --input <private JSON>`
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
not proof of HTTP/auth/source ownership. This does not solve the final native
Dashboard attach race, verify a gateway unit, load credentials, validate channel
account/token ownership or admit workers. A receipt marked READY cannot bypass
the entry's startup refusal.

Remaining integration requirements are concrete: portable A0 image/toolchain
preparation or separately admitted exact fixed deployment; useful web for A0 and
both workers in the normal compiler; final same-home/source/auth Dashboard owner
enforcement; protected launch credentials and scoped pool/channel ownership;
native gateway exact-home unit installation/readiness; final PM/build realization
and independent acceptance of all six mandatory web/admin journeys. Ordinary
SAFE-tool and text-only capacity compatibility limitations remain as documented
in the normal profile. None is removed by this source candidate.
