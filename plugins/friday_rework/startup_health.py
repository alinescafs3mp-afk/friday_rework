"""Read-only native worker admission observations; never a readiness grant."""


def worker_health():
    """Authoritative existing runtime checks in each administrator-owned scope.

    Read-only, bounded by the native profile list. No PluginState write, worker
    constructor, model request, kernel grant, or readiness conversion occurs.
    Static errors are returned without paths, exception text or secret values.
    """
    from hermes_cli.config_effective import read_user_config_effective_readonly
    from hermes_cli.friday_dashboard_owner import read_owned
    from hermes_cli.plugins_state import PluginState

    from .admin import Administration
    from .associations import Associations
    from .host_runtime import HostUnavailable, check_runtime

    admin = Administration()
    rows = []
    for profile in admin.profiles():
        with admin.scope(profile) as home:
            read_owned(home / "config.yaml", private=True)
            cfg = read_user_config_effective_readonly(home / "config.yaml")
            runtime = (
                cfg.get("plugins", {})
                .get("entries", {})
                .get("friday_rework", {})
                .get("settings", {})
                .get("runtime", {})
            )
            kind = "a0" if "a0" in runtime else ("dsh" if "dsh" in runtime else None)
            if runtime.get("enabled") is not True:
                rows.append(
                    {
                        "profile": profile,
                        "worker": kind,
                        "deployment_verified": False,
                        "blocker": "worker_disabled",
                        "execution": "NOT_OBSERVED",
                    }
                )
                continue
            try:
                checked = check_runtime(runtime, Associations(PluginState("friday_rework")))
                if kind == "a0":
                    # The original v2 A0 contract has no accepted useful-web
                    # consumer. Keep that dependency; do not invent a new field.
                    raise HostUnavailable("a0_useful_web_runtime_contract_unavailable")
                if checked["dsh"].get("web", {}).get("profile") != "exa-paid":
                    raise HostUnavailable("mandatory_worker_web_contract_required")
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                rows.append(
                    {
                        "profile": profile,
                        "worker": kind,
                        "deployment_verified": False,
                        "blocker": "worker_runtime_or_web_unverified",
                        "execution": "NOT_OBSERVED",
                    }
                )
            else:
                rows.append(
                    {
                        "profile": profile,
                        "worker": kind,
                        "deployment_verified": True,
                        "blocker": None,
                        "execution": "NOT_OBSERVED",
                    }
                )
    observed = {r["worker"] for r in rows if r["deployment_verified"]}
    return {
        "workers": rows,
        "missing_workers": sorted({"dsh", "a0"} - observed),
        "runtime_ready": False,
        "live_journeys": "NOT_RUN",
    }
