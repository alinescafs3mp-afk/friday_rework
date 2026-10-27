# Public web service source compatibility

The public web repair changes `scripts/a0_runtime.py` and
`plugins/friday_rework/adapters/a0_web.py`. The declaration module now recognizes
that exact two-file transition in its five-file public service inventory.
The launcher, profile adapter and service unit must retain their public hashes.
These hashes describe source bytes; they do not identify a running service.

The predecessor is the public source at commit
`9b3ff222898cbe1b1cb12d4a338c4aadbdfadf53`; the target is the web/runtime repair
at `b01b83ba8055bfd7c5d15d0d8c06f0c5b537fb6c`. The runtime differs from the
operational guarded-memory runtime, so their source hashes and inventories
must not be substituted. No historical transitions or embedding changes are
introduced by this port.

A second exact public edge keeps that first target as its predecessor and uses
`PUBLIC_A0_WEB_HTTP_CONFIG_GIT_EXACT`. It advances only the web adapter to
`b16fb6681372223c4c6c04e6e7021eb53993cea56136bfe28419ac566976d5b6`
and the public runtime to
`943b399247db9636dbf6aaf96f79ae988852f4366f3f7ef3893e77433425d11a`.
The first edge remains valid; skipping it, mixing tuples or substituting an
operational runtime is refused. The declaration planner, stopped operator and
mirror writer select the same exact edge and preserve the existing transaction.

This repair writes a single-directory `safe.directory` entry to `/etc/gitconfig`
only inside a newly owned container. It checks the source file, parents, tracked
source pins and version module, and refuses an existing target. HTTP diagnostics
retain `http_config` for connection failures and distinguish `http_status`,
`http_body_bound`, `http_json`, `http_version` and `http_engines` without exporting
response content. A known limitation remains: `urllib` raises `HTTPError` before
a response is returned, so that failure still reports `http_config`/`OSError`,
including HTTP 503. The HTTP status code is not retained; a synthetic returned
non-200 response is different from a raised `HTTPError`. This is accepted bounded
technical debt. This port preserves the reviewed web bytes and does not change
that behavior. This source package does not establish an installed result.

`service_source_transition` checks the complete service maps. The project-edge
helpers distinguish unchanged predecessor, pending transition and unchanged
target. Reverse, partial and mixed transitions fail. `service_publication_sources`
joins both existing staged mirrors to the expected home-relative paths and
hashes; other mirrors must remain unchanged. These functions perform no I/O.

For a source proposal, `SERVICE_SCHEMA` is
`friday.worker-web-service-source-declaration.v1`. The normal
`plan_declaration_delta` and `validate_declaration_source` entries accept it
through the same identity, current binding, generation and raw-reference joins.
The proposal changes exactly the template's worker inputs. Only the runtime
source hash changes there; the public launcher hash, both workers, source scope,
deployment, budgets, policy, endpoints and all other inputs are retained.
Both current root declarations, the profile declaration and the proposed
deployment must agree. The returned configuration is a copy, not a write.

The proposal reports `native_apply_implemented: true`, but still reports
`native_authority: false`, `ready: false` and `workers_enabled: false`.
The existing `rebind-worker-declarations` phase now implements this specific
maintenance edge with its existing `friday.worker-declarations.apply.v1` request.
The exact service bundle selects it; there is no caller-supplied bypass flag.

Install the reviewed canonical project first, in a separate supported source
installation. Both `previous_input` and `current_input` must describe that same
installed target tuple, including the complete five-member target source map;
the references may be identical. This writer refuses to install canonical or
native source code. The two existing `worker-runtime-source/` files must still
have the exact public predecessor hashes. A consumed transaction remains
consumed; neither new reference paths nor a new clock permit retrying it.

The request retains the existing fields and must include the original five
configuration/profile/marker beforeimages plus exactly those two mirror
beforeimages. Mirrors must be existing owned, unlinked regular files with mode
0400 or 0600; their modes are preserved. Canonical target donors are immutable
external pins. The original raw request, finite boot/monotonic clock, current
binding/generation, grant, native source/build/PM, runtime, inference and stopped
consumer locks remain required. The writer stages native resealed afterimages,
backs up all seven targets, publishes the two source mirrors first and the
native marker last, then validates the native consumers before commit. A
pre-commit failure uses the existing owned-inode rollback of the whole affected
set. Uncertain commit, ownership, rollback or release requires reconciliation;
there is no automatic retry, worker preparation or service start.

The original deployment transaction retains its five-file path and refusals.
This is an executable source implementation, tested in neutral fixtures, not a
production installation or native-authority acceptance. Tests do not establish
service health, worker execution, Telegram delivery or semantic acceptance.

Run the focused source controls from the repository root:

```sh
python3 -I -B tests/test_worker_service_source.py
python3 -I -B tests/test_worker_service_native.py
python3 -I -B tests/test_worker_service_publication.py
python3 -B -m unittest discover -s tests -p 'test_worker_service_http.py'
python3 -B -m unittest discover -s tests -p 'test_a0_web*.py'
```

These controls use synthetic dictionaries and standalone standard-library
imports. They do not initialize native configuration or contact services.

The native control suite simulates authority/serialization boundaries explicitly.
The publication suite extracts the genuine existing descriptor-held file
publication and rollback primitives and runs them only on its own temporary
files. Neither suite claims a real native grant or production transaction.

## Operational observations, 27 October 2026

The operational six-file deployment is separate from the public five-file
source map above. Its installed input is
`3ca27f16dcb13840eb869bf29c5bc1c240bd170a81075526283807e1681e0142`.
The source installation completed, followed by a committed native update to
runtime `4111e677a103b93ef3d898757e67cea7dad1da68c34d542689707286b802cdd9`
and web adapter `b16fb6681372223c4c6c04e6e7021eb53993cea56136bfe28419ac566976d5b6`.
The native update took 647.801 seconds; its six physical files and committed
receipt were checked after the process exited and was reaped.

The following prepared-worker configuration update was refused after 414.873
seconds by `ordinary_a0_source_successor_publication_inventory_changed`.
The historical receipt reader included the web file for the earlier web-probe
transition but omitted it from the expected inventory for the HTTP transition.
This refusal occurred before the derivative transaction was created. The nine
input pins, complete 31-entry worker tree, installed native files and marker
were checked unchanged. The completed source and native installations remain
accepted; only the missing configuration stage requires correction.

These are separate phase durations, not a combined service-start measurement.
At that checkpoint, Gateway and Dashboard were stopped for the maintenance
boundary. Worker qualification and the new DSH/A0 Telegram file tasks had not
run; no product or end-to-end readiness was claimed by those installation results.

## Accepted historical-reader source correction

The [sanitized HTTP history inventory patch and source evidence](review-candidates/http-history-inventory-20261027/README.md)
correct that exact omission and check the complete publication inventory before
walking authenticated ancestry. The full-map publication validator and the
other 38 guard predicates are preserved. This accepted source-only delta targets
an omitted private historical reader; it is analysis material, not an installed
public runtime. At export preparation, the R475 configuration derivative was in
progress and not yet accepted; worker qualification and the new Telegram file
tasks remained unperformed. The original operational observations above remain
unchanged.

## Subsequent installed state

The corrected configuration-derivative operation completed in 499.220 seconds
and its committed files were verified. Gateway and Dashboard were restored
under their existing permanent management. HTTPS returned 200 and the native
signed ownership check passed; interactive operator login was not tested.

The next qualification attempt ended after 493.332 seconds, before an A0
instance was started. Its first-worker segment reached a configuration check
about 1.295 seconds after allocation. The prepared native-input manifest still
had seven entries and lacked `web/gitconfig`, which the installed web adapter
requires. Direct evaluation by the installed deployment-contract consumer
reproduced that mismatch; the other seven entries matched. The rootless daemon
was inactive and no new A0 bootstrap, probe plan or runtime receipt existed.

At that checkpoint, the accepted source, native mirrors and configuration
derivative remained in place, with the permanent services running. The missing
manifest entry and its digest reference still required repair; the failed
attempt and its saved DSH safety observation were retained.

The subsequent R476 repair committed exactly two files: the A0 native-input
manifest gained `web/gitconfig`, and `runtime-input.json` gained the updated
manifest digest reference. The accepted source, native installation and
configuration-derivative receipts were preserved without reinstallation.

Preparation before apply took 1,266.545 seconds, including 70.094 seconds of
staging preparation. Authenticated apply took 7.770 seconds. A separate fresh
process running the installed deployment-contract consumer accepted the repaired
inputs in 4.719 seconds. Both processes exited 0 and were reaped; these apply
and observation durations are separate from preparation.

The failed qualification's two files were archived byte-for-byte, and its DSH
safety observation was kept for reuse without rerunning it. Gateway, Dashboard and Kimi
kept the same permanent processes. At repair acceptance, no new worker
qualification had completed and neither new Telegram file task had been sent.
Worker qualification, both user tasks and the broader acceptance scope remain
open.

The following R477 qualification attempt ended after 8.438 seconds, before
worker startup. Its historical inventory reader still followed an old
preparation's manifest reference to the repaired current file and rejected the
changed digest. The installed repair remains accepted. The remaining correction
is an exact retained-file mapping for that historical reader; no installation
or worker action needs to be repeated to correct it.

## Accepted nested-manifest reader correction

The [redacted S411 historical native-input reader delta](review-candidates/historical-native-input-20261027/README.md)
adds one exact original-path-and-digest mapping to the accepted retained
beforeimage; the current manifest remains separately checked. Independent review
recorded 12 positive and 9 negative cached preparation checks with bounded IO and
`private_check` seams, not a full live inventory pass. This private-adapter export
is source-only analysis material, not a public runtime installer.

R476 remains installed and accepted by a fresh installed consumer. At this
checkpoint, R478 qualification is running and has not been accepted; neither new
DSH/A0 Telegram file task has succeeded. The R477 failure is preserved above.


## R478 native execution observation

R478 passed the former historical-input refusal and started the A0 worker stage.
Preparation before that stage took 497.770 seconds. The native container process
was started, then its systemd manager recorded exit status 1 about two seconds
later. The subsequent container inspection refused `container_network_changed`;
the worker stage ended after 13.432 seconds.

The recorded cleanup and a separate current-resource check confirmed that the
container was stopped and retired, its network was absent, introduced keys were
removed, and the permanent services were unchanged. Stopped daemon execution
metadata still requires its existing exact retirement procedure before another
admission. The original attempt and clocks remain preserved.

The underlying container exit cause is undetermined: this runtime mode sent
stdout and stderr to null, and the failed raw inspection was not retained before
retirement. The next scoped diagnostic change must preserve that evidence.
Neither Telegram file task has been sent; the installed R476 repair and accepted
S411 historical-reader correction remain in place.

The subsequent bounded maintenance completed in 5.721 seconds: the two stopped
execution-state files and twelve directories were archived and retired, then the
existing registered stopped-launcher consumer passed. The daemon state directory
remains empty, persistent Docker data was preserved, and gateway, Dashboard and
Kimi kept their original processes. This closes the failed attempt's resource
cleanup; it does not qualify either worker or explain the startup exit.

The [reviewed startup diagnostic delta](review-candidates/a0-startup-diagnostics-20261027/README.md)
captures selected failure state and bounded private startup output in the next
scoped probe. Its runtime and source-binding checks passed, including an isolated
real systemd output-limit check. No subsequent A0 startup or Telegram task has
yet been accepted. The installed runtime bytes remain unchanged.

Before R479, the closed R478 qualification records, bootstrap records and probe
plan were moved together into the protected archive. The real archive consumer
accepted their preserved identities and contents. A prelaunch source-permission
refusal was corrected within the same original maintenance clock; no native
archive action had started at that point. Native archival then completed in
4.175 seconds, within the total 52.631-second phase. Those intervals overlap and
must not be added. R479 uses the final diagnostic revision and has started its
necessary source-validation stage; qualification and both Telegram results remain
unaccepted.

R479 then failed after 511.954 seconds, including 498.319 seconds of source
validation before the worker stage. This time the diagnostic captured the owned
container's exit code 1, `OOMKilled=false`, and the startup exception
`native_web_overlay_refused` at the Git installer's parent-directory guard.
The pinned image ships `/etc` as `0775`; the unchanged guard rejects its group
write bit. The [narrow parent-mode patch](review-candidates/a0-web-parent-mode-20261027/README.md)
is reviewed source only and still needs coherent installation.

R479's container, network and introduced keys were reconciled, and its stopped
daemon execution metadata was archived and retired in a separate 5.726-second
maintenance operation. Permanent gateway, Dashboard and Kimi processes were
preserved. Both Telegram file tasks remain unexecuted.
