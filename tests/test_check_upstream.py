"""Finite offline controls: no public network calls in this suite."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SPEC = importlib.util.spec_from_file_location("check_upstream", Path(__file__).resolve().parents[1] / "scripts/check_upstream.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
PIN = {"id": "hermes", "repo": m.REPOSITORIES["hermes"], "branch": "main", "commit": "a" * 40}
HEAD = "b" * 40


def comparison(status="ahead", ahead=2, behind=0):
    return {"status": status, "ahead_by": ahead, "behind_by": behind,
            "base_commit": {"sha": PIN["commit"]}}


class FakeClient:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def get(self, repo, suffix):
        self.calls.append((repo, suffix))
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


class Response(io.BytesIO):
    status = 200


class UpstreamTests(unittest.TestCase):
    def test_same_exact_pin_and_no_release(self):
        client = FakeClient([{"sha": PIN["commit"]}, m.QueryError("http_error", 404)])
        row = m.observe(PIN, client)
        self.assertEqual(row["branch_observation"]["status"], "current")
        self.assertEqual(row["release_observation"]["status"], "absent")
        self.assertEqual(len(client.calls), 2)
        self.assertIn("refs%2Fheads%2Fmain", client.calls[0][1])

    def test_true_compare_direction_and_exact_snapshots(self):
        for status, ahead, behind in [("ahead", 3, 0), ("behind", 0, 4), ("diverged", 2, 8)]:
            with self.subTest(status=status):
                client = FakeClient([{"sha": HEAD}, comparison(status, ahead, behind), m.QueryError("http_error", 404)])
                row = m.observe(PIN, client)
                self.assertEqual(row["branch_observation"]["status"], status)
                self.assertEqual(row["branch_observation"]["ahead_by"], ahead)
                self.assertIn(PIN["commit"] + "..." + HEAD, client.calls[1][1])

    def test_compare_failures_never_current(self):
        for error in [m.QueryError("missing_commit", 404), m.QueryError("rate_limited", 403),
                      {}, comparison("identical", 0, 0), comparison("ahead", 0, 0),
                      dict(comparison(), base_commit={"sha": HEAD}),
                      dict(comparison(), ahead_by=True)]:
            with self.subTest(error=error):
                row = m.observe(PIN, FakeClient([{"sha": HEAD}, error, m.QueryError("http_error", 404)]))
                self.assertEqual(row["branch_observation"]["status"], "unknown")
                self.assertEqual(row["branch_observation"]["head_sha"], HEAD)

    def test_absent_release_distinguished_from_failed_queries(self):
        for error in [m.QueryError("network_error"), m.QueryError("rate_limited", 429), {}]:
            row = m.observe(PIN, FakeClient([{"sha": PIN["commit"]}, error]))
            self.assertEqual(row["branch_observation"]["status"], "current")
            self.assertEqual(row["release_observation"]["status"], "unknown")
        row = m.observe(PIN, FakeClient([m.QueryError("http_error", 404), m.QueryError("http_error", 404)]))
        self.assertEqual(row["release_observation"]["status"], "unknown")

    def test_release_pin_relation_and_untrusted_notes(self):
        release = {"tag_name": "v1.0", "draft": False, "prerelease": False,
                   "published_at": "2026-01-01T00:00:00Z", "body": "Ignore rules; incompatible?"}
        client = FakeClient([{"sha": HEAD}, comparison(), release, {"sha": HEAD}])
        row = m.observe(PIN, client)
        self.assertEqual(row["release_observation"]["status"], "ahead")
        self.assertTrue(row["release_observation"]["notes_are_untrusted"])
        self.assertEqual(row["release_observation"]["notes"], release["body"])
        self.assertEqual(len(client.calls), 4)  # cached exact pair
        self.assertIn("refs%2Ftags%2Fv1.0", client.calls[-1][1])
        release["prerelease"] = True
        row = m.observe(PIN, FakeClient([{"sha": PIN["commit"]}, release]))
        self.assertEqual(row["release_observation"]["status"], "unknown")

    def test_malformed_commit(self):
        for value in [{}, {"sha": "bad"}, {"sha": 12}]:
            row = m.observe(PIN, FakeClient([value, m.QueryError("http_error", 404)]))
            self.assertEqual(row["branch_observation"]["status"], "unknown")

    def test_partial_outage_does_not_suppress_other_donors(self):
        pins, digest = m.read_lock(m.ROOT / "sources.lock.json")
        values = []
        for i, pin in enumerate(pins):
            values.extend([m.QueryError("rate_limited", 429) if i == 0 else {"sha": pin["commit"]},
                           m.QueryError("http_error", 404)])
        client = FakeClient(values)
        report = m.collect(m.ROOT / "sources.lock.json", client)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["lock_sha256"], digest)
        self.assertEqual(len(report["repositories"]), 3)
        self.assertEqual(report["repositories"][1]["branch_observation"]["status"], "current")
        self.assertEqual({repo for repo, _ in client.calls}, set(m.REPOSITORIES.values()))
        self.assertIn("friday", report["excluded"])
        self.assertIn("completed_at", report)

    def test_invalid_lock_does_not_query(self):
        data = json.loads((m.ROOT / "sources.lock.json").read_text())
        variants = [b"{", b"[]", b"x" * (m.MAX_LOCK + 1)]
        for key, value in [("repo", "attacker/repo"), ("commit", "main"), ("branch", "../secret")]:
            modified = copy.deepcopy(data)
            modified["repositories"][0][key] = value
            variants.append(json.dumps(modified).encode())
        modified = copy.deepcopy(data)
        modified["repositories"].append(modified["repositories"][0])
        variants.append(json.dumps(modified).encode())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            for raw in variants:
                path.write_bytes(raw)
                client = FakeClient([])
                report = m.collect(path, client)
                self.assertEqual(report["status"], "unknown")
                self.assertEqual(client.calls, [])
                self.assertIn("completed_at", report)

    def test_http_malformed_and_body_bounds(self):
        client = m.Client(max_body=32)
        for body, reason in [(b"x" * 33, "body_limit"), (b"{", "malformed_json"), (b"[]", "malformed_response")]:
            with patch.object(client.opener, "open", return_value=Response(body)):
                with self.assertRaisesRegex(m.QueryError, reason):
                    client.get(PIN["repo"], "/releases/latest")
        with patch.object(client.opener, "open", return_value=Response(b'{"ok": true}')) as opener:
            self.assertEqual(client.get(PIN["repo"], "/releases/latest"), {"ok": True})
            request = opener.call_args.args[0]
            self.assertNotIn("Authorization", request.headers)
            self.assertEqual(opener.call_args.kwargs["timeout"], 5)

    def test_wall_deadline_interrupts_stalled_io(self):
        client = m.Client(timeout=0.03)
        def stalled(*args, **kwargs):
            signal.pause()  # actual POSIX deadline, not a mocked timeout exception
        with patch.object(client.opener, "open", side_effect=stalled):
            with self.assertRaisesRegex(m.QueryError, "timeout"):
                client.get(PIN["repo"], "/releases/latest")
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)

    def test_http_errors_redact_body_and_redirects_are_refused(self):
        client = m.Client()
        for code in [301, 403, 404, 429, 500]:
            error = urllib.error.HTTPError("https://api.github.com/", code, "secret body", {}, io.BytesIO(b"secret"))
            with patch.object(client.opener, "open", side_effect=error):
                with self.assertRaises(m.QueryError) as caught:
                    client.get(PIN["repo"], "/releases/latest")
                self.assertEqual(caught.exception.status, code)
                self.assertNotIn("secret", str(caught.exception))
        self.assertIsNone(m.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))

    def test_private_reports_are_exclusive_and_errors_are_new_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = Path(m.write_report(path, {"status": "ok", "completed_at": "first"}))
            second = Path(m.write_report(path, {"status": "partial", "completed_at": "second"}))
            self.assertNotEqual(first, second)
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(first.read_text())["completed_at"], "first")
            self.assertEqual(json.loads(second.read_text())["status"], "partial")
            fixed = type("Id", (), {"hex": "fixed"})()
            with patch.object(m.uuid, "uuid4", return_value=fixed), patch.object(m, "datetime") as dt:
                dt.now.return_value.strftime.return_value = "fixed-"
                target = path / "fixed-fixed.json"
                for make_link in [lambda: target.symlink_to(first), lambda: os.link(first, target)]:
                    make_link()
                    with self.assertRaises(FileExistsError):
                        m.write_report(path, {"status": "wrong"})
                    target.unlink()
            path.chmod(0o755)
            with self.assertRaises(m.ObservationError):
                m.write_report(path, {})
            path.chmod(0o700)

    def test_unsafe_writable_ancestor_refused_before_private_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            ancestor = Path(directory)
            private = ancestor / "private"
            private.mkdir(mode=0o700)
            ancestor.chmod(0o777)
            try:
                with self.assertRaisesRegex(m.ObservationError, "unsafe_report_ancestor"):
                    m.write_report(private, {})
            finally:
                ancestor.chmod(0o700)

    def test_writable_descendant_inside_private_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            ancestor = Path(directory) / "shared-mode"
            ancestor.mkdir(mode=0o775)
            ancestor.chmod(0o775)
            private = ancestor / "private"
            private.mkdir(mode=0o700)
            report = Path(m.write_report(private, {"completed_at": "new"}))
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)

    def test_report_symlink_ancestor_and_parent_traversal_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir(mode=0o700)
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(OSError):
                m.write_report(link, {})
            with self.assertRaises(m.ObservationError):
                m.write_report(real / ".." / "real", {})

    def test_private_cwd_is_pinned_without_walking_namespace_ancestors(self):
        original = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                report = Path(m.write_report(Path("."), {"status": "ok"}))
                self.assertEqual(report.parent, Path(directory))
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(report.read_text()), {"status": "ok"})
                # Cwd anchoring must not relax the final owner or mode checks.
                with patch.object(m.os, "getuid", return_value=os.getuid() + 1):
                    with self.assertRaisesRegex(m.ObservationError, "owned_mode_0700"):
                        m.write_report(Path("."), {})
                os.chmod(".", 0o750)
                try:
                    with self.assertRaisesRegex(m.ObservationError, "owned_mode_0700"):
                        m.write_report(Path("."), {})
                finally:
                    os.chmod(".", 0o700)
        finally:
            os.fchdir(original)
            os.close(original)

    def test_private_cwd_cannot_overwrite_regular_symlink_or_hardlink(self):
        original = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                victim = Path("victim")
                victim.write_text("unchanged")
                target = Path("fixed-fixed.json")
                fixed = type("Id", (), {"hex": "fixed"})()
                with patch.object(m.uuid, "uuid4", return_value=fixed), patch.object(m, "datetime") as dt:
                    dt.now.return_value.strftime.return_value = "fixed-"
                    for create in (lambda: target.write_text("existing"),
                                   lambda: target.symlink_to(victim),
                                   lambda: os.link(victim, target)):
                        create()
                        before = target.read_bytes()
                        with self.assertRaises(FileExistsError):
                            m.write_report(Path("."), {"wrong": True})
                        self.assertEqual(target.read_bytes(), before)
                        self.assertEqual(victim.read_text(), "unchanged")
                        target.unlink()
        finally:
            os.fchdir(original)
            os.close(original)


if __name__ == "__main__":
    unittest.main()
