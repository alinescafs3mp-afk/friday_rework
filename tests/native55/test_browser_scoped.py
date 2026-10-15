import dataclasses
import os
import importlib.util
import json
from pathlib import Path
import sys
import time
import types

import pytest

BASE = Path(os.environ['FRIDAY_NATIVE_SOURCE']).resolve()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def scoped(monkeypatch):
    monkeypatch.setitem(sys.modules, 'hermes_constants', types.SimpleNamespace(get_hermes_home_override=lambda: None))
    monkeypatch.setitem(sys.modules, 'utils', types.SimpleNamespace(is_truthy_value=bool))
    urls = module('isolated_urls', BASE / 'tools/url_safety.py')
    monkeypatch.setitem(sys.modules, 'tools.url_safety', urls)
    monkeypatch.setitem(sys.modules, 'agent.bounded_context', types.SimpleNamespace(BoundedContextError=ValueError,bounded_tool_result_budget=lambda:None,serialized_bytes=lambda value:len(json.dumps(value,ensure_ascii=False).encode())))
    return module('scoped', BASE / 'tools/browser_scoped.py')


@pytest.mark.parametrize('name,args,command', [
    ('browser_navigate', {'url': 'https://example.com/'}, 'open'),
    ('browser_snapshot', {}, 'snapshot'), ('browser_click', {'ref': 'e1'}, 'click'),
    ('browser_type', {'ref': '@e2', 'text': 'ordinary form'}, 'fill'),
    ('browser_scroll', {'direction': 'up'}, 'scroll'), ('browser_back', {}, 'back'),
    ('browser_press', {'key': 'Enter'}, 'press')])
def test_full_seven_family(scoped, name, args, command):
    assert scoped.action(name, args)[0] == command


@pytest.mark.parametrize('name,args', [
    ('browser_eval', {'expression': 'fetch("http://localhost")'}),
    ('browser_console', {}), ('browser_navigate', {'url': 'file:///etc/passwd'}),
    ('browser_navigate', {'url': 'https://user:password@example.com/'}),
    ('browser_navigate', {'url': 'https://example.com/?api_key=opaque'}),
    ('browser_navigate', {'url': 'https://example.com/?token=opaque'}),
    ('browser_navigate', {'url': 'https://example.com:444/'}),
    ('browser_navigate', {'url': 'https://example.com/#secret'}),
    ('browser_navigate', {'url': 'https://example.com/\n--cdp'}),
    ('browser_click', {'ref': 'button[onclick]'}),
    ('browser_click', {'ref': '--cdp'}),
    ('browser_type', {'ref': 'e1', 'text': '--provider'}),
    ('browser_press', {'key': 'Control+L'}),
    ('browser_back', {'cdp': 'http://localhost'}),
    ('browser_snapshot', {'full': 'true'})])
def test_no_broad_authority(scoped, name, args):
    with pytest.raises((RuntimeError, ValueError)):
        scoped.action(name, args)


@dataclasses.dataclass
class Cap:
    home: Path
    authorization_home: Path
    profile: str = 'fixture'
    principal: tuple = ('telegram', 'transport', 'bot', 'alice')
    binding: dict = dataclasses.field(default_factory=dict)
    directory_identity: tuple = (1, 2)
    admission_generation: int = 1
    revoked: bool = False

    @property
    def key(self):
        return '|'.join(self.principal)

    def check(self):
        if self.revoked:
            raise PermissionError('revoked')
        return self


@pytest.fixture
def harness(scoped, monkeypatch, tmp_path):
    cap = Cap(tmp_path, tmp_path)
    monkeypatch.setitem(sys.modules, 'tools.interrupt', types.SimpleNamespace(is_interrupted=lambda: False))
    web = module('fixture_web', BASE / 'agent/web_call_context.py')
    turn = web.WebTurn()
    original = time.monotonic() + 120
    call = web.WebCall(turn, time.monotonic() + 30, 'task', 'session', 'call', run_deadline=original)
    call.turn_id = 'turn'; call.session_key = 'conversation'
    web._current.set(call)
    monkeypatch.setitem(sys.modules, 'agent.web_call_context', web)
    users = types.ModuleType('hermes_cli.friday_user_scope')
    users.current = lambda required=False: cap.check()
    users.guard_tool = lambda name, args: cap.check()
    hermes = types.ModuleType('hermes_cli'); hermes.friday_user_scope = users
    monkeypatch.setitem(sys.modules, 'hermes_cli', hermes)
    monkeypatch.setitem(sys.modules, 'hermes_cli.friday_user_scope', users)
    monkeypatch.setitem(sys.modules, 'agent.redact', types.SimpleNamespace(redact_sensitive_text=lambda text, force: text, is_secret_field_name=lambda key: key.endswith('_KEY')))
    monkeypatch.setitem(sys.modules, 'agent.secret_scope', types.SimpleNamespace(
        current_secret_scope=lambda: {'LOCAL_API_KEY': 'opaque fixture-held-value'},
        current_secret_scope_home=lambda: str(tmp_path)))
    monkeypatch.setitem(sys.modules, 'tools.website_policy', types.SimpleNamespace(check_website_access=lambda url: None))

    class Registry:
        def __init__(self):
            self.launches = []; self.stops = []; self.status = 'QUIESCENT'
        def spawn_browser(self, owner):
            self.launches.append(owner)
            owner.registry = self
            owner.session = types.SimpleNamespace(web_deadline=owner.deadline())
            return owner.session
        def settle_web(self, session, stop):
            self.stops.append((session, stop))
            return {'status': self.status}
    registry = Registry()
    monkeypatch.setitem(sys.modules, 'tools.process_registry', types.SimpleNamespace(process_registry=registry))
    monkeypatch.setattr(scoped, '_packages', lambda: {})
    payloads = []
    def exchange(registry, session, current, payload):
        current.check(); cap.check(); payloads.append(payload)
        return {'ready': True} if payload.get('start') else {'success': True, 'data': {'fixture': True}}
    monkeypatch.setattr(scoped, 'exchange', exchange)
    return types.SimpleNamespace(scoped=scoped, cap=cap, web=web, call=call, turn=turn,
                                 original=original, registry=registry, payloads=payloads)


def test_actions_share_original_owner_without_clock_refresh(harness):
    h = harness
    for name, args in [('browser_navigate', {'url': 'https://example.com/'}), ('browser_snapshot', {}),
                       ('browser_click', {'ref': 'e1'}), ('browser_type', {'ref': 'e1', 'text': 'fixture'}),
                       ('browser_scroll', {'direction': 'down'}), ('browser_back', {}), ('browser_press', {'key': 'Tab'})]:
        assert json.loads(h.scoped.execute(name, args, task_id='task'))['success']
        h.call.run_deadline += 1000
    assert len(h.registry.launches) == 1
    assert h.registry.launches[0].deadline() == h.original
    assert len(h.payloads) == 8
    start = h.payloads[0]
    assert start['authority']['principal'][-1] == 'alice'
    assert start['authority']['admission_generation'] == 1
    assert start['pin'][3:5] == ['task', 'session']
    assert set(start) == {'start', 'home', 'authority', 'deadline', 'packages', 'pin'}


def test_foreign_task_never_launches(harness):
    with pytest.raises(RuntimeError, match='native_task_session'):
        harness.scoped.execute('browser_back', {}, task_id='foreign')
    assert not harness.registry.launches


def test_revoke_before_action_never_launches(harness):
    harness.cap.revoked = True
    with pytest.raises(PermissionError):
        harness.scoped.execute('browser_back', {}, task_id='task')
    assert not harness.registry.launches


@pytest.mark.parametrize('name,args', [
    ('browser_type', {'ref': 'e1', 'text': 'opaque fixture-held-value'}),
    ('browser_type', {'ref': 'e1', 'text': 'b3BhcXVlIGZpeHR1cmUtaGVsZC12YWx1ZQ=='}),
    ('browser_navigate', {'url': 'https://example.com/opaque%20fixture-held-value'})])
def test_opaque_local_credentials_never_reach_child(harness, name, args):
    with pytest.raises(RuntimeError, match='local_credential_refused'):
        harness.scoped.execute(name, args, task_id='task')
    assert not harness.registry.launches and not harness.payloads


def test_stop_is_sticky_and_no_replay(harness):
    h = harness
    h.scoped.execute('browser_back', {}, task_id='task')
    receipt = h.turn.stop()
    assert receipt['status'] == 'QUIESCENT'
    with pytest.raises(RuntimeError, match='stopped'):
        h.scoped.execute('browser_back', {}, task_id='task')
    assert len(h.registry.launches) == 1
    assert h.registry.stops


def test_unknown_command_effect_stops_exact_owner_and_never_retries(harness, monkeypatch):
    h = harness
    h.scoped.execute('browser_back', {}, task_id='task')
    def unknown(*args):
        raise RuntimeError('unknown_effect')
    monkeypatch.setattr(h.scoped, 'exchange', unknown)
    with pytest.raises(RuntimeError, match='unknown_effect'):
        h.scoped.execute('browser_click', {'ref': 'e1'}, task_id='task')
    assert len(h.registry.launches) == 1 and len(h.registry.stops) == 1
    with pytest.raises(RuntimeError, match='not_replayable'):
        h.scoped.execute('browser_back', {}, task_id='task')
    assert len(h.registry.launches) == 1


def test_uncertain_cleanup_is_retained(harness):
    h = harness
    h.scoped.execute('browser_back', {}, task_id='task')
    h.registry.status = 'STOP_UNCONFIRMED'
    assert h.scoped.cleanup(task_id='foreign')['status'] == 'QUIESCENT'
    assert not h.registry.stops
    assert h.scoped.cleanup(task_id='task')['status'] == 'STOP_UNCONFIRMED'
    assert h.scoped._OWNERS
    h.registry.status = 'QUIESCENT'
    assert h.scoped.cleanup(task_id='task')['status'] == 'QUIESCENT'
    assert not h.scoped._OWNERS


def test_namespace_mounts_and_no_ambient_browser_configuration(tmp_path):
    gate = module('gate', BASE / 'tools/browser_process_child.py')
    packages = {}
    for name in ('agent-browser', 'chromium'):
        root = tmp_path / name; root.mkdir(); (root / 'binary').write_bytes(b'fixture')
        packages[name] = {'root': str(root), 'relative': 'binary', 'sha256': gate.digest(root / 'binary')}
    argv = gate.isolated_argv(packages, '/fixture-bridge', Path('/fixture-helper'))
    assert all(flag in argv for flag in ('--unshare-net', '--unshare-pid', '--as-pid-1', '--clearenv', '--cap-drop'))
    assert '--no-sandbox' not in argv and '--share-net' not in argv
    assert '/run' not in argv and '/sys' not in argv and '/etc' not in argv
    assert argv[-6:] == ['--', '/usr/bin/python3', '-I', '-B', '/browser_gate.py', '--namespace']
    packages['chromium']['sha256'] = '0' * 64
    with pytest.raises(RuntimeError, match='package_changed'):
        gate.isolated_argv(packages, '/fixture-bridge', Path('/fixture-helper'))


def test_output_storage_cannot_outlive_original_command_deadline(harness, monkeypatch):
    h = harness
    def bounded_output(value):
        h.call.base_deadline = time.monotonic() - 1
        return value
    monkeypatch.setattr(h.scoped, '_bounded_output', bounded_output)
    with pytest.raises(TimeoutError, match='web_original_deadline'):
        h.scoped.execute('browser_snapshot', {}, task_id='task')
    assert len(h.registry.launches) == 1 and len(h.registry.stops) == 1
