"""Safe local argument feedback through real native scope and tool dispatch.

Synthetic principals and temporary homes only; no provider, worker or gateway.
"""
import contextvars
import hashlib
import json
from types import SimpleNamespace
import weakref

import pytest

from hermes_cli import friday_user_scope as scope
from hermes_constants import set_hermes_home_override, reset_hermes_home_override


@pytest.fixture
def admitted(tmp_path, monkeypatch):
    from hermes_cli.friday_product_access import KEY, principal_id
    from hermes_cli.plugins_state import PluginState
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity

    root = tmp_path / 'home'
    root.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME', str(root))
    import hermes_constants
    monkeypatch.setattr(hermes_constants, '_PINNED_PROCESS_HERMES_HOME', str(root))
    monkeypatch.setattr(scope, '_CURRENT', contextvars.ContextVar('argument-test-scope', default=None))
    monkeypatch.setattr(scope, '_SOURCE', contextvars.ContextVar('argument-test-source', default=None))
    monkeypatch.setattr(scope, '_ENGAGED', False)

    def put(path, value):
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    binding = dict(platform='telegram', transport_profile='default', account_id='synthetic-account',
                   user_id='1', runtime_profile='fixture-user-1', tools=['memory', 'read_file', 'write_file'])
    principal = principal_id(*(binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')))
    cfg = {'plugins': {'enabled': ['friday_rework'], 'entries': {'friday_rework': {'settings': {
        'product_access': {'enabled': True, 'accounts': [dict(platform='telegram', transport_profile='default',
            account_id='synthetic-account', runtime_profiles=['fixture-user-1'])]},
        'user_isolation': {'enabled': True, 'bindings': [binding]}}}}},
        'gateway': {'multiplex_profiles': True, 'profile_routes': [dict(name='friday-' + principal,
            platform='telegram', bot_profile='default', user_id='1', profile='fixture-user-1', enabled=True)]}}
    put(root / 'config.yaml', cfg)
    with scope.authority(root):
        PluginState('friday_rework').set(KEY, dict(schema=KEY, users={principal: {
            k: binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')} |
            dict(enabled=True, role='user')}))
    home = scope.provision_new_home(root, binding, {'max_iterations': 8, 'toolsets': ['file']})
    from hermes_cli.config import atomic_config_write
    with scope.authority(home):
        atomic_config_write(home / 'config.yaml', {'max_iterations': 8, 'toolsets': ['file'], 'tools': {
            'tool_search': {'enabled': 'auto', 'defer': ['write_file', 'read_file']}}})
    (home / 'SOUL.md').write_text('Synthetic identity')
    (home / 'SOUL.md').chmod(0o600)
    (home / '.env').write_text('SYNTHETIC_FIXTURE_KEY=offline-fixture\n')
    (home / '.env').chmod(0o600)
    info = home.stat()
    put(home / scope.ONBOARDING, dict(schema='friday.onboarding.v1',
        binding_sha256=scope._fingerprint(binding), config_sha256=sha(home / 'config.yaml'),
        soul_sha256=sha(home / 'SOUL.md'), required_secrets=['SYNTHETIC_FIXTURE_KEY'],
        directory_identity=[info.st_dev, info.st_ino], template='synthetic', authorization_home=str(root)))
    marker = json.loads((home / scope.MARKER).read_text())
    marker['onboarding_sha256'] = sha(home / scope.ONBOARDING)
    put(home / scope.MARKER, marker)
    # RoutingIdentity retains a weak reference to the transport.
    class Transport:
        pass
    adapter = Transport()
    source = SessionSource(Platform.TELEGRAM, 'synthetic-chat', user_id='1', chat_type='dm', profile='fixture-user-1')
    source._identity = RoutingIdentity('default', 'fixture-user-1', root, home,
        multiplexed=True, transport_inferred=False, transport=weakref.ref(adapter))
    with scope.authority(root):
        scope.admit_source(source)
    token = set_hermes_home_override(str(root))
    try:
        with scope.authority(home), scope.scoped_source(source) as cap:
            yield SimpleNamespace(root=root, home=home, cap=cap)
    finally:
        reset_hermes_home_override(token)


def invoke(name, arguments):
    import model_tools
    return json.loads(model_tools.handle_function_call(name, arguments,
        task_id='argument-feedback-test', enabled_toolsets=['file']))


def write(arguments):
    from tools.registry import registry
    import tools.file_tools
    return json.loads(registry.dispatch('write_file', arguments, task_id='argument-feedback-test'))


def document(content, path='report.docx'):
    return dict(path=path, content=content, format='docx_structured')


@pytest.mark.parametrize('arguments', [
    {'calls': '[{"name":"write_file","arguments":'},
    {'calls': []},
    {'calls': [{'name': 'write_file', 'arguments': '{"content":"PRIVATE_SENTINEL"'}]},
    {'calls': [{'name': 'write_file', 'arguments': 7}]},
])
def test_malformed_envelope_feedback_without_dispatch(admitted, monkeypatch, arguments):
    import model_tools
    monkeypatch.setattr(model_tools, '_dispatch_bridge_tool', lambda *a: pytest.fail('must not dispatch'))
    result = invoke('tool_call', arguments)
    assert result.get('error_type') == 'invalid_arguments', result
    assert result['success'] is False and 'calls' in result['hint']
    assert 'PRIVATE_SENTINEL' not in json.dumps(result)
    assert list((admitted.home / 'workspace').iterdir()) == []


@pytest.mark.parametrize('content', ['{"blocks":[', '{"blocks":[],"secret":"PRIVATE_SENTINEL"}',
    '{"blocks":[{"type":"heading","text":"Report","level":true}]}',
    '{"blocks":[{"type":"table","rows":[["A"],["B","C"]]}]}',
    '{"blocks":[],"blocks":[]}'])
def test_structured_content_feedback_before_creation(admitted, monkeypatch, content):
    from hermes_cli import friday_workspace_docx as docx
    monkeypatch.setattr(docx, '_create_bytes', lambda *a, **kw: pytest.fail('must not publish'))
    result = write(document(content))
    assert result.get('error_type') == 'invalid_arguments', result
    assert result['success'] is False and 'blocks' in result['hint']
    assert 'PRIVATE_SENTINEL' not in json.dumps(result)
    assert list((admitted.home / 'workspace').iterdir()) == []


@pytest.mark.parametrize('fault', ['revoked', 'private_path', 'parent_symlink', 'permission_drift', 'wrong_registry'])
def test_authority_denials_stay_generic_before_content(admitted, fault):
    from tools.registry import registry
    import tools.file_tools
    args = document('{"blocks":[', 'report.docx')
    extra = {}
    if fault == 'revoked':
        admitted.cap.revoked = True
    elif fault == 'private_path':
        args['path'] = str(admitted.home / 'config.yaml')
    elif fault == 'parent_symlink':
        (admitted.home / 'workspace/link').symlink_to(admitted.root, target_is_directory=True)
        args['path'] = 'link/report.docx'
    elif fault == 'permission_drift':
        (admitted.home / 'workspace').chmod(0o755)
    else:
        extra['scope'] = str(admitted.root)
    result = json.loads(registry.dispatch('write_file', args, **extra))
    assert result.get('error_type') != 'invalid_arguments', result
    assert result['error'] == scope.PUBLIC_TOOL_REFUSAL_COPY
    assert 'hint' not in result
    assert not (admitted.home / 'workspace/report.docx').exists()


@pytest.mark.parametrize('arguments', [
    {'calls': [{'name': 'terminal', 'arguments': {}}]},
    {'calls': [{'name': 'tool_call', 'arguments': {}}]},
])
def test_disallowed_and_recursive_tools_stay_generic(admitted, arguments):
    result = invoke('tool_call', arguments)
    assert result['error'] == scope.PUBLIC_TOOL_REFUSAL_COPY
    assert 'hint' not in result


@pytest.mark.parametrize('arguments', [
    {'calls': [{'name': 'terminal', 'arguments': '{'}]},
    {'calls': [7, {'name': 'terminal', 'arguments': {}}]},
    {'calls': [{'name': 'write_file', 'arguments': '{'}, {'name': 'tool_call', 'arguments': {}}]},
])
def test_forbidden_name_wins_over_malformed_envelope(admitted, arguments):
    result = invoke('tool_call', arguments)
    assert result['error'] == scope.PUBLIC_TOOL_REFUSAL_COPY
    assert 'hint' not in result


@pytest.mark.parametrize('fault', ['revoked', 'delegation', 'missing_scope'])
def test_identity_denial_wins_over_malformed_json(admitted, monkeypatch, fault):
    if fault == 'revoked':
        admitted.cap.revoked = True
    elif fault == 'delegation':
        monkeypatch.setattr(scope, '_DELEGATION', contextvars.ContextVar('bad-delegation', default={'authority': None}))
    else:
        scope._CURRENT.set(None)
        monkeypatch.setattr(scope, '_ENGAGED', True)
    result = invoke('tool_call', {'calls': '['})
    assert result['error'] == scope.PUBLIC_TOOL_REFUSAL_COPY
    assert 'hint' not in result


def test_registry_bridge_guard_preserves_typed_feedback(admitted):
    from tools.registry import registry
    result = json.loads(registry.dispatch('tool_call', {'calls': '['}))
    assert result.get('error_type') == 'invalid_arguments', result
    assert result['argument'] == 'calls'


@pytest.mark.parametrize('route', ['parser', 'invoke', 'sequential'])
@pytest.mark.parametrize('revoked', [False, True])
def test_agent_consumers_preserve_feedback_and_identity_denial(admitted, route, revoked):
    from agent import tool_executor as executor
    from agent.agent_runtime_helpers import invoke_tool
    from agent.transports.types import ToolCall
    from agent.tool_call_batches import expand_local_tool_batches
    from agent.tool_dispatch_helpers import make_tool_result_message
    agent = SimpleNamespace()
    scope.capture_agent(agent)
    if revoked:
        admitted.cap.revoked = True
    args = {'calls': '['}
    if route == 'parser':
        call = ToolCall(id='argument-feedback-call', name='tool_call', arguments=json.dumps(args))
        expanded = expand_local_tool_batches([call])
        assert expanded == [call] and expanded[0].arguments == json.dumps(args)
        parsed = executor._parse_tool_call(agent, expanded[0])
        assert parsed.name == 'tool_call' and parsed.scope_block is None
        message = make_tool_result_message(parsed.name, parsed.parse_error, call.id)
        result = json.loads(message['content'])
    elif route == 'invoke':
        result = json.loads(invoke_tool(agent, 'tool_call', args, 'argument-feedback-test'))
    else:
        ref = executor._ToolCallRef('tool_call', args, 'argument-feedback-test', 'argument-feedback-call', [])
        dispatch = executor._resolve_sequential_dispatch(agent, ref, [])
        result = json.loads(dispatch.execute(args))
    if revoked:
        assert result['error'] == scope.PUBLIC_TOOL_REFUSAL_COPY and 'hint' not in result
    else:
        assert result.get('error_type') == 'invalid_arguments', result
        assert result['argument'] == 'calls'
    assert list((admitted.home / 'workspace').iterdir()) == []


def test_agent_invoke_structured_content_is_not_hidden(admitted):
    from agent.agent_runtime_helpers import invoke_tool
    agent = SimpleNamespace(_context_engine_tool_names=set(), _memory_manager=None,
        session_id='argument-feedback-session', valid_tool_names={'write_file'},
        enabled_toolsets=['file'], disabled_toolsets=None)
    scope.capture_agent(agent)
    result = json.loads(invoke_tool(agent, 'write_file', document('{"blocks":['),
        'argument-feedback-test', pre_tool_block_checked=True,
        skip_tool_request_middleware=True, skip_tool_execution_middleware=True))
    assert result.get('error_type') == 'invalid_arguments', result
    assert result['argument'] == 'content'
    assert list((admitted.home / 'workspace').iterdir()) == []


def test_valid_bridge_structured_document_and_create_only(admitted):
    from zipfile import ZipFile
    content = json.dumps({'blocks': [dict(type='title', text='Report'),
        dict(type='heading', level=1, text='Results'), dict(type='table', rows=[['Item', 'Value'], ['Work', '8']])]})
    args = document(content)
    result = invoke('tool_call', {'calls': [{'name': 'write_file', 'arguments': args}]})
    assert result['success'] is True and result['verified'] is True, result
    path = admitted.home / 'workspace/report.docx'
    before = path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == result['sha256']
    with ZipFile(path) as package:
        xml = package.read('word/document.xml')
        assert b'Report' in xml and b'Results' in xml and b'Work' in xml
    assert write(args)['error'] == 'document_already_exists'
    assert path.read_bytes() == before
