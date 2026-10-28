"""Execute only three exact patched native methods in a fixture owner object.

No installed module is imported, modified or started. The current installed
source is a read-only input to the already prepared patch consumer.
"""
import ast
import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from qpb.friday_adapter import ENV, session_guard_change
from qpb.idle import Coordinator
from qpb.paths import tool_root


class NativeQueueGuardTests(unittest.TestCase):
    def test_actual_guard_claim_handoff_stale_release_and_orphan_cleanup(self):
        root = tool_root()
        pins = json.loads((root / "integration/friday-foreground-pins.json").read_text())
        item = next(p for p in pins if p["relative"] == "native/gateway/platforms/base.py")
        entire = (root / "integration/friday-foreground.patch").read_text()
        delta = "--- a/native/gateway/platforms/base.py" + entire.split("--- a/native/gateway/platforms/base.py", 1)[1]
        with tempfile.TemporaryDirectory(prefix="qpb-native-queue-") as tmp:
            directory = Path(tmp)
            target = directory / item["relative"]
            target.parent.mkdir(parents=True)
            target.write_bytes(Path(item["path"]).read_bytes())
            patch_file = directory / "delta.patch"; patch_file.write_text(delta)
            subprocess.run(["patch", "-p1", "--batch", "-i", str(patch_file)], cwd=directory,
                           check=True, capture_output=True)
            tree = ast.parse(target.read_text())
            wanted = {"_start_session_processing", "_release_session_guard", "_heal_stale_session_lock"}
            methods = [copy.deepcopy(node) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in wanted]
            self.assertEqual(len(methods), 3)
            c = Coordinator(directory / "admission")
            instance = SimpleNamespace(name="fixture", _active_sessions={}, _pending_messages={}, _session_tasks={}, _requeue_counts={})
            held = []
            def mirror(owner, key, old, new):
                session_guard_change("fixture-group", str(id(old)) if old is not None else None,
                                     str(id(new)) if new is not None else None, key in owner._pending_messages)
            namespace = {"asyncio": asyncio, "session_guard_change": mirror,
                         "logger": SimpleNamespace(warning=lambda *a, **k: None)}
            module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + methods, type_ignores=[])
            exec(compile(ast.fix_missing_locations(module), "<isolated-native-queue-guard>", "exec"), namespace)
            for name in wanted:
                setattr(instance, name, namespace[name].__get__(instance))
            async def work(*args): await asyncio.Event().wait()
            def track(key, task): instance._session_tasks[key] = task; held.append(task); return True
            instance._process_message_background = work
            instance._track_session_task = track
            instance._session_task_is_stale = lambda key: True
            instance._discard_text_debounce = lambda key: None
            async def run():
                self.assertTrue(instance._start_session_processing(object(), "session"))
                old = instance._active_sessions["session"]
                self.assertEqual(len(c.snapshot()["foreground"]), 1, "reserve exists before scheduled task starts")
                instance._pending_messages["session"] = object()
                instance._release_session_guard("session", guard=old)
                self.assertTrue(next(iter(c.snapshot()["foreground"].values()))["pending"])
                instance._pending_messages.pop("session")
                instance._start_session_processing(object(), "session")
                new = instance._active_sessions["session"]
                instance._release_session_guard("session", guard=old)
                self.assertEqual(next(iter(c.snapshot()["foreground"].values()))["guards"], [str(id(new))])
                self.assertTrue(instance._heal_stale_session_lock("session"))
                self.assertFalse(c.snapshot()["foreground"])
                for task in held: task.cancel()
                await asyncio.gather(*held, return_exceptions=True)
            with patch.dict(os.environ, {ENV: str(c.dir)}):
                asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
