import base64
from pathlib import Path
import unittest
import zlib
from types import SimpleNamespace
from unittest.mock import patch

from qpb.lcb_sandbox import official_grade, decode_private_tests
from qpb.paths import tool_root


class OfficialLCBTests(unittest.TestCase):
    def grade(self, code, tests, timeout=6):
        return official_grade(tool_root(), code, tests, per_test_timeout=timeout, wall_cap=30)

    def test_stdio_binary_stdin_uses_actual_official_verifier(self):
        result = self.grade("import sys\nsys.stdout.write(sys.stdin.buffer.read().decode())",
                            {"fn_name": None, "inputs": ["7\n"], "outputs": ["7\n"]})
        self.assertEqual(result["outcome"], "correct", result)
        self.assertEqual(result["scorer"], "official_testing_util")

    def test_call_solution_and_wrong_negative(self):
        tests = {"fn_name": "solve", "inputs": ["1\n2"], "outputs": ["3"]}
        self.assertEqual(self.grade("class Solution:\n def solve(self,a,b):\n  return a+b", tests)["outcome"], "correct")
        self.assertEqual(self.grade("def solve(a,b):\n return a-b", tests)["outcome"], "wrong_answer")

    def test_no_host_or_network_and_no_global_pickle(self):
        code = "import os,socket\ns=socket.socket()\ntry:\n s.connect(('192.0.2.1',9)); v='bad'\nexcept OSError:\n v='no'\nprint(v,os.path.exists('/home/baseline-owner'))"
        result = self.grade(code, {"fn_name": None, "inputs": ["\n"], "outputs": ["no False"]})
        self.assertEqual(result["outcome"], "correct", result)
        # REDUCE cannot construct a callable even within the isolated decoder.
        encoded = base64.b64encode(zlib.compress(b"cos\nsystem\n(S'true'\ntR.")).decode()
        with self.assertRaises(RuntimeError):
            decode_private_tests(encoded)

    def test_timeout_does_not_become_wrong_answer_or_success(self):
        result = self.grade("while True:\n pass", {"fn_name": None, "inputs": ["\n"], "outputs": ["\n"]}, timeout=1)
        self.assertEqual(result["outcome"], "timeout", result)

    def test_infrastructure_failure_is_unscored_not_model_miss(self):
        from qpb.score import _review_from_prediction
        corpus = SimpleNamespace(tasks={"lcb": {"fixture": {}}})
        prediction = {"outcome": "complete", "finish_reason": "stop", "content": "```python\nprint(1)\n```"}
        with patch("qpb.score.score_lcb", return_value={"outcome": "infrastructure_failure", "correct": False}):
            review = _review_from_prediction(tool_root(), corpus, "lcb", "fixture", prediction)
        self.assertFalse(review["scored"])
        self.assertIsNone(review["correct"])


if __name__ == "__main__":
    unittest.main()
