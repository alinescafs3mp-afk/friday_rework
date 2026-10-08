# Pinned Agent Zero source preparation

This FRW-002 command prepares the full donor at
`Friday_rework/.donors/a0`. It preserves the kernel, plugins, browser/container
distribution and all tracked notices. It never imports or starts A0, installs
dependencies, starts Docker/services, or contacts a model or Telegram.

The project source lock selects upstream `agent0ai/agent-zero`, commit
`e3051fb584b1a36be2b0a0c90606f1c2c2d356ec`, tree
`f7bfedfa472b9d1bc28a88caf8be08d17daf8813`. The observed source-lock SHA-256 is
`e6b5c58308cce8b63a4d67bcf4960292579f40e718f0e445e7443f648cc0f3d1`.

From the project checkout or assigned Sol worktree:

```sh
python3 -B scripts/a0_prepare.py prepare
python3 -B scripts/a0_prepare.py check
```

`prepare` fetches only the exact commit into an absent donor, verifies the fetched
commit/tree before detached checkout, and checks the full result. An existing
directory receives the same read-only verification as `check`; it is never reset,
cleaned or updated. A failed initial fetch leaves its directory for diagnosis;
rerunning refuses an incomplete identity rather than silently repairing it.
Public fetch has a 180-second limit; other Git operations have finite limits.
The helper disables optional Git index locks, hooks and global/system Git config.

The commands check origin, HEAD/tree, source index and every tracked file's raw
Git blob hash, type and executable mode. This catches changed files even when an
index flag hides them from ordinary status. Extra non-ignored source files,
symlinked source directories, incomplete source and competing Git lockfiles cause
exit 2. CLI JSON includes notices, requirements/lock declarations, Docker sources
and actual host toolchain observations. `--lock` and `--checkout` permit explicit
offline fixture checks; they do not weaken verification against that lock.

For an initial private report, add
`--output .evidence/frw002-sol/a0.json`. Output files are created exclusively with
mode 0600; a pre-existing report is refused. Evidence and donors are already
ignored by the project. A repeated check can print a fresh report to stdout
without modifying the existing report or donor.

## Actual supported runtime prerequisites

The pinned [installation guide](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/docs/setup/installation.md)
describes a Docker container. Its
[development guide](https://github.com/agent0ai/agent-zero/blob/e3051fb584b1a36be2b0a0c90606f1c2c2d356ec/docs/setup/dev-setup.md) also requires Docker
for the hybrid host development route; a host Python import alone does not supply
the engineering environment. The development guide's native local-source build
uses `docker build -f DockerfileLocal -t agent-zero-local .` from the donor root.
This is a later execution step, **NOT_RUN** in this preparation package.

`DockerfileLocal` defaults to `BRANCH=local` and copies the complete source into
`/git/agent-zero`; `docker/run/fs/ins/install_A0.sh` retains these local files for
that branch and installs `requirements.txt`. The base image installer creates
Python **3.12.4** at `/opt/pyenv/versions/3.12.4` with `/opt/venv-a0`, alongside
system Python **3.13**. These are source declarations, not installed observations.
The host's Python **3.14.4** was used only for this standard-library preparation
command, with Git **2.53.0**.

Docker CLI is absent from the current PATH. No daemon, socket, existing worker or
remote execution backend was probed or started. A dedicated compatible container
environment and its native supervisor/stop boundary remain prerequisites for
FRW-006. Build scripts perform package installs and preload; runtime initialization
starts supervised services. They were inspected as source only.

The pinned source does **not** supply a complete root Python resolved lock:
`requirements.txt` mixes exact pins and ranges. Its SHA-256 is
`54eda564fceecd51f486861685ccd069bfd300da5e03d5edd25046c73bc5ee28`.
The WhatsApp bridge has a separate `package-lock.json`; it does not lock the A0
Python runtime. DockerfileLocal and the run Dockerfile reference
`agent0ai/agent-zero-base:latest`; the base Dockerfile uses
`kalilinux/kali-rolling`. These mutable references do not establish a reproducible
image. The eventual build needs recorded immutable image digests and the actual
resolved runtime dependencies. No image digest or built-runtime identity is
claimed here.

All **3,081** tracked source files passed the byte/mode/index check. The root MIT
`LICENSE` is preserved (blob `50b7754de5cde0fbb796ffae376fb03dc19236d1`, SHA-256
`23844ed5fb9976b15e6c0be1b617918cb1c32e13e8d70b74100dae08d40fbf23`), together
with the three plugin LICENSE files and every other tracked file. The private
manifest lists their identities. Startup, model/plugin routing, API credentials,
REST integration, cancellation and product acceptance remain **NOT_RUN**.

## Verification controls

```sh
A0_TEST_TMP_ROOT=.donors/a0/.git \
  python3 -B -m unittest discover -s tests -p test_a0_prepare.py -v
```

The controls use real synthetic Git repositories in temporary donor Git-metadata
subdirectories and remove them afterwards. They do not modify any tracked donor
source. They prove clean repeat/check does not rewrite the index; wrong commit,
tree and origin refuse; changed tracked bytes (including assume-unchanged), staged
changes, missing files, mode changes, untracked source and a competing writer
refuse. They are preparation checks; they do not certify A0 runtime behavior.

## Dedicated service in the ordinary installer

The tracked `scripts/friday-rework-docker.service` ships the existing dedicated
Docker unit with `RuntimeMaxSec=120s`, start/stop limits of 45s/20s, and the
unchanged 20GiB/8CPU/2048-task, delegation and whole-cgroup kill controls.
`rootless_docker_launch.py` pins these exact unit bytes and checks its own current native invocation, PID/cgroup, finite effective deadlines and resource/kill controls before delegation writes or daemon exec. A changed or infinite cached unit refuses even if the on-disk template SHA matches. The normal installer
requires both files in its reviewed `project_files`, checks the template and its
launcher pin together, and stages the unit alongside the complete runtime and
profile/web helpers in `<product-home>/worker-runtime-source`.

For an explicitly enabled A0 runtime, `friday_native.complete` then calls the
existing A0 preparer with the *same* original installation budget, inside the
existing finite installation namespace. It holds the existing A0 `runtime.lock`;
there is no second service, manager, owner store or clock. The runtime config
must point to its staged runtime source, the fixed dedicated launcher and unit,
and their exact new source hashes. The deployment must be explicit and equal to
the product deployment. The present narrow route supports only its declared
legacy local endpoint pair, which remains temporary test profile data. Other
valid configurable profiles refuse with `a0_service_deployment_route_unsupported`
before effects; they are not silently rewritten. A job budget shorter than 215s
cannot contain this 120+45+20+5s boundary and the existing 25s cleanup reserve.
The unchanged route consumer must still verify actual remaining original job time
and effective native limits before publishing a request. Planning is no proof of
native enforcement or production readiness.

`friday_install plan` exposes `a0_service_effect_plan`. Registration is absent-only:
active/failed/foreign/previously loaded units, old source/registration files,
requests, guards, retained RootlessKit state, changed config/script bytes or an
unreconciled prior installation intent refuse. The preparer neither overwrites
nor adopts them. In particular, the currently retained old deployment needs
separate owner reconciliation; this source package grants no migration or replay
of old installer/G5 attempts.

An eligible fresh registration publishes exact private launcher/unit files,
uses supported `systemctl --user --no-reload link <owned-unit>`, and explicitly
performs one `systemctl --user daemon-reload`. This reload affects the whole user
manager. It does not enable the service, start a daemon, publish a route request,
read credentials or run A0. Commands and cleanup consume the original remaining
install budget; bounded stdout/stderr observations remain in the install's
`preparation` directory. Intent is durable before each effect. Lost link/reload
acknowledgement, late budget exhaustion or source/native readback drift retain
`STOP_UNCONFIRMED_REGISTRATION_REQUIRES_RECONCILIATION`; no automatic rollback,
repeat link/reload, service restart or broad kill follows. The retained intent
blocks a second call. The final receipt binds the original claim and exact source
inventory, and requires a loaded, inactive service with the expected effective
finite native limits. Later install completion/check verifies staged and registered
source bytes and the receipt; it does not interpret a historical inactive receipt
as current runtime health.

Offline controls use real files, exclusive publication, locks, SHA consumers,
original budget and receipt checking, with explicit fake native manager replies.
Actual registration/reload, supported OS property behavior, gateway-down stop,
container/network cleanup, warm reuse, credentials and all seven installed
journeys/four web contexts require independent native qualification. The existing
startup-health A0 refusal remains in place.
