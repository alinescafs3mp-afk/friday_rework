"""Behavioral metadata controls. Native persistence has a separate real probe."""
import copy
import importlib.util
import os
from pathlib import Path
import json
import stat
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_associations_test", root / "__init__.py", submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_associations_test.associations import Associations, AssociationError, KEY
from friday_associations_test.boundary import WorkBrief

OWNER = dict(bot_id="fixture-bot", user_id="fixture-user", chat_id="fixture-chat",
             thread_id="", message_id="fixture-message", session_key="fixture-key",
             session_id="fixture-session", profile="")
NATIVE = dict(invocation_id="1" * 32, worker_reference="native-fixture-session")


class MemoryState:
    def __init__(self, path):
        self.data_dir = path
        self.data = {}
        self.fail_write = False

    def get(self, key, default):
        return copy.deepcopy(self.data[key]) if key in self.data else default

    def set(self, key, value):
        if self.fail_write:
            raise OSError("fixture write failure")
        self.data[key] = copy.deepcopy(value)


class AssociationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = MemoryState(Path(self.temp.name) / "private")
        self.store = Associations(self.state, clock=lambda: 1000)
        self.args = dict(task_id="existing-task", admission_key="trusted-bot-message",
                         owner=OWNER, brief=WorkBrief("dsh", "fixture task", "fixture goal"),
                         workspace_reference="owned-workspace-receipt",
                         supervisor={"scope": "user", "unit": "friday-rework-worker-" + "a" * 32 + ".service"},
                         budget_seconds=60, deadline_unix=1060)

    def test_replay_keeps_original_identity_and_budget(self):
        first, created = self.store.claim(**self.args)
        second, duplicate = self.store.claim(**{**self.args, "task_id": "newly-proposed-id", "budget_seconds": 600, "deadline_unix": 1600})
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first, second)
        self.assertEqual(len(self.state.data[KEY]["jobs"]), 1)

    def test_conflicting_owner_brief_or_supervisor_cannot_reuse_admission(self):
        self.store.claim(**self.args)
        for delta in ({"owner": {**OWNER, "thread_id": "other-topic"}},
                      {"brief": WorkBrief("a0", "different", "different")},
                      {"supervisor": {"scope": "system", "unit": self.args["supervisor"]["unit"]}}):
            with self.subTest(delta=delta), self.assertRaises(AssociationError):
                self.store.claim(**{**self.args, **delta})

    def test_one_native_boundary_cannot_be_shared_between_tasks(self):
        self.store.claim(**self.args)
        with self.assertRaisesRegex(AssociationError, "supervisor_already_owned"):
            self.store.claim(**{**self.args, "task_id": "other-task", "admission_key": "other-message"})

    def test_uncertain_submission_survives_new_store_instance(self):
        self.store.claim(**self.args)
        self.assertEqual(self.store.begin_submission("existing-task", OWNER)["submission_observation"], "UNKNOWN")
        reopened = Associations(self.state, clock=lambda: 1001)
        with self.assertRaisesRegex(AssociationError, "reconciliation"):
            reopened.begin_submission("existing-task", OWNER)

    def test_late_native_identity_cannot_clear_cancellation(self):
        self.store.claim(**self.args)
        self.store.begin_submission("existing-task", OWNER)
        self.store.request_stop("existing-task", OWNER, "cancel")
        row = self.store.attach_native("existing-task", OWNER, NATIVE)
        self.assertEqual(row["stop_intent"], "cancel")
        self.assertEqual(self.store.request_stop("existing-task", OWNER, "pause")["stop_intent"], "cancel")
        with self.assertRaises(AssociationError):
            self.store.begin_submission("existing-task", OWNER)

    def test_observation_preserves_budget_and_does_not_verify_goal(self):
        self.store.claim(**self.args)
        self.store.begin_submission("existing-task", OWNER)
        self.store.attach_native("existing-task", OWNER, NATIVE)
        self.store.observe("existing-task", OWNER, native=NATIVE, evidence_reference="actual-receipt", elapsed_seconds=40)
        row = self.store.observe("existing-task", OWNER, native=NATIVE, evidence_reference="later-receipt", elapsed_seconds=5)
        self.assertEqual((row["elapsed_seconds"], row["budget_seconds"], row["deadline_unix"]), (40, 60, 1060))
        self.assertEqual((row["goal_verification"], row["delivery"]), ("NOT_RUN", "NOT_RUN"))
        with self.assertRaises(AssociationError):
            self.store.observe("existing-task", OWNER, native={**NATIVE, "invocation_id": "2" * 32}, evidence_reference="wrong-unit", elapsed_seconds=41)

    def test_expired_or_foreign_calls_cannot_submit(self):
        self.store.claim(**self.args)
        with self.assertRaises(AssociationError):
            self.store.get("existing-task", {**OWNER, "chat_id": "foreign"})
        with self.assertRaises(AssociationError):
            Associations(self.state, clock=lambda: 1061).begin_submission("existing-task", OWNER)

    def test_new_control_message_keeps_original_destination(self):
        self.store.claim(**self.args)
        principal = {k: OWNER[k] for k in ("bot_id", "user_id", "chat_id", "thread_id", "profile")}
        original = self.store.get_for_control("existing-task", principal)
        self.assertEqual(original["owner"], OWNER)
        self.assertEqual(self.store.request_stop("existing-task", original["owner"], "cancel")["owner"], OWNER)
        for key in principal:
            with self.subTest(key=key), self.assertRaises(AssociationError):
                self.store.get_for_control("existing-task", {**principal, key: "foreign"})

    def test_failed_intent_write_does_not_grant_submission(self):
        self.store.claim(**self.args)
        self.state.fail_write = True
        with self.assertRaises(OSError):
            self.store.begin_submission("existing-task", OWNER)
        self.assertEqual(self.state.data[KEY]["jobs"]["existing-task"]["submission_observation"], "NOT_SUBMITTED")

    def test_missing_persisted_store_does_not_reopen_admission(self):
        self.store.claim(**self.args)
        self.state.data.clear()
        with self.assertRaisesRegex(AssociationError, "association_store_lost"):
            self.store.claim(**self.args)

    def test_nonblocking_lock_and_alias_controls(self):
        import fcntl
        self.store.claim(**self.args)
        lock = self.state.data_dir / "admission.lock"
        fd = os.open(lock, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with self.assertRaisesRegex(AssociationError, "admission_busy"):
                self.store.get("existing-task", OWNER)
        finally:
            os.close(fd)
        target = self.state.data_dir / "outside"
        target.write_text("preserve")
        lock.unlink()
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            self.store.get("existing-task", OWNER)
        self.assertEqual(target.read_text(), "preserve")


try:
    from hermes_cli.plugins_state import PluginState
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
except ImportError:
    PluginState = None


@unittest.skipIf(PluginState is None, "real pinned Hermes must be on PYTHONPATH")
class NativeAssociationTests(unittest.TestCase):
    """Actual native writer in fresh private profiles; no external execution.

    FRW_ASSOC_EVIDENCE_DIR retains every fixture, including injected failures.
    Without it unittest uses its normal temporary-fixture cleanup.
    """
    @contextmanager
    def fixture(self, label):
        evidence = os.environ.get("FRW_ASSOC_EVIDENCE_DIR")
        if evidence:
            parent = Path(evidence)
            info = parent.stat()
            if (not parent.is_absolute() or parent.resolve() != parent
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
                raise RuntimeError("fixture evidence directory must be private and owned")
            home = Path(tempfile.mkdtemp(prefix=label + "-", dir=parent))
        else:
            temporary = tempfile.TemporaryDirectory(prefix=label + "-")
            home = Path(temporary.name)
        token = set_hermes_home_override(home)
        state = PluginState("friday_rework")
        store = Associations(state, clock=lambda: 1000)
        args = dict(task_id="existing-task", admission_key="trusted-bot-message",
                    owner=OWNER, brief=WorkBrief("dsh", "fixture task", "fixture goal"),
                    workspace_reference="owned-workspace-receipt",
                    supervisor={"scope": "user", "unit": "friday-rework-worker-" + "a" * 32 + ".service"},
                    budget_seconds=60, deadline_unix=1060)
        try:
            yield state, store, args
        finally:
            reset_hermes_home_override(token)
            if not evidence:
                temporary.cleanup()

    @contextmanager
    def trace(self):
        events = []
        real_sync, real_replace = os.fsync, os.replace

        def sync(fd):
            events.append(("fsync", "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file",
                           os.readlink(f"/proc/self/fd/{fd}")))
            return real_sync(fd)

        def replace(src, dst, *args, **kwargs):
            events.append(("replace", str(src), str(dst)))
            return real_replace(src, dst, *args, **kwargs)

        with patch("os.fsync", sync), patch("os.replace", replace):
            yield events

    def test_real_native_writer_and_marker_commit_before_return(self):
        with self.fixture("ordering") as (state, store, args), self.trace() as events:
            state.data_dir.mkdir(mode=0o700, parents=True)
            state.set("unrelated.key", {"keep": True})
            for number, method in enumerate((lambda: store.claim(**args),
                           lambda: store.begin_submission(args["task_id"], OWNER),
                           lambda: store.request_stop(args["task_id"], OWNER, "cancel"),
                           lambda: store.attach_native(args["task_id"], OWNER, NATIVE),
                           lambda: store.observe(args["task_id"], OWNER, native=NATIVE,
                                                 evidence_reference="actual-fixture-observation", elapsed_seconds=70))):
                events.clear()
                method()
                events.append(("returned",))
                replacements = [i for i, e in enumerate(events) if e[0] == "replace" and e[2] == str(state.path)]
                self.assertTrue(replacements)
                for index in replacements:
                    self.assertTrue(any(e[0:2] == ("fsync", "file") for e in events[:index]))
                    self.assertIn(("fsync", "directory", str(state.data_dir)), events[index + 1:-1])
                marker_index = events.index(("fsync", "file", str(state.data_dir / "admission.lock")))
                cursor = marker_index
                for directory in (state.data_dir, *state.data_dir.parents):
                    cursor = events.index(("fsync", "directory", str(directory)), cursor + 1)
                if os.environ.get("FRW_ASSOC_EVIDENCE_DIR"):
                    log = state.data_dir.parent.parent / f"ordering-{number}.json"
                    # Distinct record per mutation, retained alongside native state.
                    with open(log, "x", encoding="utf-8") as out:
                        out.write(json.dumps(events, indent=2) + "\n")
            self.assertEqual(state.get("unrelated.key"), {"keep": True})
            row = store.get(args["task_id"], OWNER)
            self.assertEqual((row["elapsed_seconds"], row["budget_seconds"], row["stop_intent"]), (70, 60, "cancel"))

    def test_native_directory_failure_never_returns_grant(self):
        for operation in ("begin", "stop"):
            with self.subTest(operation=operation), self.fixture("dir-failure-" + operation) as (state, store, args):
                store.claim(**args)
                real_sync, real_replace = os.fsync, os.replace
                replaced = False

                def replace(src, dst, *a, **kw):
                    nonlocal replaced
                    result = real_replace(src, dst, *a, **kw)
                    if str(dst) == str(state.path):
                        replaced = True
                    return result

                def sync(fd):
                    if replaced and stat.S_ISDIR(os.fstat(fd).st_mode):
                        raise OSError("injected post-replace directory fsync failure")
                    return real_sync(fd)

                with patch("os.replace", replace), patch("os.fsync", sync), self.assertRaises(OSError):
                    if operation == "begin":
                        store.begin_submission(args["task_id"], OWNER)
                    else:
                        store.request_stop(args["task_id"], OWNER, "cancel")
                self.assertTrue(replaced)
                row = Associations(state, clock=lambda: 1001).get(args["task_id"], OWNER)
                self.assertEqual(row["submission_observation"] if operation == "begin" else row["stop_intent"],
                                 "UNKNOWN" if operation == "begin" else "cancel")
                with self.assertRaises(AssociationError):
                    store.begin_submission(args["task_id"], OWNER)

    def test_native_file_sync_and_replace_failures_never_authorize(self):
        for failure in ("file", "replace"):
            with self.subTest(failure=failure), self.fixture("writer-failure-" + failure) as (state, store, args):
                store.claim(**args)
                real_sync = os.fsync

                def sync(fd):
                    if (stat.S_ISREG(os.fstat(fd).st_mode)
                            and os.readlink(f"/proc/self/fd/{fd}") != str(state.data_dir / "admission.lock")):
                        raise OSError("injected native temporary-file fsync failure")
                    return real_sync(fd)

                target = patch("os.fsync", sync) if failure == "file" else patch("os.replace", side_effect=OSError("injected replace failure"))
                before = state.path.read_bytes()
                with target, self.assertRaises(OSError):
                    store.begin_submission(args["task_id"], OWNER)
                self.assertEqual(state.path.read_bytes(), before)
                self.assertEqual(store.get(args["task_id"], OWNER)["submission_observation"], "NOT_SUBMITTED")

    def test_initial_marker_and_ancestor_failures_do_not_admit(self):
        for failure in ("marker", "ancestor", "short-marker"):
            with self.subTest(failure=failure), self.fixture("init-failure-" + failure) as (state, store, args):
                real_sync, real_pwrite = os.fsync, os.pwrite

                def sync(fd):
                    path = os.readlink(f"/proc/self/fd/{fd}")
                    if ((failure == "marker" and path == str(state.data_dir / "admission.lock"))
                            or (failure == "ancestor" and path == str(state.data_dir.parent))):
                        raise OSError("injected initialization durability failure")
                    return real_sync(fd)

                def pwrite(fd, data, offset):
                    return real_pwrite(fd, data[:2], offset)

                with patch("os.fsync", sync), patch("os.pwrite", pwrite if failure == "short-marker" else real_pwrite), self.assertRaises(OSError):
                    store.claim(**args)
                self.assertEqual(state.get(KEY)["jobs"], {})
                if failure == "short-marker":
                    with self.assertRaisesRegex(AssociationError, "invalid_admission_marker"):
                        store.claim(**args)
                else:
                    with self.trace() as events:
                        row, created = store.claim(**args)
                    self.assertTrue(created)
                    self.assertEqual(row["budget_seconds"], 60)
                    self.assertIn(("fsync", "file", str(state.data_dir / "admission.lock")), events)
                    self.assertIn(("fsync", "directory", str(state.data_dir.parent)), events)

    def assert_store_refused(self, state, store, args, document):
        state.set(KEY, document)  # Deliberate native-state corruption, no tool input.
        before = state.path.read_bytes()
        principal = {k: OWNER[k] for k in ("bot_id", "user_id", "chat_id", "thread_id", "profile")}
        calls = (lambda: store.get(args["task_id"], OWNER),
                 lambda: store.get_for_control(args["task_id"], principal),
                 lambda: store.begin_submission(args["task_id"], OWNER),
                 lambda: store.claim(**{**args, "task_id": "unrelated-task", "admission_key": "unrelated-admission",
                                        "supervisor": {**args["supervisor"], "unit": "friday-rework-worker-" + "b" * 32 + ".service"}}),
                 lambda: store.request_stop(args["task_id"], OWNER, "cancel"),
                 lambda: store.attach_native(args["task_id"], OWNER, NATIVE),
                 lambda: store.observe(args["task_id"], OWNER, native=NATIVE, evidence_reference="fixture", elapsed_seconds=1))
        for call in calls:
            with self.assertRaisesRegex(AssociationError, "invalid_association_store"):
                call()
            self.assertEqual(state.path.read_bytes(), before)

    def test_exact_review_corruptions_refuse_every_access_and_admission(self):
        changes = {"negative_budget_elapsed": {"budget_seconds": -1, "elapsed_seconds": -2},
                   "nan_budget_deadline": {"budget_seconds": float("nan"), "deadline_unix": float("nan")},
                   "native_present_but_not_submitted": {"native": NATIVE},
                   "old_row": None}
        for name, change in changes.items():
            with self.subTest(name=name), self.fixture("review-" + name) as (state, store, args):
                store.claim(**args)
                document = state.get(KEY)
                if change is None:
                    document["jobs"][args["task_id"]] = {}
                else:
                    document["jobs"][args["task_id"]].update(change)
                self.assert_store_refused(state, store, args, document)

    def test_complete_native_schema_and_numeric_domains(self):
        changes = [("existing_task_id", "wrong-task"), ("owner", {}), ("worker_kind", "other"),
                   ("brief_sha256", "bad"), ("admission_hash", "f" * 63), ("workspace_reference", ""),
                   ("supervisor", {"scope": "user", "unit": "foreign.service"}),
                   ("created_at_unix", -1), ("created_at_unix", True), ("budget_seconds", 0),
                   ("budget_seconds", 10 ** 1000), ("deadline_unix", 1061), ("deadline_unix", 1000),
                   ("elapsed_seconds", 1), ("elapsed_seconds", float("inf")),
                   ("submission_observation", "OBSERVED"), ("submission_observation", []),
                   ("stop_intent", "resume"), ("execution_observation", "unbound-observation"),
                   ("goal_verification", "PASS"), ("delivery", "DELIVERED"),
                   ("owner", {**OWNER, "user_id": 1}), ("owner", {**OWNER, "chat_id": ""}),
                   ("supervisor", {"scope": "other", "unit": "friday-rework-worker-" + "a" * 32 + ".service"}),
                   ("budget_seconds", True), ("deadline_unix", False), ("elapsed_seconds", True),
                   ("created_at_unix", float("nan")), ("deadline_unix", float("inf")),
                   ("submission_observation", "UNKNOWN"), ("execution_observation", "")]
        for index, (field, value) in enumerate(changes):
            with self.subTest(field=field, value=value), self.fixture(f"schema-{index}") as (state, store, args):
                store.claim(**args)
                document = state.get(KEY)
                document["jobs"][args["task_id"]][field] = value
                if field == "submission_observation" and value == "UNKNOWN":
                    document["jobs"][args["task_id"]]["native"] = NATIVE
                self.assert_store_refused(state, store, args, document)

    def test_native_row_shape_top_level_and_all_required_fields(self):
        with self.fixture("shape-template") as (state, store, args):
            store.claim(**args)
            template = state.get(KEY)
        variants = [None, {}, {**template, "extra": 1}, {**template, "schema_version": True},
                    {**template, "jobs": []}, {**template, "jobs": {args["task_id"]: []}}]
        for field in template["jobs"][args["task_id"]]:
            document = copy.deepcopy(template)
            del document["jobs"][args["task_id"]][field]
            variants.append(document)
        document = copy.deepcopy(template)
        document["jobs"][args["task_id"]]["extra"] = 1
        variants.append(document)
        for index, document in enumerate(variants):
            with self.subTest(index=index), self.fixture(f"shape-{index}") as (state, store, args):
                store.claim(**args)
                self.assert_store_refused(state, store, args, document)

    def test_native_identity_and_uniqueness_invariants(self):
        for field in ("admission_hash", "supervisor", "invocation", "worker", "native-shape", "native-uuid"):
            with self.subTest(field=field), self.fixture("unique-" + field) as (state, store, args):
                store.claim(**args)
                store.begin_submission(args["task_id"], OWNER)
                store.attach_native(args["task_id"], OWNER, NATIVE)
                document = state.get(KEY)
                other = copy.deepcopy(document["jobs"][args["task_id"]])
                other.update(existing_task_id="other-task", admission_hash="b" * 64,
                             supervisor={"scope": "user", "unit": "friday-rework-worker-" + "b" * 32 + ".service"},
                             native={"invocation_id": "2" * 32, "worker_reference": "other-native-session"})
                if field in ("admission_hash", "supervisor"):
                    other[field] = copy.deepcopy(document["jobs"][args["task_id"]][field])
                elif field == "invocation":
                    other["native"]["invocation_id"] = NATIVE["invocation_id"]
                elif field == "worker":
                    other["native"]["worker_reference"] = NATIVE["worker_reference"]
                elif field == "native-shape":
                    other["native"]["extra"] = "unexpected"
                else:
                    other["native"]["invocation_id"] = "not-an-invocation"
                document["jobs"]["other-task"] = other
                self.assert_store_refused(state, store, args, document)

    def test_postcommit_native_error_and_stop_intent_remain_uncertain(self):
        with self.fixture("postcommit") as (state, store, args):
            store.claim(**args)
            real_set = state.set

            def postcommit(key, value):
                real_set(key, value)
                raise OSError("injected native postcommit failure")

            with patch.object(state, "set", postcommit), self.assertRaises(OSError):
                store.begin_submission(args["task_id"], OWNER)
            with self.assertRaisesRegex(AssociationError, "reconciliation"):
                Associations(state, clock=lambda: 1001).begin_submission(args["task_id"], OWNER)
            store.request_stop(args["task_id"], OWNER, "cancel")
            store.attach_native(args["task_id"], OWNER, NATIVE)
            store.request_stop(args["task_id"], OWNER, "pause")
            self.assertEqual(store.get(args["task_id"], OWNER)["stop_intent"], "cancel")

    def test_invalid_clock_cannot_issue_new_or_submission_grant(self):
        for value in (True, float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.fixture("invalid-clock") as (state, store, args):
                with self.assertRaises(AssociationError):
                    Associations(state, clock=lambda: value).claim(**args)
                store.claim(**args)
                before = state.path.read_bytes()
                with self.assertRaises(AssociationError):
                    Associations(state, clock=lambda: value).begin_submission(args["task_id"], OWNER)
                self.assertEqual(state.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
