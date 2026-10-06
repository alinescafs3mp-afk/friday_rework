# Temporary local test profile

The current legacy inference route and its context limit are temporary test conditions imposed by available hardware. They are neither product defaults nor permanent architectural limits. A future model or server needs an explicit new profile and renewed checks of the affected behavior.

`tools/configure_local_test.py` renders a profile using Hermes' native configuration writer. Run it with the isolated, PM-owned Hermes interpreter. Supply the observed local URL, exact served model ID, credential environment-variable name, real context and input ceilings, and explicit output/overhead reservations. The tool has no default capacities or server address. It does not serialize a credential value or change the model server.

The output home must be private and beneath this workspace's ignored `.runtime` directory. Replacing an existing configuration requires its expected SHA-256 and preserves an independent private backup. An unsafe backup or a changed configuration stops replacement.

The main route and configured auxiliary routes are pinned to the same local provider. The remaining native auxiliary tasks inherit that main route; their actual resolver behavior was checked without network calls. Automatic fallback routes are empty, and the failure path rejects provider discovery. The initial text component profile disables memory, automatic review/title generation, external skills, MCP and tools. These are scoped test settings; they do not define the final product's enabled features.

The `bounded_context` extension is an opt-in compatibility change under implementation and review. The unmodified pinned Hermes rejects contexts below its native minimum. Successfully writing or loading this profile does not establish agent admission or model compatibility. Output limits must reach the native agent and compression requests; an unrecognized YAML key is not evidence of that behavior.

Until the server's exact tokenizer and chat template are available, conservative request accounting is explicitly an estimate. Real local requests, pressure-triggered native compression, post-compression continuity, output reservations and failure paths must be checked before accepting the profile. No fake larger context or automatic cloud fallback is permitted.

No new Telegram consumer is started by this tool. Old Friday continues to own its existing production consumer.
