"""Native PluginState POSIX transaction. Prospective Source; no deadline proof.

Every state writer participates in the original thread/flock protocol. A
transaction retains its own directory, lock and old/new file descriptions.
Returned witnesses describe completed syscalls and explicit closure, never
unobserved past namespace mutation, kernel preemption or runtime Go.
"""
from dataclasses import dataclass
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
import time

META = "__friday_native_state_v1"
MAX_JOURNAL = 65536
MAX_HISTORY_ENTRIES = 4096
MAX_STATE_DIRECTORY_ENTRIES = MAX_HISTORY_ENTRIES + 3
# At most one state temporary is created by a transaction. An unresolved
# retained temporary refuses the next native transaction before another write.


class NativeCommitUncertain(RuntimeError):
    def __init__(self, primary, *, stage, replaced, facts, secondary=()):
        super().__init__("native_commit_UNKNOWN:" + stage)
        self.primary = primary
        self.secondary = tuple(secondary)
        self.stage = stage
        self.replaced = replaced
        self.facts = dict(facts)
        self.state = "UNKNOWN"


@dataclass(frozen=True, eq=False)
class DurableStateCommit:
    state: object
    namespace: str
    directory: tuple
    lock_inode: tuple
    previous_inode: tuple | None
    inode: tuple
    generation: int
    content_sha256: str
    content_bytes: int
    journal: tuple
    closed_at: float
    cutoff: float | None
    _seal: object


@dataclass(frozen=True, eq=False)
class StateCommitReturn:
    commit: DurableStateCommit
    state: object
    observed_at: float
    _seal: object


_SEAL = object()


def identity(info):
    return (info.st_dev, info.st_ino)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _private(info, mode, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != mode
            or not directory and info.st_nlink != 1):
        raise PermissionError("native_state_custody_not_private")


def observe_commit_return(state, witness, *, cutoff=None):
    """The consumer calls only AFTER set_commit has actually returned."""
    now = time.monotonic()
    if (type(witness) is not DurableStateCommit or witness._seal is not _SEAL
            or witness.state is not state
            or witness.namespace != state._data_namespace
            or witness.closed_at > now or cutoff != witness.cutoff
            or cutoff is not None and now >= cutoff):
        raise RuntimeError("native_state_actual_return_not_current")
    return StateCommitReturn(witness, state, now, _SEAL)


def require_commit_return(state, returned, *, cutoff=None):
    if (type(returned) is not StateCommitReturn or returned._seal is not _SEAL
            or returned.state is not state or returned.commit.state is not state
            or cutoff != returned.commit.cutoff
            or not returned.commit.closed_at <= returned.observed_at <= time.monotonic()
            or cutoff is not None and time.monotonic() >= cutoff):
        raise RuntimeError("foreign_or_late_native_commit_return")
    return returned.commit


class RetainedStateTransaction:
    def __init__(self, state, *, cutoff, lock_deadline, lock_budget):
        from hermes_cli.plugins_state import _thread_state_lock, _PLUGIN_STATE_LOCKS_GUARD, _PLUGIN_STATE_LOCKS
        self.state = state
        self.cutoff = cutoff
        self.lock_deadline = lock_deadline
        self.lock_budget = lock_budget
        self.directory = Path(state.data_dir)
        self.namespace = state._data_namespace
        self.path = self.directory / "state.json"
        self.dirfd = self.lockfd = self.oldfd = self.newfd = None
        self.stage = "BEFORE_OPEN"
        self.replaced = False
        self.facts = {}
        self.journals = []
        self.primary = None
        self.secondary = []
        self.thread_scope = None
        self.tempname = None
        self.data = None
        self.final_inode = None
        self.final_generation = None
        self.final_encoded = None
        self._thread_state_lock = _thread_state_lock
        from hermes_cli.plugins_state import LockAcquisitionBudget
        for value in (cutoff, lock_deadline):
            if value is not None and (type(value) not in (float, int) or not math.isfinite(value)):
                raise ValueError("native cutoff must be a finite original monotonic timestamp")
        if lock_budget is not None and (not isinstance(lock_budget, LockAcquisitionBudget) or lock_deadline is not None):
            raise ValueError("lock_budget requires original LockAcquisitionBudget without lock_deadline")

        if os.name != "posix":
            raise RuntimeError("native_commit_POSIX_required")
        if not self.directory.is_absolute() or self.directory.resolve() != self.directory:
            raise PermissionError("native_directory_alias_refused")
        with _thread_state_lock(_PLUGIN_STATE_LOCKS_GUARD, lock_deadline, lock_budget):
            self.thread_lock = _PLUGIN_STATE_LOCKS.setdefault(
                str(self.path.with_name(".state.json.lock").resolve(strict=False)),
                __import__("threading").RLock())

    def check(self):
        if self.cutoff is not None and time.monotonic() >= self.cutoff:
            raise TimeoutError("original_native_store_cutoff")
        if self.state._data_namespace != self.namespace or Path(self.state.data_dir) != self.directory:
            raise PermissionError("native_namespace_changed")
        if self.dirfd is not None:
            now = os.stat(self.directory, follow_symlinks=False)
            _private(now, 0o700, True)
            if identity(now) != self.facts["directory"] or identity(os.fstat(self.dirfd)) != identity(now):
                raise PermissionError("native_directory_changed")
        if self.lockfd is not None:
            info = os.stat(".state.json.lock", dir_fd=self.dirfd, follow_symlinks=False)
            _private(info, 0o600)
            if identity(info) != self.facts["lock_inode"]:
                raise PermissionError("native_lock_inode_changed")

    def __enter__(self):
        from hermes_cli.plugins_state import _acquisition_scope, _lock_remaining
        self.thread_scope = self._thread_state_lock(self.thread_lock, self.lock_deadline, self.lock_budget)
        self.thread_scope.__enter__()
        try:
            self.check()
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.dirfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            di = os.fstat(self.dirfd); _private(di, 0o700, True)
            self.facts["directory"] = identity(di)
            self.lockfd = os.open(".state.json.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  0o600, dir_fd=self.dirfd)
            li = os.fstat(self.lockfd); _private(li, 0o600)
            self.facts["lock_inode"] = identity(li)
            old = self.state._native_namespaces.get(str(self.directory))
            current = (self.facts["directory"], self.facts["lock_inode"])
            if old is not None and old != current:
                raise PermissionError("native_birth_namespace_or_lock_changed")
            self.state._native_namespaces[str(self.directory)] = current
            with _acquisition_scope(self.lock_deadline, self.lock_budget) as acquire_end:
                while True:
                    self.check()
                    try:
                        fcntl.flock(self.lockfd, fcntl.LOCK_EX | (fcntl.LOCK_NB if acquire_end is not None else 0))
                        break
                    except BlockingIOError:
                        if acquire_end is None:
                            raise
                        time.sleep(min(.01, _lock_remaining(acquire_end)))
            self.stage = "LOCKED"
            self.check()
            self.storage_inventory()
            try:
                self.oldfd = os.open("state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.dirfd)
            except FileNotFoundError:
                self.data = {}
                self.facts["previous_inode"] = None
            else:
                oi = os.fstat(self.oldfd); _private(oi, 0o600)
                raw = self.read_exact(self.oldfd, self.state.quota_bytes)
                oi_after = os.fstat(self.oldfd)
                named = os.stat("state.json", dir_fd=self.dirfd, follow_symlinks=False)
                if identity(named) != identity(oi) or identity(oi_after) != identity(oi) or oi_after.st_size != len(raw):
                    raise PermissionError("native_state_inode_changed")
                self.data = json.loads(raw.decode("utf-8-sig"))
                if type(self.data) is not dict:
                    raise ValueError("native_state_root_not_object")
                self.facts["previous_inode"] = identity(oi)
                self.facts["previous_sha256"] = hashlib.sha256(raw).hexdigest()
            meta = self.data.get(META, {"schema": META, "generation": 0})
            if (type(meta) is not dict or set(meta) != {"schema", "generation"}
                    or meta["schema"] != META or type(meta["generation"]) is not int
                    or meta["generation"] < 0):
                raise ValueError("native_generation_invalid")
            self.facts["previous_generation"] = meta["generation"]
            self.check()
            return self
        except BaseException as error:
            self.primary = error
            self._close()
            raise NativeCommitUncertain(error, stage=self.stage, replaced=self.replaced,
                                        facts=self.facts, secondary=self.secondary) from error

    def read_exact(self, fd, limit):
        chunks = []; size = 0
        while True:
            self.check()
            b = os.read(fd, min(65536, limit + 1 - size))
            if not b:
                return b"".join(chunks)
            chunks.append(b); size += len(b)
            if size > limit:
                raise ValueError("native_state_or_journal_quota")

    def storage_inventory(self):
        """Bound the managed namespace without deleting failed evidence."""
        self.check()
        history_names = set()
        history_bytes = 0
        temporary_names = []
        temporary_bytes = 0
        scanned = 0
        inventory_digest = hashlib.sha256()
        # Streaming iteration has a fixed bound; listdir cannot allocate an
        # arbitrary preexisting directory before the count is checked.
        with os.scandir(self.dirfd) as entries:
            for entry in entries:
                scanned += 1
                if scanned > MAX_STATE_DIRECTORY_ENTRIES:
                    raise ValueError("native_storage_directory_entry_quota")
                name = entry.name
                history = name.startswith("friday-unknown-") or name.startswith("friday-candidate-")
                temporary = name.startswith(".state.json.") and name.endswith(".tmp")
                if not history and not temporary:
                    continue
                info = os.stat(name, dir_fd=self.dirfd, follow_symlinks=False)
                _private(info, 0o400 if history else 0o600)
                limit = MAX_JOURNAL if history else self.state.quota_bytes
                if not 0 <= info.st_size <= limit:
                    raise ValueError("native_retained_storage_file_quota")
                inventory_digest.update(encoded((name, identity(info), info.st_size)))
                if history:
                    history_names.add(name)
                    history_bytes += info.st_size
                    if len(history_names) > MAX_HISTORY_ENTRIES:
                        raise ValueError("native_immutable_history_entry_quota")
                    if history_bytes > self.state.quota_bytes:
                        raise ValueError("native_immutable_history_byte_quota")
                else:
                    temporary_names.append(name)
                    temporary_bytes += info.st_size
                    if len(temporary_names) > 1 or temporary_bytes > self.state.quota_bytes:
                        raise ValueError("native_retained_temporary_quota")
        self.check()
        self.facts["native_storage_ledger"] = {
            "history_entries": len(history_names), "history_bytes": history_bytes,
            "retained_temporaries": len(temporary_names), "temporary_bytes": temporary_bytes,
            "scanned_entries": scanned, "managed_digest": inventory_digest.hexdigest(),
            "logical_bytes_bound": 3 * self.state.quota_bytes,
            "filesystem_allocation_and_namespace_history": "UNQUALIFIED",
        }
        if temporary_names:
            # No unlink/chmod/retry/lease reset to manufacture free capacity.
            # A separate exact admitted reconciliation is still required.
            raise ValueError("native_retained_temporary_UNRECONCILED_no_new_write")
        return history_names, history_bytes

    def journal(self, kind, body):
        self.check()
        if kind not in {"unknown", "candidate"} or type(body) is not bytes or len(body) > MAX_JOURNAL:
            raise ValueError("native_journal_schema_or_quota")
        digest = hashlib.sha256(body).hexdigest()
        name = "friday-" + kind + "-" + digest + ".json"
        history_names, history_bytes = self.storage_inventory()
        new_entry = name not in history_names
        if new_entry and len(history_names) >= MAX_HISTORY_ENTRIES:
            raise ValueError("native_immutable_history_entry_quota")
        if history_bytes + (len(body) if new_entry else 0) > self.state.quota_bytes:
            raise ValueError("native_immutable_history_byte_quota")
        fd = None
        error = None
        try:
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o400, dir_fd=self.dirfd)
            except FileExistsError:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.dirfd)
                _private(os.fstat(fd), 0o400)
                if self.read_exact(fd, MAX_JOURNAL) != body:
                    raise PermissionError("immutable_native_history_conflict")
            else:
                self.write_all(fd, body)
                os.fsync(fd)
            info = os.fstat(fd); _private(info, 0o400)
            os.fsync(fd)
            if identity(os.stat(name, dir_fd=self.dirfd, follow_symlinks=False)) != identity(info):
                raise PermissionError("native_journal_replaced")
        except BaseException as exc:
            error = exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except BaseException as exc:
                    if error is None:
                        error = exc
                    else:
                        self.secondary.append(exc)
        if error is not None:
            raise error
        os.fsync(self.dirfd)
        self.check()
        fact = (kind, name, identity(info), digest, len(body))
        self.journals.append(fact)
        return fact

    def write_all(self, fd, body):
        offset = 0
        evidence = {"fd": fd, "stage": self.stage, "requested_bytes": len(body), "accepted_bytes": 0}
        self.facts.setdefault("partial_writes", []).append(evidence)
        while offset < len(body):
            self.check()
            n = os.write(fd, body[offset:offset + 65536])
            if type(n) is not int or not 0 < n <= min(65536, len(body) - offset):
                raise OSError("native_state_short_write")
            offset += n
            evidence["accepted_bytes"] = offset

    def replace(self, key, value, *, expected_value=None, compare=False, journals=()):
        self.check()
        if compare and self.data.get(key) != expected_value:
            raise RuntimeError("native_current_value_compare_failed")
        for kind, body in journals:
            self.journal(kind, body)
        data = copy.deepcopy(self.data)
        if self.state._plugin_id == "friday_rework" and key == "product_access.v1":
            from hermes_cli.friday_product_access import KEY, advance_access
            value = advance_access(data.get(KEY, {"schema": KEY, "users": {}}), value)
        data[key] = value
        generation = self.facts["previous_generation"] + 1
        data[META] = {"schema": META, "generation": generation}
        body = encoded(data)
        self.facts["candidate_generation"] = generation
        self.facts["candidate_sha256"] = hashlib.sha256(body).hexdigest()
        self.facts["candidate_bytes"] = len(body)
        if len(body) > self.state.quota_bytes:
            raise ValueError("Plugin state quota exceeded")
        # Check every retained managed entry and reserve the prospective
        # single temporary before O_CREAT. History, current state and one
        # prospective temporary each stay within the original state quota.
        self.storage_inventory()
        self.tempname = ".state.json." + secrets.token_hex(16) + ".tmp"
        self.facts["temporary_name"] = self.tempname
        self.stage = "TEMP_OPEN_ENTERED_UNKNOWN"
        self.newfd = os.open(self.tempname, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=self.dirfd)
        self.stage = "TEMP_OPEN"
        self.write_all(self.newfd, body)
        ni = os.fstat(self.newfd); _private(ni, 0o600)
        self.facts["candidate_inode"] = identity(ni)
        if ni.st_size != len(body):
            raise OSError("native_temporary_size_changed")
        os.fsync(self.newfd)
        self.check()
        if self.oldfd is None:
            try:
                os.stat("state.json", dir_fd=self.dirfd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise PermissionError("native_state_appeared_during_write")
        elif identity(os.stat("state.json", dir_fd=self.dirfd, follow_symlinks=False)) != self.facts["previous_inode"]:
            raise PermissionError("native_state_compare_inode_failed")
        self.stage = "REPLACE_ENTERED_UNKNOWN"
        self.replaced = None  # entering rename cannot prove absence if it fails
        os.replace(self.tempname, "state.json", src_dir_fd=self.dirfd, dst_dir_fd=self.dirfd)
        self.replaced = True
        self.stage = "REPLACED_NOT_DURABLE"
        if identity(os.stat("state.json", dir_fd=self.dirfd, follow_symlinks=False)) != identity(ni):
            raise PermissionError("native_replaced_file_changed")
        os.lseek(self.newfd, 0, os.SEEK_SET)
        if self.read_exact(self.newfd, self.state.quota_bytes) != body:
            raise PermissionError("native_replaced_content_changed")
        os.fsync(self.dirfd)
        self.check()
        self.final_inode = identity(ni)
        self.final_generation = generation
        self.final_encoded = body
        self.stage = "DURABLE_NOT_CLOSED"

    def _close(self):
        for label in ("oldfd", "newfd", "lockfd", "dirfd"):
            fd = getattr(self, label)
            if fd is None:
                continue
            setattr(self, label, None)  # never retry a possibly recycled number
            try:
                if label == "lockfd":
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as exc:
                self.secondary.append(exc)
            try:
                os.close(fd)
            except BaseException as exc:
                self.secondary.append(exc)
        if self.thread_scope is not None:
            scope = self.thread_scope; self.thread_scope = None
            try:
                scope.__exit__(None, None, None)
            except BaseException as exc:
                self.secondary.append(exc)

    def __exit__(self, kind, error, traceback):
        if error is not None:
            self.primary = error
        # A failed temporary write remains private uncertain evidence; never
        # unlink a pathname after closure or turn rename visibility into success.
        self._close()
        if self.primary is not None or self.secondary:
            primary = self.primary if self.primary is not None else self.secondary[0]
            raise NativeCommitUncertain(primary, stage=self.stage, replaced=self.replaced,
                                        facts=self.facts, secondary=self.secondary) from primary
        if self.cutoff is not None and time.monotonic() >= self.cutoff:
            primary = TimeoutError("native_store_late_explicit_close")
            raise NativeCommitUncertain(primary, stage=self.stage, replaced=self.replaced,
                                        facts=self.facts) from primary
        return False

    def witness(self):
        if self.final_encoded is None or any(getattr(self, x) is not None for x in ("dirfd", "oldfd", "newfd", "lockfd")):
            raise RuntimeError("native_commit_not_written_or_closed")
        return DurableStateCommit(self.state, self.namespace, self.facts["directory"],
                                  self.facts["lock_inode"], self.facts["previous_inode"],
                                  self.final_inode, self.final_generation,
                                  hashlib.sha256(self.final_encoded).hexdigest(), len(self.final_encoded),
                                  tuple(self.journals), time.monotonic(), self.cutoff, _SEAL)


def set_native(state, key, value, *, cutoff=None, lock_deadline=None, lock_budget=None,
               expected_value=None, compare=False, journals=()):
    tx = RetainedStateTransaction(state, cutoff=cutoff, lock_deadline=lock_deadline, lock_budget=lock_budget)
    with tx:
        tx.replace(key, value, expected_value=expected_value, compare=compare, journals=journals)
    return tx.witness()


def get_native(state, key, default=None, *, cutoff=None, lock_deadline=None, lock_budget=None):
    tx = RetainedStateTransaction(state, cutoff=cutoff, lock_deadline=lock_deadline, lock_budget=lock_budget)
    with tx:
        result = copy.deepcopy(tx.data[key]) if key in tx.data else default
    return result
