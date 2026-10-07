"""Native identify generation and refusal controls; all transport is intercepted."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from scripts import friday_start as start
from scripts.install_containment import Budget

pytest_plugins = ['test_native_product_start']


@pytest.mark.parametrize('fault', ['absent', 'pid', 'start', 'home', 'code', 'source', 'config', 'protocol'])
def test_live_identity_must_match_admitted_process_and_generation(native_home, monkeypatch, fault):
    from gateway import control_socket
    from test_native_product_start import observe
    f = native_home
    observe(f, monkeypatch)
    response = copy.deepcopy(control_socket.identify_gateway(f.home))
    if fault == 'absent':
        response = None
    elif fault == 'pid':
        response['pid'] += 1
    elif fault == 'start':
        response['start_time'] += 1
    elif fault == 'home':
        response['hermes_home'] = '/synthetic-foreign'
    elif fault == 'code':
        response['code_sha'] = '0' * 40
    elif fault == 'source':
        response['friday_owner']['source']['receipt'] = 'different-overlays-same-upstream'
    elif fault == 'config':
        response['friday_owner']['configuration'] = 'old-config'
    else:
        response['protocol'] += 1
    calls = []
    def identify(home, *, timeout):
        calls.append((home, timeout))
        return response
    monkeypatch.setattr(control_socket, 'identify_gateway', identify)
    budget = Budget(30)
    with pytest.raises(ValueError, match='native_gateway_generation_unproved'):
        start.gateway_observation(f.home, budget)
    assert len(calls) == 1 and 0 < calls[0][1] <= 5


@pytest.mark.parametrize('fault', ['missing-time', 'future', 'missing-kind', 'bool-pid', 'bool-start'])
def test_runtime_record_malformed_or_future_never_reaches_live_probe(native_home, monkeypatch, fault):
    from gateway import control_socket
    from test_native_product_start import observe
    f = native_home
    observe(f, monkeypatch)
    record = f.gw._read_gateway_runtime_status()
    if fault == 'missing-time':
        record.pop('updated_at')
    elif fault == 'future':
        record['updated_at'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif fault == 'missing-kind':
        record.pop('kind')
    elif fault == 'bool-pid':
        record['pid'] = True
    else:
        record['start_time'] = True
    monkeypatch.setattr(f.gw, '_read_gateway_runtime_status', lambda: record)
    calls = []
    monkeypatch.setattr(control_socket, 'identify_gateway', lambda *a, **kw: calls.append(a))
    with pytest.raises(ValueError, match='native_gateway_start_not_observed'):
        start.gateway_observation(f.home, Budget(30))
    assert calls == []


def test_native_server_captures_generation_before_bind_and_refuses_later_adoption(tmp_path, monkeypatch):
    from gateway import control_socket
    from hermes_cli import friday_gateway_owner as proof
    current = {'home': str(tmp_path), 'source': {'receipt': 'new18-composed'}, 'configuration': 'cfg'}
    reads = []
    def expected(home):
        reads.append(home)
        return copy.deepcopy(current)
    monkeypatch.setattr(proof.owner, 'enabled', lambda: True)
    monkeypatch.setattr(proof, 'expected', expected)
    monkeypatch.setattr(control_socket, 'build_identify_payload', lambda: {'pid': 1234})
    server = control_socket.GatewayControlServer(tmp_path)
    assert reads == [tmp_path] and server._server is None
    assert server._handlers['identify']()['friday_owner'] == current
    current['source']['receipt'] = 'other-composition-with-same-donor'
    with pytest.raises(ValueError):
        server._handlers['identify']()
    current['source']['receipt'] = 'new18-composed'
    assert server._handlers['identify']()['friday_owner'] == current


def test_unconfigured_donor_keeps_original_identify_handler(tmp_path, monkeypatch):
    from hermes_cli import friday_gateway_owner as proof
    monkeypatch.setattr(proof.owner, 'enabled', lambda: False)
    calls = []
    monkeypatch.setattr(proof, 'expected', lambda *a: calls.append(a))
    handler = lambda: {'native': True}
    assert proof.bind_identify(tmp_path, handler) is handler and calls == []


def test_actual_composed_source_and_config_are_bound_without_exposing_values(owner):
    from hermes_cli import friday_gateway_owner as proof
    original = (owner.home / 'config.yaml').read_bytes()
    first = proof.expected(owner.home)
    assert first['source']['receipt'] == owner.boundary.sha((owner.home / 'hermes-agent.source.json').read_bytes())
    assert first['source']['plugin']
    assert len(first['configuration']) == 64
    assert 'FIXTURE_PASSWORD' not in json.dumps(first) and 'FIXTURE_SIGNING' not in json.dumps(first)
    try:
        (owner.home / 'config.yaml').write_bytes(original + b'\n# different-generation\n')
        changed = proof.expected(owner.home)
        assert changed['source'] == first['source'] and changed['configuration'] != first['configuration']
    finally:
        (owner.home / 'config.yaml').write_bytes(original)
    changed_file = owner.source / 'hermes_cli/friday_gateway_owner.py'
    raw = changed_file.read_bytes()
    try:
        changed_file.write_bytes(raw + b'\n# tampered overlay\n')
        with pytest.raises(ValueError):
            proof.expected(owner.home)
    finally:
        changed_file.write_bytes(raw)
