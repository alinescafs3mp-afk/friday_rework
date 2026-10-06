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
A0_TEST_TMP_ROOT=/home/jericho/jericho/Friday_rework/.donors/a0/.git \
  python3 -B -m unittest discover -s tests -p test_a0_prepare.py -v
```

The controls use real synthetic Git repositories in temporary donor Git-metadata
subdirectories and remove them afterwards. They do not modify any tracked donor
source. They prove clean repeat/check does not rewrite the index; wrong commit,
tree and origin refuse; changed tracked bytes (including assume-unchanged), staged
changes, missing files, mode changes, untracked source and a competing writer
refuse. They are preparation checks; they do not certify A0 runtime behavior.
