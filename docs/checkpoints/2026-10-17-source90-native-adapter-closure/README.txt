Source90 native adapter source closure, 2026-10-17.

This adds source closure and finite native diagnostics to
../2026-10-17-source90-native-startup-readiness/.
The previous successful PM rebuild/selection, enclosing exit code 1 with its
original unclassified failure, and incomplete cache diagnostic remain unchanged.
No closed PM operation was replayed and no successful runtime repair is claimed.

A real typed preflight failed closed at external-ancestry admission, before new
selected-SDK startup or any compiler attempt. Its parent and namespace were
reaped and verified absent. A separate metadata comparison found all 46 files
and their aliases unchanged, with 76 of 77 directory identities unchanged. The
sole difference was the private runtime home directory's metadata-change time
(ctime); its mode and directory membership were unchanged.

A new, separately bounded native preparation-prefix trace established a causal
chain: configuration/provider discovery loaded the native home policy, which
called chmod(0700) on a directory already at 0700. For that home directory, ctime was the
only changed identity field; all other identity fields and membership matched.
Five causal source files matched the installed source manifest. This establishes
that new traced point, without retroactively tracing the earlier failed point.
No permissions were manually repaired and no expected baseline pin was replaced.

Two private source packages are now complete and independently reviewed:
  * The core process driver and authenticated integration-entry hook: 84
    manifest members. Scoped producer controls passed in groups of 8, 21 and 20;
    independent controls passed in groups of 8, 5 and 7.
  * The namespace projection, exact typed metadata facade, private-home policy,
    selected collector/capture bindings and integration entry: 40 manifest
    members; 62 producer controls and 51 independent controls passed.
The groups overlap and are not a combined global test count. These are source
and local fixture results; neither package executed the selected SDK, native
compiler, recovery, capture or services as part of those source assignments.

The new source derives ownership projection from measured kernel namespace and
peer data. Its home-policy adaptation is limited to that exact private home
ctime after authentication; all other guarded metadata, membership and alias
checks remain. The original 77-directory/46-file contract and strict original
preimport source are preserved. There is no general ownership or ctime waiver.

Separate actual read-only and read-write namespace transport probes passed.
They demonstrated that child self-mappings differ from the host parent's view,
and identified ownership overflow through kernel data. Each native child exited
zero, was reaped, and had its namespace exit verified; each server thread joined
and its owned socket was removed. These probes did not execute the final
projection adapter. A separate actual probe then qualified the exact physical
process-tracing topology under the previous interpreter and original namespace
controls: one sealed compiler exited zero, a valid-header/wrong-payload cache
control was refused, and one namespace plus its PID1 child exited zero. All six
owned tasks were reaped, process groups were absent, and the server thread joined
with its owned socket removed. The measured mappings under tracing matched the
earlier calibration. This is physical compatibility, not application cache or
product acceptance.

At this checkpoint (23:02 MSK), the previous interpreter's full current default
loader code closure is still being qualified separately. The successful physical
probe ran once for about 0.349 seconds within its own original 300/240/60-second
boundary; the complete qualification assignment took about 353 of the original 900 seconds. Actual metadata recovery, new selected-SDK
startup, collector, capture, renderer, service and R9 execution remain unissued.
The complete final execution graph still needs admission and actual verification.
Full product acceptance remains pending with its existing scope.

This is finite evidence for analysis, without continuous custody, future
permission guarantees or a live PASS. The host-bound implementation, raw receipts
and private execution bindings are excluded; no portable implementation is added.
