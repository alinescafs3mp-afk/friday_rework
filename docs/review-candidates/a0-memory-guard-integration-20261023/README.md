# A0 memory guard integration — source only

S204 connects the already accepted [S202C1 memory guard](../a0-memory-nondestructive-guards-20261023/README.md) to the existing A0 service-source route. This is an accepted source integration checkpoint, **not installed**. It establishes no running service, native FAISS result, embedding API result, dimension-2560 result, migration, recalculation, reindex or semantic recall. The full product goal remains open.

The four patches below retain the accepted canonical source deltas against the reviewed Source117 C3 base. Runtime and planner patch bytes are reused exactly; receiver and history patch context is reduced to omit unchanged private profile identifiers. All four still reproduce their exact accepted after hashes. The complete 309-file map retains 305 source hashes and changes exactly these four files. This S204 branch is independent of the later Root C2/Source118 and ordinary DOCX work; this checkpoint does not claim they are merged or make memory integration a DOCX prerequisite.

| Canonical source | Patch |
| --- | --- |
| `scripts/a0_runtime.py` | [runtime patch](scripts--a0_runtime.py.patch) |
| `plugins/friday_rework/worker_declarations.py` | [planner patch](plugins--friday_rework--worker_declarations.py.patch) |
| `scripts/friday_worker_declarations.py` | [receiver patch](scripts--friday_worker_declarations.py.patch) |
| `scripts/friday_ordinary_a0_registration.py` | [history reader patch](scripts--friday_ordinary_a0_registration.py.patch) |

The runtime carries the exact accepted 28,559-byte guard as data in its existing pinned source entry. The existing `SERVICE_FILES` inventory still has five files; no sixth service file, new installer, framework, hook or controller is added. Existing prepare/staging/plan consumers carry the runtime, which materializes an owned source overlay and binding through the existing mounted `usr` tree.

For both UI and web startup, the runtime inserts a bounded standard-library check after the image source copy and before either native consumer starts. It targets the fixed native import `plugins._memory.helpers.memory` at `plugins/_memory/helpers/memory.py`. Exact original bytes are replaced with the exact guard; exact guard bytes are reused. Unknown target bytes, altered payload/binding, symlinks, hardlinks or invalid ownership/type/size/hash fail before startup. The plan binds the fixed source tuple and reconstructs it during validation. This is the reviewed source behavior, not an observation of a real image or mounted tree.

The planner, receiver and history reader add the exact runtime-only S204 transition while retaining the historical S189 edge and the existing five-file route. The unchanged launcher and other service-source pins remain required. Source-maintenance history permits the single top S204 extension only with its required S189 predecessor and preserves the earlier effective history depths. A future integration must bind current source/CAS/history, authority, image and store/cache facts afresh; no previous registration or maintenance effect is replayed here.

The cumulative guard change remains visible in the prior [memory.patch](../a0-memory-nondestructive-guards-20261023/memory.patch). The runtime patch includes the complete 28,559-byte memory module encoded as base64 for transport; the earlier public memory patch contains its delta only. No separate full-module file or private service-port source is published. To inspect the embedded source without importing or running it, run from this directory:

```python
import ast, base64, hashlib
from pathlib import Path

patch = Path("scripts--a0_runtime.py.patch").read_text()
line = next(s for s in patch.splitlines()
            if s.startswith("+MEMORY_OVERLAY_BASE64 = "))
source = base64.b64decode(ast.literal_eval(line.split(" = ", 1)[1]), validate=True)
assert hashlib.sha256(source).hexdigest() == (
    "dcd46c2b896a20ac2dc3e18f82168f09845e54b8982fbdb06ecbb6d7e2fb049a")
print(source.decode("utf-8"), end="")
```

The source review reported zero open high or medium findings within its affected source scope. The earlier 54 S202C1 helper observations are reused unchanged, not rerun. S204 added 40 focused passing source cases: actual extracted helpers, generated startup code on synthetic source trees, transition/input/history guard slices and source links. Full native imports and authenticated archived-receipt transactions were not executed. Preparing this publication only verified pins, exact existing patches, the cumulative four-patch roundtrip, JSON/checksums and privacy; it did not rerun source tests or a full gate.

[OBSERVATIONS.json](OBSERVATIONS.json) records source pins, observations and remaining limits. [SHA256SUMS](SHA256SUMS) covers the six public payload files. Private operational adapters, configuration, grants, raw receipts and handoff evidence are omitted.

Per-store provenance and unknown target-cache lineage remain integration dependencies. Same-name backend/dimension/kwargs drift and provider/name-only cache namespacing are unchanged. The FAISS hash authenticates neither pickle nor metadata, and hash-valid native corruption is outside preflight coverage. Memory save/hash/metadata writes remain non-atomic with no rollback or write-failure acceptance. Source acceptance does not settle these limits or replace installed, runtime and semantic acceptance.
