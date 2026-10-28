"""Profile load and the explicit request body. Unsupported fields are not dropped."""

from __future__ import annotations

from pathlib import Path

import yaml

from qpb.pins import PROFILE_ID

REQUEST_FIELDS = [
    "chat_template_kwargs",
    "frequency_penalty",
    "max_tokens",
    "messages",
    "min_p",
    "model",
    "n",
    "presence_penalty",
    "repetition_penalty",
    "rid",
    "seed",
    "separate_reasoning",
    "stream",
    "stream_options",
    "stream_reasoning",
    "temperature",
    "top_k",
    "top_p",
]


def load_profile(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("profile") != PROFILE_ID:
        raise RuntimeError(f"expected profile {PROFILE_ID}")
    if data.get("task_count") != 673:
        raise RuntimeError("public-core-v1 task_count must stay 673")
    if "bfcl" in data.get("benchmarks", []):
        raise RuntimeError("BFCL is not part of public-core-v1")
    return data


def generation_body(endpoint: dict, profile: dict, benchmark: str, messages: list, attempt_id: str) -> dict:
    spec = profile["sets"][benchmark]
    gen = profile["generation"]
    body = {
        "model": endpoint["model"],
        "messages": messages,
        "temperature": spec["temperature"],
        "top_p": spec["top_p"],
        "top_k": gen["top_k"],
        "min_p": gen["min_p"],
        "presence_penalty": gen["presence_penalty"],
        "frequency_penalty": gen["frequency_penalty"],
        "repetition_penalty": gen["repetition_penalty"],
        "max_tokens": spec["max_tokens"],
        "seed": gen["seed"],
        "n": gen["n"],
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": True},
        "separate_reasoning": True,
        "stream_reasoning": True,
        "rid": attempt_id,
    }
    # These stay absent on purpose. A later profile change must edit the
    # fingerprint, not silently add them after a 400.
    for banned in ("tools", "tool_choice", "stop", "reasoning_effort", "extra_body"):
        if banned in body:
            raise RuntimeError(f"banned field {banned} was added to the body")
    if set(body) != set(REQUEST_FIELDS):
        raise RuntimeError("request field set drifted")
    if body["chat_template_kwargs"] != {"enable_thinking": True}:
        raise RuntimeError("thinking method drifted")
    return body
