"""Build baseline.json and baseline.md from saved rows. Null is not zero."""

from __future__ import annotations

from qpb.atomic import atomic_write_json, load_json_result
from qpb.pins import EXPECTED, REFERENCE_CLAIMS
from qpb.store import RunStore

_NAMES = {
    "ifbench": "IFBench",
    "gpqa": "GPQA Diamond",
    "lcb": "LiveCodeBench v6 (config v6, 175)",
}
_CLAIM_NAME = {
    "ifbench": "IFBench",
    "gpqa": "GPQA Diamond",
    "lcb": "LiveCodeBench v6",
}


def is_full_model_baseline(document: dict) -> bool:
    if document.get("kind") != "model":
        return False
    if document.get("partial"):
        return False
    return all(item.get("protocol_complete") for item in document["benchmarks"].values())


def _reviews(store: RunStore, benchmark: str, ids: list[str]) -> list[dict]:
    rows = []
    for task_id in ids:
        loaded = load_json_result(store.review_path(benchmark, task_id))
        if loaded["ok"]:
            rows.append(loaded["value"])
        else:
            rows.append({"task_id": task_id, "outcome": "not_scored", "scored": False})
    return rows


def _count(rows: list[dict], outcome: str) -> int:
    return sum(1 for row in rows if row.get("outcome") == outcome)


def _benchmark_block(store: RunStore, manifest: dict, benchmark: str) -> dict:
    meta = manifest["datasets"][benchmark]
    ids = meta["ids"]
    expected = EXPECTED[benchmark]
    predictions_complete = 0
    attempts = 0
    truncated = 0
    transport = 0
    unknown = 0
    technical_losses = 0
    technical_retries = 0
    unmeasured_sent_attempts = 0
    for task_id in ids:
        loaded = store.read_prediction(benchmark, task_id)
        if not loaded["ok"]:
            continue
        if loaded["value"].get("outcome") == "complete" and loaded["value"].get("finish_reason"):
            predictions_complete += 1
            if loaded["value"].get("truncated"):
                truncated += 1
    for path in store.iter_request_files():
        loaded = load_json_result(path)
        if not loaded["ok"] or loaded["value"].get("benchmark") != benchmark:
            continue
        record = loaded["value"]
        attempts += 1
        if record.get("outcome") == "technical_loss":
            technical_losses += 1
        if record.get("recovery_retry_of") and record.get("sent") is True:
            technical_retries += 1
        if record.get("sent") is True and not isinstance(record.get("wall_s"), (int, float)):
            unmeasured_sent_attempts += 1
        if record.get("outcome") == "transport_error":
            transport += 1
        if record.get("outcome") == "OUTCOME_UNKNOWN":
            unknown += 1
    scored_rows = _reviews(store, benchmark, ids) if (store.dir / "scoring.json").exists() else []
    metrics = None
    scored_tasks = 0
    if scored_rows:
        scored_tasks = sum(1 for row in scored_rows if row.get("scored"))
        metrics = _metrics(benchmark, scored_rows, expected)
    not_run = expected - predictions_complete if not scored_rows else _count(scored_rows, "not_run")
    protocol = (
        predictions_complete == expected
        and scored_tasks == expected
        and unknown == 0
        and transport == 0
        and not_run == 0
    )
    claim = next(item for item in REFERENCE_CLAIMS["claims"] if item["benchmark"] == _CLAIM_NAME[benchmark])
    return {
        "benchmark": _NAMES[benchmark],
        "dataset_revision": meta.get("revision"),
        "subset": meta.get("split"),
        "expected_tasks": expected,
        "generated_tasks": predictions_complete,
        "scored_tasks": scored_tasks if scored_rows else None,
        "generation_attempts": attempts,
        "protocol_complete": protocol,
        "truncated_responses": truncated,
        "transport_errors": transport,
        "outcome_unknown": unknown,
        "technical_losses": technical_losses,
        "technical_retries": technical_retries,
        "unmeasured_sent_attempts": unmeasured_sent_attempts,
        "not_run": None if not scored_rows else not_run,
        "parse_errors": None if not scored_rows else _count(scored_rows, "parse_error"),
        "extraction_errors": None if not scored_rows else _count(scored_rows, "extraction_error"),
        "wrong_answers": None if not scored_rows else _count(scored_rows, "wrong_answer"),
        "infrastructure_failures": None if not scored_rows else _count(scored_rows, "infrastructure_failure"),
        "timeouts": None if not scored_rows else _count(scored_rows, "timeout"),
        "runtime_errors": None if not scored_rows else _count(scored_rows, "runtime_error"),
        "metrics": metrics,
        "generation_fingerprint": manifest.get("generation_fingerprint"),
        "scoring_fingerprint": _scoring_id(store),
        "scorer_version": _scoring_id(store),
        "comparability_to_reference": claim["comparability"],
        "reference_claim": {
            "score": claim["score"],
            "metric_confirmed": False,
            "source_url": REFERENCE_CLAIMS["source_url"],
            "reason": claim["reason"],
        },
    }


def _scoring_id(store: RunStore):
    loaded = load_json_result(store.dir / "scoring.json")
    if not loaded["ok"]:
        return None
    return loaded["value"].get("scoring_fingerprint")


def _metrics(benchmark: str, rows: list[dict], expected: int):
    scored = [row for row in rows if row.get("scored")]
    if not scored:
        return None
    if benchmark == "ifbench":
        n = len(scored)
        inst_n = sum(row.get("instruction_count") or len(row.get("inst_strict") or []) for row in scored)
        inst_strict = sum(sum(row.get("inst_strict") or []) for row in scored)
        inst_loose = sum(sum(row.get("inst_loose") or []) for row in scored)
        return {
            "prompt_level_strict": _rate(sum(1 for row in scored if row.get("prompt_strict")), n, expected),
            "prompt_level_loose": _rate(sum(1 for row in scored if row.get("prompt_loose")), n, expected),
            "inst_level_strict": _rate(inst_strict, inst_n, None),
            "inst_level_loose": _rate(inst_loose, inst_n, None),
        }
    if benchmark == "gpqa":
        correct = sum(1 for row in scored if row.get("correct") is True)
        return {"accuracy": _rate(correct, len(scored), expected)}
    correct = sum(1 for row in scored if row.get("outcome") == "correct")
    return {"all_tests_pass": _rate(correct, len(scored), expected)}


def _rate(numerator: int, denominator: int, expected):
    if denominator == 0:
        return None
    return {
        "value": numerator / denominator,
        "numerator": numerator,
        "denominator_scored": denominator,
        "denominator_expected": expected,
    }


def build_report(store: RunStore) -> dict:
    manifest = store.manifest()
    benchmarks = {}
    for name in ("ifbench", "gpqa", "lcb"):
        benchmarks[name] = _benchmark_block(store, manifest, name)
    protocol = all(item["protocol_complete"] for item in benchmarks.values())
    kind = manifest.get("kind") or "model"
    partial = not protocol or kind == "fixture"
    active = _active_seconds(store)
    document = {
        "kind": kind,
        "fixture": kind == "fixture",
        "partial": partial,
        "state": "PARTIAL" if partial else "COMPLETE",
        "run_state": manifest.get("state"),
        "run_id": manifest.get("run_id"),
        "profile": manifest.get("profile"),
        "protocol_complete": protocol and kind == "model",
        "full_model_baseline": False,
        "live_checked": manifest.get("live_checked", False),
        "endpoint_alias": manifest.get("endpoint_alias"),
        "model": manifest.get("model"),
        "generation_fingerprint": manifest.get("generation_fingerprint"),
        "benchmarks": benchmarks,
        "active_model_seconds": active if not any(b["unmeasured_sent_attempts"] for b in benchmarks.values()) else None,
        "known_active_model_seconds": active,
        "attempt_cost_complete": not any(b["unmeasured_sent_attempts"] for b in benchmarks.values()),
        "cpu_scoring_seconds": None,
        "calendar_seconds_including_pauses": None,
        "note": _note(kind, partial),
    }
    document["full_model_baseline"] = is_full_model_baseline(document)
    if manifest.get("mode") == "idle":
        from qpb.runner import _attempt_budget, unfinished_attempt_cap
        _, budget = _attempt_budget(store)
        cap = unfinished_attempt_cap(manifest["idle_policy"])
        document["unfinished_attempt_budget"] = dict(
            budget, max_interrupted_attempt_wall_seconds=cap,
            unfinished_attempt_cap_enabled=cap is not None)
    return document


def _active_seconds(store: RunStore) -> float:
    total = 0.0
    for path in store.iter_request_files():
        loaded = load_json_result(path)
        if loaded["ok"] and isinstance(loaded["value"].get("wall_s"), (int, float)):
            total += float(loaded["value"]["wall_s"])
    return total


def _note(kind: str, partial: bool) -> str:
    if kind == "fixture":
        return (
            "FIXTURE. Это не результат Qwen и не полный baseline. "
            "Ответы записаны локальным mock. Знаменатель ожидаемых задач не сжимался."
        )
    if partial:
        return "PARTIAL. Прогон не покрывает все 673 задачи. Неполный знаменатель не выдаётся за полный baseline."
    return "Полный model baseline public-core-v1."


def write_report(store: RunStore) -> dict:
    document = build_report(store)
    atomic_write_json(store.dir / "baseline.json", document)
    (store.dir / "baseline.md").write_text(render_markdown(document), encoding="utf-8")
    return document


def render_markdown(document: dict) -> str:
    lines = []
    if document["kind"] == "fixture":
        lines.append("# FIXTURE — не результат Qwen")
    elif document["partial"]:
        lines.append("# PARTIAL — не полный baseline")
    else:
        lines.append("# public-core-v1")
    lines.append("")
    lines.append(document["note"])
    lines.append("")
    lines.append(f"- run: `{document['run_id']}`")
    lines.append(f"- kind: `{document['kind']}`")
    lines.append(f"- state: `{document['state']}` / run `{document['run_state']}`")
    lines.append(f"- model field: `{document.get('model')}`")
    lines.append(f"- endpoint alias: `{document.get('endpoint_alias')}`")
    lines.append(f"- live_checked: `{document['live_checked']}`")
    lines.append(f"- full_model_baseline: `{document['full_model_baseline']}`")
    lines.append(f"- generation fingerprint: `{document.get('generation_fingerprint')}`")
    lines.append(f"- активное время модели, с: `{document['active_model_seconds']}`; известная сумма: `{document['known_active_model_seconds']}`; полнота стоимости: `{document['attempt_cost_complete']}`")
    if "unfinished_attempt_budget" in document:
        budget = document["unfinished_attempt_budget"]
        cap_text = "отключён (null)" if budget["max_interrupted_attempt_wall_seconds"] is None else budget["max_interrupted_attempt_wall_seconds"]
        lines.append(f"- незавершённые попытки, известное время, с: `{budget['unfinished_attempt_wall_s']}`; "
                     f"без измерения: `{budget['unmeasured_unfinished_attempts']}`; "
                     f"лимит: `{cap_text}`; "
                     f"историческое foreground/stop время: `{budget['interrupted_wall_s']}`")
    lines.append("- CPU scoring и календарное время с паузами в этом отчёте не смешиваются с активным временем. CPU здесь null, пока отдельный таймер скоринга не записан.")
    lines.append("")
    lines.append("Сырые ответы: `requests/`, `predictions/`. Оценки: `reviews/`.")
    lines.append("")
    for key, block in document["benchmarks"].items():
        lines.append(f"## {block['benchmark']}")
        lines.append("")
        lines.append(f"- revision: `{block['dataset_revision']}` split `{block['subset']}`")
        lines.append(
            f"- expected {block['expected_tasks']}, generated {block['generated_tasks']}, "
            f"scored {block['scored_tasks']}"
        )
        lines.append(
            f"- attempts {block['generation_attempts']}, truncated {block['truncated_responses']}, "
            f"transport_errors {block['transport_errors']}, outcome_unknown {block['outcome_unknown']}, "
            f"technical_losses {block['technical_losses']}, technical_retries {block['technical_retries']}, "
            f"unmeasured_sent_attempts {block['unmeasured_sent_attempts']}"
        )
        lines.append(
            f"- not_run {block['not_run']}, parse_errors {block['parse_errors']}, "
            f"extraction_errors {block['extraction_errors']}, wrong_answers {block['wrong_answers']}, "
            f"timeouts {block['timeouts']}, runtime_errors {block['runtime_errors']}, "
            f"infrastructure_failures {block['infrastructure_failures']}"
        )
        lines.append(f"- protocol_complete: `{block['protocol_complete']}`")
        lines.append(f"- comparability: `{block['comparability_to_reference']}`")
        claim = block["reference_claim"]
        lines.append(
            f"- reference claim {claim['score']} ({claim['source_url']}), metric_confirmed={claim['metric_confirmed']}. {claim['reason']}"
        )
        lines.append(f"- metrics: `{block['metrics']}`")
        lines.append("")
    lines.append("Null значит «не измерялось», не ноль.")
    lines.append("Неверный ответ, ошибка извлечения, инфраструктурный сбой и не запущенная задача — разные поля.")
    lines.append("")
    return "\n".join(lines) + "\n"
