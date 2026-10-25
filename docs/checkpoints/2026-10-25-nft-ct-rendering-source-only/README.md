# Strict nft 1.1.6 rendering compatibility — source only

This checkpoint publishes the exact `checked_policy` delta in `scripts/rootless_docker_launch.py`. It handles nft 1.1.6 rendering of the established/new connection-state pair as equality to an anonymous set, and restores protocol guards implied by typed IPv4 and TCP/UDP payload expressions before the existing complete-policy comparison.

The equality exception requires exactly the two distinct allowed states in an anonymous set. Scalar/list equality, extra or duplicate states, different operators and extra connection-state fields remain rejected. Explicit protocol guards are retained in their original order, including wrong guards that must fail the final policy comparison. The policy renderer and every launcher byte outside `checked_policy` are unchanged.

Independent source controls accepted the final parser against the saved real nft 1.1.6 capture; the old parser rejected that capture. Existing endpoint variants, omitted-guard combinations and meaningful invalid-policy controls were reused from the accepted review. They were not rerun for this publication. The source patch was applied and reversed in a temporary inert copy, reproducing the exact whole-file hashes in `MANIFEST.json`; that copy was removed.

The original isolated capture completed its authenticated protocol and cleanup, then reported `policy_ct_operator_changed` with the old parser. It used simulated native authority and started no Docker daemon or model. The earlier executable-identity experiment used two phase labels without applying nft policy; its isolated identity/protocol observation remains valid. Neither observation is expanded into installed product acceptance. The saved capture establishes the rendering incompatibility; it does not establish the complete cause of the earlier opaque HTTP 503.

This is a source-only checkpoint. No new kernel run, product installation, dockerd/runtime qualification, Telegram worker artifact or same-chat continuation is claimed here. The complete accepted multi-file installation package, private history-consumer joins and deployment bindings are separate; this one-function patch does not publicly reproduce them.

To inspect or apply, first verify the exact baseline SHA-256 in `MANIFEST.json`, then use `patch --batch --fuzz=0 -p1 --input nft-ct-rendering-compatibility.patch` from the source root. The zero-context patch contains only the actual changed parser lines and normal source paths, omitting unchanged deployment settings. It executes no code by itself.
