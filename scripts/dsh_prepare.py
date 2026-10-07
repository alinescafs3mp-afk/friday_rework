#!/usr/bin/env python3
"""Prepare the complete locked Harness donor without changing its sources."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time


class StopUnconfirmed(RuntimeError):
    """An owned command was signalled but its cessation was not observed."""


class CommandFailed(RuntimeError):
    """Reaped command failure; never carry argv, environment or raw output."""

    def __init__(self, observation):
        keys = ('returncode', 'elapsed_seconds', 'timeout', 'stdout_sha256',
                'stderr_sha256', 'stdout_bytes', 'stderr_bytes', 'pid',
                'starttime_ticks', 'reaped', 'reason')
        self.observation = {k: observation[k] for k in keys}
        super().__init__('command_timeout' if observation['timeout'] else 'command_nonzero_exit')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean_environment(donor):
    # Build tools retain the user's actual home, but receive no model/Telegram keys.
    allowed = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM",
               "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               COREPACK_ENABLE_DOWNLOAD_PROMPT="0",
               COREPACK_HOME=str(donor / ".git/friday-corepack"),
               npm_config_cache=str(donor / ".git/friday-npm-cache"),
               npm_config_child_concurrency="4", npm_config_network_concurrency="8",
               DSH_TELEMETRY_DISABLED="1", DSH_HOME=str(donor / ".git/friday-smoke-home"))
    return env


def run(argv, donor, *, timeout=60, log=None, env=None, deadline=None, pass_fds=()):
    """Bound one group; callers needing detached-tree custody use a PID namespace."""
    if argv[0] == "git":
        argv = ["git", "-c", "core.hooksPath=" + os.devnull,
                "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
                "-c", "pack.threads=4", *argv[1:]]
    start = time.monotonic()
    process = subprocess.Popen(argv, cwd=donor, env=env or clean_environment(donor),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True, pass_fds=pass_fds)
    try:
        starttime = int(Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        starttime = None
    timed_out = False
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if deadline is not None:
            # Installer namespace cleanup consumes the same original budget.
            # Kill namespace owner immediately; Linux closes all descendant
            # sessions when its PID-namespace init dies (including setsid).
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StopUnconfirmed('STOP_UNCONFIRMED: original cleanup budget exhausted')
            try:
                out, err = process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise StopUnconfirmed('STOP_UNCONFIRMED: contained command not reaped') from exc
        else:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                out, err = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                out, err = process.communicate(timeout=5)
    reason = ('device_null_unavailable' if
              "fatal: could not open '/dev/null' for reading and writing: Permission denied" in err
              else 'command_timeout' if timed_out else 'command_nonzero_exit' if process.returncode else 'command_succeeded')
    source_reasons = {'git_source_operation_failed': 'source_git_operation_failed',
                      'source_preparation_deadline': 'source_preparation_deadline',
                      'source_input_or_io_failed': 'source_input_or_io_failed',
                      'fresh_destination_required': 'source_destination_exists',
                      'dirty_donor_refused': 'source_donor_changed',
                      'donor_identity_changed': 'source_donor_changed',
                      'overlay_hash_mismatch': 'source_overlay_changed'}
    for code, stable in source_reasons.items():
        if err.strip() == 'FRIDAY_SOURCE_REFUSED reason=' + code:
            reason = stable
            break
    observation = {"argv": argv, "returncode": process.returncode,
                   "elapsed_seconds": round(time.monotonic() - start, 3),
                   "timeout": timed_out, "stdout_sha256": hashlib.sha256(out.encode()).hexdigest(),
                   "stderr_sha256": hashlib.sha256(err.encode()).hexdigest(),
                   "stdout_bytes": len(out.encode()), "stderr_bytes": len(err.encode()),
                   "pid": process.pid, "starttime_ticks": starttime,
                   "reaped": process.returncode is not None, "reason": reason}
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.with_suffix(".stdout").write_text(out)
        log.with_suffix(".stderr").write_text(err)
        log.with_suffix(".json").write_text(json.dumps(observation, indent=2) + "\n")
    if timed_out or process.returncode:
        raise CommandFailed(observation)
    return out.strip(), observation


def locked_source(lock):
    rows = [row for row in json.loads(lock.read_text())["repositories"] if row["id"] == "dsh"]
    if len(rows) != 1:
        raise ValueError("Expected exactly one locked Harness donor")
    source = rows[0]
    if (source["clone_url"] != "https://github.com/deepseek-ai/deepseek-harness.git"
            or source["repo"] != "deepseek-ai/deepseek-harness"):
        raise ValueError("Unexpected Harness upstream")
    for key in ("commit", "tree"):
        if not re.fullmatch(r"[0-9a-f]{40}", source[key]):
            raise ValueError(f"Invalid locked {key}")
    return source


def verify_source(donor, source):
    if donor.is_symlink() or (donor / ".git").is_symlink() or not (donor / ".git").is_dir():
        raise ValueError("An independent, non-symlink donor checkout is required")
    for name in ("index.lock", "HEAD.lock", "config.lock", "shallow.lock"):
        if (donor / ".git" / name).exists():
            raise ValueError(f"Competing donor writer: {name}")
    def git(*args):
        return run(["git", "--no-optional-locks", *args], donor)[0]
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    if (head, tree) != (source["commit"], source["tree"]):
        raise ValueError(f"Wrong donor identity: {head} {tree}")
    if git("status", "--porcelain=v1", "--untracked-files=no"):
        raise ValueError("Donor tracked source/index is dirty; refusing changes")
    if git("remote", "get-url", "origin") != source["clone_url"]:
        raise ValueError("Wrong donor origin")
    if git("branch", "--show-current"):
        raise ValueError("Expected detached pinned checkout")
    expected = {}
    for row in git("ls-tree", "-r", "-z", "HEAD").split("\0"):
        if row:
            header, name = row.split("\t", 1)
            mode, kind, blob = header.split()
            if kind != "blob":
                raise ValueError("Submodule preparation requires an explicit recursive pin")
            expected[name] = (mode, blob)
    index = {}
    for row in git("ls-files", "--stage", "-z").split("\0"):
        if row:
            header, name = row.split("\t", 1)
            mode, blob, stage = header.split()
            if stage != "0":
                raise ValueError("Unmerged donor index")
            index[name] = (mode, blob)
    if index != expected:
        raise ValueError("Donor index differs from pinned HEAD")
    if git("ls-files", "--others", "--exclude-standard", "-z"):
        raise ValueError("Unexpected untracked donor source; refusing build/startup")
    # Dotenv files are commonly ignored, but the native launcher loads them.
    for path in donor.glob(".env*"):
        if path.name not in expected:
            raise ValueError("Unexpected donor-root environment file; refusing build/startup")
    crlf_paths = []
    for name, (mode, blob) in expected.items():
        path = donor / name
        if path.parent != path.parent.resolve():
            raise ValueError(f"Symlinked source parent: {name}")
        info = path.lstat()
        if mode == "120000" and stat.S_ISLNK(info.st_mode):
            data = os.fsencode(os.readlink(path))
        elif mode in ("100644", "100755") and stat.S_ISREG(info.st_mode):
            if bool(info.st_mode & stat.S_IXUSR) != (mode == "100755"):
                raise ValueError(f"Wrong source executable mode: {name}")
            data = path.read_bytes()
        else:
            raise ValueError(f"Wrong source file type: {name}")
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != blob:
            # Upstream explicitly checks Windows .cmd files out with CRLF.
            # Apply only that declared conversion, never arbitrary clean filters.
            attr = git("check-attr", "-z", "eol", "--", name).split("\0")
            canonical = data.replace(b"\r\n", b"\n")
            canonical_blob = hashlib.sha1(b"blob " + str(len(canonical)).encode() + b"\0" + canonical).hexdigest()
            if (mode == "120000" or attr[:3] != [name, "eol", "crlf"]
                    or b"\n" in data.replace(b"\r\n", b"") or canonical_blob != blob):
                raise ValueError(f"Source blob differs from pin: {name}")
            crlf_paths.append(name)
    return {"commit": head, "tree": tree, "tracked_clean": True,
            "tracked_blob_and_git_mode_count": len(expected), "index_matches_head": True,
            "unexpected_source_and_root_env_refused": True,
            "upstream_declared_crlf_checkout_paths": crlf_paths,
            "source_lock_sha256": None,
            "notices": {name: digest(donor / name) for name in ("LICENSE", "THIRD_PARTY_NOTICES.md")},
            "dependency_locks": {"pnpm-lock.yaml": digest(donor / "pnpm-lock.yaml")}}


def node_supported(version):
    numbers = tuple(int(x) for x in version.lstrip("v").split(".")[:3])
    return (numbers[0] == 22 and numbers >= (22, 19, 0)) or numbers[0] >= 24


def toolchain(donor, *, download=False):
    package = json.loads((donor / "package.json").read_text())
    manager = package["packageManager"]
    if not re.fullmatch(r"pnpm@\d+\.\d+\.\d+", manager):
        raise ValueError("Expected exact upstream pnpm version")
    node, _ = run(["node", "--version"], donor)
    if not node_supported(node):
        raise ValueError(f"Unsupported Node {node}; upstream requires {package['engines']['node']}")
    executable, _ = run(["node", "-p", "process.execPath"], donor)
    headers = Path(executable).parent.parent / "include/node/node_api.h"
    result = {"node": node, "node_executable": executable, "node_sha256": digest(executable),
              "node_api_headers": str(headers), "node_api_headers_available": headers.is_file(),
              "declared_node_engine": package["engines"]["node"], "package_manager": manager,
              "corepack": shutil.which("corepack"), "cc": shutil.which("cc"),
              "python3": shutil.which("python3"), "make": shutil.which("make")}
    if download:
        actual, _ = run(["corepack", "pnpm", "--version"], donor, timeout=180)
        if actual != manager.split("@", 1)[1]:
            raise ValueError(f"Wrong pnpm executable: {actual}")
        result["observed_pnpm"] = actual
    return result


def build_inventory(donor):
    files = []
    # Source-backed Node launch resolves workspace lib output; keep that identity together.
    dirs = list(donor.glob("apps/*/lib")) + list(donor.glob("packages/*/*/lib")) + list(donor.glob("vendor/*/lib"))
    for directory in dirs:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.is_symlink():
                files.append([str(path.relative_to(donor)), digest(path)])
    for path in sorted((donor / "native/system/packages").rglob("*.node")):
        files.append([str(path.relative_to(donor)), digest(path)])
    files.sort()
    return {"file_count": len(files), "sha256": hashlib.sha256(json.dumps(files, separators=(",", ":")).encode()).hexdigest(),
            "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("source", "check", "toolchain", "build", "smoke"))
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "sources.lock.json")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--build-timeout", type=int, default=900)
    args = parser.parse_args()
    donor = args.donor.absolute()
    if donor != donor.resolve():
        raise ValueError("Refusing symlinked donor path or parent")
    source = locked_source(args.lock)
    if args.action == "source" and not donor.exists():
        donor.mkdir(mode=0o700, parents=False)
        run(["git", "init", "--quiet"], donor)
        run(["git", "remote", "add", "origin", source["clone_url"]], donor)
        run(["git", "fetch", "--depth=1", "origin", source["commit"]], donor, timeout=180)
        run(["git", "checkout", "--detach", source["commit"]], donor)
    identity = verify_source(donor, source)
    identity["source_lock_sha256"] = digest(args.lock)
    result = {"donor": str(donor), "source": identity, "toolchain": toolchain(donor, download=args.action in ("toolchain", "build")),
              "runtime_task": "NOT_RUN", "inference": "NOT_RUN", "telemetry_disabled": True}
    evidence = args.evidence.absolute()
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.action == "build":
        if not result["toolchain"]["node_api_headers_available"] or not result["toolchain"]["cc"]:
            raise RuntimeError("Native build prerequisite missing: Node development headers and cc are required")
        result["install"] = run(["corepack", "pnpm", "install", "--frozen-lockfile", "--store-dir", str(donor / ".git/friday-pnpm-store")],
                                donor, timeout=900, log=evidence / "dsh-install")[1]
        result["build"] = run(["corepack", "pnpm", "run", "build"], donor,
                              timeout=args.build_timeout, log=evidence / "dsh-build")[1]
        verify_source(donor, source)
    cli = donor / "apps/cli/lib/bin.js"
    if args.action == "smoke":
        if not cli.is_file():
            raise RuntimeError("Built source CLI missing; run build first")
        result["smoke"] = []
        for label, flags in (("version", ["--version"]), ("help", ["--help"]),
                             ("headless-config", ["--profile", "headless", "--dump-default-config"]),
                             ("headless-help", ["--profile", "headless", "--help"])):
            output, observation = run(["node", str(cli), *flags], donor, log=evidence / ("dsh-" + label))
            if label == "version" and json.loads((donor / "package.json").read_text())["version"] not in output:
                raise ValueError("CLI version does not match source package")
            result["smoke"].append({"kind": label, **observation})
        result["startup_scope"] = "Native entrypoint, headless composition and profile help; no agent/session/model run"
    if cli.is_file():
        result["cli"] = {"path": str(cli), "sha256": digest(cli)}
        inventory = build_inventory(donor)
        (evidence / "dsh-build-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
        result["workspace_build_identity"] = {key: inventory[key] for key in ("file_count", "sha256")}
    (evidence / ("dsh-" + args.action + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"action": args.action, "source": identity, "toolchain": result["toolchain"], "cli": result.get("cli")}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
