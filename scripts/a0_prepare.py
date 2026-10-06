#!/usr/bin/env python3
"""Prepare or inspect the complete locked Agent Zero source; never run it."""
from __future__ import annotations

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
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent.parent if ROOT.parent.name == ".worktrees" else ROOT
UPSTREAM = "https://github.com/agent0ai/agent-zero.git"


class Refusal(RuntimeError):
    pass


def git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return env


def git(path, *args, timeout=30):
    command = ["git", "--no-optional-locks", "-c", "core.hooksPath=" + os.devnull,
               "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
               "-c", "submodule.recurse=false", "-c", "pack.threads=4",
               "-C", str(path), *args]
    try:
        process = subprocess.Popen(command, env=git_env(), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        raise Refusal(f"git operation unavailable: {args[0]}") from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Terminate only this owned Git process group, including fetch helpers.
        for sig, grace in ((signal.SIGTERM, 2), (signal.SIGKILL, 5)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
        else:
            raise Refusal(f"STOP_UNCONFIRMED: timed-out git {args[0]}") from exc
        raise Refusal(f"git operation timed out: {args[0]}; owned group stopped") from exc
    if process.returncode:
        raise Refusal(f"git {args[0]} failed ({process.returncode}): "
                      + stderr.decode(errors="replace").strip()[:500])
    return stdout


def read_lock(path):
    raw = path.read_bytes()
    try:
        records = [r for r in json.loads(raw)["repositories"] if r["id"] == "a0"]
    except (KeyError, TypeError, ValueError) as exc:
        raise Refusal("invalid source lock") from exc
    if len(records) != 1:
        raise Refusal("source lock must contain exactly one a0 record")
    pin = records[0]
    if pin.get("clone_url") != UPSTREAM or pin.get("repo") != "agent0ai/agent-zero":
        raise Refusal("A0 upstream identity mismatch")
    if any(not isinstance(pin.get(k), str) or not re.fullmatch(r"[0-9a-f]{40}", pin[k])
           for k in ("commit", "tree")):
        raise Refusal("invalid commit/tree pin")
    return pin, hashlib.sha256(raw).hexdigest()


def check_checkout(path, pin):
    """Check HEAD, index and each tracked byte/mode, even assume-unchanged files."""
    if path.is_symlink() or not path.is_dir() or not (path / ".git").is_dir():
        raise Refusal("checkout must be a standalone directory with its own .git")
    for name in ("index.lock", "HEAD.lock", "config.lock", "shallow.lock"):
        if (path / ".git" / name).exists():
            raise Refusal("competing writer: " + name + " exists")
    top = git(path, "rev-parse", "--show-toplevel").decode().strip()
    if Path(top).resolve() != path.resolve():
        raise Refusal("checkout boundary mismatch")
    origin = git(path, "remote", "get-url", "origin").decode().strip()
    if origin != pin["clone_url"]:
        raise Refusal("checkout origin mismatch")
    head = git(path, "rev-parse", "HEAD").decode().strip()
    tree = git(path, "rev-parse", "HEAD^{tree}").decode().strip()
    if head != pin["commit"] or tree != pin["tree"]:
        raise Refusal(f"checkout pin mismatch: HEAD={head} tree={tree}")
    entries = []
    for record in git(path, "ls-tree", "-rz", "--full-tree", "HEAD").split(b"\0"):
        if not record:
            continue
        identity, name = record.split(b"\t", 1)
        mode, kind, blob = identity.decode().split()
        rel = os.fsdecode(name)
        if kind != "blob" or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise Refusal("unsupported tracked entry: " + rel)
        entries.append((mode, blob, rel))
    index = []
    for record in git(path, "ls-files", "--stage", "-z").split(b"\0"):
        if record:
            identity, name = record.split(b"\t", 1)
            mode, blob, stage = identity.decode().split()
            if stage != "0":
                raise Refusal("unmerged source index")
            index.append((mode, blob, os.fsdecode(name)))
    if sorted(index) != sorted(entries):
        raise Refusal("dirty tracked source index")
    files, directories = [], set()
    for mode, blob, rel in entries:
        item = path / rel
        try:
            for parent in Path(rel).parents:
                if parent != Path(".") and parent not in directories:
                    if not stat.S_ISDIR((path / parent).lstat().st_mode):
                        raise Refusal("dirty tracked source directory: " + str(parent))
                    directories.add(parent)
            info = item.lstat()
            if mode == "120000" and stat.S_ISLNK(info.st_mode):
                raw = os.fsencode(os.readlink(item))
            elif mode in ("100644", "100755") and stat.S_ISREG(info.st_mode):
                if bool(info.st_mode & 0o111) != (mode == "100755"):
                    raise Refusal("dirty tracked source mode: " + rel)
                raw = item.read_bytes()
            else:
                raise Refusal("dirty tracked source type: " + rel)
        except OSError as exc:
            raise Refusal("missing/unreadable tracked source: " + rel) from exc
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != blob:
            raise Refusal("dirty tracked source bytes: " + rel)
        files.append({"path": rel, "mode": mode, "blob": blob,
                      "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    if git(path, "ls-files", "--others", "--exclude-standard", "-z"):
        raise Refusal("untracked source files present")
    return {"commit": head, "tree": tree, "origin": origin,
            "tracked_files": len(files), "tracked_bytes_modes_and_index": "PASS"}, files


def prepare(path, pin):
    if path.exists() or path.is_symlink():
        # Never reset, repair, clean, fetch or overwrite an existing checkout.
        return check_checkout(path, pin)
    path.mkdir(parents=True)
    git(path, "init", "--template=")
    git(path, "remote", "add", "origin", pin["clone_url"])
    git(path, "fetch", "--depth=1", "--no-tags", "origin", pin["commit"], timeout=180)
    # Verify the fetched identity before materializing any tracked files.
    head = git(path, "rev-parse", "FETCH_HEAD").decode().strip()
    tree = git(path, "rev-parse", "FETCH_HEAD^{tree}").decode().strip()
    if head != pin["commit"] or tree != pin["tree"]:
        raise Refusal("fetched pin mismatch; no checkout performed")
    git(path, "checkout", "--detach", pin["commit"], timeout=60)
    return check_checkout(path, pin)


def inventory(path, pin, source_lock_sha, source, files):
    notices, dependencies, container = [], [], []
    for item in files:
        name = Path(item["path"]).name.lower()
        if name.startswith(("license", "notice", "copying")):
            notices.append(item)
        if (name.startswith("requirements") and name.endswith(".txt")) or name in {
            "pyproject.toml", "uv.lock", "poetry.lock", "pdm.lock", "pipfile.lock",
            "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"
        }:
            dependencies.append(item)
        if name.startswith("dockerfile") or item["path"].startswith("docker/"):
            container.append(item)
    if not any(i["path"] == "LICENSE" for i in notices):
        raise Refusal("missing root license")
    git_version = git(path, "--version").decode().strip()
    docker = shutil.which("docker")
    image_refs = [
        {"path": item["path"], "from": match.group(1).strip()}
        for item in container if Path(item["path"]).name.lower().startswith("dockerfile")
        for match in re.finditer(r"^FROM\s+(.+)$", (path / item["path"]).read_text(), re.MULTILINE)
    ]
    python_locks = [item for item in dependencies if "/" not in item["path"] and
                    item["path"].lower() in {"uv.lock", "poetry.lock", "pdm.lock", "pipfile.lock"}]
    return {
        "schema_version": 1, "donor": "a0",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "checkout": str(path.resolve()), "source": source,
        "source_lock_sha256": source_lock_sha,
        "source_commit_url": pin.get("commit_url"),
        "notices": notices, "dependency_declarations": dependencies,
        "python_lock_declarations": python_locks, "dependency_resolution": "NOT_RUN",
        "container_sources": container,
        "container_image_references": image_refs,
        "host_toolchain": {"git": git_version, "python": sys.version.split()[0],
                           "docker_cli": docker, "docker_daemon": "NOT_QUERIED"},
        "runtime": {"startup": "NOT_RUN", "image_digest": None,
                    "model_route": "NOT_CONFIGURED", "acceptance": "NOT_RUN"},
        "prerequisite_gaps": [
            *( ["Docker CLI unavailable on PATH"] if docker is None else [] ),
            "Dedicated supported container environment, image build/digest and supervisor not verified",
            *( ["No root Python resolved lock found; requirements include ranges"] if not python_locks else [] ),
            *( ["Container base image references lack an immutable digest"]
               if any("@sha256:" not in item["from"] for item in image_refs) else [] ),
            "Local model/plugin configuration and API credentials not configured or tested"
        ],
        "effects": "source fetch/checkout only when absent; existing checkout checks read-only"
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check"))
    parser.add_argument("--lock", type=Path, default=ROOT / "sources.lock.json")
    parser.add_argument("--checkout", type=Path, default=PROJECT / ".donors" / "a0")
    parser.add_argument("--output", type=Path, help="optional private JSON evidence path")
    args = parser.parse_args(argv)
    try:
        pin, lock_sha = read_lock(args.lock)
        source, files = (prepare if args.command == "prepare" else check_checkout)(args.checkout, pin)
        manifest = inventory(args.checkout, pin, lock_sha, source, files)
        rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            # Exclusive write: an existing report is never silently replaced.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                target.write(rendered)
        else:
            print(rendered, end="")
        return 0
    except (Refusal, OSError) as exc:
        print("REFUSED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
