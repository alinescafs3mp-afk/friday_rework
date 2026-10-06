"""Affected adapter contract controls; native effects live in private evidence."""
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

package_root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_dsh_adapter_test", package_root / "__init__.py",
                                            submodule_search_locations=[str(package_root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_dsh_adapter_test.adapters.dsh import (
    AdapterError, DshAdapter, DshHostConfig, NativeEvents, PinnedFile, _json, _write)
from friday_dsh_adapter_test.adapters.contract import PreparedNative, VerifiedInput
from friday_dsh_adapter_test.boundary import WorkBrief
from friday_dsh_adapter_test.supervision import UnitObservation

SESSION = "session-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
INV = "a" * 32


def lines(*rows):
    return b"".join((json.dumps(v)+"\n").encode() for v in rows)


OPEN = {"type": "session", "sessionId": SESSION, "cwd": "/workspace"}
COMPLETE = lines(OPEN, {"type": "status", "phase": "turn_start", "turn": 1},
                 {"type": "status", "phase": "turn_end", "turn": 1, "reason": {"kind": "completed"}},
                 {"type": "final", "text": "worker report, host still verifies goal"})


class EventTests(unittest.TestCase):
    def reduce(self, data):
        e = NativeEvents()
        for line in data.splitlines(keepends=True):
            e.feed(line)
        return e

    def test_complete_requires_native_turn_and_final(self):
        e = self.reduce(COMPLETE)
        self.assertTrue(e.completed and e.final)
        self.assertEqual(e.session, SESSION)

    def test_incomplete_is_not_completed(self):
        for data in (b"", lines(OPEN), lines(OPEN,{"type":"status","phase":"turn_start","turn":1})):
            with self.subTest(data=data):
                self.assertFalse(self.reduce(data).completed)

    def test_malformed_foreign_duplicate_truncated(self):
        cases = [b"oops\n", b"{}\n", b'{"type":"session","type":"session"}\n',
                 lines({**OPEN,"cwd":"/foreign"}), lines({**OPEN,"sessionId":"invented"}),
                 lines(OPEN,OPEN), COMPLETE.rstrip(b"\n"),
                 lines(OPEN,{"type":"final","text":"not completed"}),
                 lines(OPEN,{"type":"status","phase":"turn_end","turn":1,"reason":{"kind":"completed"}}),
                 lines(OPEN,{"type":"status","phase":"turn_start","turn":True})]
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(AdapterError): self.reduce(data)

    def test_failed_native_turn_is_failure(self):
        e=self.reduce(lines(OPEN,{"type":"status","phase":"turn_start","turn":1},
                            {"type":"status","phase":"turn_end","turn":1,"reason":{"kind":"failed"}}))
        self.assertTrue(e.failed); self.assertFalse(e.completed)

    def test_tool_results_must_match_calls(self):
        prefix=lines(OPEN,{"type":"status","phase":"turn_start","turn":1},
                     {"type":"status","phase":"step_start","turn":1,"step":1},
                     {"type":"tool_call","callId":"c","tool":"read","input":{}})
        suffix=lines({"type":"status","phase":"step_end","turn":1,"step":1},
                     {"type":"status","phase":"turn_end","turn":1,"reason":{"kind":"completed"}},
                     {"type":"final","text":"done"})
        with self.assertRaises(AdapterError):self.reduce(prefix+suffix)
        self.assertTrue(self.reduce(prefix+lines({"type":"tool_result","callId":"c","status":"completed"})+suffix).final)
        for call in ("foreign",):
            with self.assertRaises(AdapterError):self.reduce(prefix+lines({"type":"tool_result","callId":call,"status":"completed"}))


class FakeSupervisor:
    def __init__(self):
        self.running=False; self.launched=False; self.stops=0
    @staticmethod
    def description(a):return "Friday rework "+a["admission_hash"]
    def observe(self,a):
        inv=INV if self.launched else ""
        if self.launched and a.get("native") and a["native"]["invocation_id"] != inv:raise AdapterError("native_invocation_changed")
        return UnitObservation(a["supervisor"]["unit"],inv,"active" if self.running else "inactive",
                               "running" if self.running else "dead","success",123 if self.running else 0,
                               "/fake/unit" if self.running else "",self.running,not self.launched)
    def stop(self,a):
        self.observe(a);self.stops+=1;self.running=False;return self.observe(a)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        payload=self.root/"payload";payload.mkdir();(payload/"apps/cli/lib").mkdir(parents=True)
        tool=self.root/"tool";tool.mkdir();(tool/"node").write_bytes(b"node")
        (payload/"apps/cli/lib/bin.js").write_bytes(b"cli")
        patchfile=self.root/"profile.yml";patchfile.write_bytes(b"trusted local profile\n")
        jobs=self.root/"jobs";jobs.mkdir(mode=0o700);job=jobs/"job";job.mkdir(mode=0o700)
        def pin(p):return PinnedFile(p,hashlib.sha256(p.read_bytes()).hexdigest())
        self.brief=WorkBrief("dsh","fix only owned source","unchanged tests pass")
        self.now=time.time()
        self.row={"existing_task_id":"existing-task","admission_hash":"b"*64,
                  "owner":{k:"host" for k in ("bot_id","user_id","chat_id","thread_id","message_id","session_key","session_id","profile")},
                  "worker_kind":"dsh","brief_sha256":hashlib.sha256(json.dumps(vars(self.brief),sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                  "workspace_reference":str(job),"supervisor":{"scope":"user","unit":"friday-rework-worker-"+"c"*32+".service"},
                  "created_at_unix":self.now,"budget_seconds":60,"deadline_unix":self.now+60,"elapsed_seconds":0,
                  "submission_observation":"NOT_SUBMITTED","preparation_reserved":False,"native":None,"stop_intent":None,"execution_observation":None,
                  "goal_verification":"NOT_RUN","delivery":"NOT_RUN"}
        self.config=DshHostConfig(jobs,payload,tool,pin(tool/"node"),pin(payload/"apps/cli/lib/bin.js"),pin(patchfile),(),
                                 lambda:{},lambda a:copy.deepcopy(self.row),"LOCAL_TEST_KEY")
        self.sup=FakeSupervisor();self.adapter=DshAdapter(self.config,supervisor=self.sup,clock=lambda:self.now)
    def prep(self):return self.adapter.prepare(self.row,self.brief,())
    def launch(self,argv,**kw):
        self.argv=argv;self.env=kw["env"];self.sup.launched=True;self.sup.running=True
        (Path(self.row["workspace_reference"])/".dsh-adapter/events.ndjson").write_bytes(lines(OPEN))
        return subprocess.CompletedProcess(argv,0,b"",("Running as unit; invocation ID: "+INV+"\n").encode())

    def test_preparation_is_durable_harmless_and_reusable(self):
        with patch("subprocess.run",side_effect=AssertionError("no effects")):
            p=self.prep();self.assertEqual(p,self.prep())
        self.assertEqual(_json(Path(p.receipt_reference))["identity"]["existing_task_id"],"existing-task")
        self.assertFalse(self.sup.launched)
        self.assertFalse((Path(p.receipt_reference).parent/"submission.json").exists())

    def test_submit_unknown_once_and_actual_callback(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN";seen=[]
        with patch("subprocess.run",side_effect=self.launch) as run:
            o=self.adapter.submit(self.row,self.brief,(),p,seen.append)
            self.assertEqual(o.worker_reference,SESSION);self.assertEqual(o.invocation_id,INV)
            self.assertEqual(seen,[o]);self.assertEqual(run.call_count,1)
            with self.assertRaises(AdapterError):self.adapter.submit(self.row,self.brief,(),p,seen.append)
            self.assertEqual(run.call_count,1)
        self.assertIn("--property=RuntimeMaxSec=53.000000s",self.argv)
        self.assertIn("--property=MemoryMax=2147483648",self.argv)
        self.assertNotIn("--unshare-net",self.argv)
        self.assertIn("--remount-ro",self.argv)

    def test_submission_requires_durable_unknown(self):
        p=self.prep()
        with patch("subprocess.run") as r:
            with self.assertRaises(AdapterError):self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
            r.assert_not_called()

    def test_callback_failure_stops_and_retains_uncertainty(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        def broken(o):raise OSError("storage failed")
        with patch("subprocess.run",side_effect=self.launch):
            with self.assertRaises(OSError):self.adapter.submit(self.row,self.brief,(),p,broken)
        self.assertEqual(self.sup.stops,1);self.assertFalse(self.sup.running)
        self.assertEqual(self.row["submission_observation"],"UNKNOWN")

    def test_timeout_stops_exact_planned_boundary_no_retry(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        def uncertain(*a,**k):self.sup.launched=True;self.sup.running=True;raise subprocess.TimeoutExpired(a,5)
        with patch("subprocess.run",side_effect=uncertain) as r:
            with self.assertRaises(subprocess.TimeoutExpired):self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
            self.assertEqual(r.call_count,1)
        self.assertFalse(self.sup.running)
        self.assertEqual(self.adapter.observe(self.row,p).state,"unknown")

    def test_stop_intent_after_callback_prevails(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        def callback(o):self.row["stop_intent"]="cancel"
        with patch("subprocess.run",side_effect=self.launch):
            self.assertEqual(self.adapter.submit(self.row,self.brief,(),p,callback).state,"stopped")
        self.assertFalse(self.sup.running)

    def test_expired_pause_cancel_never_launch(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        for intent in ("cancel","pause",None):
            self.row["stop_intent"]=intent
            if intent is None:self.now+=61
            with patch("subprocess.run") as r:
                with self.assertRaises(AdapterError):self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
                r.assert_not_called()

    def test_prepare_rejects_foreign_brief_input_mapping_hash_and_alias(self):
        with self.assertRaises(AdapterError):self.adapter.prepare(self.row,WorkBrief("dsh","changed","goal"),())
        p=self.root/"input";p.write_bytes(b"owned")
        good=VerifiedInput(str(p),"/job-input/verified/test",5,hashlib.sha256(p.read_bytes()).hexdigest(),"original-ingress")
        for v in (replace(good,worker_path="/workspace/arbitrary"),replace(good,sha256="a"*64),replace(good,size_bytes=6)):
            with self.assertRaises(AdapterError):self.adapter.prepare(self.row,self.brief,(v,))
        with self.assertRaises(AdapterError):self.adapter.prepare(self.row,self.brief,(good,good))
        alias=self.root/"alias";alias.symlink_to(p)
        with self.assertRaises(AdapterError):self.adapter.prepare(self.row,self.brief,(replace(good,host_path=str(alias)),))
        prep=self.adapter.prepare(self.row,self.brief,(good,))
        self.assertEqual((Path(prep.reference).parent/"inputs/verified/test").read_bytes(),b"owned")

    def test_changed_host_pins_block_new_effect(self):
        p=self.prep();self.config.node.path.write_bytes(b"drift")
        self.row["submission_observation"]="UNKNOWN"
        with patch("subprocess.run") as r:
            with self.assertRaises(AdapterError):self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
            r.assert_not_called()

    def test_foreign_preparation_owner_and_invocation(self):
        p=self.prep()
        with self.assertRaises(AdapterError):self.adapter.observe(self.row,PreparedNative("foreign",p.receipt_reference))
        foreign=copy.deepcopy(self.row);foreign["owner"]["bot_id"]="foreign"
        with self.assertRaises(AdapterError):self.adapter.observe(foreign,p)
        _write(Path(p.receipt_reference).parent/"invocation.json",{"invocation_id":INV})
        self.row["native"]={"invocation_id":"d"*32,"worker_reference":SESSION};self.row["submission_observation"]="OBSERVED"
        with self.assertRaises(AdapterError):self.adapter.observe(self.row,p)
        self.assertEqual(self.sup.stops,0)

    def test_observe_completion_is_not_goal_or_delivery_success(self):
        p=self.prep();c=Path(p.receipt_reference).parent
        self.sup.launched=True
        _write(c/"invocation.json",{"invocation_id":INV})
        (c/"events.ndjson").write_bytes(COMPLETE)
        _write(c/"terminal.json",{"INVOCATION_ID":INV,"SERVICE_RESULT":"success","EXIT_CODE":"exited","EXIT_STATUS":"0"})
        self.assertEqual(self.adapter.observe(self.row,p).state,"completed")
        self.assertEqual(self.row["goal_verification"],"NOT_RUN");self.assertEqual(self.row["delivery"],"NOT_RUN")
        (c/"events.ndjson").write_bytes(lines(OPEN))
        self.assertEqual(self.adapter.observe(self.row,p).state,"failed")

    def test_malformed_observation_stops_owned_boundary(self):
        p=self.prep();c=Path(p.receipt_reference).parent;self.sup.launched=True;self.sup.running=True
        _write(c/"invocation.json",{"invocation_id":INV});(c/"events.ndjson").write_bytes(b"bad\n")
        with self.assertRaises(AdapterError):self.adapter.observe(self.row,p)
        self.assertFalse(self.sup.running)

    def test_stop_requires_durable_intent_and_survives_payload_drift(self):
        p=self.prep();self.sup.launched=True;self.sup.running=True
        _write(Path(p.receipt_reference).parent/"invocation.json",{"invocation_id":INV})
        with self.assertRaises(AdapterError):self.adapter.stop(self.row,p,"cancel")
        with self.assertRaises(AdapterError):self.adapter.stop(self.row,p,"deadline")
        self.row["stop_intent"]="cancel";self.config.node.path.write_bytes(b"drift")
        self.assertEqual(self.adapter.stop(self.row,p,"cancel").state,"stopped")
        self.assertFalse(self.sup.running)

    def test_resource_grants_cannot_expand_or_choose_profile(self):
        for kwargs in ({"memory_bytes":2*1024**3+1},{"cpu_percent":401},{"tasks":65},{"shutdown_seconds":3},
                       {"profile":"arbitrary"},{"key_name":"bad name"}):
            with self.subTest(kwargs=kwargs),self.assertRaises(AdapterError):DshAdapter(replace(self.config,**kwargs))

    def test_crash_before_session_reconciles_actual_invocation_without_replay(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        self.sup.launched=True;self.sup.running=True
        with patch("subprocess.run") as launch:
            observed=self.adapter.observe(self.row,p)
            self.assertEqual(observed.invocation_id,INV)
            self.assertEqual(observed.state,"unknown")
            self.assertEqual(observed.worker_reference,"")
            self.assertEqual(_json(Path(p.receipt_reference).parent/"invocation.json"),{"invocation_id":INV})
            launch.assert_not_called()

    def test_collected_unit_recovers_terminal_invocation_after_crash(self):
        p=self.prep();c=Path(p.receipt_reference).parent;self.row["submission_observation"]="UNKNOWN"
        (c/"events.ndjson").write_bytes(COMPLETE)
        _write(c/"terminal.json",{"INVOCATION_ID":INV,"SERVICE_RESULT":"success","EXIT_CODE":"exited","EXIT_STATUS":"0"})
        observed=self.adapter.observe(self.row,p)
        self.assertEqual(observed.invocation_id,INV);self.assertEqual(observed.state,"completed")

    def test_retained_cancel_in_observe_stops_and_cancel_dominates_pause(self):
        p=self.prep();self.sup.launched=True;self.sup.running=True
        self.row["stop_intent"]="cancel"
        self.assertEqual(self.adapter.observe(self.row,p).state,"stopped")
        self.assertFalse(self.sup.running)
        self.assertEqual(self.adapter.stop(self.row,p,"pause").state,"stopped")

    def test_mutable_worker_directory_permissions_do_not_block_stop(self):
        p=self.prep();self.sup.launched=True;self.sup.running=True
        Path(p.reference).chmod(0o755);(Path(p.reference).parent/"workspace").chmod(0o755)
        self.row["stop_intent"]="cancel"
        self.assertEqual(self.adapter.stop(self.row,p,"cancel").state,"stopped")

    def test_cancel_during_handoff_is_checked_before_native_launch(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        from friday_dsh_adapter_test.adapters import dsh
        original=dsh._write
        def cancel_after_handoff(path,value):
            original(path,value)
            if path.name=="submission.json":self.row["stop_intent"]="cancel"
        with patch.object(dsh,"_write",side_effect=cancel_after_handoff),patch("subprocess.run") as launch:
            with self.assertRaises(AdapterError):self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
            launch.assert_not_called()

    def test_slow_host_environment_does_not_replenish_native_timer(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        def slow():self.now+=10;return {}
        self.adapter.config=replace(self.config,environment=slow)
        with patch("subprocess.run",side_effect=self.launch):
            self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
        self.assertIn("--property=RuntimeMaxSec=43.000000s",self.argv)
        grant=_json(Path(p.receipt_reference).parent/"launch-grant.json")
        self.assertEqual(grant["deadline_unix"],self.row["deadline_unix"])

    def test_live_partial_ndjson_remains_unknown_then_terminal_rejects(self):
        p=self.prep();c=Path(p.receipt_reference).parent;self.sup.launched=True;self.sup.running=True
        (c/"events.ndjson").write_bytes(lines(OPEN).rstrip(b"\n"))
        self.assertEqual(self.adapter.observe(self.row,p).state,"unknown")
        self.sup.running=False
        with self.assertRaises(AdapterError):self.adapter.observe(self.row,p)

    def _receipt_failure(self, mode, phase):
        from friday_dsh_adapter_test.adapters import dsh
        case=AdapterTests();case.setUp()
        try:
            prep=case.prep();control=Path(prep.receipt_reference).parent
            case.row["submission_observation"]="UNKNOWN"
            problem=OSError(28,"identity storage fault "+phase)
            original=dsh._write
            def fail(path,value):
                if path.name!="invocation.json":return original(path,value)
                if phase=="before_open":raise problem
                if phase=="partial_write":
                    fdopen=dsh.os.fdopen
                    class Partial:
                        def __init__(self,stream):self.stream=stream
                        def __enter__(self):return self
                        def __exit__(self,*args):return self.stream.__exit__(*args)
                        def write(self,data):self.stream.write(data[:1]);self.stream.flush();raise problem
                    with patch.object(dsh.os,"fdopen",side_effect=lambda *a,**kw:Partial(fdopen(*a,**kw))):
                        return original(path,value)
                if phase=="file_fsync":
                    with patch.object(dsh.os,"fsync",side_effect=problem):return original(path,value)
                if phase=="publication":
                    with patch.object(dsh.os,"link",side_effect=problem):return original(path,value)
                if phase=="after_publication":
                    link=dsh.os.link
                    def after(*a,**kw):link(*a,**kw);raise problem
                    with patch.object(dsh.os,"link",side_effect=after):return original(path,value)
                if phase=="directory_barrier":
                    with patch.object(dsh,"_sync",side_effect=problem):return original(path,value)
                original(path,value);raise problem
            with patch.object(dsh,"_write",side_effect=fail):
                with self.assertRaises(OSError) as raised:
                    if mode=="submit":
                        with patch("subprocess.run",side_effect=case.launch):
                            case.adapter.submit(case.row,case.brief,(),prep,lambda o:None)
                    else:
                        case.sup.launched=True;case.sup.running=True
                        case.adapter.observe(case.row,prep)
            self.assertIs(raised.exception,problem)
            self.assertTrue(problem.stop_confirmed)
            self.assertFalse(case.sup.running);self.assertGreaterEqual(case.sup.stops,1)
            self.assertEqual(case.row["submission_observation"],"UNKNOWN")
            self.assertIsNone(case.row["native"])
            # A failed write exposes either nothing or the whole published file.
            if (control/"invocation.json").exists():
                self.assertEqual(_json(control/"invocation.json"),{"invocation_id":INV})
            self.assertEqual(list(control.glob(".invocation.json.*")),[])
            case.row["stop_intent"]="cancel"
            restarted=DshAdapter(case.config,supervisor=case.sup,clock=lambda:case.now)
            stopped=restarted.stop(case.row,prep,"cancel")
            self.assertEqual(stopped.state,"stopped")
            self.assertEqual(stopped.invocation_id,INV)
        finally:case.doCleanups()

    def test_identity_publication_failpoints_stop_and_preserve_original_error(self):
        for mode in ("submit","observe"):
            for phase in ("before_open","partial_write","file_fsync","publication",
                          "after_publication","directory_barrier","post_write"):
                with self.subTest(mode=mode,phase=phase):self._receipt_failure(mode,phase)

    def test_atomic_receipt_never_overwrites_foreign_complete_file(self):
        p=self.root/"identity.json";_write(p,{"invocation_id":"f"*32})
        before=p.read_bytes()
        with self.assertRaises(FileExistsError):_write(p,{"invocation_id":INV})
        self.assertEqual(p.read_bytes(),before)
        self.assertEqual(list(self.root.glob(".identity.json.*")),[])

    def test_restart_stop_survives_corrupt_or_missing_auxiliary_and_preparation(self):
        p=self.prep();c=Path(p.receipt_reference).parent
        self.sup.launched=True;self.sup.running=True;self.row["stop_intent"]="cancel"
        for data in (None,b"{",b"{}",b'{"invocation_id":"bad"}'):
            with self.subTest(data=data):
                self.sup.running=True
                if data is not None:(c/"invocation.json").write_bytes(data)
                else:(c/"invocation.json").unlink(missing_ok=True)
                (c/"preparation.json").write_bytes(b"{")
                restarted=DshAdapter(self.config,supervisor=self.sup,clock=lambda:self.now)
                with patch("subprocess.run") as launch,patch("friday_dsh_adapter_test.adapters.dsh._write",side_effect=AssertionError("stop is read-only")):
                    o=restarted.stop(self.row,p,"cancel")
                    self.assertEqual(o.invocation_id,INV);self.assertEqual(o.worker_reference,"")
                    self.assertEqual(o.state,"stopped");self.assertFalse(self.sup.running)
                    launch.assert_not_called()

    def test_corrupt_recovery_reports_original_error_after_confirmed_stop(self):
        p=self.prep();c=Path(p.receipt_reference).parent
        (c/"invocation.json").write_bytes(b"{");self.sup.launched=True;self.sup.running=True
        with self.assertRaises(json.JSONDecodeError) as ex:self.adapter.observe(self.row,p)
        self.assertTrue(ex.exception.stop_confirmed);self.assertFalse(self.sup.running)
        self.assertEqual((c/"invocation.json").read_bytes(),b"{")

    def test_retained_intent_precedes_all_launch_files_and_never_writes_identity(self):
        p=self.prep();c=Path(p.receipt_reference).parent
        self.config.node.path.write_bytes(b"drift");(c/"preparation.json").write_bytes(b"{")
        self.sup.launched=True
        for intent in ("cancel","pause"):
            self.sup.running=True;self.row["stop_intent"]=intent
            with patch("friday_dsh_adapter_test.adapters.dsh._write",side_effect=AssertionError("stop must not persist")):
                o=self.adapter.observe(self.row,p)
            self.assertEqual(o.state,"stopped");self.assertEqual(o.worker_reference,"")
            self.assertFalse(self.sup.running)

    def test_consumed_original_budget_precedes_wall_clock_and_drift(self):
        p=self.prep();self.sup.launched=True;self.sup.running=True
        self.row["native"]={"invocation_id":INV,"worker_reference":SESSION}
        self.row["submission_observation"]="OBSERVED";self.row["elapsed_seconds"]=60
        self.row["execution_observation"]="retained evidence"
        self.config.node.path.write_bytes(b"drift")
        self.assertLess(self.now,self.row["deadline_unix"])
        o=self.adapter.observe(self.row,p)
        self.assertEqual(o.state,"stopped");self.assertEqual(o.worker_reference,SESSION)
        self.assertEqual(o.elapsed_seconds,60);self.assertFalse(self.sup.running)
        self.assertEqual(self.adapter.stop(self.row,p,"deadline").state,"stopped")

    def test_launch_timer_preserves_consumed_budget_after_clock_rewind(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        # UNKNOWN cannot legally have elapsed time without native identity;
        # directly inspect the timer arithmetic on a retained checked row.
        row=copy.deepcopy(self.row);row["elapsed_seconds"]=50
        self.now-=10
        self.assertEqual(self.adapter._remaining(row),3)

    def test_stop_failure_does_not_hide_initiating_error_or_claim_settled(self):
        from friday_dsh_adapter_test.adapters import dsh
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        original=dsh._write;problem=OSError(28,"original storage failure")
        def fail(path,value):
            if path.name=="invocation.json":raise problem
            return original(path,value)
        stop_error=AdapterError("native_stop_unconfirmed")
        with patch.object(dsh,"_write",side_effect=fail),patch.object(self.sup,"stop",side_effect=stop_error),patch("subprocess.run",side_effect=self.launch):
            with self.assertRaises(OSError) as ex:self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
        self.assertIs(ex.exception,problem);self.assertFalse(problem.stop_confirmed)
        self.assertIs(problem.stop_error,stop_error);self.assertTrue(self.sup.running)
        self.assertEqual(self.row["submission_observation"],"UNKNOWN")
        self.row["stop_intent"]="cancel";self.adapter.stop(self.row,p,"cancel")

    def test_callback_store_unreadable_stops_with_last_checked_row(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        problem=OSError("association unavailable")
        def unreadable():
            self.adapter.config=replace(self.config,current_association=lambda a:(_ for _ in ()).throw(problem))
            raise problem
        with patch("subprocess.run",side_effect=self.launch):
            with self.assertRaises(OSError) as ex:self.adapter.submit(self.row,self.brief,(),p,lambda o:unreadable())
        self.assertIs(ex.exception,problem);self.assertTrue(problem.stop_confirmed)
        self.assertFalse(self.sup.running)
        self.adapter.config=self.config
        self.row["stop_intent"]="cancel";self.adapter.stop(self.row,p,"cancel")

    def test_actual_session_retained_on_empty_crash_output(self):
        p=self.prep();self.sup.launched=True;self.sup.running=True
        self.row["native"]={"invocation_id":INV,"worker_reference":SESSION}
        self.row["submission_observation"]="OBSERVED"
        self.assertEqual(self.adapter.observe(self.row,p).worker_reference,SESSION)
        self.row["stop_intent"]="cancel"
        self.assertEqual(self.adapter.stop(self.row,p,"cancel").worker_reference,SESSION)

    def test_valid_contradictory_auxiliary_identity_refuses_stop_and_is_not_overwritten(self):
        p=self.prep();c=Path(p.receipt_reference).parent
        self.sup.launched=True;self.sup.running=True
        self.adapter._remember(self.row,c,INV)
        _write(c/"invocation.json",{"invocation_id":"f"*32})
        before=(c/"invocation.json").read_bytes();self.row["stop_intent"]="cancel"
        with self.assertRaisesRegex(AdapterError,"native_invocation_changed"):
            self.adapter.stop(self.row,p,"cancel")
        self.assertEqual(self.sup.stops,0);self.assertTrue(self.sup.running)
        self.assertEqual((c/"invocation.json").read_bytes(),before)

    def test_unknown_launch_exception_keeps_original_and_stops_without_identity_write(self):
        p=self.prep();self.row["submission_observation"]="UNKNOWN"
        problem=subprocess.TimeoutExpired("systemd-run",5)
        def uncertain(*args,**kwargs):
            self.sup.launched=True;self.sup.running=True;raise problem
        with patch("subprocess.run",side_effect=uncertain):
            with self.assertRaises(subprocess.TimeoutExpired) as ex:self.adapter.submit(self.row,self.brief,(),p,lambda o:None)
        self.assertIs(ex.exception,problem);self.assertTrue(problem.stop_confirmed)
        self.assertFalse(self.sup.running)
        self.assertFalse((Path(p.receipt_reference).parent/"invocation.json").exists())
        self.assertEqual(self.row["submission_observation"],"UNKNOWN")



if __name__ == "__main__":unittest.main()
