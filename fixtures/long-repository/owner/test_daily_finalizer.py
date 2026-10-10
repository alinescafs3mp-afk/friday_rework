#!/usr/bin/env python3
"""Actual Git fixture controls; all writes stay beside this test file."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "daily_finalizer.py"


class FinalizerTests(unittest.TestCase):
    def setUp(self):
        fixtures = HERE / "fixtures"
        fixtures.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=fixtures))
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_OPTIONAL_LOCKS="0", GIT_AUTHOR_NAME="Fixture",
                        GIT_COMMITTER_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.git("init", "-q", "--initial-branch=main")
        self.write("seed.txt", "base\n")
        self.base = self.commit("base")

    def git(self, *args):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(self.repo), *args],
                                       env=self.env, stderr=subprocess.PIPE).decode().strip()

    def write(self, name, value):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def commit(self, subject):
        self.git("add", "--all")
        self.git("commit", "-q", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def invoke(self, base=None, end=None, output=None, success=True):
        dest = output or self.root / "output"
        cp = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo),
                             "--base", base or self.base, "--end", end or self.git("rev-parse", "HEAD"),
                             "--output", str(dest)], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(cp.returncode, 0 if success else 2, cp.stdout + cp.stderr)
        if success:
            index = json.loads((dest / "daily-period-index.json").read_text())
            manifest = json.loads((dest / "MANIFEST.json").read_text())
            for entry in manifest["files"]:
                payload = (dest / entry["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])
                self.assertEqual(len(payload), entry["bytes"])
            self.assertFalse(index["daily_checkpoint_complete"])
            self.assertFalse(index["runtime_grant"])
            self.assertFalse(index["product_accepted"])
            self.assertEqual(index["stage"], "PROVISIONAL_NOT_DAILY_COMPLETE")
            return index, json.loads((dest / "publication-integrity.json").read_text())
        self.assertIn("REFUSED", cp.stderr)
        return cp

    def package(self, bad_hash=False):
        payload = '{"status":"REJECTED_HISTORICAL"}\n'
        self.write("analysis/2026-10-10/payload/outcome.json", payload)
        self.write("analysis/2026-10-10/payload/MANIFEST.json", json.dumps({"files": [
            {"path": "outcome.json", "sha256": "0" * 64 if bad_hash else hashlib.sha256(payload.encode()).hexdigest(),
             "bytes": len(payload.encode())}]}))

    def test_incremental_manifest_and_readonly(self):
        self.package()
        first = self.commit("published failure")
        self.write("docs/index.md", "[outcome](../analysis/2026-10-10/payload/outcome.json)\n")
        end = self.commit("navigation")
        self.write("seed.txt", "uncommitted must not be read\n")
        index_path = self.repo / ".git/index"
        config_path = self.repo / ".git/config"
        pins = {p: p.read_bytes() for p in [index_path, config_path, self.repo / "seed.txt"]}
        index, integrity = self.invoke(end=end)
        self.assertEqual([x["commit"] for x in index["ordered_commits"]], [first, end])
        self.assertEqual(index["counts"]["manifests"], 1)
        self.assertEqual(index["counts"]["hash_references"], 1)
        self.assertEqual(integrity["publication_gaps"], [])
        self.assertEqual({p: p.read_bytes() for p in pins}, pins)
        self.assertNotIn("uncommitted", (self.root / "output/daily-period-index.json").read_text())
        incremental, _ = self.invoke(base=first, end=end, output=self.root / "later")
        self.assertEqual(incremental["counts"]["commits"], 1)
        self.assertEqual([p["path"] for p in incremental["changed_paths"]], ["docs/index.md"])

    def test_intermediate_delete_rename_preserved(self):
        self.write("removed.txt", "permanent deletion")
        base = self.commit("baseline file")
        self.write("temporary.txt", "short lived data")
        added = self.commit("add temporary")
        (self.repo / "temporary.txt").rename(self.repo / "renamed.txt")
        renamed = self.commit("rename temporary")
        (self.repo / "renamed.txt").unlink()
        (self.repo / "removed.txt").unlink()
        deleted = self.commit("delete both")
        index, _ = self.invoke(base=base, end=deleted)
        self.assertEqual(index["intermediate_only_paths"], ["renamed.txt", "temporary.txt"])
        self.assertEqual({p["path"] for p in index["changed_paths"]}, {"temporary.txt", "renamed.txt", "removed.txt"})
        refs = {r["path"]: r for r in index["changed_paths"]}
        self.assertEqual([r["commit"] for r in refs["temporary.txt"]["commits"]], [added, renamed])
        self.assertFalse(refs["temporary.txt"]["present_at_end"])
        self.assertEqual([r["path"] for r in index["net_changed_paths"]], ["removed.txt"])
        for commit in index["ordered_commits"]:
            for change in commit["changed_paths"]:
                for side in ("before", "after"):
                    if side in change:
                        self.assertRegex(change[side]["sha256"], "^[0-9a-f]{64}$")

    def test_wrong_lineage_and_invalid_sha(self):
        self.write("main.txt", "main")
        main = self.commit("main")
        self.git("checkout", "-q", "-b", "side", self.base)
        self.write("side.txt", "side")
        side = self.commit("side")
        self.invoke(base=main, end=side, success=False)
        self.invoke(base="HEAD", end=side, success=False)
        self.invoke(base="f" * 40, end=side, success=False)
        self.assertFalse((self.root / "output").exists())

    def test_bad_manifest_hash_and_unchanged_owner_manifest(self):
        self.package(bad_hash=True)
        self.commit("bad declared hash")
        self.invoke(success=False)
        self.package()
        good = self.commit("correct package")
        self.write("analysis/2026-10-10/payload/outcome.json", '{"status":"changed"}\n')
        self.commit("payload changed without manifest")
        self.invoke(base=good, success=False)
        self.assertFalse((self.root / "output").exists())

    def test_output_collision_and_repo_output_refused(self):
        dest = self.root / "existing"
        dest.mkdir()
        (dest / "sentinel").write_text("untouched")
        self.invoke(output=dest, success=False)
        self.assertEqual((dest / "sentinel").read_text(), "untouched")
        link = self.root / "dangling"
        link.symlink_to(self.root / "does-not-exist")
        self.invoke(output=link, success=False)
        self.invoke(output=self.repo / "forbidden", success=False)
        self.assertFalse((self.repo / "forbidden").exists())

    def test_truthful_link_gaps_and_empty_period(self):
        self.write("docs/gap.md", "[missing](missing.md)\n")
        self.write("docs/status.json", '{"reference":"./missing.json","logical_source":"tests/original-namespace.py"}')
        end = self.commit("public gaps")
        index, integrity = self.invoke()
        self.assertEqual(index["counts"]["publication_gaps"], 2)
        self.assertEqual(integrity["verdict"], "PUBLIC_INTEGRITY_PASS_WITH_LINK_GAPS")
        empty, _ = self.invoke(base=end, end=end, output=self.root / "empty")
        self.assertEqual(empty["counts"]["commits"], 0)
        self.assertEqual(empty["changed_paths"], [])

    def test_merge_parent_edges(self):
        self.write("main.txt", "main")
        main = self.commit("main")
        self.git("checkout", "-q", "-b", "side", self.base)
        self.write("side.txt", "side")
        side = self.commit("side")
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "-m", "merge side", "side")
        index, _ = self.invoke()
        merge = index["ordered_commits"][-1]
        self.assertEqual(merge["parents"], [main, side])
        self.assertEqual({r["parent_commit"] for r in merge["changed_paths"]}, {main, side})

    def test_historical_daily_index_and_current_artifact_hash(self):
        self.write("docs/status.md", "earlier bytes")
        old = self.commit("old reported cut")
        self.write("docs/status.md", "new bytes")
        report = {"schema": "friday.analysis.daily-period-index.v1", "end_commit": old,
                  "changed_paths": [{"path": "docs/status.md",
                                     "sha256": hashlib.sha256(b"earlier bytes").hexdigest()},
                                    {"path": "docs/deleted.md", "status": "D"}],
                  "ordered_commits": [{"changed_paths": [{"path": "docs/deleted.md"}]}],
                  "logical_blocks": [{"paths": ["docs/deleted.md"]}],
                  "intermediate_only_paths": ["docs/deleted.md"],
                  "integrity_artifact": {"path": "current.json",
                                         "sha256": hashlib.sha256(b"{}\n").hexdigest()}}
        self.write("analysis/report/current.json", "{}\n")
        self.write("analysis/report/index.json", json.dumps(report))
        self.commit("publish earlier report beside newer source")
        index, integrity = self.invoke()
        self.assertEqual(integrity["publication_gaps"], [])
        self.assertEqual(index["counts"]["hash_references"], 1)
        self.write("analysis/report/current.json", "[]\n")
        self.commit("corrupt current artifact reference")
        cp = self.invoke(output=self.root / "bad-current", success=False)
        self.assertIn("PUBLIC_REFERENCE_MISMATCH", cp.stderr)

    def test_required_daily_integrity_reference_refusals(self):
        self.write("analysis/report/current.json", "{}\n")
        good = {"path": "current.json", "sha256": hashlib.sha256(b"{}\n").hexdigest(), "bytes": 3}
        cases = [None, {}, {**good, "path": "missing.json"},
                 {**good, "path": "/current.json"},
                 {**good, "path": "../../../outside.json"},
                 {**good, "sha256": "bad"}, {**good, "bytes": 4}]
        for n, artifact in enumerate(cases):
            with self.subTest(case=n):
                report = {"schema": "friday.analysis.daily-period-index.v1"}
                if artifact is not None:
                    report["integrity_artifact"] = artifact
                self.write("analysis/report/index.json", json.dumps(report))
                self.commit("invalid current artifact " + str(n))
                self.invoke(output=self.root / ("refused-" + str(n)), success=False)
                self.assertFalse((self.root / ("refused-" + str(n))).exists())
        report["integrity_artifact"] = good
        self.write("analysis/report/index.json", json.dumps(report))
        self.commit("valid current artifact")
        index, _ = self.invoke(output=self.root / "valid-current")
        self.assertEqual(index["counts"]["hash_references"], 1)

    def pin(self, root="archive", path="validation/acceptance_matrix.json", payload=b"{}\n"):
        return {"id": root + ":" + path, "root": root, "path": path,
                "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}

    def pins(self, entries):
        self.write("fixtures/daily-use/source-pins.json", json.dumps({
            "schema": "friday.daily-use.source-pins.v1", "sources": entries}))
        return self.commit("root reference fixture")

    def freeze(self):
        for p in self.repo.rglob("*"):
            if p.is_file():
                p.chmod(0o444)
        for p in sorted(self.repo.rglob("*"), reverse=True):
            if p.is_dir():
                p.chmod(0o555)
        self.repo.chmod(0o555)
        return self.snapshot()

    def snapshot(self):
        return {str(p.relative_to(self.repo)): (p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in self.repo.rglob("*") if p.is_file()}

    def test_rooted_archive_external_and_original_reproduction(self):
        end = self.pins([self.pin()])
        frozen = self.freeze()
        original = os.environ.get("ORIGINAL_FINALIZER")
        if original:
            out = self.root / "original-output"
            cp = subprocess.run([sys.executable, original, "--repo", str(self.repo),
                                 "--base", self.base, "--end", end, "--output", str(out)],
                                env=self.env, capture_output=True, text=True, timeout=30)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            old = json.loads((out / "publication-integrity.json").read_text())
            self.assertEqual([r["kind"] for r in old["publication_gaps"]], ["JSON_LINK_MISSING"])
            self.assertEqual(old["publication_gaps"][0]["target"], "validation/acceptance_matrix.json")
        index, result = self.invoke(end=end)
        self.assertEqual(result["publication_gaps"], [])
        self.assertEqual(result["hash_references"], [])
        self.assertEqual(index["counts"]["external_root_references"], 1)
        self.assertEqual(result["external_root_references"][0]["status"], "EXTERNAL_UNVERIFIED")
        self.assertNotIn("actual_sha256", result["external_root_references"][0])
        self.assertEqual(result["external_root_references"][0]["target"], "archive:validation/acceptance_matrix.json")
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_archive_collision_does_not_verify_product_copy(self):
        self.write("validation/acceptance_matrix.json", '{"different":"product bytes"}\n')
        end = self.pins([self.pin()])
        frozen = self.freeze()
        _, result = self.invoke(end=end)
        self.assertEqual(result["hash_references"], [])
        self.assertEqual(result["external_root_references"][0]["status"], "EXTERNAL_UNVERIFIED")
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_product_paths_validate_all_roots(self):
        entries = []
        for path in ("fixtures/payload.txt", "plugins/payload.txt", "docs/payload.txt"):
            self.write(path, "payload")
            entries.append(self.pin("product", path, b"payload"))
        end = self.pins(entries)
        frozen = self.freeze()
        _, result = self.invoke(end=end)
        self.assertEqual(len(result["hash_references"]), 3)
        self.assertEqual({r["status"] for r in result["hash_references"]}, {"PASS"})
        self.assertEqual(result["external_root_references"], [])
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_product_missing_refused(self):
        end = self.pins([self.pin("product", "fixtures/missing.txt")])
        frozen = self.freeze()
        cp = self.invoke(end=end, success=False)
        self.assertIn("PUBLIC_REFERENCE_MISSING", cp.stderr)
        self.assertFalse((self.root / "output").exists())
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_product_hash_and_size_drift_refused(self):
        self.write("fixtures/payload.txt", "changed")
        end = self.pins([self.pin("product", "fixtures/payload.txt", b"earlier")])
        frozen = self.freeze()
        cp = self.invoke(end=end, success=False)
        self.assertIn("PUBLIC_REFERENCE_MISMATCH", cp.stderr)
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_product_byte_count_drift_refused(self):
        self.write("fixtures/payload.txt", "payload")
        item = self.pin("product", "fixtures/payload.txt", b"payload")
        end = self.pins([{**item, "bytes": item["bytes"] + 1}])
        frozen = self.freeze()
        cp = self.invoke(end=end, success=False)
        self.assertIn("PUBLIC_REFERENCE_MISMATCH", cp.stderr)
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_external_output_can_be_inventoried_again(self):
        self.pins([self.pin()])
        _, result = self.invoke()
        self.write("analysis/report/coverage.json", json.dumps(result))
        end = self.commit("inventory previous coverage output")
        frozen = self.freeze()
        _, reread = self.invoke(end=end, output=self.root / "reread")
        self.assertEqual(reread["publication_gaps"], [])
        self.assertEqual(reread["findings"], [])
        self.assertEqual(len(reread["external_root_references"]), 1)
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_invalid_bindings_cannot_hide_gaps(self):
        good = self.pin()
        cases = [{**good, "root": "unknown", "id": "unknown:" + good["path"]},
                 {**good, "id": "product:" + good["path"]},
                 {**good, "path": "../validation/acceptance_matrix.json",
                  "id": "archive:../validation/acceptance_matrix.json"},
                 {**good, "path": "validation/../acceptance_matrix.json",
                  "id": "archive:validation/../acceptance_matrix.json"},
                 {**good, "path": "/validation/acceptance_matrix.json",
                  "id": "archive:/validation/acceptance_matrix.json"},
                 {**good, "path": "validation/%2e%2e/acceptance_matrix.json",
                  "id": "archive:validation/%2e%2e/acceptance_matrix.json"},
                 {**good, "public_path": "docs/missing.json"},
                 {**good, "public_sha256": "0" * 64},
                 {**good, "public_bytes": 4},
                 {**good, "sha256": "invalid"}, {**good, "bytes": True},
                 {k: v for k, v in good.items() if k != "root"},
                 {k: v for k, v in good.items() if k != "id"}, None]
        for n, bad in enumerate(cases):
            with self.subTest(case=n):
                end = self.pins([bad])
                before = self.snapshot()
                cp = self.invoke(end=end, output=self.root / ("bad-root-" + str(n)), success=False)
                self.assertIn("INVALID_ROOT_REFERENCE", cp.stderr)
                self.assertEqual(self.snapshot(), before)
        self.pins([good, good])
        cp = self.invoke(output=self.root / "duplicate", success=False)
        self.assertIn("INVALID_ROOT_REFERENCE", cp.stderr)

    def test_rooted_archive_does_not_hide_sibling_or_unbound_reference(self):
        end = self.pins([{**self.pin(), "reference": "docs/missing.json"}])
        frozen = self.freeze()
        _, result = self.invoke(end=end)
        self.assertEqual([r["target"] for r in result["publication_gaps"]], ["docs/missing.json"])
        self.assertEqual(len(result["external_root_references"]), 1)
        self.assertEqual(self.snapshot(), frozen)

    def test_rooted_label_without_schema_does_not_waive_link(self):
        self.write("docs/source.json", json.dumps(self.pin()))
        end = self.commit("unbound root label")
        frozen = self.freeze()
        _, result = self.invoke(end=end)
        self.assertEqual(len(result["publication_gaps"]), 1)
        self.assertEqual(result["external_root_references"], [])
        self.assertEqual(self.snapshot(), frozen)

    def test_root_manifest_and_odd_paths(self):
        self.write("odd name\nwith-tab\t.txt", "literal path")
        self.write("MANIFEST.json", json.dumps({"files": [
            {"path": name, "sha256": hashlib.sha256((self.repo / name).read_bytes()).hexdigest()}
            for name in ("seed.txt", "odd name\nwith-tab\t.txt")]}))
        self.commit("root package")
        index, _ = self.invoke()
        self.assertEqual(index["counts"]["manifests"], 1)
        self.assertIn("odd name\nwith-tab\t.txt", [r["path"] for r in index["changed_paths"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
