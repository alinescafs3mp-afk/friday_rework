# Pinned Harness preparation

The complete donor stays at `.donors/dsh`, detached at the commit and tree in `sources.lock.json`. Preparation does not transplant or edit its kernel, Cordis plugins, vendored sources or notices. `scripts/dsh_prepare.py` refuses a different commit/tree/origin, an attached branch, symlinked checkout, dirty tracked source/index, extra untracked source, or an unexpected donor-root `.env*` file even when ignored by Git. It checks each tracked blob, file type and Git executable mode against HEAD and compares the complete index; `assume-unchanged` cannot hide changed bytes. Upstream's declared CRLF checkout for Windows command scripts is verified against the canonical blob and recorded explicitly. No external clean filter runs. Existing ignored build output is retained.

Run from the assigned Friday_rework checkout, using Python 3.10 or newer:

```sh
python3 scripts/dsh_prepare.py source --donor .donors/dsh --evidence .evidence/frw002-sol
python3 scripts/dsh_prepare.py toolchain --donor .donors/dsh --evidence .evidence/frw002-sol
python3 scripts/dsh_prepare.py build --donor .donors/dsh --evidence .evidence/frw002-sol
python3 scripts/dsh_prepare.py smoke --donor .donors/dsh --evidence .evidence/frw002-sol
python3 scripts/dsh_prepare.py check --donor .donors/dsh --evidence .evidence/frw002-sol
python3 -B -m unittest discover -s tests -p 'test_*_prepare.py'
```

Only `source` creates/fetches a missing donor. An existing incomplete or mismatched directory is preserved and refused. `check` does not download dependencies. `toolchain` obtains the exact upstream `packageManager` through the existing Corepack into donor-local `.git/friday-corepack`; no global pnpm install or Corepack shim change occurs. `build` runs the upstream frozen-lockfile install and complete `pnpm run build`, keeping its declared dependency build policy. Dependency/cache/log outputs remain inside the owned donor/evidence areas. Each command has a finite timeout; timeouts fail and terminate the owned command process group, preserving logs and source. These preparation timeouts do not implement a production worker deadline.

The pinned upstream declares Node `^22.19.0 || >=24.0.0` and pnpm `11.7.0`. Building its native host addon also needs `cc` and the running Node installation's `include/node/node_api.h`. No system packages or inference services are installed. The child environment excludes model and Telegram keys, uses an explicit private smoke home, and sets `DSH_TELEMETRY_DISABLED=1`.

Evidence records source/tree, source-lock and dependency-lock hashes, notice hashes, actual toolchain, command exit/log identities and built CLI. The workspace build inventory hashes emitted workspace `lib` files and the native `.node` addon; the frozen dependency lock identifies the installed dependency selection. This is a source-backed build identity, not a standalone redistributed executable or an independent full supply-chain attestation. `LICENSE` and `THIRD_PARTY_NOTICES.md` remain in the intact donor.

`smoke` checks the native CLI version, launcher help, the composed default headless profile, and native `--profile headless --help` startup. The headless command publishes no task on its help path, so no agent/session/model run starts. It does not configure Friday's local provider, run a coding task, prove tool calls, cancel a job, or deliver an artifact. Those remain separate current-assignment checks. The observed legacy endpoints and context 40960 are a temporary test profile, not production defaults or architecture limits.

## Next headless adapter

The preparer's clean environment supplies the fixed
`NODE_OPTIONS=--disable-wasm-trap-handler` and discards ambient `NODE_OPTIONS`.
This supported [Node option](https://nodejs.org/download/release/v22.23.2/docs/api/cli.html#--disable-wasm-trap-handler)
uses inline WebAssembly bounds checks instead of the large virtual memory cage.
It keeps memory checking, existing limits, exact package-manager/lockfile pins
and TLS verification. It does not grant a retry, reset an installation deadline,
or establish that a complete build has succeeded.

Use an argument array, a task-owned isolated repository cwd, and stdin bytes:

```text
node <donor>/apps/cli/lib/bin.js --profile headless --patch <absolute-verified-local-patch.yml> --json -
```

Hermes owns one process per existing job. Set a private persistent `DSH_HOME` for that job, disable telemetry, keep stdout NDJSON separate from stderr, and pass only the explicit local provider credential. The native configuration patch must select an observed local model through `llm-pi-ai`, disable the independent DeepSeek model/account/search routes and unnecessary goal/workflow rows, and use actual declared capacities. No cloud fallback is admitted. This preparation does not install that adapter or render a production patch.

The opening `session` object carries `sessionId` and `cwd`. Progress includes `status`, `text`, `thinking`, `tool_call` and `tool_result`; status phases include `turn_start`, `step_start`, `step_end` and `turn_end`. Require exit 0 plus a completed final turn reason; a `final` text object alone is insufficient. Preserve bounded raw output and native task state; never send thinking to Telegram. Continue the same admitted task only with its recorded home, workspace and `--session-id`; an unknown ID is refused by the donor. Stop/deadline belongs to the existing whole-job supervisor and requires descendant quiescence. The Python SDK is an existing alternative, but its RPC timeout is not a job deadline and it has no per-session cancel method at this pin.

Authoritative source inspection: `Friday_rework_Astra_Sol_Directive_V2_2026-10-06/integration/DSH_CODING_EN.md`. Actual outcomes and remaining prerequisites belong in `.evidence/frw002-sol/manifest.json`; preparation does not establish product acceptance.
