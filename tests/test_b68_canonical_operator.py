import fcntl
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override

root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location(
    "friday_b68_operator_test", root / "__init__.py",
    submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_b68_operator_test.associations import Associations, AssociationError
from friday_b68_operator_test.boundary import WorkBrief
from friday_b68_operator_test import operator_metadata

OWNER = dict(bot_id="fixture-bot", user_id="fixture-user", chat_id="fixture-chat",
             thread_id="", message_id="fixture-message", session_key="fixture-key",
             session_id="fixture-session", profile="")


class CanonicalReadonlyOperatorTests(unittest.TestCase):
    def test_readonly_operator_get_skips_only_compound_admission_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            token = set_hermes_home_override(Path(temporary))
            self.addCleanup(reset_hermes_home_override, token)
            state = PluginState("friday_rework")
            ordinary = Associations(state, clock=lambda: 1000)
            ordinary.claim(
                task_id="canonical-read", admission_key="canonical-admission", owner=OWNER,
                brief=WorkBrief("dsh", "fixture", "fixture"),
                workspace_reference="owned-workspace",
                supervisor={"scope": "user", "unit": "friday-rework-worker-" + "a" * 32 + ".service"},
                budget_seconds=60, deadline_unix=1060)
            before = state.path.read_bytes()
            operator = object.__new__(operator_metadata._OperatorMetadata)
            operator._read_only = True
            operator.state = state
            operator.namespace = state._data_namespace
            operator.directory = Path(state.data_dir)
            directory_info = operator.directory.stat()
            lock_info = (operator.directory / ".state.json.lock").stat()
            current = ((directory_info.st_dev, directory_info.st_ino),
                       (lock_info.st_dev, lock_info.st_ino))
            state._native_namespaces[str(operator.directory)] = current
            operator._read_birth = current
            operator.active = True
            operator.token = operator_metadata._CURRENT.set(operator)
            self.addCleanup(operator_metadata._CURRENT.set, None)
            with patch.object(operator_metadata._OperatorMetadata, "_verify", lambda self: None):
                store = Associations(state, _operator=operator, clock=lambda: 1000)
                self.assertEqual(store.snapshot()["canonical-read"]["stop_intent"], None)
                fd = os.open(state.data_dir / "admission.lock", os.O_RDWR)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    row = store.get("canonical-read", OWNER)
                    self.assertEqual(row["existing_task_id"], "canonical-read")
                    self.assertEqual(state.path.read_bytes(), before)
                    with self.assertRaisesRegex(AssociationError, "unknown_or_foreign_task"):
                        store.get("canonical-read", {**OWNER, "chat_id": "foreign"})
                    with self.assertRaisesRegex(PermissionError, "readonly_operator"):
                        store.request_stop("canonical-read", OWNER, "cancel")
                    with self.assertRaisesRegex(AssociationError, "admission_busy"):
                        store.snapshot()
                    self.assertEqual(state.path.read_bytes(), before)
                finally:
                    os.close(fd)
                native_fd = os.open(state.data_dir / ".state.json.lock", os.O_RDWR)
                try:
                    from hermes_cli.friday_native_state import NativeCommitUncertain
                    fcntl.flock(native_fd, fcntl.LOCK_EX)
                    with self.assertRaisesRegex(NativeCommitUncertain, "native_commit_UNKNOWN"):
                        store.get("canonical-read", OWNER)
                finally:
                    os.close(native_fd)


if __name__ == "__main__":
    unittest.main()
