# Current SDK archive fixture: source candidate

This directory archives an unconnected test-source candidate for review. It does not replace the repository test module or any installed product code. The exact baseline is `tests/test_worker_stale_archive.py`, SHA-256 `443d8140828acfb32ed19f60872d8e878f5d4d41e6fd91e42f4ba6eb910c150b`.

The candidate resolves the registered archive POST through the current FastAPI route contexts instead of assuming every top-level router has a `path`. It checks that the routed archive engine is the expected physical module and that each signed failure request reaches the intended delegate exactly once. Private per-test temporary roots remain distinct; shorter path names showed no demonstrated performance benefit. Compatibility with older FastAPI versions is not established.

On the exact candidate in its protected current-SDK fixture environment, 19 focused cases passed through genuine signed ASGI requests and the archive engine, including the four exception redaction cases and authorization refusals. A separate independent source review did not reject the route patch. These are source observations, not acceptance of the repository as a whole.

The complete archive group remains red: 350 tests were collected, 142 archive cases selected, 87 call results passed, 88 cases started, and 55 remained unfinished at the unchanged 100-second limit. No session finish was observed. The full-group timing finding remains HIGH. A completed StopUnconfirmed case does not support the earlier suspicion of an intrinsic hang. Profiling observed repeated configuration parsing costs; shorter paths did not close the timing problem.

Physical fixture materialization, producer and Focus bindings, the complete source dependency graph, current Root authority and final qualification remain pending. Previous failed execution scopes are consumed and cannot be retried or renewed. An early diagnostic helper's address-space bound was not established; corrected later helpers do not retroactively establish it. No installation, runtime, Telegram or release acceptance is claimed.

Only the existing public unit-test source, its patch and this source-status metadata are included. Private acceptance cases, expected task contents, transport evidence, account data and handoff material are excluded.
