"""Offline refusal/control checks; never start systemd or set up a namespace."""
import contextlib
import errno
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("system_boundary", ROOT / "scripts/check_upstream_system.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class SystemBoundaryTests(unittest.TestCase):
    def test_direct_host_run_refuses_before_observer(self):
        # Real process, existing host namespace, no mounting/retry. The only
        # reachable operations before this refusal are reads of uid/status.
        result = subprocess.run(["/usr/bin/python3", "-I", "-B", str(SPEC.origin), "--verify-only"],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 3, result)
        self.assertIn("sandbox_boundary_refused:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_refusal_cannot_dispatch_observer(self):
        for failure in (m.BoundaryError("required_mount_not_readonly"), OSError(errno.EIO, "private"),
                        ValueError("invalid status")):
            with self.subTest(failure=type(failure).__name__), patch.object(m, "check_boundary", side_effect=failure), \
                    patch.object(m.runpy, "run_path") as run, patch.object(m.sys, "argv", ["guard"]), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(m.main(), 3)
                run.assert_not_called()
                self.assertNotIn("private", err.getvalue())

    def test_verify_only_cannot_dispatch_observer(self):
        with patch.object(m, "check_boundary", return_value={"sandbox_preflight": "ok"}), \
                patch.object(m.runpy, "run_path") as run, patch.object(m.sys, "argv", ["guard", "--verify-only"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(), 0)
            run.assert_not_called()

    def test_observation_dispatch_requires_success_and_fixed_arguments(self):
        order = []
        with patch.object(m, "check_boundary", side_effect=lambda: order.append("check") or {}), \
                patch.object(m.runpy, "run_path", side_effect=lambda *a, **kw: order.append("observe")) as run, \
                patch.object(m.sys, "argv", ["guard"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(), 0)
            self.assertEqual(order, ["check", "observe"])
            self.assertEqual(m.sys.argv[1:], ["--report-dir", "."])
            run.assert_called_once_with(str(m.ROOT / "scripts/check_upstream.py"), run_name="__main__")

    def test_privileged_identity_refused(self):
        with patch.object(m.os, "getuid", return_value=0), patch.object(m.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(m.BoundaryError, "privileged_identity"):
                m.check_boundary()

    def test_missing_privilege_controls_refused(self):
        valid = "NoNewPrivs:\t1\n" + "".join(k + ":\t0000\n" for k in
                                                ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
        variants = [(valid.replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"), "no_new_privileges_missing")]
        variants += [(valid.replace(k + ":\t0000", k + ":\t0001"), "capabilities_not_empty")
                     for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")]
        for status, reason in variants:
            with self.subTest(reason=reason, status=status), patch.object(m.Path, "read_text", return_value=status):
                with self.assertRaisesRegex(m.BoundaryError, reason):
                    m.check_boundary()

    def test_real_writable_mount_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(os.statvfs(directory).f_flag & os.ST_RDONLY)
            with self.assertRaisesRegex(m.BoundaryError, "required_mount_not_readonly"):
                m.readonly(Path(directory))

    def test_outside_open_success_fails_without_modifying_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control"
            path.write_bytes(b"unchanged")
            with self.assertRaisesRegex(m.BoundaryError, "outside_write_allowed"):
                m.denied_write(path)
            self.assertEqual(path.read_bytes(), b"unchanged")

    def test_only_erofs_is_accepted_as_mount_denial(self):
        for error in (errno.EACCES, errno.EPERM, errno.ENOENT, errno.ELOOP):
            with self.subTest(error=error), patch.object(m.os, "open", side_effect=OSError(error, "")):
                with self.assertRaisesRegex(m.BoundaryError, "outside_write_not_denied_by_readonly_mount"):
                    m.denied_write(Path("unused"))
        with patch.object(m.os, "open", side_effect=OSError(errno.EROFS, "")):
            m.denied_write(Path("unused"))

    def test_real_private_control_readback_and_cleanup(self):
        original = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                m.private_write()
                self.assertEqual(list(Path(".").iterdir()), [])
                os.chmod(".", 0o755)
                with self.assertRaisesRegex(m.BoundaryError, "unsafe_state_directory"):
                    m.private_write()
                self.assertEqual(list(Path(".").iterdir()), [])
        finally:
            os.chdir(original)

    def test_private_control_collision_preserves_existing_file(self):
        original = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                control = Path(".boundary-fixed")
                control.write_bytes(b"preserved")
                with patch.object(m.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")):
                    with self.assertRaises(FileExistsError):
                        m.private_write()
                self.assertEqual(control.read_bytes(), b"preserved")
        finally:
            os.chdir(original)

    def test_all_boundary_checks_and_late_refusals_precede_effects(self):
        status = "NoNewPrivs:\t1\n" + "".join(k + ":\t0000\n" for k in
                                             ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
        rootfile = SimpleNamespace(st_mode=0o100644, st_uid=0, st_nlink=1)
        control = SimpleNamespace(st_mode=0o100600, st_uid=os.geteuid(), st_nlink=1)
        source = m.ROOT / "scripts/check_upstream.py"
        variants = [(None, None, None),
                    (source, SimpleNamespace(st_mode=0o100664, st_uid=0), "unsafe_installed_source"),
                    (source, SimpleNamespace(st_mode=0o120777, st_uid=0), "unsafe_installed_source"),
                    (source, SimpleNamespace(st_mode=0o100644, st_uid=os.geteuid()), "unsafe_installed_source"),
                    (m.CONTROL, SimpleNamespace(st_mode=0o100600, st_uid=0, st_nlink=1), "unsafe_outside_control"),
                    (m.CONTROL, SimpleNamespace(st_mode=0o100600, st_uid=os.geteuid(), st_nlink=2), "unsafe_outside_control")]
        for changed, replacement, reason in variants:
            def fake_lstat(path):
                return replacement if path == changed else control if path == m.CONTROL else rootfile

            with self.subTest(reason=reason, changed=changed), \
                    patch.object(m.Path, "read_text", return_value=status), \
                    patch.object(m.Path, "cwd", return_value=m.STATE), \
                    patch.object(m.Path, "is_symlink", return_value=False), \
                    patch.object(m.Path, "lstat", fake_lstat), \
                    patch.object(m.Path, "stat", return_value=rootfile), \
                    patch.object(m.os, "statvfs", side_effect=lambda p: SimpleNamespace(f_flag=0 if p == "." else os.ST_RDONLY)), \
                    patch.object(m, "denied_write") as outside, patch.object(m, "private_write") as inside:
                if reason:
                    with self.assertRaisesRegex(m.BoundaryError, reason):
                        m.check_boundary()
                    outside.assert_not_called()
                    inside.assert_not_called()
                else:
                    self.assertEqual(m.check_boundary()["sandbox_preflight"], "ok")
                    outside.assert_called_once_with(m.CONTROL)
                    inside.assert_called_once_with()

    def test_system_unit_retains_boundary_and_owner_access(self):
        unit = (ROOT / "deploy/systemd/system/friday-upstream-check-system.service").read_text()
        for directive in ("User=jericho", "Group=jericho", "StateDirectoryMode=0700", "UMask=0077",
                          "ProtectSystem=strict", "ProtectHome=read-only", "NoNewPrivileges=yes",
                          "CapabilityBoundingSet=", "AmbientCapabilities=", "PrivateUsers=no",
                          "TimeoutStartSec=100", "KillMode=control-group", "RestrictNamespaces=yes"):
            self.assertIn(directive + "\n", unit)
        self.assertIn("ExecStart=/usr/bin/python3 -I -B " + str(m.ROOT / "scripts/check_upstream_system.py"), unit)
        self.assertNotIn("ExecStartPre=", unit)


if __name__ == "__main__":
    unittest.main()
