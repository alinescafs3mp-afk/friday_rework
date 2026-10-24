# Worker execution checkpoint — 2026-10-25, 02:03 MSK

Installed: native 121 / native files 17717 / project 318 / plugin 47, with the existing external A0 launcher bytes unchanged and its current executable mode repaired to owner read/execute. Gateway and Dashboard remain under their accepted permanent owners. Their lifetime is independent of a test window. This checkpoint does not claim full product readiness.

The subsequent ordinary supported worker qualification returned HTTP503. Its protected native diagnostic identifies `child_identity` at launcher line 498; it does not identify which member of the identity/cgroup conjunction failed. The earlier executable-permission failure belongs to a different, already reconciled attempt. It is not assigned as the cause of this failure or of older opaque responses.

The failed attempt is now physically reconciled. Its original processes and cgroup are absent, its daemon state directory is empty, and only its exact retained route request was removed under the existing exclusive lock and current resource/CAS checks. Both complete failed-attempt trees, containing 25 files, were archived unchanged. Historical `STOP_UNCONFIRMED`, original deadlines, consumed intents, failure records and recovery code remain evidence; this external reconciliation does not fabricate a native successful stop. The earlier failed-attempt archive was retained.

Launcher line 498 can be reached before or after the private namespace policy step, but both call sites precede guard publication and dockerd execution. Therefore no Docker daemon or user task is claimed, while possible earlier private namespace/policy activity remains explicitly unknown and bounded to the now-dead resources.

Bounded kernel observations using the existing RootlessKit showed a separate compatibility defect: a child user namespace cannot read the parent executable through `/proc`, returning permission error 13, while the host can verify that executable. Parent identity fields were stable in these observations. A separate transient systemd diagnostic with delegation and the existing rootless wrapper also observed stable fields. These observations do not prove the cause of the actual line 498 failure. The wrapper diagnostic used its own finite unit and default detach behavior, so it is not a replay or acceptance of the product service.

| Measured interval | Seconds | Boundary |
| --- | ---: | --- |
| Current qualification data preparation | 11.402 | No qualification request |
| Qualification HTTP client, including server work | 145.038 | One request; refusal; logout confirmed |
| Exact retirement operation, including two local invocation-guard corrections | 84.202 | Same original finite clock |
| Cleanup child start to completed archive, observed upper bound | 0.066 | Nested in retirement; do not add |
| Transient delegated kernel observation | 0.173 | No Docker/model/user request |

No coding or engineering Telegram task from the next milestone has been sent, and no returned artifact or same-chat continuation is claimed. The immediate missing result is the installed A0 guard/diagnostic repair followed by real ordinary qualification and the two file tasks. Source, installation, runtime execution and semantic acceptance remain separate facts. Existing preparation, policy, installed native source and completed service startup results are retained. The source work is limited to the changed launcher and directly connected consumer/pin joins; it does not require a full reinstall, prepare replay or new verification framework. No external owner decision is currently needed.
