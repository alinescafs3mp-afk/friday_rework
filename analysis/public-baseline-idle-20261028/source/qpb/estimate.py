"""Arithmetic scenarios only. Not a measured speed and not an SLA."""

from __future__ import annotations

from qpb.pins import CORE_TOTAL, ESTIMATE_PRIOR_S


def scenario_rows() -> list[dict]:
    rows = []
    for mean_tokens in (2000, 4000, 8000):
        tokens = CORE_TOTAL * mean_tokens
        for rate in (20, 30, 40):
            hours = tokens / rate / 3600
            rows.append(
                {
                    "tasks": CORE_TOTAL,
                    "mean_output_tokens": mean_tokens,
                    "decode_tokens": tokens,
                    "tok_per_s": rate,
                    "decode_hours": round(hours, 1),
                }
            )
    return rows


def format_scenarios() -> str:
    lines = [
        "Арифметика при concurrency=1, k=1000. Это не замер и не SLA.",
        "Формула: 673 * mean_output_tokens / tok_per_s / 3600.",
        "Не включает prefill, очередь, паузы, ошибки, повторы и прогон программ.",
        "mean_tokens — не max_tokens. repeats=10 в профиль не входит.",
        "Планировочный коридор при среднем 4000 и 20–40 tok/s: примерно 20–50 часов с запасом.",
    ]
    for row in scenario_rows():
        lines.append(
            f"mean {row['mean_output_tokens']} @ {row['tok_per_s']} tok/s: "
            f"{row['decode_tokens']} tokens, {row['decode_hours']} h"
        )
    lines.append(f"До первого замера ETA одной задачи — заявленные {ESTIMATE_PRIOR_S}s, не max_tokens.")
    return "\n".join(lines)


def eta_for_remaining(remaining: int, walls: list[float]) -> dict:
    """Range from observed request walls. n<15 is a weak estimate."""
    if remaining <= 0:
        return {"remaining": 0, "low_s": 0, "high_s": 0, "point_s": 0, "n": len(walls), "weak": False}
    n = len(walls)
    if n == 0:
        point = ESTIMATE_PRIOR_S
        return {
            "remaining": remaining,
            "low_s": point * remaining,
            "high_s": point * remaining,
            "point_s": point * remaining,
            "per_task_s": point,
            "n": 0,
            "weak": True,
            "basis": f"prior {ESTIMATE_PRIOR_S}s",
        }
    ordered = sorted(walls)
    mid = ordered[n // 2]
    per_low = ordered[0]
    per_high = ordered[-1]
    return {
        "remaining": remaining,
        "low_s": per_low * remaining,
        "high_s": per_high * remaining,
        "point_s": mid * remaining,
        "per_task_s": mid,
        "n": n,
        "weak": n < 15,
        "basis": f"n={n} observed walls",
    }


def window_blocks(now_s: float, deadline_s: float | None, per_task_s: float) -> bool:
    if deadline_s is None:
        return False
    return now_s + per_task_s > deadline_s
