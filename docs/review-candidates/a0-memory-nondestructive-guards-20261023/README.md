# A0 memory nondestructive failure guards — source only

This checkpoint preserves the accepted S202C1 cumulative patch for memory-store loading. It removes a path that could silently rebuild an empty store after a missing or invalid FAISS hash. The source is reviewed and ready for integration preparation; it is **not installed**, and this checkpoint establishes no native FAISS/API, reindex, migration or semantic-recall result.

A nonempty store must have four ordinary, nonlinked companion files, a valid `index.faiss` hash, and valid UTF-8 embedding metadata with a provider and model name. Absent paths and genuinely empty directories remain fresh stores. Incomplete, orphaned, linked or hash-invalid stores fail explicitly while retaining the original files. Loaded vector count, mapping positions/IDs and complete docstore must agree before reuse or model-change rebuild.

The unchanged 6,399-byte [memory.patch](memory.patch) targets the relative upstream path `plugins/_memory/helpers/memory.py`. The complete source module is not published or installed here. SHA-256 source identities:

- Before: `25daaf04cd781629bf1acfb25c1936d5a40e6364731d6c77d3048d87d164a1a2` (26,601 bytes).
- After: `dcd46c2b896a20ac2dc3e18f82168f09845e54b8982fbdb06ecbb6d7e2fb049a` (28,559 bytes).
- Patch: `1ffaf363fdf449ad530dc79d5b7aaff900b0b6463d7d64eb7a428879446c83ff`.

## Existing observations

One previously completed isolated run executed 54 exact AST-extracted helper cases: 40 filesystem guard cases (35 refusals and 5 fresh/healthy acceptances), 3 direct hash-helper cases and 11 loaded-bundle cases. All passed within that scope. All 43 filesystem guard/hash before-and-after records were identical; all 11 loaded-bundle inputs were retained. The process exited 0, was reaped, and its synthetic temporary trees were cleaned. These cases were **not rerun** to prepare this publication.

Independent affected-source review reported 0 open high and 0 open medium findings. Guard ordering, healthy same-model reuse and the original docs/IDs on model change have source/AST evidence. Only built-in rebuild-argument expressions were evaluated on plain data; full healthy native initialization and rebuild were not executed.

[OBSERVATIONS.json](OBSERVATIONS.json) records the exact scope, counts, pins and limitations. Full proof remains private. [SHA256SUMS](SHA256SUMS) covers the three public payload files.

## Remaining integration limits

- `allow_dangerous_deserialization=True` remains. The FAISS hash authenticates neither the pickle nor embedding metadata; trusted coherent store provenance is still required. Arbitrary hash-valid binary/pickle corruption was not executed and is not detected by this preflight.
- Target embedding-cache lineage and provider/name-only namespacing remain unresolved here, including same-name backend, dimension or kwargs changes.
- Ancestor symlink custody, ownership/permissions and concurrent replacement/TOCTOU require integration checks. This patch refuses the root and required companion symlink leaves only.
- Save/hash/embedding metadata writes remain non-atomic; this patch does not repair or verify write-failure recovery or rollback.
- No actual FAISS load/rebuild/save/reload, embedding API, installed behavior, reindex or semantic recall is accepted by this checkpoint.
