# Worker controller integration

`controller.Controller` connects the existing `Associations` store to an
explicitly admitted `WorkerBinding`. It owns no queue, scheduler, workspace
allocator or background process. The gateway must invoke blocking adapter
methods through its existing execution boundary, outside its event loop.

The trusted host first matches native ingress and call correlation, acquires
the existing workspace ownership, stages verified inputs, and claims the
original association and budget. `prepare` records a reservation and the
adapter's preparation references in the same Hermes PluginState, using the
association lock. A one-way `preparation_reserved` marker in the authoritative
association is committed first. Losing auxiliary preparation metadata cannot
turn an old reservation into a new prepare. A failed or interrupted preparation remains unresolved;
calling it again cannot silently create another context or launch work.

`start` requires those exact preparation/input/brief identities and commits
UNKNOWN before effectful submission. It records actual native observations
through the adapter callback. A repeated start reconciles the original
attempt. It does not replenish the budget or submit again. Missing native
identity remains unknown and still reloads current stop/budget state; adapters must never substitute a preparation path
for an observed worker session.

`stop` resolves the authenticated control principal against the original
bot, user, chat, topic and profile. It persists cancel/pause before native
control; cancellation cannot be replaced by pause. Retained intent and the
original deadline or consumed budget take priority during reconciliation.
These methods do not implement instruction-pointer resume or authorize a new
generation for paused work.

Every admitted binding supplies an independently verified emergency stop
which needs only the last checked association and actual invocation, even
when state or auxiliary receipts become unreadable. For Harness this is the
existing native systemd supervisor. A0 must stop its dedicated execution
boundary; stopping an HTTP caller alone is insufficient. The original
exception is retained with confirmed or unconfirmed stop evidence. A failed
intent write still fails the operation; cleanup does not imply durable
cancellation or permission to transfer workspace ownership.

The current component tests use real isolated PluginState persistence with
deterministic adapter/supervisor doubles. They cover reopen, duplicate and
uncertain submission, write failures, late cancellation, foreign controls,
deadline accounting and identity changes. Worker completion never marks goal
verification or delivery complete.

This controller is not yet wired into the registered tool. Gateway task
dispatch, full recovery of an interrupted preparation, native worker/control
integration, output verification and Telegram delivery need their remaining
implementation and actual runtime checks. Admission remains closed until
that integration is ready. These tests do not constitute product acceptance.

The reservation field is mandatory for newly claimed rows. Earlier development
rows without it fail closed and need explicit reconciliation before execution;
there is no automatic migration that could erase a prior preparation, intent
or budget. Historical probe receipts remain unchanged.
