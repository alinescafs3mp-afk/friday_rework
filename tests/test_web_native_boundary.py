"""Native lossy parsing and live-key diagnostic boundaries; synthetic HTTP only."""
import ast
import json
from types import SimpleNamespace

import pytest
import requests

from test_web_runtime_runner import M
import test_web_stream_native as native


KEY = '😀𝄞\u2028\u2029\b\f\v\rABCDEFGH_secret'


def _strings(value):
    if isinstance(value, str):
        yield value
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return
        if decoded != value:
            yield from _strings(decoded)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


@pytest.mark.parametrize('key', [KEY, "LQ'\"\\\tя\x00_abcDEFghiJKLmnoPQRstuVWXyz01_tail"])
@pytest.mark.parametrize('complete,nested', [(False, False), (True, False), (False, True), (True, True)])
def test_native_lossy_search_and_repaired_live_key_are_concealed(
        key, complete, nested, tmp_path, monkeypatch, capsys):
    echo = key if complete else key[:17]
    if nested:
        echo = json.dumps(echo, ensure_ascii=True)[1:-1]
    native.test_real_native_agent_reaches_web_and_cleanup(
        tmp_path, monkeypatch, capsys, 'explicit', 'retry_4xx', key, '', sdk_error_echo=echo,
        sdk_error_complete=complete)
    dumps = list((tmp_path/'profile/sessions').glob('request_dump_*.json'))
    assert dumps
    for path in dumps:
        record = json.loads(path.read_text())
        assert record['request']['headers']['Authorization'] == 'Bearer [REDACTED]'
        error = record['error']
        actual = ast.literal_eval(error['message'].split(' - ', 1)[1])['error']['message']
        assert actual == 'synthetic terminal ' + ('[REDACTED]' if complete else '[REDACTED_PARTIAL]')
        assert error['body']['message'] == actual
        assert json.loads(error['response_text'])['error']['message'] == actual
    # Independently scan every original eight-character window, including
    # interior/suffix fragments, through recursively decoded retained values.
    chunks = {key[i:i+8] for i in range(len(key)-7)}
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert not any(chunk in value for value in _strings(path.read_text(errors='replace'))
                           for chunk in chunks), str(path)


def test_actual_mcp_response_seam_preserves_scope_errors_schema_and_cleanup(tmp_path, monkeypatch, capsys):
    base = M['Native']
    calls = []
    class Probe(base):
        def open(self, *args):
            super().open(*args)
            from plugins.web import keyless_mcp as km
            from hermes_constants import set_hermes_home_override, reset_hermes_home_override
            # Genuine parser and error path, before HTTP [:300], splitlines,
            # strip, search join, extract truncation and full-text spill.
            for shape in ('json', 'sse', 'http_error', 'rpc_error', 'tool_error'):
                text = 'Keep Cyrillic я and URL https://docs.example/api : '+KEY+' end'
                payload = {'jsonrpc':'2.0', 'id':1, 'result':{'content':[{'type':'text','text':text}]}}
                if shape == 'rpc_error':
                    payload = {'error': {'code': -32000, 'message': text}}
                if shape == 'tool_error':
                    payload['result']['isError'] = True
                body = json.dumps(payload, ensure_ascii=False)
                if shape == 'sse':
                    body = 'event: message\r\ndata: '+body+'\r\n\r\n'
                if shape == 'http_error':
                    body = 'x'*290 + KEY + ' end'
                response = SimpleNamespace(status_code=429 if shape=='http_error' else 200,
                    headers={'Content-Type':'text/event-stream; charset=utf-8'}, content=body.encode())
                assert '[REDACTED]' in km._response_text(response)
                token = set_hermes_home_override(tmp_path/'foreign-profile')
                try:
                    assert km._response_text(response) == body
                finally:
                    reset_hermes_home_override(token)
                with monkeypatch.context() as patch:
                    patch.setattr(requests, 'post', lambda *a, **kw: response)
                    if shape in ('json','sse'):
                        assert km.mcp_call(km.EXA_MCP_URL, 'web_search_exa', {}) == text.replace(KEY, '[REDACTED]')
                    else:
                        with pytest.raises(km.KeylessMCPError) as caught:
                            km.mcp_call(km.EXA_MCP_URL, 'web_fetch_exa', {})
                        assert KEY not in str(caught.value)
                        if shape == 'http_error':
                            assert str(caught.value).startswith('HTTP 429: ')
                        else:
                            assert str(caught.value) == text.replace(KEY, '[REDACTED]')
                calls.append(shape)
            assert self.agent._mask_api_key_for_logs(KEY.encode('ascii','ignore').decode()) == '[REDACTED]'
            assert self.agent._mask_api_key_for_logs('short') == '[REDACTED]'
            assert self.agent._mask_api_key_for_logs(None) is None
            def forbidden():
                pytest.fail('diagnostics must not invoke credential callbacks')
            assert self.agent._mask_api_key_for_logs(forbidden) == '<entra-id-bearer>'
            return self
    monkeypatch.setitem(M, 'Native', Probe)
    native.test_real_native_agent_reaches_web_and_cleanup(
        tmp_path, monkeypatch, capsys, 'explicit', 'retry_4xx', KEY, '')
    assert calls == ['json', 'sse', 'http_error', 'rpc_error', 'tool_error']


@pytest.mark.parametrize('surface', ['response', 'mask'])
def test_cleanup_refuses_foreign_replacement_of_new_boundaries(surface):
    obj = M['Native']()
    original, ours, foreign = (lambda value: value for _ in range(3))
    if surface == 'response':
        obj.keyless_module = SimpleNamespace(_response_text=foreign)
        obj.old_response_text, obj.response_redactor = original, ours
    else:
        obj.agent = SimpleNamespace(_mask_api_key_for_logs=foreign, close=lambda: None)
        obj.had_debug_mask = False
        obj.old_debug_mask, obj.debug_mask = None, ours
    with pytest.raises(M['Refused'], match='native_cleanup_unconfirmed'):
        obj.close()
    assert (obj.keyless_module._response_text if surface=='response'
            else obj.agent._mask_api_key_for_logs) is foreign
