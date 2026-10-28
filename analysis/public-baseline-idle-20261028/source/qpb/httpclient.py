"""One streaming POST. No SDK, no retry, no second send after an ambiguous drop."""

from __future__ import annotations

import json
import socket
import time
from http.client import HTTPConnection
from urllib.parse import urlsplit

from qpb.errors import OutcomeUnknownError, ProtocolDiagnostic, TransportError


def _reasoning_tokens(usage: dict | None):
    if not isinstance(usage, dict):
        return None
    if "reasoning_tokens" in usage:
        return usage["reasoning_tokens"]
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict) and "reasoning_tokens" in details:
        return details["reasoning_tokens"]
    return None


def _consume_sse(raw_text: str, t_send: float, arrivals=None) -> dict:
    content: list[str] = []
    reasoning: list[str] = []
    reasoning_field = None
    finish = None
    usage = None
    ttft = None
    first_final = None
    seed_echoed = None
    response_ids = set()
    done = False
    trailing_error = None
    for block_number, block in enumerate(raw_text.split("\n\n")):
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        data = "\n".join(data_lines).strip()
        if data == "[DONE]":
            done = True
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError as exc:
            if finish is not None:
                trailing_error = "partial_event_after_terminal"
                break
            raise OutcomeUnknownError(f"partial SSE event: {exc}") from exc
        if isinstance(event, dict) and "seed" in event:
            seed_echoed = True
        if isinstance(event, dict) and isinstance(event.get("id"), str):
            response_ids.add(event["id"])
        if isinstance(event, dict) and event.get("usage"):
            usage = event["usage"]
        choices = event.get("choices") if isinstance(event, dict) else None
        if not choices:
            continue
        choice = choices[0] or {}
        if choice.get("finish_reason"):
            finish = choice["finish_reason"]
        delta = choice.get("delta") or {}
        if delta.get("role") and not any(delta.get(key) for key in ("content", "reasoning_content", "reasoning")):
            continue
        now = arrivals[block_number] if arrivals and block_number < len(arrivals) else None
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            content.append(piece)
            if ttft is None and now is not None:
                ttft = now - t_send
            if first_final is None and now is not None:
                first_final = now - t_send
        for key in ("reasoning_content", "reasoning"):
            thought = delta.get(key)
            if isinstance(thought, str) and thought:
                reasoning.append(thought)
                reasoning_field = key
                if ttft is None and now is not None:
                    ttft = now - t_send
    return {
        "content": "".join(content),
        "reasoning": "".join(reasoning) or None,
        "reasoning_delta_field": reasoning_field,
        "finish_reason": finish,
        "usage": usage,
        "reasoning_tokens": _reasoning_tokens(usage),
        "ttft_s": ttft,
        "first_final_content_s": first_final,
        "seed_echoed": seed_echoed,
        "server_response_ids": sorted(response_ids),
        "sse_done_received": done,
        "trailing_stream_error": trailing_error,
    }


class UrllibTransport:
    """Created only after --allow-live. Tests can substitute a fake."""

    def post(self, base_url: str, headers: dict, body: dict, timeout_s: float, mark_sending) -> dict:
        parts = urlsplit(base_url.rstrip("/") + "/chat/completions")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if parts.scheme == "https":
            raise TransportError("https is not the prepared Spark API", sent=False)
        connection = HTTPConnection(parts.hostname, port, timeout=timeout_s)
        try:
            lines, arrivals, block = [], [], []
            try:
                connection.connect()
            except (OSError, socket.timeout) as exc:
                raise TransportError(f"connect failed: {exc}", sent=False) from exc
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            path = parts.path or "/v1/chat/completions"
            mark_sending()
            t_send = time.monotonic()
            try:
                connection.putrequest("POST", path)
                for key, value in headers.items():
                    connection.putheader(key, value)
                connection.putheader("Content-Length", str(len(payload)))
                connection.endheaders()
                connection.send(payload)
                if hasattr(self, "sent_event"):
                    self.sent_event.set()
            except Exception as exc:
                raise OutcomeUnknownError(f"send failed after SENDING: {exc}") from exc
            try:
                response = connection.getresponse()
                status = response.status
                while True:
                    line = response.readline()
                    if not line:
                        break
                    lines.append(line)
                    block.append(line)
                    if line in {b"\n", b"\r\n"}:
                        arrivals.append(time.monotonic())
                        block = []
                raw_bytes = b"".join(lines)
            except Exception as exc:
                partial = b"".join(lines).decode("utf-8", "replace")
                # The installed SGLang terminal chunk comes after all final
                # content. Losing later usage/[DONE] does not invalidate that
                # already completed generation or authorize another POST.
                try:
                    terminal = _consume_sse(partial.replace("\r\n", "\n"), t_send, arrivals)
                except OutcomeUnknownError:
                    terminal = None
                if terminal and terminal.get("finish_reason") in {"stop", "length", "abort"}:
                    terminal.update(raw=partial, wall_s=time.monotonic() - t_send,
                                    truncated=terminal["finish_reason"] == "length", http_status=status,
                                    trailing_stream_error=type(exc).__name__,
                                    usage_complete=terminal.get("usage") is not None)
                    return terminal
                raise OutcomeUnknownError("response failed after send: " + type(exc).__name__,
                    partial_raw=partial, timing={"wall_s": time.monotonic() - t_send,
                                               "arrivals_monotonic": arrivals},
                    request_id=body.get("rid")) from exc
        finally:
            connection.close()

        raw_text = raw_bytes.decode("utf-8", "replace")
        if status == 400:
            raise ProtocolDiagnostic(raw_text[:2000])
        if status in {401, 403}:
            raise TransportError(f"http {status}", sent=True, status=status)
        if status >= 400:
            raise TransportError(f"http {status}: {raw_text[:500]}", sent=True, status=status)
        try:
            parsed = _consume_sse(raw_text.replace("\r\n", "\n"), t_send, arrivals)
        except OutcomeUnknownError as exc:
            raise OutcomeUnknownError(str(exc), partial_raw=raw_text,
                                      timing={"wall_s": time.monotonic() - t_send}, request_id=body.get("rid")) from exc
        if not parsed["finish_reason"]:
            raise OutcomeUnknownError("stream ended without finish_reason", partial_raw=raw_text,
                                      timing={"wall_s": time.monotonic() - t_send}, request_id=body.get("rid"))
        parsed["http_status"] = status
        parsed["raw"] = raw_text
        parsed["wall_s"] = time.monotonic() - t_send
        parsed["truncated"] = parsed["finish_reason"] == "length"
        parsed["usage_complete"] = parsed.get("usage") is not None
        return parsed
