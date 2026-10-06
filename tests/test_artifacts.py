"""Stable-byte component controls; no native transfer or provenance acceptance.

Filesystem operations are real. Patches inject faults or deterministic mutations
at syscall boundaries, so neither sleeps nor thread scheduling affect coverage.
"""
from dataclasses import replace
import errno
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


_path = Path(__file__).resolve().parents[1] / "plugins/friday_rework/artifacts.py"
_spec = importlib.util.spec_from_file_location("friday_artifacts_test", _path)
artifacts = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = artifacts
_spec.loader.exec_module(artifacts)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="friday-artifact-control-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.staging = self.root / "staging"
        self.source.mkdir(mode=0o700)
        self.staging.mkdir(mode=0o700)
        self.payload = bytes(range(256)) * 600
        self.file = self.source / "report.dat"
        self.file.write_bytes(self.payload)

    def stage(self, **changes):
        args = dict(source_root=self.source, relative_path="report.dat",
                    staging_root=self.staging, logical_name="report.dat",
                    media_type="application/octet-stream", origin_reference="fixture:source",
                    max_bytes=len(self.payload) + 100)
        args.update(changes)
        return artifacts.stage_file(**args)

    def read(self, artifact, **changes):
        args = dict(staging_root=self.staging, artifact=artifact,
                    max_bytes=len(self.payload) + 100)
        args.update(changes)
        return artifacts.read_staged(**args)

    def empty_staging(self):
        self.assertEqual(list(self.staging.iterdir()), [])

    def after_first_read(self, callback):
        real_read = os.read
        called = False

        def read(fd, count):
            nonlocal called
            result = real_read(fd, count)
            if result and not called:
                called = True
                callback()
            return result

        return patch.object(artifacts.os, "read", side_effect=read)

    def test_exact_bytes_hash_permissions_and_fsync(self):
        real_fsync = os.fsync
        synced = []

        def fsync(fd):
            synced.append(stat.S_IFMT(os.fstat(fd).st_mode))
            return real_fsync(fd)

        with patch.object(artifacts.os, "fsync", side_effect=fsync):
            row = self.stage(max_bytes=len(self.payload))
        staged = self.staging / row.reference
        self.assertRegex(row.reference, r"^[0-9a-f]{32}\.dat$")
        self.assertEqual(row.sha256, hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(row.size_bytes, len(self.payload))
        self.assertEqual(row.origin_reference, "fixture:source")
        self.assertEqual(row.logical_name, "report.dat")
        self.assertEqual(row.media_type, "application/octet-stream")
        self.assertTrue(row.complete)
        self.assertEqual(row.verification, "verified")
        self.assertEqual(staged.read_bytes(), self.payload)
        self.assertEqual(stat.S_IMODE(staged.stat().st_mode), 0o400)
        self.assertEqual(staged.stat().st_nlink, 1)
        self.assertEqual(synced, [stat.S_IFREG, stat.S_IFDIR])
        delivered = self.read(row)
        self.assertIsInstance(delivered, bytes)
        self.assertEqual(delivered, self.payload)
        self.assertEqual(self.file.read_bytes(), self.payload)
        self.assertEqual(list(self.staging.iterdir()), [staged])

    def test_same_logical_names_keep_distinct_exact_copies(self):
        first = self.stage()
        self.file.write_bytes(b"second version")
        second = self.stage()
        self.assertNotEqual(first.reference, second.reference)
        self.assertEqual(self.read(first), self.payload)
        self.assertEqual(self.read(second), b"second version")

    def test_forced_final_collision_preserves_existing_file(self):
        fixed = SimpleNamespace(hex="a" * 32)
        with patch.object(artifacts.uuid, "uuid4", return_value=fixed):
            first = self.stage()
            self.file.write_bytes(b"replacement")
            with self.assertRaises(FileExistsError):
                self.stage()
        self.assertEqual(self.read(first), self.payload)
        self.assertEqual([p.name for p in self.staging.iterdir()], [first.reference])

    def test_existing_partial_name_is_preserved(self):
        fixed = SimpleNamespace(hex="b" * 32)
        existing = self.staging / ("." + fixed.hex + ".dat.partial")
        existing.write_bytes(b"owned earlier temporary")
        with patch.object(artifacts.uuid, "uuid4", return_value=fixed):
            with self.assertRaises(FileExistsError):
                self.stage()
        self.assertEqual(existing.read_bytes(), b"owned earlier temporary")
        self.assertEqual(list(self.staging.iterdir()), [existing])

    def test_nested_regular_file_is_supported(self):
        nested = self.source / "nested"
        nested.mkdir()
        self.file.rename(nested / "report.dat")
        row = self.stage(relative_path="nested/report.dat")
        self.assertEqual(self.read(row), self.payload)

    def test_empty_file_and_exact_ceiling(self):
        self.file.write_bytes(b"")
        row = self.stage(max_bytes=1)
        self.assertEqual(row.size_bytes, 0)
        self.assertEqual(row.sha256, hashlib.sha256(b"").hexdigest())
        self.assertEqual(self.read(row, max_bytes=1), b"")

    def test_logical_filename_cannot_select_output_path(self):
        for label in ("../../outside.txt", "/absolute/name", "report.bad-ext", "no_suffix"):
            with self.subTest(label=label):
                row = self.stage(logical_name=label)
                self.assertEqual(row.logical_name, label)
                self.assertEqual(Path(row.reference).name, row.reference)
                self.assertEqual(self.read(row), self.payload)

    def test_invalid_relative_paths(self):
        for relative in ("", ".", "..", "../report.dat", "nested/../report.dat",
                         "./report.dat", "nested/./report.dat", "/report.dat",
                         str(self.file), "nested//report.dat", "report.dat/", "a\x00b"):
            with self.subTest(relative=relative), self.assertRaises(artifacts.ArtifactError):
                self.stage(relative_path=relative)
            self.empty_staging()

    def test_missing_source_and_directory_are_rejected(self):
        (self.source / "directory").mkdir()
        for relative in ("missing", "directory"):
            with self.subTest(relative=relative), self.assertRaises((OSError, artifacts.ArtifactError)):
                self.stage(relative_path=relative)
            self.empty_staging()

    def test_fifo_is_rejected_without_waiting_for_writer(self):
        os.mkfifo(self.source / "pipe", 0o600)
        with self.assertRaisesRegex(artifacts.ArtifactError, "unsafe_artifact_file"):
            self.stage(relative_path="pipe")
        self.empty_staging()

    def test_source_leaf_and_directory_symlinks_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret").write_bytes(b"outside")
        (self.source / "leaf").symlink_to(outside / "secret")
        (self.source / "directory").symlink_to(outside, target_is_directory=True)
        for relative in ("leaf", "directory/secret"):
            with self.subTest(relative=relative), self.assertRaises(OSError):
                self.stage(relative_path=relative)
            self.empty_staging()

    def test_hardlinked_source_is_rejected(self):
        os.link(self.file, self.source / "alias")
        with self.assertRaisesRegex(artifacts.ArtifactError, "unsafe_artifact_file"):
            self.stage()
        self.empty_staging()

    def test_roots_must_exist_be_absolute_and_not_symlinked(self):
        source_alias = self.root / "source-alias"
        source_alias.symlink_to(self.source, target_is_directory=True)
        stage_alias = self.root / "stage-alias"
        stage_alias.symlink_to(self.staging, target_is_directory=True)
        for changes in ({"source_root": "relative"}, {"source_root": source_alias},
                        {"staging_root": stage_alias}, {"staging_root": self.root / "missing"}):
            with self.subTest(changes=changes), self.assertRaises((OSError, artifacts.ArtifactError)):
                self.stage(**changes)
            self.empty_staging()

    def test_staging_permissions_must_be_exactly_private(self):
        for mode in (0o755, 0o750, 0o770, 0o777, 0o2700):
            self.staging.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaisesRegex(artifacts.ArtifactError, "unsafe_artifact_root"):
                self.stage()
            self.empty_staging()
        self.staging.chmod(0o700)

    def test_invalid_limits_and_labels_fail_before_writes(self):
        for value in (0, -1, True, 1.0, None, "1"):
            with self.subTest(limit=value), self.assertRaises(artifacts.ArtifactError):
                self.stage(max_bytes=value)
        for field, ceiling in (("logical_name", 512), ("media_type", 256), ("origin_reference", 2048)):
            for value in ("", "x\x00y", None, "é" * (ceiling // 2 + 1)):
                with self.subTest(field=field, value=repr(value)[:30]), self.assertRaises(artifacts.ArtifactError):
                    self.stage(**{field: value})
        self.empty_staging()

    def test_initial_size_ceiling_rejects_before_output(self):
        with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_too_large"):
            self.stage(max_bytes=len(self.payload) - 1)
        self.empty_staging()

    def test_source_same_size_edit_during_read_is_rejected(self):
        def mutate():
            with self.file.open("r+b") as stream:
                stream.seek(70000)
                stream.write(b"changed!")
        with self.after_first_read(mutate), self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
            self.stage()
        self.empty_staging()

    def test_source_replacement_during_read_is_rejected(self):
        def replace_source():
            self.file.rename(self.source / "old")
            self.file.write_bytes(self.payload)
        with self.after_first_read(replace_source), self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
            self.stage()
        self.empty_staging()

    def test_source_replacement_with_symlink_is_rejected(self):
        def replace_source():
            retained = self.source / "old"
            self.file.rename(retained)
            self.file.symlink_to(retained)
        with self.after_first_read(replace_source), self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
            self.stage()
        self.empty_staging()

    def test_source_truncation_during_read_is_rejected(self):
        with self.after_first_read(lambda: self.file.write_bytes(b"short")):
            with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
                self.stage()
        self.empty_staging()

    def test_growth_within_limit_is_still_rejected_as_mutation(self):
        def grow():
            with self.file.open("ab") as stream:
                stream.write(b"x")
        with self.after_first_read(grow), self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
            self.stage()
        self.empty_staging()

    def test_growth_beyond_ceiling_is_bounded_while_reading(self):
        real_read = os.read
        total = 0
        limit = len(self.payload)
        def read(fd, count):
            nonlocal total
            value = real_read(fd, count)
            if total == 0:
                with self.file.open("ab") as stream:
                    stream.write(b"x" * 10000)
            total += len(value)
            return value
        with patch.object(artifacts.os, "read", side_effect=read):
            with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_too_large"):
                self.stage(max_bytes=limit)
        self.assertEqual(total, limit + 1)
        self.empty_staging()

    def test_new_hardlink_during_read_is_rejected(self):
        with self.after_first_read(lambda: os.link(self.file, self.source / "alias")):
            with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
                self.stage()
        self.empty_staging()

    def test_partial_writes_are_completed_correctly(self):
        real_write = os.write
        counts = []
        def write(fd, data):
            count = real_write(fd, data[:997])
            counts.append(count)
            return count
        with patch.object(artifacts.os, "write", side_effect=write):
            row = self.stage()
        self.assertGreater(len(counts), 100)
        self.assertEqual(self.read(row), self.payload)

    def test_zero_or_negative_write_is_rejected_and_cleaned(self):
        for count in (0, -1):
            with self.subTest(count=count), patch.object(artifacts.os, "write", return_value=count):
                with self.assertRaisesRegex(artifacts.ArtifactError, "short_artifact_write"):
                    self.stage()
            self.empty_staging()
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_write_error_after_real_partial_write_cleans_up(self):
        real_write = os.write
        calls = 0
        def write(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[:17])
            raise OSError(errno.ENOSPC, "injected full filesystem")
        with patch.object(artifacts.os, "write", side_effect=write):
            with self.assertRaises(OSError):
                self.stage()
        self.assertEqual(calls, 2)
        self.empty_staging()
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_read_error_after_real_copy_cleans_up(self):
        real_read = os.read
        calls = 0
        def read(fd, count):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_read(fd, count)
            raise OSError(errno.EIO, "injected read failure")
        with patch.object(artifacts.os, "read", side_effect=read):
            with self.assertRaises(OSError):
                self.stage()
        self.empty_staging()
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_file_fsync_failure_cleans_up(self):
        with patch.object(artifacts.os, "fsync", side_effect=OSError(errno.EIO, "file fsync fault")):
            with self.assertRaises(OSError):
                self.stage()
        self.empty_staging()
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_permission_setting_failure_cleans_up_without_publication(self):
        with patch.object(artifacts.os, "fchmod", side_effect=OSError(errno.EPERM, "mode fault")):
            with self.assertRaises(OSError):
                self.stage()
        self.empty_staging()
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_link_failure_preserves_existing_files_and_cleans_temporary(self):
        earlier = self.stage()
        with patch.object(artifacts.os, "link", side_effect=OSError(errno.EIO, "link fault")):
            with self.assertRaises(OSError):
                self.stage()
        self.assertEqual(self.read(earlier), self.payload)
        self.assertEqual([p.name for p in self.staging.iterdir()], [earlier.reference])

    def test_directory_fsync_failure_raises_without_returning_manifest(self):
        real_fsync = os.fsync
        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(errno.EIO, "directory fsync fault")
            return real_fsync(fd)
        with patch.object(artifacts.os, "fsync", side_effect=fsync):
            with self.assertRaises(OSError):
                self.stage()
        # Publication already happened: an unreferenced complete file may remain.
        paths = list(self.staging.iterdir())
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].name.endswith(".partial"))
        self.assertEqual(paths[0].read_bytes(), self.payload)
        self.assertEqual(stat.S_IMODE(paths[0].stat().st_mode), 0o400)
        self.assertEqual(self.file.read_bytes(), self.payload)

    def test_read_rejects_unverified_or_invalid_manifests(self):
        row = self.stage()
        for changes in ({"complete": False}, {"verification": "unknown"},
                        {"size_bytes": -1}, {"size_bytes": True}, {"size_bytes": 1.0},
                        {"sha256": "f" * 63}, {"sha256": "F" * 64}):
            with self.subTest(changes=changes), self.assertRaises(artifacts.ArtifactError):
                self.read(replace(row, **changes))
        with self.assertRaises(artifacts.ArtifactError):
            self.read(object())
        with self.assertRaises(artifacts.ArtifactError):
            self.read(row, max_bytes=row.size_bytes - 1)

    def test_read_rejects_modified_bytes_even_if_size_and_mode_match(self):
        row = self.stage()
        staged = self.staging / row.reference
        staged.chmod(0o600)
        staged.write_bytes(b"X" * len(self.payload))
        staged.chmod(0o400)
        with self.assertRaisesRegex(artifacts.ArtifactError, "staged_artifact_changed"):
            self.read(row)

    def test_returned_bytes_remain_exact_after_path_changes(self):
        row = self.stage()
        payload = self.read(row)
        staged = self.staging / row.reference
        staged.unlink()
        staged.write_bytes(b"substituted after checked read")
        staged.chmod(0o400)
        self.assertIsInstance(payload, bytes)
        self.assertEqual(payload, self.payload)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), row.sha256)
        with self.assertRaises(artifacts.ArtifactError):
            self.read(row)

    def test_read_rejects_substituted_file_with_different_bytes(self):
        row = self.stage()
        staged = self.staging / row.reference
        staged.unlink()
        staged.write_bytes(b"Y" * len(self.payload))
        staged.chmod(0o400)
        with self.assertRaisesRegex(artifacts.ArtifactError, "staged_artifact_changed"):
            self.read(row)

    def test_read_rejects_unsafe_reference_symlink_and_hardlink(self):
        row = self.stage()
        staged = self.staging / row.reference
        alias = self.staging / "alias"
        alias.symlink_to(staged)
        for reference in ("../source/report.dat", str(staged), "./" + row.reference, "alias"):
            with self.subTest(reference=reference), self.assertRaises((OSError, artifacts.ArtifactError)):
                self.read(replace(row, reference=reference))
        alias.unlink()
        os.link(staged, alias)
        with self.assertRaisesRegex(artifacts.ArtifactError, "unsafe_artifact_file"):
            self.read(row)

    def test_read_rejects_wrong_mode_size_and_private_root(self):
        row = self.stage()
        staged = self.staging / row.reference
        staged.chmod(0o600)
        with self.assertRaisesRegex(artifacts.ArtifactError, "staged_artifact_changed"):
            self.read(row)
        staged.chmod(0o400)
        with self.assertRaisesRegex(artifacts.ArtifactError, "staged_artifact_changed"):
            self.read(replace(row, size_bytes=row.size_bytes + 1))
        self.staging.chmod(0o755)
        with self.assertRaisesRegex(artifacts.ArtifactError, "unsafe_artifact_root"):
            self.read(row)
        self.staging.chmod(0o700)

    def test_read_checks_replacement_after_last_byte(self):
        row = self.stage()
        staged = self.staging / row.reference
        real_read = os.read
        def read(fd, count):
            data = real_read(fd, count)
            if not data:
                staged.rename(self.staging / "original")
                staged.write_bytes(self.payload)
                staged.chmod(0o400)
            return data
        with patch.object(artifacts.os, "read", side_effect=read):
            with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
                self.read(row)

    def test_read_checks_mutation_after_last_byte(self):
        row = self.stage()
        staged = self.staging / row.reference
        real_read = os.read
        def read(fd, count):
            data = real_read(fd, count)
            if not data:
                staged.chmod(0o600)
                staged.write_bytes(b"Z" * len(self.payload))
                staged.chmod(0o400)
            return data
        with patch.object(artifacts.os, "read", side_effect=read):
            with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_changed_during_read"):
                self.read(row)

    def test_read_growth_is_bounded(self):
        row = self.stage()
        staged = self.staging / row.reference
        def grow():
            staged.chmod(0o600)
            with staged.open("ab") as stream:
                stream.write(b"x" * 10000)
            staged.chmod(0o400)
        with self.after_first_read(grow):
            with self.assertRaisesRegex(artifacts.ArtifactError, "artifact_too_large"):
                self.read(row, max_bytes=row.size_bytes)


if __name__ == "__main__":
    unittest.main()
