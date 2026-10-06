# Upstream observation

`scripts/check_upstream.py` is a finite Python standard-library metadata command.
It reads the exact bytes of `sources.lock.json` and allows only the locked public
Hermes, Agent Zero and DeepSeek Harness repository identities. Old Friday and the
legacy extraction/workspace are explicitly excluded. It does not invoke Git,
models, workers, Telegram, package managers, or a new supervisor; it cannot change
pins, source checkouts or installed software.

```sh
python3 -B scripts/check_upstream.py
mkdir -m 700 .evidence/upstream
python3 -B scripts/check_upstream.py --report-dir .evidence/upstream
python3 -B -m unittest discover -s tests -p test_check_upstream.py -v
```

The report directory must already exist (create `.evidence` first if necessary).
Its owner must be the caller and its mode exactly 0700. Symlink components and
unsafe writable ancestors outside an already private owned directory are refused. Each report is a new timestamped JSON file
created exclusively with mode 0600; existing regular files, symlinks and hardlinks
are never replaced. There is no mutable `latest` file or successful-report cache.
A failed current observation produces its own dated failure report; consumers
must check `completed_at`, `lock_sha256`, overall status and individual statuses.
If persistence fails, the current report still goes to stdout, stderr explains
that writing failed, and exit status is 2. A stopped process can leave an incomplete
new file; consumers must reject incomplete JSON rather than reuse an older success.

The explicit `--report-dir .` form pins the existing current directory directly;
it must still be owned by the caller with mode exactly 0700. The caller/supervisor
selecting that directory is the trust boundary. No absolute ancestor is traversed
for this form. This supports user systemd namespaces, where host root can appear
as an unmapped UID. Unmapped UIDs are never added to the trusted-owner list; all
other report paths retain the full ancestor and symlink checks.

Each branch head is captured once and compared as `PIN...OBSERVED_SHA`, never by a
second mutable branch lookup. The direction is **upstream relative to the pin**:

| Status | Meaning |
| --- | --- |
| `current` | Observed full SHA equals the pin. |
| `ahead` | Upstream descends from the pin; GitHub reports a positive ahead count only. |
| `behind` | Upstream is an ancestor of the pin; positive behind count only. |
| `diverged` | Both sides contain commits absent from the other. |
| `unknown` | Request, identity or compare validation failed; no freshness claim. |

The latest published non-draft, non-prerelease release comes from GitHub's
`releases/latest` semantics. Its tag is resolved once to an exact commit and
compared with the same pin, including releases older than the pin. The report
includes the release tag, publication date, notes and review links. Notes are
untrusted data and are never interpreted for compatibility or executed. The
release metadata and tag lookup are sequential observations, not an atomic remote
snapshot. Moving tags can race; the captured SHA and observation times document
what was actually seen. Compatibility always remains `NOT_ASSESSED`.

`absent` is reserved for latest-release HTTP 404 after a successful branch identity
observation in the same run. Without that public-repository evidence a 404 remains
`unknown`. Failures in one donor or endpoint do not hide other observations.
Overall `ok` means the observations completed, including an absent release; it
does not mean all pins are current. `partial` means at least one endpoint is
unknown. Exit 0 means `ok`; exit 1 means incomplete observation or invalid lock.
Changes requiring review are recorded separately in `changes_observed`.

Network requests are unauthenticated HTTPS GET to fixed `api.github.com` repository
paths. There are no token reads, proxy-environment use, redirects or retries.
Calls are serial, at most 15 per run, each with a five-second POSIX wall deadline
covering DNS, TLS, headers and a trickling body. Each response is capped at 1 MiB;
the lock is capped at 128 KiB. Large or malformed responses become unknown. Compare
page two, with one commit per page, avoids the large first-page patch list while
retaining GitHub's relation and counts. HTTP errors retain only a safe category and
status code, never server prose or response bodies. Rate limits are failures, not
no-change observations. Default worst-case network time is 75 seconds; there is
no background loop. This command targets the Linux/POSIX host.

## Optional daily user timer (not installed or enabled)

Templates live in `deploy/systemd/friday-upstream-check.service.in` and
`deploy/systemd/friday-upstream-check.timer`. The parent integrator may review and
render `@PROJECT_ROOT@` to the absolute reviewed project path, then install the
rendered service as `friday-upstream-check.service` and the timer in the existing
systemd user unit directory. Use systemd quoting/escaping for unusual path
characters (notably literal `%`); do not use a shell expansion as the root value.
No helper installs or enables these units.

The existing user systemd supervisor owns the oneshot and daily scheduling.
`StateDirectory=friday-upstream-check` supplies a private per-user state directory;
`%S` selects that user's state root without embedding a home path or user name.
The manager selects this state directory as `WorkingDirectory`, and the writer
pins `.`. The script and its default lock retain their absolute project paths.
The service requests a 100-second supervisor deadline, restrictive umask, read-only
home/system mounts and only its report directory writable. Nonzero observations
mark the unit failed and remain visible in the current report/journal. The daily
timer runs with up to 30 minutes of jitter and may catch up once when activated.
Installation, host-specific unit validation and activation remain parent review
steps; offline probe units do not constitute deployment acceptance.

Host acceptance must verify the effective mounts and a denied write outside the
allowed report directory. Merely accepting `ProtectSystem`/`ProtectHome` unit
properties does not prove that a user manager enforced those mounts.

API contracts: [compare commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits),
[resolve a commit/ref](https://docs.github.com/en/rest/commits/commits#get-a-commit),
and [latest release](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).
