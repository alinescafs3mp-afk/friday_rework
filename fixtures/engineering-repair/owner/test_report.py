"""Immutable owner checks; never part of the worker's write grant."""
import hashlib
import json
from pathlib import Path
import unittest


EXPECTED = {
    "currency": "RUB", "records": 4,
    "period": {"from": "2026-10-01", "to": "2026-10-02"},
    "total_kwh": "33.00", "total_amount": "199.13",
    "meters": [
        {"meter": "M01", "customer": "Север", "kwh": "22.50", "amount": "144.00"},
        {"meter": "M02", "customer": "Юг", "kwh": "10.50", "amount": "55.13"},
    ],
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReportTests(unittest.TestCase):
    def test_actual_generated_report_matches_independent_totals(self):
        actual = json.loads(Path("/job/report.json").read_text(encoding="utf-8"))
        self.assertEqual(canonical(actual), canonical(EXPECTED))

    def test_returned_report_matches_same_independent_totals(self):
        actual = json.loads(Path("/returned/report.json").read_text(encoding="utf-8"))
        self.assertEqual(canonical(actual), canonical(EXPECTED))

    def test_returned_report_is_actual_application_output(self):
        actual = json.loads(Path("/job/report.json").read_text(encoding="utf-8"))
        returned = json.loads(Path("/returned/report.json").read_text(encoding="utf-8"))
        self.assertEqual(canonical(actual), canonical(returned))

    def test_effective_settings_repair_both_faults(self):
        config = json.loads(Path("/job/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(config, {"encoding": "cp1251", "delimiter": ";",
                                  "currency": "RUB", "input": "readings.csv",
                                  "output": "report.json"})

    def test_owner_and_application_are_read_only_and_home_absent(self):
        self.assertFalse(Path("/home").exists())
        for name in ("/owner/test_report.py", "/job/report.py", "/job/readings.csv",
                     "/job/settings.json", "/returned/report.json"):
            with self.assertRaises(OSError):
                with open(name, "ab") as stream:
                    stream.write(b"tampering")


if __name__ == "__main__":
    unittest.main()
