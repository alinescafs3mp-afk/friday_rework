"""Actual bounded offline controls. A0, REST, model and Telegram are NOT_RUN."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/engineering-repair"
spec = importlib.util.spec_from_file_location("frw014_check", FIXTURE / "check.py")
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


class EngineeringFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="frw014-control-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = self.root / "settings.json"
        self.settings.write_bytes((FIXTURE / "calibration/settings.json").read_bytes())
        self.report = self.root / "report.json"
        self.good = checker.run(self.settings)
        self.assertEqual(self.good.returncode, 0, self.good.stderr)
        self.report.write_bytes(self.good.stdout)
        self.before = {p: p.read_bytes() for p in (FIXTURE / "input").iterdir()}
        self.before[FIXTURE / "owner/test_report.py"] = (FIXTURE / "owner/test_report.py").read_bytes()
        self.addCleanup(self.assert_immutable)

    def assert_immutable(self):
        for path, data in self.before.items():
            self.assertEqual(path.read_bytes(), data)

    def setting(self, **changes):
        data = json.loads(self.settings.read_bytes())
        data.update(changes)
        self.settings.write_text(json.dumps(data), encoding="utf-8")

    def refused_before_execution(self, **kwargs):
        with patch.object(checker.subprocess, "run", side_effect=AssertionError("must not execute")):
            result = checker.run(self.settings, self.report, **kwargs)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(result.accepted)
        self.assertIn(b"FIXTURE_REFUSED", result.stderr)

    def test_original_fault_is_actual_unicode_failure(self):
        result = checker.run(FIXTURE / "input/settings.json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b"UnicodeDecodeError", result.stderr)
        self.assertNotIn(b"FIXTURE_REFUSED", result.stderr)
        self.assertFalse(result.accepted)

    def test_encoding_only_repair_exposes_second_fault(self):
        self.setting(delimiter=",")
        result = checker.run(self.settings)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b"CSV columns; check delimiter", result.stderr)

    def test_delimiter_only_repair_keeps_encoding_failure(self):
        self.setting(encoding="utf-8")
        result = checker.run(self.settings)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b"UnicodeDecodeError", result.stderr)

    def test_known_corrected_config_passes_original_owner_checks(self):
        result = checker.run(self.settings, self.report)
        self.assertTrue(result.accepted, result.stderr)
        self.assertIn(b"Ran 5 tests", result.stderr)
        actual = json.loads(result.stdout)
        self.assertEqual(actual["total_amount"], "199.13")
        self.assertEqual(actual["meters"][1]["amount"], "55.13")

    def test_reproduction_exit_zero_is_not_owner_acceptance(self):
        self.assertFalse(self.good.accepted)
        self.assertNotIn(b"Ran 5 tests", self.good.stderr)

    def test_real_limits_observed_inside_sandbox(self):
        line = next(s for s in self.good.stderr.splitlines() if s.startswith(b"CHECK_LIMITS: "))
        info = json.loads(line.split(b": ", 1)[1])
        self.assertEqual(len(info["affinity"]), 2)
        self.assertEqual(info["address_space"], [1 << 30, 1 << 30])
        self.assertEqual(info["cpu_seconds"], [3, 3])
        self.assertEqual(info["file_bytes"], [65536, 65536])
        self.assertEqual(info["core_bytes"], [0, 0])

    def test_wrong_total_is_real_owner_failure(self):
        data = json.loads(self.report.read_bytes())
        data["total_amount"] = "200.00"
        self.report.write_text(json.dumps(data), encoding="utf-8")
        result = checker.run(self.settings, self.report)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(b"FAILED", result.stderr)
        self.assertFalse(result.accepted)

    def test_correct_global_total_with_wrong_meter_is_failure(self):
        data = json.loads(self.report.read_bytes())
        data["meters"][0]["amount"] = "143.99"
        self.report.write_text(json.dumps(data), encoding="utf-8")
        result = checker.run(self.settings, self.report)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(result.accepted)

    def test_missing_records_and_extra_fields_are_not_partial_success(self):
        original = json.loads(self.report.read_bytes())
        for data in ({"total_amount": "199.13"}, dict(original, plausible="success"),
                     dict(original, records=4.0)):
            with self.subTest(data=data):
                self.report.write_text(json.dumps(data), encoding="utf-8")
                result = checker.run(self.settings, self.report)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(result.accepted)

    def test_self_attested_success_text_is_refused(self):
        self.report.write_bytes(b"All tests passed\n")
        self.refused_before_execution()

    def test_duplicate_truncated_nonfinite_and_nonobject_json_refused(self):
        for value in (b'{"records":4,"records":4}', b'{"records":', b'{"x":NaN}',
                      b'{"x":1e400}', b'[]'):
            with self.subTest(value=value):
                self.report.write_bytes(value)
                self.refused_before_execution()

    def test_deep_valid_json_with_wrong_report_shape_fails_owner_checks(self):
        # Valid JSON is not automatically malformed at a particular Python
        # parser recursion threshold. Actual unchanged owner checks must fail.
        self.report.write_bytes(b'{"x":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}')
        result = checker.run(self.settings, self.report)
        self.assertFalse(result.accepted)
        self.assertNotEqual(result.returncode, 0)

    def test_unknown_settings_and_extra_keys_refused(self):
        for config in ({"encoding": "utf-16"}, {"delimiter": "|"},
                       {"currency": "USD"}, {"extra": "ignored"}):
            with self.subTest(config=config):
                self.settings.write_bytes((FIXTURE / "calibration/settings.json").read_bytes())
                self.setting(**config)
                self.refused_before_execution()

    def test_escaping_input_and_output_paths_refused_without_effects(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"preserve")
        for key in ("input", "output"):
            for path in ("../sentinel", str(sentinel), "/etc/passwd", "nested/report.json"):
                with self.subTest(key=key, path=path):
                    self.settings.write_bytes((FIXTURE / "calibration/settings.json").read_bytes())
                    self.setting(**{key: path})
                    self.refused_before_execution()
                    self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_tampered_application_not_executed(self):
        app = self.root / "report.py"
        app.write_bytes(b"raise RuntimeError('candidate code must not execute')\n")
        self.refused_before_execution(application=app)

    def test_tampered_owner_copy_is_refused_before_execution(self):
        other = self.root / "fake-owner-fixture"
        (other / "input").mkdir(parents=True)
        (other / "owner").mkdir()
        for name in ("report.py", "readings.csv"):
            (other / "input" / name).write_bytes((FIXTURE / "input" / name).read_bytes())
        (other / "owner/test_report.py").write_bytes(b"print('forged pass')\n")
        with patch.object(checker, "FIXTURE", other):
            self.refused_before_execution()

    def test_changed_readings_not_accepted_as_new_input(self):
        readings = self.root / "readings.csv"
        readings.write_bytes((FIXTURE / "input/readings.csv").read_bytes().replace(b"12.50", b"12.51"))
        self.refused_before_execution(readings=readings)

    def test_missing_input_and_missing_output_refused(self):
        self.refused_before_execution(readings=self.root / "absent.csv")
        self.report.unlink()
        self.refused_before_execution()

    def test_missing_settings_refused(self):
        self.settings.unlink()
        self.refused_before_execution()

    def test_file_symlink_parent_symlink_and_hardlink_refused(self):
        for kind in ("symlink", "parent", "hardlink"):
            with self.subTest(kind=kind):
                link = self.root / kind
                if kind == "symlink":
                    link.symlink_to(self.report)
                    candidate = link
                elif kind == "parent":
                    link.symlink_to(self.root, target_is_directory=True)
                    candidate = link / "report.json"
                else:
                    os.link(self.report, link)
                    candidate = link
                with patch.object(checker.subprocess, "run", side_effect=AssertionError("must not execute")):
                    result = checker.run(self.settings, candidate)
                self.assertFalse(result.accepted)
                self.assertIn(b"FIXTURE_REFUSED", result.stderr)
                link.unlink()

    def test_fifo_and_oversize_refused_without_blocking(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        big = self.root / "big.json"
        big.write_bytes(b" " * 65537)
        for candidate in (fifo, big):
            result = checker.run(self.settings, candidate)
            self.assertEqual(result.returncode, 2)
            self.assertLess(result.elapsed_seconds, 1)
            self.assertFalse(result.accepted)

    def test_relative_and_dotdot_artifact_paths_refused(self):
        for candidate in ("report.json", str(self.root) + "/../" + self.root.name + "/report.json"):
            result = checker.run(self.settings, candidate)
            self.assertIn(b"noncanonical artifact path", result.stderr)
            self.assertFalse(result.accepted)

    def test_returned_config_formatting_is_allowed(self):
        data = json.loads(self.settings.read_bytes())
        self.settings.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))
        result = checker.run(self.settings, self.report)
        self.assertTrue(result.accepted, result.stderr)

    def test_cli_checks_actual_files(self):
        result = subprocess.run([sys.executable, "-B", str(FIXTURE / "check.py"),
                                 "--settings", str(self.settings), "--report", str(self.report)],
                                capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'"accepted": true', result.stdout)
        self.assertIn(b"Ran 5 tests", result.stderr)

    def test_snapshots_mount_read_only_no_home_no_network_namespace_share(self):
        result = checker.run(self.settings, self.report)
        self.assertTrue(result.accepted, result.stderr)
        self.assertIn("--unshare-all", result.command)
        self.assertIn("--clearenv", result.command)
        self.assertNotIn("--share-net", result.command)
        self.assertIn(b"test_owner_and_application_are_read_only_and_home_absent", result.stderr)
        snapshots = [value for value in result.command if value.startswith("/tmp/frw014-owner-")]
        self.assertTrue(snapshots)
        self.assertTrue(all(not Path(value).exists() for value in snapshots))

    def test_exact_manifest_and_prepared_mapping_do_not_grant_live_effects(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
        mapping = json.loads((FIXTURE / "mapping.json").read_bytes())
        self.assertEqual(manifest["state"], "PREPARED_SOURCE_ONLY")
        self.assertEqual(mapping["state"], "PREPARED_NOT_RUN")
        self.assertEqual(mapping["delivery"], "NOT_RUN")
        self.assertEqual(len(mapping["input_files"]), 3)
        self.assertEqual(len(mapping["output_files"]), 4)
        for relative, expected in manifest["pins"].items():
            actual = (FIXTURE / relative).read_bytes()
            self.assertEqual(len(actual), expected["bytes"])
            self.assertEqual(hashlib.sha256(actual).hexdigest(), expected["sha256"])
        for item in mapping["input_files"]:
            self.assertEqual(item["sha256"], manifest["pins"]["input/" + item["logical_name"]]["sha256"])
        for output in mapping["output_files"]:
            self.assertEqual(output["native_path_template"],
                             "/a0/usr/workdir/<prefix>/<prefix>-" + output["logical_name"])


if __name__ == "__main__":
    unittest.main()
