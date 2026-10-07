"""Normal startup over checked native ownership; no admission or process store.

All checks use installed native consumers. A worker receipt is reusable source
readiness only: this module never mints a per-job A0 capability or starts workers.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path


def prerequisites(value, budget):
    """No label in an installer/profile/health receipt grants launch authority."""
    from hermes_cli.friday_dashboard_owner import expected
    from hermes_cli.source_build import source_product_current
    from hermes_constants import get_hermes_home
    from pm.environments import owning_home_root, project_python
    from pm.paths import repo_root
    from scripts.friday_install import owned_file, require

    home = Path(value["home"])
    source = home / "hermes-agent"
    require(
        get_hermes_home() == home
        and repo_root() == source
        and Path(sys.executable) == project_python(source)
        and owning_home_root(source) in (None, home),
        "native_start_generation_mismatch",
    )
    require(
        source_product_current(source, "tui", source / "ui-tui/dist")
        and source_product_current(source, "web", source / "hermes_cli/web_dist"),
        "native_frontend_freshness_not_verified",
    )
    pins = snapshot(home, budget)
    # This API is from the separately reviewed credential-admission overlay.
    # Its absence in the TLS-only base is a real dependency, not an invitation
    # to duplicate its key/pool/route/channel policy here.
    try:
        from hermes_cli.friday_credential_admission import bootstrap, channel_inputs, route_inputs, scoped
    except ModuleNotFoundError as exc:
        if exc.name != "hermes_cli.friday_credential_admission":
            raise
        raise ValueError("native_credential_admission_join_required") from None
    budget.call(bootstrap, home)
    identity = budget.call(expected)
    require(identity["home"] == str(home), "native_start_home_mismatch")
    with scoped(home):
        budget.call(route_inputs)
        contract, _values = budget.call(channel_inputs)
        require(
            contract["profile"] == "default" and bool(contract["required_scoped_names"]["channels"]),
            "native_receiving_channel_required",
        )
    from plugins.friday_rework.startup_health import worker_health

    report = budget.call(worker_health)
    rows = report["workers"]
    require(
        {r["worker"] for r in rows if r["deployment_verified"]} == {"dsh", "a0"}
        and all(r["deployment_verified"] for r in rows),
        "mandatory_a0_web_kernel_and_final_native_dashboard_owner_not_admitted",
    )
    # All imported code and native launchers belong to the same already checked
    # source generation. Snapshot comparison closes drift before service effects.
    from hermes_cli._launchers import _launcher_script, resolve_store_python

    python = resolve_store_python(source, publication=True)
    require(python is not None, "native_published_python_required")
    launcher = source / ".hermes/bin/hermes"
    command = [str(python), "-I", "-c", _launcher_script("hermes", source, None)]
    require(
        owned_file(launcher) == ("#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n').encode()
        and os.access(launcher, os.X_OK)
        and not launcher.stat().st_mode & 0o022,
        "native_launcher_generation_changed",
    )
    unchanged(pins, budget)
    return identity, pins


def snapshot(home, budget):
    from scripts.friday_install import digest, owned_file, read_json

    source = home / "hermes-agent"
    launcher = source / ".hermes/bin/hermes"
    files = {
        str(home / p): True
        for p in ("config.yaml", "FRIDAY-PROFILE.json", "FRIDAY-INSTALL.json", "hermes-agent.source.json")
    }
    marker = read_json(home / "FRIDAY-INSTALL.json")
    files.update({str(source / p): False for p in read_json(home / "hermes-agent.source.json")["files"]})
    files.update({str(home / p): True for p in marker["plugin_files"]})
    files.update({str(home / p): True for p in marker.get("tls_files", {})})
    files[str(launcher)] = False
    for name in (".env", "auth.json"):
        if (home / name).exists() or (home / name).is_symlink():
            files[str(home / name)] = True
    pins = {
        path: {"private": private, "sha256": digest(owned_file(path, private=private))}
        for path, private in files.items()
    }
    for name in (".env", "auth.json"):
        if str(home / name) not in pins:
            pins[str(home / name)] = {"private": True, "sha256": None}
    return pins


def unchanged(pins, budget):
    from scripts.friday_install import digest, owned_file, require

    for path, row in pins.items():
        if row["sha256"] is None:
            require(not Path(path).exists() and not Path(path).is_symlink(), "native_start_input_changed")
            continue
        require(
            digest(budget.call(owned_file, path, private=row["private"])) == row["sha256"],
            "native_start_input_changed",
        )
    for path in pins:
        if Path(path).name == "hermes-agent.source.json":
            from hermes_cli.friday_dashboard_owner import source_identity

            budget.call(source_identity, Path(path).parent, source=Path(path).parent / "hermes-agent")


def gateway_preflight(home, profile, budget):
    """Native exact user unit only; never adopt, refresh, replace or reap foreign."""
    from gateway import host_rendezvous as hr
    from hermes_cli import gateway as gw
    from hermes_constants import get_hermes_home
    from scripts.friday_install import owned_file, require

    require(get_hermes_home() == home and profile == "default", "foreign_gateway_launch_home")
    require(gw.supports_systemd_services(), "native_user_systemd_required")
    require(
        not budget.call(gw.has_legacy_hermes_units) and not budget.call(gw.has_conflicting_systemd_units),
        "duplicate_native_gateway_service",
    )
    unit = gw.get_systemd_unit_path(system=False)
    require(not gw.get_systemd_unit_path(system=True).exists(), "system_gateway_unit_not_adopted")
    dropins = unit.parent / (unit.name + ".d")
    require(
        not dropins.is_symlink() and (not dropins.exists() or not any(dropins.iterdir())),
        "gateway_dropin_requires_reconciliation",
    )
    expected = budget.call(gw.generate_systemd_unit, system=False)
    if unit.exists() or unit.is_symlink():
        require(not unit.stat().st_mode & 0o022, "writable_gateway_unit_refused")
        actual = budget.call(owned_file, unit).decode("utf-8-sig")
        require(
            gw._hermes_home_pinned_by_unit(unit) == str(home)
            and gw._normalize_service_definition(gw._strip_optional_systemd_directives(actual))
            == gw._normalize_service_definition(gw._strip_optional_systemd_directives(expected)),
            "foreign_or_changed_gateway_unit",
        )
    # Existing live native owners must have proved exact home/profile/incarnation.
    record = budget.call(hr.read_record, hr.ROLE_GATEWAY, include_stale=True)
    if record is not None:
        from scripts.friday_native import host_owner

        budget.call(host_owner, record, home, profile)
        require(
            hr.liveness_is_proven(record) and hr.record_token_is_consistent(record),
            "gateway_incarnation_requires_reconciliation",
        )
    return unit, record


def gateway_observation(home, budget):
    from gateway import host_rendezvous as hr
    from gateway.control_socket import CONTROL_PROTOCOL_VERSION, identify_gateway
    from gateway.status import normalize_updated_at, runtime_status_is_stale
    from hermes_cli import gateway as gw
    from hermes_cli.friday_gateway_owner import expected as expected_gateway
    from scripts.friday_install import read_json, require
    from scripts.friday_native import host_owner

    record = budget.call(hr.read_record, hr.ROLE_GATEWAY, include_stale=True)
    require(record is not None, "native_gateway_owner_not_observed")
    budget.call(host_owner, record, home, "default")
    require(
        hr.liveness_is_proven(record) and hr.record_token_is_consistent(record),
        "native_gateway_incarnation_unproved",
    )
    props = budget.call(
        gw._read_systemd_unit_properties,
        system=False,
        properties=("ActiveState", "SubState", "MainPID", "InvocationID"),
    )
    state = budget.call(gw._read_gateway_runtime_status)
    source = budget.call(read_json, home / "hermes-agent.source.json")
    updated = normalize_updated_at(state.get("updated_at")) if isinstance(state, dict) else None
    require(
        props.get("ActiveState") == "active"
        and props.get("SubState") == "running"
        and props.get("MainPID") == str(record.pid)
        and re.fullmatch("[0-9a-f]{32}", props.get("InvocationID", "")) is not None
        and isinstance(state, dict)
        and type(state.get("pid")) is int
        and state.get("pid") == record.pid
        and state.get("gateway_state") == "running"
        and state.get("kind") == "hermes-gateway"
        and type(state.get("start_time")) is int
        and state.get("start_time") == record.start_time
        and state.get("hermes_home") == str(home)
        and isinstance(source.get("commit"), str)
        and re.fullmatch("[0-9a-f]{40}", source["commit"]) is not None
        and state.get("code_sha") == source["commit"]
        and not runtime_status_is_stale(state)
        and updated is not None
        and datetime.fromisoformat(updated) <= datetime.now(timezone.utc),
        "native_gateway_start_not_observed",
    )
    generation = budget.call(expected_gateway, home)
    live = budget.call(identify_gateway, home, timeout=min(5.0, budget.check()))
    require(
        isinstance(live, dict)
        and live.get("protocol") == CONTROL_PROTOCOL_VERSION
        and live.get("kind") == "hermes-gateway"
        and live.get("pid") == record.pid
        and live.get("start_time") == record.start_time
        and live.get("hermes_home") == str(home)
        and live.get("code_sha") == source["commit"]
        and live.get("friday_owner") == generation,
        "native_gateway_generation_unproved",
    )
    return record


def load_required_plugins(budget):
    from hermes_cli.plugins import discover_plugins, get_plugin_manager
    from hermes_cli.plugins_activation import activation_summaries
    from scripts.friday_install import require

    # Native normal dashboard CLI performs the same discovery. No POST or
    # localhost role-token escalation is needed for a trusted installed plugin.
    budget.call(discover_plugins)
    summaries = budget.call(activation_summaries, get_plugin_manager())
    names = {r["name"] for r in summaries}
    require({"friday_rework", "basic", "web-exa"} <= names, "mandatory_native_plugin_activation_failed")


def dashboard_admission(value, budget):
    from hermes_cli import web_server
    from hermes_cli.friday_dashboard_owner import expected

    dash = value["product"]["dashboard"]
    budget.call(web_server._configure_auth_gate, dash["host"], True, None, None)
    return budget.call(
        expected,
        registered=True,
        auth_required=web_server.app.state.auth_required,
        host=dash["host"],
        port=dash["port"],
    )


def launch(value, budget, *, pins):
    """Finite native service handoff, then the existing foreground Dashboard.

    The native gateway unit owns its receiver. A service-command ambiguity is
    STOP_UNCONFIRMED; no automatic stop/retry or invented receipt follows it.
    Dashboard bind/attachment keeps the donor's lock/auth/nonce lifecycle.
    """
    from gateway import host_rendezvous as hr
    from hermes_cli.friday_dashboard_owner import check_attachment
    from scripts.dsh_prepare import StopUnconfirmed
    from scripts.friday_install import clean_environment, commands, require
    from scripts.install_containment import Containment

    home = Path(value["home"])
    argv = budget.call(commands, value)
    unchanged(pins, budget)
    unit, old = gateway_preflight(home, "default", budget)
    serve = budget.call(hr.read_record, hr.ROLE_SERVE, include_stale=True)
    if serve is not None:
        budget.call(check_attachment, serve)  # Actual authenticated native probe.
    budget.call(load_required_plugins, budget)
    budget.call(dashboard_admission, value, budget)
    unchanged(pins, budget)
    custody = Containment(value["containment"], budget, clean_environment(home))
    custody.probe(value["bootstrap_python"]["path"], Path(value["home"]) / "hermes-agent")
    if old is None:
        # Preflight cannot prove absence from a missing rendezvous alone. Refuse
        # a live/unresolved native unit or process before any start request.
        from hermes_cli import gateway as gw

        props = budget.call(gw._read_systemd_unit_properties, system=False)
        require(
            props.get("ActiveState") in ("inactive", "failed", "")
            and str(props.get("MainPID", "0")) == "0"
            and not budget.call(gw.find_gateway_pids),
            "gateway_start_requires_reconciliation",
        )
        unchanged(pins, budget)
        unit, current = gateway_preflight(home, "default", budget)
        require(current is None, "gateway_owner_changed_before_handoff")
        try:
            if not unit.exists():
                custody.run(argv["gateway_install"], home / "hermes-agent", timeout=30)
            unchanged(pins, budget)
            _unit, current = gateway_preflight(home, "default", budget)
            require(current is None, "gateway_owner_changed_before_handoff")
            custody.run(argv["gateway_start"], home / "hermes-agent", timeout=30)
            gateway_observation(home, budget)
        except BaseException as exc:
            raise StopUnconfirmed("native gateway handoff requires reconciliation") from exc
    else:
        gateway_observation(home, budget)  # Reattach only; never restart/replay.
    try:
        unchanged(pins, budget)
        # Native foreground ownership transfers to the operator's terminal.
        # No child, nohup, daemon, launcher replacement or readiness claim.
        env = clean_environment(home)
        require((home / "hermes-agent/.hermes/bin/hermes").is_file(), "native_dashboard_launcher_missing")
        budget.check()
        os.execve(argv["dashboard"][0], argv["dashboard"], env)
        raise RuntimeError("native_foreground_transfer_not_observed")
    except BaseException as exc:
        # The checked gateway is now a native service owner. Never label a
        # failed Dashboard handoff as cessation or silently start it again.
        raise StopUnconfirmed(
            "native gateway remains owned; dashboard handoff requires reconciliation"
        ) from exc


def start(value, budget):
    _identity, pins = prerequisites(value, budget)
    launch(value, budget, pins=pins)
