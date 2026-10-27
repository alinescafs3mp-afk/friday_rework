# A0 startup diagnostics: reviewed source, not worker acceptance

These files describe the scoped diagnostic delta prepared after R478 started
an A0 container and the attached native process exited with status 1. The
subsequent inspection refused the network state. The original exit cause is
unknown because startup output and the failed inspection were not retained.

`runtime.patch` targets the operational runtime with SHA-256
`4111e677a103b93ef3d898757e67cea7dad1da68c34d542689707286b802cdd9`.
It is review material, not a patch to apply automatically to public main.
`diagnostic_binding.py` applies only the diagnostic methods to one authenticated
Runtime instance. `prepare_start_scope.py` inserts that binding into the exact
existing start scope. Their source references grant no execution authority.
The installed runtime and its original source checks remain unchanged.

The delta retains the first rejected inspection's selected state and network
fields, and only the size/hash of arbitrary Docker error text. Startup stdout
and stderr go to private files, each limited to 128 KiB. Output overflow can
terminate the attached process; this is a bounded diagnostic operation, not
passive observation. Network ownership, readiness and cleanup predicates are
unchanged.

Validation recorded eleven distinct runtime tests and sixteen scope/recipe
checks, including the authentic private runtime loader, rejected foreign or
missing network fields, retained first failure, cleanup on diagnostic failure,
source substitution and metadata changes. A read may update access time; inode,
ownership, mode, size, modification/change times and content digest remain
checked. An isolated real systemd test accepted both output streams and enforced
the 128 KiB limit; both transient units were stopped and collected. These tests
do not prove a new A0 startup, worker qualification or Telegram result.

The next operation still requires current admission, preserved failed-attempt
archival and a fresh finite budget. The existing source-validation prerequisite
must run in that process: the retained stage records do not contain an exported
validator state that the current consumer can restore. Saved DSH safety evidence
remains reusable through its existing checks. No prior worker effect is replayed.
