# Explicit local CLI onboarding source candidate

This candidate connects the normal product renderer and existing administrative
onboarding to the frozen native CLI principal helper. It has selected-source
controls, not installed or live acceptance. Rendering a local account, preparing
a profile or passing a source checker grants no ordinary product access.

The optional product specification field is separate from receiving accounts:

```json
{
  "accounts": [],
  "cli_accounts": [{"transport_profile": "default", "account_id": "local-console"}]
}
```

All other normal specification fields remain required. Receiving accounts may
coexist with this declaration. Omitting `cli_accounts` retains the previous
renderer output exactly. A local account becomes a generic native
`product_access.accounts` identity with `platform=cli`. It never passes through
`gateway.config.Platform`, adds a receiving listener, receives channel credential
references, registers an adapter or produces a messaging profile route. CLI in
`accounts` continues to refuse. No OS UID or principal is inferred by rendering.

Use the existing protected `POST /onboarding/prepare` API with its original
operator Session, current root configuration SHA, installation template and
explicit `platform`, `transport_profile`, `account_id`, `user_id` and
`runtime_profile`. For CLI only, add `uid` as a nonnegative strict JSON integer.
Missing, boolean, string, duplicate and ambiguous UID assignments refuse. A
messaging preparation refuses a supplied UID. `user_id` is the product identity;
it need not be the decimal UID, a login name or a channel/chat identity.

The transaction persists a disabled native PluginState user first. It retains
one exact `{uid, transport_profile, account_id, user_id}` row in the existing
`cli_admission={enabled:true, principals:[...]}` configuration. Existing users,
profiles and UID mappings cannot be adopted. The same binding/account/profile
joins remain authoritative. The protected onboarding receipt additionally pins
that exact row's fingerprint. CLI preparation leaves messaging routes unchanged.
Partial setup stays disabled and requires reconciliation; it is not replayed.

The current frozen helper resolves authorization from the native default root.
Accordingly this candidate supports `transport_profile=default` and preparation
in that actual root only. Named gateway authorization roots refuse. Native
private-file checks require the running process UID to own the authorization and
ordinary home files; preparation therefore also requires the submitted UID to
equal the kernel's real/effective process UID. One numeric UID can identify only
one CLI principal. Different OS user provisioning, shared ownership, ACL/chown
workflows and alternative authorization roots need a separately reviewed
contract. No such system changes or isolation proof are supplied here.

Credential capture, template/persona checks, private new home creation, worker
preparation/qualification, root configuration CAS and native access generations
retain their original paths. CLI local authority rechecks the exact kernel UID,
configuration mapping, account and profile. It uses no PairingStore grant or
messaging identity. The original native home consumer checks the CLI receipt,
scoped required keys, map fingerprint and product account membership, and refuses
any CLI messaging route. Telegram retains its exact route and pairing check.

`POST /onboarding/activate` remains the explicit product-enable operation.
Normal `friday-local` profiles still require both qualified own-profile workers
and scoped keys. Incomplete credentials or workers leave them disabled and
without a capability marker. Administrative disable or role change uses the
existing native PluginState generation transition; a retained CLI capability
cannot revive on re-enable. The frozen helper remains the actual retained-cap
entry and consumer and is unchanged by this package.

Selected-source positive activation uses an explicitly disabled-worker legacy
installation template to check only the local authority/home/generation join.
It is not a normal-product worker readiness result. All normal CLI worker
execution, provider authentication, full native imports, real admin browser/API,
installation and independent final acceptance remain required.

The existing `friday_work`/`friday_result` IngressAdmissions/Host/receipt ownership
consumer still requires its separately reviewed CLI ingress join. This package
creates no work/result receipt, task/history engine, chat, bot, update or message
identity. The TUI principal transfer is a separate candidate. SAFE tools,
process admission, original budgets, stop/cleanup and release gates are unchanged.
