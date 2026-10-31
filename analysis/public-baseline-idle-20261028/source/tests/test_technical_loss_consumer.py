"""Offline synthetic checks of exact technical-loss evidence consumption.

Uses only a disposable protected directory under the current user's home.
No live reconciliation producer, request, coordinator or model is invoked.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from qpb.store import RunStore, technical_loss_retry_authorized


class TechnicalLossConsumerTests(unittest.TestCase):
    def setUp(self):
        home = Path.home().resolve()
        for parent in (home, *home.parents):
            info = parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                    or info.st_mode & 0o022):
                self.skipTest("requires protected home ancestry, matching consumer contract")
        self.temp = tempfile.TemporaryDirectory(prefix="qpb-loss-fixture-", dir=home)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "evidence.json"
        self.store = RunStore(self.root, "fixture-run")

    def fixture(self, loss_state="LOST_RESPONSE_AFTER_STREAM_FAILURE"):
        evidence = dict(
            schema="frw.baseline.orphan-reconciliation.v1",
            loss_state=loss_state, original_request_state="OUTCOME_UNKNOWN",
            attempt_id="gpqa__fixture__a1", run_id="fixture-run",
            rid="fixture-request", request_hash="a" * 64,
            generation_fingerprint="b" * 64,
            original_request_sha256="c" * 64, authorized_next_attempt_n=2,
            repeat_authorized=True, result_unknown=True,
            request_no_longer_active=True, empty_backend_verified=True,
            same_serving_verified=True,
        )
        record = dict(
            outcome="technical_loss", state=loss_state, sent=True,
            attempt_id=evidence["attempt_id"], attempt_n=1,
            permit={"run_id": evidence["run_id"]},
            server_request_id=evidence["rid"], request_hash=evidence["request_hash"],
            generation_fingerprint=evidence["generation_fingerprint"],
            recovery=dict(
                evidence_ref=str(self.path), result_unknown=True,
                request_no_longer_active=True, repeat_authorized=True,
                authorized_next_attempt_n=2,
                original_request_sha256=evidence["original_request_sha256"],
            ),
        )
        return record, evidence

    def bind(self, record, evidence):
        self.path.write_bytes(json.dumps(evidence, sort_keys=True).encode())
        self.path.chmod(0o600)
        record["recovery"]["evidence_sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        return record

    def test_supported_loss_states_need_exact_bound_evidence(self):
        for state in ("LOST_RESPONSE_AFTER_CLIENT_REBOOT",
                      "LOST_RESPONSE_AFTER_CANCEL_REQUEST",
                      "LOST_RESPONSE_AFTER_STREAM_FAILURE"):
            with self.subTest(state=state):
                record, evidence = self.fixture(state)
                self.bind(record, evidence)
                self.assertTrue(technical_loss_retry_authorized(record))
                self.assertIsNone(self.store.attempt_blocks_send(record))

    def test_distinct_losses_require_matching_loss_and_original_unknown(self):
        for state in ("LOST_RESPONSE_AFTER_CANCEL_REQUEST", "LOST_RESPONSE_AFTER_STREAM_FAILURE"):
            for field, value in (("loss_state", "other-loss"),
                                 ("original_request_state", "complete"),
                                 ("original_request_state", None)):
                with self.subTest(state=state, field=field, value=value):
                    record, evidence = self.fixture(state)
                    evidence[field] = value
                    self.bind(record, evidence)
                    self.assertFalse(technical_loss_retry_authorized(record))

    def test_unknown_request_and_unbound_next_attempt_remain_blocked(self):
        self.assertEqual(self.store.attempt_blocks_send(
            {"state": "OUTCOME_UNKNOWN", "outcome": "OUTCOME_UNKNOWN", "sent": True}),
            "OUTCOME_UNKNOWN")
        record, evidence = self.fixture()
        self.bind(record, evidence)
        for field, value in (("repeat_authorized", False),
                             ("authorized_next_attempt_n", 3),
                             ("result_unknown", False),
                             ("request_no_longer_active", False)):
            with self.subTest(field=field):
                changed = deepcopy(record)
                changed["recovery"][field] = value
                self.assertEqual(self.store.attempt_blocks_send(changed), "technical_loss_not_authorized")

    def test_identity_hash_permission_and_symlink_fail_closed(self):
        record, evidence = self.fixture()
        self.bind(record, evidence)
        changed = deepcopy(record)
        changed["server_request_id"] = "other-request"
        self.assertFalse(technical_loss_retry_authorized(changed))
        changed = deepcopy(record)
        changed["recovery"]["evidence_sha256"] = "0" * 64
        self.assertFalse(technical_loss_retry_authorized(changed))
        self.path.chmod(0o644)
        self.assertFalse(technical_loss_retry_authorized(record))
        self.path.chmod(0o600)
        link = self.root / "evidence-link.json"
        link.symlink_to(self.path)
        record["recovery"]["evidence_ref"] = str(link)
        self.assertFalse(technical_loss_retry_authorized(record))


if __name__ == "__main__":
    unittest.main()
