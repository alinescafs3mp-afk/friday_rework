"""Block real network connects during offline commands.

The guard replaces socket connect paths. A blocked call does not reach
the kernel connect, so a named production address is not contacted.
"""

from __future__ import annotations

import socket
from typing import Iterable


class OfflineGuardError(RuntimeError):
    pass


_STATE = {
    "installed": False,
    "allow": set(),
    "attempts": [],
    "orig_connect": None,
    "orig_connect_ex": None,
    "orig_create": None,
}


def _host_port(address):
    if isinstance(address, tuple) and address:
        host = address[0]
        port = address[1] if len(address) > 1 else None
        return str(host), port
    return str(address), None


def install_socket_guard(allow: Iterable[tuple] | None = None) -> None:
    if _STATE["installed"]:
        _STATE["allow"] = set(allow or ())
        _STATE["attempts"] = []
        return
    _STATE["orig_connect"] = socket.socket.connect
    _STATE["orig_connect_ex"] = socket.socket.connect_ex
    _STATE["orig_create"] = socket.create_connection
    _STATE["allow"] = set(allow or ())
    _STATE["attempts"] = []

    def _allowed(host, port) -> bool:
        if (host, port) in _STATE["allow"]:
            return True
        if host in {"127.0.0.1", "localhost"} and ("127.0.0.1", port) in _STATE["allow"]:
            return True
        return False

    def blocked_connect(self, address):
        host, port = _host_port(address)
        _STATE["attempts"].append((host, port))
        if not _allowed(host, port):
            raise OfflineGuardError(f"offline guard blocked {host}:{port}")
        return _STATE["orig_connect"](self, address)

    def blocked_connect_ex(self, address):
        host, port = _host_port(address)
        _STATE["attempts"].append((host, port))
        if not _allowed(host, port):
            raise OfflineGuardError(f"offline guard blocked {host}:{port}")
        return _STATE["orig_connect_ex"](self, address)

    def blocked_create(address, *args, **kwargs):
        host, port = _host_port(address)
        _STATE["attempts"].append((host, port))
        if not _allowed(host, port):
            raise OfflineGuardError(f"offline guard blocked {host}:{port}")
        return _STATE["orig_create"](address, *args, **kwargs)

    socket.socket.connect = blocked_connect
    socket.socket.connect_ex = blocked_connect_ex
    socket.create_connection = blocked_create
    _STATE["installed"] = True


def restore_socket_guard() -> None:
    if not _STATE["installed"]:
        return
    socket.socket.connect = _STATE["orig_connect"]
    socket.socket.connect_ex = _STATE["orig_connect_ex"]
    socket.create_connection = _STATE["orig_create"]
    _STATE["installed"] = False
    _STATE["allow"] = set()


def attempts() -> list:
    return list(_STATE["attempts"])


def assert_real_targets_blocked() -> list[str]:
    """Prove the guard rejects known model and embedding addresses.

    The replacement raises before the original connect, so no SYN is sent.
    """
    targets = [
        ("192.0.2.195", 30000),
        ("192.0.2.195", 8002),
        ("192.0.2.78", 8001),
    ]
    notes = []
    for host, port in targets:
        try:
            socket.create_connection((host, port), timeout=1)
        except OfflineGuardError as exc:
            notes.append(str(exc))
        else:
            raise RuntimeError(f"guard failed open for {host}:{port}")
    return notes
