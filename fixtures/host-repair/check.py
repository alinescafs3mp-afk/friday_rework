"""Owner check for the finite add(a, b) fixture; never imports candidate on host."""
import argparse
from dataclasses import dataclass
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import tempfile
import time

FIXTURE = Path(__file__).resolve().parent
INPUT = FIXTURE / "input/calculator.py"
GOLDEN = FIXTURE / "owner/test_calculator.py"
INPUT_SHA = "e1a894022d1a082987b87adecb623438c9e386d86b2b621cff4a5fe7fdf7edc8"
GOLDEN_SHA = "3046b45b0b2c2702ac686ef1e946a6601c67d456a4e49b895566310674b33995"
CORRECTION = b"def add(a, b):\n    return a + b\n"
MAX_BYTES = 65536
WALL_SECONDS = 5
CLEANUP_SECONDS = 0.25
RUNNER = (
    "import sys,unittest; sys.path[:0]=['/owner','/job']; "
    "r=unittest.TextTestRunner(verbosity=2).run("
    "unittest.defaultTestLoader.loadTestsFromName('test_calculator')); "
    "sys.exit(not r.wasSuccessful())"
)


@dataclass(frozen=True)
class Observation:
    args: tuple
    returncode: object
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    artifact_sha256: object = None
    owner_sha256: object = None
    status: str = "refused"
    grammar_checked: bool = False
    cleanup_completed: bool = True
    child_pid: object = None

    @property
    def accepted(self):
        return (self.status == "completed" and self.grammar_checked
                and self.cleanup_completed and self.returncode == 0
                and self.owner_sha256 == GOLDEN_SHA
                and b"Ran 1 test" in self.stderr
                and self.stderr.rstrip().endswith(b"OK"))


def stable_read(path):
    """Bounded, owned single-link regular file; reject every symlink component."""
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("artifact_noncanonical_path")
    path = Path(os.path.abspath(path))  # Do not resolve symlinks.
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
                raise ValueError("artifact_identity_type_size_refused")
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
                raise ValueError("artifact_changed_during_snapshot")
            return bytes(data)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def source_allowed(source):
    """Keep the original grammar; owner assertions decide arithmetic success."""
    try:
        tree = ast.parse(source)
        expected = ast.parse(CORRECTION)
        for operator in (ast.Add(), ast.Sub()):
            for names in (("a", "b"), ("b", "a")):
                value = expected.body[0].body[0].value
                value.op = operator
                value.left.id, value.right.id = names
                if ast.dump(tree) == ast.dump(expected):
                    return True
    except (SyntaxError, ValueError, RecursionError):
        pass
    return False


def limits():
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _process_identity(pid):
    fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return fields[19], fields[0]  # starttime and state, safe for spaces in comm


def _descendants(pid):
    """Finite teardown evidence for this launcher's existing PID subtree."""
    pending, identities = [pid], []
    while pending:
        current = pending.pop()
        try:
            identity, _ = _process_identity(current)
            identities.append((current, identity))
            pending.extend(map(int, Path('/proc', str(current), 'task', str(current),
                                         'children').read_text().split()))
        except FileNotFoundError:
            continue
    return identities


def _ceased(identities):
    for pid, expected in identities:
        try:
            identity, state = _process_identity(pid)
        except FileNotFoundError:
            continue
        if identity == expected and state not in ('Z', 'X'):
            return False
    return True


def _run(candidate, *, grammar_checked):
    started = time.monotonic()
    deadline = started + WALL_SECONDS
    digest = None
    owner_digest = None
    command = ()
    pid = None
    def observation(code, stdout=b"", stderr=b"", status="refused", cleanup=True):
        return Observation(tuple(command), code, stdout, stderr,
                           time.monotonic() - started, digest, owner_digest,
                           status, grammar_checked, cleanup, pid)
    try:
        source = stable_read(candidate)
        digest = hashlib.sha256(source).hexdigest()
        if grammar_checked and not source_allowed(source):
            return observation(2, stderr=b"fixture_source_contract_refused\n")
        golden = stable_read(GOLDEN)
        owner_digest = hashlib.sha256(golden).hexdigest()
        if owner_digest != GOLDEN_SHA:
            return observation(2, stderr=b"fixture_owner_hash_mismatch\n")
        with tempfile.TemporaryDirectory(prefix="frw013-owner-") as temporary:
            root = Path(temporary)
            # Only these owner-held copies are mounted; no second candidate read.
            for name, data in (("calculator.py", source), ("test_calculator.py", golden)):
                fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
            command = [
                "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                "--cap-drop", "ALL", "--clearenv", "--setenv", "PATH", "/usr/bin",
                "--setenv", "HOME", "/tmp", "--setenv", "LANG", "C.UTF-8",
                "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
                "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                "--tmpfs", "/job", "--tmpfs", "/owner",
                "--ro-bind", str(root / "calculator.py"), "/job/calculator.py",
                "--ro-bind", str(root / "test_calculator.py"), "/owner/test_calculator.py",
                "--chdir", "/job", "/usr/bin/python3", "-I", "-S", "-B", "-c", RUNNER,
            ]
            # Regular files enforce RLIMIT_FSIZE. Pipes/capture_output alone do not.
            with tempfile.TemporaryFile(dir=root) as out, tempfile.TemporaryFile(dir=root) as err:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=err, preexec_fn=limits,
                                           start_new_session=True)
                pid = process.pid
                status = "completed"
                cleanup = False
                try:
                    try:
                        process.wait(timeout=max(0, deadline - time.monotonic() - CLEANUP_SECONDS))
                    except subprocess.TimeoutExpired:
                        status = "timeout"
                    except (OSError, subprocess.SubprocessError):
                        status = "execution_error"
                finally:
                    # Every exit after spawn, including wait errors/interruption,
                    # stops and reaps the launcher within the same 5s budget.
                    identities = []
                    observed = True
                    if process.returncode is None:
                        try:
                            identities = _descendants(process.pid)
                        except (OSError, ValueError, IndexError):
                            observed = False
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except OSError:
                            pass
                        try:
                            process.wait(timeout=max(0, deadline - time.monotonic()))
                        except (OSError, subprocess.SubprocessError):
                            pass
                    try:
                        while not _ceased(identities) and time.monotonic() < deadline:
                            time.sleep(0.001)
                        cleanup = (observed and process.returncode is not None
                                   and _ceased(identities))
                    except (OSError, ValueError, IndexError):
                        cleanup = False
                out.seek(0)
                err.seek(0)
                stdout, stderr = out.read(MAX_BYTES), err.read(MAX_BYTES)
                if status == "completed" and (len(stdout) >= MAX_BYTES or len(stderr) >= MAX_BYTES):
                    status = "output_limit"
                if not cleanup:
                    status = "cleanup_unconfirmed"
                # Recheck both immutable owner source and actual mounted copies.
                try:
                    intact = (stable_read(GOLDEN) == golden
                              and stable_read(root / "test_calculator.py") == golden
                              and stable_read(root / "calculator.py") == source)
                except (OSError, ValueError):
                    intact = False
                if not intact:
                    status = "snapshot_changed"
                return observation(process.returncode, stdout, stderr, status, cleanup)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        # Never include candidate path/source or a Python exception repr in refusal.
        return observation(None if pid is None else 2,
                           stderr=b"fixture_read_or_execution_refused\n")


def isolated_check(candidate):
    """Owner acceptance: bounded snapshot, exact source grammar and real unittest."""
    return _run(candidate, grammar_checked=True)


def _isolated_unittest(candidate):
    """Isolation probe compatibility only; bypassing grammar never yields accepted."""
    return _run(candidate, grammar_checked=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", help="one staged calculator.py file")
    args = parser.parse_args(argv)
    result = isolated_check(args.candidate)
    print(json.dumps({
        "accepted": result.accepted, "returncode": result.returncode,
        "executed": result.child_pid is not None,
        "child_returncode": result.returncode if result.child_pid is not None else None,
        "status": result.status, "elapsed_seconds": result.elapsed_seconds,
        "artifact_sha256": result.artifact_sha256, "owner_sha256": result.owner_sha256,
        "stdout": result.stdout.decode("utf-8", errors="replace"),
        "stderr": result.stderr.decode("utf-8", errors="replace"),
        "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(result.stderr).decode("ascii"),
        "cleanup_completed": result.cleanup_completed,
    }, sort_keys=True))
    return 0 if result.accepted else (124 if result.status == "timeout" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
