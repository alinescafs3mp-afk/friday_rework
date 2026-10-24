# Worker qualification after permanent-service restoration

Snapshot: **2026-10-25 01:26 Moscow time**. This supplements the fixed 01:09 service snapshot; it preserves the earlier observations.

Gateway and Dashboard remain accepted under permanent management. The installed source is still native121/project318 with the same external launcher SHA-256 `31caed537d264856338a3dbf776aaf13b62ab2006897cc54191239b5cfb4cd0f`.

The new R388 supported qualification returned HTTP 503. Its native failure recorded `STOP_UNCONFIRMED` at `a0_probe_start`. The exact new daemon invocation terminated with status 126; its journal proves that the rootless Docker child could not directly execute the current launcher because that file retained mode `0400`. This evidence describes R388 only. It does not establish the cause of the historical opaque 503.

R389 corrected only the current launcher's metadata to `0500` (owner read and execute), preserving its bytes, ownership and inode. The existing installed-source consumer accepted the state before and after the change. No installation, service start, preparation, qualification or user task was repeated by that repair; archive permissions remain unchanged.

At this snapshot the failed daemon has no MainPID, ControlPID, queued job or cgroup. Every PID recorded in that invocation's journal is absent, and its runtime state directory is empty. The exact pending route request and failed qualification/bootstrap records still require protected reconciliation and preservation before a genuinely separate missing qualification operation. No private guard receipt or successful stop is fabricated. The old clock, once-intent and native failure remain intact.

The earlier DSH safety stage reached its successor stage, but its full returned observation was only in memory. Its surviving scratch files are retained; they cannot manufacture a readiness receipt. Any necessary new safety observation must state this concrete reason, while preserving the completed installation, source repair, policy, preparation and permanent-service results.

| Separate measured interval | Seconds |
| --- | ---: |
| Current input/data preparation | 11.203 |
| R388 HTTP client including native server work | 141.682 |
| R389 metadata repair including source-consumer checks | 6.514 |

These intervals are separate and are not summed with nested server intervals. B56 DSH and B57 A0 Telegram tasks remain **NOT_SENT**; neither artifact acceptance nor contextual follow-up has occurred. Full release acceptance remains ungranted. The remaining blocker is the exact failed A0 attempt's reconciliation and missing successful qualification; it currently requires no owner decision.
