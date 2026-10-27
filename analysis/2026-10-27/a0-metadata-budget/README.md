# A0 metadata budget checks

Read-only constructor validation was rereading and copying the complete
association store for every Git metadata callback. The observed scan had 6,430
callbacks over 3,081 paths. It now uses one checked row during the constructor,
keeps cancellation and original deadline checks on each callback, and checks
current durable ownership/stop state again before any native route effect.
Subsequent runtime operations retain their original full-store checks.

The canonical method delta matches the reviewed installed variant. Validation
covered ten negative controls and five producer-boundary cases, including
cancellation, stop, owner changes, and deadline changes during construction.
An isolated copy of the actual metadata tree took 0.121 CPU seconds and 0.390
wall seconds for the scan; these figures exclude the two surrounding store
reads. No complete before/after end-to-end timing is claimed.

The installed variant and its four configuration links were updated. Permanent
gateway and Dashboard services were restored and verified. A subsequent fresh
worker check found a separate historical qualification source-pin dependency;
its compatibility correction is in progress. No successful Telegram worker
artifact or full-product acceptance is claimed by this checkpoint.
