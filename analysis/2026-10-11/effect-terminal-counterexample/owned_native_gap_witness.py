"""Bounded OWNED-only witness against Post/command-exit-only release.

Two direct owned Python children model a completed command and a retained
asynchronous callback; the callback is not mislabeled an OS descendant. Its
effect is the newly captured exact actual NativeControl.call AST, with the
native WebSocket replaced solely by an owned file sentinel. No installed
runtime script is imported and no native connection is made.
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import stat
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
AS_LIMIT = 768 * 1024 * 1024


def configure() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])


def identity(pid: int) -> tuple[int, int]:
    raw = Path(f"/proc/{pid}/stat").read_text()
    return pid, int(raw[raw.rfind(")") + 2:].split()[19])


def read_bounded(stream, seconds=5):
    ready, _, _ = select.select([stream], [], [], seconds)
    if not ready:
        raise RuntimeError("Owned fixture handshake exceeded deadline")
    line = stream.readline(4097)
    if not line or len(line) > 4096:
        raise RuntimeError("Missing/big owned fixture handshake")
    return json.loads(line)


def callback_worker():
    configure()
    raw = (BASE / "captured/native_control.py").read_bytes()
    tree = ast.parse(raw)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "NativeControl")
    node = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == "call")
    selected_hash = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {"asyncio": asyncio, "json": json}
    exec(compile(ast.fix_missing_locations(module), "OWNED_exact_actual_NativeControl.call", "exec"), namespace)
    loaded_hash = hashlib.sha256(raw).hexdigest()
    print(json.dumps({"pid_start": identity(os.getpid()), "loaded_sha256": loaded_hash,
                      "actual_call_AST_sha256": selected_hash}), flush=True)
    ready, _, _ = select.select([sys.stdin], [], [], 5)
    if not ready or sys.stdin.readline().strip() != "EFFECT":
        raise RuntimeError("Owned callback gate expired")

    class SentinelSocket:
        async def send(self, value):
            payload = json.loads(value)
            assert payload["method"] == "thread/queue/start"
            (BASE / "owned/effect.json").write_text(json.dumps({
                "terminal": "INERT_OWNED_FILE_SENTINEL_NO_NATIVE_RPC",
                "method": payload["method"], "loaded_sha256": loaded_hash,
                "disk_sha256_at_effect": hashlib.sha256((BASE / "owned/control.py").read_bytes()).hexdigest(),
                "pid_start": identity(os.getpid())}, sort_keys=True) + "\n")

        async def recv(self):
            return json.dumps({"id": 1, "result": {"OWNED": True}})

    class SelectedObject:
        thread = "OWNED_THREAD"
        sequence = 0
        ws = SentinelSocket()

    result = asyncio.run(namespace["call"](SelectedObject(), "thread/queue/start",
                                          {"threadId": "OWNED_THREAD"}))
    assert result == {"OWNED": True}
    print(json.dumps({"callback_returned": True}), flush=True)


def command_worker():
    configure()
    # The command requests an async callback from the owned broker, then exits.
    print(json.dumps({"ordinary_async_request": "OWNED_CALLBACK"}), flush=True)


def schema_object_valid(value, spec, definitions):
    if "$ref" in spec:
        return schema_object_valid(value, definitions[spec["$ref"].split("/")[-1]], definitions)
    if "allOf" in spec:
        return all(schema_object_valid(value, s, definitions) for s in spec["allOf"])
    if "oneOf" in spec:
        return sum(schema_object_valid(value, s, definitions) for s in spec["oneOf"]) == 1
    if "enum" in spec and value not in spec["enum"]:
        return False
    kind = spec.get("type")
    if isinstance(kind, list):
        return any(schema_object_valid(value, {**spec, "type": k}, definitions) for k in kind)
    if kind == "null":
        return value is None
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list) and all(schema_object_valid(v, spec.get("items", {}), definitions) for v in value)
    if kind == "object":
        if not isinstance(value, dict) or any(k not in value for k in spec.get("required", [])):
            return False
        return all(schema_object_valid(v, spec["properties"][k], definitions)
                   for k, v in value.items() if k in spec.get("properties", {}))
    return True


def run():
    configure()
    sys.path.insert(0, str(BASE))
    from prospective_terminal_gate import Reservation, loaded_identity_is_current, production_release_status
    before = {"fd": len(os.listdir("/proc/self/fd")), "threads": len(os.listdir("/proc/self/task")),
              "pid_start": identity(os.getpid()), "children": Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").read_text()}
    owned = BASE / "owned"
    owned.mkdir(mode=0o700, exist_ok=False)
    raw = (BASE / "captured/native_control.py").read_bytes()
    control = owned / "control.py"
    control.write_bytes(raw)
    loaded_hash = hashlib.sha256(raw).hexdigest()
    children = []
    observations = {}
    try:
        command = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__)), "command"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        command_identity = identity(command.pid)
        children.append((command, command_identity))
        request = read_bounded(command.stdout)
        assert request == {"ordinary_async_request": "OWNED_CALLBACK"}
        callback = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__)), "callback"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
        callback_identity = identity(callback.pid)
        children.append((callback, callback_identity))
        ready = read_bounded(callback.stdout)
        assert tuple(ready["pid_start"]) == callback_identity
        assert ready["loaded_sha256"] == loaded_hash
        command_exit = command.wait(timeout=5)
        assert command_exit == 0
        assert identity(callback.pid) == callback_identity
        pending = Reservation("OWNED_TOOL_USE", {"native_control": loaded_hash},
                              retained_callbacks={callback_identity})
        pending.permission_returned()
        pending.observe_post("OWNED_TOOL_USE")
        pending.observe_command_exit()

        hooks_schema = json.loads((BASE / "pinned-schema/HookCompletedNotification.json").read_text())
        item_schema = json.loads((BASE / "pinned-schema/ItemCompletedNotification.json").read_text())
        hook = {"threadId": "OWNED_THREAD", "turnId": "OWNED_TURN", "run": {
            "id": "OWNED_HOOK_RUN_NOT_TOOL_ID", "eventName": "postToolUse", "executionMode": "sync",
            "handlerType": "command", "scope": "turn", "sourcePath": "/OWNED/hook.py",
            "startedAt": 1, "completedAt": 2, "status": "completed", "displayOrder": 0, "entries": []}}
        command_variant = next(v for v in item_schema["definitions"]["ThreadItem"]["oneOf"]
                               if v.get("title") == "CommandExecutionThreadItem")
        item = {"type": "commandExecution", "id": "OWNED_ITEM", "command": "OWNED Python async request",
                "commandActions": [], "cwd": str(owned), "status": "completed", "exitCode": 0,
                "durationMs": 1, "processId": None}
        assert schema_object_valid(hook, hooks_schema, hooks_schema["definitions"])
        assert schema_object_valid(item, command_variant, item_schema["definitions"])
        assert pending.unsafe_post_only_release() and not pending.safe_owned_release()
        old_disk = control.read_bytes()
        control.write_bytes(old_disk + b"\n# OWNED prospective changed epoch\n")
        assert not loaded_identity_is_current(pending.source_identity, {"native_control": control})
        callback.stdin.write("EFFECT\n")
        callback.stdin.flush()
        returned = read_bounded(callback.stdout)
        assert returned == {"callback_returned": True}
        callback_exit = callback.wait(timeout=5)
        assert callback_exit == 0
        effect = json.loads((owned / "effect.json").read_text())
        assert effect["loaded_sha256"] != effect["disk_sha256_at_effect"]
        pending.own_reaped_callback(callback_identity)
        assert pending.safe_owned_release()
        control.write_bytes(old_disk)
        assert loaded_identity_is_current(pending.source_identity, {"native_control": control})
        observations = {"verdict": "SOURCE_FAIL/NOT_READY", "schema_valid_hook_and_command_shapes": True,
            "post_stdin_tool_use_id": "CURRENT_DOCS_SUPPORTED_NOT_RELEASE_WIRE_PROBED",
            "hook_notification_correlation": "NOT_DECLARED_UNKNOWN_UNPROBED_NOT_PROVED_IMPOSSIBLE",
            "command": {"pid_start": command_identity, "exit_code": command_exit, "reaped": True},
            "retained_callback": {"pid_start": callback_identity, "exact_selected_AST": ready["actual_call_AST_sha256"],
                "is_OS_descendant_of_command": False, "relation": "owned async callback requested by completed command",
                "alive_after_command_exit": True, "exit_code": callback_exit, "reaped": True},
            "rejected_post_only_release": {"released_before_callback": True, "effect": effect,
                "loaded_current_disk_identity_mismatch_at_effect": True},
            "safe_owned_positive": {"reservation_retained_across_post_and_command_exit": True,
                "released_after_exact_owned_waitpid_receipt": True, "loaded_identity_checked_before_new_epoch": True},
            "live_terminal_evidence": "NOT_RUN_OR_PROVIDED", "genuine_bootstrap": "NOT_RUN",
            "production_classifier": production_release_status(all_actor_coverage="NOT_ACCEPTED",
                native_terminal_coverage="UNESTABLISHED", genuine_bootstrap="NOT_RUN"),
            "actual_native_calls": 0, "actual_runtime_imports": 0, "actual_installs": 0}
    finally:
        closure = []
        for child, key in children:
            if child.returncode is None:
                if identity(child.pid) != key:
                    raise RuntimeError("STOP_UNCONFIRMED: fixture PID/start changed")
                child.kill()
                child.wait(timeout=5)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream:
                    stream.close()
            closure.append({"pid_start": key, "return_code": child.returncode, "reaped": True,
                            "proc_identity_absent": not Path(f"/proc/{key[0]}").exists()})
        after = {"fd": len(os.listdir("/proc/self/fd")), "threads": len(os.listdir("/proc/self/task")),
                 "children": Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").read_text()}
        observations["resource_closure"] = {"before": before, "after": after, "children": closure,
            "fd_delta": after["fd"]-before["fd"], "thread_delta": after["threads"]-before["threads"],
            "RLIMIT_AS": resource.getrlimit(resource.RLIMIT_AS), "affinity": sorted(os.sched_getaffinity(0)),
            "self_reported_ru_maxrss_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "self_ru_maxrss_scope": "OS_REPORTED_HIGHWATER_MAY_INCLUDE_PRE_EXEC_HOST_HISTORY",
            "children_reported_ru_maxrss_KiB": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            "whole_assignment_peak_RSS": "UNKNOWN_NOT_ZERO"}
        (BASE / "NATIVE-GAP-OBSERVATIONS.json").write_text(json.dumps(observations, indent=2, sort_keys=True)+"\n")
    assert observations["resource_closure"]["fd_delta"] == 0
    assert observations["resource_closure"]["thread_delta"] == 0
    assert not observations["resource_closure"]["after"]["children"].strip()
    print(json.dumps({"result": observations["verdict"], "own_children_reaped": len(children),
                      "actual_call_AST": ready["actual_call_AST_sha256"]}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "callback":
        callback_worker()
    elif len(sys.argv) > 1 and sys.argv[1] == "command":
        command_worker()
    else:
        run()
