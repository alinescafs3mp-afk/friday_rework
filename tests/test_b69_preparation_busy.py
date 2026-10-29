"""Exact B69 pre-adapter lock boundary; native systemd is an offline fixture."""
import asyncio
import copy
import fcntl
import sys
import threading
from contextlib import contextmanager

import pytest

from test_host_native import isolated, setup, native, offline_boundary, ingress, _pending_running
from agent.secret_scope import set_secret_scope, reset_secret_scope


@pytest.fixture(autouse=True)
def owned_secret_scope(setup, monkeypatch):
    # The systemd boundary is already offline; its synthetic node cannot
    # satisfy actual root AppArmor pins. The unchanged guard has its own suite.
    dsh = sys.modules[setup.module.__package__ + ".adapters.dsh"]
    monkeypatch.setattr(dsh, "_apparmor_boundary", lambda config, argv: argv)
    # Production gateway work retains this scope across its executor calls.
    token = set_secret_scope({"OFFLINE_DSH_KEY": "offline-profile-value"},
                             profile_home=str(setup.home))
    try:
        yield
    finally:
        reset_secret_scope(token)


def hold_preparation_lock(setup, row, monkeypatch):
    controller = setup.host._controller(row)
    original = controller._load
    lock = setup.host.store.state.data_dir / "admission.lock"

    def held(*args, **kwargs):
        # Different open file descriptions contend even in the same process.
        # Only Controller._load is held; preceding fresh host/controller reads
        # succeed, reproducing the exact diagnostic's acquisition site.
        with lock.open("r+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return original(*args, **kwargs)

    monkeypatch.setattr(controller, "_load", held)
    monkeypatch.setattr(setup.host, "_controller", lambda checked: controller)
    return controller, original


@pytest.mark.asyncio
async def test_real_preparation_busy_defers_without_observation_or_relaunch(setup, monkeypatch):
    row = _pending_running(setup, await ingress(setup))
    before = setup.host.store.state.path.read_bytes()
    controller, original = hold_preparation_lock(setup, row, monkeypatch)
    deferred = await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=True)
    assert deferred == row
    assert setup.host.store.state.path.read_bytes() == before
    assert setup.boundary.stops == []
    assert len(setup.boundary.launches) == 1
    assert all(unit["running"] for unit in setup.boundary.units.values())
    assert row["existing_task_id"] not in getattr(setup.host, "_pending_observations", {})
    assert deferred["host"]["terminal"] is deferred["host"]["quiescence"] is None
    assert deferred["goal_verification"] == deferred["delivery"] == "NOT_RUN"

    # A later fresh observation uses the same invocation and original clocks.
    monkeypatch.setattr(controller, "_load", original)
    observed = await asyncio.to_thread(setup.host._reconcile, deferred, defer_owned_busy=True)
    assert observed["native"] == row["native"]
    for key in ("created_at_unix", "deadline_unix", "budget_seconds", "stop_intent"):
        assert observed[key] == row[key]
    assert observed["host"]["observation"]["state"] == "running"
    assert observed["host"]["quiescence"] is None
    assert len(setup.boundary.launches) == 1
    assert setup.boundary.stops == []
    setup.host._stop(observed, "cancel")


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["not_background", "truthy_optin", "closed", "deadline", "elapsed", "stop", "runtime"])
async def test_preparation_busy_keeps_required_cleanup(setup, monkeypatch, reason):
    row = _pending_running(setup, await ingress(setup))
    controller, original = hold_preparation_lock(setup, row, monkeypatch)
    if reason == "closed":
        setup.host._closed = True
    elif reason == "deadline":
        monkeypatch.setattr(setup.host.store, "clock", lambda: row["deadline_unix"] + 1)
    elif reason == "elapsed":
        setup.host.store.observe(row["existing_task_id"], row["owner"], native=row["native"],
            evidence_reference=row["execution_observation"], elapsed_seconds=row["budget_seconds"])
    elif reason == "stop":
        setup.host.store.request_stop(row["existing_task_id"], row["owner"], "cancel")
    elif reason == "runtime":
        changed = copy.deepcopy(setup.runtime)
        changed["budget_seconds"] += 1
        setup.configure(changed)
    busy = type(setup.host.store).__module__
    import sys
    error_type = sys.modules[busy].AssociationLockBusy
    with pytest.raises(error_type):
        await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=(False if reason == "not_background" else 1 if reason == "truthy_optin" else True))
    assert setup.boundary.stops
    assert all(not unit["running"] for unit in setup.boundary.units.values())
    assert len(setup.boundary.launches) == 1
    retained = setup.host.store.snapshot()[row["existing_task_id"]]
    assert retained["deadline_unix"] == row["deadline_unix"]
    assert retained["budget_seconds"] == row["budget_seconds"]
    assert retained["host"]["terminal"] is retained["host"]["quiescence"] is None
    monkeypatch.setattr(controller, "_load", original)
    setup.configure(setup.runtime)
    setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_busy_after_adapter_is_never_deferred(setup, monkeypatch):
    row = _pending_running(setup, await ingress(setup))
    controller = setup.host._controller(row)
    original = controller._record
    import sys
    busy = sys.modules[type(setup.host.store).__module__].AssociationLockBusy
    error = busy("injected post-adapter metadata refusal")
    def reject(*args, **kwargs):
        raise error
    monkeypatch.setattr(controller, "_record", reject)
    monkeypatch.setattr(setup.host, "_controller", lambda checked: controller)
    with pytest.raises(busy) as caught:
        await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=True)
    assert caught.value is error
    assert any(note.startswith("owned execution STOP_CONFIRMED") for note in error.__notes__)
    assert setup.boundary.stops
    assert all(not unit["running"] for unit in setup.boundary.units.values())
    monkeypatch.setattr(controller, "_record", original)
    setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_plain_preparation_timeout_is_not_contention(setup, monkeypatch):
    row = _pending_running(setup, await ingress(setup))
    controller = setup.host._controller(row)
    original = controller._load
    error = TimeoutError("native state or original allowance timeout")
    def reject(*args, **kwargs):
        raise error
    monkeypatch.setattr(controller, "_load", reject)
    monkeypatch.setattr(setup.host, "_controller", lambda checked: controller)
    with pytest.raises(TimeoutError) as caught:
        await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=True)
    assert caught.value is error
    assert any(note.startswith("owned execution STOP_CONFIRMED") for note in error.__notes__)
    assert setup.boundary.stops and all(not unit["running"] for unit in setup.boundary.units.values())
    monkeypatch.setattr(controller, "_load", original)
    setup.host._stop(row, "cancel")


@pytest.mark.asyncio
@pytest.mark.parametrize("off_loop", [False, True])
async def test_unload_after_deferred_preparation_still_stops(setup, monkeypatch, off_loop):
    row = _pending_running(setup, await ingress(setup))
    controller, original = hold_preparation_lock(setup, row, monkeypatch)
    assert await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=True) == row
    monkeypatch.setattr(controller, "_load", original)
    if off_loop:
        await asyncio.to_thread(setup.manager.unload)
    else:
        setup.manager.unload()
        if setup.host._cleanup_future is not None:
            await asyncio.wait_for(asyncio.shield(setup.host._cleanup_future), 3)
    retained = setup.host.store.snapshot()[row["existing_task_id"]]
    assert retained["stop_intent"] == "cancel"
    assert retained["host"]["quiescence"] is not None
    assert all(not unit["running"] for unit in setup.boundary.units.values())
    assert len(setup.boundary.launches) == 1


@pytest.mark.asyncio
async def test_failed_custody_check_cannot_defer(setup, monkeypatch):
    row = _pending_running(setup, await ingress(setup))
    controller, original = hold_preparation_lock(setup, row, monkeypatch)
    from hermes_cli import friday_user_scope
    check = friday_user_scope.check_retained_job
    calls = []
    def revoked(checked):
        calls.append(checked["existing_task_id"])
        # First check guards the normal path; deferral revalidates custody.
        if len(calls) == 2:
            raise PermissionError("offline custody revoked before deferral")
        return check(checked)
    monkeypatch.setattr(friday_user_scope, "check_retained_job", revoked)
    with pytest.raises(PermissionError):
        await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=True)
    assert len(calls) == 2
    assert setup.boundary.stops and all(not unit["running"] for unit in setup.boundary.units.values())
    monkeypatch.setattr(controller, "_load", original)
    monkeypatch.setattr(friday_user_scope, "check_retained_job", check)
    setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_foreign_state_path_cannot_defer_or_gain_stop_authority(setup, monkeypatch, tmp_path):
    row = _pending_running(setup, await ingress(setup))
    controller, original = hold_preparation_lock(setup, row, monkeypatch)
    allowed = setup.host._state_directory
    monkeypatch.setattr(setup.host, "_state_directory", tmp_path / "different-owned-home")
    with pytest.raises(setup.module.HostUnavailable, match="foreign_runtime_home") as caught:
        await asyncio.to_thread(setup.host._reconcile, row, defer_owned_busy=True)
    assert any(note.startswith("owned execution STOP_UNCONFIRMED") for note in caught.value.__notes__)
    # A foreign runtime home never authorizes stop. Restore the owned identity
    # before this fixture performs its required exact cleanup.
    assert not setup.boundary.stops
    monkeypatch.setattr(setup.host, "_state_directory", allowed)
    monkeypatch.setattr(controller, "_load", original)
    setup.host._stop(row, "cancel")


@pytest.mark.asyncio
async def test_real_thread_lock_contention_is_typed_but_expired_allowance_is_not(setup):
    row = _pending_running(setup, await ingress(setup))
    store = setup.host.store
    busy = sys.modules[type(store).__module__].AssociationLockBusy
    entered, release = threading.Event(), threading.Event()
    def hold():
        with store._thread_lock:
            entered.set()
            assert release.wait(3)
    holder = asyncio.create_task(asyncio.to_thread(hold))
    assert await asyncio.to_thread(entered.wait, 3)
    try:
        with pytest.raises(busy):
            await asyncio.to_thread(store.snapshot)
    finally:
        release.set()
        await holder
    from hermes_cli.plugins_state import LockAcquisitionBudget
    class Expired(LockAcquisitionBudget):
        @contextmanager
        def acquiring(self):
            yield 0.0
    token = store._lock_allowance.set(Expired(.25))
    try:
        with pytest.raises(TimeoutError) as caught:
            store.snapshot()
        assert not isinstance(caught.value, busy)
    finally:
        store._lock_allowance.reset(token)
    setup.host._stop(row, "cancel")
