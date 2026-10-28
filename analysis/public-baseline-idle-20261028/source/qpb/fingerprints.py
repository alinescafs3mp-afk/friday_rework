"""Generation identity and a separate scoring identity."""

from __future__ import annotations

import hashlib

from qpb.atomic import canonical
from qpb.pins import (
    EVALSCOPE_VERSION,
    EXTRACT_VERSION,
    IFBENCH_COMMIT,
    LCB_COMMIT,
    PER_TEST_TIMEOUT_S,
    SANDBOX_WALL_CAP_S,
)
from qpb.profile import REQUEST_FIELDS
from qpb.prompts import prompt_fingerprint_material


def sha256_obj(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def generation_material(endpoint: dict, profile: dict, manifest: dict) -> dict:
    datasets = {}
    for name in ("ifbench", "gpqa", "lcb"):
        item = manifest["datasets"][name]
        datasets[name] = {
            "revision": item["revision"],
            "sha256": item["sha256"],
            "order_sha256": item["order_sha256"],
            "count": item["count"],
        }
    return {
        "profile": profile["profile"],
        "profile_version": profile["version"],
        "generation": profile["generation"],
        "sets": profile["sets"],
        "prompts": prompt_fingerprint_material(),
        "endpoint_alias": manifest["endpoint_alias"],
        "model": endpoint["model"],
        "request_fields": REQUEST_FIELDS,
        "thinking": {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_effort": None},
        "datasets": datasets,
        "seed": profile["generation"]["seed"],
    }


def generation_fingerprint(endpoint: dict, profile: dict, manifest: dict) -> str:
    return sha256_obj(generation_material(endpoint, profile, manifest))


def scoring_material(manifest: dict) -> dict:
    return {
        "extract_version": EXTRACT_VERSION,
        "ifbench_commit": IFBENCH_COMMIT,
        "ifbench_call": "test_instruction_following_strict/loose on final answer only",
        "gpqa_parser": "last ANSWER marker, else exact final-line letter; no last-capital fallback",
        "lcb_extract": "last fenced block, one program, no repair",
        "lcb_pass_rule": "every test True; not pass_rate>0",
        "lcb_commit_reference": LCB_COMMIT,
        "lcb_runner": "not_invoked; pinned official testing_util.run_test in bwrap",
        "lcb_testing_util_sha256": "b7cb6a8a69807bb868150a61742e25d7bb5328bbe01d514471b6ec43c9fa9ed2",
        "infrastructure_failure_is_model_answer": False,
        "review_provenance": "versioned-history-v1",
        "review_cache": "prediction-sha256+review-sha256+generation-fp+scoring-fp-v1",
        "evalscope_version_pin": EVALSCOPE_VERSION,
        "evalscope_generate": "not_used",
        "evalscope_rerun_review": "forbidden",
        "sandbox": "bwrap --unshare-all",
        "host_execution_fallback": False,
        "per_test_timeout_s": PER_TEST_TIMEOUT_S,
        "sandbox_wall_cap_s": SANDBOX_WALL_CAP_S,
        "sandbox_wall_formula": "min((per_test_timeout_s+1)*n_tests+15, sandbox_wall_cap_s)",
        "network_in_sandbox": False,
        "private_tests_decode": "restricted-pickle-in-bwrap-v1",
        "sandbox_rlimits": {"as_bytes": 2147483648, "cpu": "ceil(test_timeout)", "nproc": 32,
                           "fsize_bytes": 16777216, "nofile": 64},
        "gold_sha256": {name: manifest["datasets"][name]["sha256"] for name in ("ifbench", "gpqa", "lcb")},
    }


def scoring_fingerprint(manifest: dict) -> str:
    return sha256_obj(scoring_material(manifest))
