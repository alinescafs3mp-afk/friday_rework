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
```

These controls use synthetic dictionaries and standalone standard-library
imports. They do not initialize native configuration or contact services.

The native control suite simulates authority/serialization boundaries explicitly.
The publication suite extracts the genuine existing descriptor-held file
publication and rollback primitives and runs them only on its own temporary
files. Neither suite claims a real native grant or production transaction.
