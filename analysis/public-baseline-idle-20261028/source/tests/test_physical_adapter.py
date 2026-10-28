import asyncio
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from qpb.friday_adapter import ENV, physical_create, tracked
from qpb.idle import Coordinator


def client(callback):
    return SimpleNamespace(base_url="http://192.0.2.195:30000/v1", chat=SimpleNamespace(completions=SimpleNamespace(create=callback)))


def chunk(finish=None, index=0):
    return SimpleNamespace(choices=[SimpleNamespace(index=index, finish_reason=finish)])


class Stream:
    def __init__(self, values):
        self.values, self.response, self.closed = iter(values), object(), False
    def __iter__(self): return self
    def __next__(self): return next(self.values)
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class PhysicalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-physical-")
        self.addCleanup(self.tmp.cleanup)
        self.c = Coordinator(Path(self.tmp.name) / "admission")
        env = patch.dict(os.environ, {ENV: str(self.c.dir)})
        env.start(); self.addCleanup(env.stop)

    def test_swallowed_error_then_success_keeps_first_unknown(self):
        called = []
        def create(**request):
            called.append(request)
            if len(called) == 1: raise OSError("fixture possibly accepted")
            return chunk("stop")
        c = client(create)
        @tracked("whole-turn")
        def turn():
            try: physical_create(c, {"stream": False})
            except OSError: pass
            return physical_create(c, {"stream": False})
        turn()
        rows = list(self.c.snapshot()["foreground"].values())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "OUTCOME_UNKNOWN")
        self.assertEqual(len(called), 2)

    def test_sync_next_context_attrs_and_close_preserved(self):
        stream = Stream([chunk(), chunk("tool_calls")])
        wrapped = physical_create(client(lambda **kwargs: stream), {"stream": True})
        self.assertIs(wrapped.response, stream.response)
        with wrapped as entered:
            self.assertIs(entered, wrapped)
            next(wrapped); next(wrapped)
            with self.assertRaises(StopIteration): next(wrapped)
        self.assertTrue(stream.closed)
        self.assertFalse(self.c.snapshot()["foreground"])
        self.assertNotIn("COORDINATOR_FAULT", self.c.snapshot()["blocks"])

    def test_stream_close_and_eof_without_terminal_keep_unknown(self):
        wrapped = physical_create(client(lambda **kwargs: Stream([chunk()])), {"stream": True})
        list(wrapped); wrapped.close()
        rows = list(self.c.snapshot()["foreground"].values())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "OUTCOME_UNKNOWN")

    def test_all_requested_choices_require_terminal(self):
        result = physical_create(client(lambda **kwargs: chunk("stop", 0)), {"stream": False, "n": 2})
        self.assertIsNotNone(result)
        self.assertEqual(len(self.c.snapshot()["foreground"]), 1)

    def test_async_anext_full_and_early_eof(self):
        async def exercise():
            class AsyncStream:
                def __init__(self, terminal): self.values=iter([chunk("stop" if terminal else None)])
                def __aiter__(self): return self
                async def __anext__(self):
                    try: return next(self.values)
                    except StopIteration: raise StopAsyncIteration
                async def close(self): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): await self.close()
            async def create(**kwargs): return AsyncStream(kwargs.get("fixture_terminal"))
            wrapped = await physical_create(client(create), {"stream": True, "fixture_terminal": True})
            async with wrapped:
                await anext(wrapped)
                with self.assertRaises(StopAsyncIteration): await anext(wrapped)
            self.assertFalse(self.c.snapshot()["foreground"])
            other = await physical_create(client(create), {"stream": True})
            async for _ in other: pass
            await other.close()
            self.assertEqual(len(self.c.snapshot()["foreground"]), 1)
        asyncio.run(exercise())

    def test_proxy_constructor_failure_keeps_original_response_and_one_create(self):
        stream = Stream([chunk("stop")])
        calls = []
        c = client(lambda **kw: calls.append(kw) or stream)
        with patch("qpb.friday_adapter._SyncStream", side_effect=RuntimeError("fixture adapter failure")):
            result = physical_create(c, {"stream": True})
        self.assertIs(result, stream)
        self.assertEqual(len(calls), 1)
        self.assertEqual(list(result)[0].choices[0].finish_reason, "stop")
        rows = list(self.c.snapshot()["foreground"].values())
        self.assertEqual(rows[0]["outcome"], "OUTCOME_UNKNOWN")
        self.assertIn("COORDINATOR_FAULT", self.c.snapshot()["blocks"])


if __name__ == "__main__":
    unittest.main()
