"""Read-only native worker admission observations; never a readiness grant."""


def _runtime_settings(config):
    value = config
    for key in ("plugins", "entries", "friday_rework", "settings", "runtime"):
        if not isinstance(value, dict):
            raise ValueError("worker_config_invalid")
        value = value.get(key, {})
    if not isinstance(value, dict):
        raise ValueError("worker_config_invalid")
    return value


def worker_health():
    """Authoritative existing runtime checks in each administrator-owned scope.

    Read-only, bounded by the native profile list. No PluginState write, worker
    constructor, model request, kernel grant, or readiness conversion occurs.
    Static errors are returned without paths, exception text or secret values.
    """
    from hermes_cli.config_effective import read_user_config_effective_readonly
    from hermes_cli.friday_dashboard_owner import read_owned
    from hermes_cli.plugins_state import PluginState
    from hermes_yaml import YAMLError

    from .admin import Administration
    from .associations import Associations
    from .host_runtime import HostUnavailable, check_runtime, configured_runtimes

    admin = Administration()
    rows = []
    for profile in admin.profiles():
        # Admission failures remain fatal; a corrupt admitted profile's config
        # must not hide the remaining administrator-owned profiles.
        with admin.scope(profile) as home:
            try:
                read_owned(home / "config.yaml", private=True)
                cfg = read_user_config_effective_readonly(home / "config.yaml")
                runtime = _runtime_settings(cfg)
            except (OSError, ValueError, TypeError, YAMLError):
                rows.append(
                    {
                        "profile": profile,
                        "worker": None,
                        "deployment_verified": False,
                        "blocker": "worker_config_unavailable",
                        "execution": "NOT_OBSERVED",
                    }
                )
                continue
            if runtime == {"enabled": False}:
                rows.append({"profile": profile, "worker": None, "deployment_verified": False,
                             "blocker": "worker_disabled", "execution": "NOT_OBSERVED"})
                continue
            try:
                configured = configured_runtimes(runtime)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                rows.append({"profile": profile, "worker": None, "deployment_verified": False,
                             "blocker": "worker_runtime_or_web_unverified", "execution": "NOT_OBSERVED"})
                continue
            for kind, selected in configured.items():
                try:
                    checked = check_runtime(selected, Associations(PluginState("friday_rework")))
                    if kind == "a0":
                        # Selection does not grant current native A0 admission.
                        raise HostUnavailable("a0_useful_web_runtime_contract_unavailable")
                    if checked["dsh"].get("web", {}).get("profile") not in ("exa-paid", "exa-keyless"):
                        raise HostUnavailable("mandatory_worker_web_contract_required")
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    rows.append({"profile": profile, "worker": kind, "deployment_verified": False,
                                 "blocker": "worker_runtime_or_web_unverified", "execution": "NOT_OBSERVED"})
                else:
                    rows.append({"profile": profile, "worker": kind, "deployment_verified": True,
                                 "blocker": None, "execution": "NOT_OBSERVED"})
    observed = {r["worker"] for r in rows if r["deployment_verified"]}
    return {
        "workers": rows,
        "missing_workers": sorted({"dsh", "a0"} - observed),
        "runtime_ready": False,
        "live_journeys": "NOT_RUN",
    }
