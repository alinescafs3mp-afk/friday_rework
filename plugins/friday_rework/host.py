"""Hermes-owned scheduling around Associations -> Controller -> native DSH.

One admitted association reserves capacity. This module owns no pool, queue,
daemon, model call or retry engine. Native systemd deadlines survive the gateway.
"""
from __future__ import annotations

import asyncio
import copy
from contextvars import copy_context
from dataclasses import asdict, replace
import time
import json
import logging
from pathlib import Path

from .admission import _snapshot, delivery_route
from .adapters.contract import NativeObservation, VerifiedInput
from .associations import AssociationError, _native, _sync_directory
from .boundary import bound_owner, parse_brief
from .controller import Controller
from .host_record import association_address, owner_from_ingress, quiescence_record
from .host_runtime import HostUnavailable, check_runtime, dsh_binding, a0_binding, private_directory
from .inputs import stage_inputs
from .supervision import NativeSupervisor, UnitObservation

PRINCIPAL = ("bot_id", "user_id", "chat_id", "thread_id", "profile")


def status(row):
    host = row["host"]
    return {"accepted": True, "reference": row["existing_task_id"], "worker": row["worker_kind"],
            "submission": row["submission_observation"], "stop_intent": row["stop_intent"],
            "execution": (host["terminal"] or host["observation"] or {"state": "unresolved"})["state"],
            "quiescent": host["quiescence"] is not None,
            "goal_verification": row["goal_verification"], "delivery": row["delivery"],
            "deadline_unix": row["deadline_unix"], "elapsed_seconds": row["elapsed_seconds"]}


class WorkerHost:
    def __init__(self, ctx, admission):
        self.ctx, self.admission = ctx, admission
        self.store = admission.associations
        self._state_directory = Path(self.store.state.data_dir)
        # Cached *checked* associations permit emergency stop after store damage.
        # They are not an admission authority, task database or execution queue.
        self._owned = {}
        self._a0_controllers = {}
        self._a0_admissions = set()
        self._closed = False
        self._cleanup_future = None

    def _controller(self, row):
        if row['worker_kind'] == 'a0':
            from .adapters.a0 import A0Controller
            from .adapters.dsh import _identity
            address = row['existing_task_id']
            old = self._a0_controllers.get(address)
            if old is not None:
                old.bindings['a0'].adapter._same(row)
                return old
            binding = a0_binding(row['host']['binding']['runtime'], self.store, row)
            controller = A0Controller(self.store, {'a0': binding})
            controller = self._a0_controllers.setdefault(address, controller)
            controller.bindings['a0'].adapter._same(row)
            return controller
        return Controller(self.store, {"dsh": dsh_binding(row["host"]["binding"]["runtime"], self.store)})

    def handle(self, args, **kwargs):
        try:
            if Path(self.store.state.data_dir) != self._state_directory:
                raise HostUnavailable("foreign_runtime_home")
            brief = parse_brief(args)
            owner = bound_owner(session_id=kwargs.get("session_id"))
            ingress, correlation = self.admission.match(
                owner, task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id"))
        except (ValueError, RuntimeError, OSError):
            return json.dumps({"accepted": False, "error": "unproved_admission"})
        if brief.worker not in {'dsh', 'a0'}:
            return json.dumps({"accepted": False, "error": "worker_not_admitted"})
        row = None
        try:
            if (self._closed or correlation["task_id"] != correlation["session_id"]
                    or Path(self.store.state.data_dir) != self._state_directory):
                raise HostUnavailable("worker_not_available")
            address = association_address(correlation, ingress)
            old = self.store.snapshot().get(address)
            if old is not None:
                # Exact duplicate is read-only: no budget reset, preparation,
                # new scheduler task, cache restaging or implicit continuation.
                binding = old.get("host", {}).get("binding", {})
                if (binding.get("correlation") != correlation or binding.get("ingress") != ingress
                        or binding.get("brief") != vars(brief)):
                    raise AssociationError("admission_conflict")
                return json.dumps(status(old))
            configured = self.ctx.get_config("runtime")
            if not isinstance(configured, dict) or configured.get("enabled") is not True:
                return json.dumps({"accepted": False, "error": "worker_not_admitted"})
            if any(not callable(getattr(self.ctx, api, None))
                   for api in ("get_command_context", "schedule_gateway_work")):
                raise HostUnavailable("worker_not_available")
            runtime = check_runtime(configured, self.store)
            if ('a0' in runtime) != (brief.worker == 'a0'):
                raise HostUnavailable('worker_runtime_mismatch')
            if runtime["runtime_profile"] != ingress["runtime_profile"]:
                raise HostUnavailable("runtime_profile_mismatch")
            route = delivery_route(ingress)
            owner = owner_from_ingress(correlation, ingress)
            acceptance = None
            if brief.worker == 'a0':
                acceptance = {'accepted_unix': self.store.clock(), 'accepted_monotonic_ns': time.monotonic_ns(),
                              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
            row, fresh = self.store.claim(
                task_id=address, admission_key=address, owner=owner, brief=brief,
                workspace_reference=str(Path(runtime["workspace_root"]) / address),
                supervisor={"scope": "user", "unit": "friday-rework-worker-" + address[7:39] + ".service"},
                budget_seconds=runtime["budget_seconds"],
                deadline_unix=(acceptance['accepted_unix'] if acceptance else self.store.clock()) + runtime["budget_seconds"],
                acceptance=acceptance,
                host_binding={"correlation": correlation, "ingress": ingress,
                              "brief": vars(brief), "runtime": runtime})
            if not fresh:
                return json.dumps(status(row))
            self._owned[address] = copy.deepcopy(row)
            if brief.worker == 'a0': self._a0_admissions.add(address)
            # No fallback to a shared directory, no clobber of earlier artifacts.
            workspace = Path(row["workspace_reference"])
            staging = Path(runtime["staging_root"]) / address
            for directory in (workspace, staging):
                private_directory(directory.parent)
                directory.mkdir(mode=0o700)
                private_directory(directory)
                _sync_directory(directory.parent)
            inputs = stage_inputs(
                matched_ingress=ingress, admitted_reference="association:" + address + "#ingress",
                cache_roots=runtime["cache_roots"], staging_root=staging,
                worker_input_root="/job-input/verified", max_file_bytes=runtime["max_file_bytes"],
                max_total_bytes=runtime["max_total_bytes"])
            if brief.worker == 'a0':
                from .adapters.a0 import input_path
                if len(inputs) > 16 or sum(v.size_bytes for v in inputs) > runtime['max_file_bytes']:
                    raise HostUnavailable('a0_input_limit')
                inputs = tuple(replace(v,worker_path=input_path(row,i)) for i,v in enumerate(inputs))
            row = self.store.retain_inputs(address, owner, [asdict(item) for item in inputs])
            self._owned[address] = copy.deepcopy(row)
            # A0 reserves immutable clocks/identity first. A separately authorized
            # current producer attaches once, then uses this existing scheduler.
            if brief.worker != 'a0':
                self.ctx.schedule_gateway_work(self._run(row), route=route, name="friday:" + address)
            return json.dumps(status(row))
        except (ValueError, RuntimeError, OSError, TypeError):
            # Any admitted partial setup remains reserved and non-replayable.
            # Explicit stop can withdraw an unsubmitted row. Never claim queued
            # execution when scheduling or input verification failed.
            answer = {"accepted": False, "error": "worker_not_available"}
            if row is not None:
                answer["reference"] = row["existing_task_id"]
            return json.dumps(answer)

    def attach_a0_capability(self, task_id, owner, pin):
        """Host/operator-only entry; never exported as a worker/model tool.

        Current producer receives the already reserved row. A restored host is
        stop-only: it cannot redispatch a precrash reservation or attachment.
        """
        if self._closed or task_id not in self._a0_admissions:
            raise HostUnavailable('a0_attachment_requires_current_owner')
        row = self.store.get(task_id, owner)
        runtime = row['host']['binding']['runtime']
        if row['worker_kind'] != 'a0' or self.ctx.get_config('runtime') != runtime:
            raise HostUnavailable('foreign_a0_runtime_binding')
        session = self._controller(row).bindings['a0'].adapter
        row, fresh = self.store.attach_a0_capability(task_id, owner, pin, session.validate_capability)
        self._remember(row)
        if fresh:
            self.ctx.schedule_gateway_work(self._run(row), route=delivery_route(row['host']['binding']['ingress']),
                                           name='friday:'+task_id)
        return status(row)

    def _remember(self, row):
        self._owned[row["existing_task_id"]] = copy.deepcopy(row)
        return row

    def _settle(self, row, observation):
        # Controller already checked this observation. Keep its exact invocation
        # locally before host storage can fail, including after a recovered call.
        row = copy.deepcopy(row)
        if isinstance(observation, NativeObservation) and observation.invocation_id and observation.worker_reference:
            native = _native({"invocation_id": observation.invocation_id,
                              "worker_reference": observation.worker_reference})
            if row["native"] is not None and row["native"] != native:
                raise HostUnavailable("native_identity_changed")
            row["native"] = native
        try:
            return self._retain_settlement(row, observation)
        except BaseException as error:
            self._stop_on_error(row, error)
            raise

    def _stop_on_error(self, row, error):
        # No storage access or owned coroutine is required for emergency stop.
        # A changed runtime home cannot turn cached ownership into authority.
        try:
            if Path(self.store.state.data_dir) != self._state_directory:
                raise HostUnavailable("foreign_runtime_home")
            observed = (self._controller(row).bindings['a0'].emergency_stop(copy.deepcopy(row))
                        if row['worker_kind'] == 'a0' else NativeSupervisor().stop(copy.deepcopy(row)))
            if not isinstance(observed, UnitObservation) or not observed.quiescent:
                raise HostUnavailable("STOP_UNCONFIRMED")
        except BaseException as stop_error:
            error.add_note("owned execution STOP_UNCONFIRMED: " + type(stop_error).__name__)
        else:
            error.add_note("owned execution STOP_CONFIRMED; original failure retained")

    def _retain_settlement(self, row, observation):
        row = self._remember(self.store.get(row["existing_task_id"], row["owner"]))
        terminal = quiet = None
        if isinstance(observation, NativeObservation) and observation.state in {"completed", "failed", "stopped"}:
            terminal = {"state": observation.state, "evidence_reference": observation.evidence_reference,
                        "at_unix": self.store.clock()}
        if (row["submission_observation"] == "NOT_SUBMITTED" and row["stop_intent"]
                and (row['worker_kind'] != 'a0' or row['host']['a0']['launch'] is None)):
            quiet = {"kind": "never_submitted", "observation": None, "at_unix": self.store.clock()}
        elif terminal is not None and row['worker_kind'] == 'a0':
            binding = self._controller(row).bindings['a0']
            binding.emergency_stop(row)
            quiet = binding.adapter.quiescence(row)
        elif terminal is not None and row["native"] is not None:
            observed = NativeSupervisor().observe(row)
            if observed.quiescent:
                quiet = quiescence_record(observed, self.store.clock)
        # In particular, UNKNOWN before any opening event retains capacity:
        # a concurrent pending launch RPC cannot be disproved by absent unit.
        if quiet is None:
            terminal = None
        if isinstance(observation, NativeObservation):
            row = self.store.retain_outcome(row["existing_task_id"], row["owner"],
                                           observation=asdict(observation), terminal=terminal, quiescence=quiet)
        return self._remember(row)

    def _start(self, row):
        row = self._remember(self.store.get(row["existing_task_id"], row["owner"]))
        controller = self._controller(row)
        if self._closed or row["stop_intent"]:
            return self._stop(row, row["stop_intent"] or "cancel")
        if self.store.clock() >= row["deadline_unix"]:
            # Withdrawal precedes prepare; expiry never gets a fresh budget.
            return self._stop(row, "cancel")
        runtime = row["host"]["binding"]["runtime"]
        if self.ctx.get_config("runtime") != runtime:
            return self._stop(row, "cancel")
        check_runtime(runtime, self.store)
        brief = parse_brief(row["host"]["binding"]["brief"])
        inputs = tuple(VerifiedInput(**v) for v in row["host"]["inputs"])
        controller.prepare(row["existing_task_id"], row["owner"], brief, inputs)
        return self._settle(row, controller.start(row["existing_task_id"], row["owner"], brief, inputs))

    def _reconcile(self, row):
        try:
            with self.store.lock_budget():
                return self._reconcile_checked(row)
        except BaseException as error:
            if not any(note.startswith("owned execution STOP_")
                       for note in getattr(error, "__notes__", ())):
                self._stop_on_error(row, error)
            raise

    def _reconcile_checked(self, row):
        row = self._remember(self.store.get(row["existing_task_id"], row["owner"]))
        if row["host"]["terminal"] is not None and row["host"]["quiescence"] is not None:
            return row
        if row["submission_observation"] == "NOT_SUBMITTED":
            if row['worker_kind'] == 'a0' and row['host']['a0']['launch'] is not None:
                session = self._controller(row).bindings['a0'].adapter
                if session.preparing and not row['stop_intent'] and self.store.clock() < row['deadline_unix']:
                    return row
                return self._stop(row,row['stop_intent'] or 'cancel')
            if row["stop_intent"] or self.store.clock() >= row["deadline_unix"]:
                return self._stop(row, row["stop_intent"] or "cancel")
            return row  # Restart/status never prepares or launches.
        return self._settle(row, self._controller(row).reconcile(row["existing_task_id"], row["owner"]))

    def _stop(self, row, intent):
        with self.store.lock_budget():
            return self._stop_bounded(row, intent)

    def _stop_bounded(self, row, intent):
        # A last checked row remains enough for emergency stop if reads fail.
        try:
            if Path(self.store.state.data_dir) != self._state_directory:
                raise HostUnavailable("foreign_runtime_home")
            row = self._remember(self.store.request_stop(row["existing_task_id"], row["owner"], intent))
            if (row["submission_observation"] == "NOT_SUBMITTED"
                    and (row['worker_kind'] != 'a0' or row['host']['a0']['launch'] is None)):
                return self._settle(row, NativeObservation("", "", "association:" + row["existing_task_id"] + "#stop_intent",
                                                         row["elapsed_seconds"], "stopped"))
            principal = {k: row["owner"][k] for k in PRINCIPAL}
            value = self._controller(row).stop(row["existing_task_id"], principal, intent)
            return self._settle(row, value)
        except BaseException as error:
            # A settlement failure has already attempted exact-owned cleanup.
            if not any(note.startswith("owned execution STOP_")
                       for note in getattr(error, "__notes__", ())):
                self._stop_on_error(row, error)
            raise

    async def _run(self, row):
        # Existing asyncio default executor, no custom thread pool. Shield the
        # actual executor future so cancellation cannot make its thread vanish.
        loop = asyncio.get_running_loop()
        execution = loop.run_in_executor(None, copy_context().run, self._start, row)
        try:
            current = await asyncio.shield(execution)
            while current["host"]["quiescence"] is None:
                await asyncio.sleep(min(1.0, max(.01, current["deadline_unix"] - self.store.clock())))
                if self._closed or self.ctx.get_config("runtime") != row["host"]["binding"]["runtime"]:
                    current = await asyncio.to_thread(self._stop, current, "cancel")
                else:
                    current = await asyncio.to_thread(self._reconcile, current)
            from .result_tool import notify_finished
            await notify_finished(self, current)
            return status(current)
        except asyncio.CancelledError as error:
            # Native stop first, then wait for the bounded in-flight launch to
            # settle and stop again. Future.cancel alone is never quiescence.
            try:
                await asyncio.to_thread(self._stop, self._owned.get(row["existing_task_id"], row), "cancel")
            except BaseException as stop_error:
                error.add_note("owned execution STOP_UNCONFIRMED: " + type(stop_error).__name__)
            try:
                await asyncio.shield(execution)
            except BaseException as execution_error:
                error.add_note("owned launch settlement failed: " + type(execution_error).__name__)
            try:
                await asyncio.to_thread(self._stop, self._owned.get(row["existing_task_id"], row), "cancel")
            except BaseException as stop_error:
                error.add_note("owned execution STOP_UNCONFIRMED: " + type(stop_error).__name__)
            raise
        except Exception as error:
            try:
                await asyncio.to_thread(self._stop, self._owned.get(row["existing_task_id"], row), "cancel")
            except BaseException as stop_error:
                error.add_note("owned execution STOP_UNCONFIRMED: " + type(stop_error).__name__)
            raise

    def _principal(self, receipt, command):
        if not isinstance(receipt, dict):
            raise HostUnavailable("unproved_control")
        operation = receipt.get("native_operation")
        if operation is not None:
            if (command != "friday-stop" or operation not in ("stop", "new")
                    or receipt.get("command") != operation or receipt.get("control_command") != command):
                raise HostUnavailable("unproved_control")
        elif receipt.get("command") != command or "control_command" in receipt:
            raise HostUnavailable("unproved_control")
        ingress = _snapshot(receipt.get("admitted_ingress"))
        source, message = receipt.get("source"), ingress["message"]
        if (not isinstance(source, dict) or source.get("platform") != ingress["platform"]
                or source.get("profile") != ingress["runtime_profile"]
                or receipt.get("session_key") != ingress["session_key"]
                or any((source.get(k) or "") != message[k] for k in ("user_id", "chat_id", "thread_id"))):
            raise HostUnavailable("unproved_control")
        return {**{k: message[k] for k in PRINCIPAL if k != "profile"}, "profile": ingress["runtime_profile"]}

    def control(self, command, raw_args):
        with self.store.lock_budget():
            return self._control_bounded(command, raw_args)

    @staticmethod
    def _matches_control(row, principal, receipt):
        return ("host" in row and row["host"]["quiescence"] is None
                and all(row["owner"][k] == principal[k] for k in PRINCIPAL)
                and row["host"]["binding"]["ingress"]["transport_profile"]
                == receipt["admitted_ingress"]["transport_profile"])

    def _control_bounded(self, command, raw_args):
        cached = None
        receipt = None
        try:
            if Path(self.store.state.data_dir) != self._state_directory:
                raise HostUnavailable("foreign_runtime_home")
            receipt = self.ctx.get_command_context()
            principal = self._principal(receipt, command)
            builtin = receipt.get("native_operation") is not None
            if not isinstance(raw_args, str) or (builtin and raw_args != ""):
                raise HostUnavailable("unproved_control")
            reference = raw_args.strip()
            candidates = [r for r in tuple(self._owned.values())
                          if (not reference or r["existing_task_id"] == reference)
                          and self._matches_control(r, principal, receipt)]
            if len(candidates) == 1:
                cached = copy.deepcopy(candidates[0])
            if not reference:
                rows = [r for r in self.store.snapshot().values()
                        if self._matches_control(r, principal, receipt)]
                if builtin and not rows:
                    return None
                if len(rows) != 1:
                    raise HostUnavailable("no_unique_owned_task")
                reference = rows[0]["existing_task_id"]
                # snapshot validated the same durable ownership and transport;
                # a subsequent metadata wait cannot withhold this checked stop.
                cached = copy.deepcopy(rows[0])
            row = self.store.get_for_control(reference, principal)
            if "host" not in row:
                raise HostUnavailable("missing_host_binding")
            if (row["host"]["binding"]["ingress"]["transport_profile"]
                    != receipt["admitted_ingress"]["transport_profile"]):
                raise HostUnavailable("foreign_control_profile")
            self._remember(row)
            cached = row
            if self.ctx.get_command_context() != receipt:
                raise HostUnavailable("expired_control_lease")
            if command == "friday-status":
                row = self._reconcile(row)
            else:
                row = self._stop(row, "pause" if command == "friday-pause" else "cancel")
            return json.dumps(status(row))
        except (ValueError, RuntimeError, OSError, TypeError) as error:
            if (cached is not None and self.ctx.get_command_context() == receipt
                    and not any(note.startswith("owned execution STOP_")
                                for note in getattr(error, "__notes__", ()))):
                self._stop_on_error(cached, error)
            answer = {"accepted": False, "error": "control_unavailable"}
            if any("STOP_UNCONFIRMED" in note for note in getattr(error, "__notes__", ())):
                answer["cleanup"] = "STOP_UNCONFIRMED"
            return json.dumps(answer)

    def close(self):
        """Public unload cleanup also handles tasks cancelled before first await."""
        self._closed = True
        rows = tuple(copy.deepcopy(list(self._owned.values())))
        if not rows:
            return
        def stop_owned():
            errors = []
            for row in rows:
                if row["host"]["quiescence"] is not None:
                    continue
                try:
                    self._stop(row, "cancel")
                except Exception:
                    errors.append(row["existing_task_id"])
            if errors:
                raise HostUnavailable("STOP_UNCONFIRMED")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            stop_owned()
        else:
            # Lifecycle callbacks are synchronous; use the already owned loop's
            # executor, while _run's finally and native RuntimeMax also remain.
            self._cleanup_future = loop.run_in_executor(None, copy_context().run, stop_owned)
            def completed(future):
                if not future.cancelled() and future.exception() is not None:
                    logging.getLogger(__name__).error("Friday owned worker STOP_UNCONFIRMED")
            self._cleanup_future.add_done_callback(completed)


def register_host(ctx, admission):
    host = WorkerHost(ctx, admission)
    ctx.on_unload(host.close)
    if callable(getattr(ctx, "get_command_context", None)):
        for command in ("friday-stop", "friday-pause", "friday-status"):
            def handler(raw_args, name=command):
                return host.control(name, raw_args)
            ctx.register_command(command, handler, args_hint="[reference]", gateway_control=True,
                                 native_controls=("stop", "new") if command == "friday-stop" else ())
    return host
