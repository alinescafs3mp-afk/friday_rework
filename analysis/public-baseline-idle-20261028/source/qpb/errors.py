"""Shared failures. Importing this module does not open a socket."""


class TransportError(RuntimeError):
    def __init__(self, message: str, *, sent: bool, status: int | None = None):
        super().__init__(message)
        self.sent = sent
        self.status = status


class OutcomeUnknownError(RuntimeError):
    def __init__(self, message, *, partial_raw=None, timing=None, request_id=None):
        super().__init__(message)
        self.partial_raw = partial_raw
        self.timing = timing
        self.request_id = request_id


class ProtocolDiagnostic(RuntimeError):
    pass
