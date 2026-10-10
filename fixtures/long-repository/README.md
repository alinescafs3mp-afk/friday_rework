# Real historical repository task — source input only

This is the actual root-qualified reference bug in Friday_rework's daily Git
inventory tool, selected as a coding and explicit-continuation case. It is a
historical task replay, not a claim of new product implementation or worker work.

Give a separately admitted worker only `worker-input.tar.gz` and `brief.txt`.
The archive contains `worker/USER_BRIEF.ru.txt`, `worker/SOURCE_ORIGIN.json`, and
`worker/repository/`: five exact files from source commit
`93090925f065d68b2b77c85b8903590864468e99` with a single isolated seed commit
`4be5689279ec0e3c6ef94826b6e1906c7e9f1e48`. It has no remotes, borrowed history,
solved source or new owner tests. The task changes the implementation, regression
tests and usage documentation; source Git identities and scope stay fixed.

`owner/selection.json` records the exact input and proposed write boundary.
Everything in `owner/` stays outside worker access. The known solution is only a
calibration oracle. Evaluate a returned implementation in a separate owner
workspace beside the unchanged `test_daily_finalizer.py` and
`current_reference_checks.py`, under separately admitted bounds. These checks
create finite local Git fixtures. Do not run them inside the immutable oracle
or replace them with tests modified by the worker. Documentation, diff and
scope still need owner review; literal equality to the known solution is not
required. File modes and hashes alone are not runtime access isolation.

Observed source calibration: original10 tests PASS; original source with new
owner tests FAIL as expected; historical solution20 tests and24 reference
controls PASS. The solution and final tests are exact bytes from commit
`a26c9b8525808a46f04ac41956ed60c3912520ef`. Calibration is not Harness execution.

On an actual explicit continuation, retain the same original repository, partial
diff, native association and deadline. No reseeding, new job, reset budget,
repetition or artificial sleep. Runtime budget/grant, actual continuation,
measured duration and delivery remain pending. The daily corpus's full seven
installed and four web journeys, soak and release acceptance are unchanged.

`validation/validate_daily_data.py` checks the six fixed source/oracle byte pins
and the corpus's original-goal, seed, worker/owner and pending-runtime joins.
It does not unpack, import or run the repository. Its PASS is data integrity only.
