"""CLI. No arguments prints help and status and starts nothing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qpb import __version__
from qpb.paths import tool_root
from qpb.store import RunStore


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=None)
    parser = argparse.ArgumentParser(
        prog="baseline",
        description=(
            "Публичный baseline public-core-v1. Без --allow-live к модели не обращается. "
            "Меню нет: выход из помощи ничего не запускает."
        ),
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    idle = sub.add_parser("idle", parents=[common], help="Локальная подготовка idle; production API не вызывается.")
    idle.add_argument("action", choices=["prepare", "validate", "plan"])
    idle.add_argument("--offline", action="store_true")
    idle.add_argument("--profile", default="public-core-v1")
    idle.add_argument("--coordinator-dir", type=Path)

    sub.add_parser("prepare", parents=[common], help="Проверить локальные данные и записать manifests.")

    validate = sub.add_parser("validate", parents=[common], help="Офлайн-проверка. Реальная сеть закрыта.")
    validate.add_argument("--offline", action="store_true")

    plan = sub.add_parser("plan", parents=[common], help="Показать профиль, пилоты и оценку времени.")
    plan.add_argument("--profile", default="public-core-v1")

    status = sub.add_parser("status", parents=[common], help="Статус инструмента или одного run.")
    status.add_argument("--run", default=None)

    report = sub.add_parser("report", parents=[common], help="Собрать baseline.md из сохранённых ответов.")
    report.add_argument("--run", required=True)

    score = sub.add_parser("score", parents=[common], help="Оценить только сохранённые ответы.")
    score.add_argument("--run", required=True)
    score.add_argument("--offline", action="store_true")

    run = sub.add_parser("run", parents=[common], help="Генерация. Требует --allow-live и отдельную команду Деста.")
    run.add_argument("--profile", default="public-core-v1")
    run.add_argument("--run", required=True)
    run.add_argument("--allow-live", action="store_true")
    run.add_argument("--pilot-only", action="store_true")
    run.add_argument("--window-hours", type=float, default=None)
    run.add_argument("--endpoint", type=Path, default=None)
    run.add_argument("--runs-root", type=Path, default=None)
    run.add_argument("--mode", choices=["manual", "idle"], default="manual")
    run.add_argument("--coordinator-dir", type=Path, default=None)

    pause = sub.add_parser("pause", parents=[common], help="Не планировать следующий запрос.")
    pause.add_argument("--run", required=True)

    resume = sub.add_parser("resume", parents=[common], help="Продолжить тот же run. Требует --allow-live.")
    resume.add_argument("--run", required=True)
    resume.add_argument("--allow-live", action="store_true")
    resume.add_argument("--window-hours", type=float, default=None)
    resume.add_argument("--endpoint", type=Path, default=None)
    resume.add_argument("--runs-root", type=Path, default=None)
    resume.add_argument("--mode", choices=["manual", "idle"], default="manual")
    resume.add_argument("--coordinator-dir", type=Path, default=None)

    stop = sub.add_parser("stop", parents=[common], help="Остановить планирование. Состояние STOPPED.")
    stop.add_argument("--run", required=True)
    return parser


def _root(args) -> Path:
    return (args.root or tool_root()).resolve()


def _endpoint(args, root: Path) -> Path:
    given = getattr(args, "endpoint", None)
    return Path(given) if given else root / "config" / "endpoint.json"


def _runs(args, root: Path) -> Path:
    given = getattr(args, "runs_root", None)
    return Path(given) if given else root / "runs"


def _help_text() -> str:
    return f"""baseline {__version__}
Статус сборки: READY_OFFLINE / AWAITING_USER_START
Профиль: public-core-v1 (673 = IFBench 300 + GPQA Diamond 198 + LiveCodeBench config v6 175)
BFCL: DISABLED_ADAPTER_PENDING, в core не входит.
Живые команды без --allow-live не создают HTTP-клиент и ничего не отправляют.

  baseline prepare
  baseline validate --offline
  baseline plan --profile public-core-v1
  baseline status [--run RUN_ID]
  baseline report --run RUN_ID
  baseline score --run RUN_ID --offline

После отдельной команды Деста, не из этой сборки:
  baseline run --profile public-core-v1 --run RUN_ID --allow-live
  baseline run --profile public-core-v1 --run RUN_ID --pilot-only --allow-live
  baseline run --profile public-core-v1 --run RUN_ID --window-hours 4 --allow-live
  baseline pause --run RUN_ID
  baseline resume --run RUN_ID --allow-live
  baseline stop --run RUN_ID
"""


def _brief(root: Path) -> None:
    runs = root / "runs"
    names = []
    if runs.exists():
        names = sorted(path.name for path in runs.iterdir() if (path / "manifest.json").exists())
    print(f"runs: {', '.join(names) if names else 'нет'}")
    print("Замер не запущен. Жду команду.")


def _status(root: Path, runs_root: Path, run_id: str | None) -> int:
    if run_id is None:
        print(f"baseline {__version__} READY_OFFLINE / AWAITING_USER_START")
        print("live_checked=false")
        _brief(root)
        return 0
    store = RunStore(runs_root, run_id)
    if not store.exists():
        print(f"run {run_id} не найден")
        return 2
    progress = store.progress()
    manifest = store.manifest()
    state = progress.get("state") or manifest.get("state")
    print(
        f"run={run_id} profile={manifest.get('profile')} state={state} "
        f"kind={manifest.get('kind')} live_checked={manifest.get('live_checked')} "
        f"fingerprint={manifest.get('generation_fingerprint')}"
    )
    if progress:
        current = progress.get("current") or "-"
        print(
            f"completed={progress.get('completed')}/{progress.get('expected')} "
            f"attempts={progress.get('attempts')} errors={progress.get('errors')} "
            f"trunc={progress.get('truncations')} current={current} "
            f"active_s={progress.get('active_s')} window={progress.get('window')} eta={progress.get('eta')}"
        )
    if manifest.get("mode") == "idle":
        import json
        import time
        from qpb.idle import Coordinator
        from qpb.runner import _attempt_budget, unfinished_attempt_cap
        _, budget = _attempt_budget(store)
        snapshot = Coordinator(manifest["coordinator_dir"]).snapshot()
        print(json.dumps({"admission": snapshot, "control": store.control(),
                          "authorization_expires_epoch": manifest.get("authorization_expires_epoch"),
                          "authorization_remaining_s": max(0, manifest.get("authorization_expires_epoch", 0) - time.time()),
                          "deferred_ids": manifest.get("deferred_ids", []),
                          **budget,
                          "max_interrupted_attempt_wall_seconds": unfinished_attempt_cap(manifest["idle_policy"]),
                          "unfinished_attempt_cap_enabled": unfinished_attempt_cap(manifest["idle_policy"]) is not None,
                          "expected": 673}, ensure_ascii=False))
    return 0


def _pause_or_stop(root: Path, run_id: str, *, stop: bool) -> int:
    store = RunStore(root / "runs", run_id)
    if not store.exists():
        print(f"run {run_id} не найден")
        return 2
    control = store.control()
    if stop:
        store.set_control(pause=control.get("pause", False), stop=True)
    else:
        store.set_control(pause=True, stop=control.get("stop", False))
    if store.manifest().get("mode") == "idle":
        # Keep active rid/current visible until the worker confirms terminal.
        manifest = store.manifest()
        manifest["user_intent"] = "STOPPED" if stop else "MANUAL_PAUSED"
        store.write_manifest(manifest)
        print("STOP_REQUESTED; cancellation/terminal status remains visible" if stop else "MANUAL_PAUSED; current response may drain")
        return 0
    progress = store.progress() or {"run_id": run_id, "profile": "public-core-v1"}
    if progress.get("current") and not stop:
        progress["state"] = "PAUSING"
        store.write_progress(progress)
        print("PAUSING. Текущий запрос дописывается. Следующий не планируется. Health-check не отправляется.")
        return 0
    manifest = store.manifest()
    manifest["state"] = "STOPPED" if stop else "PAUSED"
    store.write_manifest(manifest)
    progress["state"] = manifest["state"]
    progress["current"] = None
    store.write_progress(progress)
    if stop:
        print("STOPPED. Автопродолжения нет.")
    else:
        print("PAUSED. Активного benchmark-запроса в этом процессе нет. Cancel на сервер не отправлялся.")
    return 0


def _live(args, command: str) -> int:
    if not args.allow_live:
        print("ОТКАЗ: нет --allow-live. HTTP-клиент не создавался. Замер не начат.")
        return 2
    from qpb.endpoint import load_endpoint
    from qpb.prepare import identity_for
    from qpb.profile import load_profile
    from qpb.runner import Runner, IdleRunner

    root = _root(args)
    endpoint_path = _endpoint(args, root)
    endpoint = load_endpoint(endpoint_path)
    profile = load_profile(root / "config" / "public-core-v1.yaml")
    if getattr(args, "profile", "public-core-v1") != "public-core-v1":
        print("Сейчас собран только профиль public-core-v1.")
        return 2
    identity = identity_for(root, endpoint)
    runner_type = IdleRunner if args.mode == "idle" else Runner
    extra = {"coordinator_dir": args.coordinator_dir} if args.mode == "idle" else {}
    runner = runner_type(
        root,
        _runs(args, root),
        args.run,
        profile,
        endpoint,
        identity,
        allow_live=True,
        pilot_only=bool(getattr(args, "pilot_only", False)),
        window_hours=args.window_hours,
        transport_factory=None,
        command=command,
        **extra,
    )
    return runner.execute()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(_help_text(), end="")
        _brief(tool_root())
        return 0
    parser = _parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    root = _root(args)
    if args.command == "idle":
        import json
        from qpb.idle import Coordinator, POLICY, endpoint_key
        from qpb.endpoint import load_endpoint
        if args.action == "validate" and not args.offline:
            print("idle validate requires --offline")
            return 2
        endpoint = load_endpoint(root / "config" / "endpoint.json")
        directory = args.coordinator_dir or root / "runs" / ".admission" / endpoint_key(endpoint["base_url"])
        coordinator = Coordinator(directory)
        snapshot = coordinator.snapshot()
        print(json.dumps({"policy": POLICY, "coordinator_dir": str(directory),
                          "state": snapshot, "live_handoff": "UNVERIFIED",
                          "readiness": "AUTOMATIC_MODE_BLOCKED" if snapshot["blocks"] else "OFFLINE_CONFIGURED_LIVE_EVIDENCE_REQUIRED"},
                         ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare":
        from qpb.prepare import prepare

        runtime = prepare(root, root / "config" / "endpoint.json")
        print(f"prepare PASS fingerprint={runtime['generation_fingerprint']}")
        print("live_checked=false")
        return 0
    if args.command == "validate":
        if not args.offline:
            print("ОТКАЗ: validate без --offline не запускается.")
            return 2
        from qpb.prepare import validate

        return validate(root, root / "config" / "endpoint.json")
    if args.command == "plan":
        if args.profile != "public-core-v1":
            print("Сейчас собран только профиль public-core-v1.")
            return 2
        from qpb.prepare import plan

        return plan(root, root / "config" / "endpoint.json", root / "config" / "public-core-v1.yaml")
    if args.command == "status":
        return _status(root, root / "runs", args.run)
    if args.command == "report":
        from qpb.report import write_report

        store = RunStore(root / "runs", args.run)
        if not store.exists():
            print(f"run {args.run} не найден")
            return 2
        document = write_report(store)
        print(f"report {store.dir / 'baseline.md'} kind={document['kind']} state={document['state']}")
        return 0
    if args.command == "score":
        if not args.offline:
            print("ОТКАЗ: score без --offline не запускается и недостающие ответы не генерирует.")
            return 2
        from qpb.atomic import read_json
        from qpb.fingerprints import generation_fingerprint
        from qpb.profile import load_profile
        from qpb.report import write_report
        from qpb.score import score_run

        store = RunStore(root / "runs", args.run)
        if not store.exists():
            print(f"run {args.run} не найден")
            return 2
        # Recompute from the endpoint stored on the run plus the current
        # profile and dataset pins. Do not load a different endpoint file
        # over this run, and do not generate anything.
        manifest = store.manifest()
        endpoint = {"model": manifest["model"], "base_url": manifest["base_url"]}
        profile = load_profile(root / "config" / "public-core-v1.yaml")
        identity = {
            "endpoint_alias": manifest["endpoint_alias"],
            "datasets": read_json(root / "manifests" / "datasets.json"),
        }
        current = generation_fingerprint(endpoint, profile, identity)
        try:
            score_run(root, store, generation_fingerprint=current)
        except Exception as exc:
            print(str(exc))
            return 2
        document = write_report(store)
        print(
            f"score PASS kind={document['kind']} full_model_baseline={document['full_model_baseline']} "
            "missing answers were not generated"
        )
        return 0
    if args.command == "pause":
        return _pause_or_stop(root, args.run, stop=False)
    if args.command == "stop":
        return _pause_or_stop(root, args.run, stop=True)
    if args.command == "run":
        return _live(args, "run")
    if args.command == "resume":
        return _live(args, "resume")
    print(_help_text(), end="")
    return 0
