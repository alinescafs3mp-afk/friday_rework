# Native observation and stop

`plugins/friday_rework/supervision.py` observes and stops an existing owned
transient user-systemd service. It does not launch, restart or retry work.
The controller must supply a checked durable association and retain sole
ownership of the unit across observation and stop. Model arguments cannot
provide a unit, invocation or admission identity.

Observation verifies the exact service name, admission-hash description,
transient status, known invocation and whole-cgroup kill policy. All requested
properties must be present and unique. Unsupported or contradictory service
states, malformed PIDs, foreign cgroups, failed commands and unreadable cgroup
observations raise an error. A racing observation is uncertainty, not proof
of cessation. A missing unit requires the complete consistent native shape.

`stop` sends one command for that exact unit, then checks invocation continuity,
terminal state, zero MainPID and an empty cgroup. Valid pre/post commands,
unknown forking MainPID and RemainAfterExit states are distinguished from
terminal states. Empty or duplicate population fields never prove cleanup.
No broad kill or automatic retry is used.

Independent component verification passed 44 offline controls and two real
bounded fixtures. Explicit stop and a systemd deadline each terminated a
parent and detached descendant; original PID/starttime identities disappeared
and both cgroups were removed. Wrong owner and invocation refused to stop
the live fixtures. Actual limits were 64 MiB, one CPU and 16 tasks. Prior
rejected parser/state snapshots and their failures remain in private evidence.

These checks prove only the observed unit boundary. Stopping an A0 client
does not prove its server, context or remote inference stopped. File isolation,
the controller's sole-writer boundary, retained stop intent, submission recovery
and the complete gateway/worker acceptance paths remain separate requirements.
The module is not yet connected to product worker admission.
