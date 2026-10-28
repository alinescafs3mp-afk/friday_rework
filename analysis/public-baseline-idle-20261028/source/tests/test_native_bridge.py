import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from qpb.idle import Coordinator, IdleBlocked, POLICY
from qpb.paths import tool_root


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="qpb-native-bridge-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "qpb").mkdir()
        (self.root / "qpb/friday_adapter.py").write_text("# fixture")
        spec = importlib.util.spec_from_file_location("fixture_friday_bridge", tool_root() / "integration/friday_baseline_bridge.py")
        self.bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.bridge)
        self.bridge.BASELINE_ROOT = self.root
        self.bridge.COORDINATOR = self.root / "admission"
        self.c = Coordinator(self.bridge.COORDINATOR)
        self.c.snapshot()
        self.env = patch.dict(os.environ, {self.bridge.ENV: str(self.bridge.COORDINATOR)})
        self.env.start(); self.addCleanup(self.env.stop)
        package = SimpleNamespace(__file__=str(self.root / "qpb/__init__.py"))
        self.modules = patch.dict(sys.modules, {"qpb": package})
        self.modules.start(); self.addCleanup(self.modules.stop)

    def assert_open_foreground_closed_background(self, import_side_effect=None, module=None):
        @self.bridge.tracked("fixture-Friday")
        def turn():
            return 42
        with patch.object(self.bridge.importlib, "import_module", side_effect=import_side_effect, return_value=module):
            self.assertEqual(turn(), 42)
        self.assertTrue((self.bridge.COORDINATOR / "FAULT").exists())
        with self.assertRaisesRegex(IdleBlocked, "COORDINATOR_FAULT"):
            self.c.reserve("run", "task", "hash", "fingerprint", policy=dict(POLICY, idle_grace_seconds=0), manual=True)

    def test_missing_optional_package(self):
        self.assert_open_foreground_closed_background(import_side_effect=ModuleNotFoundError("fixture"))

    def test_broken_optional_import(self):
        self.assert_open_foreground_closed_background(import_side_effect=RuntimeError("fixture"))

    def test_begin_and_end_runtime_faults(self):
        def bad(*args, **kwargs):
            raise OSError("fixture")
        module = SimpleNamespace(__file__=str(self.root / "qpb/friday_adapter.py"), begin=bad, end=bad)
        self.assert_open_foreground_closed_background(module=module)

    def test_malformed_path_faults_canonical_slot(self):
        with patch.dict(os.environ, {self.bridge.ENV: "/tmp/not-the-canonical-slot"}):
            self.assert_open_foreground_closed_background()

    def test_missing_import_physical_fallback_sends_once(self):
        calls = []
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw) or 42)))
        with patch.object(self.bridge.importlib, "import_module", side_effect=ModuleNotFoundError("fixture")):
            self.assertEqual(self.bridge.physical_create(client, {"stream": False}), 42)
        self.assertEqual(len(calls), 1)
        self.assertTrue((self.bridge.COORDINATOR / "FAULT").exists())

    def test_model_exception_propagates_without_fallback_repeat(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            raise OSError("possibly accepted request")
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        module = SimpleNamespace(__file__=str(self.root / "qpb/friday_adapter.py"),
                                 physical_create=lambda c, request: c.chat.completions.create(**request))
        with patch.object(self.bridge.importlib, "import_module", return_value=module):
            with self.assertRaises(OSError):
                self.bridge.physical_create(client, {"stream": False})
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
