#!/usr/bin/env python3
"""Finite stdlib source helper; exact PID/start identity before its barrier."""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time


def identity(pid):
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        return int(data[data.rfind(")") + 2:].split()[19])
    except FileNotFoundError:
        return None


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--worker", required=True, type=Path)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--seconds", type=int, default=90)
    p.add_argument("--seal-package", action="store_true")
    p.add_argument("--clock-ref", required=True, type=Path,
                   help="Pinned original task clock ref JSON; no hardcoded historical deadline")
    a = p.parse_args()
    assert 1 <= a.seconds <= 120
    a.output.mkdir(parents=True, mode=0o700)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    os.sched_setaffinity(0, cpus)
    # Child inherits soft96/hard384 and raises only its own soft limit to384.
    # This supervisor never raises its soft96; aggregate live AS bounds480MiB.
    resource.setrlimit(resource.RLIMIT_AS, (96 * 1024**2, 384 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (130, 130))
    begin = time.monotonic()
    clock_ref = json.loads(a.clock_ref.read_text())
    clock_bytes = Path(clock_ref['path']).read_bytes()
    assert len(clock_bytes) == clock_ref['bytes'] and hashlib.sha256(clock_bytes).hexdigest() == clock_ref['sha256'], 'original_clock_ref_changed'
    clock = json.loads(clock_bytes)
    accepted = datetime.datetime.fromisoformat(clock['accepted_msk']).timestamp()
    task_hard_epoch = clock.get('hard_epoch', accepted + clock['original_seconds'])
    assert task_hard_epoch <= accepted + clock['original_seconds']
    assert clock['cleanup_seconds'] >= 60 and clock['original_seconds'] > clock['cleanup_seconds']
    deadline = min(begin + a.seconds, begin + task_hard_epoch - time.time() - clock['cleanup_seconds'])
    assert deadline > begin
    stamp = lambda: datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).isoformat()
    supervisor = {"pid": os.getpid(), "start_ticks": identity(os.getpid()), "started_msk": stamp()}
    write(a.output / "SUPERVISOR.json", supervisor)
    log = open(a.output / "worker.log", "xb")
    worker_bytes = a.worker.read_bytes()
    input_bytes = a.input.read_bytes()
    worker_sha = hashlib.sha256(worker_bytes).hexdigest()
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    interpreter = Path(sys.executable).resolve()
    interpreter_sha = hashlib.sha256(interpreter.read_bytes()).hexdigest()
    bootstrap = "import base64,sys;source=base64.b64decode(sys.argv[1]);sys.argv=sys.argv[2:];exec(compile(source,sys.argv[0],'exec'),{'__name__':'__main__','__file__':sys.argv[0]})"
    child = None
    record = {"supervisor": supervisor, "barrier_released": False}
    try:
        child = subprocess.Popen([str(interpreter), "-I", "-B", "-c", bootstrap, base64.b64encode(worker_bytes).decode("ascii"), str(a.worker), str(a.output), str(a.input)],
                                 env={"LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
                                 cwd=a.output, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        start_ticks = identity(child.pid)
        assert start_ticks is not None
        record["worker"] = {"pid": child.pid, "start_ticks": start_ticks,
                            "python": str(interpreter),
                            "python_sha256": interpreter_sha,
                            "worker_sha256": worker_sha}
        write(a.output / "IDENTITY.json", record)
        while not (a.output / "READY.json").exists():
            assert child.poll() is None and time.monotonic() < deadline, "readiness_timeout_or_exit"
            time.sleep(0.01)
        ready = json.loads((a.output / "READY.json").read_text())
        assert ready["pid"] == child.pid and ready["start_ticks"] == start_ticks
        assert identity(child.pid) == start_ticks
        assert ready["address_space_bytes"] <= 384 * 1024**2
        assert len(ready["affinity"]) <= 2
        assert hashlib.sha256(a.worker.read_bytes()).hexdigest() == worker_sha, 'own_worker_changed_before_barrier'
        assert hashlib.sha256(a.input.read_bytes()).hexdigest() == input_sha, 'own_input_changed_before_barrier'
        assert hashlib.sha256(interpreter.read_bytes()).hexdigest() == interpreter_sha, 'own_interpreter_changed_before_barrier'
        assert Path(clock_ref['path']).read_bytes() == clock_bytes, 'original_clock_changed_before_barrier'
        record['exact_verified_worker_buffer_executed'] = True
        record['input_sha256'] = input_sha
        record["ready"] = ready
        record["identity_record_written_before_barrier"] = True
        write(a.output / "IDENTITY.json", record)
        write(a.output / "BARRIER.json", {"pid": child.pid, "start_ticks": start_ticks,
                                         "hard_monotonic": deadline})
        record["barrier_released"] = True
        child.wait(timeout=max(0.01, deadline - time.monotonic()))
        record["exit_code"] = child.returncode
    except BaseException as error:
        record["failure"] = type(error).__name__ + ":" + str(error)
        if child is not None and child.poll() is None and identity(child.pid) == record.get("worker", {}).get("start_ticks"):
            os.kill(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if identity(child.pid) == record["worker"]["start_ticks"]:
                    os.kill(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
        record["exit_code"] = child.returncode if child else None
    finally:
        log.close()
        record.update(ended_msk=stamp(), elapsed_seconds=time.monotonic() - begin,
                      worker_identity_absent=child is None or identity(child.pid) is None,
                      worker_reaped=child is None or child.poll() is not None,
                      exact_owned_only_stop=True,
                      supervisor_final_children=Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").read_text().strip(),
                      declared_aggregate_address_space_bytes=480 * 1024**2,
                      native_runtime_effects=0)
        write(a.output / "CLOSURE.json", record)
    complete = (record.get('exit_code') == 0 and not record.get('failure') and
                record['worker_reaped'] and record['worker_identity_absent'] and
                not record['supervisor_final_children'])
    if a.seal_package and complete:
        package=a.output.parent
        entries={}
        for path in sorted(package.rglob('*')):
            if path.name == 'MANIFEST.json':continue
            name=path.relative_to(package).as_posix()
            if path.is_symlink():entries[name]={'kind':'symlink','target':os.readlink(path)}
            elif path.is_file():
                data=path.read_bytes();entries[name]={'kind':'file','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'final_mode':'0400'}
            elif path.is_dir():entries[name]={'kind':'directory','final_mode':'0500'}
        write(package/'MANIFEST.json',{'schema':'friday.source-gate-package-manifest.v1','entries':entries,
             'manifest_self_excluded':True,'all_helper_closure_records_included':True})
        for path in package.rglob('*'):
            if not path.is_symlink() and path.is_file():path.chmod(0o400)
        for path in sorted((p for p in package.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):path.chmod(0o500)
        package.chmod(0o500)
    print(json.dumps({"exit_code": record["exit_code"], "reaped": record["worker_reaped"],
                      "identity_absent": record["worker_identity_absent"], "failure": record.get("failure")}))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
