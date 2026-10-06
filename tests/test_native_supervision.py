"""Offline ownership, observation, and stop controls; never contacts systemd.

Live fixture evidence belongs to the independent bounded native check, not the
default suite. Quiescence proves only this unit boundary, never an A0 server or
remote inference boundary.
"""
import copy
import importlib
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch


PACKAGE = "friday_native_supervision_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "plugins/friday_rework")]
sys.modules[PACKAGE] = package
module = importlib.import_module(PACKAGE + ".supervision")
AssociationError = importlib.import_module(PACKAGE + ".associations").AssociationError
NativeSupervisor = module.NativeSupervisor
SupervisorError = module.SupervisorError

UNIT = "friday-rework-worker-" + "a" * 32 + ".service"
INVOCATION = "b" * 32
GROUP = "/user.slice/user-1000.slice/user@1000.service/app.slice/" + UNIT
ASSOCIATION = {
    "supervisor": {"scope": "user", "unit": UNIT},
    "admission_hash": "c" * 64,
    "native": {"invocation_id": INVOCATION, "worker_reference": "owned-fixture"},
}
FIELDS = {
    "LoadState": "loaded", "Transient": "yes",
    "Description": "Friday rework " + ASSOCIATION["admission_hash"],
    "InvocationID": INVOCATION, "ActiveState": "active", "SubState": "running",
    "Result": "success", "MainPID": "1234", "ControlGroup": GROUP,
    "KillMode": "control-group", "SendSIGKILL": "yes",
}


def observation(*, changes=None, omit=(), prefix="", suffix="", returncode=0):
    fields = {**FIELDS, **(changes or {})}
    for key in omit:
        fields.pop(key)
    return subprocess.CompletedProcess([], returncode,
        prefix + "".join(f"{key}={value}\n" for key, value in fields.items()) + suffix,
        "injected command failure" if returncode else "")


class NativeSupervisionTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = NativeSupervisor()
        self.association = copy.deepcopy(ASSOCIATION)
        self.command_patcher = patch.object(NativeSupervisor, "_command")
        self.command = self.command_patcher.start()
        self.addCleanup(self.command_patcher.stop)
        self.command.return_value = observation()

    def assert_refused_without_stop(self, response, error=SupervisorError, *, populated=True):
        self.command.reset_mock()
        self.command.return_value = response
        with patch.object(NativeSupervisor, "_populated", return_value=populated), self.assertRaises(error):
            self.supervisor.stop(self.association)
        self.assertFalse(any(call.args[0][0] == "stop" for call in self.command.call_args_list))

    def test_owned_observation_preserves_native_identity(self):
        with patch.object(NativeSupervisor, "_populated", return_value=True) as populated:
            result = self.supervisor.observe(self.association)
        self.assertEqual((result.unit, result.invocation_id, result.main_pid),
                         (UNIT, INVOCATION, 1234))
        self.assertFalse(result.quiescent)
        populated.assert_called_once_with(GROUP)
        self.assertEqual(self.command.call_args.args[0][0:2], ["show", UNIT])

    def test_wrong_owner_and_nontransient_never_stop(self):
        for changes in ({"Description": "Friday rework " + "d" * 64},
                        {"Transient": "no"}, {"Description": ""}):
            with self.subTest(changes=changes):
                self.assert_refused_without_stop(observation(changes=changes))

    def test_known_invocation_replacement_never_stops(self):
        self.assert_refused_without_stop(observation(changes={"InvocationID": "e" * 32}))

    def test_unsafe_stop_boundary_never_stops(self):
        for changes in ({"KillMode": "process"}, {"KillMode": "mixed"},
                        {"SendSIGKILL": "no"}):
            with self.subTest(changes=changes):
                self.assert_refused_without_stop(observation(changes=changes))

    def test_invalid_unit_or_scope_cannot_contact_systemd(self):
        for supervisor in ({"scope": "system", "unit": UNIT},
                           {"scope": "user", "unit": "foreign.service"},
                           {"scope": "user", "unit": UNIT + " --all"}):
            with self.subTest(supervisor=supervisor):
                self.association["supervisor"] = supervisor
                with self.assertRaises((SupervisorError, AssociationError)):
                    self.supervisor.stop(self.association)
        self.command.assert_not_called()

    def test_invalid_admission_cannot_contact_systemd(self):
        for identity in (None, 1, "c" * 63, "C" * 64, "c" * 64 + "\n"):
            with self.subTest(identity=identity):
                self.association["admission_hash"] = identity
                with self.assertRaises(SupervisorError):
                    self.supervisor.stop(self.association)
        self.command.assert_not_called()

    def test_unreadable_command_never_stops(self):
        self.assert_refused_without_stop(observation(returncode=1))

    def test_malformed_lines_required_fields_pid_invocation_never_stop(self):
        variants = [observation(suffix="broken row\n"), observation(suffix="\n")]
        variants += [observation(omit=(field,)) for field in
                     ("Transient", "Description", "InvocationID", "MainPID",
                      "ControlGroup", "ActiveState", "SubState", "Result", "KillMode", "SendSIGKILL")]
        variants += [observation(changes={"MainPID": value}) for value in ("", "-1", "123x")]
        variants += [observation(changes={"InvocationID": value}) for value in ("", "x" * 32)]
        for index, response in enumerate(variants):
            with self.subTest(index=index):
                self.assert_refused_without_stop(response)

    def test_not_found_with_live_identity_is_not_quiescence(self):
        # A missing-unit marker cannot override a contradictory live PID/cgroup.
        self.assert_refused_without_stop(observation(changes={"LoadState": "not-found"}))

    def test_failed_observation_cannot_become_success_by_not_found_marker(self):
        self.assert_refused_without_stop(observation(changes={"LoadState": "not-found"}, returncode=124))

    def test_truncated_not_found_is_not_a_complete_observation(self):
        self.assert_refused_without_stop(subprocess.CompletedProcess([], 0, "LoadState=not-found\n", ""))

    def test_complete_native_not_found_observation_sends_no_stop(self):
        # Exact property shape observed with read-only systemctl show of an
        # independently declared absent fixture name on this user manager.
        self.command.return_value = observation(changes={"LoadState": "not-found", "Transient": "no",
            "Description": UNIT, "InvocationID": "", "ActiveState": "inactive", "SubState": "dead",
            "MainPID": "0", "ControlGroup": ""})
        result = self.supervisor.stop(self.association)
        self.assertTrue(result.missing)
        self.assertTrue(result.quiescent)
        self.assertEqual(self.command.call_count, 1)

    def test_duplicate_unit_fields_are_not_authority(self):
        # dict(last-wins) would discard contradictory ownership evidence.
        self.assert_refused_without_stop(observation(prefix="Description=foreign owner\n"))

    def test_missing_load_state_is_invalid_observation(self):
        self.assert_refused_without_stop(observation(omit=("LoadState",)))

    def test_every_required_property_is_unique_and_present(self):
        for field, value in FIELDS.items():
            with self.subTest(field=field, defect="duplicate"):
                self.assert_refused_without_stop(observation(suffix=f"{field}={value}\n"))
            with self.subTest(field=field, defect="missing"):
                self.assert_refused_without_stop(observation(omit=(field,)))

    def test_loaded_inactive_running_cannot_claim_quiescence(self):
        # The terminal active state contradicts the service's live substate.
        self.assert_refused_without_stop(observation(changes={
            "ActiveState": "inactive", "SubState": "running",
            "MainPID": "0", "ControlGroup": ""}), populated=False)

    def test_loaded_failed_running_cannot_claim_quiescence(self):
        self.assert_refused_without_stop(observation(changes={
            "ActiveState": "failed", "SubState": "running", "Result": "timeout",
            "MainPID": "0", "ControlGroup": ""}), populated=False)

    def test_loaded_empty_substate_cannot_claim_quiescence(self):
        self.assert_refused_without_stop(observation(changes={
            "ActiveState": "inactive", "SubState": "",
            "MainPID": "0", "ControlGroup": ""}), populated=False)

    def test_loaded_empty_result_cannot_claim_quiescence(self):
        self.assert_refused_without_stop(observation(changes={
            "ActiveState": "inactive", "SubState": "dead", "Result": "",
            "MainPID": "0", "ControlGroup": ""}), populated=False)

    def test_loaded_unsupported_active_state_cannot_authorize_stop(self):
        self.assert_refused_without_stop(observation(changes={"ActiveState": "unsupported-state"}))

    def test_loaded_empty_active_state_cannot_authorize_stop(self):
        self.assert_refused_without_stop(observation(changes={"ActiveState": ""}))

    def test_loaded_unsupported_substate_cannot_authorize_stop(self):
        self.assert_refused_without_stop(observation(changes={"SubState": "unsupported-state"}))

    def test_loaded_unsupported_result_cannot_claim_quiescence(self):
        self.assert_refused_without_stop(observation(changes={
            "ActiveState": "inactive", "SubState": "dead", "Result": "unsupported-result",
            "MainPID": "0", "ControlGroup": ""}), populated=False)

    def test_loaded_transitional_states_reject_contradictory_substates(self):
        for active, sub in (("active", "dead"), ("activating", "running"),
                            ("reloading", "dead"), ("deactivating", "dead")):
            with self.subTest(active=active, sub=sub):
                self.assert_refused_without_stop(observation(changes={
                    "ActiveState": active, "SubState": sub}))

    def test_live_main_pid_without_cgroup_cannot_authorize_stop(self):
        self.assert_refused_without_stop(observation(changes={"ControlGroup": ""}), populated=False)

    def test_live_main_pid_with_empty_cgroup_is_inconsistent_observation(self):
        self.assert_refused_without_stop(observation(), populated=False)

    def test_running_service_without_any_process_is_inconsistent_observation(self):
        self.assert_refused_without_stop(observation(changes={
            "MainPID": "0", "ControlGroup": ""}), populated=False)

    def test_valid_transitions_and_exited_service_are_not_quiescent(self):
        # MainPID zero is valid for pre/post commands, unknown forking main PID,
        # and RemainAfterExit. Do not replace consistency checks with PID > 0.
        cases = [
            ("activating", "start-pre", "0", GROUP, True),
            ("activating", "start", "1234", GROUP, True),
            ("active", "running", "0", GROUP, True),
            ("active", "exited", "0", "", False),
            ("reloading", "reload", "1234", GROUP, True),
            ("deactivating", "stop-sigterm", "0", GROUP, True),
            ("deactivating", "stop-post", "0", GROUP, True),
            ("deactivating", "stop-post", "0", "", False),
        ]
        for active, sub, pid, group, populated in cases:
            with self.subTest(active=active, sub=sub, populated=populated):
                self.command.return_value = observation(changes={
                    "ActiveState": active, "SubState": sub,
                    "MainPID": pid, "ControlGroup": group})
                with patch.object(NativeSupervisor, "_populated", return_value=populated):
                    result = self.supervisor.observe(self.association)
                self.assertFalse(result.quiescent)
                self.assertEqual((result.active_state, result.sub_state, result.main_pid),
                                 (active, sub, int(pid)))

    def test_complete_terminal_failure_remains_valid_quiescence(self):
        self.command.return_value = observation(changes={
            "ActiveState": "failed", "SubState": "failed", "Result": "timeout",
            "MainPID": "0", "ControlGroup": ""})
        with patch.object(NativeSupervisor, "_populated", return_value=False):
            result = self.supervisor.stop(self.association)
        self.assertTrue(result.quiescent)
        self.assertEqual(result.result, "timeout")
        self.assertEqual(self.command.call_count, 1)

    def test_cgroup_must_name_the_exact_owned_service(self):
        for group in ("/", "/foreign.slice/foreign.service", GROUP + "/child"):
            with self.subTest(group=group):
                self.assert_refused_without_stop(observation(changes={"ControlGroup": group}))

    def test_terminal_state_with_live_main_pid_is_inconsistent(self):
        for active, sub in (("inactive", "dead"), ("failed", "failed")):
            with self.subTest(active=active):
                self.assert_refused_without_stop(observation(changes={"ActiveState": active, "SubState": sub}))

    def test_pid_is_a_canonical_bounded_native_integer(self):
        for pid in ("+1", " 1", "01", "1" * 21):
            with self.subTest(pid=pid):
                self.assert_refused_without_stop(observation(changes={"MainPID": pid}))

    def test_owned_stop_checks_post_stop_cgroup(self):
        self.command.side_effect = [observation(), subprocess.CompletedProcess([], 0, "", ""),
                                   observation(changes={"ActiveState": "inactive", "SubState": "dead",
                                                        "MainPID": "0", "ControlGroup": ""})]
        with patch.object(NativeSupervisor, "_populated", side_effect=[True, False]):
            result = self.supervisor.stop(self.association)
        self.assertTrue(result.quiescent)
        self.assertEqual([call.args[0][0] for call in self.command.call_args_list], ["show", "stop", "show"])
        self.assertEqual(self.command.call_args_list[1].args[0], ["stop", UNIT])

    def test_lingering_descendant_prevents_confirmed_stop(self):
        self.command.side_effect = [observation(), subprocess.CompletedProcess([], 0, "", ""),
                                   observation(changes={"ActiveState": "failed", "SubState": "failed",
                                                        "MainPID": "0"})]
        with patch.object(NativeSupervisor, "_populated", return_value=True), self.assertRaisesRegex(
                SupervisorError, "native_stop_unconfirmed"):
            self.supervisor.stop(self.association)

    def test_failed_native_stop_stays_unconfirmed(self):
        self.command.side_effect = [observation(), subprocess.CompletedProcess([], 1, "", "refused")]
        with patch.object(NativeSupervisor, "_populated", return_value=True), self.assertRaisesRegex(
                SupervisorError, "native_stop_unconfirmed"):
            self.supervisor.stop(self.association)
        self.assertEqual(self.command.call_count, 2)

    def test_post_stop_invocation_replacement_stays_unconfirmed(self):
        self.command.side_effect = [observation(), subprocess.CompletedProcess([], 0, "", ""),
                                   observation(changes={"InvocationID": "f" * 32})]
        with patch.object(NativeSupervisor, "_populated", return_value=True), self.assertRaisesRegex(
                SupervisorError, "native_invocation_changed"):
            self.supervisor.stop(self.association)

    def test_initial_reconciliation_cannot_accept_post_stop_replacement(self):
        self.association["native"] = None
        self.command.side_effect = [observation(), subprocess.CompletedProcess([], 0, "", ""),
                                   observation(changes={"InvocationID": "f" * 32, "MainPID": "0",
                                                        "ActiveState": "inactive", "SubState": "dead",
                                                        "ControlGroup": ""})]
        with patch.object(NativeSupervisor, "_populated", side_effect=[True, False]), self.assertRaisesRegex(
                SupervisorError, "native_invocation_changed"):
            self.supervisor.stop(self.association)

    def test_already_quiescent_never_sends_stop(self):
        self.command.return_value = observation(changes={"ActiveState": "inactive", "SubState": "dead",
                                                        "MainPID": "0", "ControlGroup": ""})
        with patch.object(NativeSupervisor, "_populated", return_value=False):
            self.assertTrue(self.supervisor.stop(self.association).quiescent)
        self.assertEqual(self.command.call_count, 1)

    def test_cgroup_invalid_paths_rejected(self):
        for group in ("relative/path", "/../../etc", "/user.slice/../etc"):
            with self.subTest(group=group), self.assertRaises(SupervisorError):
                self.supervisor._populated(group)

    def test_cgroup_unreadable_or_malformed_is_not_empty(self):
        for content in ("", "populated 2\n", "populated\n", "populated 0 extra\n"):
            with self.subTest(content=content), patch.object(Path, "read_text", return_value=content), self.assertRaises(SupervisorError):
                self.supervisor._populated(GROUP)
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")), self.assertRaises(SupervisorError):
            self.supervisor._populated(GROUP)

    def test_duplicate_cgroup_population_is_not_empty(self):
        with patch.object(Path, "read_text", return_value="populated 1\npopulated 0\n"), self.assertRaises(SupervisorError):
            self.supervisor._populated(GROUP)

    def test_valid_cgroup_population(self):
        for value, expected in (("1", True), ("0", False)):
            with patch.object(Path, "read_text", return_value=f"populated {value}\nfrozen 0\n"):
                self.assertIs(self.supervisor._populated(GROUP), expected)


class NativeCommandTests(unittest.TestCase):
    def test_exact_argv_and_clean_environment(self):
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(module.subprocess, "run", return_value=result) as run:
            self.assertIs(NativeSupervisor._command(["show", UNIT], 3), result)
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["/usr/bin/systemctl", "--user", "--no-pager", "show", UNIT])
        self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin", "LC_ALL": "C",
            "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{os.getuid()}/bus"})
        self.assertEqual(kwargs["timeout"], 3)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("shell", kwargs)

    def test_unavailable_or_timed_out_native_command_is_error(self):
        for error in (OSError("unavailable"), subprocess.TimeoutExpired("systemctl", 3)):
            with self.subTest(error=type(error).__name__), patch.object(module.subprocess, "run", side_effect=error), self.assertRaisesRegex(
                    SupervisorError, "native_control_unavailable"):
                NativeSupervisor._command(["show", UNIT], 3)


if __name__ == "__main__":
    unittest.main()
