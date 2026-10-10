"""Local OS authentication joined to explicit native Friday product admission.

A profile selects a destination, never a principal. No environment UID, invented
bot identity, implicit local grant or second user/session database is accepted.
Source-only candidate: local stdio TUI principal handoff is still unsupported.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import os
from pathlib import Path

from hermes_cli import friday_user_scope as users
from hermes_cli.friday_product_access import principal_id, profile_name, text

_LOCAL = ContextVar("friday_native_cli_principal", default=None)


def numeric_os_uid():
    """The kernel owns this identity; privilege-changing invocations fail closed."""
    getuid, geteuid = getattr(os, "getuid", None), getattr(os, "geteuid", None)
    if not callable(getuid) or not callable(geteuid):
        raise users.ScopeDenied()
    uid, effective = getuid(), geteuid()
    if type(uid) is not int or type(effective) is not int or uid < 0 or uid != effective:
        raise users.ScopeDenied()
    return uid


def cli_policy(authorization_home):
    from hermes_cli.friday_product_access import settings
    users._private(Path(authorization_home), directory=True)
    users._private(Path(authorization_home) / "config.yaml")
    with users.authority(authorization_home):
        value = settings().get("cli_admission")
    if (not isinstance(value, dict) or set(value) != {"enabled", "principals"}
            or value["enabled"] is not True or not isinstance(value["principals"], list)
            or not 0 < len(value["principals"]) <= 10000):
        raise users.ScopeDenied()
    seen_uid, seen_principal = set(), set()
    for row in value["principals"]:
        if (not isinstance(row, dict) or set(row) != {"uid", "transport_profile", "account_id", "user_id"}
                or type(row["uid"]) is not int or row["uid"] < 0):
            raise users.ScopeDenied()
        profile_name(row["transport_profile"])
        text(row["account_id"]); text(row["user_id"])
        key = principal_id("cli", row["transport_profile"], row["account_id"], row["user_id"])
        if row["uid"] in seen_uid or key in seen_principal:
            raise users.ScopeDenied()
        seen_uid.add(row["uid"]); seen_principal.add(key)
    return value


@dataclass
class CLIUserScope(users.UserScope):
    os_uid: int = None
    admission: dict = None

    @property
    def session_authority(self):
        return {"schema": "friday.cli-os-authority.v1", "uid": self.os_uid,
                "principal_id": self.key, "generation": self.admission_generation,
                "admission_sha256": users._fingerprint(self.admission)}

    def require_owner(self, owner, ingress):
        from hermes_cli.friday_cli_work import check_owner
        check_owner(owner, ingress)

    def require_retained_owner(self, owner, ingress):
        self.require_owner(owner, ingress)

    def check(self):
        try:
            if (self.revoked or numeric_os_uid() != self.os_uid
                    or self.principal != ("cli", self.admission["transport_profile"],
                                          self.admission["account_id"], self.admission["user_id"])):
                raise users.ScopeDenied()
            rows = [r for r in cli_policy(self.authorization_home)["principals"] if r["uid"] == self.os_uid]
            if len(rows) != 1 or rows[0] != self.admission:
                raise users.ScopeDenied()
            return super().check()
        except Exception:
            self.revoked = True
            raise users.ScopeDenied() from None


def initialize_cli():
    """Authenticate before CLI readers; existing product policy owns every grant."""
    from hermes_constants import get_hermes_home, get_default_hermes_root
    from hermes_cli.friday_product_access import access_policy, current_access
    home = Path(get_hermes_home())
    retained = _LOCAL.get()
    if retained is not None:
        if users._CURRENT.get() is not retained or home != retained.home:
            raise users.ScopeDenied()
        return retained.check()
    # A gateway capability cannot turn a new CLI ingress into that gateway user.
    if users._CURRENT.get() is not None:
        raise users.ScopeDenied()
    root = get_default_hermes_root(home=home)
    active = users.policy(root)
    if active is None:
        if (users._ENGAGED or (home / users.MARKER).exists()
                or (home / users.MARKER).is_symlink() or users.policy(home) is not None):
            raise users.ScopeDenied()
        return None
    users._ENGAGED = True
    uid = numeric_os_uid()
    rows = [r for r in cli_policy(root)["principals"] if r["uid"] == uid]
    if len(rows) != 1:
        raise users.ScopeDenied()
    admission = dict(rows[0])
    principal = ("cli", admission["transport_profile"], admission["account_id"], admission["user_id"])
    bindings = [r for r in active["bindings"] if tuple(r[k] for k in
                ("platform", "transport_profile", "account_id", "user_id")) == principal]
    if len(bindings) != 1:
        raise users.ScopeDenied()
    binding = dict(bindings[0])
    profile = binding["runtime_profile"]
    expected_home = root / "profiles" / profile
    # Destination comparison follows authentication. --profile/HERMES_HOME grants nothing.
    if home != expected_home or home.resolve() != home:
        raise users.ScopeDenied()
    with users.authority(root):
        access = current_access()["users"].get(principal_id(*principal))
        accounts = access_policy()["accounts"]
    matches = [r for r in accounts if (r["platform"], r["transport_profile"], r["account_id"]) == principal[:3]
               and profile in r["runtime_profiles"]]
    if (len(matches) != 1 or not access or access["enabled"] is not True
            or type(access.get("generation")) is not int or access["generation"] < 1):
        raise users.ScopeDenied()
    st = users._private(home, directory=True)
    cap = CLIUserScope(root, home, profile, principal, binding, (st.st_dev, st.st_ino),
                       access["generation"], os_uid=uid, admission=admission)
    with users.authority(home):
        cap.check()
    # The ordinary process already selected this exact home. Pin only its authenticated capability.
    users._CURRENT.set(cap)
    _LOCAL.set(cap)
    users.check_database(cap)
    return cap


def initialize_cli_argv(argv):
    from hermes_cli._parser import command_argv
    words = command_argv(argv)
    if not words or words[0] == "chat":
        return initialize_cli()
    return None


@contextmanager
def cli_activity(cli):
    cap = getattr(cli, "_friday_cli_scope", None)
    if cap is None:
        # A legacy object cannot adopt a later admission or an inherited gateway user.
        from hermes_constants import get_hermes_home, get_default_hermes_root
        home = Path(get_hermes_home())
        if (users._CURRENT.get() is not None or users._ENGAGED
                or users.policy(get_default_hermes_root(home=home)) is not None
                or users.policy(home) is not None or (home / users.MARKER).exists()
                or (home / users.MARKER).is_symlink()):
            raise users.ScopeDenied()
        yield
        return
    if not isinstance(cap, CLIUserScope) or _LOCAL.get() is not cap or users._CURRENT.get() is not cap:
        raise users.ScopeDenied()
    cap.check()
    users.check_database(cap)
    agent = getattr(cli, "agent", None)
    if agent is not None:
        users.check_agent(agent)
        if (getattr(agent, "_user_id", None) != cap.principal[3]
                or getattr(agent, "platform", None) != "cli"
                or getattr(agent, "session_id", None) != getattr(cli, "session_id", None)):
            raise users.ScopeDenied()
    yield cap


def cli_bound(method):
    @wraps(method)
    def bound(self, *args, **kwargs):
        with cli_activity(self):
            return method(self, *args, **kwargs)
    return bound


def native_cli_user_id(cli):
    with cli_activity(cli) as cap:
        return cap.principal[3] if cap is not None else None


def require_cli_command(cli, command):
    with cli_activity(cli) as cap:
        if cap is None:
            return
        # Config/code installation, quick shell commands, cross-profile readers and native
        # goal/background execution have no admission contract on this CLI ingress yet.
        from hermes_cli.commands import resolve_command
        base = command.strip().split()[0].lstrip("/").lower()
        definition = resolve_command(base)
        name = definition.name if definition is not None else base
        if name in {'friday-stop','friday-pause','friday-status'}:
            from hermes_cli.friday_cli_work import require_local_command
            require_local_command(cli,name)
            return
        if definition is None or name not in {"help", "status", "stop", "cancel", "new", "reset", "history", "resume", "sessions", "memory", "exit", "quit"}:
            raise users.ScopeDenied()


def refuse_unbound_tui():
    if initialize_cli() is not None:
        raise users.ScopeDenied()  # no authenticated stdio session principal transfer exists


def context_thread(*args, **kwargs):
    """Reuse the native ContextVar carrier; every target retains the original capability."""
    from agent.memory_provider import ctx_bound
    import threading
    if args:
        raise TypeError("native_cli_thread_requires_keyword_target")
    kwargs = dict(kwargs)
    target = kwargs.get("target")
    if target is not None:
        kwargs["target"] = ctx_bound(target)
    return threading.Thread(**kwargs)


def cli_session_authority(cap):
    if not isinstance(cap, CLIUserScope) or users._CURRENT.get() is not cap or _LOCAL.get() is not cap:
        raise users.ScopeDenied()
    cap.check()
    return cap.session_authority


@contextmanager
def cli_cleanup_scope(agent):
    """Retain original home for native stop/release after revoke, without regrant."""
    cap = getattr(agent, "_friday_user_scope", None) if agent is not None else _LOCAL.get()
    if cap is None or not isinstance(cap, CLIUserScope):
        yield
        return
    if _LOCAL.get() is not cap or users._CURRENT.get() is not cap:
        raise users.ScopeDenied()
    with users.authority(cap.home):
        # Native cleanup can settle original handles. Data/prompt/tool readers still call
        # cap.check() and therefore remain refused after sticky revocation.
        yield


def cli_cleanup_bound(method):
    @wraps(method)
    def bound(*args, **kwargs):
        from cli import _active_agent_ref
        with cli_cleanup_scope(_active_agent_ref):
            return method(*args, **kwargs)
    return bound


def reject_cli_extension(cli):
    with cli_activity(cli) as cap:
        if cap is not None:
            raise users.ScopeDenied()


def native_cli_session_fields(cli):
    with cli_activity(cli) as cap:
        if cap is None:
            return {}
        from run_agent import _gateway_origin_json
        return {"user_id": cap.principal[3], "profile_name": cap.profile,
                "origin_json": users.delegation_session_origin(cli.agent, _gateway_origin_json(cli.agent))}


def current_cli(required=False):
    """Trusted retained local ingress seam for native consumers; never mint a grant."""
    cap = _LOCAL.get()
    if cap is None:
        if required or users._ENGAGED or users._CURRENT.get() is not None:
            raise users.ScopeDenied()
        return None
    if not isinstance(cap, CLIUserScope) or users._CURRENT.get() is not cap:
        raise users.ScopeDenied()
    cap.check()
    users.check_database(cap)
    return cap


def check_cli_resume(value):
    cap = current_cli()
    if cap is None or value in (None, ""):
        return
    if not isinstance(value, str) or value.lstrip().startswith("@"):
        raise users.ScopeDenied()  # foreign transcript imports have no original CLI authority
    users.check_search(session_id=value)


def check_cli_args(args):
    cap = initialize_cli()
    if cap is None:
        return
    if any(getattr(args, k, False) for k in
           ("yolo", "ignore_user_config", "safe_mode", "worktree", "accept_hooks", "oneshot")):
        raise users.ScopeDenied()
    check_cli_resume(getattr(args, "resume", None))
    in_dir = getattr(args, "in_dir", None)
    if in_dir:
        path = Path(in_dir).expanduser().absolute()
        if not path.is_relative_to(cap.home / "workspace") or path.resolve() != path:
            raise users.ScopeDenied()
        users._private(path, directory=True)
    query_file = getattr(args, "query_file", None)
    if query_file:
        users.check_context_path(Path(query_file).absolute())


def check_cli_main_options(*, gateway, worktree, ignore_user_config, resume):
    if initialize_cli() is None:
        return
    if gateway or worktree or ignore_user_config:
        raise users.ScopeDenied()
    check_cli_resume(resume)


def check_cli_cwd(cli, path):
    """Native resume may retarget only the original exclusive workspace."""
    with cli_activity(cli) as cap:
        if cap is None:
            return
        path = Path(path)
        if not path.is_relative_to(cap.home / "workspace") or path.resolve() != path:
            raise users.ScopeDenied()
        if path.exists():
            users._private(path, directory=True)


def refuse_unbound_oneshot():
    if initialize_cli() is not None:
        raise users.ScopeDenied()  # Alternate runner has no original CLI agent/session join.
