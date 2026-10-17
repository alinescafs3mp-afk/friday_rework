# Ordinary Office intake: source candidate

The ordinary `read_file` path selects an immutable byte snapshot from the current
principal's private workspace. DOCX keeps its existing native body extractor.
PDF, RTF, ODT, XLSX, ODS, PPTX and ODP use the installed maintained anydoc byte
API with an explicit format and `ocr='reject'`. The converter receives bytes,
never the document's filesystem path. Current capability and access generation
checks bracket extraction and response creation. Extracted text does not grant
coverage for overwriting a binary document.

This path extracts text/Markdown. It does not establish image, layout, formula
recalculation, rich editing, rendering, export or round-trip preservation. There
is no ordinary archive reader in this change. Missing or unsupported local
conversion returns a typed capability failure without installation, hosted OCR,
network, shell or model fallback.

The input bound is 1,000,000 bytes. ODF/XLSX/PPTX ZIP envelopes allow at most 256
members, 1,000,000 actual decompressed bytes per member and 8,000,000 total,
with a 200:1 expansion bound. Duplicate, encrypted, linked, unsafe-path or
unsupported-compression members are rejected. Actual raw deflate streams are
bounded through EOF and checked against their size and CRC, including directory
entries. Expected package parts/ODF MIME and native format detection must agree.

The byte converter runs in an isolated Python child with a five-second wall
deadline, three-second CPU limit, 1 GiB address-space limit and bounded output.
It imports the selected local package before installing a mandatory Linux
libseccomp filter with TSYNC. Conversion cannot open files, use sockets or create
separate processes. A narrowly filtered pthread clone supports the single Rayon
helper used by PDF extraction; new threads inherit the filter. Cleanup kills and
waits for the owned child on timeout or cancellation. Missing containment fails
closed. The JSON envelope has a 6.1 MB limit; decoded text has a 1 MB limit.

For `write_file(format='text')`, the scoped path now applies native binary and
opaque-document extension predicates, including SQLite sidecars, plus Office/ODF
templates and add-ins. These names cannot receive a UTF-8 text creation or
revision. Legitimate text/code/CSV/TSV remain text operations. Explicit native
DOCX creation remains create-only; rich same-format editing is not added.

This directory is a review-only SOURCE export. The patch remains outside
`patches/hermes`, so it is not added to the installer inventory or composition.
The currently installed Source90 is unchanged by this export. `backend_cases.py`
and `scope_cases.py` preserve their original bytes but use review filenames that
do not match default pytest discovery. They are not automatically wired into the
canonical test suite. The scope cases still require the repository's
`tests/file_native_fixture.py` and the corresponding pinned native source/deps;
these documents do not ship an installed converter or a standalone test runtime.
The six files under `fixtures/core_office` remain alongside the backend cases at
the exact relative lookup path used by those cases.

The current genuine affected real DEV SOURCE gate passed 82/82 focused cases and
254/254 coherent cases with zero errors, skips or dropped cases, on the exact
final `tests/test_user_isolation.py` SHA recorded in `SOURCE-STATUS.json`. This is
the same original 254-case selection. Four exact locked dependency wheels were
staged in an isolated development dependency directory: ruamel.yaml, requests,
urllib3 and snowballstemmer. No existing host environment was installed into or
modified. The interpreter was Python 3.14.4; this evidence does not qualify the
target Python 3.14.7 native interpreter or SDK.

The correction changes public localized-refusal expectations and performs genuine
native gateway startup before synthetic principal fixtures. The helper checks
the exact raw refusal payload, including rejection of duplicate/extra keys;
12 separate negative helper controls and a cold-bootstrap refusal control are
recorded outside the 254 pytest cases. Internal model_tools refusal markers and
all principal, privacy, generation, revocation and foreign-file guards remain.
No candidate product guard was weakened: all three candidate product-source
files and 2,664 predecessor source/vendor/original dependency files remained
unchanged. The sole Git integrator handles the final test bytes separately in
`tests/test_user_isolation.py`; these review files do not install that correction.

The initial zero-collection/dependency failures and the earlier real gate with
229 PASS and 25 FAIL remain historical failures. Those 25 failures also reproduced
on original Source90. The new green result belongs only to the new pinned
execution. It is not a full project, runtime, product/model, user-journey or
release pass. Replacing the historical ruamel.yaml blocker with current SOURCE
evidence does not establish installation or runtime acceptance.

These are independent synthetic unit documents, not private user-journey oracle
files. Their bytes are preserved exactly. PPTX and its converted ODP retain
standard upstream python-pptx template author metadata; XLSX and ODS identify
openpyxl. No host/user paths, external relationships or linked content were
observed. No anydoc binary/vendor payload, private logs, host-bound result data,
credentials or private oracle documents are part of this export.

`core-office-native-intake-guards-manifest.json` is an explicit public projection
of the original frozen manifest. It records that original manifest's exact SHA,
retains its old dependency blocker as historical status, and adds the current
scoped gate evidence. It does not claim that the original frozen manifest was
edited. The unchanged patch represents the three pinned native afterimages.

`SOURCE-STATUS.json` records the exact evidence hashes, case selection, historical
failures and remaining boundaries. Source integration, native interpreter/SDK
qualification, installed runtime, ordinary user journey and final release gates
remain separate admission work. Publishing this review candidate does not add
it to the installed source chain.
