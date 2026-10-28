"""Pinned public dataset/scorer protocol; deployment identity is a placeholder.

This analysis copy is not live verified or deployable as-is.
"""

from __future__ import annotations

IFBENCH_COMMIT = "1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d"
LCB_COMMIT = "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
EVALSCOPE_VERSION = "1.14.1"
EXTRACT_VERSION = "1"
PROFILE_ID = "public-core-v1"
EXPECTED = {"ifbench": 300, "gpqa": 198, "lcb": 175}
CORE_TOTAL = 673
ESTIMATE_PRIOR_S = 600
PER_TEST_TIMEOUT_S = 6
SANDBOX_WALL_CAP_S = 1800

DATASETS = {
    "ifbench": {
        "path": "data/ifbench/test.jsonl",
        "sha256": "6fdd5e7802f23cb1fdd62f3b03bb027738c302c1644d04ec17319aa2d955ca68",
        "bytes": 421503,
        "rows": 300,
        "id_field": "key",
        "repo": "allenai/IFBench_test",
        "revision": "2e8a48de45ff3bf41242f927254ca81b59ca3ae2",
        "split": "train",
        "source": "huggingface",
    },
    "gpqa": {
        "path": "data/gpqa/train.jsonl",
        "sha256": "969e3420021deb736f64328e2bb239accb7a301ad90a6c3686c8ad7ebf2528f3",
        "bytes": 1874046,
        "rows": 198,
        "id_field": "Record ID",
        "repo": "AI-ModelScope/gpqa_diamond",
        "revision": "master",
        "revision_note": "master is a moving label. The pin is the file sha256, not the label.",
        "split": "train",
        "split_note": "The split is named train. It is the Diamond test set, not few-shot examples.",
        "source": "modelscope",
    },
    "lcb": {
        "path": "data/lcb/v6.jsonl",
        "sha256": "e92fbf266ad18eaa6995a03104792d494b342f1a3c2524bbd99d67afc35b6f21",
        "bytes": 134303098,
        "rows": 175,
        "id_field": "question_id",
        "repo": "livecodebench/code_generation_lite",
        "config": "v6",
        "revision": "175d0ac20500fd7aa0813f7a2e6ae7ecad3c76c9",
        "split": "test",
        "source": "huggingface",
        "not_configs": ["release_v6", "release_latest"],
        "contest_date_min": "2025-01-04T00:00:00",
        "contest_date_max": "2025-04-06T00:00:00",
        "difficulty": {"easy": 43, "medium": 52, "hard": 80},
        "parquet": "v6/test-00000-of-00001.parquet",
    },
}

# Public placeholder metadata; not a deployment configuration.
MODEL_IDENTITY = {'source': 'public_placeholder_not_live_verified', 'live_checked': False, 'served_model_id': 'qwen38-flash-next-abliterated', 'base_url': 'http://192.0.2.195:30000/v1', 'api_key_env': 'FRIDAY_BENCH_API_KEY', 'context_tokens': 262144, 'image': 'UNVERIFIED_DEPLOYMENT_IMAGE', 'image_id': 'UNVERIFIED', 'container': 'UNVERIFIED_DEPLOYMENT_CONTAINER', 'quantization': 'modelopt_fp4', 'weights_path': '/opt/models/UNVERIFIED', 'observed_run_generation': None, 'observed_run_id': 'UNVERIFIED', 'observed_ready_at': None, 'note': 'Public deployment placeholders. This file is not the installed deployment identity. Official dataset and scorer pins are preserved.'}

REFERENCE_CLAIMS = {
    "source_url": "https://huggingface.co/Qwen/Qwen3.8-Flash-Next",
    "checked_on": "2026-10-28",
    "metric_confirmed": False,
    "note": (
        "Card scores belong to the original model and its unpublished exact procedure. "
        "They are not targets for the abliterated NVFP4 endpoint and are not an average IQ."
    ),
    "claims": [
        {
            "benchmark": "IFBench",
            "score": 81.3,
            "comparability": "B",
            "reason": (
                "Same named benchmark. The card does not publish sample, prompt, shots, "
                "generation mode, or attempt count for this score."
            ),
        },
        {
            "benchmark": "GPQA Diamond",
            "score": 91.7,
            "comparability": "B",
            "reason": (
                "Same named benchmark. The card footnotes do not specify the protocol "
                "for this score. Our profile is 0-shot generative CoT, one sample."
            ),
        },
        {
            "benchmark": "LiveCodeBench v6",
            "score": 91.9,
            "comparability": "C",
            "reason": (
                "The card label v6 is ambiguous with release_v6=1055. This profile pins "
                "config v6 = 175 problems at revision 175d0ac, contest dates "
                "2025-01-04 through 2025-04-06. Author subset is not confirmed."
            ),
        },
    ],
}

UNVERIFIED = [
    "Живое совпадение model id, контекста, квантизации и ревизии весов не проверялось.",
    "Серверное принятие тела (top_k, min_p, seed, chat_template_kwargs.enable_thinking, separate_reasoning, stream_reasoning) не проверялось.",
    "Имя SSE-поля reasoning (reasoning_content или reasoning) не проверялось. Клиент принимает оба и пишет, какое пришло.",
    "Эхо seed в ответе не проверялось. Отсутствие эха — UNVERIFIED, не ошибка запроса.",
    "Исторический native-abort по rid не перепроверялся и этим инструментом не вызывается. Пауза — мягкое ожидание.",
    "Эндпоинт эмбеддера этим профилем не используется и не опрашивался.",
]

BFCL_BLOCKER = (
    "EvalScope 1.14.1 BFCL v4 adapter calls OpenAICompletionsHandler "
    "(is_fc_model default true) but pins bfcl-eval==2025.10.27.1, not the "
    "leaderboard pin 2025.12.17 / commit f7cf735. Adapter init and match_score "
    "construct that handler and can run prereq inference. Wiring it into "
    "retries=0, offline score, and the atomic journal needs a separate adapter "
    "port. Core is not blocked. BFCL was not installed and was not run."
)

OPENAPI_NOTE = {
    "source": "HISTORICAL_SCHEMA_NOT_INCLUDED",
    "live_checked": False,
    "chat_required": ["messages"],
    "first_class_fields": [
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "frequency_penalty",
        "repetition_penalty",
        "seed",
        "max_tokens",
        "max_completion_tokens",
        "chat_template_kwargs",
        "stream",
        "stream_options",
        "stop",
        "tools",
        "tool_choice",
        "rid",
        "separate_reasoning",
        "stream_reasoning",
        "reasoning_effort",
    ],
    "not_sent": ["stop", "tools", "tool_choice", "reasoning_effort", "extra_body", "preserve_thinking"],
    "note": "Historical schema only. extra_body is absent there, so top_k and min_p are sent as top-level fields. Live acceptance is UNVERIFIED.",
}
