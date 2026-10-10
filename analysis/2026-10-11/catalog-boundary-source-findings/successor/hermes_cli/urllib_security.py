"""Security policy for credential-bearing stdlib urllib requests."""

from __future__ import annotations

import copy
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
    """Bind admission to this cloned opener's actual dispatch/transport methods.

    Request processors, proxy handlers and response authentication can mutate a
    Request or recursively reopen it. Checking every native open dispatch, and
    do_open immediately before connection construction, covers those boundaries
    without changing the installed opener or the native handler architecture.
    """
    from functools import wraps

    def bound(method):
        @wraps(method)
        def checked(request, *args, **kwargs):
            request_guard(request, final=True)
            return method(request, *args, **kwargs)
        return checked

    wrapped = set()
    for protocol, handlers in getattr(opener, "handle_open", {}).items():
        name = protocol + "_open"
        for handler in handlers:
            key = (id(handler), name)
            if key not in wrapped:
                setattr(handler, name, bound(getattr(handler, name)))
                wrapped.add(key)
    # urllib's authentication error handlers can recursively open a retry before
    # closing their original response. A refused retry must still settle that
    # native response handle; successful handler behavior remains unchanged.
    for protocol, handlers in getattr(opener, "process_response", {}).items():
        name = protocol + "_response"
        for handler in handlers:
            native = getattr(handler, name)
            @wraps(native)
            def checked_response(request, response, _native=native):
                try:
                    return _native(request, response)
                except Exception:
                    response.close()
                    raise
            setattr(handler, name, checked_response)
    for handler in getattr(opener, "handlers", ()):
        if isinstance(handler, urllib.request.AbstractHTTPHandler):
            # do_open has http_class before Request; retain the native signature.
            native = handler.do_open
            def checked_transport(http_class, request, *args, _native=native, **kwargs):
                request_guard(request, final=True)
                return _native(http_class, request, *args, **kwargs)
            handler.do_open = checked_transport


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
    if request_guard is not None:
        request_guard(request)
    if opener_factory is None:
        construction = {} if request_guard is None else {"request_guard": request_guard}
        opener = _secure_opener_from_installed_policy(request.full_url, ssl_context=ssl_context, **construction)
        for name, value in getattr(opener, "_hermes_initial_addheaders", ()):
            if not request.has_header(name):
                request.add_header(name, value)
    else:
        opener = opener_factory(SafeCredentialRedirectHandler(request.full_url))
    if request_guard is not None:
        # Constructors/copy hooks and installed addheaders ran since admission.
        request_guard(request)
        _bind_request_guard(opener, request_guard)
        request_guard(request)
    response = opener.open(request, timeout=timeout)
    if request_guard is not None:
        try:
            request_guard(request)
        except Exception:
            response.close()
            raise
    return response


__all__ = ["SafeCredentialRedirectHandler", "open_credentialed_url", "url_origin"]
