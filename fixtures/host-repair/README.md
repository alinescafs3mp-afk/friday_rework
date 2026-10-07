# Controlled coding repair input

This controlled Hermes → Harness repair uses the same calculator and
byte-identical owner tests previously proved in FRW005 native coding. The fixture
itself grants no execution, route or destination authority. The complete live
AC014 and AC050 Telegram journeys require the current reviewed integration.

## Attachment and brief

Upload only `input/calculator.py`, with original filename `calculator.py`, MIME
type `text/x-python`, UTF-8 text, **32 bytes**, SHA-256
`e1a894022d1a082987b87adecb623438c9e386d86b2b621cff4a5fe7fdf7edc8`.
Do not package an archive or upload the owner directory.

Suggested brief:

> Repair the supplied calculator.py: add(a, b) must add its two arguments.
> Keep its public function and fix the expression in the supplied file. Return
> the repaired calculator.py and the repair diff. The owner independently
> checks add(7, 5) == 12, add(-2, 3) == 1 and add(0, 0) == 0. Keep the
> implementation as one plain function with a returned expression on a and b;
> do not add imports, calls, module effects or alter the owner's checks.

This deliberately small fixture accepts `a + b` or `b + a` as the returned
expression. Its checker also admits the original subtraction shape, which must
fail the behavioral tests. Other Python shapes are classified as
`fixture_source_contract_refused`, not as a successful repair or a general claim
that the submitted code is incorrect.

## Ownership and checks

`owner/test_calculator.py` is **270 bytes**, SHA-256
`3046b45b0b2c2702ac686ef1e946a6601c67d456a4e49b895566310674b33995`.
Its three assertions are copied unchanged from the earlier native fixture.
The parent retains and pins these bytes **outside every worker write grant**.
If the worker needs to run the existing unittest command, expose the same checks
read-only in its assigned disposable repository. The worker's reported PASS,
test edits or process exit alone do not certify the owner's goal.

The portable operator check in `fixtures/host-repair/check.py` uses the existing
bwrap isolation and ordinary Python unittest. The original test module explicitly
imports its compatible `isolated_check` and `_isolated_unittest` exports. `isolated_check` parses the
finite fixture grammar without executing candidate code on the host, then
mounts the checked candidate at `/job/calculator.py` and the unchanged owner
tests at `/owner/test_calculator.py`, both read-only. It exposes `/usr`, isolated
`/proc`, `/dev` and temporary `/tmp`; no host home, user bus or network is
available. Limits are two CPU affinity entries, 1 GiB address space per process,
3 CPU seconds per isolated check and a 5-second wall timeout. A quarter second of the wall budget is reserved for forced cleanup; a timed out
check never reports acceptance. Forced teardown records start-time identities in
this launcher's existing descendant tree, kills its process group, reaps the
launcher and confirms the recorded descendants ceased within the remaining wall
budget. Missing teardown evidence returns `cleanup_unconfirmed` with acceptance
false; no global kill or extra supervisor process is used. Captured stdout and stderr use regular temporary
files under the same 64 KiB file limit, with a full-boundary output classified as
`output_limit`. All checks run
sequentially; no host cgroup or native unit is changed. This is a finite fixture
check, not a new worker, store or orchestration protocol.

Run the offline preparation gate from the checkout root:

```sh
python3 -B -m unittest discover -s tests -p test_host_repair_fixture.py -v
```

For an actual returned output, the parent first uses the existing `stage_file`
and `read_staged` helpers to retain exact bounded bytes under its allowed private
artifact directory. It then applies `isolated_check` to that stable, owner-held
copy; it never imports returned code directly on the host. The checker reads a single-link, current-user-owned regular candidate through
no-follow descriptors for every path component, with a 64 KiB limit and identity/
size/mtime/ctime comparison before and after reading. It parses the captured bytes
and mounts only private mode-0400 copies of those bytes and the pinned owner tests.
Replacing the caller file after reading cannot change what executes. The private
checker directory is a trusted owner boundary, not protection against a hostile
process already running with the same host UID. Check
the pinned owner test hash before and after execution. A PASS requires the
actual original unittest run to complete successfully with all three assertions;
retain exit status and stdout/stderr as evidence. Missing output or refused
source shape cannot be relabelled PASS.

Run the portable CLI with one candidate path (relative paths are allowed; `..` and
symlinks are refused):

```sh
python3 -I -S -B fixtures/host-repair/check.py /absolute/staged/calculator.py
```

It emits one bounded JSON object: `accepted`, `executed`, actual `child_returncode` (`null`
when no child started), helper `returncode`, `status`, elapsed seconds, artifact and owner SHA-256,
complete captured `stdout`/`stderr`, lossless base64 copies, and cleanup status.
A preflight source-contract refusal uses code 2. CLI exit is 0 only for acceptance,
124 on timeout, otherwise 1. The actual child code is retained separately, including
negative signal codes. Acceptance requires grammar admission, original unittest
completion, unchanged owner/snapshot bytes and confirmed cleanup. `_isolated_unittest`
remains an internal compatibility probe for isolation tests; its observations never
claim acceptance because the grammar is bypassed. No stale output is reused.

The trusted CLI does not accept a command, test override, interpreter override or
other execution profile. It is Linux/bwrap dependent and proves only this arithmetic
fixture. It does not prove Telegram origin/delivery, general project safety, a live
host execution route, or the absence of same-UID interference with checker internals.

## Native input and output contract

Use Hermes's actual authorized upload/reply identity and receive-time byte
receipt. `stage_inputs` must return the exact byte count/hash and task-specific
stable host/worker mapping. The parent proves the same bytes at the **actual**
worker-visible location before submitting dependent work. The offline receipt
fixtures and checker mount prove neither Telegram provenance nor worker access.
Actual positive configured size/type limits come from that receiving adapter;
the offline tests' 32/64-byte limits are test controls, not Telegram limits.

The expected output is a regular, task-owned `calculator.py` that satisfies the
above function contract and unchanged checks, plus its repair diff and actual
worker test output. A known independently supplied correction has SHA-256
`ba1a531f581d2e6094e978ed6f7aca7a8d92eeb62c6e7ad73ee692f7f18bc772`
and the same 32-byte size. This hash identifies the calibration correction;
equivalent accepted formatting/operand order need not have that hash. Record
the actual output name, type, size, SHA-256, complete/verified flags, staged
reference, task origin and the owner's real check result using existing artifact
records. Deliver those same stable bytes to the original authorized destination.

Missing required upload is an explicit refusal: an empty `stage_inputs` tuple
is only a zero-file observation, never permission to invent a replacement.
A missing cache file refuses mapping; same-size changed bytes must produce
`input_bytes_changed_since_receive`. Two tasks with the same original filename
retain separate staging roots, byte receipts and destination bindings. Forced
stable-name collision must preserve the first file and refuse the second copy.
Unsupported type and real delivery failures use the current native route's
truthful result; this preparation does not claim those live cases have run.

Before native execution, Astra binds the reviewed host/adapter candidate,
actual route/IDs, original budgets, isolated worktree and write grants.

## Observed coding component

The actual Hermes → Harness run completed on 2026-10-07 at 02:49 MSK in
26.76 seconds, using the accepted host source at `4f09c3f` and these exact fixture
bytes. Hermes made one native worker call. Harness read the original file,
produced a 32-byte correction with the hash above and a 180-byte diff, and
observed `12 1 0` in its own Python check. The parent staged the actual outputs
and independently confirmed original-test FAIL → returned-file PASS with the
unchanged owner test. Actual native resources and process cessation were also
observed. Earlier diagnostic setup failures remain recorded separately.

This used a synthetic Telegram ingress through native admission, with the
temporary local context-40960/output-4096 test profile. It proves the coding
component, not actual Telegram upload/reply or returned delivery; those complete
journeys remain **NOT_RUN**. The fixture checker is not a general product goal
verifier, and its result does not populate the production association's pending
goal-verification or delivery fields.
