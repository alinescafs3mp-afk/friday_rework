"""Source identity and scope controls use disposable local Git fixtures."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dsh_prepare", ROOT / "scripts/dsh_prepare.py")
dsh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dsh)


class SourceChecks(unittest.TestCase):
    def setUp(self):
        parent = (Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']) / 'dsh-source-fixtures'
                  if 'FRIDAY_FIXTURE_EVIDENCE' in os.environ else ROOT / '.evidence/frw002-sol/test-fixtures')
        parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "--quiet")
        self.git("remote", "add", "origin", "https://github.com/deepseek-ai/deepseek-harness.git")
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "pnpm-lock.yaml"):
            (self.repo / name).write_text(name + "\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@invalid", "commit", "--quiet", "-m", "fixture")
        self.git("checkout", "--detach", "--quiet")
        self.source = {"commit": self.git("rev-parse", "HEAD"), "tree": self.git("rev-parse", "HEAD^{tree}"),
                       "clone_url": "https://github.com/deepseek-ai/deepseek-harness.git"}

    def git(self, *args):
        return subprocess.check_output(["git", "--no-optional-locks", "-c", "core.hooksPath=" + os.devnull, *args], cwd=self.repo,
                                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_GLOBAL": os.devnull,
                                            "GIT_CONFIG_SYSTEM": os.devnull}, text=True).strip()

    def test_clean_exact_source(self):
        self.assertTrue(dsh.verify_source(self.repo, self.source)["tracked_clean"])

    def test_wrong_commit(self):
        with self.assertRaisesRegex(ValueError, "Wrong donor identity"):
            dsh.verify_source(self.repo, {**self.source, "commit": "0" * 40})

    def test_wrong_tree(self):
        with self.assertRaisesRegex(ValueError, "Wrong donor identity"):
            dsh.verify_source(self.repo, {**self.source, "tree": "0" * 40})

    def test_dirty_source_preserved(self):
        path = self.repo / "LICENSE"
        path.write_text("owner edit\n")
        with self.assertRaisesRegex(ValueError, "dirty"):
            dsh.verify_source(self.repo, self.source)
        self.assertEqual(path.read_text(), "owner edit\n")

    def test_staged_source_refused(self):
        (self.repo / "LICENSE").write_text("staged edit\n")
        self.git("add", "LICENSE")
        with self.assertRaisesRegex(ValueError, "dirty"):
            dsh.verify_source(self.repo, self.source)

    def test_assume_unchanged_does_not_hide_dirty_bytes(self):
        self.git("update-index", "--assume-unchanged", "LICENSE")
        (self.repo / "LICENSE").write_text("hidden owner edit\n")
        self.assertEqual(self.git("status", "--porcelain=v1", "--untracked-files=no"), "")
        with self.assertRaisesRegex(ValueError, "Source blob differs"):
            dsh.verify_source(self.repo, self.source)
        self.assertEqual((self.repo / "LICENSE").read_text(), "hidden owner edit\n")

    def test_wrong_origin(self):
        self.git("remote", "set-url", "origin", "https://invalid.example/donor.git")
        with self.assertRaisesRegex(ValueError, "origin"):
            dsh.verify_source(self.repo, self.source)

    def test_symlink_checkout(self):
        link = self.repo / "link"
        link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            dsh.verify_source(link, self.source)

    def test_source_branch_refused(self):
        self.git("checkout", "-b", "floating", "--quiet")
        with self.assertRaisesRegex(ValueError, "detached"):
            dsh.verify_source(self.repo, self.source)

    def test_competing_writer_refused_without_removing_lock(self):
        lock = self.repo / ".git/index.lock"
        lock.write_bytes(b"owned by another writer")
        with self.assertRaisesRegex(ValueError, "Competing donor writer"):
            dsh.verify_source(self.repo, self.source)
        self.assertEqual(lock.read_bytes(), b"owned by another writer")

    def test_untracked_source_refused_and_preserved(self):
        path = self.repo / "unexpected-source.ts"
        path.write_text("owner source\n")
        with self.assertRaisesRegex(ValueError, "Unexpected untracked donor source"):
            dsh.verify_source(self.repo, self.source)
        self.assertEqual(path.read_text(), "owner source\n")

    def test_ignored_root_env_refused_and_preserved(self):
        (self.repo / ".git/info/exclude").write_text(".env\n")
        path = self.repo / ".env"
        path.write_text("DEEPSEEK_API_KEY=fixture-only\n")
        self.assertEqual(self.git("ls-files", "--others", "--exclude-standard"), "")
        with self.assertRaisesRegex(ValueError, "donor-root environment file"):
            dsh.verify_source(self.repo, self.source)
        self.assertEqual(path.read_text(), "DEEPSEEK_API_KEY=fixture-only\n")

    def test_declared_crlf_checkout_keeps_the_pinned_blob(self):
        (self.repo / ".gitattributes").write_text("*.cmd text eol=crlf\n")
        path = self.repo / "launcher.cmd"
        path.write_bytes(b"echo intact\r\n")
        self.git("add", ".gitattributes", "launcher.cmd")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@invalid", "commit", "--quiet", "-m", "Windows checkout")
        self.source.update(commit=self.git("rev-parse", "HEAD"), tree=self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(dsh.verify_source(self.repo, self.source)["upstream_declared_crlf_checkout_paths"], ["launcher.cmd"])
        self.git("update-index", "--assume-unchanged", "launcher.cmd")
        path.write_bytes(b"echo drift\r\n")
        with self.assertRaisesRegex(ValueError, "Source blob differs"):
            dsh.verify_source(self.repo, self.source)


class ToolchainChecks(unittest.TestCase):
    def test_supported_node_engine_range(self):
        self.assertTrue(dsh.node_supported("v22.19.0"))
        self.assertTrue(dsh.node_supported("v24.0.0"))
        self.assertFalse(dsh.node_supported("v22.18.9"))
        self.assertFalse(dsh.node_supported("v23.9.0"))

    def test_child_environment_excludes_provider_and_telegram_secrets(self):
        env = dsh.clean_environment(ROOT)
        self.assertEqual(env["DSH_TELEMETRY_DISABLED"], "1")
        self.assertFalse(any("KEY" in key or "TOKEN" in key for key in env))


if __name__ == "__main__":
    unittest.main()
