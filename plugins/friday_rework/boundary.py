"""Model arguments are task content, never ownership or execution authority."""
from __future__ import annotations

from contextvars import copy_context
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class WorkBrief:
    worker: str
    brief: str
    goal_check: str


def parse_brief(args):
    if not isinstance(args, dict) or set(args) != {"worker", "brief", "goal_check"}:
        raise ValueError("invalid_fields")
    if args["worker"] not in ("dsh", "a0"):
        raise ValueError("unsupported_worker")
    for key, limit in (("brief", 8192), ("goal_check", 2048)):
        value = args[key]
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError("invalid_task_text")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("invalid_task_text") from exc
        if size > limit:
            raise ValueError("task_text_too_large")
    return WorkBrief(**args)


def bound_owner(*, session_id=None):
    # The native get_session_env accessor falls back to process environment.
    # Only values bound in this execution context can be routing observations.
    # This is not authorization/admission proof; bot/update/input provenance
    # must be joined at the trusted gateway boundary before any future launch.
    names = ("PLATFORM", "CHAT_ID", "CHAT_TYPE", "THREAD_ID", "USER_ID",
             "KEY", "ID", "MESSAGE_ID", "PROFILE")
    wanted = {"HERMES_SESSION_" + name for name in names}
    bound = {var.name: value for var, value in copy_context().items() if var.name in wanted}
    if len(bound) != len(wanted) or any(not isinstance(value, str) for value in bound.values()):
        raise ValueError("missing_bound_owner")
    owner = {name.lower(): bound["HERMES_SESSION_" + name] for name in names}
    required = ("platform", "chat_id", "chat_type", "user_id", "key", "id", "message_id")
    if any(not owner[key] or len(owner[key]) > 512 for key in required):
        raise ValueError("missing_bound_owner")
    if any(len(value) > 512 or "\x00" in value for value in owner.values()):
        raise ValueError("invalid_bound_owner")
    if session_id is not None and session_id != owner["id"]:
        raise ValueError("session_mismatch")
    return owner


def work_handler(args, **kwargs):
    try:
        brief = parse_brief(args)
        bound_owner(session_id=kwargs.get("session_id"))
    except ValueError as exc:
        return json.dumps({"accepted": False, "error": str(exc)})
    # FRW-008 establishes the supported registration/content boundary only.
    # FRW-010 must add durable admission and real supervisor identity before
    # either adapter may make effects. Never simulate a job or mint a queued ID.
    return json.dumps({
        "accepted": False,
        "worker": brief.worker,
        "error": "worker_not_admitted",
        "message": "Supervised worker execution is not available in this candidate.",
    })
