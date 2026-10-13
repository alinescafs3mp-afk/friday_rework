"""Retain and compare the actual opened directory and named state bytes.

This is an observation fence. It cannot turn path-based PluginState.set into
compare-and-swap, prevent an uncooperative same-uid rename after the last
comparison, or atomically combine a Python return with an fsync.
"""
import hashlib
import os
from pathlib import Path
import stat


class NamedStateUnconfirmed(RuntimeError):
    pass


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid)


class NamedStateFence:
    def __init__(self, directory, *, max_bytes):
        directory = Path(directory)
        if (not directory.is_absolute() or directory.resolve() != directory
                or type(max_bytes) is not int or not 0 < max_bytes <= 4 * 1024 * 1024):
            raise NamedStateUnconfirmed("named_state_capture_not_bounded")
        self.directory = directory
        self.max_bytes = max_bytes
        self.fd = None
        self.failure = None
        self.close_started = False
        self.closed = False
        self.snapshot = None
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.fd = fd
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise NamedStateUnconfirmed("original_state_directory_not_private")
            self.birth = _directory_identity(info)
            self.check_directory()
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:
                raise BaseExceptionGroup("named_state_capture_and_close_unknown",
                                         [primary, cleanup])
            raise

    def _refuse(self, reason):
        if self.failure is None:
            self.failure = reason
        raise NamedStateUnconfirmed(reason)

    def check_directory(self):
        if self.closed or self.failure is not None:
            raise NamedStateUnconfirmed("named_state_prior_failure_or_closed")
        try:
            if (_directory_identity(os.fstat(self.fd)) != self.birth
                    or _directory_identity(os.stat(self.directory, follow_symlinks=False)) != self.birth):
                self._refuse("original_named_state_directory_replaced")
        except BaseException as exc:
            if self.failure is None:
                self.failure = type(exc).__name__
            raise

    def _read_current(self):
        self.check_directory()
        fd = os.open("state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
        primary = None
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                    or not 0 < before.st_size <= self.max_bytes):
                self._refuse("named_state_file_not_exact_private")
            data = bytearray()
            while len(data) <= before.st_size:
                chunk = os.read(fd, min(65536, before.st_size + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            named = os.stat("state.json", dir_fd=self.fd, follow_symlinks=False)
            if (len(data) != before.st_size or _file_identity(before) != _file_identity(after)
                    or _file_identity(named) != _file_identity(before)):
                self._refuse("named_state_inode_or_content_changed_during_capture")
            self.check_directory()
            return (_file_identity(before), bytes(data))
        except BaseException as exc:
            primary = exc
            if self.failure is None:
                self.failure = type(exc).__name__
            raise
        finally:
            try:
                os.close(fd)
            except BaseException as cleanup:
                self.failure = "named_state_capture_fd_close_unknown"
                if primary is not None:
                    raise BaseExceptionGroup("named_state_read_and_close_unknown",
                                             [primary, cleanup])
                raise NamedStateUnconfirmed(self.failure) from cleanup

    def capture_current_unknown(self):
        if self.snapshot is not None:
            self._refuse("named_state_unknown_capture_repeated")
        identity, body = self._read_current()
        self.snapshot = (identity, body, hashlib.sha256(body).hexdigest())
        return self.snapshot[2]

    def compare_before_commit(self):
        if self.snapshot is None:
            self._refuse("named_state_original_unknown_missing")
        identity, body = self._read_current()
        if (identity, body) != self.snapshot[:2]:
            self._refuse("named_state_unknown_generation_or_bytes_replaced")
        return self.snapshot[2]

    def sync_original_directory(self):
        # Uses the retained original directory FD, then checks the name again.
        # A writer can still race AFTER the final check; this is not atomic CAS.
        self.check_directory()
        os.fsync(self.fd)
        self.check_directory()

    def close(self):
        if self.closed:
            return
        if self.close_started:
            raise NamedStateUnconfirmed("named_state_fd_close_unknown_no_repeat")
        self.close_started = True
        try:
            os.close(self.fd)
        except BaseException as exc:
            self.failure = "named_state_directory_fd_close_unknown"
            raise NamedStateUnconfirmed(self.failure) from exc
        self.closed = True
