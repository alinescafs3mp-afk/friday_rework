# DSH input paths and web-module visibility

A live coding task received five verified input files, but its prompt contained only host-facing filenames. The worker spent tool calls discovering the opaque paths under `/job-input/verified`. The source candidate now appends a deterministic inventory of worker paths, sizes and hashes. File content, host paths and ingress receipts are excluded. Preparation and its consumer verify the same rendered brief. Existing prepared tasks are not rewritten.

The same live task reported that the keyless web module failed to import. The renderer names `/payload/friday-web-keyless.mjs`, while the sandbox exposed its payload only at the original absolute path. A conditional read-only alias exposes the already pinned module at the required path. Other web profiles and existing mounts are unchanged.

The combined source passed 55 focused adapter/web tests. The real module loader reproduced `ERR_MODULE_NOT_FOUND` before the alias and loaded/registered the provider after it in a read-only, network-denied diagnostic. That is import validation, not live web-retrieval acceptance.

This block is published source and is not installed. The running coding task retains its original source, inputs and clock. Its user artifact remains under evaluation; this checkpoint does not claim complete DSH, web or product readiness.
