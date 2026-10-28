"""Local corpora, frozen order, pilot ids, and GPQA choice order."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from qpb.pins import DATASETS, EXPECTED
from qpb.prompts import SYSTEM_LCB, gpqa_user, lcb_user

_CACHE: dict[str, "Corpus"] = {}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preprocess(text) -> str:
    if text is None:
        return " "
    return str(text).strip()


def gpqa_choice_order(row: dict) -> dict:
    """Same pure shuffle EvalScope 1.14.1 uses for GPQA Diamond."""
    choices = [
        _preprocess(row["Incorrect Answer 1"]),
        _preprocess(row["Incorrect Answer 2"]),
        _preprocess(row["Incorrect Answer 3"]),
        _preprocess(row["Correct Answer"]),
    ]
    seed = int.from_bytes(
        hashlib.sha256(_preprocess(row["Question"]).encode("utf-8")).digest()[:8],
        "big",
    )
    random.Random(seed).shuffle(choices)
    correct = _preprocess(row["Correct Answer"])
    index = choices.index(correct)
    return {
        "choices": choices,
        "correct_letter": chr(65 + index),
        "shuffle_seed": seed,
    }


def ordered_ids(ids: list[str]) -> list[str]:
    order = sorted(ids)
    random.Random(42).shuffle(order)
    return order


def pilot_ids(order: list[str], k: int = 5) -> list[str]:
    indexes = sorted(random.Random(42).sample(range(len(order)), k))
    return [order[i] for i in indexes]


def decode_lcb_tests(row: dict) -> dict:
    public = row["public_test_cases"]
    if isinstance(public, str):
        public = json.loads(public)
    private_raw = row["private_test_cases"]
    if isinstance(private_raw, str):
        try:
            private = json.loads(private_raw)
        except json.JSONDecodeError:
            from qpb.lcb_sandbox import decode_private_tests
            private = decode_private_tests(private_raw)
    else:
        private = private_raw
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata) if metadata else {}
    cases = list(public) + list(private)
    return {
        "fn_name": (metadata or {}).get("func_name"),
        "inputs": [case["input"] for case in cases],
        "outputs": [case["output"] for case in cases],
        "n_public": len(public),
        "n_private": len(private),
    }


class Corpus:
    def __init__(self, root: Path):
        self.root = root
        self.tasks: dict[str, dict[str, dict]] = {name: {} for name in EXPECTED}
        self.order: dict[str, list[str]] = {}
        self.pilot: dict[str, list[str]] = {}
        self.lcb_offsets: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        self._load_ifbench()
        self._load_gpqa()
        self._load_lcb_prompts()
        for name, rows in self.tasks.items():
            if len(rows) != EXPECTED[name]:
                raise RuntimeError(f"{name} count {len(rows)} != {EXPECTED[name]}")
            if len(set(rows)) != EXPECTED[name]:
                raise RuntimeError(f"{name} ids are not unique")
            self.order[name] = ordered_ids(list(rows))
            self.pilot[name] = pilot_ids(self.order[name], 5)

    def _load_ifbench(self) -> None:
        path = self.root / DATASETS["ifbench"]["path"]
        with path.open("rb") as handle:
            for line in handle:
                row = json.loads(line)
                task_id = str(row["key"])
                self.tasks["ifbench"][task_id] = {
                    "task_id": task_id,
                    "prompt": row["prompt"],
                    "instruction_id_list": row["instruction_id_list"],
                    "kwargs": row["kwargs"],
                    "messages": [{"role": "user", "content": row["prompt"]}],
                }

    def _load_gpqa(self) -> None:
        path = self.root / DATASETS["gpqa"]["path"]
        with path.open("rb") as handle:
            for line in handle:
                row = json.loads(line)
                task_id = str(row["Record ID"])
                choice = gpqa_choice_order(row)
                prompt = gpqa_user(row["Question"], choice["choices"])
                self.tasks["gpqa"][task_id] = {
                    "task_id": task_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "correct_letter": choice["correct_letter"],
                    "choices": choice["choices"],
                    "shuffle_seed": choice["shuffle_seed"],
                }

    def _load_lcb_prompts(self) -> None:
        path = self.root / DATASETS["lcb"]["path"]
        dates = []
        difficulty = {"easy": 0, "medium": 0, "hard": 0}
        with path.open("rb") as handle:
            while True:
                start = handle.tell()
                line = handle.readline()
                if not line:
                    break
                row = json.loads(line)
                task_id = str(row["question_id"])
                starter = row.get("starter_code") or ""
                user = lcb_user(row["question_content"], starter)
                self.lcb_offsets[task_id] = start
                dates.append(row.get("contest_date"))
                diff = row.get("difficulty")
                if diff in difficulty:
                    difficulty[diff] += 1
                self.tasks["lcb"][task_id] = {
                    "task_id": task_id,
                    "messages": [
                        {"role": "system", "content": SYSTEM_LCB},
                        {"role": "user", "content": user},
                    ],
                    "contest_date": row.get("contest_date"),
                    "difficulty": diff,
                    "platform": row.get("platform"),
                }
        self.lcb_dates = dates
        self.lcb_difficulty = difficulty

    def lcb_tests(self, task_id: str) -> dict:
        path = self.root / DATASETS["lcb"]["path"]
        with path.open("rb") as handle:
            handle.seek(self.lcb_offsets[task_id])
            row = json.loads(handle.readline())
        if str(row["question_id"]) != task_id:
            raise RuntimeError("LCB offset did not land on the requested id")
        return decode_lcb_tests(row)

    def verify_files(self) -> dict:
        report = {}
        for name, pin in DATASETS.items():
            path = self.root / pin["path"]
            digest = file_sha256(path)
            size = path.stat().st_size
            ids = list(self.tasks[name])
            ok = digest == pin["sha256"] and size == pin["bytes"] and len(ids) == pin["rows"]
            report[name] = {
                "ok": ok,
                "sha256": digest,
                "bytes": size,
                "rows": len(ids),
                "unique": len(set(ids)),
            }
            if not ok:
                raise RuntimeError(f"{name} pin mismatch: {report[name]}")
        return report


def get_corpus(root: Path) -> Corpus:
    key = str(root.resolve())
    cached = _CACHE.get(key)
    if cached is None:
        cached = Corpus(root)
        _CACHE[key] = cached
    return cached
