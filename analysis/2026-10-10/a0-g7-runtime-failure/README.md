# G7 runtime failure and verified cleanup

G7 consumed its actual six-scenario run with nine submissions: **five cases PASS; native-timeout-binding FAIL**. All required checkpoints completed within their original component deadlines; scenario validity passed. This is a failed runtime result, not A0 or release acceptance. [The normalized result](result.json) records outcomes and exact original evidence hashes; [the diagnosis](source-diagnosis.json) records limits, source references and offline checks.

The earlier [readonly component PASS](../a0-readonly-live/observations/05-live-and-custody.json) covered nine readonly calls and zero job submissions. [Prior source and corrected-input acceptance](../a0-g7-final-owner-source/README.md) accepted preparation only. Those dated records remain immutable history; their then-current NOT_MINTED/NOT_RUN states do not describe this later consumed run. The original [nine-source projection](../a0-g7-final-owner-source/composition/source-projection.json) and [source manifest](../a0-g7-final-owner-source/composition/projected-original-manifest.json.inert.txt) identify its bytes.

| Actual case | Result |
| --- | --- |
| late-dependency | PASS |
| late-ready-bound | PASS |
| late-ready-negative | PASS |
| native-timeout-binding | FAIL |
| post-gc-no-replay | PASS |
| sentinel | PASS |

The timeout case retained valid native capture, TERM-ignoring descendants, SIGKILL exit metadata, cessation before dependent fallback and the other recorded predicates. The outer stop hook nevertheless preceded the dependent hook by about 3.407 ms, violating mandatory reverse ordering. The offline diagnosis reproduced the original failing object, isolated that predicate with one explicitly synthetic counterfactual and passed twelve negative controls. These fourteen diagnostic checks are not another live run.

The source-supported explanation is a mismatch between the required order and the configured mechanism. RuntimeMax expiry directly enters service teardown. [systemd v259 service_dispatch_timer](https://github.com/systemd/systemd/blob/v259/src/core/service.c#L4097-L4100) supports this path. BindsTo then queues the dependent stop after the outer transition has begun. [retroactively_stop_dependencies](https://github.com/systemd/systemd/blob/v259/src/core/unit.c#L2119-L2128) and [unit_notify](https://github.com/systemd/systemd/blob/v259/src/core/unit.c#L2533-L2548) describe that propagation. After orders existing jobs; it cannot delay an outer teardown already in progress. [job_is_runnable](https://github.com/systemd/systemd/blob/v259/src/core/job.c#L488-L524) checks that condition. This is an inference consistent with captured events, not proof of the exact mapped manager image/source identity or an authenticated originating stop-job cause. That admitted uncertainty remains; no systemd runtime defect is established.

Reverse stop-hook ordering remains mandatory. An explicit bounded enforcement design still needs independent review while preserving kill/fallback guarantees, descendant cessation, coverage, resource limits and original deadlines. Removing the assertion, accepting either order, moving the marker, adding delays or enlarging budgets would not meet the retained requirement.

A separate finalization defect then prevented both final bus-inventory and refusal reports from fitting their fixed 64 KiB limits. The retained exception chain confirms those two failures, no original cleanup/snapshot error, and a closed terminal bus without a pending call. The failed parent produced no final release artifact. A serialization repair is separate work; this package claims no repaired candidate is ready or accepted.

Cleanup is established separately: the original parent recorded both cleanup phases, an independent review checked cessation and absence, and compact actual diagnostics were preserved and verified. The phases recorded 540 then 545 reaped transports, 27 absent actors, seven absent groups and eight absent units, with no jobs. The independent check also found 574 original identities absent and eight temporary drop-in directories absent. Finally, **at 17:26:16 MSK on 10 October 2026**, a separate checkpoint observed the original parent absent and no matching custody flock; the integrator also reported the owner's console-exit confirmation. This was normal owner exit after review, not successful replay of the failed finalizers. Cleanup does not turn G7 green.

The original 4/5/35/110/120-second component budgets, six scenarios, eight roles and nine-submission ceiling remain unchanged. kernel120 is NOT_GRANTED_NOT_RUN; normal3600 is UNSTARTED; seven user journeys, four web contexts, A0 and release remain UNACCEPTED. UC1 remains open because sudo/PAM/bootstrap precede component clocks. Old Friday remains OFF and Pandora/FRW013/FRW026 stops remain preserved. This package grants no retry or next generation.

Only aggregate facts and nonsecret original content hashes are published. Raw logs, receipts, grants, private paths, routing state, host/process identifiers and credentials are excluded. Original evidence hashes identify private source bytes; [the manifest](manifest.json) hashes these normalized public files. No new runtime execution occurred during publication preparation; root publication review remains required.
