# A0 REST candidate

This is an unregistered source candidate for FRW-011. Hermes owns admission,
original task/budget, execution outside its gateway loop, goal checks and delivery.
The complete A0 stays inside one dedicated Docker environment under the existing
NativeSupervisor. Nothing in these modules launches or admits a worker.

The adapter establishes an actual context with one blocking
`POST /api/api_message`, retaining environment/invocation/request intent first.
Bootstrap is local **model work**, including attachment writes, and consumes the
original independently enforced job deadline. It records the returned context
before verifying inputs and sending exactly one effectful task message. The
controller's existing one-way preparation reservation prevents unknown bootstrap
replay. An ambiguous task response is also retained and never resubmitted.

The HTTP helper runs inside the exact container with loopback port 5000. It reads
the effective `settings.get_settings()['mcp_server_token']` after native dotenv
initialization and passes `X-API-KEY`; neither this token nor inference keys enter
argv, payloads, receipts or transport errors. Redirects, environment proxies and
automatic POST retries are disabled. Known runtime secrets are redacted from
response text; file transfer rejects files containing those secrets.

`GET /api/api_log_get` provides factual counts/GUID/activity, without streaming
thinking. `progress_active=false` cannot complete a task. Only the awaited task
response plus complete checked artifact retention completes the adapter call;
goal verification and delivery remain `NOT_RUN`. Missing/foreign log contexts
require reconciliation. No chat-delete or A2A cancel endpoint implements stop.

Host-verified inputs use `input_path(row, index, suffix)`, unique to the task and
its original admission, under `/a0/usr/uploads`. Attachments are followed by
exact-path native no-follow snapshots and `/api/api_files_get` byte/hash checks
before dependent work. Expected output paths are trusted `ExpectedFile` values:
`/a0/usr/workdir/<job_prefix>/<job_prefix>-<unique-basename>`. Arbitrary paths,
duplicate basenames, symlinks/hardlinks/FIFOs, missing or partial/extra maps,
noncanonical base64, size overflow and mutations during retrieval are rejected.
The existing `stage_file`/`read_staged` retain checked immutable bytes outside
the worker; delivery retries can consume them without re-executing A0.

On normal completion this first candidate stops the dedicated environment after
retaining outputs. On error/cancel/pause/deadline it stops conservatively and
preserves context/workspace/intents. Docker exit/PID0, exact invocation/unit
quiescence, empty original container cgroup and sampled PID/start cessation are
required. Resource drift does not block an identified owned stop. Cleanup never
stops the inference server, Docker daemon, Hermes or an unrelated worker. A
repeated cleanup observes cessation without issuing another stop. Warm sequential
reuse remains **NOT_RUN**, requiring separate actual acceptance.

## Host integration boundary

Use `A0Controller(associations, {'a0': WorkerBinding(adapter,
adapter.emergency_stop), ...})` with the same existing Associations/PluginState
and preparation journal. Its A0 overrides correct the shared Controller's
assumption that preparation is harmless: cancellation must stop an active
bootstrap even before a context exists. Every checked start/reconcile failure,
including an unreadable preparation journal, changed brief/input declaration or
lost UNKNOWN-write acknowledgement, attempts the existing exact native stop.
One last checked association stays in memory solely for stop if the next state
read fails for that same task/principal. A new process needs its owner's verified
association/native receipt; it cannot invent ownership from an unreadable store.
Shared Controller, DSH adapter, host and registration are unchanged. Wiring
this candidate into the actual host belongs to Astra.

`A0Deployment` supplies pinned Docker/daemon paths, unix socket, immutable image,
private state dir, authenticated read-only Git stage, intact reviewed startup
command and explicit local network inputs. `NativeGrant` comes from the **actual
current** native launch receipt: container/name, worker/daemon invocations,
labels, original association wall/monotonic times, original cgroup, current boot and pre-start
key transaction timestamp. The host validates source/image/Git provenance and
sole ownership before constructing it. Its labels' task/admission hash and unit
must match the authoritative association. No model-supplied descriptor qualifies.

`LocalNetwork()` defaults to `none` and refuses model admission. A proposed named
bridge must carry pinned, independently reviewed deny-by-default egress evidence
for only the owner's two local HTTP endpoints on ports 8001/8002. Docker network
selection alone supplies **no egress restriction**. `network_verified=True` is a
trusted current owner's native verification result, never a readiness file,
automatic admission or permission derived from the policy file's presence.
Host networking, exposed ports, Docker-socket mounts, privilege, SSH and cloud
routes are excluded. The currently accepted `network=none` runtime cannot execute
this candidate's model path, and the e882 diagnostic launcher rejects a named
network. Do not monkeypatch it or reuse its old plan. Its owner's separately
reviewed portable launch change is a concrete prerequisite to the next runtime.

`local_profile(network)` produces the actual A0 plugin preset collection, with
`Default`, agent0/no-project, local dispatcher chat/utility and qwen3 embedding,
and SSH disabled. This matches the accepted e882 templates for the current URLs.
40960 input/4096 output are temporary TEST capacities, **not** a hard total prompt
bound or full-capacity evidence. A project override is refused in this candidate.
Container native/kernel caps remain 2CPU/2GiB/swap0/256PID; daemon caps remain
8CPU/20GiB/2048tasks. Unit RuntimeMax plus stop grace must fit the ORIGINAL
association deadline; a lost gateway must not keep the container alive.

Before UI starts, `prepare_keys(new_usr, existing_reference_resolver)` atomically
adds only absent `API_KEY_OPENAI` / `API_KEY_OTHER` to its owned 0600 `usr/.env`.
References are `FRIDAY_LLM_API_KEY` / `FRIDAY_EMBEDDINGS_API_KEY`. Existing auth,
runtime identity and generated state are preserved. Keys never enter Docker Env
or secret hashes. Keep the returned KeyMaterial only in private memory; after
confirmed cessation its cleanup removes exactly the introduced unchanged fields.
Unique key binding uses the same `python-dotenv` parser as the intact donor,
including quoted/export/valueless assignments. Duplicate, changed, partial or
malformed binding refuses reads/effects and cleanup without deleting foreign
state. Cleanup is idempotent only when both introduced names are absent.
The native API helper receives the original admitted values through private
stdin, checks the actual bounded/no-follow `.env` before initialization/request
and after response, and redacts those original values after JSON decoding.
Keys never enter command arguments, request bodies, receipts or evidence.
A new process must reconstruct it from the private scoped source and current
receipt under its existing owner, without copying/swapping logins or budgets.
Same-boot monotonic evidence must show this transaction preceded UI startup.
Post-start probe key readiness does not establish UI-process readiness.

## Offline checks and finite next proof

Run the candidate tests in the existing installed Hermes Python, with its source
on PYTHONPATH, `FRW_A0_DONOR` selecting the pinned intact donor and
`FRW_A0_ACCEPTED_MODULE` selecting the unchanged e882 helper:

```sh
python -B -m unittest discover -s tests -p test_a0_adapter.py -v
```

Tests execute the unchanged pinned A0 handler class methods with an in-memory
agent and real isolated files, real PluginState/Controller, generated HTTP script
with an intercepted opener, and produced config against the accepted schema
consumer. Native API/model/container/kernel/gateway-down effects are NOT_RUN.
Mocks exercise identity/cap/deadline refusal; they do not establish live caps.

The repair controls are in `tests/test_a0_adapter_recovery.py`; run both A0 test
files and the unchanged `tests/test_controller.py` for the relevant offline gate.
Worker-visible selected input is checked again after the native identity callback
and before the dependent task POST. Missing/replaced/mutable input stops without
uploading over uncertain state or repeating bootstrap. This verifies a bounded
handoff snapshot, not an immutable upload lease against later worker writes.
Recovery validates the exact expected artifact set/order, unique references and
logical names, preparation/task origin, completeness, metadata and retained bytes
before reporting completion. Corrupt old manifests require reconciliation;
there is no automatic migration or replay.

The exact original independent 71-test harness is retained privately. Its one
duplicate-key redaction scenario calls `ready()` outside an `assertRaises`; the
fixed guard now refuses there before its old response assertion. Its literal run
records that error rather than being reported green. The new corresponding
control preserves the original secret-absence assertion and explicitly checks
early refusal, no mocked HTTP call, unchanged cleanup state, legitimate redaction
through the actual donor loader, escaped JSON secrets and mid-call mutation.

The result's private `runtime_recipe.py` is a one-shot PREPARED command:

```sh
python -B runtime_recipe.py --input CURRENT_OWNER_INPUT --sha256 INPUT_SHA256
```

Its input must be published by Astra after source review and a separate current
bounded live grant. It references the existing exclusive lock, exact committed
candidate/source pins, actual existing Hermes state/association and native
deployment/grant; no secret values. Astra must first close these prerequisites:

The earlier a267 candidate's private recipe and live inputs remain immutable;
their source pins are obsolete for this repair. The current owner must review
and pin the repaired commit before preparing any separately admitted execution.

1. Review the complete package and wire the A0 Controller binding under the same
   host owner; verify source/image/donor and complete Git stage provenance.
2. Prepare one **new** finite owned association/runtime with its original budget,
   daemon/outer/container caps, independent RuntimeMax/ExecStopPost exact ID and
   fresh sole-owner/current boot observations. Hold the existing exclusive slot.
3. Admit and actually verify the two local routes' restrictive policy, no cloud
   fallback, startup preset and UI key visibility from the pre-start transaction.
4. Execute one harmless context initialization followed by one controlled
   engineering failure/diagnosis/repair/check, including a verified input and
   expected unique output. Verify retained bytes and the actual goal outside A0.
5. Confirm dedicated environment cessation and key removal; perform separately
   assigned child-stop and gateway-down deadline controls. Delivery and warm
   next-job/context reuse require their own real acceptance and do not follow
   from this finite call's response.

The recipe does not create a task/service/network, reset an old budget, install,
retry, register, release or push anything. It always yields a factual adapter
observation with goal/delivery NOT_RUN, not self-certified product readiness.
