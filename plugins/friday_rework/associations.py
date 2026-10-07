"""Small durable associations in Hermes PluginState; no executor or queue.

Every argument comes from the trusted host/controller, never a tool payload.
The controller must prove native observations and stop any known boundary even
if recording stop intent fails. This store itself cannot stop execution.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time

from .boundary import WorkBrief, parse_brief

KEY = "associations.v1"
OWNER_FIELDS = {"bot_id", "user_id", "chat_id", "thread_id", "message_id",
                "session_key", "session_id", "profile"}
ROW_FIELDS = {"existing_task_id", "admission_hash", "owner", "worker_kind",
              "brief_sha256", "workspace_reference", "supervisor",
              "created_at_unix", "budget_seconds", "deadline_unix",
              "elapsed_seconds", "submission_observation", "native",
              "stop_intent", "execution_observation", "goal_verification", "delivery",
              "preparation_reserved"}


class AssociationError(RuntimeError):
    pass


def _text(value, limit=512, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or "\x00" in value:
        raise AssociationError("invalid_reference")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise AssociationError("invalid_reference") from exc
    if size > limit:
        raise AssociationError("invalid_reference")
    return value


def _owner(value):
    if not isinstance(value, dict) or set(value) != OWNER_FIELDS:
        raise AssociationError("invalid_owner")
    return {k: _text(v, empty=k in {"thread_id", "profile"}) for k, v in value.items()}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssociationError("invalid_budget")
    try:
        valid = math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise AssociationError("invalid_budget")
    return value


def _supervisor(value):
    if (not isinstance(value, dict) or set(value) != {"scope", "unit"}
            or value["scope"] not in ("user", "system")
            or not isinstance(value["unit"], str)
            or not re.fullmatch(r"friday-rework-worker-[0-9a-f]{32}\.service", value["unit"])):
        raise AssociationError("invalid_supervisor_identity")
    return dict(value)


def _native(value):
    if not isinstance(value, dict) or set(value) != {"invocation_id", "worker_reference"}:
        raise AssociationError("invalid_native_reference")
    value = {k: _text(v, 2048) for k, v in value.items()}
    if not re.fullmatch(r"[0-9a-f]{32}", value["invocation_id"]):
        raise AssociationError("invalid_native_reference")
    return value


def _validate_store(data):
    """Reject the whole document, including unrelated damaged rows."""
    try:
        if (not isinstance(data, dict) or set(data) != {"schema_version", "jobs"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1
                or not isinstance(data["jobs"], dict)):
            raise AssociationError("invalid_association_store")
        admissions, supervisors, invocations, workers = set(), set(), set(), set()
        for task_id, row in data["jobs"].items():
            _text(task_id, 128)
            if (not isinstance(row, dict) or set(row) - {"result", "notification"} not in (ROW_FIELDS, ROW_FIELDS | {"host"})
                    or ("result" in row or "notification" in row) and "host" not in row):
                raise AssociationError("invalid_association_store")
            if "host" in row:
                from .host_record import validate_host_record
                validate_host_record(row)
            if "notification" in row:
                notice = row["notification"]
                if (not isinstance(notice, dict) or set(notice) != {"state", "at_unix"}
                        or notice["state"] not in {"UNKNOWN", "SCHEDULED", "FAILED", "OBSERVED"}
                        or row["host"]["quiescence"] is None):
                    raise AssociationError("invalid_result_notification")
                _number(notice["at_unix"])
            if _text(row["existing_task_id"], 128) != task_id:
                raise AssociationError("invalid_association_store")
            for field in ("admission_hash", "brief_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", _text(row[field], 64)):
                    raise AssociationError("invalid_association_store")
            _owner(row["owner"])
            _text(row["workspace_reference"], 2048)
            supervisor = _supervisor(row["supervisor"])
            if row["worker_kind"] not in ("dsh", "a0"):
                raise AssociationError("invalid_association_store")
            if type(row["preparation_reserved"]) is not bool:
                raise AssociationError("invalid_association_store")
            created, budget, deadline, elapsed = (
                _number(row[field]) for field in
                ("created_at_unix", "budget_seconds", "deadline_unix", "elapsed_seconds"))
            grant_end = _number(created + budget)
            if budget <= 0 or not created < deadline <= grant_end:
                raise AssociationError("invalid_association_store")
            # Over-budget observations are retained, never clamped or erased.
            submission = row["submission_observation"]
            if submission not in ("NOT_SUBMITTED", "UNKNOWN", "OBSERVED"):
                raise AssociationError("invalid_association_store")
            if row["stop_intent"] not in (None, "cancel", "pause"):
                raise AssociationError("invalid_association_store")
            if "result" in row:
                from .results import validate_result
                validate_result(row)
            elif row["goal_verification"] != "NOT_RUN" or row["delivery"] != "NOT_RUN":
                raise AssociationError("invalid_association_store")
            observation = row["execution_observation"]
            if observation is not None:
                _text(observation, 2048)
            if row["native"] is None:
                if submission == "OBSERVED" or observation is not None or elapsed != 0:
                    raise AssociationError("invalid_association_store")
            else:
                native = _native(row["native"])
                if submission != "OBSERVED" or (observation is None and elapsed != 0):
                    raise AssociationError("invalid_association_store")
                invocation = (supervisor["scope"], native["invocation_id"])
                worker = (row["worker_kind"], native["worker_reference"])
                if invocation in invocations or worker in workers:
                    raise AssociationError("invalid_association_store")
                invocations.add(invocation)
                workers.add(worker)
            boundary = (supervisor["scope"], supervisor["unit"])
            if row["admission_hash"] in admissions or boundary in supervisors:
                raise AssociationError("invalid_association_store")
            admissions.add(row["admission_hash"])
            supervisors.add(boundary)
    except AssociationError as exc:
        raise AssociationError("invalid_association_store") from exc


def _sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Associations:
    """Serializes compound operations around the native atomic get/set API.

    Threads sharing this owned store serialize short metadata operations before
    taking the nonblocking flock. Another writer still receives admission_busy;
    native preparation/control never holds either metadata lock.
    """
    def __init__(self, native_state, *, clock=time.time):
        self.state = native_state
        self.clock = clock
        self._thread_lock = threading.RLock()
        self._lock_allowance = ContextVar("association_lock_allowance", default=None)

    @contextmanager
    def lock_budget(self):
        """One cumulative acquisition allowance, excluding native work and I/O."""
        from hermes_cli.plugins_state import LockAcquisitionBudget
        budget = self._lock_allowance.get()
        token = self._lock_allowance.set(budget if budget is not None else LockAcquisitionBudget(.25))
        try:
            yield
        finally:
            self._lock_allowance.reset(token)

    def state_get(self, key, default=None):
        with self.lock_budget():
            return self.state.get(key, default, lock_budget=self._lock_allowance.get())

    def state_set(self, key, value):
        with self.lock_budget():
            self.state.set(key, value, lock_budget=self._lock_allowance.get())

    @contextmanager
    def _locked(self):
        # Unload and coroutine cancellation use the same owned store through
        # different executor threads. Their contention is not a foreign writer.
        with self.lock_budget():
            with self._lock_allowance.get().acquiring() as deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._thread_lock.acquire(timeout=remaining):
                    raise TimeoutError("association_lock_deadline")
            try:
                with self._locked_file() as data:
                    yield data
            finally:
                self._thread_lock.release()

    @contextmanager
    def _locked_file(self):
        directory = Path(self.state.data_dir)
        if not directory.is_absolute() or directory.resolve() != directory:
            raise AssociationError("unsafe_state_directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        ds = directory.stat()
        if ds.st_uid != os.getuid() or stat.S_IMODE(ds.st_mode) != 0o700:
            raise AssociationError("state_directory_not_private")
        fd = os.open(directory / "admission.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            ls = os.fstat(fd)
            if (not stat.S_ISREG(ls.st_mode) or ls.st_uid != os.getuid()
                    or ls.st_nlink != 1 or stat.S_IMODE(ls.st_mode) != 0o600):
                raise AssociationError("unsafe_admission_lock")
            try:
                with self._lock_allowance.get().acquiring():
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise AssociationError("admission_busy") from exc
            # Native PluginState opens these paths itself. They must be inside
            # this private, worker-inaccessible directory, never symlink aliases.
            for name in ("state.json", ".state.json.lock"):
                path = directory / name
                if path.is_symlink():
                    raise AssociationError("unsafe_native_state")
                if path.exists():
                    fs = path.stat()
                    if not stat.S_ISREG(fs.st_mode) or fs.st_uid != os.getuid() or fs.st_nlink != 1:
                        raise AssociationError("unsafe_native_state")
            marker = os.pread(fd, 4, 0)
            if marker not in (b"", b"v1\n"):
                raise AssociationError("invalid_admission_marker")
            missing = object()
            data = self.state_get(KEY, missing)
            if data is missing:
                if marker:
                    raise AssociationError("association_store_lost")
                data = {"schema_version": 1, "jobs": {}}
                self._save(data)
            _validate_store(data)
            if not marker:
                if os.pwrite(fd, b"v1\n", 0) != 3:
                    raise OSError("short_admission_marker_write")
            os.fsync(fd)
            # mkdir(parents=True) can create multiple directory entries. Sync
            # bottom-up on every open, including recovery after a failed first
            # initialization, before returning access or an external grant.
            for parent in (directory, *directory.parents):
                _sync_directory(parent)
            yield data
        finally:
            os.close(fd)

    def _save(self, data):
        _validate_store(data)
        self.state_set(KEY, data)
        # PluginState fsyncs its temporary file, but not the replacement's
        # directory. Keep its native writer/store; finish the commit under our
        # compound-operation lock and propagate an uncertain durability error.
        _sync_directory(Path(self.state.data_dir))

    @staticmethod
    def _owned(data, task_id, owner):
        _text(task_id, 128)
        row = data["jobs"].get(task_id)
        if not isinstance(row, dict) or row.get("owner") != _owner(owner):
            raise AssociationError("unknown_or_foreign_task")
        return row

    def claim(self, *, task_id, admission_key, owner, brief: WorkBrief,
              workspace_reference, supervisor, budget_seconds, deadline_unix, host_binding=None,
              acceptance=None):
        """Save trusted launch intent. Duplicate input returns the old grant.

        A replay with a later deadline cannot replenish its original budget.
        Different content/ownership under an old admission key is rejected.
        """
        task_id = _text(task_id, 128)
        admission_hash = hashlib.sha256(_text(admission_key, 2048).encode()).hexdigest()
        owner = _owner(owner)
        brief = parse_brief(vars(brief))
        workspace_reference = _text(workspace_reference, 2048)
        identity = {"owner": owner, "worker_kind": brief.worker,
                    "brief_sha256": hashlib.sha256(json.dumps(vars(brief), sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    "workspace_reference": workspace_reference,
                    "supervisor": _supervisor(supervisor)}
        budget_seconds = _number(budget_seconds)
        deadline_unix = _number(deadline_unix)
        with self._locked() as data:
            for old_id, row in data["jobs"].items():
                if not isinstance(row, dict):
                    raise AssociationError("invalid_association_store")
                if old_id == task_id or row.get("admission_hash") == admission_hash:
                    if row.get("admission_hash") != admission_hash or any(row.get(k) != v for k, v in identity.items()):
                        raise AssociationError("admission_conflict")
                    if host_binding is not None and row.get("host", {}).get("binding") != host_binding:
                        raise AssociationError("admission_conflict")
                    return copy.deepcopy(row), False
                if row.get("supervisor") == identity["supervisor"]:
                    raise AssociationError("supervisor_already_owned")
            if host_binding is not None and any(
                    row.get("host", {}).get("quiescence") is None for row in data["jobs"].values()):
                raise AssociationError("worker_capacity_reserved")
            now = _number(self.clock())
            if acceptance is not None:
                from .host_record import validate_acceptance
                validate_acceptance(acceptance)
                if (brief.worker != 'a0' or host_binding is None
                        or acceptance['accepted_monotonic_ns'] > time.monotonic_ns()
                        or acceptance['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                        or not acceptance['accepted_unix'] <= now < deadline_unix
                        or deadline_unix != acceptance['accepted_unix'] + budget_seconds):
                    raise AssociationError('invalid_original_acceptance')
                now = acceptance['accepted_unix']
            if budget_seconds <= 0 or deadline_unix <= now or deadline_unix > now + budget_seconds:
                raise AssociationError("invalid_deadline")
            row = {"existing_task_id": task_id, "admission_hash": admission_hash, **identity,
                   "created_at_unix": now, "budget_seconds": budget_seconds,
                   "deadline_unix": deadline_unix, "elapsed_seconds": 0,
                   "submission_observation": "NOT_SUBMITTED", "native": None,
                   "preparation_reserved": False,
                   "stop_intent": None, "execution_observation": None,
                   "goal_verification": "NOT_RUN", "delivery": "NOT_RUN"}
            if host_binding is not None:
                row["host"] = {"binding": copy.deepcopy(host_binding), "inputs": None,
                               "observation": None, "terminal": None, "quiescence": None}
                if brief.worker == 'a0':
                    if acceptance is None:
                        raise AssociationError('original_acceptance_missing')
                    row['host']['a0'] = {'schema': 'friday.a0.host.v2',
                        'acceptance': copy.deepcopy(acceptance),
                        'expected_files': copy.deepcopy(host_binding['runtime']['a0']['expected_files']),
                        'launch': None, 'grant': None, 'key_cleanup': 'NOT_PREPARED', 'capability': None,
                        'observations': {'pending': False, 'samples': []}}
            data["jobs"][task_id] = row
            self._save(data)
            return copy.deepcopy(row), True

    def snapshot(self):
        """Checked profile snapshot; callers still enforce ownership per control."""
        with self._locked() as data:
            return copy.deepcopy(data["jobs"])

    def attach_a0_capability(self, task_id, owner, pin, validate):
        """Once-only trusted producer attachment in the existing durable row.

        Persisted attachment consumes dispatch before scheduling. Lost schedule
        acknowledgement/restart cannot acquire a second dispatch or reset clocks.
        """
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            a = row['host']['a0']
            if a['capability'] is not None:
                if a['capability'] != pin: raise AssociationError('a0_capability_conflict')
                return copy.deepcopy(row), False
            if (row['stop_intent'] or row['preparation_reserved'] or row['native'] is not None
                    or row['submission_observation'] != 'NOT_SUBMITTED'
                    or row['host']['terminal'] is not None or row['host']['quiescence'] is not None
                    or row['host']['inputs'] is None or a['launch'] is not None):
                raise AssociationError('a0_capability_attachment_not_admitted')
            validate(copy.deepcopy(row), copy.deepcopy(pin))
            a['capability'] = copy.deepcopy(pin)
            self._save(data)
            return copy.deepcopy(row), True

    def a0_observation(self, task_id, owner, sample=None):
        """Persist intent before sampling and the full sample before acknowledging it.

        An interrupted sample stays pending across a host restart. Never reset
        that uncertainty or replace a missing legacy record with an empty list.
        """
        from .host_record import validate_a0_observations
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            a0 = row['host']['a0']
            observations = a0.get('observations')
            if observations is None or (a0['launch'] or {}).get('created') is None:
                raise AssociationError('a0_observation_ownership_unknown')
            if sample is None:
                if observations['pending']:
                    raise AssociationError('a0_observation_requires_reconciliation')
                observations['pending'] = True
            else:
                if not observations['pending']:
                    raise AssociationError('a0_observation_not_reserved')
                validate_a0_observations({'pending': False, 'samples': [sample]},
                                        a0['launch']['created']['container_id'])
                observations['samples'].append(copy.deepcopy(sample))
                observations['pending'] = False
            self._save(data)
            return copy.deepcopy(observations)

    def retain_a0(self, task_id, owner, field, value):
        """One-way nonsecret ownership metadata, in the existing locked row."""
        if field not in {'launch', 'grant', 'keys_prepared_monotonic', 'key_cleanup', 'created'}:
            raise AssociationError('invalid_a0_retention')
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            a0 = row['host']['a0']
            target = a0['launch'] if field in {'keys_prepared_monotonic', 'created'} else a0
            if target is None:
                raise AssociationError('missing_a0_launch')
            if field == 'key_cleanup':
                allowed = {'NOT_PREPARED': {'PREPARED', 'RECONCILIATION_REQUIRED'}, 'PREPARED': {'REMOVED', 'RECONCILIATION_REQUIRED'},
                           'RECONCILIATION_REQUIRED': set(), 'REMOVED': set()}
                if value != target[field] and value not in allowed[target[field]]:
                    raise AssociationError('a0_retention_conflict')
            elif target[field] is not None and target[field] != value:
                raise AssociationError('a0_retention_conflict')
            target[field] = copy.deepcopy(value)
            self._save(data)
            return copy.deepcopy(row)

    def retain_inputs(self, task_id, owner, inputs):
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            if "host" not in row or row["host"]["inputs"] is not None or row["preparation_reserved"]:
                raise AssociationError("inputs_already_retained_or_unowned")
            row["host"]["inputs"] = copy.deepcopy(inputs)
            self._save(data)
            return copy.deepcopy(row)

    def retain_outcome(self, task_id, owner, *, observation=None, terminal=None, quiescence=None):
        """First terminal truth is immutable; UNKNOWN alone never releases capacity."""
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            if "host" not in row:
                raise AssociationError("missing_host_binding")
            if observation is not None and row["host"]["terminal"] is None:
                row["host"]["observation"] = copy.deepcopy(observation)
            for key, value in (("terminal", terminal), ("quiescence", quiescence)):
                if value is not None and row["host"][key] is None:
                    row["host"][key] = copy.deepcopy(value)
            self._save(data)
            return copy.deepcopy(row)

    def get(self, task_id, owner):
        with self._locked() as data:
            return copy.deepcopy(self._owned(data, task_id, owner))

    def get_for_control(self, task_id, principal):
        """Resolve a new authorized control message to the original owner.

        The trusted gateway supplies the authenticated principal. A new
        message/session never changes the retained delivery destination.
        """
        fields = {"bot_id", "user_id", "chat_id", "thread_id", "profile"}
        if not isinstance(principal, dict) or set(principal) != fields:
            raise AssociationError("invalid_control_principal")
        principal = {k: _text(v, empty=k in {"thread_id", "profile"}) for k, v in principal.items()}
        _text(task_id, 128)
        with self._locked() as data:
            row = data["jobs"].get(task_id)
            if (not isinstance(row, dict) or not isinstance(row.get("owner"), dict)
                    or any(row["owner"].get(k) != v for k, v in principal.items())):
                raise AssociationError("unknown_or_foreign_task")
            return copy.deepcopy(row)

    def begin_submission(self, task_id, owner):
        """Persist uncertainty BEFORE the external native submission call."""
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            if (row["stop_intent"] is not None or row["deadline_unix"] <= _number(self.clock())
                    or row["elapsed_seconds"] >= row["budget_seconds"]):
                raise AssociationError("submission_stopped_or_expired")
            if row["submission_observation"] != "NOT_SUBMITTED":
                raise AssociationError("submission_requires_reconciliation")
            row["submission_observation"] = "UNKNOWN"
            self._save(data)
            return copy.deepcopy(row)

    def attach_native(self, task_id, owner, native):
        """Record real identity after submission; retain any concurrent stop."""
        native = _native(native)
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            if row["submission_observation"] != "UNKNOWN" or row["native"] is not None:
                raise AssociationError("native_reference_conflict")
            row["native"] = native
            row["submission_observation"] = "OBSERVED"
            self._save(data)
            # Caller must immediately stop this identity if stop_intent exists;
            # persisting identity is not authority for another effect.
            return copy.deepcopy(row)

    def request_stop(self, task_id, owner, intent):
        if intent not in ("cancel", "pause"):
            raise AssociationError("invalid_stop_intent")
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            if row["stop_intent"] != "cancel":
                row["stop_intent"] = intent
            self._save(data)
            return copy.deepcopy(row)

    def observe(self, task_id, owner, *, native, evidence_reference, elapsed_seconds):
        """Store an evidence reference, never infer completion/quiescence."""
        evidence_reference = _text(evidence_reference, 2048)
        elapsed_seconds = _number(elapsed_seconds)
        with self._locked() as data:
            row = self._owned(data, task_id, owner)
            if row["native"] is None or native != row["native"]:
                raise AssociationError("native_reference_conflict")
            row["elapsed_seconds"] = max(row["elapsed_seconds"], elapsed_seconds)
            row["execution_observation"] = evidence_reference
            self._save(data)
            return copy.deepcopy(row)
