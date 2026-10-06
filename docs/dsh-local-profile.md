# Temporary local Harness profile

This package configures the intact, already built Harness at source
`5badb15009ae1756c3afe0ae0cef1faafc290ccc`. It does not implement a coding-job
adapter. The profile is a native Cordis patch applied after the headless bundle.
The renderer requires an explicit purpose, API, local endpoint, observed model
ID, context, output cap, summary cap and compaction headroom. There is no default
endpoint/model/context. A later larger server needs new explicit inputs.

Use an owned directory with mode `0700`. For example, with deployment values
supplied by the caller:

```sh
python -B tools/render_dsh_local.py \
  --purpose temporary-local-test --api openai-completions \
  --base-url "$FRW_TEST_BASE_URL" --model "$FRW_TEST_MODEL" \
  --context-window "$FRW_TEST_CONTEXT" --max-tokens "$FRW_TEST_OUTPUT" \
  --summary-max-tokens "$FRW_TEST_SUMMARY_OUTPUT" \
  --headroom-tokens "$FRW_TEST_HEADROOM" \
  --api-key-env FRIDAY_LLM_API_KEY \
  --output "$FRW_PRIVATE_DIR/local.patch.yml"
```

`--api-key-env` is only a reference. Omit it for an intentionally unauthenticated
endpoint; the renderer never reads a key. Output is JSON, which is a valid YAML
patch list accepted by the native launcher. Files are published atomically with
mode `0600`; an existing file, symlink or hardlink destination is refused and
preserved. Errors do not repeat argv values. Repeated flags are refused.

The admitted route uses an explicit private/loopback IP, explicit port and `/v1`
path, without embedded credentials, query/fragment, substitutions or DNS
discovery. `openai-completions` is Harness's native spelling for the audited
Chat Completions transport. The profile declares one `friday-local` provider,
one text model and an explicit per-request output cap. It disables the ten
independent cloud/account/search/title/goal/workflow rows from the audited
template. Cordis replaces a row's entire config object; the provider dictionary
is replaced as a unit, not merged with catalog routes.

Compaction uses explicit `summarizationProvider`, `summarizationModel`,
`maxTokens` and `headroomTokens`. Its upstream default headroom is 65,536 tokens,
which does not fit the current small temporary test window. The renderer admits
only a positive summary cap no larger than the model output cap and headroom
that leaves input space. Admission also requires the native retained-tail budget
to stay strictly below the pressure threshold, including at integer boundaries.
It retains native threshold/retention/retry behavior.
This is donor configuration, not Hermes's `bounded_context` schema.

The current private profile records the separately observed temporary server
route/model/context and the explicit test reservations. Rendering does not
establish compatibility or measured capacity. Request timeout defaults to 30s
and can be supplied explicitly with `--request-timeout-ms`; it is a provider
request bound, not a complete coding-job deadline. Native retry remains intact.
The existing outer job owner must enforce the complete job deadline and stop.

Run finite component checks against the accepted CLI without rebuilding it:

```sh
python -B -m unittest discover -s tests -p test_dsh_local_profile.py
python -B scripts/check_dsh_local.py \
  --node "$FRW_VERIFIED_NODE" --donor "$FRW_DSH_DONOR" \
  --evidence "$FRW_PRIVATE_DIR/cli-checks"
```

The second command mounts the real native headless profile in disposable private
homes, with no inherited model/cloud/Telegram credentials. It tests effective
config dump, native startup, a real local HTTP model refusal, missing credential,
invalid native patch and delayed-request timeout. Its test-only Node socket
guard allows the one loopback fixture endpoint and refuses other TCP routes;
an explicit public-address denial control verifies the guard before the CLI
cases. It records destinations, request model/output cap, terminal reason,
exit code, separate raw stdout/stderr and owned process cleanup. A native final
event can accompany an error and is not treated as success. The guard is not a
new product transport or an inference implementation.

See `dsh-native-probe.md` for native main/child/compaction route inspection.
Component fixtures establish configuration and failure behavior. They do not
establish real model responses/tool calling, long-context compaction quality,
coding-job success, cancellation/restart, Telegram delivery or product/live
acceptance. Astra owns those integration and acceptance lanes.

Source references: `apps/cli/src/dump-config.ts`,
`packages/bundle/base/cordis.patch.yml`, `packages/llm/llm-pi-ai/src/config.ts`,
`packages/compaction/compaction-basic/src/config.ts`,
`packages/bundle/headless/src/runner-internals.ts` at the pinned donor commit;
audited `integration/DSH_CODING_EN.md` and `config/dsh-local.patch.template.yml`.
