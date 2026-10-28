"""Monitor one existing raw transport and cancel only its registered rid.

Cancellation success is the original SSE terminal abort, never the abort HTTP
status. Losing either response conservatively retains endpoint ownership.
"""
from concurrent.futures import Future
from http.client import HTTPConnection
import json
import threading
import time
from urllib.parse import urlsplit

from qpb.errors import OutcomeUnknownError
from qpb.idle import IdleBlocked


class InterruptedByForeground(RuntimeError):
    def __init__(self, result, reason):
        self.result, self.reason = result, reason


def abort_owned(coordinator, permit, base_url, headers, timeout_s):
    # The local ownership check happens before constructing any HTTP object.
    if not coordinator.cancellation(permit):
        return
    parts = urlsplit(base_url)
    if parts.scheme != "http":
        raise IdleBlocked("only the installed HTTP serving route is prepared")
    connection = HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout_s)
    try:
        body = json.dumps({"rid": permit["rid"], "abort_all": False}).encode()
        connection.request("POST", "/abort_request", body, headers)
        response = connection.getresponse()
        response.read()
        if response.status != 200:
            raise OutcomeUnknownError("owned cancellation rejected")
    finally:
        connection.close()


def monitored_post(transport, coordinator, permit, store, base_url, headers, body, timeout_s, mark_sending, policy, *, cancel=abort_owned):
    sent_event = threading.Event()
    transport.sent_event = sent_event
    future = Future()
    def generate():
        try:
            future.set_result(transport.post(base_url, headers, body, timeout_s, mark_sending))
        except BaseException as exc:
            future.set_exception(exc)
    threading.Thread(target=generate, name="qpb-one-request", daemon=True).start()
    reason, cancel_at = None, None
    handoff = {"foreground_signal_epoch": None, "cancel_requested_epoch": None, "cancel_sent_epoch": None,
               "terminal_observed_epoch": None, "foreground_to_terminal_s": None,
               "added_foreground_dispatch_delay_s": None}
    while not future.done():
        try:
            snapshot = coordinator.snapshot()
        except Exception:
            coordinator.fault("snapshot_failed")
            raise OutcomeUnknownError("coordinator failed during generation")
        control = store.control()
        should_cancel = bool(snapshot["foreground"]) or control.get("stop") or bool(snapshot["blocks"])
        # Wait until the complete POST has crossed the socket. Never send abort
        # before a request which could then arrive after that abort.
        if should_cancel and sent_event.is_set() and cancel_at is None:
            reason = "CANCELLED_BY_STOP" if control.get("stop") else "INTERRUPTED_BY_FOREGROUND"
            cancel_at = time.monotonic()
            handoff["foreground_signal_epoch"] = (snapshot.get("inflight") or {}).get("foreground_at")
            handoff["cancel_requested_epoch"] = time.time()
            cancelled = Future()
            def do_cancel():
                try:
                    cancelled.set_result(cancel(coordinator, permit, base_url, headers, policy["cancel_confirm_timeout_seconds"]))
                except BaseException as exc:
                    cancelled.set_exception(exc)
            threading.Thread(target=do_cancel, name="qpb-owned-cancel", daemon=True).start()
        if cancel_at is not None and time.monotonic() - cancel_at >= policy["cancel_confirm_timeout_seconds"]:
            if not future.done():
                raise OutcomeUnknownError("BLOCKED_CANCEL: original SSE has no terminal confirmation")
        time.sleep(0.02)
    result = future.result()
    response_ids = result.get("server_response_ids")
    # Fake transports explicitly omit this field. Actual HTTP transports always
    # supply it and must echo this random owned request namespace.
    if response_ids is not None and (not response_ids or any(not rid.startswith(permit["rid"]) for rid in response_ids)):
        raise OutcomeUnknownError("original SSE did not match the owned request namespace")
    if cancel_at is not None:
        handoff["terminal_observed_epoch"] = time.time()
        if handoff["foreground_signal_epoch"] is not None:
            handoff["foreground_to_terminal_s"] = max(0, handoff["terminal_observed_epoch"] - handoff["foreground_signal_epoch"])
        result["handoff"] = handoff
    if result.get("finish_reason") == "abort":
        if reason is None:
            raise OutcomeUnknownError("unsolicited abort; server outcome needs reconciliation")
        raise InterruptedByForeground(result, reason)
    if result.get("finish_reason") not in {"stop", "length"}:
        raise OutcomeUnknownError("unrecognized terminal reason")
    return result
