"""Finite checker controls; all returned Python runs only inside existing bwrap."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/host-repair'
spec = importlib.util.spec_from_file_location('host_repair_portable_tests', FIXTURE / 'check.py')
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


class CheckerControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='frw013-controls-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = self.root / 'calculator.py'
        self.candidate.write_bytes(checker.CORRECTION)

    def test_cli_original_fail_and_correction_pass_exact_evidence(self):
        for candidate, accepted, code in ((checker.INPUT, False, 1), (self.candidate, True, 0)):
            with self.subTest(accepted=accepted):
                child = subprocess.run([sys.executable, '-I', '-S', '-B', str(FIXTURE / 'check.py'),
                                        str(candidate)], capture_output=True, timeout=6)
                row = json.loads(child.stdout)
                self.assertEqual(child.returncode, code)
                self.assertEqual(row['accepted'], accepted)
                self.assertEqual(row['returncode'], code)
                self.assertEqual(row['artifact_sha256'], hashlib.sha256(candidate.read_bytes()).hexdigest())
                self.assertEqual(row['owner_sha256'], checker.GOLDEN_SHA)
                self.assertTrue(row['cleanup_completed'])
                self.assertIn('Ran 1 test', row['stderr'])
                self.assertEqual(base64.b64decode(row['stderr_base64']).decode(), row['stderr'])
                self.assertEqual(child.stderr, b'')

    def test_path_type_link_and_size_negatives(self):
        linked = self.root / 'link.py'
        linked.symlink_to(self.candidate)
        parent = self.root / 'parent'
        parent.symlink_to(self.root, target_is_directory=True)
        hard = self.root / 'hard.py'
        os.link(self.candidate, hard)
        fifo = self.root / 'fifo.py'
        os.mkfifo(fifo)
        big = self.root / 'large.py'
        big.write_bytes(b'#' * (checker.MAX_BYTES + 1))
        for path in (linked, parent / 'large.py', hard, self.candidate, fifo, big, self.root):
            with self.subTest(path=path.name):
                result = checker.isolated_check(path)
                self.assertFalse(result.accepted)
                self.assertIsNone(result.child_pid)
        hard.unlink()
        self.assertTrue(checker.isolated_check(self.candidate).accepted)

    def test_same_size_mutation_during_read_refused(self):
        original_read = checker.os.read
        changed = False
        def mutate(fd, count):
            nonlocal changed
            data = original_read(fd, count)
            if not changed and data:
                changed = True
                self.candidate.write_bytes(checker.INPUT.read_bytes())
            return data
        with patch.object(checker.os, 'read', side_effect=mutate):
            result = checker.isolated_check(self.candidate)
        self.assertTrue(changed)
        self.assertFalse(result.accepted)
        self.assertIsNone(result.child_pid)

    def test_replacement_during_read_refused(self):
        original_read = checker.os.read
        changed = False
        def replace(fd, count):
            nonlocal changed
            data = original_read(fd, count)
            if not changed and data:
                changed = True
                replacement = self.root / 'replacement.py'
                replacement.write_bytes(checker.CORRECTION)
                replacement.replace(self.candidate)
            return data
        with patch.object(checker.os, 'read', side_effect=replace):
            result = checker.isolated_check(self.candidate)
        self.assertFalse(result.accepted)
        self.assertIsNone(result.child_pid)

    def test_mutation_after_ast_cannot_change_executed_snapshot(self):
        allowed = checker.source_allowed
        def mutate(source):
            outcome = allowed(source)
            self.candidate.write_bytes(checker.INPUT.read_bytes())
            return outcome
        with patch.object(checker, 'source_allowed', side_effect=mutate):
            result = checker.isolated_check(self.candidate)
        self.assertTrue(result.accepted, result)
        self.assertEqual(result.artifact_sha256, hashlib.sha256(checker.CORRECTION).hexdigest())
        self.assertEqual(self.candidate.read_bytes(), checker.INPUT.read_bytes())

    def test_module_effects_and_forged_completion_are_not_executed(self):
        marker = self.root / 'host-effect'
        for source in (b"import sys\nsys.stderr.write('Ran 1 test\\nOK\\n');sys.exit(0)\n",
                       f"open({str(marker)!r},'w').write('effect')\ndef add(a,b):return a+b\n".encode(),
                       b'def add(a,b): return 42\n',
                       b'@print\ndef add(a,b): return a+b\n'):
            self.candidate.write_bytes(source)
            result = checker.isolated_check(self.candidate)
            self.assertFalse(result.accepted)
            self.assertEqual(result.returncode, 2)
            self.assertIsNone(result.child_pid)
            self.assertEqual(result.stderr, b'fixture_source_contract_refused\n')
        self.assertFalse(marker.exists())

    def test_operand_order_and_original_subtraction_grammar_unchanged(self):
        for source, success in ((b'def add(a, b): return b+a\n', True),
                                (b'def add(a, b): return b-a\n', False)):
            self.candidate.write_bytes(source)
            result = checker.isolated_check(self.candidate)
            self.assertEqual(result.accepted, success)
            self.assertEqual(result.status, 'completed')

    def test_timeout_cleanup_actual_code_and_no_stale_pass(self):
        self.assertTrue(checker.isolated_check(self.candidate).accepted)
        self.candidate.write_bytes(
            b'import os,time\nif os.fork()==0:\n os.setsid()\n time.sleep(20)\ntime.sleep(20)\n')
        descendants = []
        real_killpg = checker.os.killpg
        def track_and_kill(pid, sig):
            pending = [pid]
            while pending:
                current = pending.pop()
                try:
                    fields = Path('/proc', str(current), 'stat').read_text().split()
                    descendants.append((current, fields[21]))
                    pending.extend(map(int, Path('/proc', str(current), 'task',
                                                str(current), 'children').read_text().split()))
                except FileNotFoundError:
                    pass
            return real_killpg(pid, sig)
        with patch.object(checker.os, 'killpg', side_effect=track_and_kill):
            result = checker._isolated_unittest(self.candidate)
        self.assertGreaterEqual(len(descendants), 3)
        for pid, identity in descendants:
            try:
                fields = Path('/proc', str(pid), 'stat').read_text().split()
            except FileNotFoundError:
                continue
            self.assertTrue(fields[21] != identity or fields[2] == 'Z',
                            f'live checker descendant remains: {pid}')
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, 'timeout')
        self.assertEqual(result.returncode, -9)
        self.assertTrue(result.cleanup_completed)
        self.assertLess(result.elapsed_seconds, 5)
        self.assertFalse(Path('/proc', str(result.child_pid)).exists())
        self.assertNotIn(b'OK', result.stderr)

    def test_resource_cpu_and_output_limits_are_honest(self):
        self.candidate.write_bytes(b'while True: pass\n')
        cpu = checker._isolated_unittest(self.candidate)
        self.assertFalse(cpu.accepted)
        self.assertNotEqual(cpu.returncode, 0)
        self.assertTrue(cpu.cleanup_completed)
        self.assertLess(cpu.elapsed_seconds, 5)
        self.candidate.write_bytes(b'import os\nos.write(1, b"x" * 100000)\ndef add(a,b):return a+b\n')
        output = checker._isolated_unittest(self.candidate)
        self.assertFalse(output.accepted)
        self.assertEqual(output.status, 'output_limit')
        self.assertEqual(len(output.stdout), checker.MAX_BYTES)
        self.assertLessEqual(len(output.stderr), checker.MAX_BYTES)

    def test_actual_child_is_reaped_after_injected_wait_error(self):
        self.candidate.write_bytes(b'import time\ntime.sleep(20)\n')
        real_popen = checker.subprocess.Popen
        children = []
        def broken_wait_once(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            real_wait = child.wait
            first = True
            def wait(*args, **kwargs):
                nonlocal first
                if first:
                    first = False
                    raise OSError('injected wait error')
                return real_wait(*args, **kwargs)
            child.wait = wait
            return child
        with patch.object(checker.subprocess, 'Popen', side_effect=broken_wait_once):
            result = checker._isolated_unittest(self.candidate)
        self.assertEqual(len(children), 1)
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, 'execution_error')
        self.assertEqual(result.returncode, -9)
        self.assertTrue(result.cleanup_completed)
        self.assertLess(result.elapsed_seconds, 5)
        self.assertFalse(Path('/proc', str(result.child_pid)).exists())

    def test_owner_drift_preserves_actual_child_code_but_refuses(self):
        owner = self.root / 'owner.py'
        owner.write_bytes(checker.GOLDEN.read_bytes())
        real_popen = checker.subprocess.Popen
        def change_owner(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            owner.unlink()
            return child
        with patch.object(checker, 'GOLDEN', owner), patch.object(
                checker.subprocess, 'Popen', side_effect=change_owner):
            result = checker.isolated_check(self.candidate)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.status, 'snapshot_changed')
        self.assertFalse(result.accepted)

    def test_observed_limits_and_memory_failure(self):
        self.candidate.write_bytes(
            b'import os,resource,json\n'
            b'print(json.dumps([len(os.sched_getaffinity(0)), '
            b'resource.getrlimit(resource.RLIMIT_AS), resource.getrlimit(resource.RLIMIT_CPU), '
            b'resource.getrlimit(resource.RLIMIT_FSIZE), resource.getrlimit(resource.RLIMIT_CORE)]))\n'
            b'def add(a,b):return a+b\n')
        result = checker._isolated_unittest(self.candidate)
        limits = json.loads(result.stdout)
        self.assertLessEqual(limits[0], 2)
        self.assertEqual(limits[1:], [[1 << 30, 1 << 30], [3, 3], [65536, 65536], [0, 0]])
        self.candidate.write_bytes(b'large = bytearray(1 << 30)\n')
        result = checker._isolated_unittest(self.candidate)
        self.assertFalse(result.accepted)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'MemoryError', result.stderr)

    def test_bypass_probe_and_launch_failure_cannot_claim_acceptance(self):
        result = checker._isolated_unittest(self.candidate)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.accepted)
        with patch.object(checker.subprocess, 'Popen', side_effect=OSError('private detail')):
            refused = checker.isolated_check(self.candidate)
        self.assertFalse(refused.accepted)
        self.assertIsNone(refused.returncode)
        self.assertEqual(refused.stdout, b'')
        self.assertNotIn(b'private detail', refused.stderr)


if __name__ == '__main__':
    unittest.main()
