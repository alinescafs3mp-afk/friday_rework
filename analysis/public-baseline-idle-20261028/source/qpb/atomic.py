"""Atomic JSON and an append-only journal with a recoverable tail."""

from __future__ import annotations

import json
import os
from pathlib import Path


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = text.encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_result(path: Path) -> dict:
    """Return {ok, value|error}. A partial file is not a success."""
    if not path.exists():
        return {"ok": False, "error": "missing"}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {"ok": False, "error": "empty"}
    try:
        return {"ok": True, "value": json.loads(raw)}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": "partial_json", "detail": str(exc)}


def append_jsonl(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (canonical(obj) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def recover_jsonl_tail(path: Path) -> dict:
    """Drop a truncated final line. Do not treat it as a committed event."""
    if not path.exists():
        return {"recovered": False, "dropped": False}
    raw = path.read_bytes()
    if not raw:
        return {"recovered": False, "dropped": False}
    if raw.endswith(b"\n"):
        lines = raw.splitlines()
        bad = None
        good = []
        for line in lines:
            try:
                json.loads(line.decode("utf-8"))
                good.append(line)
            except json.JSONDecodeError:
                bad = line
        if bad is None:
            return {"recovered": False, "dropped": False}
        atomic_write_text(path, b"\n".join(good).decode("utf-8") + ("\n" if good else ""))
        return {"recovered": True, "dropped": True}
    # No trailing newline: the last line is an unfinished write.
    head, _, _tail = raw.rpartition(b"\n")
    text = head.decode("utf-8") + ("\n" if head else "")
    atomic_write_text(path, text)
    return {"recovered": True, "dropped": True}
