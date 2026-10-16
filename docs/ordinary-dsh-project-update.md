# Existing-host DSH AppArmor project update

This source-only package installs the independently reviewed DSH R2 adapter using
`friday_install.py update-telegram` with schema
`friday.ordinary-telegram-project-update.v1`. It extends the existing ordinary
updater because its native source schemas always require another Hermes layer.
The project update keeps Source77's receipt, install stamp, all 77 layers and
native files unchanged. Only the installed DSH plugin and installation marker
are published; startup helpers remain project source referenced by the input.

The request uses the existing ordinary-update pins, including the exact committed
Source77 predecessor and complete recursive consumed history. Previous and current
inputs differ only in the reviewed DSH/updater/start/native helper files and one
new policy source. Runtime settings, workers, credentials and original budgets
remain pinned. The current input includes the exact policy source SHA.

Use the existing stopped maintenance workflow: retain its source/data backups,
verify current SDK parity against coherent database backups, prove native stop,
then invoke this updater under the existing finite deadline. The updater holds
native consumer/build custody and uses the existing private beforeimages and
owned-file publication/rollback. Its consumed journal is not retried. The normal
start/closure checks remain separate mandatory steps. A successful update is
source installation, without worker or runtime acceptance.

## Existing-host policy provenance and activation

`config/apparmor/friday-dsh-native-v1` is the exact independently reviewed R2
policy source (SHA-256
`5a400147afe52cf1ce879112ca41f6d2ff5718032971f438f7e5461b02e4176b`).
Its Node path and hash match this existing host deployment; this is not a portable
policy renderer. The adapter SHA-256 is
`b055c33ece99f669ec2a185f8227ffa70eea54b1afb696384670641ccd2c0554`.
No binary copy is distributed in this repository.

A separately authorized, enforced root activation verifies original root-owned
`/usr/bin/bwrap` SHA-256
`523da3e7399044be5163aee6f57a77a6bef7454376e28f0a0627920bae1b76b6`,
then creates a single-link exact COPY at `/usr/local/libexec/friday-dsh-bwrap`
(root:root 0755) and installs this policy at
`/etc/apparmor.d/friday-dsh-native-v1` (root:root 0644). Before creation, both
paths and both profile names must be absent; existing canonical ancestor
ownership/modes and original/global policy identity must pass. Reverify copied
bytes and metadata before loading with `apparmor_parser --add --skip-cache
--abort-on-error --jobs=1 --max-jobs=1`. Stop at the first failed check and retain
partial state. An existing activation must be verified rather than repeated.
Loaded profile evidence and bounded kernel/worker qualification remain separate
from this source package. Do not replace global bwrap or relax global policy.
