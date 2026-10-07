"""Finite owner check for these exact report inputs. No candidate Python imports."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import stat
import subprocess
import tempfile
import time


FIXTURE = Path(__file__).resolve().parent
PINS = {
    "input/report.py": "00990b6a906b0105d95710544728b7308d45066c05a382ab43cdcb42f49e01aa",
    "input/readings.csv": "c96621da714aead2d7924f394249a4f33e0f871041da27dfa6663c2b7994f8bc",
    "owner/test_report.py": "b5ba3fde01b614ff95651a9f3f8306edbaa339764b4b7594e2ad39e6bec5460a",
}
MAX_BYTES = 65536
RUNNER = """import subprocess,sys,unittest,os,resource,json
print('CHECK_LIMITS: ' + json.dumps({'affinity': sorted(os.sched_getaffinity(0)),
      'address_space': resource.getrlimit(resource.RLIMIT_AS),
      'cpu_seconds': resource.getrlimit(resource.RLIMIT_CPU),
      'file_bytes': resource.getrlimit(resource.RLIMIT_FSIZE),
      'core_bytes': resource.getrlimit(resource.RLIMIT_CORE)}), file=sys.stderr)
r = subprocess.run(['/usr/bin/python3','-I','-S','-B','/job/report.py','/job/settings.json'],
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
sys.stdout.buffer.write(r.stdout); sys.stderr.buffer.write(r.stderr)
if r.returncode: sys.exit(r.returncode)
if sys.argv[1] == 'verify':
    sys.path.insert(0, '/owner')
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName('test_report'))
    sys.exit(not result.wasSuccessful())
"""


@dataclass(frozen=True)
class Observation:
    command: tuple
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float

    @property
    def accepted(self):
        return (self.returncode == 0 and b"Ran 5 tests" in self.stderr
                and self.stderr.rstrip().endswith(b"OK"))


def stable_read(path):
    """Bounded regular single-link bytes; no symlink in any path component."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("noncanonical artifact path")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or before.st_size > MAX_BYTES):
                raise ValueError("artifact identity/type/size")
            data = bytearray()
            while len(data) <= MAX_BYTES:
                chunk = os.read(fd, min(8192, MAX_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            def identity(item):
                return (item.st_dev, item.st_ino, item.st_uid, item.st_mode,
                        item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if (identity(before) != identity(after) or identity(after) != identity(named)
                    or len(data) != before.st_size or len(data) > MAX_BYTES):
                raise ValueError("artifact changed during snapshot")
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def strict_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    def bad_constant(value):
        raise ValueError("nonfinite JSON value")
    def float_value(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite JSON value")
        return result
    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                       parse_constant=bad_constant, parse_float=float_value)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def checked_settings(data):
    config = strict_json(data)
    if set(config) != {"encoding", "delimiter", "currency", "input", "output"}:
        raise ValueError("settings schema")
    if (config["encoding"] not in ("utf-8", "cp1251")
            or config["delimiter"] not in (",", ";") or config["currency"] != "RUB"
            or config["input"] != "readings.csv" or config["output"] != "report.json"):
        raise ValueError("settings values/path outside fixture")
    return config


def limits():
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(settings, returned_report=None, *, application=None, readings=None):
    """Copies verified bytes into private snapshots before one bounded sandbox.

    returned_report=None is calibration/reproduction only, never owner PASS.
    The parent supplies stable staged files from existing artifact helpers.
    """
    started = time.monotonic()
    try:
        source = stable_read(application or FIXTURE / "input/report.py")
        csv_data = stable_read(readings or FIXTURE / "input/readings.csv")
        golden = stable_read(FIXTURE / "owner/test_report.py")
        for key, data in (("input/report.py", source), ("input/readings.csv", csv_data),
                          ("owner/test_report.py", golden)):
            if hashlib.sha256(data).hexdigest() != PINS[key]:
                raise ValueError("immutable source/input/owner hash mismatch: " + key)
        config = stable_read(settings)
        checked_settings(config)
        report = None if returned_report is None else stable_read(returned_report)
        if report is not None:
            strict_json(report)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        return Observation((), 2, b"", ("FIXTURE_REFUSED: " + str(error) + "\n").encode(),
                           time.monotonic() - started)
    with tempfile.TemporaryDirectory(prefix="frw014-owner-") as temporary:
        root = Path(temporary)
        values = {"report.py": source, "readings.csv": csv_data, "settings.json": config,
                  "test_report.py": golden}
        if report is not None:
            values["returned.json"] = report
        for name, data in values.items():
            p = root / name
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
        command = [
            "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
            "--cap-drop", "ALL", "--clearenv", "--setenv", "PATH", "/usr/bin",
            "--setenv", "HOME", "/tmp", "--setenv", "LANG", "C.UTF-8",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--tmpfs", "/job", "--tmpfs", "/owner", "--tmpfs", "/returned",
        ]
        for source_name, target in (("report.py", "/job/report.py"),
                                    ("readings.csv", "/job/readings.csv"),
                                    ("settings.json", "/job/settings.json"),
                                    ("test_report.py", "/owner/test_report.py")):
            command.extend(("--ro-bind", str(root / source_name), target))
        if report is not None:
            command.extend(("--ro-bind", str(root / "returned.json"), "/returned/report.json"))
        command.extend(("--chdir", "/job", "/usr/bin/python3", "-I", "-S", "-B",
                        "-c", RUNNER, "verify" if report is not None else "reproduce"))
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    timeout=5, check=False, preexec_fn=limits)
            return Observation(tuple(command), result.returncode, result.stdout, result.stderr,
                               time.monotonic() - started)
        except subprocess.TimeoutExpired as error:
            return Observation(tuple(command), 124, (error.stdout or b"")[:MAX_BYTES],
                               (error.stderr or b"")[:MAX_BYTES] + b"\nOWNER_CHECK_TIMEOUT\n",
                               time.monotonic() - started)
        except OSError as error:
            return Observation(tuple(command), 2, b"", ("CHECKER_UNAVAILABLE: " + str(error)).encode(),
                               time.monotonic() - started)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = run(args.settings, args.report)
    print(json.dumps({"accepted": result.accepted, "exit": result.returncode,
                      "elapsed_seconds": result.elapsed_seconds}))
    print(result.stdout.decode("utf-8", errors="replace"), end="")
    print(result.stderr.decode("utf-8", errors="replace"), end="", file=__import__("sys").stderr)
    raise SystemExit(0 if result.accepted else (result.returncode or 1))
