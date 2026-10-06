"""Offline acceptance inputs, not a native worker or Telegram demonstration.

Returned Python executes only in bwrap with the owner's original tests mounted
read-only. File receipt fixtures are synthetic; actual native admission remains
the parent's responsibility. No host/adapter/route candidate is selected here.
"""
import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/host-repair"
INPUT = FIXTURE / "input/calculator.py"
GOLDEN = FIXTURE / "owner/test_calculator.py"
INPUT_SHA = "e1a894022d1a082987b87adecb623438c9e386d86b2b621cff4a5fe7fdf7edc8"
GOLDEN_SHA = "3046b45b0b2c2702ac686ef1e946a6601c67d456a4e49b895566310674b33995"
CORRECTION = b"def add(a, b):\n    return a + b\n"

package_root = ROOT / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location(
    "friday_fixture_inputs", package_root / "__init__.py",
    submodule_search_locations=[str(package_root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_fixture_inputs.inputs import stage_inputs
from friday_fixture_inputs.artifacts import ArtifactError, stage_file, read_staged
from friday_fixture_inputs import artifacts


def isolated_check(candidate):
    """Check this finite arithmetic fixture without executing host-side code.

    The owner accepts one plain add(a,b) function returning a binary arithmetic
    expression on its two arguments. Imports, calls, decorators and module
    effects cannot forge unittest completion. This deliberately narrow fixture
    grammar is not a general-purpose Python acceptance policy.
    """
    source = Path(candidate).read_bytes()
    try:
        tree = ast.parse(source)
        expected = ast.parse(CORRECTION)
        # Allow the original subtraction and either operand order too; the
        # immutable behavioral tests, rather than AST shape, determine PASS.
        for operator in (ast.Add(), ast.Sub()):
            for names in (("a", "b"), ("b", "a")):
                value = expected.body[0].body[0].value
                value.op = operator
                value.left.id, value.right.id = names
                if ast.dump(tree) == ast.dump(expected):
                    return _isolated_unittest(candidate)
    except (SyntaxError, ValueError):
        pass
    return subprocess.CompletedProcess([], 2, b"", b"fixture_source_contract_refused\n")


def _isolated_unittest(candidate):
    """Use an ordinary unittest process; never import candidate into this host.

    This finite fixture check is not a worker launcher or a general code judge.
    The parent must first validate/stage returned bytes using existing helpers.
    Exit zero without the original unittest completion is not goal evidence.
    """
    assert hashlib.sha256(GOLDEN.read_bytes()).hexdigest() == GOLDEN_SHA
    command = [
        "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
        "--cap-drop", "ALL", "--clearenv", "--setenv", "PATH", "/usr/bin",
        "--setenv", "HOME", "/tmp", "--setenv", "LANG", "C.UTF-8",
        "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/bin", "/bin",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--tmpfs", "/job", "--tmpfs", "/owner",
        "--ro-bind", str(Path(candidate).resolve()), "/job/calculator.py",
        "--ro-bind", str(GOLDEN), "/owner/test_calculator.py",
        "--chdir", "/job", "/usr/bin/python3", "-I", "-S", "-B", "-c",
        "import sys,unittest; sys.path[:0]=['/owner','/job']; "
        "r=unittest.TextTestRunner(verbosity=2).run("
        "unittest.defaultTestLoader.loadTestsFromName('test_calculator')); "
        "sys.exit(not r.wasSuccessful())",
    ]

    def limits():
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=5, check=False, preexec_fn=limits)


class HostRepairFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="frw013-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cache, self.stage = self.root / "cache", self.root / "stage"
        self.cache.mkdir(mode=0o700)
        self.stage.mkdir(mode=0o700)
        self.source = self.cache / "calculator.py"
        self.source.write_bytes(INPUT.read_bytes())
        self.proof = {
            "platform": "telegram", "session_key": "synthetic-fixture-only",
            "source_profile": "", "transport_profile": "default",
            "runtime_profile": "default", "message": {
                "bot_id": "9001", "user_id": "111", "chat_id": "-1001",
                "thread_id": "17", "message_id": "501",
                "platform_update_id": "701", "reply_to_message_id": "499",
                "media": [{"local_reference": str(self.source),
                           "mime_type": "text/x-python",
                           "origin": {"bot_id": "9001", "chat_id": "-1001",
                                      "thread_id": "17", "message_id": "501",
                                      "file_id": "synthetic-file",
                                      "file_unique_id": "synthetic-unique",
                                      "declared_bytes": 32},
                           "content": {"size_bytes": 32,
                                       "sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest()}}]}}

    def stage_input(self, **changes):
        args = dict(matched_ingress=self.proof, admitted_reference="synthetic:frw013",
                    cache_roots=(self.cache,), staging_root=self.stage,
                    worker_input_root="/job/inputs", max_file_bytes=32,
                    max_total_bytes=64)
        args.update(changes)
        return stage_inputs(**args)

    def test_baseline_fails_original_owner_checks(self):
        self.assertEqual(hashlib.sha256(INPUT.read_bytes()).hexdigest(), INPUT_SHA)
        before = GOLDEN.read_bytes()
        result = isolated_check(INPUT)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(b"AssertionError: 2 != 12", result.stderr)
        self.assertIn(b"FAILED (failures=1)", result.stderr)
        self.assertEqual(GOLDEN.read_bytes(), before)

    def test_known_independent_correction_passes_same_checks(self):
        candidate = self.root / "calculator.py"
        candidate.write_bytes(CORRECTION)
        result = isolated_check(candidate)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"Ran 1 test", result.stderr)
        self.assertTrue(result.stderr.rstrip().endswith(b"OK"))
        self.assertEqual(hashlib.sha256(GOLDEN.read_bytes()).hexdigest(), GOLDEN_SHA)

    def test_wrong_result_and_self_attested_success_do_not_pass(self):
        for source in (b"def add(a,b): return 42\n",
                       b"import sys\nsys.exit(0)\n",
                       b"raise RuntimeError('not a completed repair')\n"):
            with self.subTest(source=source):
                candidate = self.root / "calculator.py"
                candidate.write_bytes(source)
                result = isolated_check(candidate)
                completed = (result.returncode == 0 and b"Ran 1 test" in result.stderr
                             and result.stderr.rstrip().endswith(b"OK"))
                self.assertFalse(completed, result.stderr)

    def test_returned_code_cannot_write_golden_or_read_owner_home(self):
        before = GOLDEN.read_bytes()
        candidate = self.root / "calculator.py"
        candidate.write_bytes(
            b"from pathlib import Path\n"
            b"assert not Path('/home').exists()\n"
            b"try:\n"
            b"    Path('/owner/test_calculator.py').write_text('forged pass')\n"
            b"except OSError:\n"
            b"    pass\n"
            b"else:\n"
            b"    raise RuntimeError('golden was writable')\n"
            b"def add(a,b): return a-b\n")
        result = _isolated_unittest(candidate)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(b"FAILED (failures=1)", result.stderr)
        self.assertEqual(GOLDEN.read_bytes(), before)

    def test_exact_input_bytes_caption_and_reply_mapping(self):
        for message in ("501", "499"):
            with self.subTest(message=message):
                self.proof["message"]["media"][0]["origin"]["message_id"] = message
                (item,) = self.stage_input()
                self.assertEqual(Path(item.host_path).read_bytes(), INPUT.read_bytes())
                self.assertEqual(item.size_bytes, 32)
                self.assertEqual(item.sha256, hashlib.sha256(INPUT.read_bytes()).hexdigest())
                self.assertEqual(item.worker_path, "/job/inputs/" + Path(item.host_path).name)
                self.assertEqual(item.receipt_reference, "synthetic:frw013")

    def test_absent_input_is_not_a_substitute(self):
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage_input()
        self.assertEqual(list(self.stage.iterdir()), [])
        empty = copy.deepcopy(self.proof)
        empty["message"]["media"] = []
        self.assertEqual(self.stage_input(matched_ingress=empty), ())
        # Required attachment: the host must refuse this zero-file outcome.

    def test_same_size_wrong_bytes_cannot_receive_mapping(self):
        self.source.write_bytes(CORRECTION)
        with self.assertRaisesRegex(ArtifactError, "input_bytes_changed_since_receive"):
            self.stage_input()
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o400
                            for p in self.stage.iterdir()))

    def test_same_original_name_keeps_two_task_bytes_independent(self):
        (first,) = self.stage_input()
        second_stage = self.root / "second-stage"
        second_stage.mkdir(mode=0o700)
        self.source.write_bytes(CORRECTION)
        second = copy.deepcopy(self.proof)
        second["message"]["media"][0]["content"]["sha256"] = hashlib.sha256(CORRECTION).hexdigest()
        (other,) = self.stage_input(matched_ingress=second, staging_root=second_stage,
                                   admitted_reference="synthetic:second-task")
        self.assertNotEqual(first.host_path, other.host_path)
        self.assertEqual(Path(first.host_path).read_bytes(), INPUT.read_bytes())
        self.assertEqual(Path(other.host_path).read_bytes(), CORRECTION)
        self.assertNotEqual(first.receipt_reference, other.receipt_reference)

    def test_forced_staging_collision_never_overwrites_prior_bytes(self):
        with patch.object(artifacts.uuid, "uuid4", return_value=SimpleNamespace(hex="a" * 32)):
            (first,) = self.stage_input()
            with self.assertRaises(FileExistsError):
                self.stage_input()
        self.assertEqual(Path(first.host_path).read_bytes(), INPUT.read_bytes())
        self.assertEqual(len(list(self.stage.iterdir())), 1)

    def test_checked_output_uses_existing_stable_artifact_bytes(self):
        self.source.write_bytes(CORRECTION)
        row = stage_file(source_root=self.cache, relative_path="calculator.py",
                         staging_root=self.stage, logical_name="calculator.py",
                         media_type="text/x-python", origin_reference="synthetic:output",
                         max_bytes=32)
        self.source.write_bytes(b"changed after staging")
        self.assertEqual(read_staged(staging_root=self.stage, artifact=row, max_bytes=32),
                         CORRECTION)
        result = isolated_check(self.stage / row.reference)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
