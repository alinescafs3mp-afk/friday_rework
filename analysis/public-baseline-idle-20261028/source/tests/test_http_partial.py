import unittest
from unittest.mock import patch

from qpb.httpclient import UrllibTransport
from qpb.errors import OutcomeUnknownError


class PartialHTTPTests(unittest.TestCase):
    def post(self, payload, *, lost_after=True):
        class Response:
            status = 200
            lines = iter(payload.splitlines(keepends=True))
            def readline(self):
                try:
                    return next(self.lines)
                except StopIteration:
                    if lost_after:
                        raise OSError("fixture read failure")
                    return b""
        class Connection:
            def __init__(self, *args, **kwargs): pass
            def connect(self): pass
            def putrequest(self, *args): pass
            def putheader(self, *args): pass
            def endheaders(self): pass
            def send(self, *args): pass
            def close(self): pass
            def getresponse(self): return Response()
        with patch("qpb.httpclient.HTTPConnection", Connection):
            return UrllibTransport().post("http://127.0.0.1:9/v1", {}, {"rid": "qpb-owned"}, 1, lambda: None)

    def test_lost_partial_stream_keeps_exact_available_bytes_and_namespace(self):
        raw = b'data: {"id":"qpb-owned","choices":[{"delta":{"content":"partial"}}]}\n\n'
        with self.assertRaises(OutcomeUnknownError) as caught:
            self.post(raw)
        self.assertEqual(caught.exception.partial_raw, raw.decode())
        self.assertEqual(caught.exception.request_id, "qpb-owned")
        self.assertGreaterEqual(caught.exception.timing["wall_s"], 0)

    def test_terminal_content_survives_lost_usage_and_done_without_repeat(self):
        raw = (b'data: {"id":"qpb-owned","choices":[{"delta":{"content":"final"}}]}\n\n'
               b'data: {"id":"qpb-owned","choices":[{"finish_reason":"stop"}]}\n\n')
        result = self.post(raw)
        self.assertEqual(result["content"], "final")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertIsNone(result["usage"])
        self.assertFalse(result["usage_complete"])
        self.assertFalse(result["sse_done_received"])
        self.assertEqual(result["raw"], raw.decode())

    def test_malformed_tail_after_terminal_preserves_completed_generation(self):
        raw = (b'data: {"id":"qpb-owned","choices":[{"finish_reason":"length"}]}\n\n'
               b'data: {"usage":')
        result = self.post(raw, lost_after=False)
        self.assertEqual(result["finish_reason"], "length")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["trailing_stream_error"], "partial_event_after_terminal")


if __name__ == "__main__":
    unittest.main()
