"""Score saved answers only. Missing predictions stay not_run."""

from __future__ import annotations

import copy
import os
import sys
import uuid
from pathlib import Path

from qpb.corpus import get_corpus, file_sha256
from qpb.extract import extract_code, gpqa_letter, split_final
from qpb.fingerprints import scoring_fingerprint, scoring_material
from qpb.lcb_sandbox import official_grade
from qpb.pins import PER_TEST_TIMEOUT_S, SANDBOX_WALL_CAP_S
from qpb.store import FingerprintMismatch, RunStore


class OfflineScoreError(RuntimeError):
    pass


def _ifbench_api(root: Path):
    nltk_path = str(root / "data" / "nltk")
    os.environ["NLTK_DATA"] = nltk_path
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import nltk

    if nltk_path not in nltk.data.path:
        nltk.data.path.insert(0, nltk_path)

    def _refuse_download(*_args, **_kwargs):
        raise OfflineScoreError("nltk download is disabled; data/nltk is the local pin")

    nltk.download = _refuse_download
    third = str(root / "third_party" / "IFBench")
    if third not in sys.path:
        sys.path.insert(0, third)
    from evaluation_lib import (  # type: ignore
        InputExample,
        test_instruction_following_loose,
        test_instruction_following_strict,
    )

    return InputExample, test_instruction_following_strict, test_instruction_following_loose


def score_ifbench(root: Path, task: dict, final_answer: str) -> dict:
    InputExample, strict, loose = _ifbench_api(root)
    example = InputExample(
        key=task["task_id"],
        instruction_id_list=list(task["instruction_id_list"]),
        prompt=task["prompt"],
        kwargs=copy.deepcopy(task["kwargs"]),
    )
    strict_out = strict(example, {example.prompt: final_answer})
    # Official order: strict() drops None kwargs in place, then loose()
    # reads that filtered dict. Restoring the wide null-filled row makes
    # build_description() reject keys the checker does not take.
    loose_out = loose(example, {example.prompt: final_answer})
    return {
        "outcome": "scored",
        "correct": None,
        "prompt_strict": bool(strict_out.follow_all_instructions),
        "prompt_loose": bool(loose_out.follow_all_instructions),
        "inst_strict": list(strict_out.follow_instruction_list),
        "inst_loose": list(loose_out.follow_instruction_list),
        "instruction_count": len(task["instruction_id_list"]),
    }


def score_gpqa(task: dict, final_answer: str) -> dict:
    letter = gpqa_letter(final_answer)
    if letter is None:
        return {
            "outcome": "parse_error",
            "correct": False,
            "extracted": None,
            "gold": task["correct_letter"],
        }
    return {
        "outcome": "correct" if letter == task["correct_letter"] else "wrong_answer",
        "correct": letter == task["correct_letter"],
        "extracted": letter,
        "gold": task["correct_letter"],
    }


def score_lcb(corpus, task_id: str, final_answer: str) -> dict:
    code = extract_code(final_answer)
    if not code.strip():
        return {"outcome": "extraction_error", "correct": False, "extracted": ""}
    tests = corpus.lcb_tests(task_id)
    graded = official_grade(corpus.root, code, tests, per_test_timeout=PER_TEST_TIMEOUT_S, wall_cap=SANDBOX_WALL_CAP_S)
    graded["extracted"] = code
    graded["fn_name"] = tests.get("fn_name")
    graded["n_tests"] = len(tests["inputs"])
    return graded


def _review_from_prediction(root: Path, corpus, benchmark: str, task_id: str, prediction: dict) -> dict:
    if prediction.get("outcome") == "PARTIAL_RECORD" or not prediction.get("finish_reason"):
        return {
            "benchmark": benchmark,
            "task_id": task_id,
            "outcome": prediction.get("outcome") or "PARTIAL_RECORD",
            "correct": None,
            "scored": False,
        }
    final, _reasoning = split_final(prediction.get("content"), prediction.get("reasoning"))
    # Prefer the final answer frozen at generation time when it matches the
    # same extractor. Re-split from raw content so a scoring-version change
    # can reinterpret without a new generation.
    task = corpus.tasks[benchmark][task_id]
    if benchmark == "ifbench":
        detail = score_ifbench(root, task, final)
    elif benchmark == "gpqa":
        detail = score_gpqa(task, final)
    elif benchmark == "lcb":
        detail = score_lcb(corpus, task_id, final)
    else:
        raise OfflineScoreError(benchmark)
    infrastructure = detail.get("outcome") == "infrastructure_failure"
    if infrastructure:
        detail["correct"] = None
    detail.update(
        {
            "benchmark": benchmark,
            "task_id": task_id,
            "attempt_id": prediction.get("attempt_id"),
            "scored": not infrastructure,
            "truncated": bool(prediction.get("truncated")),
            "final_answer_sha_note": "scored final answer only",
        }
    )
    return detail


def score_run(root: Path, store: RunStore, *, generation_fingerprint: str) -> dict:
    """Write reviews for saved answers. Never creates a generation client."""
    store.lock()
    try:
        return _score_run_locked(root, store, generation_fingerprint=generation_fingerprint)
    finally:
        store.unlock()


def _score_run_locked(root: Path, store: RunStore, *, generation_fingerprint: str) -> dict:
    manifest = store.manifest()
    if manifest.get("generation_fingerprint") != generation_fingerprint:
        raise FingerprintMismatch(
            "generation fingerprint не совпал. Чужие или изменённые генерации не смешиваются. "
            "Недостающие ответы не генерируются."
        )
    notes = store.reconcile()
    corpus = get_corpus(root)
    corpus.verify_files()
    from qpb.atomic import atomic_write_json, load_json_result

    scoring_id = scoring_fingerprint(manifest)
    # Retain prior observations even when recovering an infrastructure failure
    # or changing only the scorer. Predictions and their identity never move.
    previous = store.dir / "scoring.json"
    prior_record = load_json_result(previous)
    prior_reviews = store.reviews
    if previous.exists():
        history = store.dir / "scoring-history" / uuid.uuid4().hex
        history.mkdir(parents=True)
        previous.replace(history / "scoring.json")
        if store.reviews.exists():
            store.reviews.replace(history / "reviews")
            prior_reviews = history / "reviews"
            store.reviews.mkdir()
    prior = prior_record.get("value", {}) if prior_record.get("ok") else {}
    reuse_allowed = (prior.get("scoring_fingerprint") == scoring_id
                     and prior.get("generation_fingerprint") == manifest["generation_fingerprint"])
    written = 0
    reused = 0
    review_hashes = {}
    for benchmark in ("ifbench", "gpqa", "lcb"):
        for task_id in manifest["datasets"][benchmark]["ids"]:
            loaded = store.read_prediction(benchmark, task_id)
            prediction_hash = file_sha256(store.prediction_path(benchmark, task_id)) if loaded["ok"] else None
            review_name = store.review_path(benchmark, task_id).name
            cached_path = prior_reviews / review_name
            cached = load_json_result(cached_path) if reuse_allowed else {"ok": False}
            cached_value = cached.get("value", {}) if cached.get("ok") else {}
            if (reuse_allowed and cached.get("ok") and cached_value.get("scored") is True
                    and prediction_hash is not None
                    and cached_value.get("benchmark") == benchmark and cached_value.get("task_id") == task_id
                    and cached_value.get("prediction_sha256") == prediction_hash
                    and cached_value.get("scoring_fingerprint") == scoring_id
                    and cached_value.get("generation_fingerprint") == manifest["generation_fingerprint"]
                    and prior.get("review_sha256", {}).get(review_name) == file_sha256(cached_path)):
                atomic_write_json(store.review_path(benchmark, task_id), cached_value)
                review_hashes[review_name] = file_sha256(store.review_path(benchmark, task_id))
                reused += 1
                written += 1
                continue
            if not loaded["ok"] and loaded["error"] == "missing":
                review = {
                    "benchmark": benchmark,
                    "task_id": task_id,
                    "outcome": "not_run",
                    "correct": None,
                    "scored": False,
                }
            elif not loaded["ok"]:
                review = {
                    "benchmark": benchmark,
                    "task_id": task_id,
                    "outcome": "PARTIAL_RECORD",
                    "correct": None,
                    "scored": False,
                    "detail": loaded.get("error"),
                }
            else:
                prediction = loaded["value"]
                if prediction.get("outcome") == "OUTCOME_UNKNOWN":
                    review = {
                        "benchmark": benchmark,
                        "task_id": task_id,
                        "outcome": "OUTCOME_UNKNOWN",
                        "correct": None,
                        "scored": False,
                    }
                elif prediction.get("outcome") != "complete":
                    review = {
                        "benchmark": benchmark,
                        "task_id": task_id,
                        "outcome": prediction.get("outcome") or "PARTIAL_RECORD",
                        "correct": None,
                        "scored": False,
                    }
                else:
                    review = _review_from_prediction(root, corpus, benchmark, task_id, prediction)
            review.update(prediction_sha256=prediction_hash, scoring_fingerprint=scoring_id,
                          generation_fingerprint=manifest["generation_fingerprint"])
            atomic_write_json(store.review_path(benchmark, task_id), review)
            review_hashes[review_name] = file_sha256(store.review_path(benchmark, task_id))
            written += 1
    record = {
        "scoring_fingerprint": scoring_id,
        "scoring_material": scoring_material(manifest),
        "generation_fingerprint": manifest["generation_fingerprint"],
        "reviews": written,
        "reused_reviews": reused,
        "review_sha256": review_hashes,
        "reconcile": notes,
    }
    atomic_write_json(store.dir / "scoring.json", record)
    return record


