# A0 web installer parent-mode fix — installed, worker qualification pending

R479's captured startup output identifies `native_web_overlay_refused` at the
generated installer's parent-directory check. The owned container exited with
code 1 after about two seconds; `OOMKilled` was false. Its network endpoint was
absent when the later runtime inspection refused it. This is direct R479
evidence; R478's unrecorded original exit cause remains unproved.

The pinned image (`6b300a0a4341632f021fb1b5d2641296ff4882ba7636e228f57c58bc9105c4f8`)
contains `/etc` with root ownership and mode `0775`. Image configuration, layer
metadata and the stored filesystem agree. The existing Git-configuration
installer rejects group-writable parent directories. `/a0` is `0755`, and the
repository copy script does not change `/etc`.

The patch normalizes only that known image's fresh-container `/etc` from `0775`
to `0755`, or accepts its already-correct `0755` mode. It requires UID/GID `0:0`,
opens the directory with `O_DIRECTORY|O_NOFOLLOW`, and checks descriptor/path
identity before and after `fchmod`. The original strict parent, source-content
and exclusive target-creation checks still execute afterward. Retained user
files, host directories and the base image are unchanged.

The target `a0_web.py` digest is
`975bfd8c75e43b18e6d55d66f172d0d5929f100c83c16611a98efb841dd32b76`.
Twenty-one filesystem replay cases passed, with independent source review and
nearest-consumer checks. Tests use actual image files and metadata with explicit
container-UID translation; they are not an actual container startup. The native update
must join the canonical and native copies and their exact source-transition
consumer before the next real qualification. No worker or Telegram acceptance
is claimed by this source package.


R480 installed this web adapter and its exact declaration edge into canonical
source. A fresh installed process accepted the installed input and verified
47 physical plugin files. The later separate native update committed and its
six files were verified; a real container startup has not yet been accepted.
The 21 replay cases above remain source evidence, and neither new DSH/A0
Telegram file task has been sent. See the
[R480 installation checkpoint](../../worker-web-service-source.md#r480-canonical-source-installation)
for the separate capture/updater timings and the two preserved pre-dispatch
refusals.

The exact [declaration edge](declaration-edge.patch) is part of the installed
canonical source change. The [maintenance budget guard](maintenance-budget-provenance.patch)
and [typed finalizer excerpt](typed-finalizer-excerpt.patch) document the two
private maintenance corrections used for this installation. The finalizer
patch is a function excerpt for analysis; private invocation bindings and
execution records are intentionally omitted. These patches do not constitute
a standalone installer or a native/runtime acceptance result.


## R480 native preflight refusal and sidecar-absence correction

The first R480 native apply refused during retained-input preflight, before a
native update transaction was created. The producer records already absent
`kanban.db-wal` and `kanban.db-shm` files; the private consumer's absence allowlist
did not admit those two names. The closed attempt left all 11 pinned before-state
hashes unchanged, the core database unchanged, both sidecars absent and no native
leader. This is a confirmed no-update result, not an unknown native effect.
The accepted canonical source installation and its capture remain preserved;
this correction does not require replaying that installation.

The [sidecar-absence patch excerpt](sidecar-absence-excerpt.patch) changes only
the private retained-input consumer. It admits an absent WAL or SHM only for the
exact parent-mode service family, with both input digests equal to the accepted
installed input, and a non-null core database reference having exactly `path`
and `sha256` fields at the expected home-relative path. The caller must still
prove physical absence with `os.path.lexists`. The core database continues
through the unchanged retained-pin guard; access, attachment, native-unit and
full-admission checks remain in place. Other files and service families do not
gain an absence exception.

The excerpt uses a generic `private-worker/` header; its hunk body is the exact
accepted private-source delta, including the fixed input digest. It is published
for analysis, not as a standalone installer. No captured request or user data is
included. The final private worker digest is
`f0e40a05f63e7ff485c755e5c9911f1856e832fcd1878084714c372310ce99fe`.

Source checks covered byte-exact inverse reconstruction, the retained-input
consumer and unchanged guards, including rejection of present sidecars,
wrong input digests or family, missing/invalid core references, unrelated
absence entries, and changed access/attachment joins. Independent source review
recorded 178 passing checks with no high or medium findings. Its retained-loop
replay used a virtual filesystem: it is source/metadata evidence, not live
runtime acceptance. A separate 24-check binder supplement preserves refusal of
the closed first attempt's authority; it also does not prove a new native run.

| Stage | State at this checkpoint |
| --- | --- |
| Canonical source installation | Accepted; preserved without reinstall |
| First native apply | Closed: preflight refusal, no native update transaction |
| Private sidecar-absence correction | Source accepted; exact limited delta |
| Separately admitted R2 native apply | Committed and physically verified in 833.396566 seconds |
| Gateway and Dashboard | Restored permanently; process/systemd/HTTPS checks passed |
| Fresh container/runtime and Telegram file tasks | Not accepted by this source checkpoint |

The compact [result record](sidecar-absence-results.json) carries the same scope
and actual R2 status. R2 reused the saved capture and did not repeat canonical
installation. A fresh installed process checked the native adapter against the
existing runtime input. The next qualification preflight exposed a separate
reader compatibility issue with immutable `0400` native receipts and stopped
before worker admission. Receipt permissions and healthy services are preserved.
These results do not establish worker or Telegram user acceptance.

## Qualification reader and immutable native receipts

The post-install qualification preflight stopped before creating its operation
directory or clock: its private document reader expected `0600`, while the native
mechanism had correctly sealed the new receipt and commit at `0400`. No worker
was started by that refusal. The installed source, services and signed owner
observation were preserved.

The [reader delta](immutable-receipt-reader.patch) admits `0400` only for the two
exact current native receipt references in the bound qualification input and
their canonical transaction directory. Existing owner, protected-parent, link,
identity and content checks remain. A separate callback keeps the exact prior
service receipt on the nonprivate protected-read contract already used by the
historical derivative reader. Other private `0400` files remain refused.

The actual nearest consumer passed 130 reads across 76 pinned files; independent
review covered the narrow policy and caller graph. The existing driver then
started a distinct qualification with the repaired local reader, retaining the
installation and owner proof. Qualification and Telegram results are separate
from these reader checks.

The resumed R481 qualification subsequently saved a successful real A0 startup
observation: local route, native Web UI and configured local model slots passed
the no-model startup check. Cleanup then returned `STOP_UNCONFIRMED`. Read-only
reconciliation confirmed stopped units and processes, with the route removed.
A separate maintenance operation then retired the stopped container and removed
its introduced keys in 3.193394 seconds. A fresh postcheck verified that cleanup
on the same result after correcting an access-time comparison in the checker;
the cleanup operation was not repeated. The remaining real DSH observer then
passed four smoke commands and a network probe in 5.801276 seconds; all five
commands were reaped. Its separate 300-second operation used a 270-second
observer deadline and a 30-second outer reserve. A0 was not restarted.

The two observations remain individually preserved. Final qualification and
runtime attachment still require a consumer that correctly accounts for their
distinct original clocks; these observations alone are not a Telegram result.

## Early structural checks — source proposal, not integrated

The [early-input patch](cheap-input-preflight.patch) checks impossible request
shapes before native input reads, inspection or history traversal. It validates
required source companions, static inventory entries, relative paths and the
existing narrowly permitted absence cases. All physical custody, current state,
complete dynamic inventory, history and authority checks remain at their original
boundaries. A well-formed but wrong hash still needs the later content check.

This independent source proposal passed structural and caller-prefix checks and
a separate review. It is not integrated into the running qualification or the
installed runtime and is not a condition for the pending Telegram tasks.
