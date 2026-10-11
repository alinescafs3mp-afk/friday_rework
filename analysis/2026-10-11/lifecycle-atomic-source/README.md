# Atomic lifecycle writes and read-only peer checks: source analysis

An inherited 2 MiB file-size limit exposed an unchecked short write in the lifecycle registry writer: the original implementation renamed a truncated temporary JSON file. A nominal read-only peer check also rewrote the registry.

The source candidate checks the inherited file limit before writing, completes partial writes, checks temporary file length, preserves the original file on pre-rename failures, and reports failures after rename honestly. Event appends check the total file length and complete writes. Peer checks take the existing lock and work on a copy without creating or rewriting the registry. Default writer behavior remains covered.

The author recorded 27 source controls. Independent review accepted 38 groups, 25 transitions using the exact existing pure core, and five isolated kernel controls with a real 2 MiB limit. These kernel controls used inert fixture files and owned helper processes. They did not execute native admission or the installed guard. SOURCE-REVIEW.json and AUTHOR-CONTROLS.json retain the control outcomes without private identities.

source/original_functions.py and source/candidate_functions.py contain exact function bodies and decorators extracted from the full files. The explicit header leaves namespace dependencies unbound. SOURCE-PROVENANCE.json records original byte slices and whole-source hashes; its historical whole_original_sha256 field under candidate identifies the whole candidate. atomic-write-readonly-peer.patch preserves the exact source delta. The full files contain private profile and routing bindings and are withheld. The excerpts are analysis materials, not an executable installed guard.

The actual global guard remains unchanged. The required full 19-test native compatibility gate is NOT_RUN. No runtime qualification, installed journey, ordinary full gate, or release acceptance follows from these source results.

Publication preparation generation 1 stopped after six immutable files because it selected a missing license source. Its original 240-second clock and late final failure receipt remain in private evidence without success credit. Generation 2 reuses those six exact files and the previously verified public MIT license; it has a separate finite preparation scope and clock. No functional control was rerun or credited to the preparation.

Final publication removes terminal empty lines from the two excerpts. All sixteen function/decorator slices remain exact and their ASTs unchanged. The archived source patch retains nine blank context lines byte for byte; those literal patch lines are a documented whitespace-check exception. The final publication snapshot receives independent delta review; prior acceptance is not silently transferred to new bytes.
