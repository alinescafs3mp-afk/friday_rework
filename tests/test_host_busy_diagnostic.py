"""Exercise the exact private diagnostic writer without product runtime imports."""
import ast
import asyncio
import json
from pathlib import Path
import re
import stat
import time


def test_association_lock_busy_diagnostic_keeps_only_fixed_metadata(tmp_path):
    plugin = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
    host = plugin / "host.py"
    namespace = {"__file__": str(host), "__package__": "_busy_diagnostic_fixture",
                 "Path": Path, "asyncio": asyncio, "json": json, "re": re,
                 "time": time, "HostUnavailable": type("HostUnavailable", (RuntimeError,), {})}
    # Execute the real exception definitions and writer, never a runtime import.
    for path, names in ((plugin / "associations.py", {"AssociationError", "AssociationLockBusy"}),
                        (host, {"_record_async_failure"})):
        tree = ast.parse(path.read_text())
        selected = [node for node in tree.body
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
        assert {node.name for node in selected} == names
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)

    private = "PRIVATE_MESSAGE_PATH_USER_PAYLOAD_61cd3f"
    private_path = str(tmp_path / private / "private.py")
    row = {"worker_kind": "dsh", "existing_task_id": "native-" + "a" * 64,
           "native": {"invocation_id": "b" * 32}, "brief": private,
           "owner": {"user_id": private}, "workspace_reference": private_path}
    directory = tmp_path / "protected-diagnostic"
    directory.mkdir(mode=0o700)
    busy = namespace["AssociationLockBusy"](private + private_path)
    try:
        # Retain one allowlisted source site and exclude an untrusted path.
        exec(compile("raise busy", str(host), "exec"), {"busy": busy})
    except namespace["AssociationLockBusy"] as error:
        try:
            exec(compile("raise error", private_path, "exec"), {"error": error})
        except namespace["AssociationLockBusy"] as caught:
            assert namespace["_record_async_failure"](directory, row, "host_cleanup", caught)

    records = list(directory.glob("*.json"))
    assert len(records) == 1
    raw = records[0].read_text()
    value = json.loads(raw)
    assert value["exception_type"] == "association_lock_busy"
    assert value["phase"] == "host_cleanup"
    assert value["source_frames"] == [{"module": "host.py", "line": 1}]
    assert value["trace_truncated"] is False and value["causes"] == []
    assert value["reference"] == row["existing_task_id"]
    assert value["invocation_id"] == "b" * 32
    assert value["execution_outcome"] == "UNPROVEN"
    assert value["cleanup_outcome"] == "NOT_ASSERTED"
    assert set(value) == {"schema", "reference", "invocation_id", "phase", "exception_type",
                          "source_frames", "trace_truncated", "causes", "observed_unix",
                          "observed_monotonic", "execution_outcome", "cleanup_outcome"}
    assert all(item not in raw for item in (private, private_path, str(plugin), "AssociationLockBusy"))
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(records[0].stat().st_mode) == 0o600
    assert records[0].stat().st_nlink == 1
    assert not list(directory.glob(".worker-*"))
