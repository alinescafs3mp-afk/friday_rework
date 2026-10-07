"""Actual SDK status-error repr plus native persistence, synthetic transport."""
import ast
import json

import pytest

from test_web_runtime_runner import M
import test_web_stream_native as native


PERIOD = 'JQ"\\яя_abcDEFghiJKLmnoPQRstuVWXyz01_'


@pytest.mark.parametrize('key,overlap', [
    (PERIOD + PERIOD[:10], PERIOD),
    ("KQ'\\яя_abcDEFghiJKLmnoPQRstuVWXyz01_tail", ''),
    ("MQ'\"\\\tя\x00_abcDEFghiJKLmnoPQRstuVWXyz01_tail", ''),
])
@pytest.mark.parametrize('complete', [False, True])
def test_real_sdk_repr_error_has_no_recoverable_echo(tmp_path, monkeypatch, capsys,
                                                   key, overlap, complete):
    echo = key if complete else key[:17]
    native.test_real_native_agent_reaches_web_and_cleanup(
        tmp_path, monkeypatch, capsys, 'explicit', 'retry_4xx', key, overlap,
        sdk_error_echo=echo)
    dumps = list((tmp_path/'profile/sessions').glob('request_dump_*.json'))
    assert dumps
    for path in dumps:
        error = json.loads(path.read_text())['error']
        message = error['message']
        assert message.startswith('Error code: 400 - ')
        # Parse the actual representation, not just a whole-token string scan.
        recovered = ast.literal_eval(message.split(' - ', 1)[1])
        actual = recovered['error']['message']
        assert actual == 'synthetic terminal ' + (
            '[REDACTED]' if complete else '[REDACTED_PARTIAL]')
        assert recovered['error']['type'] == 'invalid_request_error'
        assert recovered['error']['code'] == 'fixture_invalid_request'
        assert error['body']['message'] == actual
        assert json.loads(error['response_text'])['error']['message'] == actual


@pytest.mark.parametrize('quote', ["'", '"'])
@pytest.mark.parametrize('ascii_only', [False, True])
@pytest.mark.parametrize('order', ['repr', 'repr_json', 'json_repr', 'json_repr_json'])
def test_repr_forms_preserve_original_character_threshold_and_shared_overlap(
        quote, ascii_only, order):
    first = 'ZQ"\\яя_abcdefghijkLMNOP'
    second = first[-12:] + '_qrstUVWXYZ'
    def transform(value):
        if order.startswith('json_'):
            value = json.dumps(value, ensure_ascii=ascii_only)[1:-1]
        value = M['_repr_string_body'](value, quote, ascii_only)
        if order.endswith('_json'):
            value = json.dumps(value, ensure_ascii=ascii_only)[1:-1]
        return value
    echo = first + second[12:]
    assert M['_redact']('safe ' + transform(echo) + ' end', (first, second)) == 'safe [REDACTED] end'
    assert M['_redact'](transform(first[:7]), (first,)) == transform(first[:7])
    assert M['_redact'](transform(first[:8]), (first,)) == '[REDACTED_PARTIAL]'
    assert M['_redact'](transform(first), (first,)) == '[REDACTED]'


@pytest.mark.parametrize('value', [
    'a"b\\cя\t\n\r\x00\x7f\u2028', "a'b\\cя", "a'\"b\\cя", 'ASCII_plain',
])
def test_repr_transform_matches_real_python_literal(value):
    for render in (repr, ascii):
        actual = render(value)
        assert M['_repr_string_body'](value, actual[0], render is ascii) == actual[1:-1]
        for quote in ("'", '"'):
            assert ast.literal_eval(quote + M['_repr_string_body'](value, quote, render is ascii) + quote) == value
