"""Verified Dashboard authority over the existing owning host, not Telegram ingress.

Opaque native access tokens travel only over Hermes' protected local socket.
Providers that cannot verify the token in the gateway process refuse the action.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat


@contextmanager
def authority_home(home):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    token = set_hermes_home_override(str(home))
    try:
        yield
    finally:
        reset_hermes_home_override(token)


def prove_operator(provider, access_token, home, profile):
    from hermes_cli.dashboard_auth.registry import get_provider
    from hermes_cli.friday_product_access import admin_policy, session_allowed
    if (not isinstance(provider, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", provider)
            or not isinstance(access_token, str) or not 0 < len(access_token) <= 8192
            or any(ord(c) < 32 for c in access_token)):
        raise PermissionError("verified_admin_required")
    with authority_home(home):
        policy = admin_policy()
        if policy is None or profile not in policy["profiles"]:
            raise PermissionError("foreign_product_profile")
        verifier = get_provider(provider, scope=str(home))
        if verifier is None or verifier.supports_session is not True:
            raise PermissionError("gateway_auth_provider_unavailable")
        session = verifier.verify_session(access_token=access_token)
        if not session_allowed(session) or session.provider != provider:
            raise PermissionError("verified_admin_required")
    return session


def host_command(host):
    """Capture the loaded host's actual native context once; never construct a host."""
    from contextvars import copy_context
    from hermes_constants import get_hermes_home, get_process_hermes_home
    context, home, launch = copy_context(), get_hermes_home(), get_process_hermes_home()
    def handler(raw):
        try:
            if not isinstance(raw, str) or len(raw.encode()) > 12000:
                raise ValueError("bounded_admin_request")
            params = json.loads(raw)
            if not isinstance(params, dict) or set(params) != {"profile", "provider", "access_token", "task_id", "action"}:
                raise ValueError("invalid_admin_request")
            def run():
                if get_hermes_home() != home:
                    raise PermissionError("foreign_host_home")
                def verify():
                    from hermes_cli.config import load_config_readonly
                    consent = (load_config_readonly().get("plugins") or {}).get("entries", {}).get(host.ctx.plugin_id, {})
                    if consent.get("allow_gateway_control") is not True:
                        raise PermissionError("owning_control_consent_required")
                    return prove_operator(params["provider"], params["access_token"], launch, params["profile"])
                verify()
                return host.admin_control(params["profile"], params["task_id"], params["action"],
                    verify)
            return context.copy().run(run)
        except PermissionError:
            return {"accepted": False, "error": "verified_admin_or_profile_refused"}
        except Exception:
            return {"accepted": False, "error": "admin_control_unconfirmed", "execution": "UNKNOWN"}
    return handler


def request_control(home, profile, session, task_id, action):
    from gateway.control_socket import query_gateway_control, resolve_client_socket_path
    if action not in ("status", "pause", "cancel") or not isinstance(task_id, str) or not re.fullmatch(r"native-[a-f0-9]{64}", task_id):
        raise ValueError("invalid_admin_control")
    # The native socket/pointer remains the transport and ACL authority.
    endpoint = resolve_client_socket_path(home)
    if endpoint is None:
        return {"accepted": False, "execution": "UNKNOWN", "error": "owning_gateway_unavailable"}
    info = endpoint.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("unprotected_native_control_socket")
    response = query_gateway_control(home, "plugin-control", params={
        "profile": profile, "plugin": "friday_rework", "control": "friday-admin-control",
        "arguments": {"provider": session.provider, "access_token": session.access_token,
                      "task_id": task_id, "action": action}}, timeout=2.0)
    if not isinstance(response, dict) or type(response.get("accepted")) is not bool:
        return {"accepted": False, "execution": "UNKNOWN", "error": "owning_control_response_lost"}
    # A current retained projection is useful after a lost response. Never retry
    # the control or relaunch execution automatically.
    return response
