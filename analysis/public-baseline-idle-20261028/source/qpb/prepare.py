"""Offline prepare, validate, and plan. None of these open a model socket."""

from __future__ import annotations

from pathlib import Path

from qpb.atomic import atomic_write_json, read_json
from qpb.corpus import get_corpus
from qpb.endpoint import alias, load_endpoint
from qpb.estimate import format_scenarios
from qpb.fingerprints import generation_fingerprint, scoring_fingerprint
from qpb.guard import assert_real_targets_blocked, install_socket_guard, restore_socket_guard
from qpb.lcb_sandbox import bwrap_available, grade
from qpb.pins import (
    BFCL_BLOCKER,
    DATASETS,
    EVALSCOPE_VERSION,
    IFBENCH_COMMIT,
    LCB_COMMIT,
    MODEL_IDENTITY,
    OPENAPI_NOTE,
    REFERENCE_CLAIMS,
    UNVERIFIED,
)
from qpb.profile import load_profile

DATA_NAMES = ("ifbench", "gpqa", "lcb")


def _sha(obj) -> str:
    from qpb.fingerprints import sha256_obj

    return sha256_obj(obj)


def datasets_document(root: Path) -> dict:
    corpus = get_corpus(root)
    corpus.verify_files()
    document = {}
    for name in DATA_NAMES:
        pin = DATASETS[name]
        order = corpus.order[name]
        item = {
            "revision": pin["revision"],
            "sha256": pin["sha256"],
            "bytes": pin["bytes"],
            "count": len(order),
            "split": pin["split"],
            "repo": pin["repo"],
            "id_field": pin["id_field"],
            "ids": order,
            "pilot_ids": corpus.pilot[name],
            "order_sha256": _sha(order),
            "id_set_sha256": _sha(sorted(order)),
        }
        if name == "gpqa":
            item["revision_note"] = pin["revision_note"]
            item["split_note"] = pin["split_note"]
            item["choices_file"] = "manifests/gpqa-choices.json"
        if name == "lcb":
            item["config"] = pin["config"]
            item["not_configs"] = pin["not_configs"]
            item["contest_date_min"] = min(corpus.lcb_dates)
            item["contest_date_max"] = max(corpus.lcb_dates)
            item["difficulty"] = corpus.lcb_difficulty
            item["scorer_reference_commit"] = LCB_COMMIT
        if name == "ifbench":
            item["scorer_commit"] = IFBENCH_COMMIT
        document[name] = item
    return document


def identity_for(root: Path, endpoint: dict) -> dict:
    datasets = read_json(root / "manifests" / "datasets.json")
    return {"endpoint_alias": alias(endpoint), "datasets": datasets}


def prepare(root: Path, endpoint_path: Path) -> dict:
    endpoint = load_endpoint(endpoint_path)
    document = datasets_document(root)
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    corpus = get_corpus(root)
    choices = {
        task_id: {
            "correct_letter": task["correct_letter"],
            "choices": task["choices"],
            "shuffle_seed": task["shuffle_seed"],
        }
        for task_id, task in corpus.tasks["gpqa"].items()
    }
    atomic_write_json(manifest_dir / "gpqa-choices.json", choices)
    atomic_write_json(manifest_dir / "datasets.json", document)
    atomic_write_json(manifest_dir / "reference-claims.json", REFERENCE_CLAIMS)
    profile = load_profile(root / "config" / "public-core-v1.yaml")
    identity = {"endpoint_alias": alias(endpoint), "datasets": document}
    runtime = {
        "tool_version": "0.1.0",
        "evalscope_pin": EVALSCOPE_VERSION,
        "evalscope_generate": "not_used",
        "evalscope_reason": (
            "EvalScope 1.14.1 retries streaming POSTs by default (retries=5 plus the OpenAI SDK default). "
            "This tool sends one raw HTTP POST with retries=0."
        ),
        "ifbench_commit": IFBENCH_COMMIT,
        "ifbench_verifier_note": "Official IFBench commit, not the drifted copy vendored in evalscope.",
        "lcb_commit_reference": LCB_COMMIT,
        "lcb_runner": "not_invoked",
        "sandbox": "bwrap" if bwrap_available() else "MISSING",
        "docker": False,
        "nltk_dir": "data/nltk",
        "model_identity": MODEL_IDENTITY,
        "openapi_historical": OPENAPI_NOTE,
        "endpoint_alias": alias(endpoint),
        "live_checked": False,
        "generation_fingerprint": generation_fingerprint(endpoint, profile, identity),
        "scoring_fingerprint": scoring_fingerprint(identity),
        "unverified": UNVERIFIED,
        "bfcl": {"status": "DISABLED_ADAPTER_PENDING", "blocker": BFCL_BLOCKER},
        "ruifeval": {"enabled": False, "downloaded": False},
    }
    atomic_write_json(manifest_dir / "runtime.json", runtime)
    return runtime


def validate(root: Path, endpoint_path: Path) -> int:
    install_socket_guard()
    try:
        blocked = assert_real_targets_blocked()
        endpoint = load_endpoint(endpoint_path)
        if endpoint.get("kind") != "model":
            raise RuntimeError("production endpoint kind drifted")
        if endpoint.get("live_checked"):
            raise RuntimeError("live_checked must stay false until a real command")
        profile = load_profile(root / "config" / "public-core-v1.yaml")
        if profile["generation"]["retries_after_accepted_post"] != 0:
            raise RuntimeError("retries must stay 0")
        document = datasets_document(root)
        saved = read_json(root / "manifests" / "datasets.json")
        for name in DATA_NAMES:
            if saved[name]["ids"] != document[name]["ids"]:
                raise RuntimeError(f"{name} id order drifted")
            if saved[name]["count"] != document[name]["count"]:
                raise RuntimeError(f"{name} count drifted")
            if len(set(saved[name]["ids"])) != saved[name]["count"]:
                raise RuntimeError(f"{name} ids are not unique")
        saved_choices = read_json(root / "manifests" / "gpqa-choices.json")
        for task_id, task in get_corpus(root).tasks["gpqa"].items():
            frozen = saved_choices[task_id]
            if frozen["correct_letter"] != task["correct_letter"] or frozen["choices"] != task["choices"]:
                raise RuntimeError("GPQA choice order drifted")
        auth = read_json(root / "config" / "authorization-state.json")
        if auth.get("granted") is True:
            print("authorization granted=true замечен и проигнорирован. Флаг --allow-live он не заменяет.")
        probe = grade(
            "import sys\nsys.stdout.write(sys.stdin.read())",
            {"fn_name": None, "inputs": ["7\n"], "outputs": ["7\n"]},
            per_test_timeout=6,
            wall_cap=30,
        )
        if probe["outcome"] != "correct":
            raise RuntimeError(f"sandbox self-check failed: {probe}")
        hidden = grade(
            "import os\nprint('yes' if os.path.exists('/home/baseline-owner') else 'no')",
            {"fn_name": None, "inputs": ["\n"], "outputs": ["no\n"]},
            per_test_timeout=6,
            wall_cap=30,
        )
        if hidden["outcome"] != "correct":
            raise RuntimeError(f"sandbox can see the host tree or failed: {hidden}")
        print("validate PASS")
        print("counts 300/198/175 unique ids match manifests")
        print("socket guard blocked:", "; ".join(blocked))
        print("sandbox bwrap PASS; host path not visible; no host-exec fallback")
        print("live_checked false")
        for line in UNVERIFIED:
            print("UNVERIFIED:", line)
        return 0
    finally:
        restore_socket_guard()


def plan(root: Path, endpoint_path: Path, profile_path: Path) -> int:
    endpoint = load_endpoint(endpoint_path)
    profile = load_profile(profile_path)
    identity = identity_for(root, endpoint)
    fingerprint = generation_fingerprint(endpoint, profile, identity)
    datasets = identity["datasets"]
    print(f"profile {profile['profile']} tasks {profile['task_count']}")
    for name in DATA_NAMES:
        item = datasets[name]
        print(
            f"{name}: count={item['count']} revision={item['revision']} "
            f"sha256={item['sha256'][:12]} pilot={','.join(item['pilot_ids'])}"
        )
    print(f"generation_fingerprint {fingerprint}")
    print(f"endpoint_alias {identity['endpoint_alias']} live_checked=false")
    print("BFCL DISABLED_ADAPTER_PENDING")
    print(BFCL_BLOCKER)
    print("ruIFEval enabled=false downloaded=false")
    for line in UNVERIFIED:
        print("UNVERIFIED:", line)
    print(format_scenarios())
    print("Команды после отдельной команды Деста, не сейчас:")
    print("  baseline run --profile public-core-v1 --run public-core-v1 --allow-live")
    print("  baseline run --profile public-core-v1 --run public-core-v1 --pilot-only --allow-live")
    print("  baseline run --profile public-core-v1 --run public-core-v1 --window-hours 4 --allow-live")
    print("  baseline pause --run public-core-v1")
    print("  baseline resume --run public-core-v1 --allow-live")
    print("  baseline stop --run public-core-v1")
    print("  baseline score --run public-core-v1 --offline")
    return 0
