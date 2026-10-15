These are reusable source regressions for Native55 browser configuration, native IPC,
authenticated custody and owned update publication. They use synthetic filesystem
fixtures and fake transport/registry handles. They do not establish installed runtime,
real browser execution, network behavior or release acceptance.

Run from a Linux host with CPUs 0 and 1 available, using the project's existing venv:

```sh
export FRIDAY_NATIVE_SOURCE=/path/to/native55-source
export FRIDAY_PROJECT_SOURCE=/path/to/Friday_rework
# Optional: a dependency-only site-packages directory for native SDK imports.
# export SDK_SITE=/path/to/compatible/venv/lib/python3.14/site-packages
/path/to/project-venv/bin/python -B tests/native55/run_source_tests.py
```

The default is a selective readiness slice, including all eight owned-publication
controls. The broader original qualification remains a separate requirement. To
select another prepared group or an exact test, append its local filename or node ID:

```sh
/path/to/project-venv/bin/python -B tests/native55/run_source_tests.py test_browser_native_ipc.py
/path/to/project-venv/bin/python -B tests/native55/run_source_tests.py test_browser_scoped.py::test_foreign_task_never_launches
```

The runner requires the project to retain `tests/test_user_onboarding.py` and
`tests/test_admin_foundation.py`. It imports those existing fixtures directly and
preserves the corrected onboarding expectations. Native imports resolve through
`FRIDAY_NATIVE_SOURCE`; project modules and fixture resources resolve through
`FRIDAY_PROJECT_SOURCE`. Optional SDK_SITE is appended after these explicit trees.

Before heavy imports, the runner installs address-space 512 MiB, CPU 60 seconds,
file-size 64 MiB and core-size zero limits, affinity `{0, 1}`, and a 75-second wall
alarm. Pytest uses `/dev/null` configuration, disabled plugin autoload and cache,
and an owned HOME/TMPDIR beneath a temporary fixture directory. Set
`FRIDAY_TEST_WORKDIR` to choose an existing writable fixture parent. Temporary
fixtures are removed when the run completes.

The runner suppresses only legacy browser lifecycle atexit registration and audits
network/socket creation, process creation, signals, `/proc` reads and global browser
scans. A refused `/proc` read raises PermissionError, allowing native host detection
to use its existing failure path without reading another process. This source-only
host-detection refusal does not qualify container-specific behavior. All observed
refusals and selected module provenance appear in the final JSON output.

Native56 adds the gateway grant consumer regression in the same directory. Run only
this affected group for the narrow consumer correction; the earlier37-test source
readiness remains historical evidence for its unchanged Native55 snapshot:

```sh
/path/to/project-venv/bin/python -B tests/native55/run_source_tests.py test_gateway_browser_grants.py
```

The new group is also included in the default selection. The19 cases exercise the real `dynamic_configuration` consumer with synthetic
account/profile/route identities: complete seven-tool browser family, SAFE-only
regression, each partial family, unsupported/duplicate tools and foreign relationships.
This group does not invoke the full installed checker; exact read-only full-checker
observations are reported separately in the current installed-status record.
