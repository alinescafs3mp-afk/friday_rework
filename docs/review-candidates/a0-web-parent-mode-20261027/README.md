# A0 web installer parent-mode fix — canonical source installed, native pending

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
47 physical plugin files. The native web copy still has its previous digest;
the native update and a real container startup have not been accepted.
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
