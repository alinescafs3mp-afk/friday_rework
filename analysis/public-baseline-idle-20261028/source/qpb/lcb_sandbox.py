"""Run one untrusted program per test inside bwrap.

Expected outputs stay in the parent. There is no host-execution fallback.
The stock LiveCodeBench runner is not invoked: it can reload a dataset
script and is the path that loads a model.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import tempfile
import textwrap
import time
import math
import resource
import hashlib
from decimal import Decimal
from pathlib import Path

from qpb.pins import PER_TEST_TIMEOUT_S, SANDBOX_WALL_CAP_S

IMPORT_STRING = (
    "from string import *\nfrom re import *\nfrom datetime import *\n"
    "from collections import *\nfrom heapq import *\nfrom bisect import *\n"
    "from copy import *\nfrom math import *\nfrom random import *\n"
    "from statistics import *\nfrom itertools import *\nfrom functools import *\n"
    "from operator import *\nfrom io import *\nfrom sys import *\nfrom json import *\n"
    "from builtins import *\nfrom typing import *\n"
    "import string\nimport re\nimport datetime\nimport collections\nimport heapq\n"
    "import bisect\nimport copy\nimport math\nimport random\nimport statistics\n"
    "import itertools\nimport functools\nimport operator\nimport io\nimport sys\n"
    "import json\nsys.setrecursionlimit(50000)\n"
)

_STDIO_DRIVER = textwrap.dedent(
    """
    import ast
    import sys
    from io import BytesIO, TextIOWrapper
    from unittest.mock import mock_open, patch

    IMPORTS = open("/work/imports.txt", encoding="utf-8").read()
    code = open("/work/program.py", encoding="utf-8").read()
    raw = open("/work/input.txt", encoding="utf-8").read()

    def clean_if_name(source):
        try:
            tree = ast.parse(source)
            last = tree.body[-1]
            if isinstance(last, ast.If) and ast.unparse(last.test).strip() == "__name__ == '__main__'":
                source = ast.unparse(tree.body[:-1]) + "\\n" + ast.unparse(last.body)
        except Exception:
            pass
        return source

    def make_function(source):
        try:
            tree = ast.parse(source)
            imports, other = [], []
            for stmt in tree.body:
                if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                    imports.append(stmt)
                else:
                    other.append(stmt)
            if not other:
                other = [ast.Pass()]
            function = ast.FunctionDef(
                name="wrapped_function",
                args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                body=other,
                decorator_list=[],
                lineno=-1,
            )
            return IMPORTS + "\\n" + ast.unparse(imports) + "\\n" + ast.unparse(function)
        except Exception:
            return source

    source = make_function(clean_if_name(code))
    namespace = {}
    try:
        exec(compile(source, "<candidate>", "exec"), namespace)
    except Exception as exc:
        sys.stderr.write("compile/exec: " + repr(exc))
        sys.exit(2)
    method = namespace.get("wrapped_function")
    if method is None:
        sys.stderr.write("no wrapped_function")
        sys.exit(2)
    iterator = iter(raw.split("\\n"))

    @patch("builtins.open", mock_open(read_data=raw))
    @patch("sys.stdin", TextIOWrapper(BytesIO(raw.encode("utf-8")), encoding="utf-8"))
    @patch("sys.stdin.readline", lambda *args, **kwargs: next(iterator))
    @patch("sys.stdin.readlines", lambda *args, **kwargs: raw.split("\\n"))
    @patch("sys.stdin.read", lambda *args, **kwargs: raw)
    def _call(function):
        try:
            return function()
        except SystemExit:
            return None

    try:
        _call(method)
    except Exception as exc:
        sys.stderr.write(repr(exc))
        sys.exit(3)
    """
).lstrip()

_CALL_DRIVER = textwrap.dedent(
    """
    import contextlib
    import io
    import json
    import sys
    import types

    imports = open("/work/imports.txt", encoding="utf-8").read()
    code = open("/work/program.py", encoding="utf-8").read()
    fn_name = open("/work/fn_name.txt", encoding="utf-8").read().strip()
    raw = open("/work/input.txt", encoding="utf-8").read()
    try:
        args = [json.loads(line) for line in raw.split("\\n")]
    except Exception as exc:
        sys.stderr.write("bad input json: " + repr(exc))
        sys.exit(2)
    module = types.ModuleType("candidate")
    try:
        exec(compile(imports + "\\n\\n" + code, "<candidate>", "exec"), module.__dict__)
        if "class Solution" in code:
            target = module.Solution()
        else:
            target = module
        function = getattr(target, fn_name)
    except Exception as exc:
        sys.stderr.write("compile/exec: " + repr(exc))
        sys.exit(2)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            result = function(*args)
    except Exception as exc:
        sys.stderr.write(repr(exc))
        sys.exit(3)
    if isinstance(result, tuple):
        result = list(result)
    sys.stdout.write(repr(result))
    """
).lstrip()


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def _python_mount() -> tuple[str, str]:
    import sys

    real = Path(sys.executable).resolve()
    return str(real.parent.parent), real.name


def _run_bwrap(job: Path, timeout_s: float, *, site_packages: Path | None = None) -> subprocess.CompletedProcess:
    if not bwrap_available():
        raise FileNotFoundError("bwrap is not installed; host execution is not a fallback")
    pyroot, pyname = _python_mount()
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--ro-bind",
        pyroot,
        "/opt/python",
        "--ro-bind",
        str(job),
        "/work",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--clearenv",
        "--setenv",
        "PATH",
        "/opt/python/bin:/usr/bin",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--chdir",
        "/work",
        f"/opt/python/bin/{pyname}",
        "-s",
        "-B",
        "/work/driver.py",
    ]
    if site_packages is not None:
        at = command.index("--chdir")
        command[at:at] = ["--ro-bind", str(site_packages), "/opt/site",
                          "--setenv", "PYTHONPATH", "/opt/site",
                          "--setenv", "OPENBLAS_NUM_THREADS", "1",
                          "--setenv", "OMP_NUM_THREADS", "1"]
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(timeout_s)), max(1, math.ceil(timeout_s))))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 ** 2, 16 * 1024 ** 2))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # Apply process-count limit after entering bwrap's user namespace. Setting
    # it in the host preexec sees all unrelated owner processes and can prevent
    # bwrap from creating its own namespace.
    driver_path = job / "driver.py"
    driver_path.write_text("import resource\nresource.setrlimit(resource.RLIMIT_NPROC, (32, 32))\n" + driver_path.read_text())
    return subprocess.run(
        command,
        capture_output=True,
        timeout=timeout_s,
        check=False,
        preexec_fn=limits,
    )


def decode_private_tests(encoded: str) -> list:
    """Dataset pickle never executes in the parent or with access to /home."""
    driver = '''import base64, io, json, pickle, zlib
class Restricted(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError("pickle globals forbidden")
    def persistent_load(self, pid):
        raise ValueError("pickle persistent IDs forbidden")
encoded = open("/work/encoded.txt").read()
raw = zlib.decompress(base64.b64decode(encoded))
if len(raw) > 64 * 1024 * 1024:
    raise ValueError("decoded tests too large")
text = Restricted(io.BytesIO(raw)).load()
if not isinstance(text, str):
    raise ValueError("expected pickled JSON string")
cases = json.loads(text)
if not isinstance(cases, list):
    raise ValueError("expected case list")
print(json.dumps(cases))
'''
    with tempfile.TemporaryDirectory(prefix="qpb-lcb-decode-") as tmp:
        job = Path(tmp)
        (job / "driver.py").write_text(driver)
        (job / "encoded.txt").write_text(encoded)
        completed = _run_bwrap(job, 10)
    if completed.returncode:
        raise RuntimeError("isolated private-test decoding failed")
    result = json.loads(completed.stdout)
    if not isinstance(result, list):
        raise RuntimeError("isolated decoder returned invalid cases")
    return result


OFFICIAL_TESTING_SHA256 = "b7cb6a8a69807bb868150a61742e25d7bb5328bbe01d514471b6ec43c9fa9ed2"


def official_grade(root: Path, code: str, tests: dict, *, per_test_timeout=PER_TEST_TIMEOUT_S, wall_cap=SANDBOX_WALL_CAP_S):
    """Pinned upstream run_test, within the existing CPU sandbox, no runner/model.

    Copy only the pinned evaluator into the ephemeral job. The read-only
    dependency directory contains this tool's installed numpy, never /home.
    """
    import sysconfig
    source = root / "third_party/LiveCodeBench/lcb_runner/evaluation/testing_util.py"
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != OFFICIAL_TESTING_SHA256:
        raise RuntimeError("official LCB testing_util pin mismatch")
    count = len(tests["inputs"])
    if not count or count != len(tests["outputs"]):
        raise RuntimeError("LCB requires nonempty matched input/output tests")
    cap = min((per_test_timeout + 1) * count + 15, wall_cap)
    driver = '''import contextlib, io, json, sys
sys.path.insert(0, "/work")
from official_testing import run_test
code = open("/work/program.py").read()
sample = {"input_output": open("/work/tests.json").read()}
with contextlib.redirect_stdout(io.StringIO()):
    results, metadata = run_test(sample, test=code, debug=False, timeout=TIMEOUT)
print(json.dumps({"results": [bool(x) if isinstance(x, bool) else x for x in results], "metadata": metadata}))
'''.replace("TIMEOUT", str(int(per_test_timeout)))
    try:
        with tempfile.TemporaryDirectory(prefix="qpb-lcb-official-") as tmp:
            job = Path(tmp)
            (job / "official_testing.py").write_bytes(raw)
            (job / "program.py").write_text(code)
            (job / "tests.json").write_text(json.dumps(tests))
            (job / "driver.py").write_text(driver)
            completed = _run_bwrap(job, cap, site_packages=Path(sysconfig.get_paths()["purelib"]))
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout", "correct": False, "n_tests": count, "tests_run": None,
                "reason": "parent_wall_cap", "scorer": "official_testing_util"}
    if completed.returncode:
        return {"outcome": "infrastructure_failure", "correct": False, "n_tests": count,
                "tests_run": None, "scorer": "official_testing_util", "returncode": completed.returncode}
    try:
        result = json.loads(completed.stdout)
    except (ValueError, UnicodeError):
        return {"outcome": "infrastructure_failure", "correct": False, "n_tests": count, "tests_run": None,
                "scorer": "official_testing_util", "reason": "evaluator_output_invalid"}
    values = result["results"]
    correct = len(values) == count and all(value is True for value in values)
    error_code = result.get("metadata", {}).get("error_code")
    outcome = "correct" if correct else ("timeout" if error_code == -3 else ("runtime_error" if error_code == -4 else "wrong_answer"))
    return dict(result, outcome=outcome, correct=correct, n_tests=count, tests_run=len(values),
                scorer="official_testing_util", scorer_sha256=OFFICIAL_TESTING_SHA256)


def _write_job(job: Path, code: str, stdin_text: str, fn_name: str | None) -> None:
    (job / "program.py").write_text(code, encoding="utf-8")
    (job / "input.txt").write_text(stdin_text, encoding="utf-8")
    (job / "imports.txt").write_text(IMPORT_STRING, encoding="utf-8")
    if fn_name:
        (job / "fn_name.txt").write_text(fn_name, encoding="utf-8")
        (job / "driver.py").write_text(_CALL_DRIVER, encoding="utf-8")
    else:
        (job / "driver.py").write_text(_STDIO_DRIVER, encoding="utf-8")


def _one(code: str, stdin_text: str, fn_name: str | None, timeout_s: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="qpb-lcb-") as tmp:
        job = Path(tmp)
        _write_job(job, code, stdin_text, fn_name)
        try:
            completed = _run_bwrap(job, timeout_s)
        except subprocess.TimeoutExpired:
            return {"status": "timeout"}
        except FileNotFoundError as exc:
            return {"status": "infrastructure_failure", "detail": str(exc)}
    if completed.returncode != 0:
        err = completed.stderr.decode("utf-8", "replace")[:500]
        return {"status": "runtime_error", "detail": err, "returncode": completed.returncode}
    payload = completed.stdout.decode("utf-8", "replace")
    return {"status": "ok", "payload": payload}


def _stripped_lines(value: str) -> list[str]:
    value = value.strip()
    return [line.strip() for line in value.split("\n")]


def _decimals(line: str):
    try:
        return [Decimal(part) for part in line.split()]
    except Exception:
        return None


def stdio_equal(prediction: str, expected: str) -> bool:
    pred_lines = _stripped_lines(prediction)
    exp_lines = _stripped_lines(expected)
    if len(pred_lines) != len(exp_lines):
        return False
    for pred, exp in zip(pred_lines, exp_lines):
        if pred == exp:
            continue
        left, right = _decimals(pred), _decimals(exp)
        if left is None or right is None or left != right:
            return False
    return True


def call_equal(payload: str, expected: str) -> bool:
    try:
        got = ast.literal_eval(payload.strip())
        gold = json.loads(expected)
    except (SyntaxError, ValueError, json.JSONDecodeError):
        return False
    return got == gold


def grade(
    code: str,
    tests: dict,
    *,
    per_test_timeout: float = PER_TEST_TIMEOUT_S,
    wall_cap: float = SANDBOX_WALL_CAP_S,
) -> dict:
    if code is None or not str(code).strip():
        return {"outcome": "extraction_error", "correct": False, "tests_run": 0}
    fn_name = tests.get("fn_name")
    inputs = tests["inputs"]
    outputs = tests["outputs"]
    n_tests = len(inputs)
    cap = min((per_test_timeout + 1) * n_tests + 15, wall_cap)
    started = time.monotonic()
    for index, (stdin_text, expected) in enumerate(zip(inputs, outputs)):
        if time.monotonic() - started > cap:
            return {
                "outcome": "timeout",
                "reason": "parent_wall_cap",
                "correct": False,
                "tests_run": index,
                "n_tests": n_tests,
            }
        result = _one(code, stdin_text, fn_name, per_test_timeout)
        if result["status"] != "ok":
            return {
                "outcome": result["status"],
                "correct": False,
                "tests_run": index + 1,
                "index": index,
                "n_tests": n_tests,
                "detail": result.get("detail"),
            }
        if fn_name:
            ok = call_equal(result["payload"], expected)
        else:
            ok = stdio_equal(result["payload"], expected)
        if not ok:
            return {
                "outcome": "wrong_answer",
                "correct": False,
                "tests_run": index + 1,
                "index": index,
                "n_tests": n_tests,
            }
    return {"outcome": "correct", "correct": True, "tests_run": n_tests, "n_tests": n_tests}
