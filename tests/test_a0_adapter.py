"""Offline A0 protocol/ownership controls. No UI, model, network or daemon.

The pinned donor handler classes execute unchanged with an in-memory agent and
real private temporary files. This is protocol evidence, never runtime proof.
"""
import ast
import asyncio
import base64
import copy
from dataclasses import asdict, replace
import datetime
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import contextlib
import types
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import uuid

package_root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_a0_test", package_root / "__init__.py",
                                            submodule_search_locations=[str(package_root)])
package = importlib.util.module_from_spec(spec); sys.modules[spec.name] = package; spec.loader.exec_module(package)
from friday_a0_test.adapters.a0 import A0Adapter, A0HostConfig, A0Controller, ExpectedFile, input_path, job_prefix
from friday_a0_test.adapters.a0_config import A0Deployment, A0Error, LocalNetwork, prepare_keys, local_profile
from friday_a0_test.adapters.a0_native import A0NativeBoundary, NativeGrant, native_file, file_script, strict_json, decode_file, API_SCRIPT
from friday_a0_test.adapters.dsh import PinnedFile
from friday_a0_test.adapters.contract import PreparedNative, VerifiedInput
from friday_a0_test.associations import Associations
from friday_a0_test.controller import WorkerBinding, Controller, ControllerError
from friday_a0_test.boundary import WorkBrief
from friday_a0_test.supervision import UnitObservation
from friday_a0_test.artifacts import read_staged
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override

OWNER = dict(bot_id="bot", user_id="user", chat_id="chat", thread_id="topic",
             message_id="message", session_key="key", session_id="session", profile="")
PRINCIPAL = {k: OWNER[k] for k in ("bot_id", "user_id", "chat_id", "thread_id", "profile")}
BRIEF = WorkBrief("a0", "diagnose and repair fixture", "the supplied check passes")
INV, CID = "a" * 32, "b" * 64
UNIT = "friday-rework-worker-" + "a" * 32 + ".service"


def pinned(path, content):
    path.write_bytes(content)
    return PinnedFile(path, hashlib.sha256(content).hexdigest())


class Silent:
    def __init__(self, **kwargs): pass
    def print(self, *args): pass
    @staticmethod
    def error(*args): pass
    @staticmethod
    def warning(*args): pass


class OfflineNative:
    """Execute actual donor process methods; substitute only agent/UI runtime."""
    def __init__(self, case):
        self.case = case; self.contexts = {}; self.calls = []; self.running = True; self.stops = 0
        self.config = NS(state_dir=case.usr)
        self.grant = NativeGrant(CID,'frw-a0-'+'b'*32,INV,
            {'friday.rework.assignment':'task','friday.rework.plan':case.row['admission_hash']},1000,1060,
            '/user.slice/fixture/docker-'+CID+'.scope',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            True,case.keys.prepared_monotonic,daemon_invocation_id='e'*32,accepted_monotonic=case.keys.prepared_monotonic-1)
        self.supervisor = NS(observe=lambda row: self.unit())
        self.task_hook = None; self.file_hook = None; self.log_hook = None
        native = self
        class Context:
            def __init__(self, config, type):
                self.id = "actual-created-context"; native.contexts[self.id] = self
                self.agent0 = NS(config=NS(profile="agent0")); self.data = {}
                self.log = NS(logs=[], guid="guid", progress="", progress_active=False)
                self.log.log = lambda **kw: self.log.logs.append(kw)
                self.log.output = lambda start: NS(items=self.log.logs[start:])
            @staticmethod
            def use(id): return native.contexts.get(id)
            def get_data(self, key): return self.data.get(key)
            def set_data(self, key, value): self.data[key] = value
            def communicate(self, msg):
                async def result():
                    if msg.message.startswith("Existing job:"):
                        if native.task_hook: native.task_hook()
                        for output in case.outputs:
                            p = native.local(output.worker_path); p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            p.write_bytes(b"retained result\n")
                        return "worker report; acceptance is host-owned"
                    return "READY"
                return NS(result=result)
        class Response:
            def __init__(self, body, status, mimetype): self.status = status
        donor = Path(os.environ["FRW_A0_DONOR"]).resolve()
        ns = dict(ApiHandler=object, Request=object, Response=Response, AgentContext=Context,
                  UserMessage=lambda **kwargs: NS(**kwargs), AgentContextType=NS(USER="user"),
                  initialize_agent=lambda **kw: kw, os=os, base64=base64, uuid=uuid,
                  datetime=datetime.datetime, timezone=datetime.timezone,
                  files=NS(get_abs_path=lambda *parts: str(case.native_root.joinpath(*parts))),
                  projects=NS(CONTEXT_DATA_KEY_PROJECT="project", activate_project=lambda *a: None),
                  activate_project=lambda *a: None, PrintStyle=Silent,
                  safe_filename=lambda value: Path(value).name, json=json)
        self.handlers = {}
        for filename, name in [("api_message", "ApiMessage"), ("api_files_get", "ApiFilesGet"), ("api_log_get", "ApiLogGet")]:
            source = (donor / "api" / (filename + ".py")).read_text()
            cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == name)
            exec(compile(ast.Module(body=[cls], type_ignores=[]), str(donor / "api" / (filename + ".py")), "exec"), ns)
            self.handlers["/api/" + filename] = ns[name]()
    def local(self, worker): return self.case.native_root / worker.removeprefix("/a0/")
    def unit(self):
        return UnitObservation(UNIT, INV, "active" if self.running else "inactive",
                               "running" if self.running else "dead", "success",
                               123 if self.running else 0, "/fake" if self.running else "", self.running)
    def admit(self, row):
        if row["stop_intent"] or self.case.clock >= row["deadline_unix"] or not self.running:
            raise A0Error("stopped_or_expired")
        return self.unit()
    def request(self, row, method, path, payload, timeout, max_bytes):
        self.admit(row); self.calls.append((method, path, copy.deepcopy(payload), timeout))
        result = asyncio.run(self.handlers[path].process(payload, NS(method=method, args=payload)))
        if path.endswith("api_files_get") and self.file_hook: result = self.file_hook(result)
        if path.endswith("api_log_get") and self.log_hook: result = self.log_hook(result)
        if not isinstance(result, dict): raise A0Error("api_outcome_unknown")
        return result
    def file(self, row, path, limit, timeout):
        self.admit(row)
        return native_file(str(self.case.native_root), path.removeprefix("/a0/"), limit)
    def stop(self, row):
        self.stops += 1; self.running = False; return self.unit()
    def _association(self, row): return row
    def inspect(self, row, stopping=False): return {"State": {"Running": self.running, "Pid": 123 if self.running else 0}}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name).resolve()
        token = set_hermes_home_override(self.root / "home"); self.addCleanup(reset_hermes_home_override, token)
        self.clock = 1000
        self.work = self.root / "jobs"; self.inputs_root = self.root / "inputs"; self.staging = self.root / "staging"
        self.native_root = self.root / "native"; self.usr = self.native_root / "usr"
        for p in (self.work, self.inputs_root, self.staging, self.native_root, self.usr): p.mkdir(mode=0o700)
        self.job = self.work / "job"; self.job.mkdir(mode=0o700)
        self.env = self.usr / ".env"; self.env.write_text("AUTH_LOGIN=fixture\n"); self.env.chmod(0o600)
        self.keys = prepare_keys(self.usr, lambda ref: "synthetic-secret-" + ref)
        self.store = Associations(PluginState("friday_a0"), clock=lambda: self.clock)
        self.row, _ = self.store.claim(task_id="task", admission_key="admission", owner=OWNER, brief=BRIEF,
            workspace_reference=str(self.job), budget_seconds=60, deadline_unix=1060,
            supervisor={"scope": "user", "unit": UNIT})
        name = job_prefix(self.row)
        self.outputs = (ExpectedFile(f"/a0/usr/workdir/{name}/{name}-output.txt", "report.txt", "text/plain"),)
        self.native = OfflineNative(self)
        self.config = A0HostConfig(self.work, self.inputs_root, self.staging,
            lambda row: self.store.get(row["existing_task_id"], row["owner"]),
            lambda row: self.outputs, self.keys)
        self.adapter = A0Adapter(self.config, self.native, clock=lambda: self.clock)
        self.binding = WorkerBinding(self.adapter, self.adapter.emergency_stop)
        self.controller = A0Controller(self.store, {"a0": self.binding})
    def prepare(self, inputs=()): return self.controller.prepare("task", OWNER, BRIEF, inputs)
    def start(self, inputs=()): return self.controller.start("task", OWNER, BRIEF, inputs)
    def input(self, content=b"input\n", suffix=".txt", index=0):
        p = self.inputs_root / (str(index) + suffix); p.write_bytes(content)
        return VerifiedInput(str(p), input_path(self.row, index, suffix), len(content), hashlib.sha256(content).hexdigest(), "native-ingress")
    def test_actual_donor_bootstrap_then_single_task_and_stable_artifact(self):
        value = self.input(); prepared = self.prepare((value,))
        self.assertEqual(prepared.reference, "actual-created-context")
        def before_task():
            row = self.store.get("task", OWNER)
            self.assertEqual(row["native"]["worker_reference"], "a0:" + CID + ":actual-created-context")
            self.assertTrue((self.job / "task-post-intent.json").exists())
            self.assertEqual(json.loads((self.job / "a0-prepared.json").read_text())["inputs"][0]["sha256"], value.sha256)
        self.native.task_hook = before_task
        result = self.start((value,)); self.assertEqual(result.state, "completed")
        calls = [p for m, path, p, _ in self.native.calls if path == "/api/api_message"]
        self.assertEqual(len(calls), 2); self.assertNotIn("context_id", calls[0]); self.assertEqual(calls[1]["context_id"], prepared.reference)
        self.assertNotIn("api_key", calls[0]); self.assertFalse(self.native.running)
        artifacts = self.adapter.artifacts(self.store.get("task", OWNER), prepared)
        self.native.local(self.outputs[0].worker_path).unlink()
        self.assertEqual(read_staged(staging_root=self.staging, artifact=artifacts[0], max_bytes=1024), b"retained result\n")
        self.assertEqual((self.store.get("task", OWNER)["goal_verification"], self.store.get("task", OWNER)["delivery"]), ("NOT_RUN", "NOT_RUN"))
        self.assertEqual(self.start((value,)).state, "completed")
        self.assertEqual(len([c for c in self.native.calls if c[1] == "/api/api_message"]), 2)
        self.assertNotIn("API_KEY_", self.env.read_text())
    def test_unknown_bootstrap_stops_and_cannot_replay(self):
        original = self.native.request
        def lose(*args): original(*args); raise A0Error("api_outcome_unknown")
        self.native.request = lose
        with self.assertRaisesRegex(A0Error, "unknown"): self.prepare()
        self.assertTrue((self.job / "bootstrap-intent.json").exists()); self.assertFalse(self.native.running)
        with self.assertRaisesRegex(ControllerError, "reconciliation"): self.prepare()
        self.assertEqual(len(self.native.calls), 1)
    def test_unknown_task_result_never_resubmits(self):
        prepared = self.prepare(); original = self.native.request
        def lose(row, method, path, payload, *args):
            result = original(row, method, path, payload, *args)
            if path.endswith("api_message"): raise A0Error("api_outcome_unknown")
            return result
        self.native.request = lose
        with self.assertRaisesRegex(A0Error, "unknown"): self.start()
        self.assertFalse(self.native.running); self.assertEqual(self.start().state, "unknown")
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith("api_message")]), 2)
    def test_pause_during_bootstrap_stops_actual_boundary(self):
        original = self.native.request
        def cancel(row, *args):
            self.assertEqual(self.controller.stop("task", PRINCIPAL, "pause").state, "stopped")
            return original(row, *args)
        self.native.request = cancel
        with self.assertRaisesRegex(A0Error, "expired"): self.prepare()
        self.assertEqual(self.store.get("task", OWNER)["stop_intent"], "pause")
        self.assertFalse(self.native.running)
    def test_shared_controller_has_harmless_preparation_assumption(self):
        controller = Controller(self.store, {"a0": self.binding})
        controller.stop("task", PRINCIPAL, "cancel")
        self.assertTrue(self.native.running)  # Regression demonstrated; A0 shim required.
    def test_input_missing_map_stops_before_task(self):
        self.native.file_hook = lambda result: {}
        with self.assertRaisesRegex(A0Error, "missing"): self.prepare((self.input(),))
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith("api_message")]), 1)
        self.assertFalse(self.native.running)
    def test_wrong_uploaded_bytes_not_trusted(self):
        self.native.file_hook = lambda result: {k: base64.b64encode(b"other").decode() for k in result}
        with self.assertRaisesRegex(A0Error, "mismatched"): self.prepare((self.input(),))
    def test_changed_host_input_prevents_submit(self):
        v = self.input(); self.prepare((v,)); Path(v.host_path).write_bytes(b"tamper")
        with self.assertRaisesRegex(A0Error, "input_changed"): self.start((v,))
        self.assertFalse(self.native.running)
    def test_duplicate_basename_and_foreign_input(self):
        v = self.input()
        with self.assertRaisesRegex(A0Error, "duplicate"): self.adapter._inputs(self.row, (v, v))
        with self.assertRaisesRegex(A0Error, "foreign"): self.adapter._inputs(self.row, (replace(v, host_path=str(self.env)),))
    def test_repeat_original_filename_gets_distinct_generated_names(self):
        a, b = self.input(index=0), self.input(index=1)
        self.assertNotEqual(Path(a.worker_path).name, Path(b.worker_path).name)
        self.prepare((a, b)); self.assertEqual(len(list((self.usr / "uploads").iterdir())), 2)
    def test_output_missing_partial_or_extra_maps(self):
        for failure in ({}, {"extra": ""}):
            with self.subTest(failure=failure):
                # Exercise verifier directly; no second task/model bootstrap.
                p = self.native.local(self.outputs[0].worker_path); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
                self.native.file_hook = lambda result, v=failure: v
                with self.assertRaisesRegex(A0Error, "missing_or_extra"): self.adapter._verified_files(self.row, (self.outputs[0].worker_path,))
    def test_partial_multi_file_map_and_duplicate_outputs_are_refused(self):
        second=replace(self.outputs[0],worker_path=self.outputs[0].worker_path.replace('-output.txt','-second.txt'))
        paths=(self.outputs[0].worker_path,second.worker_path)
        for path in paths:
            p=self.native.local(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x')
        self.native.file_hook=lambda result:{next(iter(result)):next(iter(result.values()))}
        with self.assertRaisesRegex(A0Error,'missing_or_extra'):self.adapter._verified_files(self.row,paths)
        self.outputs=(self.outputs[0],self.outputs[0])
        with self.assertRaisesRegex(A0Error,'duplicate'):self.adapter._outputs(self.row)
    def test_output_symlink_is_rejected_before_api(self):
        self.prepare()
        p = self.native.local(self.outputs[0].worker_path); p.parent.mkdir(parents=True); p.symlink_to(self.env)
        with self.assertRaises(OSError): self.adapter._verified_files(self.row, (self.outputs[0].worker_path,))
        self.assertFalse(any(c[1].endswith("api_files_get") for c in self.native.calls))
    def test_mutation_during_file_transfer_is_rejected(self):
        p = self.native.local(self.outputs[0].worker_path); p.parent.mkdir(parents=True); p.write_bytes(b"x")
        def change(result): p.write_bytes(b"y"); return result
        self.native.file_hook = change
        with self.assertRaisesRegex(A0Error, "mutable"): self.adapter._verified_files(self.row, (self.outputs[0].worker_path,))
    def test_file_decoding_negatives(self):
        for value in ("eA==\n", "eA=", "@@@=", "eB==", 123, "eHh4"):
            with self.subTest(value=value), self.assertRaises(A0Error): decode_file(value, 1)
    def test_traversal_and_noncanonical_output_paths(self):
        for p in ("/a0/usr/workdir/../secret", "/etc/passwd", self.outputs[0].worker_path.replace("/usr/", "/usr//"), self.outputs[0].worker_path + "/../x"):
            with self.subTest(path=p), self.assertRaises(A0Error): self.adapter._path(self.row, p)
    def test_progress_inactive_is_still_running(self):
        prepared = self.prepare(); self.adapter.inflight = True
        observed = self.adapter.observe(self.store.get("task", OWNER), prepared)
        self.assertEqual(observed.state, "running"); self.assertTrue(self.native.running)
        progress = json.loads(Path(observed.evidence_reference).read_text())
        self.assertEqual(set(progress), {"guid", "total_items", "progress_active"}); self.assertFalse(progress["progress_active"])
    def test_foreign_progress_context_refused(self):
        prepared = self.prepare(); self.adapter.inflight = True
        self.native.log_hook = lambda result: {**result, "context_id": "foreign"}
        with self.assertRaisesRegex(A0Error, "progress_unknown"): self.adapter.observe(self.row, prepared)
    def test_log_guid_change_requires_reconciliation(self):
        prepared=self.prepare();self.adapter.inflight=True
        self.adapter.observe(self.row,prepared)
        self.native.contexts[prepared.reference].log.guid='changed-guid'
        with self.assertRaisesRegex(A0Error,'requires_reconciliation'):self.adapter.observe(self.row,prepared)
    def test_expired_preparation_has_no_api_effect(self):
        self.clock = 1060
        with self.assertRaisesRegex(ControllerError, 'stopped_or_uncertain'): self.prepare()
        self.assertEqual(self.native.calls, []); self.assertFalse(self.native.running)
    def test_deadline_after_bootstrap_retained_without_task(self):
        original = self.native.request
        def expire(*args): result = original(*args); self.clock = 1060; return result
        self.native.request = expire
        with self.assertRaises(A0Error): self.prepare()
        self.assertEqual(len(self.native.calls), 1); self.assertFalse(self.native.running)
    def test_failed_native_persistence_stops_before_task(self):
        self.prepare()
        with patch.object(self.store, "attach_native", side_effect=OSError("metadata failure")):
            with self.assertRaises(OSError): self.start()
        self.assertEqual(len(self.native.calls), 1); self.assertFalse(self.native.running)
    def test_bootstrap_stop_persistence_failure_still_stops(self):
        with patch.object(self.store,'request_stop',side_effect=OSError('metadata unavailable')):
            with self.assertRaises(OSError): self.controller.stop('task',PRINCIPAL,'cancel')
        self.assertFalse(self.native.running)
        self.assertEqual(self.native.calls,[])
    def test_stop_uncertainty_is_not_success(self):
        prepared = self.prepare()
        self.native.stop = lambda row: self.native.unit()
        self.store.request_stop("task", OWNER, "cancel")
        with self.assertRaisesRegex(A0Error, "cessation"): self.adapter.stop(self.store.get("task", OWNER), prepared, "cancel")
    def test_changed_preparation_or_config_refused(self):
        prepared = self.prepare()
        with self.assertRaisesRegex(A0Error, "preparation"): self.adapter._prepared(self.row, replace(prepared, reference="forged"))
        self.outputs = (replace(self.outputs[0], logical_name="other"),)
        with self.assertRaisesRegex(A0Error, "changed"): self.start()
        self.assertEqual(len(self.native.calls), 1)
    def test_staged_mutation_is_rejected_without_reexecution(self):
        prepared = self.prepare(); self.start()
        artifact = self.adapter.artifacts(self.store.get("task", OWNER), prepared)[0]
        staged = self.staging / artifact.reference
        self.assertEqual(staged.stat().st_mode & 0o777, 0o400)
        staged.chmod(0o600); staged.write_bytes(b"tamper")
        with self.assertRaises(Exception): self.start()
        self.assertEqual(len([c for c in self.native.calls if c[1].endswith("api_message")]), 2)
    def test_private_key_cleanup_preserves_native_generated_fields(self):
        with self.env.open("a") as f: f.write("A0_GENERATED_STATE=retained\n")
        with self.assertRaisesRegex(A0Error, "cessation"): self.keys.remove(cessation_confirmed=False)
        self.keys.remove(cessation_confirmed=True); self.keys.remove(cessation_confirmed=True)
        self.assertEqual(self.env.read_text(), "AUTH_LOGIN=fixture\nA0_GENERATED_STATE=retained\n")
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
    def test_keys_refuse_existing_changed_or_unsafe_file(self):
        with self.assertRaisesRegex(A0Error, "existing"): prepare_keys(self.usr, lambda _: "synthetic")
        self.env.write_text(self.env.read_text().replace("synthetic-secret-", "changed-"))
        with self.assertRaisesRegex(A0Error, "changed"): self.keys.remove(cessation_confirmed=True)
        self.env.chmod(0o644)
        with self.assertRaises(Exception): prepare_keys(self.usr, lambda _: "synthetic")
    def test_native_file_real_symlink_hardlink_fifo_and_limit_controls(self):
        p = self.native_root / "regular"; p.write_bytes(b"abc")
        self.assertEqual(native_file(str(self.native_root), "regular", 3)["sha256"], hashlib.sha256(b"abc").hexdigest())
        (self.native_root / "link").symlink_to(p); os.link(p, self.native_root / "hard")
        os.mkfifo(self.native_root / "fifo")
        for name in ("link", "hard", "regular", "fifo", "../regular"):
            with self.subTest(name=name), self.assertRaises((A0Error, OSError)): native_file(str(self.native_root), name, 2)
        (self.native_root / "dirlink").symlink_to(self.inputs_root, target_is_directory=True)
        with self.assertRaises(OSError): native_file(str(self.native_root), "dirlink/file", 10)
    def test_actual_generated_native_scripts_compile_and_secret_channel(self):
        compile(file_script(), "native-file", "exec"); compile(API_SCRIPT, "native-api", "exec")
        self.assertIn("X-API-KEY", API_SCRIPT); self.assertIn("get_settings()['mcp_server_token']", API_SCRIPT)
        self.assertIn("NoRedirect", API_SCRIPT); self.assertIn("ProxyHandler({})", API_SCRIPT)
        self.assertNotIn("api_terminate_chat", API_SCRIPT)
        self.assertNotIn("synthetic-secret", repr(self.keys))
    def test_json_duplicate_nonfinite_and_truncation(self):
        for data in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":'):
            with self.assertRaises(A0Error): strict_json(data)


class NativeConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name).resolve()
        self.state = self.root / 'usr'; self.state.mkdir(mode=0o700)
        env = self.state / '.env'; env.write_text('AUTH_LOGIN=fixture\n'); env.chmod(0o600)
        self.keys = replace(prepare_keys(self.state, lambda ref: 'synthetic-secret-' + ref),
                            prepared_monotonic=99)
        self.git = self.root / 'git'; self.git.mkdir(mode=0o700)
        docker = pinned(self.root / 'docker', b'offline-docker-fixture')
        daemon = pinned(self.root / 'daemon.service', b'offline-daemon-fixture')
        policy = pinned(self.root / 'policy.json', b'{"state":"OFFLINE_FIXTURE_NOT_LIVE_GRANT"}')
        self.network = LocalNetwork('frw-local-reviewed', ('http://192.168.1.78:8001/v1', 'http://192.168.1.78:8002/v1'), policy)
        self.config = A0Deployment(docker, daemon, 'unix:///run/user/1000/frw/docker.sock',
            'sha256:' + 'c' * 64, self.state, self.git, ('-ceu', 'exec python run_ui.py --host=127.0.0.1 --port=5000'), self.network)
        for name, value in local_profile(self.network).items():
            p=self.state/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
        self.row = dict(worker_kind='a0', existing_task_id='task', admission_hash='d' * 64,
            created_at_unix=1000, deadline_unix=1060, budget_seconds=60, elapsed_seconds=0,
            stop_intent=None, native=None, supervisor={'scope':'user','unit':UNIT})
        labels = {'friday.rework.owner':'sol:task#1','friday.rework.assignment':'task',
            'friday.rework.generation':'1','friday.rework.plan':'d' * 64}
        self.grant = NativeGrant(CID, 'frw-a0-' + 'b' * 32, INV, labels, 1000, 1060,
            '/user.slice/frw-fixture/docker-' + CID + '.scope', Path('/proc/sys/kernel/random/boot_id').read_text().strip(), True, 99,
            daemon_invocation_id='e'*32,accepted_monotonic=98)
        self.obj = dict(Id=CID, Name='/' + self.grant.container_name, Image=self.config.image,
            Config=dict(Image=self.config.image, Labels=labels, Entrypoint=['/bin/bash'],
                        Cmd=list(self.config.command), WorkingDir='/a0'),
            HostConfig=dict(NetworkMode=self.network.name, Privileged=False, PortBindings={},
                PublishAllPorts=False, Binds=None, Devices=[], DeviceRequests=None, CapAdd=None,
                CapDrop=['ALL'], SecurityOpt=['no-new-privileges'], PidMode='', IpcMode='private',
                RestartPolicy={'Name':'no','MaximumRetryCount':0}, Memory=2147483648,
                MemorySwap=2147483648, NanoCpus=2000000000, PidsLimit=256),
            State={'Running':True,'Pid':123}, Mounts=[
                dict(Type='bind',Source=str(self.state),Destination='/a0/usr',RW=True,Propagation='rprivate'),
                dict(Type='bind',Source=str(self.git),Destination='/a0/.git',RW=False,Propagation='rprivate')])
        self.fields = {'RuntimeMaxUSec':'20s','ActiveEnterTimestampMonotonic':'100000000',
            'TimeoutStopUSec':'10s','Restart':'no',
            'MemoryMax':'268435456','CPUQuotaPerSecUSec':'1s','TasksMax':'64',
            'ExecStopPost':f'{{ path={docker.path} ; argv[]={docker.path} --host {self.config.socket} stop --time 2 {CID} ; ignore_errors=no ; }}'}
        self.commands = []; self.native_stops = 0
        self.daemon_fields={'ActiveState':'active','InvocationID':'e'*32,'MemoryMax':'21474836480',
            'CPUQuotaPerSecUSec':'8s','TasksMax':'2048','ControlGroup':'/user.slice/mock/daemon.service','MainPID':'789'}
        def stop(row): self.native_stops += 1; return UnitObservation(UNIT,INV,'inactive','dead','success',0,'',False)
        self.supervisor = NS(observe=lambda row: UnitObservation(UNIT,INV,'active' if self.obj['State']['Running'] else 'inactive',
                        'running' if self.obj['State']['Running'] else 'dead','success',123 if self.obj['State']['Running'] else 0,
                        '/mock' if self.obj['State']['Running'] else '',self.obj['State']['Running']),
            stop=stop, _command=lambda args, timeout: NS(returncode=0,stdout='\n'.join(k+'='+v for k,v in
                        (self.daemon_fields if args[1]=='daemon.service' else self.fields).items())))
        def runner(argv, data, timeout):
            self.commands.append((argv,data,timeout))
            if 'inspect' in argv: return json.dumps([self.obj]).encode()
            if 'stop' in argv: self.obj['State'] = {'Running':False,'Pid':0}; return b''
            payload = json.loads(data)
            return json.dumps({'ok':True,'body':base64.b64encode(json.dumps({'context_id':'ctx','response':'READY'}).encode()).decode()}).encode()
        self.boundary = A0NativeBoundary(self.config,self.grant,supervisor=self.supervisor,runner=runner,
            clock=lambda:1000,monotonic=lambda:100)
        self.boundary.key_material = self.keys
        self.boundary._sample = lambda obj, caps: None  # Kernel execution NOT_RUN in offline protocol controls.
        self.boundary._daemon_caps=lambda group:None
    def test_produced_config_consumed_by_native_boundary_and_argv(self):
        args = self.config.container_arguments(name=self.grant.container_name,labels=self.grant.labels)
        self.assertIn('--network=frw-local-reviewed',args); self.assertIn('--memory-swap=2147483648',args)
        self.assertEqual(args[-3:], [self.config.image,*self.config.command])
        self.assertTrue(self.boundary.admit(self.row))
        value = self.boundary.request(self.row,'POST','/api/api_message',{'message':'fixture'},50,1024)
        self.assertEqual(value['context_id'],'ctx')
        argv,data,timeout = self.commands[-1]; self.assertIn('-i',argv)
        self.assertEqual(json.loads(data)['payload'],{'message':'fixture'}); self.assertLess(timeout,20)
        self.assertNotIn('synthetic-secret',str(argv))
    def test_default_none_is_renderable_but_not_model_admitted(self):
        default = replace(self.config,network=LocalNetwork())
        self.assertIn('--network=none', default.container_arguments(name=self.grant.container_name,labels=self.grant.labels))
        self.boundary.config = default
        with self.assertRaisesRegex(A0Error,'not_admitted'): self.boundary.admit(self.row)
    def test_network_denies_generic_cloud_dns_and_unpinned_policy(self):
        bad = [LocalNetwork('host'), LocalNetwork('bridge'), LocalNetwork('local',('https://api.openai.com/v1','http://192.168.1.78:8002/v1'),self.network.policy),
            replace(self.network,endpoints=('http://localhost:8001/v1','http://192.168.1.78:8002/v1')),
            replace(self.network,policy=None), replace(self.network,endpoints=('http://192.168.1.78:8001/v1',)*2)]
        for network in bad:
            with self.subTest(network=network), self.assertRaises(A0Error): network.checked()
    def test_container_identity_exposure_mount_and_resource_negatives(self):
        original = copy.deepcopy(self.obj)
        changes = [('Id','x'*64),('Image','sha256:'+'e'*64),('Name','/foreign')]
        for key,value in changes:
            self.obj = copy.deepcopy(original); self.obj[key] = value
            with self.subTest(key=key),self.assertRaises(A0Error): self.boundary.inspect(self.row)
        for key,value in [('MemorySwap',-1),('NanoCpus',4000000000),('PidsLimit',1000),('Privileged',True),('PortBindings',{'5000/tcp':[]} ),('NetworkMode','host')]:
            self.obj = copy.deepcopy(original); self.obj['HostConfig'][key]=value
            with self.subTest(key=key),self.assertRaises(A0Error): self.boundary.inspect(self.row)
        self.obj=copy.deepcopy(original); self.obj['Mounts'][1]['RW']=True
        with self.assertRaises(A0Error): self.boundary.inspect(self.row)
        self.obj=copy.deepcopy(original); self.obj['Config']['Labels']['friday.rework.owner']='foreign'
        with self.assertRaises(A0Error): self.boundary.inspect(self.row)
    def test_deadline_extension_infinity_or_wrong_cleanup_refused(self):
        original=copy.deepcopy(self.fields)
        for key,value in [('RuntimeMaxUSec','infinity'),('RuntimeMaxUSec','2min'),('TimeoutStopUSec','90s'),
            ('Restart','always'),('ExecStopPost',original['ExecStopPost'].replace(CID,'f'*64))]:
            self.fields=copy.deepcopy(original);self.fields[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(A0Error): self.boundary.admit(self.row)
    def test_late_keys_wrong_boot_and_foreign_binding_refused(self):
        self.boundary.grant=replace(self.grant,keys_prepared_monotonic=101)
        with self.assertRaisesRegex(A0Error,'before_ui'): self.boundary.admit(self.row)
        with self.assertRaisesRegex(A0Error,'boot'): A0NativeBoundary(self.config,replace(self.grant,boot_id='obsolete-boot'))
        self.boundary.grant=self.grant
        for field,value in [('deadline_unix',1061),('existing_task_id','foreign'),('admission_hash','f'*64),
            ('native',{'invocation_id':'e'*32,'worker_reference':'a0:'+CID+':ctx'})]:
            with self.subTest(field=field),self.assertRaises(A0Error): self.boundary.inspect({**self.row,field:value})
    def test_actual_accepted_profile_consumer_and_drift_negatives(self):
        p=Path(os.environ['FRW_A0_ACCEPTED_MODULE'])
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'e882529ecd1d3df138647f636775e3b2d757c6319ccd0651bba7fc10f5048327')
        spec=importlib.util.spec_from_file_location('a0_accepted_schema_only',p)
        m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
        produced=local_profile(self.network)
        self.assertEqual(produced,m.templates())
        preset=produced['plugins/_model_config/presets.yaml'][0]
        cfg={'model_preset':'Default',**{s+'_model':preset[s] for s in ('chat','utility','embedding')}}
        m.probe_config_checked(cfg,'Default',preset)
        path=self.state/'plugins/_code_execution/config.json';path.write_text('{"ssh_enabled":"true"}')
        with self.assertRaisesRegex(A0Error,'profile_changed'): self.boundary.admit(self.row)
    def test_daemon_changed_identity_or_resource_is_refused(self):
        original=copy.deepcopy(self.daemon_fields)
        for key,value in [('InvocationID','f'*32),('MemoryMax','infinity'),('CPUQuotaPerSecUSec','16s'),('TasksMax','4096'),('ActiveState','inactive')]:
            self.daemon_fields=copy.deepcopy(original);self.daemon_fields[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(A0Error,'daemon_identity_or_caps'):self.boundary.admit(self.row)
    def test_caps_drift_does_not_block_owned_stop(self):
        self.obj['HostConfig']['MemorySwap']=-1
        self.assertTrue(self.boundary.stop(self.row).quiescent); self.assertEqual(self.native_stops,1)
        self.assertFalse(self.obj['State']['Running'])
    def test_wrong_container_never_gets_stop_and_native_stop_still_attempted(self):
        self.obj['Id']='e'*64
        with self.assertRaisesRegex(A0Error,'STOP_UNCONFIRMED'): self.boundary.stop(self.row)
        self.assertEqual(self.native_stops,1)
        self.assertFalse(any('stop' in argv for argv,_,_ in self.commands))
    def test_unconfirmed_native_stop_keeps_uncertainty(self):
        self.supervisor.stop=lambda row: UnitObservation(UNIT,INV,'active','running','success',123,'/mock',True)
        with self.assertRaisesRegex(A0Error,'STOP_UNCONFIRMED'): self.boundary.stop(self.row)
    def test_repeated_cleanup_only_observes_and_never_reissues_stop(self):
        self.assertTrue(self.boundary.stop(self.row).quiescent)
        self.assertTrue(self.boundary.stop(self.row).quiescent)
        self.assertEqual(self.native_stops,1)
        self.assertEqual(len([argv for argv,_,_ in self.commands if 'stop' in argv]),1)
    def test_changed_pinned_binary_never_executes(self):
        self.config.docker.path.write_bytes(b'changed')
        with self.assertRaises(Exception): self.boundary.inspect(self.row)
        self.assertEqual(self.commands,[])
    def test_actual_native_http_script_auth_redaction_and_redirect_refusal(self):
        helpers=types.ModuleType('helpers')
        helpers.dotenv=NS(load_dotenv=lambda:os.environ.update(self.keys.admitted()),
                          get_dotenv_file_path=lambda:str(self.keys.path));helpers.runtime=NS(initialize=lambda:None)
        helpers.settings=NS(get_settings=lambda:{'mcp_server_token':'native-synthetic-key'})
        captured=[]
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"response":"native-synthetic-key"}'
        class Opener:
            def open(self,req,timeout):captured.append((req,timeout));return Response()
        payload={'method':'POST','path':'/api/api_message','payload':{'message':'fixture'},
                 'admitted_keys':self.keys.admitted(),'timeout':2,'max_bytes':1024}
        output=io.StringIO();ns={}
        with patch.dict(sys.modules,{'helpers':helpers}),patch.dict(os.environ),patch('sys.stdin',io.StringIO(json.dumps(payload))),patch('urllib.request.build_opener',return_value=Opener()),contextlib.redirect_stdout(output):
            exec(compile(API_SCRIPT,'native-http','exec'),ns)
        req,timeout=captured[0]; self.assertEqual(req.get_header('X-api-key'),'native-synthetic-key')
        self.assertEqual(req.full_url,'http://127.0.0.1:5000/api/api_message');self.assertEqual(timeout,2)
        self.assertNotIn('native-synthetic-key',req.data.decode())
        value=strict_json(output.getvalue());body=decode_file(value['body'],1024)
        self.assertEqual(strict_json(body)['response'],'[redacted]')
        with self.assertRaisesRegex(ValueError,'redirect_refused'): ns['NoRedirect']().redirect_request(None,None,None,None,None,None)
    def test_native_http_errors_do_not_leak_credentials(self):
        helpers=types.ModuleType('helpers');helpers.dotenv=NS(load_dotenv=lambda:None);helpers.runtime=NS(initialize=lambda:None)
        helpers.settings=NS(get_settings=lambda:{'mcp_server_token':'native-synthetic-key'})
        payload={'method':'POST','path':'/api/api_message','payload':{'message':'fixture'},'timeout':2,'max_bytes':1024}
        output=io.StringIO()
        with patch.dict(sys.modules,{'helpers':helpers}),patch('sys.stdin',io.StringIO(json.dumps(payload))),patch('urllib.request.build_opener',side_effect=ValueError('native-synthetic-key')),contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):exec(compile(API_SCRIPT,'native-http','exec'),{})
        self.assertEqual(output.getvalue().strip(),'{"ok":false}')


if __name__ == "__main__": unittest.main()
