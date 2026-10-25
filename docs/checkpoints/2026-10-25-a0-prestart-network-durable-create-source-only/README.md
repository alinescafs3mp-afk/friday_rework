# A0 pre-start network and durable create identity — source checkpoint

Docker can return an exact newly created container whose selected network is still pending. The previous checker required an allocated network ID before starting the container, and it wrote the native receipt only after that check. A failure could therefore retain a created container while cleanup lacked its durable receipt.

The two-file source patch adds an explicit never-started inspection phase, persists the actual create identity before fallible callbacks/inspection, records submission intent before native start, and reconciles retained observations during cleanup. Running/allocated network identity, owner, image, mounts, transport restrictions and stopped-object custody remain checked. The legacy accepted stop-source edge is preserved.

This is an exact source delta against the hashes in `MANIFEST.json`, archived for analysis. It is not applied to the repository's runnable source by this commit. Independent source review and targeted offline controls completed; several controls simulate native/container effects. Their counts do not represent product acceptance scenarios.

At this checkpoint the repair is not installed. Its registered-source/declaration/private-consumer integration is in progress. A real qualification reached container creation before the original refusal; that container never started and remains retained while exact cleanup compatibility is repaired. Gateway and Dashboard remain running. The requested ordinary Telegram coding and engineering file tasks, returned artifacts and contextual continuations remain incomplete. No product-ready claim is made.

Unchanged accepted installation and stage observations are retained. Failed attempts, their original clocks and uncertain effects are not replayed. Private operational snapshots, credentials, native routing details, task oracles and user data are excluded.
