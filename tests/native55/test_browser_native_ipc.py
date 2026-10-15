import ast
import importlib.util
import json
import os
from pathlib import Path
import resource
import socket

import pytest

ROOT = Path(os.environ['FRIDAY_NATIVE_SOURCE']).resolve()
spec = importlib.util.spec_from_file_location('browser_native_ipc', ROOT / 'tools/browser_native_ipc.py')
ipc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipc)


class FakeSocket:
    def __init__(self, replies=None, fail=None):
        self.replies = list(replies if replies is not None else [b'{"id":"f1","success":true,"data":{}}\n'])
        self.fail = fail
        self.connects = []
        self.writes = []
        self.timeouts = []
        self.closed = False

    def settimeout(self, value):
        assert 0 < value <= 30
        self.timeouts.append(value)

    def connect(self, path):
        self.connects.append(path)
        if self.fail == 'connect':
            raise ConnectionRefusedError(111, 'connect failed')

    def sendall(self, wire):
        self.writes.append(wire)
        if self.fail == 'write':
            raise BrokenPipeError(32, 'partial write uncertain')

    def recv(self, size):
        if self.fail == 'read':
            raise BlockingIOError(11, 'Resource temporarily unavailable')
        if self.fail == 'cancel':
            raise KeyboardInterrupt
        piece = self.replies.pop(0) if self.replies else b''
        assert len(piece) <= size
        return piece

    def close(self):
        self.closed = True


def make_client(sock, check=lambda: 19):
    created = []
    def factory(family, kind):
        assert (family, kind) == (socket.AF_UNIX, socket.SOCK_STREAM)
        created.append(sock)
        return sock
    return ipc.NativeIPC(check, factory), created


def test_limits_installed_before_imports():
    assert resource.getrlimit(resource.RLIMIT_AS) == (536870912, 536870912)
    assert resource.getrlimit(resource.RLIMIT_CPU) == (60, 60)
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == (67108864, 67108864)
    assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
    assert os.sched_getaffinity(0) == {0, 1}
    assert os.environ['HOME'] == os.environ['FRIDAY_TEST_HOME']
    assert os.environ['TMPDIR'] == os.environ['FRIDAY_TEST_TMP']
    assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'


@pytest.mark.parametrize('command,args,expected', [
    ('open', ['https://example.com/path?q=a'], {'action': 'navigate', 'url': 'https://example.com/path?q=a'}),
    ('snapshot', [], {'action': 'snapshot'}),
    ('snapshot', ['-c'], {'action': 'snapshot', 'compact': True}),
    ('click', ['@e3'], {'action': 'click', 'selector': '@e3'}),
    ('fill', ['@e4', ' hello\nworld "é" '], {'action': 'fill', 'selector': '@e4', 'value': ' hello\nworld "é" '}),
    ('scroll', ['up', '500'], {'action': 'scroll', 'direction': 'up', 'amount': 500}),
    ('scroll', ['down', '500'], {'action': 'scroll', 'direction': 'down', 'amount': 500}),
    ('back', [], {'action': 'back'}),
    ('press', ['Enter'], {'action': 'press', 'key': 'Enter'}),
])
def test_exact_pinned_closed_mappings(command, args, expected):
    assert ipc.native_request(command, args, 'f1') == {'id': 'f1', **expected}


@pytest.mark.parametrize('command,args', [
    ('eval', ['1']), ('launch', []), ('close', []), ('type', ['@e1', 'x']),
    ('click', ['#selector']), ('click', ['@e0']), ('click', ['@e1234567890']),
    ('click', ['@e1', '--new-tab']), ('snapshot', ['--selector', 'body']),
    ('open', ['file:///etc/passwd']), ('open', ['https://u:p@example.com/']),
    ('open', ['https://example.com/#fragment']), ('open', ['https://example.com:22/']),
    ('open', ['https://exam%70le.com/']), ('open', ['https://example.com/\n']),
    ('fill', ['@e1', '-flag']), ('fill', ['@e1', 'a' * 32769]),
    ('fill', ['@e1', '\x00']), ('press', ['Ctrl+L']), ('press', ['Enter', 'Tab']),
    ('back', ['extra']), ('scroll', ['left', '500']), ('scroll', ['down', '501']),
])
def test_invalid_input_rejected_before_any_socket(command, args):
    sock = FakeSocket()
    client, created = make_client(sock)
    with pytest.raises((RuntimeError, ValueError)):
        client.exchange(command, args)
    assert created == []
    assert sock.writes == []


def test_success_has_one_frame_one_connect():
    sock = FakeSocket([b'{"id":"f1",', b'"success":true,"data":{}}\n'])
    client, created = make_client(sock)
    result = client.exchange('click', ['@e1'])
    assert result == {'id': 'f1', 'success': True, 'data': {}}
    assert created == [sock]
    assert sock.connects == ['/work/socket/scoped.sock']
    assert len(sock.writes) == 1
    assert json.loads(sock.writes[0]) == {'id': 'f1', 'action': 'click', 'selector': '@e1'}
    assert sock.closed


@pytest.mark.parametrize('failure', ['connect', 'write', 'read', 'cancel'])
def test_transient_or_cancel_never_replays_and_poison_is_sticky(failure):
    sock = FakeSocket(fail=failure)
    client, created = make_client(sock)
    with pytest.raises(RuntimeError, match='unknown_effect'):
        client.exchange('press', ['Enter'])
    assert len(created) == 1
    assert len(sock.connects) == 1
    assert len(sock.writes) == (0 if failure == 'connect' else 1)
    assert sock.closed
    with pytest.raises(RuntimeError, match='worker_poisoned'):
        client.exchange('press', ['Enter'])
    assert len(created) == 1
    assert len(sock.writes) <= 1


@pytest.mark.parametrize('reply', [
    b'', b'{}', b'\n', b'{"id":"f1","success":true}',
    b'{"id":"f2","success":true}\n', b'{"success":true}\n',
    b'{"id":"f1","success":1}\n', b'{"id":"f1","success":false}\n',
    b'[]\n', b'{"id":"f1","success":true}\n{}\n',
    b'{"id":"f1","success":true}\ntrailing', b'\xff\n',
])
def test_eof_partial_malformed_mismatched_or_negative_reply_never_replays(reply):
    sock = FakeSocket([reply])
    client, created = make_client(sock)
    with pytest.raises(RuntimeError, match='unknown_effect'):
        client.exchange('back', [])
    with pytest.raises(RuntimeError, match='worker_poisoned'):
        client.exchange('back', [])
    assert len(created) == 1
    assert len(sock.writes) == 1
    assert sock.closed


def test_original_deadline_after_dispatch_poisoned():
    checks = iter([19, 19, 19, 19, 0])
    def remaining():
        value = next(checks)
        if not value:
            raise RuntimeError('original_deadline')
        return value
    sock = FakeSocket()
    client, created = make_client(sock, remaining)
    with pytest.raises(RuntimeError, match='unknown_effect'):
        client.exchange('click', ['@e1'])
    with pytest.raises(RuntimeError, match='worker_poisoned'):
        client.exchange('click', ['@e1'])
    assert len(created) == 1 and len(sock.writes) == 1


def test_known_success_allows_new_command_with_new_id():
    sockets = [FakeSocket(), FakeSocket([b'{"id":"f2","success":true}\n'])]
    made = []
    def factory(*unused):
        sock = sockets[len(made)]
        made.append(sock)
        return sock
    client = ipc.NativeIPC(lambda: 19, factory)
    client.exchange('snapshot', [])
    client.exchange('press', ['Tab'])
    assert len(made) == 2
    assert [json.loads(s.writes[0])['id'] for s in made] == ['f1', 'f2']


def test_large_output_stops_before_replay():
    sock = FakeSocket([b'x' * 65536] * 30 + [b'x' * 33921, b'x'])
    client, created = make_client(sock)
    with pytest.raises(RuntimeError, match='unknown_effect'):
        client.exchange('snapshot', [])
    with pytest.raises(RuntimeError, match='worker_poisoned'):
        client.exchange('snapshot', [])
    assert len(created) == 1 and len(sock.writes) == 1


def test_explicit_daemon_env_prevents_ambient_backend_attach(monkeypatch):
    for name in ('AGENT_BROWSER_AUTO_CONNECT', 'AGENT_BROWSER_CDP', 'AGENT_BROWSER_PROVIDER',
                 'AGENT_BROWSER_STATE', 'AGENT_BROWSER_SESSION_NAME', 'AI_GATEWAY_API_KEY',
                 'AGENT_BROWSER_ARGS', 'AGENT_BROWSER_PROXY'):
        monkeypatch.setenv(name, 'ambient-unsafe')
    env = ipc.daemon_environment('chrome-linux64/chrome', 4242, 50000)
    assert env['AGENT_BROWSER_DAEMON'] == '1'
    assert env['AGENT_BROWSER_SESSION'] == 'scoped'
    assert env['AGENT_BROWSER_ENGINE'] == 'chrome'
    assert env['AGENT_BROWSER_EXECUTABLE_PATH'] == '/chromium/chrome-linux64/chrome'
    assert env['AGENT_BROWSER_PROFILE'] == '/work/profile'
    assert env['AGENT_BROWSER_PROXY'] == 'socks5://127.0.0.1:4242'
    assert env['AGENT_BROWSER_PROXY_BYPASS'] == '<-loopback>'
    assert not any('ambient-unsafe' in value for value in env.values())
    assert not ({'AGENT_BROWSER_AUTO_CONNECT', 'AGENT_BROWSER_CDP', 'AGENT_BROWSER_PROVIDER',
                 'AGENT_BROWSER_STATE', 'AGENT_BROWSER_SESSION_NAME', 'AI_GATEWAY_API_KEY'} & env.keys())


def test_helper_source_uses_foreground_daemon_before_any_exchange():
    source = (ROOT / 'tools/browser_process_child.py').read_text()
    tree = ast.parse(source)
    namespace = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'namespace_main')
    popens = [node for node in ast.walk(namespace) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen']
    assert len(popens) == 1
    assert "prefix + [command]" not in source
    assert 'native.exchange(command, args)' in source
    assert "'browser_native_ipc.py'" in source
    assert "stat.S_ISSOCK(mode)" in source
    assert "scoped.version" in source and "scoped.pid" in source
    for path in (ROOT / 'tools').glob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
