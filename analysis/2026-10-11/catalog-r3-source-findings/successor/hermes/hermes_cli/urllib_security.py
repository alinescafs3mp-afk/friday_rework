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
    # One memo for the handler graph preserves intentional links inside the
    # owned graph. The installed parent is never copied or changed. TLS contexts
    # are external native policy handles, exposed through an immutable view.
    # Every Python mutable instance/container and synchronization lock is owned.
    import types
    import ssl
    lock_types = (type(threading.Lock()), type(threading.RLock()))
    class ReadOnlyTLS:
        # Native SSLContext cannot be duplicated without losing opaque keys,
        # callbacks and platform trust-store policy. A read-only view retains
        # those semantics while a cloned handler cannot mutate installed policy.
        __slots__ = ("_policy",)
        _read_methods = frozenset({"wrap_socket", "wrap_bio", "get_ca_certs",
                                   "cert_store_stats", "get_ciphers", "session_stats"})
        def __init__(self, policy):
            object.__setattr__(self, "_policy", policy)
        @property
        def __class__(self):
            return ssl.SSLContext
        def __getattribute__(self, name):
            if name == "_policy":
                from hermes_cli.friday_user_scope import ScopeDenied
                raise ScopeDenied()
            return object.__getattribute__(self, name)
        def __setattr__(self, name, value):
            from hermes_cli.friday_user_scope import ScopeDenied
            raise ScopeDenied()
        def __getattr__(self, name):
            from hermes_cli.friday_user_scope import ScopeDenied
            policy = object.__getattribute__(self, "_policy")
            value = getattr(policy, name)
            if callable(value):
                if name not in self._read_methods:
                    raise ScopeDenied()
                def read(*a, **k):
                    request_guard()
                    result = value(*a, **k)
                    try:
                        request_guard()
                    except BaseException:
                        if name == "wrap_socket":
                            try:
                                result.close()
                            except BaseException:
                                logger.debug("catalog TLS cleanup failed", exc_info=True)
                        raise
                    return result
                return read
            if isinstance(value, (str, bytes, int, float, bool, type(None), tuple)):
                return value
            raise ScopeDenied()
    memo = {}
    seen = set()
    opaque = (type, types.FunctionType, types.BuiltinFunctionType, types.ModuleType,
              weakref.ReferenceType)
    def prepare(value):
        key = id(value)
        if key in seen:
            return
        seen.add(key)
        if isinstance(value, ssl.SSLContext):
            memo[key] = ReadOnlyTLS(value)
            return
        if isinstance(value, lock_types):
            memo[key] = threading.RLock() if isinstance(value, lock_types[1]) else threading.Lock()
            return
        if isinstance(value, opaque) or value is installed:
            return
        if isinstance(value, dict):
            children = list(value.keys()) + list(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            children = list(value)
        else:
            children = list(getattr(value, "__dict__", {}).values())
            for cls in type(value).__mro__:
                slots = cls.__dict__.get("__slots__", ())
                slots = (slots,) if isinstance(slots, str) else slots
                for name in slots:
                    if name not in ("__dict__", "__weakref__") and hasattr(value, name):
                        children.append(getattr(value, name))
        for child in children:
            prepare(child)
    handlers = []
    originals = []
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
            memo[id(handler)] = cloned
        handlers.append(cloned)
        originals.append(handler)
    if request_guard is not None:
        from hermes_cli.friday_user_scope import ScopeDenied
        # Avoid copying parent through nested bound methods/handler references.
        memo[id(installed)] = None
        for handler, cloned in zip(originals, handlers):
            state = {k: v for k, v in handler.__dict__.items() if k != "parent"}
            slots = {}
            for cls in type(handler).__mro__:
                names = cls.__dict__.get("__slots__", ())
                names = (names,) if isinstance(names, str) else names
                for name in names:
                    if name not in ("__dict__", "__weakref__", "parent") and hasattr(handler, name):
                        slots[name] = getattr(handler, name)
            prepare(state)
            prepare(slots)
            try:
                state = copy.deepcopy(state, memo)
                slots = copy.deepcopy(slots, memo)
            except Exception as error:
                raise ScopeDenied() from error
            request_guard()
            cloned.__dict__.clear()
            cloned.__dict__.update(state)
            for name, value in slots.items():
                setattr(cloned, name, value)
            request_guard()
        # Audit the reachable clone, rather than only deepcopy's memo: a
        # custom __deepcopy__ returning itself is deliberately not memoized by
        # Python. Such a value must not smuggle mutable installed state through.
        checked = set()
        def audit(value):
            key = id(value)
            if key in checked:
                return
            checked.add(key)
            if isinstance(value, (ReadOnlyTLS, ssl.SSLContext)):
                return  # native policy exposed read-only in managed handler state
            if isinstance(value, weakref.ReferenceType):
                # Weak references could retain an original mutable target. They
                # cannot be transparently rehomed without changing its lifetime.
                if value() is not None:
                    raise ScopeDenied()
                return
            if isinstance(value, opaque):
                return
            if isinstance(value, dict):
                mutable = True
                children = list(value.keys()) + list(value.values())
            elif isinstance(value, (list, set, bytearray, memoryview)):
                mutable = True
                children = list(value) if not isinstance(value, (bytearray, memoryview)) else []
            elif isinstance(value, (tuple, frozenset)):
                mutable = False
                children = list(value)
            else:
                state = getattr(value, "__dict__", {})
                mutable = bool(state) or isinstance(value, lock_types)
                children = list(state.values())
                for cls in type(value).__mro__:
                    names = cls.__dict__.get("__slots__", ())
                    names = (names,) if isinstance(names, str) else names
                    for name in names:
                        if name not in ("__dict__", "__weakref__") and hasattr(value, name):
                            mutable = True
                            children.append(getattr(value, name))
            if mutable and key in seen:
                raise ScopeDenied()
            for child in children:
                audit(child)
        for cloned in handlers:
            audit(cloned)
    if replace_https:
        context = ReadOnlyTLS(ssl_context) if request_guard is not None else ssl_context
        handlers.append(_https_handler_cls(context=context))
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
                import http.client
                expected_wire = [None]
                expected_request = [None]
                request_dict = urllib.request.Request.__dict__["__dict__"]
                connection_dict = http.client.HTTPConnection.__dict__["__dict__"]
                owned_sockets = []
                active_connection = [None]
                def effect_guard(data=None, socket=None):
                    request_guard(request, final=True)
                    connection = active_connection[0]
                    parsed = urllib.parse.urlsplit(request.full_url)
                    if connection is None or (getattr(connection, "host", None), getattr(connection, "port", None)) != (
                            parsed.hostname, parsed.port or _DEFAULT_PORTS[parsed.scheme]):
                        raise ScopeDenied()
                    if getattr(connection, "_tunnel_host", None):
                        raise ScopeDenied()
                    if data is not None:
                        # Preserve native framing but attest its finished bytes. No
                        # body, duplicate headers, alternate method/path or key can
                        # cross this boundary after an encoder/send callback.
                        if type(data) is not bytes or expected_wire[0] is None:
                            raise ScopeDenied()
                        head, sep, body = data.partition(b"\r\n\r\n")
                        if sep != b"\r\n\r\n" or body:
                            raise ScopeDenied()
                        lines = head.decode("latin1").split("\r\n")
                        if lines[0] != "GET " + parsed.path + " HTTP/1.1":
                            raise ScopeDenied()
                        wire = {}
                        for line in lines[1:]:
                            name, separator, value = line.partition(":")
                            name = name.lower()
                            if not separator or name in wire:
                                raise ScopeDenied()
                            wire[name] = value.lstrip(" ")
                        if wire != expected_wire[0]:
                            raise ScopeDenied()
                    request_guard(request, final=True)
                    # The final Request callback has now finished. Read native
                    # instance dictionaries through retained descriptors, with no
                    # further dynamic methods/properties before the byte effect.
                    state = connection_dict.__get__(connection)
                    if (type(state.get("host")) is not str or type(state.get("port")) is not int
                            or (state["host"], state["port"]) != (parsed.hostname,
                                parsed.port or _DEFAULT_PORTS[parsed.scheme])
                            or state.get("_tunnel_host") or state.get("sock") is not socket):
                        raise ScopeDenied()
                    state = request_dict.__get__(request)
                    expected = expected_request[0]
                    if expected is None or state.get("_data") is not None or state.get("_tunnel_host"):
                        raise ScopeDenied()
                    for name in ("_full_url", "type", "host", "selector"):
                        if type(state.get(name)) is not str or state[name] != expected[name]:
                            raise ScopeDenied()
                    method = state.get("method")
                    if method is not None and (type(method) is not str or method != "GET"):
                        raise ScopeDenied()
                    for name in ("headers", "unredirected_hdrs"):
                        headers = state.get(name)
                        if (type(headers) is not dict
                                or any(type(k) is not str or type(v) is not str for k, v in headers.items())
                                or headers != expected[name]):
                            raise ScopeDenied()
                class OwnedSocket:
                    def __init__(self, sock):
                        self._sock = sock
                        owned_sockets.append(sock)
                    def __getattr__(self, name):
                        return getattr(self._sock, name)
                    def sendall(self, data, *a, **k):
                        target = self._sock.sendall
                        effect_guard(data, socket=self)
                        return target(data, *a, **k)
                    def send(self, data, *a, **k):
                        target = self._sock.send
                        effect_guard(data, socket=self)
                        return target(data, *a, **k)
                    def close(self):
                        return self._sock.close()
                native_class = http_class
                if isinstance(http_class, type) and issubclass(http_class, http.client.HTTPConnection):
                    class NativeConnection(http_class):
                        def __init__(self, *a, **k):
                            # Track before constructor callbacks, including failed
                            # constructors that already own a socket.
                            active_connection[0] = self
                            connections.append(self)
                            super().__init__(*a, **k)
                        def __setattr__(self, name, value):
                            if name == "sock" and value is not None and not isinstance(value, OwnedSocket):
                                value = OwnedSocket(value)
                            super().__setattr__(name, value)
                    native_class = NativeConnection
                class Connection:
                    def __init__(self, host, *ctor_args, **ctor_kwargs):
                        connection = native_class(host, *ctor_args, **ctor_kwargs)
                        object.__setattr__(self, "_connection", connection)
                        if connection not in connections:
                            connections.append(connection)
                        active_connection[0] = connection
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
                        # Freeze plain header values after all conversions and
                        # then recheck retained authority. Native encoders still
                        # receive the original values and run normally.
                        expected = {str(n).lower(): str(v) for n, v in canonical.items()}
                        expected.setdefault("host", parsed.netloc)
                        expected.setdefault("accept-encoding", "identity")
                        expected_wire[0] = expected
                        state = request_dict.__get__(request)
                        expected_request[0] = {name: state[name] for name in ("_full_url", "type", "host", "selector")}
                        expected_request[0].update({name: dict(state[name]) for name in ("headers", "unredirected_hdrs")})
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
                                settle(connection)
                            for sock in owned_sockets:
                                settle(sock)
                    response.close = close
                    return response
                except BaseException as error:
                    for response in responses:
                        settle(response)
                    for connection in connections:
                        settle(connection)
                    for sock in owned_sockets:
                        settle(sock)
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
