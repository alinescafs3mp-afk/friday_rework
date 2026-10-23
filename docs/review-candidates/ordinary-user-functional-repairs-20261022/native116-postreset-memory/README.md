# Source116: actual post-reset memory recall and origin integrity

On 2026-10-23 the installed Source116 service answered a new key-only question about an existing durable-memory record in a genuinely new, initially empty native conversation. The request contained a fresh correlation nonce and the record's key, with no answer value or hint. Root compared the received normal text and the persisted native assistant answer to the private oracle without exporting the oracle or raw conversation.

The single new request completed its full 180-second capture and terminal drain. Actual observation closed at 08:03:39 Moscow time, 186.015 seconds after its original 300-second admission. The native transcript and persisted counter both changed from zero to three rows: one user, one assistant and one session metadata row. The same new conversation, parent lineage, durable creation origin and route origin remained intact. The permanent owned service stayed healthy.

This exercises the installed fix for the [preserved Source114 origin regression](../native114-runtime-reset-memory/README.md): the subsequent ordinary request no longer writes the previous conversation's origin over the new conversation's creation metadata. The oracle match establishes this scoped post-reset recall; it does not establish the general memory matrix or the exact memory payload in the provider prompt, which was not retained.

The preceding official reset used one `/new` and one confirmation. Its actual new empty conversation and parent closure were independently reconciled from native state, but the confirmation's receive observation stopped on a transport alarm before completing its own full window. That old run remains STOPPED with incomplete capture. It was neither replayed nor promoted to full-window acceptance. The new memory question was a distinct operation with its own finite clock.

The existing tester's receiver label remains `NEW_NONCE_CONTRACT_UNBOUND_UNGRADED`. Root separately verified that the retained raw Telegram reply targets the exact request ACK in the same tester account. Contextual attribution also joined the raw peer/private chat, fresh nonce, answer-free request bytes in the native user row, and the persisted assistant response. Receiver records were not rewritten to claim attribution or semantic acceptance.

Two narrow local verification corrections were checked before the new request. The confirmed reset with incomplete receive capture could authorize only this exact new key-only task, retaining the shared tester's original global UNKNOWN, quarantine, credential, cursor and physical once-only protections. The native completion ledger's existing 24-hour retention was authenticated: its previous 63 entries became 59 after six expired and two reset-command completions arrived. During the memory query, four more expired and one completion arrived, leaving 56. This retention applies to that bounded service ledger. All 93 preceding tester runs were preserved; verification did not prune user history. No ledger repair, clock reset or old-effect replay was performed.

Source presence, actual installation, healthy runtime, this scoped user result and full release acceptance remain separate facts. Both-worker runtime, shared-room live acceptance, the full matrix and overall product readiness remain open.

- [Machine-readable facts and limits](facts.json)
- [Actual Source116 installation and permanent service](../native116-install-runtime/README.md)

Private operational inputs, account/session/process identifiers, raw conversation and the memory oracle are excluded.
