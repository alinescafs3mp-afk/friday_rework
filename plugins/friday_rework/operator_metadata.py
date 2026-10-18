"""Scope-local verified operator access to the native metadata store.

This authority cannot admit an ordinary user or authorize a different store.
The native transaction still owns locks, generation, comparison and custody.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import time


_CURRENT = ContextVar("friday_onboarding_metadata", default=None)


class _OperatorMetadata:
    def __init__(self, onboarding, profile, session, root, state, expected_paths=None, *, read_only=False):
        from hermes_cli.dashboard_auth.registry import get_provider

        selected, paths = preflight_operator_metadata(onboarding, profile, session, state,
                                                       read_only=read_only)
        if Path(root) != selected:
            raise PermissionError("foreign_operator_metadata_authority")
        self._expected_paths(expected_paths or {})
        onboarding._verify_operator(profile, session)
        if _CURRENT.get() is not None:
            raise PermissionError("operator_metadata_authority_required")
        self.onboarding, self.admin = onboarding, onboarding.admin
        self._read_only = read_only
        self.profile, self.session, self.root, self.state = profile, session, Path(root), state
        self.launch = Path(self.admin.launch_home)
        self.session_values = tuple(vars(session).items())
        self.namespace = state._data_namespace
        self.provider = get_provider(session.provider, scope=str(self.launch))
        self.target_homes = {}
        self.directory = self.root / "plugin-data" / self.namespace
        self.paths = {path: identity for path, (identity, directory, _) in paths.items() if directory}
        lock = self.directory / ".state.json.lock"
        if lock in paths:
            self.lock_identity = paths[lock][0]
        self._verify()
        if self.read_only:
            # A read request may borrow an existing verified native namespace,
            # never initialize or repair it through PluginState.data_dir.
            current = (self.paths[self.directory], self.lock_identity)
            prior = state._native_namespaces.get(str(self.directory))
            if prior is not None and prior != current:
                raise PermissionError("foreign_operator_metadata_state")
            state._native_namespaces[str(self.directory)] = current
            self._read_birth = current
        # Writable onboarding may initialize only after native verification.
        if Path(state.data_dir) != self.directory:
            raise PermissionError("foreign_operator_metadata_state")
        self.paths = {path: self._identity(self._private(path, directory=True))
                      for path in (self.launch, self.root, self.directory.parent, self.directory)}
        lock = self.directory / ".state.json.lock"
        self.lock_identity = self._identity(self._private(lock, mode=0o600))
        self.active = True
        self.token = _CURRENT.set(self)

    @staticmethod
    def _identity(info):
        return info.st_dev, info.st_ino

    @staticmethod
    def _private(path, *, directory=False, mode=None):
        from hermes_cli import friday_user_scope as users

        info = users._private(path, directory=directory)
        if mode is not None and stat.S_IMODE(info.st_mode) != mode:
            raise PermissionError("operator_metadata_custody_changed")
        return info

    @classmethod
    def _expected_paths(cls, paths):
        for path, (identity, directory, mode) in paths.items():
            if cls._identity(cls._private(path, directory=directory, mode=mode)) != identity:
                raise PermissionError("operator_metadata_directory_changed")

    def _custody(self):
        if self.session.expires_at <= time.time():
            raise PermissionError("verified_admin_required")
        if (tuple(vars(self.session).items()) != self.session_values
                or self.state._plugin_id != "friday_rework"
                or self.state._data_namespace != self.namespace):
            raise PermissionError("foreign_operator_metadata_authority")
        for path, identity in self.paths.items():
            mode = 0o700 if path in (self.directory.parent, self.directory) else None
            if self._identity(self._private(path, directory=True, mode=mode)) != identity:
                raise PermissionError("operator_metadata_directory_changed")
        if hasattr(self, "lock_identity"):
            lock = self._private(self.directory / ".state.json.lock", mode=0o600)
            if self._identity(lock) != self.lock_identity:
                raise PermissionError("operator_metadata_lock_changed")
        if (hasattr(self, "_read_birth")
                and self.state._native_namespaces.get(str(self.directory)) != self._read_birth):
            raise PermissionError("foreign_operator_metadata_state")

    def _verify(self, *, metadata=True):
        from hermes_cli import friday_user_scope as users
        from hermes_cli.dashboard_auth.registry import get_provider
        from hermes_cli.profiles import get_profile_dir
        from hermes_constants import (get_hermes_home, get_process_hermes_home,
                                      get_routing_process_hermes_home)
        from .admin_controls import prove_operator

        if self.session.expires_at <= time.time():
            raise PermissionError("verified_admin_required")
        if (users._CURRENT.get() is not None or self.onboarding.admin is not self.admin
                or Path(self.admin.launch_home) != self.launch
                or get_process_hermes_home() != self.launch
                or metadata and get_hermes_home() != self.root
                or get_routing_process_hermes_home() != self.root
                or get_profile_dir(self.profile) != self.root
                or self.root.resolve() != self.root or self.launch.resolve() != self.launch
                or tuple(vars(self.session).items()) != self.session_values
                or self.state._plugin_id != "friday_rework"
                or self.state._data_namespace != self.namespace
                or self.provider is None):
            raise PermissionError("foreign_operator_metadata_authority")
        # Native config readers may persist a known-good backup. A retained
        # authority must refuse changed custody before any config/provider read.
        self._custody()
        home = get_hermes_home()
        target_identity = None
        if not metadata and home != self.root:
            if home.resolve() != home:
                raise PermissionError("foreign_operator_onboarding_home")
            target_identity = self._identity(self._private(home, directory=True))
            if home in self.target_homes and self.target_homes[home] != target_identity:
                raise PermissionError("operator_onboarding_home_changed")
        if get_provider(self.session.provider, scope=str(self.launch)) is not self.provider:
            raise PermissionError("foreign_operator_metadata_authority")
        self.admin._verify_session(self.profile, self.session)
        verified = prove_operator(self.session.provider, self.session.access_token,
                                  self.launch, self.profile)
        security = ("provider", "user_id", "org_id", "access_token", "expires_at")
        if (any(getattr(verified, key) != getattr(self.session, key) for key in security)
                or get_provider(self.session.provider, scope=str(self.launch)) is not self.provider):
            raise PermissionError("foreign_operator_metadata_session")
        self._custody()
        # Provider verification can wait. Check the complete native context
        # again before returning authority to the reader or writer.
        if (users._CURRENT.get() is not None or self.onboarding.admin is not self.admin
                or Path(self.admin.launch_home) != self.launch
                or get_process_hermes_home() != self.launch
                or get_routing_process_hermes_home() != self.root
                or get_profile_dir(self.profile) != self.root
                or get_provider(self.session.provider, scope=str(self.launch)) is not self.provider):
            raise PermissionError("foreign_operator_metadata_authority")
        if metadata and get_hermes_home() != self.root:
            raise PermissionError("foreign_operator_metadata_authority")
        if not metadata and get_hermes_home() != self.root:
            from hermes_constants import get_default_hermes_root
            policy = users.policy(self.root)
            matches = [] if policy is None else [binding for binding in policy["bindings"]
                if get_default_hermes_root(home=self.root) / "profiles" / binding["runtime_profile"] == home]
            if len(matches) != 1 or get_hermes_home() != home:
                raise PermissionError("foreign_operator_onboarding_home")
            if self._identity(self._private(home, directory=True)) != target_identity:
                raise PermissionError("operator_onboarding_home_changed")
            self.target_homes[home] = target_identity

    def _context(self):
        if not self.active or _CURRENT.get() is not self:
            raise PermissionError("expired_operator_metadata_authority")
        # Token.reset is bound to the actual Context, unlike a copied ContextVar
        # value. A foreign copy cannot consume this token or revoke its owner.
        try:
            _CURRENT.reset(self.token)
        except (ValueError, RuntimeError):
            raise PermissionError("operator_metadata_original_context_required") from None
        self.token = _CURRENT.set(self)

    def check(self, state):
        self._context()
        if (state is not self.state or state._plugin_id != "friday_rework"
                or state._data_namespace != self.namespace):
            raise PermissionError("foreign_operator_metadata_state")
        self._verify()
        # Check path custody before evaluating PluginState.data_dir: its first
        # access can initialize/tighten metadata, which must never repair drift.
        if Path(state.data_dir) != self.directory:
            raise PermissionError("foreign_operator_metadata_state")

    @property
    def read_only(self):
        return self._read_only

    def require_write(self):
        self._context()
        if self.read_only:
            raise PermissionError("readonly_operator_metadata_authority")

    @contextmanager
    def transaction(self, state, budget):
        from hermes_cli.friday_native_state import RetainedStateTransaction

        authority = self

        class OperatorTransaction(RetainedStateTransaction):
            def __enter__(self):
                if not authority.read_only:
                    return super().__enter__()
                return self._enter_read_only()

            def _enter_read_only(self):
                # Keep the native transaction's retained descriptors, lock,
                # inventory, bounded reads and cleanup. The read variant opens
                # only existing names: no mkdir or O_CREAT, including races.
                from hermes_cli.friday_native_state import NativeCommitUncertain

                self.thread_scope = self._thread_state_lock(self.thread_lock, self.lock_deadline, self.lock_budget)
                self.thread_scope.__enter__()
                try:
                    self.check()
                    self._open_read_only()
                    self._acquire_read_only()
                    self.stage = "LOCKED"
                    self.check()
                    self.storage_inventory()
                    self._load_read_only()
                    self.check()
                    return self
                except BaseException as error:
                    self.primary = error
                    self._close()
                    raise NativeCommitUncertain(error, stage=self.stage, replaced=self.replaced,
                                                facts=self.facts, secondary=self.secondary) from error

            def _open_read_only(self):
                from hermes_cli.friday_native_state import _private, identity
                self.dirfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                di = os.fstat(self.dirfd); _private(di, 0o700, True)
                self.facts["directory"] = identity(di)
                _private(os.stat(".state.json.lock", dir_fd=self.dirfd, follow_symlinks=False), 0o600)
                self.lockfd = os.open(".state.json.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                                      dir_fd=self.dirfd)
                li = os.fstat(self.lockfd); _private(li, 0o600)
                self.facts["lock_inode"] = identity(li)
                current = (self.facts["directory"], self.facts["lock_inode"])
                if self.state._native_namespaces.get(str(self.directory)) != current:
                    raise PermissionError("native_birth_namespace_or_lock_changed")

            def _acquire_read_only(self):
                from hermes_cli.plugins_state import _acquisition_scope, _lock_remaining
                import fcntl
                with _acquisition_scope(self.lock_deadline, self.lock_budget) as acquire_end:
                    while True:
                        self.check()
                        try:
                            fcntl.flock(self.lockfd, fcntl.LOCK_EX | (fcntl.LOCK_NB if acquire_end is not None else 0))
                            return
                        except BlockingIOError:
                            if acquire_end is None:
                                raise
                            time.sleep(min(.01, _lock_remaining(acquire_end)))

            def _load_read_only(self):
                from hermes_cli.friday_native_state import META, _private
                try:
                    _private(os.stat("state.json", dir_fd=self.dirfd, follow_symlinks=False), 0o600)
                except FileNotFoundError:
                    self.data = {}
                    self.facts["previous_inode"] = None
                else:
                    self.oldfd = os.open("state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                                         dir_fd=self.dirfd)
                    self._load_existing_read_only()
                meta = self.data.get(META, {"schema": META, "generation": 0})
                if (type(meta) is not dict or set(meta) != {"schema", "generation"}
                        or meta["schema"] != META or type(meta["generation"]) is not int or meta["generation"] < 0):
                    raise ValueError("native_generation_invalid")
                self.facts["previous_generation"] = meta["generation"]

            def _load_existing_read_only(self):
                from hermes_cli.friday_native_state import _private, identity
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

            def check(self):
                authority.check(self.state)
                super().check()

            def replace(self, *args, **kwargs):
                authority.require_write()
                return super().replace(*args, **kwargs)

            def journal(self, *args, **kwargs):
                authority.require_write()
                return super().journal(*args, **kwargs)

            def write_all(self, *args, **kwargs):
                authority.require_write()
                return super().write_all(*args, **kwargs)

        self.check(state)
        with OperatorTransaction(state, cutoff=None, lock_deadline=None, lock_budget=budget) as native:
            yield native
        self.check(state)

    def get(self, state, key, default, budget):
        self.check(state)
        state._validate_key(key)
        with self.transaction(state, budget) as native:
            return copy.deepcopy(native.data[key]) if key in native.data else default

    def set(self, state, key, value, budget, *, expected_value=None, compare=False):
        from hermes_cli.friday_native_state import META, observe_commit_return

        self.check(state)
        self.require_write()
        state._validate_key(key)
        if key == META:
            raise ValueError("native state generation is reserved")
        with self.transaction(state, budget) as native:
            native.replace(key, value, expected_value=expected_value, compare=compare)
        return observe_commit_return(state, native.witness())

    def close(self):
        self.active = False
        _CURRENT.reset(self.token)


def preflight_operator_metadata(onboarding, profile, session, state, *, read_only=False):
    """Read-only shape/custody checks before a config reader can make backups."""
    from hermes_cli import friday_user_scope as users
    from hermes_cli.dashboard_auth.base import Session
    from hermes_cli.plugins_state import PluginState, _plugin_data_namespace
    from hermes_cli.friday_product_access import profile_name
    from hermes_cli.profiles import get_profile_dir
    from hermes_constants import (get_hermes_home, get_process_hermes_home,
                                  get_routing_process_hermes_home)

    if users._CURRENT.get() is not None:
        raise PermissionError("operator_source_scope_required")
    if _CURRENT.get() is not None:
        raise PermissionError("operator_metadata_authority_required")
    if (type(session) is not Session or type(session.expires_at) not in (int, float)
            or session.expires_at <= time.time()):
        raise PermissionError("verified_admin_required")
    profile_name(profile)
    root, launch = get_profile_dir(profile), Path(onboarding.admin.launch_home)
    if (type(state) is not PluginState or state._plugin_id != "friday_rework"
            or state._data_namespace != _plugin_data_namespace("friday_rework", "")
            or get_hermes_home() != root or get_process_hermes_home() != launch
            or get_routing_process_hermes_home() != root):
        raise PermissionError("operator_metadata_authority_required")
    planned = root / "plugin-data" / state._data_namespace
    paths = {}
    for path in (launch, root, planned.parent, planned):
        if path.resolve() != path:
            raise PermissionError("operator_metadata_directory_alias")
        mode = 0o700 if path in (planned.parent, planned) else None
        if path in (launch, root) or path.exists() or path.is_symlink():
            info = _OperatorMetadata._private(path, directory=True, mode=mode)
            paths[path] = (_OperatorMetadata._identity(info), True, mode)
    for name in ("state.json", ".state.json.lock"):
        path = planned / name
        if path.exists() or path.is_symlink():
            info = _OperatorMetadata._private(path, mode=0o600)
            if name == ".state.json.lock":
                paths[path] = (_OperatorMetadata._identity(info), False, 0o600)
    if read_only and any(path not in paths for path in (planned.parent, planned, planned / ".state.json.lock")):
        raise PermissionError("operator_metadata_read_store_missing")
    return root, paths


@contextmanager
def operator_metadata(onboarding, profile, session, root, state, *, expected_paths=None):
    authority = _OperatorMetadata(onboarding, profile, session, root, state, expected_paths)
    try:
        yield authority
    finally:
        authority.close()


@contextmanager
def operator_metadata_read(onboarding, profile, session, root, state, *, expected_paths=None):
    """Verified request metadata reads; never a writable onboarding authority."""
    authority = _OperatorMetadata(onboarding, profile, session, root, state,
                                  expected_paths, read_only=True)
    try:
        yield authority
        authority.check(state)
    finally:
        authority.close()


def require_operator_write():
    """An active read request cannot be reused by a product write entrypoint."""
    authority = _CURRENT.get()
    if authority is not None:
        authority.require_write()


def verify_active_operator(onboarding, profile, session):
    """Keep existing per-write checks current during deliberate target-home scopes."""
    authority = _CURRENT.get()
    if authority is None:
        return
    authority.require_write()
    if (authority.onboarding is not onboarding or authority.profile != profile
            or authority.session is not session):
        raise PermissionError("foreign_operator_metadata_authority")
    authority._context()
    # This check grants no store access. Native onboarding temporarily enters a
    # prepared user's home to write its config; metadata checks still require
    # the exact original root and exact native state.
    authority._verify(metadata=False)
