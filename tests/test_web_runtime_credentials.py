"""Actual native runtime key repair/rollback; synthetic SDK HTTP only."""
import ast
import json
from pathlib import Path

import httpx
import pytest

from test_web_runtime_runner import M, prepared, digest, OriginalTask
import test_web_stream_native as fixture

KEYS = ('😀𝄞\u2028\u2029\b\f\v\rABCDEFGH_secret',
        'prefixXяAbC"\\LONG_secret_suffix_123456789',
        '  localяWHITESPACE_SUFFIX_123456789  ')


def strings(value, depth=0):
    if depth > 8:
        return
    if isinstance(value, str):
        yield value
        for decode in (json.loads, ast.literal_eval):
            try:
                decoded = decode(value)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                continue
            if decoded != value:
                yield from strings(decoded, depth+1)
        if ' - {' in value:
            yield from strings(value.split(' - ', 1)[1], depth+1)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(key, depth+1)
            yield from strings(item, depth+1)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from strings(item, depth+1)


def scan(value, keys):
    windows = {key[i:i+8] for key in keys for i in range(len(key)-7)}
    for text in strings(value):
        if any(window in text for window in windows):
            raise SystemExit('CREDENTIAL_DISCLOSURE_STOP')


@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('variant', ['retry_4xx', 'escaped_stream'])
def test_actual_live_key_all_sinks_and_native_rollback(key, variant, tmp_path, monkeypatch, capsys):
    base = M['Native']
    events = []
    class Probe(base):
        def open(self, *args):
            super().open(*args)
            self.initial_key = self.agent.api_key
            from agent.message_sanitization import _strip_non_ascii
            live = _strip_non_ascii(self.initial_key)
            assert live != self.initial_key
            assert key in self.credential_policy.values
            assert live in self.credential_policy.values
            send = httpx.Client.send
            def checked_send(client, request, **kw):
                actual = request.headers['Authorization'].removeprefix('Bearer ')
                assert actual == live
                assert self.agent.api_key == self.agent.client.api_key == self.agent._client_kwargs['api_key'] == live
                result = send(client, request, **kw)
                if result.status_code == 400:
                    assert result.json()['error']['message'] == 'synthetic terminal '+actual
                    events.append('actual_sdk_http400_echoes_sent_key')
                events.append('actual_sdk_sent_repaired_key')
                return result
            monkeypatch.setattr(httpx.Client, 'send', checked_send)
            return self

        def run(self, *args):
            from agent.turn_recovery import _repair_transport_credentials
            from agent.agent_runtime_helpers import try_recover_primary_transport
            from openai import APIConnectionError
            assert _repair_transport_credentials(self.agent)
            live = self.agent.api_key
            redactor = self.stream_redactor
            probe_text = redactor.feed('rollback probe safe '+live[:7])
            # Run the actual primary recovery branch; only its retry wait is
            # suppressed. No credential assignment or rebuild is mocked.
            with monkeypatch.context() as patch:
                import time
                patch.setattr(time, 'sleep', lambda seconds: None)
                assert try_recover_primary_transport(self.agent,
                    APIConnectionError(request=httpx.Request('POST', self.agent.base_url)),
                    retry_count=1, max_retries=1)
            assert self.agent.api_key == self.agent.client.api_key == self.agent._client_kwargs['api_key'] == self.initial_key
            assert self.stream_redactor is redactor
            probe_text += redactor.feed(live[7:]+'; '+self.initial_key+'; safe rollback complete; ')
            scan(probe_text+redactor.tail(), (key, self.initial_key, live))
            events.append('actual_primary_recovery_restored_original_and_kept_pending_stream')
            # Real conversation subsequently repairs Unicode again and uses
            # the repaired Authorization value in web/stream/error fixtures.
            return super().run(*args)

    monkeypatch.setitem(M, 'Native', Probe)
    fixture.test_real_native_agent_reaches_web_and_cleanup(tmp_path, monkeypatch, capsys,
        'explicit', variant, key, '', runtime_key_echo=True)
    assert 'actual_primary_recovery_restored_original_and_kept_pending_stream' in events
    assert 'actual_sdk_sent_repaired_key' in events
    if variant == 'retry_4xx':
        assert 'actual_sdk_http400_echoes_sent_key' in events
        for path in (tmp_path/'profile/sessions').glob('request_dump_*.json'):
            record = json.loads(path.read_text())
            assert record['request']['headers']['Authorization'] == 'Bearer [REDACTED]'
            error = record['error']
            assert error['body']['message'] == 'synthetic terminal [REDACTED]'
            assert json.loads(error['response_text'])['error']['message'] == error['body']['message']
    keys = (key, key.strip(), key.strip().encode('ascii', 'ignore').decode())
    product_files, fixture_files = [], []
    for path in sorted(tmp_path.rglob('*')):
        if path.is_file():
            scan(path.read_text(errors='replace'), keys)
            (fixture_files if path.name in ('callback-diagnostic.json', 'artifact-scan.json', 'partial-stream-witness.json')
             else product_files).append(str(path.relative_to(tmp_path)))
    (tmp_path/'runtime-coverage.json').write_text(json.dumps({
        'events': events, 'product_files_scanned': product_files,
        'fixture_diagnostics_scanned_separately': fixture_files}, indent=2)+'\n')


def test_policy_bounds_forms_overlap_and_original_character_threshold():
    policy = M['_CredentialPolicy']
    originals = tuple('key'+str(i)+'_ORIGINALя_tail' for i in range(8))
    reached = tuple(k.encode('ascii', 'ignore').decode() for k in originals)
    p = policy.create(originals, reached)
    assert len(p.originals) == 8 and len(p.values) == 16
    assert M['_redact'](' '.join(p.values), p) == ' '.join(['[REDACTED]']*16)
    with pytest.raises(M['Refused'], match='secret_redaction_limit'):
        policy.create((*originals, 'ninth'), ())
    with pytest.raises(M['Refused'], match='secret_redaction_limit'):
        policy.create(('a'*8193,), ())
    with pytest.raises(M['Refused'], match='secret_redaction_limit'):
        policy.create(('valid',), tuple('form'+str(i) for i in range(65)))
    with pytest.raises(M['Refused'], match='secret_redaction_limit'):
        policy.create(('valid',), ('b'*65537,))
    overflow = '  prefixXяAbC"\\LONG_secret_suffix_123456789  '
    assert len(M['_secret_form_prefixes']((overflow, overflow.strip()))) == 60
    with pytest.raises(M['Refused'], match='secret_redaction_limit'):
        policy.create((overflow,), (overflow.strip(), overflow.strip().encode('ascii', 'ignore').decode()))
    original = 'α"\\\n\t\b\fABCDEFGH_tail'
    live = original.encode('ascii', 'ignore').decode()
    p = policy.create((original, live[7:]+'SECOND_SECRET_tail'), (live,))
    for form, threshold in M['_secret_form_prefixes']((live,)).items():
        assert M['_redact'](form[:threshold], p) == '[REDACTED_PARTIAL]'
        assert M['_redact'](form, p) == '[REDACTED]'
    overlap = live + 'SECOND_SECRET_tail'
    assert M['_redact'](overlap, p) == '[REDACTED]'
    raw = M['_CredentialPolicy'].create(('original',), ('ABCDEFGH_tail',))
    assert M['_redact']('ABCDEFG!', raw) == 'ABCDEFG!'
    assert M['_redact']('ABCDEFGH!', raw) == '[REDACTED_PARTIAL]!'
    assert M['_redact']('useful citation https://docs.example/api 中 я', p) == 'useful citation https://docs.example/api 中 я'


@pytest.mark.parametrize('case', ['key_cmd', 'inline', 'callable', 'provider'])
def test_native_refuses_outside_static_local_closure(case, tmp_path, monkeypatch, capsys):
    from hermes_cli import config, runtime_provider
    load, resolve = config.load_config, runtime_provider.resolve_runtime_provider
    resolved, tokens, failures = [], [], []
    if case in ('key_cmd', 'inline'):
        def configured(*args, **kwargs):
            value = load(*args, **kwargs)
            value['providers']['friday-local']['key_cmd' if case == 'key_cmd' else 'api_key'] = 'fixture forbidden source'
            return value
        monkeypatch.setattr(config, 'load_config', configured)
    def resolver(*args, **kwargs):
        resolved.append(True)
        value = resolve(*args, **kwargs)
        if case == 'provider':
            value['provider'] = 'openai'
        elif case == 'callable':
            def token():
                tokens.append(True)
                raise AssertionError('CALLABLE_MUST_NOT_BE_INVOKED')
            value['api_key'] = token
        return value
    monkeypatch.setattr(runtime_provider, 'resolve_runtime_provider', resolver)
    base = M['Native']
    class Probe(base):
        def open(self, *args):
            try:
                return super().open(*args)
            except M['Refused'] as exc:
                failures.append(str(exc))
                assert not hasattr(self, 'agent') and not hasattr(self, 'stream_redactor')
                raise
    monkeypatch.setitem(M, 'Native', Probe)
    fixture.test_real_native_agent_reaches_web_and_cleanup(tmp_path, monkeypatch, capsys,
        'explicit', 'retry_4xx', KEYS[0], '', construction_failure=True)
    assert failures == ['native_runtime_route_mismatch' if case == 'provider' else 'static_scoped_credential_required']
    assert not tokens
    assert bool(resolved) == (case in ('callable', 'provider'))


@pytest.mark.parametrize('name', ['.env', 'auth.json'])
def test_policy_refuses_profile_refresh_sources_before_native_import(prepared, name):
    plan, task = prepared
    (Path(plan['profile']['path']).parent/name).write_text('{}')
    with pytest.raises(M['Refused'], match='fresh_credential_profile_required'):
        M['verify_plan'](plan, task)


@pytest.mark.parametrize('name', ['agent/message_sanitization.py', 'agent/turn_recovery.py',
    'agent/turn_api_error.py', 'agent/client_lifecycle.py', 'agent/credential_pool.py',
    'hermes_cli/runtime_provider_custom.py'])
def test_policy_requires_native_mutation_source_pins(prepared, name):
    plan, old = prepared
    del plan['source_files'][name]
    task = OriginalTask(old.task_id, old.accepted_monotonic, old.accepted_wall,
                        old.budget_seconds, old.boot_id, digest(plan))
    with pytest.raises(M['Refused'], match='native_candidate_pins_incomplete'):
        M['verify_plan'](plan, task)
