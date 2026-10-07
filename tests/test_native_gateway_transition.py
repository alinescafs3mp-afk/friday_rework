"""Additional independent transitions, retaining a red expected-safety result if present."""
import copy
import dataclasses
import hashlib
import json

import pytest
from scripts import friday_start as start
from scripts.install_containment import Budget

pytest_plugins = ['test_native_product_start']


def test_valid_replaced_source_same_upstream_is_not_adopted(owner, monkeypatch):
    from gateway import control_socket as cs
    from hermes_cli import friday_gateway_owner as proof
    monkeypatch.setattr(cs, 'build_identify_payload', lambda: {'kind': 'hermes-gateway'})
    server = cs.GatewayControlServer(owner.home)
    paths = [owner.source / 'hermes_cli/friday_gateway_owner.py',
             owner.home / 'hermes-agent.source.json', owner.home / 'FRIDAY-INSTALL.json']
    before = [p.read_bytes() for p in paths]
    boot = proof.expected(owner.home)
    try:
        paths[0].write_bytes(before[0] + b'\n# independent valid different-generation\n')
        receipt = json.loads(before[1]); entry = receipt['files']['hermes_cli/friday_gateway_owner.py']
        entry['sha256'] = hashlib.sha256(paths[0].read_bytes()).hexdigest(); entry['bytes'] = paths[0].stat().st_size
        paths[1].write_text(json.dumps(receipt))
        marker = json.loads(before[2]); marker['source_receipt_sha256'] = hashlib.sha256(paths[1].read_bytes()).hexdigest()
        paths[2].write_text(json.dumps(marker))
        current = proof.expected(owner.home)
        assert current['source']['commit'] == boot['source']['commit']
        assert current['source']['receipt'] != boot['source']['receipt']
        response = json.loads(server.handle_request_line(b'{"verb":"identify"}'))
        assert response['ok'] is False
    finally:
        for p, raw in zip(paths, before): p.write_bytes(raw)


def test_unconfigured_native_server_keeps_original_handler(tmp_path, monkeypatch):
    from gateway import control_socket as cs
    from hermes_cli import friday_gateway_owner as proof
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    monkeypatch.setattr(proof.owner, 'SOURCE', tmp_path / 'hermes-agent')
    token = set_hermes_home_override(str(tmp_path))
    calls = []
    handler = lambda: {'native': True}
    monkeypatch.setattr(cs, 'build_identify_payload', handler)
    monkeypatch.setattr(proof, 'expected', lambda *a: calls.append(a))
    try:
        server = cs.GatewayControlServer(tmp_path)
        assert server._handlers['identify'] is handler and calls == []
        assert json.loads(server.handle_request_line(b'{"verb":"identify"}'))['result'] == {'native': True}
    finally: reset_hermes_home_override(token)


@pytest.mark.parametrize('transition', ['replaced-record', 'liveness-lost'])
def test_owner_transition_during_identity_probe_refuses(native_home, monkeypatch, transition):
    from gateway import control_socket as cs
    from hermes_cli import friday_gateway_owner as proof
    from test_native_product_start import observe
    f = native_home
    native_identify = cs.identify_gateway
    observe(f, monkeypatch)
    payload = copy.deepcopy(cs.identify_gateway(f.home))
    monkeypatch.setattr(cs, 'identify_gateway', native_identify)
    monkeypatch.setattr(proof.owner, 'enabled', lambda: True)
    monkeypatch.setattr(cs, 'build_identify_payload', lambda: copy.deepcopy(payload))
    server = cs.GatewayControlServer(f.home)
    calls = []
    def intercepted_transport(home, request, timeout):
        calls.append(home)
        response = server.handle_request_line(request)
        if transition == 'replaced-record':
            replacement = dataclasses.replace(f.record, pid=f.record.pid + 1, start_time=f.record.start_time + 1)
            monkeypatch.setattr(f.hr, 'read_record', lambda *a, **kw: replacement)
        else: monkeypatch.setattr(f.hr, 'liveness_is_proven', lambda *a: False)
        return response
    monkeypatch.setattr(cs, '_query_unix_socket', intercepted_transport)
    with pytest.raises(ValueError): start.gateway_observation(f.home, Budget(30))
    assert calls == [f.home]
