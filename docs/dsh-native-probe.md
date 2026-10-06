# Offline native Harness probe

`scripts/dsh_native_probe.mjs` inspects the pinned, already-built donor without editing or rebuilding it. Use Node 22.23.2 and a rendered local Cordis overlay. All paths are explicit; `--home` must be an empty disposable directory with an existing canonical parent. A new home is created mode700; an existing home must already be owned and mode700. The report parent must be owned, private and canonical. The report is created exclusively mode600: existing files, symlinks and hardlinks are preserved. Use a new report destination and disposable home for each run.

```sh
node scripts/dsh_native_probe.mjs \
  --donor /absolute/read-only/dsh \
  --patch /absolute/rendered-local.patch.yml \
  --home /absolute/disposable/probe-home \
  --report /absolute/private/native-probe-report.json
```

The source pin must be `5badb15009ae1756c3afe0ae0cef1faafc290ccc`. The probe removes inherited environment entries before importing donor modules, does not load `.env`, supplies `DSH_HOME` and `DSH_TELEMETRY_DISABLED=1`, blocks external process creation and common Node network entry points, and exits within 45 seconds. It rejects inserted plugins, executable overlay expressions, inline API keys, serialized endpoint credentials, active auxiliary cloud/account/title/search/goal paths, and multiple provider/model routes. Provide a private report location: route metadata, paths and source hashes appear there. Credential reference names may appear; secret values are never needed.

The probe uses native `prepareProfile`, `readProfilePatches` and `composeEntries`, including the final telemetry opt-out patch, to inspect effective rows. It then calls the built CLI's `runProfile` and native Loader/startup audit over the complete base profile. An inspection overlay holds only `headless-startup` and `headless-runner` so no task is submitted. The report records native entry state, the registered provider, resolved model metadata and built/source hashes.

Main selection executes `installModelSelection`, isolated native prompt assembly and the native `agent/request` waterfall with the effective deployment default and a native disposable Session. Child checks execute `resolveChildAgentOptions`, which the native in-process spawn/fork driver calls: inherited routes follow the latest durable request even when creation options differ; explicit child route overrides remain possible. Configuring one provider does not disable this selection API. The probe also verifies that an alternate unregistered route fails at native model resolution without discovery or fallback.

The actual mounted `BasicCompactionEngine.summarize` resolves its target and emits native `GenerateOptions` to an observer that throws before adapter streaming. No model completion is fabricated. `compactIfNeeded` additionally runs in a private Context with the registered native LLM/model metadata and controlled token measurements immediately below and at the policy threshold. The pruning branch demonstrates the native output-reservation/headroom calculation at that exact boundary; an oversized durable request reservation must fail through the native policy resolver. This does not measure real token-count accuracy or produce a checkpoint.

Source references and SHA256 values are recorded in the report. The method is anchored in `apps/cli/src/profile-boot.ts`, `packages/boot/app-boot/src/profile-context.ts`, `packages/core/agent/src/model-selection.ts`, `packages/subagent/subagent/src/child-agent.ts`, and `packages/compaction/compaction-basic/src/{index,config,summarizer}.ts`. Cordis replaces complete row `config` objects: the renderer must retain all required fields. Small contexts also need explicit compaction output and headroom values; upstream defaults reserve 65536 tokens.

A PASS establishes effective native composition, held-app base startup and executed route/pressure component selection. It does not establish successful headless task execution, spawned-child operation, endpoint credentials, request compatibility, long-context summary quality, persisted compaction, tools, cancellation, or production isolation. Real CLI refusal controls and live deployment acceptance are separate checks. The network guard is a probe guard, not a general security boundary.
