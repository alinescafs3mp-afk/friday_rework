Complete cgroup event DATA validation candidate, 18 October 2026

This standalone review source rejects incomplete or malformed event observations.
It performs no cgroup reads or writes and grants no execution authority. It is
not imported by the product or connected to the native backend in this snapshot.

The six-field and current seven-field memory event profiles must be selected
explicitly. Unsupported optional fields remain unsupported, rather than zero.
The unchanged-control predicate compares memory max/OOM controls and pids max;
it preserves other observed fields without claiming every counter is equal.

One bounded HOST Python3.14.4 execution passed all13 methods and113 separately
recorded subtests. The process was actually reaped, its PID and process group
were absent, and input hashes were unchanged. Kernel/backend integration and
its whole dependent producer/consumer family still require independent review
and fresh native qualification. No private regression oracle or raw data is
included in this public archive.
