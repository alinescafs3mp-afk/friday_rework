# System-manager installation candidate (not activated)

The 2026-10-06 host probes demonstrated a real user-manager failure: correlated
executor PIDs 105720, 106122, 107411 and 108993 entered AppArmor's
`unprivileged_userns` profile and were denied `CAP_SYS_ADMIN`. Their `/home` and
source mounts remained writable; an outside `O_WRONLY` open succeeded without
writing bytes. This is not a report-writer defect and is not a passing deployment.

The candidate uses the existing **system** systemd manager to establish mount
protection, then runs a finite oneshot as `User=jericho`, `Group=jericho` with empty
capability sets and `NoNewPrivileges=yes`. `PrivateUsers=no` avoids asking the
unprivileged user manager to create the failing user namespace. It does not grant
mount privileges to Python. AppArmor profiles, sysctls, guards, old Friday and
the disabled user timer remain unchanged. No new supervisor is introduced.

The installed host has systemd `259.5-0ubuntu3.4`. Its local
`/usr/share/man/man5/systemd.exec.5.gz` documents system-manager identity switching,
the mount restrictions, state directory ownership and graceful degradation when
underlying sandbox facilities are unavailable. The same contracts are in the
[upstream v259 execution documentation](https://github.com/systemd/systemd/blob/v259/man/systemd.exec.xml).
[Ubuntu's AppArmor documentation](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/)
describes the unprivileged namespace restriction. These support the proposed
mechanism; they do not substitute for a live result on this host.

Only the reviewed observer, lock and small preflight are copied into a root-owned
`/usr/local/lib/friday-upstream-check-system` tree. Python uses isolated mode and
does not load code from the working directory, user site or Python environment.
Before observing any network data, the same process checks its non-root identity,
empty capability sets, no-new-privileges, private writable state directory,
root-owned source ancestors and effective read-only mounts. It then requires
`EROFS` from a non-truncating outside-write open of a dedicated owner-writable
0600 control file. DAC denial, missing files and successful opens all fail closed.
No bytes are written to the outside control, even on failure. A small exclusive
0600 state control is written, read back, fsynced and removed. Failure exits 3
before the observer is loaded. `--verify-only` performs these finite checks with
no network or upstream report. There is no separate `ExecStartPre` namespace gap.

Reports reside in `/var/lib/friday-upstream-check-system`, owned by jericho with
mode 0700; each existing observer report remains exclusive 0600. Dest/Astra
running as jericho can read them directly. No DynamicUser, group/world-readable
report access, or relocation of earlier evidence is involved.

## Exact remaining administrative installation

This is a reviewable candidate, not an installer executed by the agent. The
parent must accept the exact committed source/hash manifest first. The following
commands are for the owner, from that reviewed checkout, and deliberately stop
after installation and reload. They do not start or enable either timer/service.
The initial absence checks prevent an accidental replacement of another install;
an existing target needs explicit review, not removal to force these commands.

```sh
set -eu
test "$(id -un)" = jericho
test ! -e /usr/local/lib/friday-upstream-check-system
test ! -L /usr/local/lib/friday-upstream-check-system
test ! -e /var/lib/friday-upstream-check-system
test ! -L /var/lib/friday-upstream-check-system
test ! -e /var/lib/friday-upstream-check-system-control
test ! -L /var/lib/friday-upstream-check-system-control
test ! -e /etc/systemd/system/friday-upstream-check-system.service
test ! -L /etc/systemd/system/friday-upstream-check-system.service
test ! -e /etc/systemd/system/friday-upstream-check-system.timer
test ! -L /etc/systemd/system/friday-upstream-check-system.timer
systemd-analyze verify --man=no deploy/systemd/system/friday-upstream-check-system.service deploy/systemd/system/friday-upstream-check-system.timer
sudo install -d -o root -g root -m 0755 /usr/local/lib/friday-upstream-check-system /usr/local/lib/friday-upstream-check-system/scripts
sudo install -o root -g root -m 0644 scripts/check_upstream.py scripts/check_upstream_system.py /usr/local/lib/friday-upstream-check-system/scripts/
sudo install -o root -g root -m 0644 sources.lock.json /usr/local/lib/friday-upstream-check-system/
sudo install -o jericho -g jericho -m 0600 /dev/null /var/lib/friday-upstream-check-system-control
sudo install -o root -g root -m 0644 deploy/systemd/system/friday-upstream-check-system.service deploy/systemd/system/friday-upstream-check-system.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

No service code is run as root. The system manager creates the private state
directory on the first authorized start; the existing per-user state is untouched.
Both source directories must be named explicitly: `install -d -m 0755` does
not apply that mode to an implicitly created parent under a restrictive umask.
Verify both directories are root-owned `0755` before starting the service.
The new distinct unit names prevent an accidental operation on the blocked user
units. Check that the old user timer is still disabled/inactive before any future
scheduled use; do not run both timers.

## Live acceptance still NOT_RUN

The source candidate alone does not prove system-manager execution. After
installation, the first run must be offline:
use this exact runtime-only override (only if that override path is absent),
start the service once, and inspect the actual result and journal.

```sh
test ! -e /run/systemd/system/friday-upstream-check-system.service.d
test ! -L /run/systemd/system/friday-upstream-check-system.service.d
sudo install -d -o root -g root -m 0755 /run/systemd/system/friday-upstream-check-system.service.d
printf '%s\n' '[Service]' 'ExecStart=' 'ExecStart=/usr/bin/python3 -I -B /usr/local/lib/friday-upstream-check-system/scripts/check_upstream_system.py --verify-only' | sudo tee /run/systemd/system/friday-upstream-check-system.service.d/90-boundary-verify.conf >/dev/null
sudo systemctl daemon-reload
sudo systemctl start friday-upstream-check-system.service
systemctl show friday-upstream-check-system.service -p Result -p ExecMainStatus -p User -p Group -p ProtectSystem -p ProtectHome -p FragmentPath -p DropInPaths
journalctl -u friday-upstream-check-system.service -n 30 --no-pager
stat -c '%U %a %n' /var/lib/friday-upstream-check-system /var/lib/friday-upstream-check-system-control
```

Require the new invocation's `sandbox_preflight=ok`, `outside_write=EROFS`, status
0, correct owner and mode, and unchanged empty outside-control bytes. Review
effective mount coverage, cgroup/deadline behavior and final artifact hashes.
Neither unit property output nor offline tests are live mount evidence. On
failure retain the override/evidence and keep scheduling disabled; investigate
without weakening the guard or retrying another mount mechanism.

Only after acceptance may the exact runtime override be removed, the manager
reloaded and a single public metadata observation authorized. Require a fresh
complete report with the installed lock hash and verify direct jericho access.
Enabling the daily system timer is a later explicit activation step. No automatic
activation command is included in the installation block.

This is a write boundary for a reviewed finite metadata program, not a hostile
code sandbox. A same-UID host process can affect another same-UID process; home
data remains readable, supplementary login groups are inherited, and read-only
mounts do not block UNIX-socket IPC. Private `/tmp` and `/var/tmp`, and necessary
API filesystems, are not claimed read-only. The preflight checks the affected
paths and controls; it is not an exhaustive verifier of every submount or kernel
policy. External mount changes and source upgrades require renewed acceptance.
