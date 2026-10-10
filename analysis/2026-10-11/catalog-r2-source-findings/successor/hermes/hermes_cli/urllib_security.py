"""Security policy for credential-bearing stdlib urllib requests."""

from __future__ import annotations

import copy
import weakref
import threading
import logging
import ssl
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

logger = logging.getLogger(__name__)

# Headers safe to forward to a different origin. Everything else is dropped:
# custom provider headers routinely carry credentials under arbitrary names.
_CROSS_ORIGIN_SAFE_HEADERS = frozenset({"accept", "user-agent"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_CATALOG_ADMISSIONS = weakref.WeakSet()


def url_origin(url: str) -> tuple[str, str, int | None]:
    """Return a normalized (scheme, hostname, effective port) origin."""
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    # ``parsed.port`` raises ValueError on malformed ports — let that fail the
    # request closed instead of collapsing it to a default.
    port = parsed.port
    return scheme, (parsed.hostname or "").lower().rstrip("."), port if port is not None else _DEFAULT_PORTS.get(scheme)


def _strip_headers(request, keep: frozenset[str]) -> None:
    """Drop every header on *request* whose lowercased name is not in *keep*."""
    for name, _value in list(request.header_items()):
        if name.lower() not in keep:
            request.remove_header(name)


class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Preserve request headers only while redirects stay on one origin."""

    def __init__(
        self, original_url: str, *, cross_origin_safe_headers: Iterable[str] = _CROSS_ORIGIN_SAFE_HEADERS
    ) -> None:
        self._original_origin = url_origin(original_url)
        self._cross_origin_safe_headers = frozenset(str(name).lower() for name in cross_origin_safe_headers)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Let urllib enforce status/method semantics first (notably 307/308).
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None

        # Allowlist rather than guessing credential header names: normalize_extra_headers
        # permits arbitrary secret-bearing names.
        if url_origin(urllib.parse.urljoin(req.full_url, newurl)) != self._original_origin:
            _strip_headers(redirected, self._cross_origin_safe_headers)
        return redirected


class _CrossOriginRequestSanitizer(urllib.request.BaseHandler):
    """Strip headers after installed request processors have run."""

    # Request processors run in ascending order; infinity keeps this last so an
    # installed cookie/auth/instrumentation processor cannot re-add a secret after
    # the redirect handler sanitized the new Request (stable sort keeps this
    # appended handler after another infinity-ordered one).
    handler_order = float("inf")  # type: ignore[assignment]

    def __init__(self, original_url: str) -> None:
        self._original_origin = url_origin(original_url)

    def _sanitize(self, request: urllib.request.Request):
        if url_origin(request.full_url) != self._original_origin:
            _strip_headers(request, _CROSS_ORIGIN_SAFE_HEADERS)
        return request

    http_request = _sanitize
    https_request = _sanitize


def _resolved_https_context() -> ssl.SSLContext | None:
    """TLS context for Hermes-owned urllib openers.

    None means "use urllib's default", which — with the OS trust store
    installed process-wide — already verifies against the platform's
    certificates. There is nothing to resolve here any more.
    """
    from agent.ssl_verify import install_truststore

    install_truststore()
    return None


def _secure_opener_from_installed_policy(original_url: str, *, ssl_context=None, request_guard=None):
    """Clone the installed opener's handlers, replacing redirect policy only.

    When ``ssl_context`` is provided, the cloned HTTPS handler is replaced with
    one bound to that context so per-provider TLS settings (``ssl_ca_cert`` /
    ``ssl_verify``) apply to this request. When it is None, Hermes-owned
    openers verify against the OS trust store; an application-installed
    opener's TLS policy is preserved unchanged.
    """
    installed = getattr(urllib.request, "_opener", None)
    if installed is None:
        context = _resolved_https_context()
        installed = urllib.request.build_opener(*([] if context is None else [urllib.request.HTTPSHandler(context=context)]))

    _https_handler_cls = getattr(urllib.request, "HTTPSHandler", None)
    replace_https = ssl_context is not None and _https_handler_cls is not None
    handlers = []
    for handler in getattr(installed, "handlers", ()):
        if (isinstance(handler, urllib.request.HTTPRedirectHandler)
                or (replace_https and isinstance(handler, _https_handler_cls))):
            continue
        cloned = copy.copy(handler)
        if request_guard is not None:
            request_guard()
            if cloned is handler:
                from hermes_cli.friday_user_scope import ScopeDenied
                raise ScopeDenied()
        if request_guard is not None and isinstance(handler, urllib.request.HTTPCookieProcessor):
            jar = handler.cookiejar
            with jar._cookies_lock:
                isolated = copy.copy(jar)
                if isolated is jar:
                    from hermes_cli.friday_user_scope import ScopeDenied
                    raise ScopeDenied()
                isolated._cookies = copy.deepcopy(jar._cookies)
                isolated._policy = copy.deepcopy(jar._policy)
                isolated._cookies_lock = threading.RLock()
            cloned.cookiejar = isolated
            request_guard()
        if request_guard is not None and isinstance(handler, (
                urllib.request.AbstractBasicAuthHandler, urllib.request.AbstractDigestAuthHandler)):
            cloned.passwd = copy.deepcopy(handler.passwd)
            request_guard()
        handlers.append(cloned)
    if replace_https:
        handlers.append(_https_handler_cls(context=ssl_context))
    handlers.append(SafeCredentialRedirectHandler(original_url))
    handlers.append(_CrossOriginRequestSanitizer(original_url))
    secured = urllib.request.build_opener(*handlers)
    # OpenerDirector injects addheaders after request processors (bypassing the
    # sanitizer on redirects), so carry them on the initial request instead.
    secured._hermes_initial_addheaders = list(getattr(installed, "addheaders", ()))
    secured.addheaders = []
    return secured


def _bind_request_guard(opener, request_guard):
    """Guard cloned dispatch and actual stdlib connection/effect boundaries."""
    from functools import wraps
    from hermes_cli.friday_user_scope import ScopeDenied

    def settle(handle):
        # Preserve the causal exception while still attempting native cleanup.
        try:
            handle.close()
        except BaseException:
            logger.debug("catalog cleanup failed", exc_info=True)

    def bound(method):
        @wraps(method)
        def checked(request, *args, **kwargs):
            request_guard(request, final=True)
            response = method(request, *args, **kwargs)
            if response is not None:
                try:
                    request_guard(request, final=True)
                except BaseException:
                    settle(response)
                    raise
            return response
        return checked

    wrapped = set()
    for protocol, handlers in getattr(opener, "handle_open", {}).items():
        name = protocol + "_open"
        for handler in handlers:
            key = (id(handler), name)
            if key not in wrapped:
                setattr(handler, name, bound(getattr(handler, name)))
                wrapped.add(key)
    for protocol, handlers in getattr(opener, "process_response", {}).items():
        name = protocol + "_response"
        for handler in handlers:
            native = getattr(handler, name)
            @wraps(native)
            def checked_response(request, response, _native=native):
                try:
                    request_guard(request, final=True)
                    result = _native(request, response)
                    if result is not None and result is not response:
                        response.close()
                    try:
                        request_guard(request, final=True)
                    except BaseException:
                        if result is not None and result is not response:
                            settle(result)
                        raise
                    return result
                except BaseException:
                    if "result" in locals() and result is not None and result is not response:
                        settle(result)
                    settle(response)
                    raise
            setattr(handler, name, checked_response)
    for handler in getattr(opener, "handlers", ()):
        if isinstance(handler, urllib.request.AbstractHTTPHandler):
            native = handler.do_open
            def checked_transport(http_class, request, *args, _native=native, **kwargs):
                request_guard(request, final=True)
                connections = []
                responses = []
                class Connection:
                    def __init__(self, host, *ctor_args, **ctor_kwargs):
                        connection = http_class(host, *ctor_args, **ctor_kwargs)
                        object.__setattr__(self, "_connection", connection)
                        connections.append(connection)
                        request_guard(request, final=True)
                    def __getattr__(self, name):
                        return getattr(self._connection, name)
                    def __setattr__(self, name, value):
                        setattr(self._connection, name, value)
                    def set_debuglevel(self, level):
                        request_guard(request, final=True)
                        self._connection.set_debuglevel(level)
                        request_guard(request, final=True)
                    def set_tunnel(self, *a, **k):
                        request_guard(request, final=True)
                        raise ScopeDenied()
                    def request(self, method, url, data, headers, **options):
                        request_guard(request, final=True)
                        canonical = {n.lower(): v for n, v in request.header_items()}
                        canonical["connection"] = "close"
                        parsed = urllib.parse.urlsplit(request.full_url)
                        connection = self._connection
                        host = getattr(connection, "host", None)
                        port = getattr(connection, "port", None)
                        if (method != "GET" or url != parsed.path or data is not None
                                or {n.lower(): v for n, v in headers.items()} != canonical
                                or options.get("encode_chunked", False)
                                or (host != parsed.netloc and not (host == parsed.hostname
                                    and port == (parsed.port or _DEFAULT_PORTS[parsed.scheme])))
                                or getattr(connection, "_tunnel_host", None)):
                            raise ScopeDenied()
                        request_guard(request, final=True)
                        connection.request(method, url, data, headers, **options)
                        request_guard(request, final=True)
                    def getresponse(self):
                        request_guard(request, final=True)
                        response = self._connection.getresponse()
                        responses.append(response)
                        try:
                            request_guard(request, final=True)
                        except BaseException:
                            settle(response)
                            raise
                        return response
                try:
                    response = _native(Connection, request, *args, **kwargs)
                    request_guard(request, final=True)
                    native_close = response.close
                    def close():
                        try:
                            return native_close()
                        finally:
                            for connection in connections:
                                connection.close()
                    response.close = close
                    return response
                except BaseException as error:
                    for response in responses:
                        settle(response)
                    for connection in connections:
                        settle(connection)
                    # stdlib catches OSError around h.request; ScopeDenied is a
                    # PermissionError. Retain the admission refusal as the cause.
                    if isinstance(error, urllib.error.URLError) and isinstance(error.reason, ScopeDenied):
                        raise error.reason from error
                    raise
            handler.do_open = checked_transport


def _retained_catalog_guard(request, callback):
    from hermes_cli.friday_cli_principal import current_cli
    from hermes_cli.friday_credential_admission import managed
    from hermes_cli.friday_user_scope import ScopeDenied
    from agent.secret_scope import _SECRET_SCOPE, _MULTIPLEX_CONTEXT
    cap = current_cli()
    if cap is None:
        if managed() or _MULTIPLEX_CONTEXT.get() is True or _SECRET_SCOPE.get() is not None:
            raise ScopeDenied()
        return callback
    admission = getattr(request, "_hermes_catalog_admission", None)
    if admission not in _CATALOG_ADMISSIONS:
        raise ScopeDenied()
    admission(request)
    if callback is None or callback is admission:
        return admission
    def check(request=None, *, final=False):
        admission(request, final=final)
        callback(request, final=final)
        admission(request, final=final)
    return check


def open_credentialed_url(
    request: urllib.request.Request,
    *,
    timeout: float,
    opener_factory: Callable[..., Any] | None = None,
    ssl_context=None,
    request_guard: Callable[..., Any] | None = None,
):
    """Open a request without forwarding credentials across origins.

    The default preserves an application-installed opener's proxy, TLS,
    cookies, custom protocol handlers, and instrumentation while replacing its
    redirect handler. ``opener_factory`` is an explicit test seam; security is
    never disabled based on global ``urlopen`` identity.

    ``request_guard`` retains caller authority for this request and every native
    recursive open; unmanaged callers keep the original behavior.

    ``ssl_context`` (an ``ssl.SSLContext``) overrides the HTTPS handler's TLS
    policy for this request only. It is used to honor a custom provider's
    ``ssl_ca_cert`` / ``ssl_verify`` on the ``/models`` discovery path, which
    otherwise falls back to the process-wide platform trust store
    (``agent.ssl_verify.install_truststore``).
    """
    request_guard = _retained_catalog_guard(request, request_guard)
    if request_guard is not None:
        request_guard(request)
    if opener_factory is not None and getattr(request, "_hermes_catalog_admission", None) in _CATALOG_ADMISSIONS:
        # A managed caller cannot substitute an arbitrary endpoint factory for
        # its native admitted transport. Unmanaged test factories stay supported.
        from hermes_cli.friday_user_scope import ScopeDenied
        raise ScopeDenied()
    if opener_factory is None:
        construction = {} if request_guard is None else {"request_guard": request_guard}
        opener = _secure_opener_from_installed_policy(request.full_url, ssl_context=ssl_context, **construction)
        for name, value in getattr(opener, "_hermes_initial_addheaders", ()):
            if not request.has_header(name):
                request.add_header(name, value)
    else:
        opener = opener_factory(SafeCredentialRedirectHandler(request.full_url))
        if request_guard is not None and type(opener) is not urllib.request.OpenerDirector:
            from hermes_cli.friday_user_scope import ScopeDenied
            raise ScopeDenied()
    if request_guard is not None:
        # Constructors/copy hooks and installed addheaders ran since admission.
        request_guard(request)
        _bind_request_guard(opener, request_guard)
        request_guard(request)
    response = opener.open(request, timeout=timeout)
    if request_guard is not None:
        try:
            request_guard(request)
        except BaseException:
            try:
                response.close()
            except BaseException:
                logger.debug("catalog cleanup failed", exc_info=True)
            raise
    return response


__all__ = ["SafeCredentialRedirectHandler", "open_credentialed_url", "url_origin"]
