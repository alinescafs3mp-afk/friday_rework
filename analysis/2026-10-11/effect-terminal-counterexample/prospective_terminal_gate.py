"""SOURCE-ONLY terminal classifier. It does not install or grant a live permit.

The existing native notification vocabulary is preserved. A hook callback's
completion and a tool command's exit do not certify every retained callback.
The OWNED runner supplies process closure through its own waitpid receipt;
there is deliberately no caller-provided 'quiescent' or 'exclusive' shortcut.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path


@dataclass
class Reservation:
    tool_use_id: str
    source_identity: dict[str, str]
    pre_returned: bool = False
    post_seen: bool = False
    command_exited: bool = False
    retained_callbacks: set[tuple[int, int]] = field(default_factory=set)
    closed_callbacks: set[tuple[int, int]] = field(default_factory=set)

    def permission_returned(self) -> None:
        self.pre_returned = True

    def observe_post(self, tool_use_id: str) -> None:
        if not tool_use_id or tool_use_id != self.tool_use_id:
            raise ValueError("Post correlation is unestablished; retain reservation")
        self.post_seen = True

    def observe_command_exit(self) -> None:
        self.command_exited = True

    def own_reaped_callback(self, identity: tuple[int, int]) -> None:
        if identity not in self.retained_callbacks:
            raise ValueError("Unknown callback identity")
        self.closed_callbacks.add(identity)

    def safe_owned_release(self) -> bool:
        return (self.pre_returned and self.post_seen and self.command_exited
                and self.retained_callbacks == self.closed_callbacks)

    def unsafe_post_only_release(self) -> bool:
        """Rejected hypothesis, retained only to execute its counterexample."""
        return self.pre_returned and self.post_seen and self.command_exited


def loaded_identity_is_current(loaded: dict[str, str], paths: dict[str, Path]) -> bool:
    if loaded.keys() != paths.keys():
        return False
    return all(hashlib.sha256(paths[name].read_bytes()).hexdigest() == digest
               for name, digest in loaded.items())


def production_release_status(*, all_actor_coverage: str,
                              native_terminal_coverage: str,
                              genuine_bootstrap: str) -> str:
    # This is a source result classifier, never a runtime admission function.
    if (all_actor_coverage, native_terminal_coverage, genuine_bootstrap) != (
            "INDEPENDENTLY_ACCEPTED", "INDEPENDENTLY_ACCEPTED", "AUTHENTIC"):
        return "SOURCE_FAIL/NOT_READY"
    return "REQUIRES_SEPARATE_INSTALLATION_AND_RUNTIME_ACCEPTANCE"
