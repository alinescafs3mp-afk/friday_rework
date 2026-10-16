"""Run offline native web tests with explicit source paths and private effects."""
import importlib
import json
import os
from pathlib import Path
import runpy
import socket
import stat
import sys
import tempfile


root = Path(os.environ["FRIDAY_TEST_SANDBOX"]).resolve()
native = Path(os.environ["FRIDAY_TEST_NATIVE"]).resolve()
project = Path(os.environ["FRIDAY_TEST_PROJECT"]).resolve()
overlay_value = os.environ.get("FRIDAY_TEST_NATIVE_OVERLAY")
overlay = Path(overlay_value).resolve() if overlay_value else None
root.mkdir(mode=0o700, parents=True, exist_ok=True)
assert root != native and not root.is_relative_to(native)
assert not any(name in sys.modules for name in ("tools", "agent", "hermes_cli", "run_agent"))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
private_paths = {
    "HERMES_HOME": root / "hermes-home",
    "HERMES_RUNTIME_DIR": root / "runtime",
    "HERMES_GATEWAY_LOCK_DIR": root / "locks",
    "XDG_CACHE_HOME": root / "cache",
    "XDG_CONFIG_HOME": root / "config",
    "XDG_DATA_HOME": root / "data",
    "XDG_STATE_HOME": root / "state",
    "XDG_RUNTIME_DIR": root / "xdg-runtime",
    "TMPDIR": root / "tmp",
    "TMP": root / "tmp",
    "TEMP": root / "tmp",
}
for name, value in private_paths.items():
    value.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.environ[name] = str(value)
os_home = root / "os-home"
os_home.mkdir(mode=0o700, exist_ok=True)
Path.home = classmethod(lambda cls: os_home)
tempfile.tempdir = str(private_paths["TMPDIR"])
assert Path.home().resolve().is_relative_to(root)
assert Path(tempfile.gettempdir()).resolve().is_relative_to(root)
assert all(Path(os.environ[name]).resolve().is_relative_to(root) for name in private_paths)


def denied_network(*args, **kwargs):
    raise AssertionError("offline native web test attempted network or DNS")


socket.socket.connect = denied_network
socket.socket.connect_ex = denied_network
socket.create_connection = denied_network
socket.getaddrinfo = denied_network


def check_write(path, *, allow_null_sink=False):
    if isinstance(path, (str, bytes, os.PathLike)):
        candidate = Path(os.fsdecode(path)).resolve()
        if allow_null_sink and candidate == Path(os.devnull):
            info = candidate.stat()
            if stat.S_ISCHR(info.st_mode) and info.st_rdev == os.makedev(1, 3):
                return
        if not candidate.is_relative_to(root):
            with (root / "refused-writes.jsonl").open("a") as handle:
                handle.write(json.dumps({"path": str(candidate), "pid": os.getpid()}) + "\n")
            raise AssertionError("offline native web write outside sandbox: " + str(candidate))


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        denied_network()
    if event == "open":
        path, mode, flags = args
        if (mode and any(flag in mode for flag in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            check_write(path, allow_null_sink=True)
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate", "os.utime"}:
        check_write(args[0])
    elif event in {"os.rename", "os.link", "os.symlink"}:
        check_write(args[0])
        check_write(args[1])
    elif event == "sqlite3.connect" and args[0] != ":memory:":
        check_write(args[0])


sys.addaudithook(audit)
proof = {
    "native_imports_before_isolation": False,
    "path_home": str(Path.home()),
    "tempfile_root": tempfile.gettempdir(),
    "paths": {name: os.environ[name] for name in private_paths},
    "network_dns_denied": True,
    "write_scope": str(root),
    "null_character_sink": "permitted for open only; metadata mutations remain fenced",
    "native": str(native),
    "project": str(project),
    "overlay": str(overlay) if overlay else None,
}
(root / ("isolation-" + str(os.getpid()) + ".json")).write_text(json.dumps(proof, indent=2) + "\n")
if os.environ.get("FRIDAY_TEST_EXTRA_SITE"):
    sys.path.append(os.environ["FRIDAY_TEST_EXTRA_SITE"])
sys.path[:0] = [str(native), str(project)]
if overlay:
    sys.path.insert(0, str(overlay))
for name in ("tools", "plugins", "hermes_cli", "agent", "gateway"):
    package = importlib.import_module(name)
    if overlay and (overlay / name).is_dir():
        package.__path__.insert(0, str(overlay / name))
    if (project / name).is_dir():
        package.__path__.append(str(project / name))
if os.environ.get("FRIDAY_TEST_WRAPPER"):
    sys.executable = os.environ["FRIDAY_TEST_WRAPPER"]
args = sys.argv[1:]
while args and args[0] in ("-B", "-E", "-I", "-s", "-u"):
    args.pop(0)
if args[:1] == ["-c"]:
    sys.argv = ["-c", *args[2:]]
    exec(compile(args[1], "<command>", "exec"), {"__name__": "__main__"})
elif args[:1] == ["-m"]:
    sys.argv = args[1:]
    if args[1] == "pytest":
        sys.argv += ["-p", "no:cacheprovider", "-o", "log_file=" + str(root / "pytest.log")]
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
else:
    sys.argv = args
    runpy.run_path(args[0], run_name="__main__")
