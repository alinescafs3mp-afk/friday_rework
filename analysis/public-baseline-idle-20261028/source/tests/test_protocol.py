"""Offline protocol tests. They do not call the Spark model or the embedder."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qpb.atomic import atomic_write_json, recover_jsonl_tail  # noqa: E402
from qpb.cli import main  # noqa: E402
from qpb.corpus import get_corpus  # noqa: E402
from qpb.endpoint import redact_headers  # noqa: E402
from qpb.errors import OutcomeUnknownError, ProtocolDiagnostic  # noqa: E402
from qpb.extract import extract_code, gpqa_letter, split_final  # noqa: E402
from qpb.guard import assert_real_targets_blocked, install_socket_guard, restore_socket_guard  # noqa: E402
from qpb.lcb_sandbox import grade  # noqa: E402
from qpb.pins import EXPECTED  # noqa: E402
from qpb.prepare import plan, prepare  # noqa: E402
from qpb.profile import generation_body, load_profile  # noqa: E402
from qpb.report import is_full_model_baseline, write_report  # noqa: E402
from qpb.runner import Runner, live_permitted  # noqa: E402
from qpb.score import score_gpqa, score_ifbench, score_run  # noqa: E402
from qpb.store import RunStore  # noqa: E402

PY = sys.executable
PROD = "http://192.0.2.195:30000/v1"


def _outcome(text: str, reasoning: str = "secretword") -> dict:
    return {
        "content": text,
        "reasoning": reasoning,
        "reasoning_delta_field": "reasoning_content",
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
        "reasoning_tokens": None,
        "ttft_s": 0.01,
        "first_final_content_s": 0.02,
        "seed_echoed": None,
        "http_status": 200,
        "raw": "data: fixture\n\n",
        "wall_s": 0.05,
        "truncated": False,
    }


class RecordingTransport:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def post(self, base_url, headers, body, timeout_s, mark_sending):
        self.calls.append({"base_url": base_url, "headers": dict(headers), "body": body})
        return self.handler(self, base_url, headers, body, timeout_s, mark_sending)


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FRIDAY_BENCH_API_KEY"] = "SENTINEL-NOT-A-KEY"
        os.environ["QPB_TEST_KEY"] = "mock-secret-not-a-real-token"
        cls.runtime = prepare(ROOT, ROOT / "config" / "endpoint.json")
        cls.profile = load_profile(ROOT / "config" / "public-core-v1.yaml")
        cls.corpus = get_corpus(ROOT)

    def tearDown(self):
        restore_socket_guard()

    def _endpoint(self, url: str, kind: str = "fixture") -> dict:
        return {
            "base_url": url,
            "model": "fixture-model",
            "api_key_env": "QPB_TEST_KEY",
            "kind": kind,
            "live_checked": False,
        }

    def _runner(self, run_id, runs, endpoint, transport, **kwargs):
        from qpb.prepare import identity_for

        return Runner(
            ROOT,
            runs,
            run_id,
            self.profile,
            endpoint,
            identity_for(ROOT, endpoint),
            allow_live=True,
            pilot_only=kwargs.get("pilot_only", True),
            window_hours=kwargs.get("window_hours"),
            transport_factory=lambda: transport,
            command=kwargs.get("command", "run"),
        )

    def test_counts_and_ids_match_manifest(self):
        document = json.loads((ROOT / "manifests" / "datasets.json").read_text(encoding="utf-8"))
        for name, count in EXPECTED.items():
            self.assertEqual(document[name]["count"], count)
            self.assertEqual(len(document[name]["ids"]), count)
            self.assertEqual(len(set(document[name]["ids"])), count)
            self.assertEqual(len(document[name]["pilot_ids"]), 5)
            self.assertTrue(set(document[name]["pilot_ids"]).issubset(document[name]["ids"]))
        self.assertEqual(sum(EXPECTED.values()), 673)
        self.assertEqual(document["lcb"]["config"], "v6")
        self.assertNotIn("release_v6", document["lcb"]["ids"])

    def test_reasoning_does_not_enter_ifbench_or_gpqa(self):
        task = {
            "task_id": "fixture",
            "prompt": "Do not use the forbidden word.",
            "instruction_id_list": ["keywords:forbidden_words"],
            "kwargs": [{"forbidden_words": ["secretword"]}],
        }
        raw = "<think>secretword is the clue</think>\nhello there"
        final, reasoning = split_final(raw, None)
        self.assertNotIn("secretword", final)
        self.assertIn("secretword", reasoning)
        self.assertTrue(score_ifbench(ROOT, task, final)["prompt_strict"])
        self.assertFalse(score_ifbench(ROOT, task, raw)["prompt_strict"])

        final_b, _ = split_final("<think>ANSWER: A</think>\nANSWER: B", "The letter C appears here")
        self.assertEqual(gpqa_letter(final_b), "B")
        self.assertIsNone(gpqa_letter("I think the answer is C because of the diagram"))
        self.assertEqual(gpqa_letter("some reasoning\nB"), "B")
        scored = score_gpqa({"correct_letter": "B"}, final_b)
        self.assertEqual(scored["extracted"], "B")
        self.assertTrue(scored["correct"])
        missing = score_gpqa({"correct_letter": "B"}, "I think the answer is C")
        self.assertEqual(missing["outcome"], "parse_error")
        self.assertIsNone(missing["extracted"])

    def test_lcb_extracts_last_fence_only(self):
        text = "```python\nprint(1)\n```\nlater\n```python\nprint(2)\n```"
        self.assertEqual(extract_code(text), "print(2)")
        self.assertEqual(extract_code("no fence"), "")

    def test_request_body_is_explicit(self):
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        ifbench = generation_body(
            endpoint, self.profile, "ifbench", [{"role": "user", "content": "q"}], "ifbench__0__a1"
        )
        gpqa = generation_body(
            endpoint, self.profile, "gpqa", [{"role": "user", "content": "q"}], "gpqa__0__a1"
        )
        self.assertEqual(ifbench["temperature"], 0.0)
        self.assertEqual(ifbench["max_tokens"], 16384)
        self.assertEqual(gpqa["temperature"], 1.0)
        self.assertEqual(gpqa["top_p"], 0.95)
        self.assertEqual(gpqa["max_tokens"], 32768)
        self.assertEqual(ifbench["chat_template_kwargs"], {"enable_thinking": True})
        for body in (ifbench, gpqa):
            self.assertEqual(body["top_k"], 20)
            self.assertEqual(body["min_p"], 0.0)
            self.assertEqual(body["seed"], 42)
            self.assertNotIn("tools", body)
            self.assertNotIn("stop", body)
            self.assertNotIn("reasoning_effort", body)
            self.assertNotIn("preserve_thinking", json.dumps(body))
            self.assertNotIn("SENTINEL-NOT-A-KEY", json.dumps(body))

    def test_guard_blocks_real_targets_without_connecting(self):
        install_socket_guard()
        notes = assert_real_targets_blocked()
        self.assertEqual(len(notes), 3)
        self.assertTrue(all("192.0.2." in note for note in notes))

    def test_authorization_file_is_not_permission(self):
        self.assertFalse(live_permitted(False, {"granted": True}))
        self.assertTrue(live_permitted(True, {"granted": False}))

    def test_run_without_flag_does_not_import_client(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        script = (
            "import sys\n"
            "from qpb.cli import main\n"
            "rc = main(['run', '--profile', 'public-core-v1', '--run', 'not-started', '--root', sys.argv[1]])\n"
            "assert rc == 2, rc\n"
            "assert 'qpb.httpclient' not in sys.modules\n"
            "assert 'qpb.runner' not in sys.modules\n"
            "print('refused')\n"
        )
        completed = subprocess.run(
            [PY, "-c", script, str(ROOT)],
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("refused", completed.stdout)
        self.assertIn("ОТКАЗ", completed.stdout)

    def test_no_args_starts_nothing(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        completed = subprocess.run(
            [PY, "-m", "qpb"],
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("AWAITING_USER_START", completed.stdout)
        self.assertNotIn("RUNNING", completed.stdout)

    def test_sandbox_matches_stdio_and_hides_host(self):
        ok = grade(
            "import sys\nsys.stdout.write(sys.stdin.read())",
            {"fn_name": None, "inputs": ["7\n"], "outputs": ["7\n"]},
            per_test_timeout=6,
            wall_cap=30,
        )
        self.assertEqual(ok["outcome"], "correct", ok)
        hidden = grade(
            "import os\nprint('yes' if os.path.exists('/home/baseline-owner') else 'no')",
            {"fn_name": None, "inputs": ["\n"], "outputs": ["no\n"]},
            per_test_timeout=6,
            wall_cap=30,
        )
        self.assertEqual(hidden["outcome"], "correct", hidden)
        added = grade(
            "def solve(a, b):\n    return a + b\n",
            {"fn_name": "solve", "inputs": ["1\n2"], "outputs": ["3"]},
            per_test_timeout=6,
            wall_cap=30,
        )
        self.assertEqual(added["outcome"], "correct", added)
        wrong = grade(
            "def solve(a, b):\n    return a - b\n",
            {"fn_name": "solve", "inputs": ["1\n2"], "outputs": ["3"]},
            per_test_timeout=6,
            wall_cap=30,
        )
        self.assertEqual(wrong["outcome"], "wrong_answer")
        timed = grade(
            "while True:\n    pass\n",
            {"fn_name": None, "inputs": ["\n"], "outputs": ["\n"]},
            per_test_timeout=1,
            wall_cap=30,
        )
        self.assertEqual(timed["outcome"], "timeout")

    def test_pause_saves_current_and_skips_next(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-pause-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        store_holder = {}

        def handler(transport, base_url, headers, body, timeout_s, mark_sending):
            mark_sending()
            store_holder["store"].set_control(pause=True, stop=False)
            return _outcome("hello")

        transport = RecordingTransport(handler)
        runner = self._runner("pause-case", runs, endpoint, transport)
        store_holder["store"] = runner.store
        code = runner.execute()
        self.assertEqual(code, 0, "pause should end the invocation cleanly")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(runner.store.manifest()["state"], "PAUSED")
        benchmark = transport.calls[0]["body"]["messages"]
        self.assertTrue(benchmark)
        saved = list(runner.store.predictions.glob("*.json"))
        self.assertEqual(len(saved), 1)
        prediction = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assertEqual(prediction["outcome"], "complete")
        self.assertNotIn("mock-secret-not-a-real-token", json.dumps(prediction))
        request = json.loads(next(runner.store.requests.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(request["headers"]["Authorization"], "REDACTED")
        blob = json.dumps(request)
        self.assertNotIn("mock-secret-not-a-real-token", blob)
        self.assertNotIn("SENTINEL-NOT-A-KEY", blob)

    def test_resume_does_not_repeat_saved_generation(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-resume-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        first = RecordingTransport(lambda *args: (_ for _ in ()).throw(AssertionError("bind later")))

        def first_handler(transport, base_url, headers, body, timeout_s, mark_sending):
            mark_sending()
            transport_store.set_control(pause=True, stop=False)
            return _outcome("hello")

        transport_store = None
        first.handler = first_handler
        runner = self._runner("resume-case", runs, endpoint, first)
        transport_store = runner.store
        self.assertEqual(runner.execute(), 0)
        saved_id = json.loads(next(runner.store.predictions.glob("*.json")).read_text(encoding="utf-8"))["task_id"]
        second_calls = []

        def second_handler(transport, base_url, headers, body, timeout_s, mark_sending):
            second_calls.append(body["rid"])
            mark_sending()
            transport_store.set_control(pause=True, stop=False)
            return _outcome("hello")

        second = RecordingTransport(second_handler)
        again = self._runner("resume-case", runs, endpoint, second, command="resume", pilot_only=True)
        self.assertEqual(again.execute(), 0)
        self.assertEqual(len(second_calls), 1)
        self.assertNotIn(saved_id, second_calls[0].split("__a")[0].split("__", 1)[1] if False else second_calls[0])
        self.assertNotIn(f"__{saved_id}__", second_calls[0])

    def test_unknown_drop_is_not_posted_again(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-drop-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        seen = []

        def drop(transport, base_url, headers, body, timeout_s, mark_sending):
            mark_sending()
            seen.append(body["rid"])
            raise OutcomeUnknownError("connection dropped")

        runner = self._runner("drop-case", runs, endpoint, RecordingTransport(drop))
        self.assertEqual(runner.execute(), 2)
        self.assertEqual(len(seen), 1)
        self.assertEqual(runner.store.manifest()["state"], "INCOMPLETE")
        note = runner.store.latest_attempt("ifbench", seen[0].split("__")[1])
        # The first pilot task is ifbench, so the rid starts with ifbench.
        self.assertTrue(seen[0].startswith("ifbench__"))
        self.assertIn("OUTCOME_UNKNOWN", json.dumps(note))

        def again(transport, base_url, headers, body, timeout_s, mark_sending):
            seen.append(body["rid"])
            mark_sending()
            transport_store.set_control(pause=True, stop=False)
            return _outcome("hello")

        transport_store = runner.store
        resume = self._runner("drop-case", runs, endpoint, RecordingTransport(again), command="resume")
        self.assertEqual(resume.execute(), 2)
        self.assertEqual(len(seen), 1, "unknown server work blocks the entire endpoint")

    def test_fingerprint_mismatch_does_not_call_transport(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-fp-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        calls = []
        transport = RecordingTransport(lambda *args: calls.append("x"))
        runner = self._runner("fp-case", runs, endpoint, transport)
        runner.store.ensure_dirs()
        atomic_write_json(
            runner.store.dir / "manifest.json",
            {
                "run_id": "fp-case",
                "state": "PAUSED",
                "generation_fingerprint": "0" * 64,
                "pilot_only": True,
                "kind": "fixture",
            },
        )
        with self.assertRaises(Exception) as caught:
            runner.execute()
        self.assertIn("fingerprint", str(caught.exception))
        self.assertEqual(calls, [])
        self.assertEqual(transport.calls, [])

    def test_partial_record_is_not_success(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-partial-"))
        self.addCleanup(shutil.rmtree, runs, True)
        store = RunStore(runs, "partial-case")
        store.ensure_dirs()
        broken = store.predictions / "ifbench__broken.json"
        broken.write_text("{", encoding="utf-8")
        (store.dir / "events.jsonl").write_text('{"event":"ok"}\n{"event":', encoding="utf-8")
        notes = store.reconcile()
        self.assertTrue(notes["events_tail"]["dropped"])
        loaded = store.read_prediction("ifbench", "broken")
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["value"]["outcome"], "PARTIAL_RECORD")
        self.assertFalse(loaded["value"]["success"])
        self.assertFalse(store.prediction_complete("ifbench", "broken"))
        tail = recover_jsonl_tail(store.dir / "events.jsonl")
        self.assertFalse(tail["dropped"])

    def test_score_offline_does_not_generate_and_fixture_is_not_a_full_baseline(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-score-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        holder = {}

        def handler(transport, base_url, headers, body, timeout_s, mark_sending):
            mark_sending()
            if len(transport.calls) >= 2:
                holder["store"].set_control(pause=True, stop=False)
            bench = body["rid"].split("__", 1)[0]
            if bench == "gpqa":
                return _outcome("<think>ANSWER: A</think>\nANSWER: B", reasoning="C")
            if bench == "lcb":
                return _outcome("I will not emit a program")
            return _outcome("<think>secretword</think>\nhello there")

        transport = RecordingTransport(handler)
        runner = self._runner("fixture-score", runs, endpoint, transport)
        holder["store"] = runner.store
        self.assertEqual(runner.execute(), 0)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0]["base_url"], "http://127.0.0.1:9/v1")
        self.assertNotEqual(transport.calls[0]["base_url"], PROD)
        before = len(list(runner.store.predictions.glob("*.json")))
        sys.modules.pop("qpb.httpclient", None)
        score_run(ROOT, runner.store, generation_fingerprint=runner.store.manifest()["generation_fingerprint"])
        self.assertNotIn("qpb.httpclient", sys.modules)
        self.assertEqual(len(list(runner.store.predictions.glob("*.json"))), before)
        document = write_report(runner.store)
        self.assertEqual(document["kind"], "fixture")
        self.assertTrue(document["partial"])
        self.assertFalse(document["full_model_baseline"])
        self.assertFalse(is_full_model_baseline(document))
        self.assertFalse(document["benchmarks"]["ifbench"]["protocol_complete"])
        self.assertEqual(document["benchmarks"]["ifbench"]["expected_tasks"], 300)
        self.assertLess(document["benchmarks"]["ifbench"]["generated_tasks"], 300)
        text = (runner.store.dir / "baseline.md").read_text(encoding="utf-8")
        self.assertIn("FIXTURE", text)
        self.assertIn("не результат Qwen", text)
        reviews = list(runner.store.reviews.glob("*.json"))
        self.assertGreaterEqual(len(reviews), 673)
        not_run = 0
        for path in reviews:
            row = json.loads(path.read_text(encoding="utf-8"))
            if row["outcome"] == "not_run":
                not_run += 1
        self.assertGreater(not_run, 600)

    def test_window_stops_before_the_first_request(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-window-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        transport = RecordingTransport(lambda *args: (_ for _ in ()).throw(AssertionError("window sent a request")))
        runner = self._runner("window-case", runs, endpoint, transport, window_hours=0.0001)
        self.assertEqual(runner.execute(), 0)
        self.assertEqual(transport.calls, [])
        self.assertEqual(runner.store.manifest()["state"], "PAUSED")
        progress = runner.store.progress()
        self.assertIn("хвост", progress.get("tail", ""))

    def test_second_executor_is_refused(self):
        runs = Path(tempfile.mkdtemp(prefix="qpb-lock-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint("http://127.0.0.1:9/v1")
        transport = RecordingTransport(lambda *args: (_ for _ in ()).throw(AssertionError("locked runner sent")))
        runner = self._runner("lock-case", runs, endpoint, transport)
        runner.store.ensure_dirs()
        lock_path = runner.store.dir / "runner.lock"
        holder = subprocess.Popen(
            [
                PY,
                "-c",
                "import fcntl,os,time,sys; fd=os.open(sys.argv[1], os.O_RDWR|os.O_CREAT, 0o644); fcntl.flock(fd, fcntl.LOCK_EX); time.sleep(30)",
                str(lock_path),
            ]
        )
        self.addCleanup(holder.kill)
        self.addCleanup(holder.wait)
        import time

        time.sleep(0.3)
        self.assertEqual(runner.execute(), 2)
        self.assertEqual(transport.calls, [])

    def test_plan_and_report_stay_offline(self):
        install_socket_guard()
        code = plan(ROOT, ROOT / "config" / "endpoint.json", ROOT / "config" / "public-core-v1.yaml")
        self.assertEqual(code, 0)
        # report of a missing run is a local miss, not a connection
        rc = main(["report", "--run", "does-not-exist", "--root", str(ROOT)])
        self.assertEqual(rc, 2)

    def test_local_mock_endpoint_is_explicit(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                seen.append(json.loads(raw))
                body = (
                    'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
                    'data: {"choices":[{"delta":{"reasoning_content":"secretword"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
                    'data: {"choices":[{"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n\n'
                    "data: [DONE]\n\n"
                )
                raw_body = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(raw_body)))
                self.end_headers()
                self.wfile.write(raw_body)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        install_socket_guard({("127.0.0.1", port)})
        from qpb.httpclient import UrllibTransport

        runs = Path(tempfile.mkdtemp(prefix="qpb-mock-"))
        self.addCleanup(shutil.rmtree, runs, True)
        endpoint = self._endpoint(f"http://127.0.0.1:{port}/v1")
        runner = self._runner("mock-http", runs, endpoint, UrllibTransport(), window_hours=None)
        # Stop after the first real HTTP response.
        original = runner.store.set_control

        def stop_after(pause, stop):
            return original(pause=pause, stop=stop)

        def wrapped_post(base_url, headers, body, timeout_s, mark_sending):
            result = UrllibTransport.post(UrllibTransport(), base_url, headers, body, timeout_s, mark_sending)
            runner.store.set_control(pause=True, stop=False)
            return result

        runner.transport_factory = lambda: type("T", (), {"post": staticmethod(wrapped_post)})()
        self.assertEqual(runner.execute(), 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["temperature"], 0.0)
        self.assertNotIn("tools", seen[0])
        saved = json.loads(next(runner.store.predictions.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["final_answer"], "hello")
        self.assertIn("secretword", saved["reasoning"])
        self.assertNotIn("secretword", saved["final_answer"])
        self.assertIsNone(saved["usage"]["reasoning_tokens"])
        blob = (runs / "mock-http").read_text() if False else json.dumps(saved)
        self.assertNotIn("mock-secret-not-a-real-token", blob)
        self.assertNotIn(PROD, json.dumps(seen))


if __name__ == "__main__":
    unittest.main()
