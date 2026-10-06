# Friday persona provenance

`config/SOUL.md` adapts the actual Friday identity and dialogue guidance from `friday/agent_runtime/__init__.py`, beginning with `SYSTEM_PROMPT` and `MODE_GUIDANCE`, in the owner's frozen source snapshot:

- Commit: `cecd28a92ac4fd4e34c4d3813d0c598debe09436`
- Source blob: `cd46049b1976d490fb610304e41abdaaa076406e`

It retains Friday / Пятница / Jericho identity aliases, Russian by default, bounded initiative, natural dialogue, evidence-based claims and readable Markdown. Legacy claims about archive, graph and tool capabilities are omitted until those capabilities exist in the new composition. No developer identity, private history or invented personal background is included.

The identity is loaded through the native Hermes `SOUL.md` mechanism. An isolated native loader check read the adapted identity successfully. That is component evidence; model behavior and end-to-end persona acceptance remain untested.

The inherited notice is retained in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
