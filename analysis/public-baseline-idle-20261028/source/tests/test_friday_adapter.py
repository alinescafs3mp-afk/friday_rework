import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qpb.idle import Coordinator
from qpb.friday_adapter import ENV, tracked, atracked, start_worker, observe_worker


class FridayAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-friday-adapter-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "admission"
        self.env = patch.dict("os.environ", {ENV: str(self.directory)})
        self.env.start(); self.addCleanup(self.env.stop)
        self.c = Coordinator(self.directory)
        self.row = {"owner": {"profile": "fixture"}, "existing_task_id": "fixture-worker",
                    "admission_hash": "a" * 64, "worker_kind": "a0",
                    "host": {"terminal": None, "quiescence": None}}

    def test_old_unknown_read_does_not_reserve_but_current_worker_persists_past_turn(self):
        observe_worker(self.row)
        self.assertEqual(self.c.snapshot()["foreground"], {})
        @tracked("fixture-turn")
        def turn():
            self.assertEqual(len(self.c.snapshot()["foreground"]), 1)
            start_worker(self.row)
            # Independent child reservation survives tool gaps and parent end.
            self.assertEqual(len(self.c.snapshot()["foreground"]), 2)
        turn()
        self.assertEqual(len(self.c.snapshot()["foreground"]), 1)
        start_worker(self.row)  # Same actual assignment, no duplicate reserve.
        self.assertEqual(len(self.c.snapshot()["foreground"]), 1)
        self.row["host"]["terminal"] = {"state": "completed"}
        observe_worker(self.row)
        self.assertEqual(len(self.c.snapshot()["foreground"]), 1, "terminal alone is insufficient")
        self.row["host"]["quiescence"] = {"kind": "a0", "observation": {"native_cessation": True}}
        observe_worker(self.row)
        self.assertEqual(self.c.snapshot()["foreground"], {})

    def test_coordinator_fault_never_prevents_foreground(self):
        self.c.snapshot()
        (self.directory / "state.json").write_text("{")
        called = []
        @tracked("fixture-turn")
        def turn():
            called.append(True)
            return 42
        self.assertEqual(turn(), 42)
        self.assertEqual(called, [True])
        self.assertTrue((self.directory / "FAULT").exists())

    def test_async_pending_and_tool_gap_keep_reserve(self):
        @atracked("fixture-async")
        async def turn():
            self.assertEqual(len(self.c.snapshot()["foreground"]), 1)
            await asyncio.sleep(0)
            self.assertEqual(len(self.c.snapshot()["foreground"]), 1)
        asyncio.run(turn())
        self.assertEqual(self.c.snapshot()["foreground"], {})

    def test_unknown_task_exception_does_not_clear_resource(self):
        @tracked("fixture-turn")
        def turn():
            raise OSError("fixture lost response")
        with self.assertRaises(OSError):
            turn()
        reservations = list(self.c.snapshot()["foreground"].values())
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0]["outcome"], "OUTCOME_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
