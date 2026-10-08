#!/usr/bin/env python3
"""Prepare or inspect the complete locked Agent Zero source; never run it."""
from __future__ import annotations

import argparse
import ast
import configparser
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
SERVICE_SOURCE = 'scripts/friday-rework-docker.service'
SERVICE_FILES = ('scripts/a0_runtime.py', 'scripts/rootless_docker_launch.py',
                 'plugins/friday_rework/adapters/a0_profile.py',
                 'plugins/friday_rework/adapters/a0_web.py', SERVICE_SOURCE)


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


def service_sources(project_files, *, root=ROOT):
    """One byte inventory for staging, registration and the launch consumer."""
    from scripts.friday_install import require, owned_file, digest
    payload = {}
    for name in SERVICE_FILES:
        require(name in project_files, 'worker_runtime_source_not_pinned')
        data = owned_file(root / name)
        require(digest(data) == project_files[name], 'worker_runtime_source_changed')
        payload[name] = data
    tree = ast.parse(payload['scripts/rootless_docker_launch.py'])
    unit_pin = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'UNIT_SHA256' for t in n.targets)]
    require(unit_pin == [digest(payload[SERVICE_SOURCE])], 'a0_service_launcher_unit_pin_mismatch')
    unit = configparser.ConfigParser(interpolation=None, strict=True)
    unit.optionxform = str
    unit.read_string(payload[SERVICE_SOURCE].decode())
    require(not unit.defaults() and set(unit.sections()) == {'Unit', 'Service', 'Install'},
            'a0_service_template_shape')
    expected = {'Type': 'notify', 'NotifyAccess': 'all', 'Restart': 'no',
                'RuntimeMaxSec': '120s', 'TimeoutStartSec': '45s', 'TimeoutStopSec': '20s',
                'KillMode': 'control-group', 'SendSIGKILL': 'yes', 'Delegate': 'yes',
                'DelegateSubgroup': 'dockerd', 'TasksMax': '2048', 'MemoryHigh': '12G',
                'MemoryMax': '20G', 'CPUQuota': '800%', 'LimitNOFILE': '65535', 'UMask': '0077',
                'ExecStart': '/usr/bin/python3 /home/jericho/jericho/Friday_rework/.runtime/rootless-docker/launch.py'}
    require(dict(unit['Service']) == expected, 'a0_service_native_boundary_changed')
    require(dict(unit['Unit']) == {
        'Description': 'Friday rework dedicated rootless Docker development runtime',
        'Documentation': 'https://docs.docker.com/engine/security/rootless/',
        'Requires': 'dbus.socket', 'After': 'dbus.socket'}
        and dict(unit['Install']) == {'WantedBy': 'default.target'}, 'a0_service_template_changed')
    return payload


def service_required(value):
    """An A0 effect belongs only to an explicitly enabled receiving runtime."""
    runtime = value['product'].get('runtime', {})
    return runtime.get('enabled') is True and ('a0' in runtime or 'a0' in runtime.get('workers', {}))


def service_plan(value, home):
    """Explicit normal-install phase; no native IO or registration while planning."""
    from scripts.friday_install import require, digest, owned_file
    payload = service_sources(value['project_files'])
    from scripts import a0_runtime as runtime
    from scripts import rootless_docker_launch as launcher
    # These remain the existing deployment. No path, endpoint, capacity or
    # source-pin override is accepted from the operational install document.
    required = service_required(value)
    if required:
        from plugins.friday_rework.host_runtime import configured_runtimes
        selected = configured_runtimes(value['product']['runtime'])['a0']
        config = selected['a0']
        require(config['docker']['path'] == str(runtime.DOCKER)
                and digest(owned_file(runtime.DOCKER)) == config['docker']['sha256'],
                'a0_service_docker_pin_changed')
        profile = runtime.profile_module()
        require(config.get('deployment') is not None, 'explicit_a0_service_deployment_required')
        deployment = profile.checked_profile(config['deployment'])
        require(value['product'].get('a0_deployment') == deployment,
                'a0_service_product_deployment_mismatch')
        require(profile.network_endpoints(deployment) == launcher.ENDPOINTS,
                'a0_service_deployment_route_unsupported')
        # This is a ceiling/readiness check, never a fresh per-job clock. The
        # unchanged route consumer must check actual remaining time again.
        require(selected['budget_seconds'] >= 120 + 45 + 20 + 5 + 25,
                'a0_service_job_budget_insufficient')
        for key, path, name in (
            ('runtime', home / 'worker-runtime-source/scripts/a0_runtime.py', 'scripts/a0_runtime.py'),
            ('launcher', runtime.LAUNCHER, 'scripts/rootless_docker_launch.py'),
            ('daemon_unit', launcher.ROOT / 'supervisor' / runtime.DAEMON, SERVICE_SOURCE)):
            require(config[key] == {'path': str(path), 'sha256': digest(payload[name])},
                    'a0_service_config_source_mismatch')
    return {'schema': 'friday.a0.service-install-plan.v1', 'required': required,
            'home': str(home), 'unit': runtime.DAEMON,
            'launcher': str(runtime.LAUNCHER),
            'unit_source': str(launcher.ROOT / 'supervisor' / runtime.DAEMON),
            'registration': str(launcher.INSTALLED_UNIT),
            'source_files': {n: digest(b) for n, b in payload.items()},
            'native_limits': {'runtime_seconds': 120, 'start_seconds': 45, 'stop_seconds': 20},
            'link_argv': ['/usr/bin/systemctl', '--user', '--no-reload', 'link',
                          str(launcher.ROOT / 'supervisor' / runtime.DAEMON)],
            'reload_argv': ['/usr/bin/systemctl', '--user', 'daemon-reload'],
            'whole_user_manager_reload': True, 'enable': False, 'start': False,
            'existing_state_policy': 'REFUSE_RECONCILE_NO_OVERWRITE_NO_ADOPTION',
            'runtime_acceptance': 'NOT_ACCEPTED'}


def service_receipt_checked(value, home, *, original_attempt):
    """Verify shipped/registered bytes and a historical receipt, not live health."""
    from scripts.friday_install import require, owned_file, read_json, digest
    from scripts import rootless_docker_launch as launcher
    plan = service_plan(value, home)
    receipt = read_json(home / 'preparation/a0-service.receipt.json')
    require(receipt.get('schema') == 'friday.a0.service-install-receipt.v1'
            and receipt.get('state') == 'REGISTERED_INACTIVE_NATIVE_START_NOT_RUN'
            and receipt.get('plan') == plan and receipt.get('original_attempt') == original_attempt
            and receipt.get('resume_allowed') is False
            and receipt.get('runtime_acceptance') == 'NOT_ACCEPTED', 'a0_service_receipt_changed')
    require(not (home / 'preparation/a0-service.failure.json').exists()
            and not (home / 'preparation/a0-service.failure.json').is_symlink(),
            'a0_service_attempt_requires_reconciliation')
    for name, data in service_sources(value['project_files']).items():
        require(owned_file(home / 'worker-runtime-source' / name) == data, 'staged_a0_service_source_changed')
    require(digest(owned_file(plan['launcher'])) == plan['source_files']['scripts/rootless_docker_launch.py'],
            'a0_install_published_source_changed')
    launcher.checked_unit_registration()
    return receipt


def install_service(value, home, budget):
    """One original install attempt, under its existing namespace and runtime lock.

    A failed/lost link or whole-user reload acknowledgement is retained; a
    second call cannot replay it. This publishes no request and starts nothing.
    """
    from scripts.friday_install import (require, directory, owned_file, digest,
                                        read_json, publish, partial_claim, MARKER)
    from scripts.dsh_prepare import run, StopUnconfirmed, safe_observation
    from scripts import a0_runtime as runtime
    from scripts import rootless_docker_launch as launcher
    plan = budget.call(service_plan, value, home)
    if not plan['required']:
        return {'state': 'A0_NOT_CONFIGURED_SOURCE_STAGED', 'runtime_acceptance': 'NOT_ACCEPTED'}
    budget.check(reserve=35)
    directory(home)
    claim = read_json(home / MARKER)
    require(claim == partial_claim(claim['input_sha256'], budget), 'fresh_install_claim_required')
    payload = service_sources(value['project_files'])
    stage = home / 'worker-runtime-source'
    for name, data in payload.items():
        require(owned_file(stage / name) == data, 'staged_a0_service_source_changed')
    evidence = home / 'preparation'
    evidence.mkdir(mode=0o700, exist_ok=True); directory(evidence)
    intent = evidence / 'a0-service.intent.json'
    require(not intent.exists() and not intent.is_symlink(), 'a0_service_attempt_requires_reconciliation')
    names = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlPID',
             'InvocationID', 'ControlGroup', 'FragmentPath', 'DropInPaths', 'Restart',
             'KillMode', 'SendSIGKILL', 'DelegateSubgroup', 'MemoryMax', 'TasksMax',
             'CPUQuotaPerSecUSec', 'RuntimeMaxUSec', 'TimeoutStartUSec', 'TimeoutStopUSec')
    def command(argv, phase):
        out, observation = run(argv, runtime.PROJECT, timeout=min(10, budget.check(reserve=1)),
                               deadline=budget.deadline, env=runtime.ENV,
                               log=evidence / ('a0-service-' + phase))
        budget.check()
        return out, safe_observation(observation)
    def observe(phase):
        raw, receipt = command(['/usr/bin/systemctl', '--user', 'show', runtime.DAEMON,
                                '--property=' + ','.join(names)], phase)
        pairs = [line.split('=', 1) for line in raw.splitlines()]
        fields = dict(pairs)
        require(len(pairs) == len(fields) and set(fields) == set(names), 'a0_install_unit_observation_unknown')
        require(fields['Id'] == runtime.DAEMON and fields['ActiveState'] == 'inactive'
                and fields['SubState'] == 'dead' and fields['MainPID'] == fields['ControlPID'] == '0'
                and not fields['InvocationID'] and not fields['ControlGroup']
                and not fields['DropInPaths'], 'active_or_unreconciled_a0_service')
        return fields, receipt
    def quiet_paths():
        boundary = Path(os.path.commonpath((launcher.ROOT, launcher.INSTALLED_UNIT.parent)))
        require(boundary != Path('/'), 'a0_install_directory_boundary_changed')
        for parent in (launcher.ROOT / 'supervisor', launcher.ROOT / 'config', launcher.INSTALLED_UNIT.parent):
            while True:
                launcher.owned_directory(parent)
                if parent == boundary: break
                require(parent.is_relative_to(boundary), 'a0_install_directory_boundary_changed')
                parent = parent.parent
        launcher.checked_source(launcher.ROOT / 'config/daemon.json', launcher.CONFIG_SHA256)
        launcher.checked_source(launcher.ROOT.parent / 'docker-29.8.2/docker-rootless-extras/dockerd-rootless.sh',
                                launcher.SCRIPT_SHA256)
        # Do not infer namespace cessation from an inactive service or PID 0.
        # Any retained state, including child_pid, must first be reconciled by
        # the existing owner. No namespace/process adoption or cleanup here.
        for p in (launcher.REQUEST, launcher.GUARD, launcher.STATE / 'rootlesskit'):
            require(not p.exists() and not p.is_symlink(), 'a0_install_retained_route_or_namespace')
        if launcher.STATE.exists() or launcher.STATE.is_symlink():
            launcher.owned_directory(launcher.STATE)
            require(not any(launcher.STATE.iterdir()), 'a0_install_retained_route_or_namespace')
    def published_sources():
        require(digest(owned_file(runtime.LAUNCHER)) == plan['source_files']['scripts/rootless_docker_launch.py']
                and digest(owned_file(plan['unit_source'])) == plan['source_files'][SERVICE_SOURCE],
                'a0_install_published_source_changed')
    with runtime.Runtime.locked(None):
        quiet_paths()
        before, before_command = observe('before')
        require(before['LoadState'] == 'not-found' and not before['FragmentPath'],
                'existing_a0_service_requires_reconciliation')
        target = launcher.ROOT / 'supervisor' / runtime.DAEMON
        for p in (runtime.LAUNCHER, target, launcher.INSTALLED_UNIT):
            require(not p.exists() and not p.is_symlink(), 'existing_a0_service_source_requires_reconciliation')
        record = {'schema': 'friday.a0.service-install-intent.v1', 'plan': plan,
                  'original_attempt': claim, 'before': before, 'before_command': before_command,
                  'resume_allowed': False, 'cessation': 'NO_START_SUBMITTED'}
        publish(intent, record, budget=budget)
        try:
            def exclusive(path, data):
                budget.check()
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                runtime.sync_dir(path.parent); budget.check()
            quiet_paths()
            current, _ = observe('before-publication')
            require(current == before, 'a0_install_unit_changed_before_publication')
            exclusive(runtime.LAUNCHER, payload['scripts/rootless_docker_launch.py'])
            exclusive(target, payload[SERVICE_SOURCE])
            published_sources()
            quiet_paths()
            current, _ = observe('before-link')
            require(current == before and not launcher.INSTALLED_UNIT.exists()
                    and not launcher.INSTALLED_UNIT.is_symlink(), 'a0_install_registration_changed')
            publish(evidence / 'a0-service.link-intent.json', record, budget=budget)
            _, link = command(plan['link_argv'], 'link')
            launcher.checked_unit_registration()
            published_sources()
            publish(evidence / 'a0-service.link-receipt.json', link, budget=budget)
            quiet_paths()
            publish(evidence / 'a0-service.reload-intent.json', record, budget=budget)
            _, reload = command(plan['reload_argv'], 'reload')
            launcher.checked_unit_registration()
            published_sources()
            after, after_command = observe('after')
            require(after['LoadState'] == 'loaded' and after['FragmentPath'] in (str(target), str(launcher.INSTALLED_UNIT)),
                    'a0_install_registered_unit_unknown')
            expected = {'Restart': 'no', 'KillMode': 'control-group', 'SendSIGKILL': 'yes',
                        'DelegateSubgroup': 'dockerd', 'MemoryMax': str(20 * 1024**3),
                        'TasksMax': '2048', 'CPUQuotaPerSecUSec': '8s'}
            require(all(after[k] == v for k, v in expected.items()), 'a0_install_effective_native_limits_changed')
            from plugins.friday_rework.adapters.a0_native import _duration
            require([_duration(after[k]) for k in ('RuntimeMaxUSec', 'TimeoutStartUSec', 'TimeoutStopUSec')]
                    == [120, 45, 20], 'a0_install_effective_native_limits_changed')
            quiet_paths()
            published_sources()
            result = {**record, 'schema': 'friday.a0.service-install-receipt.v1',
                      'state': 'REGISTERED_INACTIVE_NATIVE_START_NOT_RUN', 'after': after,
                      'link': link, 'reload': reload, 'after_command': after_command,
                      'runtime_acceptance': 'NOT_ACCEPTED'}
            publish(evidence / 'a0-service.receipt.json', result, budget=budget)
            return result
        except BaseException as exc:
            failure = {**record, 'state': 'STOP_UNCONFIRMED_REGISTRATION_REQUIRES_RECONCILIATION',
                       'failure_type': type(exc).__name__, 'resume_allowed': False}
            # Preserve exact uncertain effects even if the original clock ran
            # out. This finite evidence write grants no execution or replay.
            try: publish(evidence / 'a0-service.failure.json', failure)
            except (OSError, ValueError): pass
            raise StopUnconfirmed('STOP_UNCONFIRMED: A0 registration/reload requires reconciliation') from exc


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
