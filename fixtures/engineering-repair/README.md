# Controlled engineering configuration repair

This finite stdlib meter-report application has two reversible settings faults.
The original application and 149-byte CSV stay unchanged. The CSV contains four
Russian customer readings in CP1251 with semicolon-separated columns. Initial
UTF-8/comma settings fail with a real `UnicodeDecodeError`; correcting only the
encoding exposes `CSV columns; check delimiter`. Correcting both settings yields
four readings, 33.00 kWh and 199.13 RUB, including a 13.125 → 13.13 per-reading
rounding case. This is fixture calibration, not observed A0 diagnosis.

`manifest.json` pins the exact source, input, original/known settings, actual
calibration report and owner checks. `mapping.json` contains PREPARED templates
and required current receipts; its placeholders grant no execution or destination
authority. Upload only `input/report.py`, `input/readings.csv`, `input/settings.json`
and the short `brief.txt` through the currently authorized receiving path. Retain
CSV as binary bytes; UTF-8 conversion changes the fixture. Never upload or grant
worker write access to `owner`, `calibration`, the checker or owner-side tests.

Only settings and generated report may change in the job. The diagnosis and
settings diff are retained evidence. The later parent proves source/input hashes
at the actual worker location before work and after work, retains actual native
tool logs, checks that the repair diff is confined to settings, and retrieves all
four exact outputs. Use the already reviewed native artifact/association helpers.

The finite owner checker parses data on the host, verifies immutable source/input
and golden hashes, snapshots regular single-link bounded bytes in a private
directory, and executes the unchanged app plus five original unittest checks in
the existing bwrap pattern. It never imports returned Python into the host.
Original app/CSV/settings/owner tests/returned report are mounted read-only;
generated report goes to isolated `/job`. The check has no home, host bus, inherited
environment or shared network namespace. Symlinks, hardlinks, FIFOs, oversized or
changing files, duplicate/truncated/nonfinite JSON, unrecognized settings and
escaping input/output paths refuse before execution. Wrong/partial/extra report
content fails the real owner checks even if a plausible success message exists.

Limits are two CPU affinity entries, 1 GiB address space **per subprocess**,
3 CPU seconds per process, 64 KiB file size and no core dump; inner app wall timeout
3 seconds and outer sandbox timeout 5 seconds. This offline checker does not
install a cgroup, enforce an aggregate native-worker memory quota, create a worker,
alter guards or validate an arbitrary Python program. The preparation gate uses
2 GiB address-space/45 CPU-second per-process limits and runs checks sequentially.

From this checkout root, run the full offline preparation gate:

```sh
python3 -B -m unittest discover -s tests -p test_engineering_repair_fixture.py -v
```

Run a known calibration with the same owner checker:

```sh
python3 -B fixtures/engineering-repair/check.py \
  --settings "$PWD/fixtures/engineering-repair/calibration/settings.json" \
  --report "$PWD/fixtures/engineering-repair/calibration/report.json"
```

For actual output, substitute absolute paths to the parent's stable staged copies
of returned settings and report. Do not pass worker-controlled host paths. The
parent first verifies/stages every artifact with existing `stage_file`/`read_staged`
and records type, byte count, SHA, origin and exact original task/destination.
Owner PASS requires exit zero **and** completed five-test `OK`; generation alone,
missing files, worker self-attestation or partial transfer cannot establish it.

This checker independently proves the corrected config works on the original
app/input and the returned report matches its actual output and independent
expected totals. It does not independently establish what tools A0 ran or whether
its earlier source was modified: those require current native logs, before/after
workspace bytes and scoped diff. Native A0/REST/model/Hermes/Telegram and real
delivery acceptance remain **NOT_RUN**. Astra reviews and binds a stable adapter,
current route, original budgets and isolated write grant before any live run.
