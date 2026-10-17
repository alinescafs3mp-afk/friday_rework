Source90 PM refresh and selected-environment admission, 2026-10-17.

The package manager (PM) actually rebuilt and selected a new environment for the
installed Source90 source. This is new execution evidence after the earlier
source-install-and-artifact-checks checkpoint. That checkpoint's earlier
pre-dispatch refusals and cancellations remain historical facts; this report
does not relabel them as successful runs.

The native PM receipt reports a successful source refresh and rebuild. The
manager-import subprocess and the PM subprocess both returned zero, were reaped,
and had their process-namespace exits verified. Their measured native durations
were 0.044 and 12.794 seconds respectively. These are subprocess observations,
not the elapsed time of the whole operation. The selected environment recorded
in the current package Facts agrees with the successful refresh result.

Current product source identity:
  3a87e0c40c0d1b985e8775db9bc1e8bd79863241acd82068444fae344ebd3a52
Parent product source identity:
  060273f891c563d81f71e41de63ef5ef2be566c696d6533718afd96c789f6101
The installed source remains the genuine 90-layer, 17710-file Source90 package.
Its canonical complete-files fingerprint, published in the preceding checkpoint:
  9d3d1bed9ae48dfcd16df8e0835eeac9b408074ff11d5cea8e50099a1254532c
These source identities are distinct from a public repository commit identity.

The enclosing operation nevertheless exited with code 1 at the selected
metadata admission stage, before the post-PM selected collector entered the new
selected SDK. Its original failure record reports an unclassified ValueError at
pm_selected_preimport; no successful enclosing-operation return is claimed.
The native PM producer may execute its own interpreter while building an
environment. The pre-collector failure must not be described as proof that no
interpreter ran during the successful native build.

A separate read-only metadata diagnostic, running with the previous interpreter
in isolated/no-bytecode mode, reproduced the refusal reason
owned_nonwritable_selected_directory_required. It did not execute the new
selected interpreter and is neither selected-SDK admission nor a live test.
The point observation found native directories with mode 0775 and files with
mode 0664, which fail the current strict requirement to exclude group/other write
bits (0022). A containing runtime directory was observed with mode 0700; that
shielding observation does not waive the gate. The editable-install .pth file
also had two hard links. Its admissibility remains a separate metadata issue.
The diagnostic does not retroactively recover a more specific exception message
from the original enclosing-operation failure.

Before this PM run, a narrow native working-directory correction was qualified:
four manager dependency imports and the previous interpreter's exact environment
passed; an unexpected extra environment variable was rejected as required. All
three probe namespaces were reaped. The qualification took approximately 0.088
seconds of its own 30-second allowance. It establishes that limited environment
contract, without transferring it into new selected-SDK or runtime acceptance.

All completed PM scopes remain closed without replay or a PM rebuild retry.
A distinct metadata-only recovery/source correction is pending. The gateway and
Web UI remain stopped, with zero new Telegram requests since Source installation
at this checkpoint. Full-scope, R9, renderer, skills, memory and Web UI acceptance
remain pending. Successful rebuilding and selection therefore do not establish
runtime or product acceptance.

A separate finite preservation recheck made stable reads of all 2284 baseline
files. The 2283 retained files, totalling 353178870 bytes, matched their baseline
content and metadata. One receipt control was replaced by the expected native
PM receipt; the accepted check confirms that replacement matches the successful
PM receipt on disk. Thus not all 2284 baseline files were unchanged. This is a
point observation, not an exhaustive inventory of the new selected environment
or a claim of continuous custody.

This is a curated progress-and-failure report. The host-bound recovery/control
packages remain private; no new portable implementation is introduced here.
Raw receipts, local filesystem identities and private execution bindings are
withheld. The observations are finite checkpoint evidence, not continuous
custody or permission guarantees.
