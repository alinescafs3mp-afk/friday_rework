"""Join native call correlation to a durable post-authorization ingress receipt.

This authorizes no worker by itself: verified workspace/input bytes, budgets,
native supervision and adapter readiness are separate controller prerequisites.
"""
from __future__ import annotations

from contextvars import ContextVar
import copy
import hashlib
import json
from pathlib import Path

from .associations import Associations, _sync_directory
from .boundary import bound_owner, parse_brief, work_handler

KEY = "admitted_ingress.v1"
CALL_FIELDS = ("task_id", "session_id", "turn_id", "api_request_id", "tool_call_id")
_call = ContextVar("friday_native_call", default=None)


def _text(value, limit=512, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or "\x00" in value:
        raise ValueError("invalid_ingress")
    if len(value.encode("utf-8")) > limit:
        raise ValueError("invalid_ingress")
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _snapshot(value):
    top = {"platform", "session_key", "source_profile", "transport_profile", "runtime_profile", "message"}
    fields = {"bot_id", "user_id", "chat_id", "thread_id", "message_id", "platform_update_id", "reply_to_message_id", "media"}
    if not isinstance(value, dict) or set(value) != top or value["platform"] != "telegram":
        raise ValueError("unproved_ingress")
    for key in top - {"message"}:
        _text(value[key], empty=key == "source_profile")
    message = value["message"]
    if not isinstance(message, dict) or set(message) != fields:
        raise ValueError("invalid_ingress")
    for key in fields - {"media"}:
        _text(message[key], empty=key in {"thread_id", "reply_to_message_id"})
    if not isinstance(message["media"], list) or len(message["media"]) > 64:
        raise ValueError("invalid_ingress")
    for media in message["media"]:
        if not isinstance(media, dict) or set(media) != {"local_reference", "mime_type", "origin"}:
            raise ValueError("invalid_ingress")
        _text(media["local_reference"], 2048)
        _text(media["mime_type"], 256)
        origin = media["origin"]
        if origin is not None:
            required = {"bot_id", "chat_id", "thread_id", "message_id", "file_id", "file_unique_id", "declared_bytes"}
            if not isinstance(origin, dict) or set(origin) != required:
                raise ValueError("invalid_ingress")
            for key in required - {"declared_bytes"}:
                _text(origin[key], empty=key == "thread_id")
            size = origin["declared_bytes"]
            if size is not None and (type(size) is not int or size < 0):
                raise ValueError("invalid_ingress")
            if any(origin[k] != message[k] for k in ("bot_id", "chat_id", "thread_id")):
                raise ValueError("foreign_input_origin")
    if len(_encoded(value)) > 65536:
        raise ValueError("ingress_too_large")
    return copy.deepcopy(value)


def _receipt_key(value):
    # One routed message cannot silently acquire another bot/update identity.
    return hashlib.sha256(_encoded([
        value["session_key"], value["source_profile"], value["message"]["message_id"]
    ])).hexdigest()


def native_call_scope(*, tool_name, args, next_call, **context):
    """Transport correlation through the supported middleware, never effects.

    Native policy is inside next_call. If this wrapper fails, Hermes may fall
    through; therefore the registered handler independently requires a scope.
    """
    if tool_name != "friday_work":
        return next_call(args)
    # Mask an outer invocation before allocation/validation can fail. Hermes
    # falls through after middleware exceptions, so no such fallback may use
    # the parent's correlation as proof for this call.
    token = _call.set(None)
    try:
        try:
            identity = tuple(_text(context.get(key)) for key in CALL_FIELDS)
        except Exception:
            identity = None
        _call.set(identity)
        # Native middleware propagates downstream errors without replay. Keep
        # the surrounding call usable when it handles an inner tool failure.
        return next_call(args)
    finally:
        _call.reset(token)


class IngressAdmissions:
    def __init__(self, state):
        self.state = state
        self.associations = Associations(state)

    def _read(self):
        document = self.state.get(KEY, {"schema_version": 1, "receipts": {}})
        if (not isinstance(document, dict) or set(document) != {"schema_version", "receipts"}
                or type(document["schema_version"]) is not int or document["schema_version"] != 1
                or not isinstance(document["receipts"], dict)):
            raise ValueError("invalid_ingress_store")
        for key, value in document["receipts"].items():
            if key != _receipt_key(_snapshot(value)):
                raise ValueError("invalid_ingress_store")
        return document

    def record(self, *, admitted_ingress=None, session_key, message_id, source, platform, **_):
        snapshot = _snapshot(admitted_ingress)
        message = snapshot["message"]
        if (platform != snapshot["platform"] or session_key != snapshot["session_key"]
                or message_id != message["message_id"] or not isinstance(source, dict)
                or any((source.get(k) or "") != message[k] for k in ("user_id", "chat_id", "thread_id", "message_id"))
                or (source.get("profile") or "") != snapshot["source_profile"]):
            raise ValueError("ingress_source_mismatch")
        with self.associations._locked():
            document = self._read()
            key = _receipt_key(snapshot)
            prior = document["receipts"].get(key)
            if prior is not None:
                if prior != snapshot:
                    raise ValueError("ingress_identity_conflict")
                return
            document["receipts"][key] = snapshot
            self.state.set(KEY, document)
            _sync_directory(Path(self.state.data_dir))

    def match(self, owner, *, task_id, session_id):
        call = _call.get()
        if call is None or call[:2] != (task_id, session_id) or session_id != owner["id"]:
            raise ValueError("missing_native_correlation")
        lookup = {"session_key": owner["key"], "source_profile": owner["profile"],
                  "message": {"message_id": owner["message_id"]}}
        with self.associations._locked():
            snapshot = self._read()["receipts"].get(_receipt_key(lookup))
            if snapshot is None:
                raise ValueError("missing_admitted_ingress")
            if (snapshot["platform"] != owner["platform"]
                    or any(snapshot["message"][k] != owner[k] for k in ("user_id", "chat_id", "thread_id", "message_id"))):
                raise ValueError("foreign_admitted_ingress")
            # Native state may have committed before an earlier caller failed
            # its directory barrier. Complete that barrier before using it.
            _sync_directory(Path(self.state.data_dir))
            return copy.deepcopy(snapshot), dict(zip(CALL_FIELDS, call))

    def handle(self, args, **kwargs):
        try:
            parse_brief(args)
            owner = bound_owner(session_id=kwargs.get("session_id"))
            self.match(owner, task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id"))
        except (ValueError, UnicodeError, RuntimeError, OSError):
            return json.dumps({"accepted": False, "error": "unproved_admission"})
        # This candidate proves the join; the controller/worker readiness gate
        # stays closed until actual native supervision and adapters are wired.
        return work_handler(args, **kwargs)
