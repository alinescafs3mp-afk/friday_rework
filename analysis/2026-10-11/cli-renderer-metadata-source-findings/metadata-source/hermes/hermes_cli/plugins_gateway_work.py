"""Owned plugin work on the already published gateway loop; no new runtime owner."""
from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import logging
from typing import Any, Mapping

logger = logging.getLogger("hermes_cli.plugins")


def cancel_task(task):
    """Unload may run in a discovery thread, whereas Task.cancel is loop-affine."""
    loop = task.get_loop()
    if task.done() or loop.is_closed():
        return
    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None
    if current is loop:
        task.cancel()
    else:
        loop.call_soon_threadsafe(task.cancel)


def _close_unstarted(coro):
    if inspect.iscoroutine(coro) and inspect.getcoroutinestate(coro) == inspect.CORO_CREATED:
        coro.close()
    elif inspect.isgenerator(coro) and inspect.getgeneratorstate(coro) == inspect.GEN_CREATED:
        coro.close()


def require_capability(context, flag, *, owner=None):
    """Read consent from the immutable manager home and reject stale plugin contexts."""
    from hermes_cli.plugins import _plugin_home_scope, _plugin_settings_entry, load_config_readonly
    manager = context._manager
    loaded = manager._plugins.get(context.plugin_id)
    lease = getattr(context, "_gateway_work_lease", None)
    if (context._load_abandoned or getattr(manager, "_gateway_unloading", False)
            or loaded is None or not loaded.enabled
            or loaded.manifest is not context.manifest or (lease is not None and not lease.active)):
        raise RuntimeError("plugin_unloaded")
    host = manager._gateway_message_injector
    if host is None or (owner is not None and host[0] is not owner):
        raise RuntimeError("gateway_offline")
    runner = host[0]
    loop = getattr(runner, "_gateway_loop", None)
    if (not callable(getattr(runner, "_plugin_document_route", None))
            or not runner._plugin_injection_accepting() or loop is None
            or loop.is_closed() or not loop.is_running()):
        raise RuntimeError("gateway_offline")
    try:
        with _plugin_home_scope(manager.home_path):
            cfg = load_config_readonly() or {}
        allowed = (_plugin_settings_entry(cfg, context.plugin_id) or {}).get(flag) is True
    except Exception:  # health: allow BLE001 -- Consent read fails closed without exposing configuration or secrets.
        allowed = False
    if not allowed:
        raise RuntimeError("gateway_capability_denied")
    if lease is None:
        context._gateway_work_lease = context.on_unload(lambda: None)
    return runner


async def _run_owned(context, runner, route, coro):
    from gateway.run import _async_profile_runtime_scope
    from hermes_cli.plugins import _plugin_home_scope
    # The initial scope also accompanies native secret hydration's thread hop.
    with _plugin_home_scope(context._manager.home_path):
        async with _async_profile_runtime_scope(context._manager.home_path):
            require_capability(context, "allow_gateway_work", owner=runner)
            try:
                runner._plugin_document_route(context, route)
            except Exception:  # health: allow BLE001 -- Authorization/routing failures must not disclose SDK or configuration secrets.
                raise RuntimeError("gateway_route_rejected") from None
            return await coro


def _start_owned(context, runner, route, coro, name, future, pending):
    """The gateway callback atomically hands pending ownership to spawn_task's ledger."""
    with context._manager._discovery_lock:
        if future.cancelled():
            _close_unstarted(coro)
            pending.dispose()
            return
        try:
            require_capability(context, "allow_gateway_work", owner=runner)
            owned = _run_owned(context, runner, route, coro)
            try:
                task = context.spawn_task(owned, name=name)
            except BaseException:
                owned.close()
                raise
        except Exception:  # health: allow BLE001 -- Public admission returns a sanitized refusal; closes caller coroutine.
            _close_unstarted(coro)
            _settle(future, error=RuntimeError("gateway_work_rejected"))
            pending.dispose()
            return
        # Pending disposal must not cancel the accepted task/future at this handoff.
        pending.release = lambda: None
        pending.dispose()
        runner._background_tasks.add(task)
        task.add_done_callback(runner._background_tasks.discard)

    def finish(completed):
        _close_unstarted(coro)
        if completed.cancelled():
            future.cancel()
            return
        error = completed.exception()
        _settle(future, error=error, result=None if error else completed.result())

    task.add_done_callback(finish)
    future.add_done_callback(lambda done: cancel_task(task) if done.cancelled() else None)


def _settle(future, *, error=None, result=None):
    try:
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)
    except concurrent.futures.InvalidStateError:
        # Another thread may cancel between task completion and Future completion.
        if not future.cancelled():
            raise


def schedule_gateway_work(context, coro, *, route, name=None):
    if not asyncio.iscoroutine(coro):
        raise TypeError("schedule_gateway_work expects a coroutine")
    pending = None
    try:
        with context._manager._discovery_lock:
            runner = require_capability(context, "allow_gateway_work")
            # Detach the persisted input before crossing the thread boundary.
            from gateway.run_plugin_delivery import freeze_route
            original_route = freeze_route(route)
            future = concurrent.futures.Future()
            def release_pending():
                future.cancel()
                _close_unstarted(coro)
            pending = context._track("gateway_work_pending", name or "gateway_work", release_pending)
            runner._gateway_loop.call_soon_threadsafe(
                _start_owned, context, runner, original_route, coro, name, future, pending)
            return future
    except BaseException:
        _close_unstarted(coro)
        if pending is not None:
            pending.dispose()
        raise


async def deliver_gateway_document(context, **kwargs):
    from gateway.run import _async_profile_runtime_scope
    from gateway.run_plugin_delivery import freeze_route
    from hermes_cli.plugins import _plugin_home_scope
    delivery_entered = False
    try:
        with context._manager._discovery_lock:
            runner = require_capability(context, "allow_gateway_delivery")
        if asyncio.get_running_loop() is not runner._gateway_loop:
            raise RuntimeError("gateway_loop_required")
        kwargs["route"] = freeze_route(kwargs["route"])
        with _plugin_home_scope(context._manager.home_path):
            async with _async_profile_runtime_scope(context._manager.home_path):
                require_capability(context, "allow_gateway_delivery", owner=runner)
                delivery_entered = True
                return await runner._deliver_plugin_document(context, **kwargs)
    except Exception:  # health: allow BLE001 -- Errors after delivery entry may follow a committed send; never authorize replay.
        if delivery_entered:
            return {"state": "UNKNOWN", "error": "gateway_delivery_uncertain"}
        return {"state": "FAILED", "error": "gateway_delivery_preflight_rejected"}


class PluginGatewayWorkMixin:
    """Public context methods for owned asyncio work and gateway delivery."""

    def spawn_task(self, coro, *, name: str | None = None) -> asyncio.Task:
        """Spawn a supervised asyncio task; unload/force reload cancels it. Needs a running loop."""
        if not asyncio.iscoroutine(coro):
            raise TypeError("spawn_task expects a coroutine")
        loop = asyncio.get_running_loop()
        task_name = name or f"plugin:{self.plugin_id}:task"
        # Register ownership before task creation. A registration failure must
        # not leave an unowned task queued on the native loop.
        task = None
        def release():
            if task is None:
                _close_unstarted(coro)
            else:
                cancel_task(task)
        try:
            logger.debug("Plugin %s spawning supervised task: %s", self.manifest.name, task_name)
            handle = self._track("background_task", task_name, release)
        except BaseException:
            _close_unstarted(coro)
            raise
        try:
            task = loop.create_task(coro, name=task_name)
            task.add_done_callback(lambda _t: handle.dispose())
            if not handle.active:
                cancel_task(task)  # unload raced registration before assignment
            return task
        except BaseException:
            handle.dispose()
            if task is not None:
                def reap(finished):
                    if not finished.cancelled():
                        finished.exception()
                    _close_unstarted(coro)
                task.add_done_callback(reap)
            raise

    def schedule_gateway_work(self, coro, *, route: Mapping[str, Any], name: str | None = None):
        """Submit owned work to the live gateway loop, including from a sync tool thread.

        Returns a concurrent Future. Refusal closes the coroutine and raises RuntimeError.
        Cancellation requests asyncio cancellation; it does not stop a blocking worker.
        Requires this profile's per-plugin ``allow_gateway_work: true`` and original route.
        """
        return schedule_gateway_work(self, coro, route=route, name=name)

    async def deliver_gateway_document(
        self, *, route: Mapping[str, Any], data: bytes, file_name: str,
        caption: str | None = None, timeout: float = 60,
    ) -> dict:
        """Deliver immutable bytes on the gateway loop to a persisted original route.

        Requires ``allow_gateway_delivery: true``. Returns DELIVERED only with a native
        document acknowledgement; UNKNOWN must not be automatically retried.
        """
        return await deliver_gateway_document(
            self, route=route, data=data, file_name=file_name, caption=caption, timeout=timeout)
