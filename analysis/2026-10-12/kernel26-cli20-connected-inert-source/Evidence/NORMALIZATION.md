# Inert-source normalization and integrity

The archive carries complete module and fixture contents as `.py.txt`. Private absolute paths are replaced by portable `${PRIVATE_PATH_NNN}` symbols. Host-specific device/inode and associated nanosecond timestamps in the two GNU readers are replaced only in their exact expected-value comparisons by `CURRENT_GNU_DEVICE`, `CURRENT_GNU_INODE`, `CURRENT_GNU_MTIME_NS` and `CURRENT_GNU_CTIME_NS`.

These placeholders represent required current bindings. They do not loosen identity validation or supply a runtime binding. The source comparison structure, full function bodies/calls, modes, ownership predicates, GNU bytes/SHA/ELF check and every unrelated algorithm/syscall/catalog/clock/cap constant remain. No definitions are added and no Source executes.

A private ledger records each original and public byte range, literal replacement, source/public byte count and SHA256. Reverse substitution reproduces the exact pinned original bytes. The private paths, inode/device/timestamps and private ledger are excluded from this public archive. This archive's public hashes refer only to the inert normalized bytes.

The source is deliberately not an executable distribution. Original fixture paths are historical definitions; portable symbols do not connect them to current input. Before any future execution, current fixture binding, exact final Safety, specific Root admission and all original physical gates remain mandatory. Old acceptance is not transferable to these changed derivatives or dependencies.

[PUBLIC-MANIFEST.json](../PUBLIC-MANIFEST.json) uses repo-relative path, exact byte count and SHA256 for every candidate file including the root README. It excludes only its own recursively impossible digest. Its own exact byte/SHA is in the private delivery manifest for integrator review.
