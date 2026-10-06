"""Real Git refusal controls; fixtures never change the donor's tracked files."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "a0_prepare.py"
spec = importlib.util.spec_from_file_location("a0_prepare", SCRIPT)
a0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a0)


class CheckoutControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("A0_TEST_TMP_ROOT"))
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        a0.git(self.path, "init", "--template=")
        a0.git(self.path, "remote", "add", "origin", a0.UPSTREAM)
        (self.path / "LICENSE").write_text("Synthetic fixture license\n")
        (self.path / "fixture.txt").write_text("Synthetic source bytes\n")
        a0.git(self.path, "add", "LICENSE", "fixture.txt")
        a0.git(self.path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
               "-c", "commit.gpgsign=false", "commit", "-m", "Synthetic refusal fixture")
        self.pin = {"commit": a0.git(self.path, "rev-parse", "HEAD").decode().strip(),
                    "tree": a0.git(self.path, "rev-parse", "HEAD^{tree}").decode().strip(),
                    "clone_url": a0.UPSTREAM}

    def test_clean_check_and_prepare_are_read_only(self):
        index = self.path / ".git" / "index"
        before = hashlib.sha256(index.read_bytes()).hexdigest()
        source, files = a0.check_checkout(self.path, self.pin)
        self.assertEqual(source["tracked_files"], 2)
        self.assertEqual(a0.prepare(self.path, self.pin), (source, files))
        self.assertEqual(hashlib.sha256(index.read_bytes()).hexdigest(), before)

    def test_wrong_commit_refused_without_reset(self):
        with self.assertRaisesRegex(a0.Refusal, "pin mismatch"):
            a0.prepare(self.path, {**self.pin, "commit": "0" * 40})
        self.assertEqual(a0.git(self.path, "rev-parse", "HEAD").decode().strip(), self.pin["commit"])

    def test_wrong_tree_refused(self):
        with self.assertRaisesRegex(a0.Refusal, "pin mismatch"):
            a0.check_checkout(self.path, {**self.pin, "tree": "0" * 40})

    def test_dirty_bytes_refused_even_with_assume_unchanged(self):
        a0.git(self.path, "update-index", "--assume-unchanged", "fixture.txt")
        (self.path / "fixture.txt").write_text("Changed synthetic source\n")
        with self.assertRaisesRegex(a0.Refusal, "dirty tracked source bytes"):
            a0.prepare(self.path, self.pin)
        self.assertEqual((self.path / "fixture.txt").read_text(), "Changed synthetic source\n")

    def test_dirty_index_refused(self):
        (self.path / "fixture.txt").write_text("Changed staged source\n")
        a0.git(self.path, "add", "fixture.txt")
        with self.assertRaisesRegex(a0.Refusal, "dirty tracked source index"):
            a0.check_checkout(self.path, self.pin)

    def test_missing_tracked_source_refused(self):
        (self.path / "fixture.txt").unlink()
        with self.assertRaisesRegex(a0.Refusal, "missing/unreadable tracked source"):
            a0.check_checkout(self.path, self.pin)

    def test_wrong_origin_refused(self):
        a0.git(self.path, "remote", "set-url", "origin", "https://example.invalid/wrong.git")
        with self.assertRaisesRegex(a0.Refusal, "origin mismatch"):
            a0.check_checkout(self.path, self.pin)

    def test_competing_writer_refused(self):
        (self.path / ".git" / "index.lock").write_text("fixture writer\n")
        with self.assertRaisesRegex(a0.Refusal, "competing writer"):
            a0.prepare(self.path, self.pin)

    def test_wrong_file_mode_refused(self):
        (self.path / "fixture.txt").chmod(0o755)
        with self.assertRaisesRegex(a0.Refusal, "dirty tracked source mode"):
            a0.check_checkout(self.path, self.pin)

    def test_wrong_tracked_file_type_refused(self):
        (self.path / "fixture.txt").unlink()
        (self.path / "fixture.txt").symlink_to("LICENSE")
        with self.assertRaisesRegex(a0.Refusal, "dirty tracked source type"):
            a0.check_checkout(self.path, self.pin)

    def test_untracked_source_refused(self):
        (self.path / "additional.py").write_text("# synthetic additional source\n")
        with self.assertRaisesRegex(a0.Refusal, "untracked source"):
            a0.check_checkout(self.path, self.pin)


if __name__ == "__main__":
    unittest.main()
