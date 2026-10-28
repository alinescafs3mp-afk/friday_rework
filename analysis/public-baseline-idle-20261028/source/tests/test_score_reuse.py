from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qpb.atomic import read_json, atomic_write_json
from qpb.corpus import file_sha256
from qpb.paths import tool_root
from qpb.score import score_run, _review_from_prediction
from qpb.store import RunStore, RunBusy


class ScoreReuseTests(unittest.TestCase):
    def test_saved_scores_reused_only_with_exact_prediction_review_and_fingerprints(self):
        root = tool_root()
        datasets = read_json(root / "manifests/datasets.json")
        first, second = datasets["gpqa"]["ids"][:2]
        with tempfile.TemporaryDirectory(prefix="qpb-score-reuse-") as tmp:
            store = RunStore(Path(tmp), "fixture"); store.ensure_dirs()
            store.write_manifest({"datasets": datasets, "generation_fingerprint": "fixture-fp", "kind": "fixture"})
            def save(task):
                store.save_prediction({"attempt_id": "fixture-" + task, "benchmark": "gpqa", "task_id": task,
                    "outcome": "complete", "finish_reason": "stop", "content": "ANSWER: A"})
            save(first)
            before = file_sha256(store.prediction_path("gpqa", first))
            with patch("qpb.score._review_from_prediction", wraps=_review_from_prediction) as evaluate:
                initial = score_run(root, store, generation_fingerprint="fixture-fp")
                self.assertEqual(initial["reused_reviews"], 0)
                self.assertEqual(evaluate.call_count, 1)
                save(second)
                final = score_run(root, store, generation_fingerprint="fixture-fp")
                self.assertEqual(final["reused_reviews"], 1)
                self.assertEqual(evaluate.call_count, 2)
                row = read_json(store.review_path("gpqa", first)); row["correct"] = not row["correct"]
                atomic_write_json(store.review_path("gpqa", first), row)
                repaired = score_run(root, store, generation_fingerprint="fixture-fp")
                self.assertEqual(repaired["reused_reviews"], 1)
                self.assertEqual(evaluate.call_count, 3, "tampered review must be recomputed, saved generation reused")
            self.assertEqual(file_sha256(store.prediction_path("gpqa", first)), before)
            self.assertEqual(len(list((store.dir / "scoring-history").glob("*/scoring.json"))), 2)

    def test_scorer_does_not_reconcile_a_live_locked_runner(self):
        with tempfile.TemporaryDirectory(prefix="qpb-score-busy-") as tmp:
            owner = RunStore(Path(tmp), "fixture"); owner.lock()
            try:
                with self.assertRaises(RunBusy):
                    score_run(tool_root(), RunStore(Path(tmp), "fixture"), generation_fingerprint="fixture-fp")
            finally:
                owner.unlock()


if __name__ == "__main__":
    unittest.main()
