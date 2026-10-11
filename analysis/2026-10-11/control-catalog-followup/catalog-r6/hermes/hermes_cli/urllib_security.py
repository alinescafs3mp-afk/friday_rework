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
        import types
        request_dict = urllib.request.Request.__dict__["__dict__"]
        original_state = request_dict.__get__(req)
        admission = (original_state.get("_hermes_catalog_admission")
                     if type(original_state) is dict and all(type(key) is str for key in original_state)
                     else None)
        admitted = type(admission) is types.FunctionType and admission in _CATALOG_ADMISSIONS
        # Let urllib enforce status/method semantics first (notably 307/308).
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if admitted:
            state = request_dict.__get__(req)
            if (type(state) is not dict or any(type(key) is not str for key in state)
                    or state.get("_hermes_catalog_admission") is not admission):
                from hermes_cli.friday_user_scope import ScopeDenied
                raise ScopeDenied()
            if redirected is not None:
                state = request_dict.__get__(redirected)
                if (type(state) is not dict or any(type(key) is not str for key in state)
                        or (state.get("_hermes_catalog_admission") is not None
                            and state.get("_hermes_catalog_admission") is not admission)):
                    from hermes_cli.friday_user_scope import ScopeDenied
                    raise ScopeDenied()
                state["_hermes_catalog_admission"] = admission
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
    import contextvars
    import http.client
    import threading
    # A callable factory may run inherited native connect before returning its
    # instance. Interpose that finite native function entry, with a context-local
    # callback; unrelated concurrent callers retain the original behavior.
    # This is an effect boundary, not a sandbox for arbitrary factory Python.
    registry = _bind_request_guard.__dict__.setdefault(
        "_constructor_connect_scope",
        (threading.RLock(), contextvars.ContextVar("catalog_constructor_connect", default=None), [0, None, None]))
    scope_lock, connect_context, scope_state = registry
    from contextlib import contextmanager
    @contextmanager
    def constructor_connect_scope(prepare):
        with scope_lock:
            if scope_state[0] == 0:
                import types
                native_connect = http.client.HTTPConnection.connect
                key = "_hermes_catalog_constructor_connect_scope"
                if (type(native_connect) is not types.FunctionType or native_connect.__closure__
                        or key in native_connect.__dict__):
                    raise ScopeDenied()
                original_code = native_connect.__code__
                # Retain and execute the complete original stdlib body. Pin its
                # function entry as well as class lookup: callers may have saved
                # the original connect function before this constructor starts.
                native_body = types.FunctionType(original_code, native_connect.__globals__,
                    native_connect.__name__, native_connect.__defaults__, native_connect.__closure__)
                native_body.__kwdefaults__ = native_connect.__kwdefaults__
                boundary = (connect_context, native_body)
                def dispatch(connection):
                    import http.client as native_http
                    context, body = native_http.HTTPConnection.connect.__dict__["_hermes_catalog_constructor_connect_scope"]
                    callback = context.get()
                    if callback is not None:
                        callback(connection)
                    return body(connection)
                native_connect.__dict__[key] = boundary
                native_connect.__code__ = dispatch.__code__
                scope_state[1:] = [(native_connect, original_code, boundary), dispatch.__code__]
            elif (http.client.HTTPConnection.connect is not scope_state[1][0]
                    or scope_state[1][0].__code__ is not scope_state[2]):
                raise ScopeDenied()
            scope_state[0] += 1
        token = connect_context.set(prepare)
        try:
            yield
        finally:
            connect_context.reset(token)
            with scope_lock:
                scope_state[0] -= 1
                if scope_state[0] == 0:
                    native_connect, original_code, boundary = scope_state[1]
                    key = "_hermes_catalog_constructor_connect_scope"
                    intact = (http.client.HTTPConnection.connect is native_connect
                        and native_connect.__code__ is scope_state[2]
                        and native_connect.__dict__.get(key) is boundary)
                    native_connect.__code__ = original_code
                    native_connect.__dict__.pop(key, None)
                    http.client.HTTPConnection.connect = native_connect
                    scope_state[1:] = [None, None]
                    if not intact:
                        raise ScopeDenied()

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
                request_dict = urllib.request.Request.__dict__["__dict__"]
                original_state = request_dict.__get__(request)
                if type(original_state) is not dict or any(type(key) is not str for key in original_state):
                    raise ScopeDenied()
                original_carrier = original_state.get("_hermes_catalog_admission")
                request_guard(request, final=True)
                connections = []
                responses = []
                import http.client
                expected_wire = [None]
                expected_request = [None]
                request_dict = urllib.request.Request.__dict__["__dict__"]
                connection_dict = http.client.HTTPConnection.__dict__["__dict__"]
                def settle_connection(connection):
                    try:
                        state = connection_dict.__get__(connection) if native_instance(connection, http.client.HTTPConnection) else None
                        if isinstance(state, dict):
                            clean = {key: value for key, value in dict.items(state) if type(key) is str}
                            sock = clean.get("sock")
                            prior_ids = (connection_prior_objects.get(id(connection), construction_prior_objects[0]) or (None,))[0]
                            if (sock is not None and type(sock) is not OwnedSocket
                                    and prior_ids is not None and id(sock) not in prior_ids
                                    and id(sock) not in raw_owners):
                                owned_sockets.append(sock)
                            clean["sock"] = None
                            retained_response = clean.get("_HTTPConnection__response")
                            if (retained_response is not None and prior_ids is not None
                                    and id(retained_response) in prior_ids):
                                clean["_HTTPConnection__response"] = None
                            connection_dict.__set__(connection, clean)
                        # The original owned close keeps native adapter and
                        # instrumentation semantics; its socket and borrowed
                        # response have already been safely detached.
                        connection.close()
                    except BaseException:
                        logger.debug("catalog native connection cleanup failed", exc_info=True)
                owned_sockets = []
                owned_buffers = []
                active_connection = [None]
                first_sockets = {}
                socket_owners = {}
                socket_custody = {}
                raw_owners = {}
                connect_targets = {}
                connection_prior_objects = {}
                construction_prior_objects = [None]
                transport_closed = [False]
                # These validators use only exact built-in containers and
                # primitives. In particular, validate EVERY dictionary key
                # before a lookup: an alien key with a colliding hash can run
                # __eq__ even when the looked-up key is an ordinary string.
                def plain_dict(value):
                    if type(value) is not dict:
                        raise ScopeDenied()
                    for name in value:
                        if type(name) is not str:
                            raise ScopeDenied()
                    return value
                def plain_headers(value):
                    value = plain_dict(value)
                    for item in value.values():
                        if type(item) is not str:
                            raise ScopeDenied()
                    return value
                def plain_request_state():
                    state = plain_dict(request_dict.__get__(request))
                    for name in ("_full_url", "type", "host", "selector"):
                        if type(state.get(name)) is not str:
                            raise ScopeDenied()
                    for name in ("headers", "unredirected_hdrs"):
                        plain_headers(state.get(name))
                    return state
                expected_endpoint = [None]
                expected_carrier = [original_carrier]
                initial_state = plain_request_state()
                initial_url = urllib.parse.urlsplit(initial_state["_full_url"])
                expected_endpoint[0] = (initial_url.hostname, initial_url.port or _DEFAULT_PORTS[initial_url.scheme], initial_url.path)
                def effect_guard(data=None, socket=None, raw_socket=None):
                    if transport_closed[0]:
                        raise ScopeDenied()
                    # Complete parsing and all potentially dynamic callbacks
                    # BEFORE the final retained authority check.
                    request_guard(request, final=True)
                    connection = active_connection[0]
                    if connection is None:
                        raise ScopeDenied()
                    connection_state = plain_dict(connection_dict.__get__(connection))
                    connection_tunnel = connection_state.get("_tunnel_host")
                    request_state = plain_dict(request_dict.__get__(request))
                    request_tunnel = request_state.get("_tunnel_host")
                    # Preserve inert false-valued policy sentinels, completing
                    # their callbacks before the last authority check. Later
                    # attest only their retained identity; never call bool late.
                    if connection_tunnel or request_tunnel or connection_tunnel:
                        raise ScopeDenied()
                    expected = expected_request[0]
                    endpoint = expected_endpoint[0]
                    carrier = expected_carrier[0]
                    if type(data) is not bytes:
                        raise ScopeDenied()
                    head, sep, body = data.partition(b"\r\n\r\n")
                    if sep != b"\r\n\r\n" or body:
                        raise ScopeDenied()
                    lines = head.decode("latin1").split("\r\n")
                    wire = {}
                    for line in lines[1:]:
                        name, separator, value = line.partition(":")
                        name = name.lower()
                        if not separator or name in wire:
                            raise ScopeDenied()
                        wire[name] = value.lstrip(" ")
                    request_guard(request, final=True)
                    # No user dispatch from here through the retained send
                    # target invocation: descriptors are native, dictionary
                    # types/keys and BOTH sides of equality are exact builtins.
                    wire_expected = plain_headers(expected_wire[0])
                    plain_dict(expected)
                    for name in ("_full_url", "type", "host", "selector"):
                        if type(expected.get(name)) is not str:
                            raise ScopeDenied()
                    for name in ("headers", "unredirected_hdrs"):
                        plain_headers(expected.get(name))
                    if type(endpoint) is not tuple or len(endpoint) != 3:
                        raise ScopeDenied()
                    hostname, port, path = endpoint
                    if type(hostname) is not str or type(port) is not int or type(path) is not str:
                        raise ScopeDenied()
                    if lines[0] != "GET " + path + " HTTP/1.1" or wire != wire_expected:
                        raise ScopeDenied()
                    if active_connection[0] is not connection:
                        raise ScopeDenied()
                    state = plain_dict(connection_dict.__get__(connection))
                    if (type(state.get("host")) is not str or type(state.get("port")) is not int
                            or state["host"] != hostname or state["port"] != port
                            or state.get("_tunnel_host") is not connection_tunnel
                            or state.get("sock") is not socket
                            or first_sockets.get(id(connection)) is not socket):
                        raise ScopeDenied()
                    if type(socket) is not OwnedSocket:
                        raise ScopeDenied()
                    socket_state = plain_dict(owned_socket_dict.__get__(socket))
                    custody = socket_custody.get(id(socket))
                    if (custody is None or custody[0] is not socket
                            or custody[1] is not raw_socket or custody[2] is not connection
                            or raw_owners.get(id(raw_socket)) is not connection
                            or socket_state.get("_sock") is not custody[1]):
                        raise ScopeDenied()
                    state = plain_request_state()
                    if (state.get("_data") is not None
                            or state.get("_tunnel_host") is not request_tunnel
                            or state.get("_hermes_catalog_admission") is not carrier):
                        raise ScopeDenied()
                    for name in ("_full_url", "type", "host", "selector"):
                        if state[name] != expected[name]:
                            raise ScopeDenied()
                    method = state.get("method")
                    if method is not None and (type(method) is not str or method != "GET"):
                        raise ScopeDenied()
                    for name in ("headers", "unredirected_hdrs"):
                        if state[name] != expected[name]:
                            raise ScopeDenied()
                class OwnedSocket:
                    def __init__(self, sock, connection):
                        self._sock = sock
                        socket_custody[id(self)] = (self, sock, connection)
                        raw_owners[id(sock)] = connection
                        owned_sockets.append(sock)
                    def __getattr__(self, name):
                        custody = socket_custody.get(id(self))
                        if transport_closed[0] or custody is None or custody[0] is not self:
                            raise ScopeDenied()
                        state = plain_dict(owned_socket_dict.__get__(self))
                        if state.get("_sock") is not custody[1]:
                            raise ScopeDenied()
                        if name == "makefile":
                            _raw, target = send_target(self, name)
                            def makefile(*a, **k):
                                if any(type(value) not in (str, int, bool, type(None)) for value in (*a, *k.values())):
                                    raise ScopeDenied()
                                socket_operation_guard(self, custody)
                                buffer = target(*a, **k)
                                prior_ids = connection_prior_objects.get(id(custody[2]), (None,))[0]
                                if prior_ids is None or id(buffer) in prior_ids:
                                    raise ScopeDenied()
                                owned_buffers.append(buffer)
                                socket_operation_guard(self, custody)
                                return buffer
                            return makefile
                        return getattr(custody[1], name)
                    def sendall(self, data, *a, **k):
                        if len(a) > 1 or k or (a and type(a[0]) is not int):
                            raise ScopeDenied()
                        sock, target = send_target(self, "sendall")
                        effect_guard(data, socket=self, raw_socket=sock)
                        return target(data, *a, **k)
                    def send(self, data, *a, **k):
                        if len(a) > 1 or k or (a and type(a[0]) is not int):
                            raise ScopeDenied()
                        sock, target = send_target(self, "send")
                        effect_guard(data, socket=self, raw_socket=sock)
                        return target(data, *a, **k)
                    def close(self):
                        custody = socket_custody.get(id(self))
                        if custody is not None and custody[0] is self:
                            return custody[1].close()
                owned_socket_dict = OwnedSocket.__dict__["__dict__"]
                def socket_operation_guard(socket, custody):
                    if transport_closed[0]:
                        raise ScopeDenied()
                    request_guard(request, final=True)
                    state = plain_dict(owned_socket_dict.__get__(socket))
                    connection_state = plain_dict(connection_dict.__get__(custody[2]))
                    endpoint = expected_endpoint[0]
                    if (socket_custody.get(id(socket)) is not custody
                            or state.get("_sock") is not custody[1]
                            or active_connection[0] is not custody[2]
                            or raw_owners.get(id(custody[1])) is not custody[2]
                            or (connection_state.get("sock") is not socket and connection_state.get("sock") is not None)
                            or type(endpoint) is not tuple or len(endpoint) != 3
                            or type(endpoint[0]) is not str or type(endpoint[1]) is not int
                            or type(connection_state.get("host")) is not str
                            or type(connection_state.get("port")) is not int
                            or connection_state["host"] != endpoint[0] or connection_state["port"] != endpoint[1]):
                        raise ScopeDenied()
                def send_target(socket, name):
                    import types
                    if transport_closed[0]:
                        raise ScopeDenied()
                    custody = socket_custody.get(id(socket))
                    if custody is None or custody[0] is not socket:
                        raise ScopeDenied()
                    # Resolve callbacks against the original owned raw handle,
                    # then attest both the callback receiver and backing identity.
                    sock = custody[1]
                    target = getattr(sock, name)
                    if type(target) not in (types.MethodType, types.BuiltinMethodType):
                        raise ScopeDenied()
                    receiver = target.__self__
                    if receiver is not sock:
                        prior_ids = connection_prior_objects.get(id(custody[2]), (None,))[0]
                        if (prior_ids is not None and id(receiver) not in prior_ids
                                and id(receiver) not in raw_owners):
                            owned_sockets.append(receiver)
                        raise ScopeDenied()
                    return sock, target
                def own_socket(connection, value):
                    if value is None:
                        return None
                    if transport_closed[0]:
                        raise ScopeDenied()
                    if socket_owners.get(id(value)) is connection:
                        custody = socket_custody.get(id(value))
                        if (custody is None or custody[0] is not value
                                or custody[2] is not connection
                                or plain_dict(owned_socket_dict.__get__(value)).get("_sock") is not custody[1]):
                            raise ScopeDenied()
                        return value
                    if (id(value) in connection_prior_objects.get(id(connection), ((), None))[0]
                            or id(value) in raw_owners or id(value) in socket_custody):
                        plain_dict(connection_dict.__get__(connection))["sock"] = None
                        raise ScopeDenied()
                    value = OwnedSocket(value, connection)
                    socket_owners[id(value)] = connection
                    first_sockets.setdefault(id(connection), value)
                    return value
                def read_socket(connection):
                    state = plain_dict(connection_dict.__get__(connection))
                    value = own_socket(connection, state.get("sock"))
                    state["sock"] = value
                    return value
                def connect_guard(connection, address, timeout, source_address):
                    import socket as native_socket
                    if transport_closed[0]:
                        raise ScopeDenied()
                    if (type(address) is not tuple or len(address) != 2
                            or type(address[0]) is not str or type(address[1]) is not int
                            or (timeout is not native_socket._GLOBAL_DEFAULT_TIMEOUT
                                and timeout is not None and type(timeout) not in (int, float))
                            or (source_address is not None and (type(source_address) is not tuple
                                or len(source_address) != 2 or type(source_address[0]) is not str
                                or type(source_address[1]) is not int))):
                        raise ScopeDenied()
                    state = plain_dict(connection_dict.__get__(connection))
                    tunnel = state.get("_tunnel_host")
                    if tunnel:
                        raise ScopeDenied()
                    request_guard(request, final=True)
                    # The connect audit and all user callbacks precede this
                    # attestation of the actual retained create-connection target.
                    state = plain_dict(connection_dict.__get__(connection))
                    record = connect_targets.get(id(connection))
                    endpoint = expected_endpoint[0]
                    request_state = plain_request_state()
                    if request_state.get("_hermes_catalog_admission") is not original_carrier:
                        raise ScopeDenied()
                    if (type(endpoint) is not tuple or len(endpoint) != 3
                            or type(endpoint[0]) is not str or type(endpoint[1]) is not int
                            or type(endpoint[2]) is not str or record is None
                            or record[0] is not connection or active_connection[0] is not connection
                            or state.get("_create_connection") is not record[2]
                            or type(state.get("host")) is not str or type(state.get("port")) is not int
                            or state["host"] != endpoint[0] or state["port"] != endpoint[1]
                            or address != endpoint[:2] or state.get("_tunnel_host") is not tunnel
                            or state.get("sock") is not None or id(connection) in first_sockets):
                        raise ScopeDenied()
                def bind_connect_target(connection):
                    import socket as native_socket
                    import types
                    state = plain_dict(connection_dict.__get__(connection))
                    retained = connect_targets.get(id(connection))
                    if retained is not None:
                        if retained[0] is not connection or state.get("_create_connection") is not retained[2]:
                            raise ScopeDenied()
                        return
                    target = state.get("_create_connection")
                    if type(target) not in (types.FunctionType, types.BuiltinFunctionType,
                                            types.MethodType, types.BuiltinMethodType):
                        raise ScopeDenied()
                    def checked(address, timeout=native_socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
                        connect_guard(connection, address, timeout, source_address)
                        raw = target(address, timeout, source_address)
                        prior_ids = connection_prior_objects.get(id(connection), (None,))[0]
                        if prior_ids is None or id(raw) in prior_ids or id(raw) in raw_owners:
                            raise ScopeDenied()
                        owned_sockets.append(raw)
                        connect_guard(connection, address, timeout, source_address)
                        return raw
                    connect_targets[id(connection)] = (connection, target, checked)
                    state["_create_connection"] = checked
                def read_connect_target(connection):
                    record = connect_targets.get(id(connection))
                    state = plain_dict(connection_dict.__get__(connection))
                    if record is None or record[0] is not connection or state.get("_create_connection") is not record[2]:
                        raise ScopeDenied()
                    return record[2]
                native_class = http_class
                owned_native_class = None
                def native_instance(value, cls):
                    return any(base is cls for base in type.__getattribute__(type(value), "__mro__"))
                adopted_connections = set()
                def adopt_native_instance(connection):
                    if id(connection) in adopted_connections:
                        return
                    state = plain_dict(connection_dict.__get__(connection))
                    sock = state.get("sock")
                    if sock is not None and id(sock) in connection_prior_objects[id(connection)][0]:
                        # The connection itself is new and owned; the
                        # socket is foreign. Detach it before owned
                        # cleanup, without changing or closing the sock.
                        state["sock"] = None
                        raise ScopeDenied()
                    class AdoptedConnection(type(connection)):
                        __slots__ = ()
                        def __getattribute__(self, name):
                            if name == "sock":
                                return read_socket(self)
                            if name == "_create_connection":
                                return read_connect_target(self)
                            return super().__getattribute__(name)
                        def __setattr__(self, name, value):
                            if name == "sock":
                                value = own_socket(self, value)
                            super().__setattr__(name, value)
                    try:
                        object.__setattr__(connection, "__class__", AdoptedConnection)
                    except (TypeError, AttributeError) as error:
                        raise ScopeDenied() from error
                    state = plain_dict(connection_dict.__get__(connection))
                    sock = state.get("sock")
                    if sock is not None:
                        state["sock"] = own_socket(connection, sock)
                    adopted_connections.add(id(connection))
                def prepare_constructor_connect(connection):
                    # Entered BEFORE stdlib's connect audit and before target
                    # lookup, for classes and callable/lambda factories alike.
                    prior = None
                    try:
                        prior = construction_prior_objects[0]
                        if (transport_closed[0] or prior is None
                                or not native_instance(connection, http.client.HTTPConnection)
                                or id(connection) in prior[0]
                                or (active_connection[0] is not None and active_connection[0] is not connection)):
                            raise ScopeDenied()
                        if not any(connection is owned for owned in connections):
                            connections.append(connection)
                        active_connection[0] = connection
                        connection_prior_objects[id(connection)] = prior
                        # Pin BEFORE adoption's __init_subclass__ callbacks too.
                        bind_connect_target(connection)
                        if not (owned_native_class is not None and native_instance(connection, owned_native_class)):
                            # Pin target lookup as well as invocation before the
                            # native audit; a replaced instance callable must not
                            # bypass checked() by replacing its dictionary slot.
                            adopt_native_instance(connection)
                        bind_connect_target(connection)
                    finally:
                        prior = None
                if isinstance(http_class, type) and issubclass(http_class, http.client.HTTPConnection):
                    class NativeConnection(http_class):
                        def __init__(self, *a, **k):
                            # A custom __new__ may return a cached instance
                            # even of this locally owned subclass. Refuse before
                            # tracking, constructor mutation or cleanup ownership.
                            prior_ids = (construction_prior_objects[0] or (None,))[0]
                            if prior_ids is None or id(self) in prior_ids:
                                raise ScopeDenied()
                            # Track before constructor callbacks, including failed
                            # constructors that already own a socket.
                            active_connection[0] = self
                            connections.append(self)
                            connection_prior_objects[id(self)] = construction_prior_objects[0]
                            super().__init__(*a, **k)
                        def __getattribute__(self, name):
                            if name == "sock":
                                return read_socket(self)
                            if name == "_create_connection":
                                return read_connect_target(self)
                            return super().__getattribute__(name)
                        def __setattr__(self, name, value):
                            if name == "sock":
                                value = own_socket(self, value)
                            super().__setattr__(name, value)
                    native_class = NativeConnection
                    owned_native_class = NativeConnection
                class Connection:
                    def __init__(self, host, *ctor_args, **ctor_kwargs):
                        import gc
                        # A factory may return a cached or foreign connection.
                        # Capture object identities before it runs and never
                        # adopt, mutate, or close such a pre-existing handle.
                        # Retain the snapshot objects, not only their IDs: a
                        # freed object ID can otherwise be reused by a new
                        # socket and falsely label it foreign. Release the
                        # snapshot when this finite owned transport closes.
                        prior_objects = preexisting = connection = value = state = sock = None
                        try:
                            prior_objects = gc.get_objects()
                            preexisting = {id(value) for value in prior_objects}
                            construction_prior_objects[0] = (preexisting, prior_objects)
                            try:
                                with constructor_connect_scope(prepare_constructor_connect):
                                    connection = native_class(host, *ctor_args, **ctor_kwargs)
                            except BaseException:
                                # A callable can fail after allocating native
                                # handles. Discover only objects born during this
                                # finite invocation, preserving foreign connections
                                # and foreign sockets while settling owned handles.
                                for value in gc.get_objects():
                                    if id(value) not in preexisting and native_instance(value, http.client.HTTPConnection):
                                        state = connection_dict.__get__(value)
                                        if type(state) is dict and all(type(key) is str for key in state):
                                            sock = state.get("sock")
                                            if sock is not None and id(sock) in preexisting:
                                                state["sock"] = None
                                        settle_connection(value)
                                raise
                            adopt = (native_instance(connection, http.client.HTTPConnection)
                                and not (owned_native_class is not None
                                    and native_instance(connection, owned_native_class)))
                            if id(connection) in preexisting or (native_instance(connection, http.client.HTTPConnection) and not gc.is_tracked(connection)):
                                raise ScopeDenied()
                            if active_connection[0] is not None and active_connection[0] is not connection:
                                # Refuse a factory's second returned instance,
                                # while still settling that newly born handle.
                                if not any(connection is owned for owned in connections):
                                    connections.append(connection)
                                connection_prior_objects[id(connection)] = (preexisting, prior_objects)
                                raise ScopeDenied()
                            object.__setattr__(self, "_connection", connection)
                            if not any(connection is owned for owned in connections):
                                connections.append(connection)
                            active_connection[0] = connection
                            connection_prior_objects[id(connection)] = (preexisting, prior_objects)
                            # Callable connection factories are a supported stdlib
                            # seam. Adopt the returned native instance into an owned
                            # layout-compatible subclass so its later connect/send
                            # sock assignments use the same effect boundary. Custom
                            # classes and the installed opener stay intact; the
                            # scoped stdlib connect dispatcher has been restored.
                            if native_instance(connection, http.client.HTTPConnection):
                                bind_connect_target(connection)
                            if adopt:
                                adopt_native_instance(connection)
                            if native_instance(connection, http.client.HTTPConnection):
                                bind_connect_target(connection)
                                response_class = getattr(connection, "response_class")
                                if isinstance(response_class, type) and issubclass(response_class, http.client.HTTPResponse):
                                    class OwnedResponse(response_class):
                                        def __init__(self, *a, **k):
                                            # HTTPResponse's base finalizer reads
                                            # fp even when makefile refuses during
                                            # construction. Initialize before any
                                            # constructor callback and own the
                                            # partial response through cleanup.
                                            object.__setattr__(self, "fp", None)
                                            responses.append(self)
                                            super().__init__(*a, **k)
                                    connection.response_class = OwnedResponse
                            request_guard(request, final=True)
                        finally:
                            prior_objects = preexisting = connection = value = state = sock = None
                            construction_prior_objects[0] = None
                    def close(self):
                        settle_connection(self._connection)
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
                        state = plain_request_state()
                        expected_request[0] = {name: state[name] for name in ("_full_url", "type", "host", "selector")}
                        expected_request[0].update({name: dict(state[name]) for name in ("headers", "unredirected_hdrs")})
                        if state.get("_hermes_catalog_admission") is not original_carrier:
                            raise ScopeDenied()
                        request_guard(request, final=True)
                        connection.request(method, url, data, headers, **options)
                        request_guard(request, final=True)
                    def getresponse(self):
                        request_guard(request, final=True)
                        response = self._connection.getresponse()
                        prior_ids = connection_prior_objects.get(id(self._connection), (None,))[0]
                        if prior_ids is None or id(response) in prior_ids:
                            raise ScopeDenied()
                        responses.append(response)
                        try:
                            request_guard(request, final=True)
                        except BaseException:
                            settle(response)
                            raise
                        return response
                def finish_transport():
                    if transport_closed[0]:
                        return
                    transport_closed[0] = True
                    try:
                        for connection in connections:
                            settle_connection(connection)
                        for wrapper, raw, connection in tuple(socket_custody.values()):
                            state = owned_socket_dict.__get__(wrapper)
                            if isinstance(state, dict):
                                backing = next((value for key, value in dict.items(state)
                                                if type(key) is str and key == "_sock"), None)
                                prior_ids = connection_prior_objects.get(id(connection), (None,))[0]
                                if (backing is not None and backing is not raw and prior_ids is not None
                                        and id(backing) not in prior_ids and id(backing) not in raw_owners):
                                    settle(backing)
                            settle(raw)
                        for sock in owned_sockets:
                            settle(sock)
                        for buffer in owned_buffers:
                            settle(buffer)
                    finally:
                        connection_prior_objects.clear()
                        construction_prior_objects[0] = None
                        first_sockets.clear()
                        socket_owners.clear()
                        socket_custody.clear()
                        raw_owners.clear()
                        connect_targets.clear()
                        adopted_connections.clear()
                        connections.clear()
                        owned_sockets.clear()
                        owned_buffers.clear()
                        responses.clear()
                try:
                    response = _native(Connection, request, *args, **kwargs)
                    request_guard(request, final=True)
                    native_close = response.close
                    def close():
                        try:
                            return native_close()
                        finally:
                            finish_transport()
                    response.close = close
                    return response
                except BaseException as error:
                    for response in responses:
                        settle(response)
                    finish_transport()
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
    request_dict = urllib.request.Request.__dict__["__dict__"]
    def carrier_state(value):
        state = request_dict.__get__(value)
        if type(state) is not dict or any(type(key) is not str for key in state):
            raise ScopeDenied()
        return state
    admission = carrier_state(request).get("_hermes_catalog_admission")
    if admission not in _CATALOG_ADMISSIONS:
        raise ScopeDenied()
    def check(value=None, *, final=False):
        target = request if value is None else value
        def same_carrier():
            if (carrier_state(request).get("_hermes_catalog_admission") is not admission
                    or carrier_state(target).get("_hermes_catalog_admission") is not admission):
                raise ScopeDenied()
        same_carrier()
        admission(value, final=final)
        same_carrier()
        if callback is not None and callback is not admission:
            callback(value, final=final)
            same_carrier()
            admission(value, final=final)
            same_carrier()
    check(request)
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
