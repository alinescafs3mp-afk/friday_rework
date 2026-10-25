# A0 deferred safe failure diagnostics — source only

S290 is accepted as a **deferred source package**. It does not enter the current
R398 candidate. The accepted launcher/runtime pair remains unchanged. These
files document a future launcher change; they establish no installation,
native, kernel, runtime, API, or Telegram acceptance.

## Source behavior

The patch adds request/context SHA-256 correlation, fixed stage/phase labels,
and allowlisted builtin exception classes to attester failure diagnostics.
Failure reporting uses one best-effort nonblocking write of at most 1024 bytes
under the existing deadline: the readiness pipe during startup, or the connected
socket after peer authentication. A failure frame is never accepted as proof.
The launcher sanitizes attached diagnostic fields using exact builtin types;
arbitrary exception messages, diagnostic values, and custom class names are
not exported. Existing cleanup and success-proof validation remain unchanged.

## Exact source identities

All hashes are SHA-256. The complete patch targets `scripts/rootless_docker_launch.py`.

| Material | SHA-256 |
| --- | --- |
| Original accepted launcher; complete-patch input | `bd4864aa015870583dda97c23da9b4f0ce024bf0ebcb00c97c0a579530298098` |
| Initial proposed diagnostics launcher, before reviewer fix | `0d32c9469f4b4d469c0792cd33063610dad2c6e68e2d3f7ec6f82097e3b3f04b` |
| Final deferred launcher, including reviewer fix | `265b9817ea4949c41ee8c4a5c17f90711010fe0f9cf9c54598c9e55721b14acf` |
| Complete patch in this directory | `4b45ff7642943f5f337f7f53404be2ff3ef426fd18e46fadf87fa91db5671bd1` |
| Unchanged accepted runtime | `80d99c263c0a242ca9ef5c76e34140d58e15c93f77f9994b776d6122b4aa5ccb` |

## Accepted offline evidence

Independent delta review accepted the final source. Its reviewer-owned sanitizer
fix was independently checked by the parent with 21 passing checks using pure
extracted functions. The original synthetic local finding is preserved: string
subclasses used as attached diagnostic keys/values, and a custom exception
metaclass, could spoof comparisons and export a canary in the initial proposal.
The final source rejects those synthetic leaks. No remote exploit was demonstrated;
normal JSON decoding produces builtin strings.

Existing socket/pipe, EOF, timeout, full-buffer, authentication, cleanup, and proof
controls are reused only for unchanged relevant subtrees. Changed sanitizer
dependencies received focused independent controls and the parent checks above.
This publication package reuses those accepted results without rerunning them.
Historical R397 kernel observations apply only to the unchanged baseline and do
not establish acceptance for the final deferred launcher.

## Remaining LOW limitations

- The unchanged runtime does not forward launcher stderr into runtime/API responses.
- Between readiness-pipe closure and an authenticated connection, there is no
  trusted reporting channel; the underlying cause remains `UNKNOWN`.
- EOF, timeout, malformed or missing frames leave the cause and phase `UNKNOWN`.
- A failure frame describes the body failure before cleanup. Cleanup remains
  `UNKNOWN`; existing cleanup-failure replacement semantics are retained.
- The new source has no native, kernel, runtime, or Telegram user acceptance.
