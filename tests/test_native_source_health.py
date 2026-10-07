"""Affected native hook/read behavior under the existing offline source fixture."""
import json
from types import SimpleNamespace

import pytest

from test_user_isolation import users  # noqa: F401
from hermes_cli import friday_user_scope as scope


@pytest.mark.parametrize('verdict', ['allow', 'block', 'revoked'])
def test_concurrent_tool_hook_preserves_identity_and_rechecks_authority(users, verdict):
    from agent.agent_runtime_helpers import invoke_tool
    from hermes_cli import plugins
    from tools.memory_tool import MemoryStore
    seen = []
    with users.enter(0):
        store = MemoryStore()
        store.load_from_disk()
        agent = SimpleNamespace(_memory_store=store, _memory_manager=None, session_id='original-session',
                                _current_turn_id='original-turn', _current_api_request_id='original-api')
        scope.capture_agent(agent)
        def before(name, arguments, **identity):
            seen.append((name, identity))
            if verdict == 'revoked':
                users.access('1', enabled=False)
            return ('blocked-by-hook' if verdict == 'block' else None,
                    {**arguments, 'content': 'modified-own-memory'})
        users.monkeypatch.setattr(plugins, '_dispatch_pre_tool_call_hooks', before)
        result = json.loads(invoke_tool(agent, 'memory', {'action': 'add', 'content': 'original'},
                                        'original-task', tool_call_id='original-call'))
        assert seen == [('memory', dict(task_id='original-task', session_id='original-session',
                                       turn_id='original-turn', api_request_id='original-api',
                                       tool_call_id='original-call', middleware_trace=[]))]
        if verdict == 'allow':
            assert result['success']
            store.load_from_disk()
            assert 'modified-own-memory' in store.format_for_system_prompt('memory')
        else:
            assert result['error'] == ('blocked-by-hook' if verdict == 'block' else 'product_user_scope_refused')
            assert not (users.homes[0] / 'memories/MEMORY.md').exists()


@pytest.mark.parametrize('body,conflicts', [
    ('1|<<<<<<< HEAD\n2|old\n3|=======\n4|new\n5|>>>>>>> branch', 1),
    ("1|print('<<<<<<< not a conflict')", 0),
    ('', 0),
])
def test_ordinary_read_keeps_conflict_hints_after_native_read_pipeline(tmp_path, monkeypatch, body, conflicts):
    from tools import file_tools
    from tools.file_operations_common import ReadResult
    # Existing donor fixture seam: no shell/environment construction is authorized.
    monkeypatch.setattr(scope, '_ENGAGED', False)
    calls = []
    def read(path, offset, limit):
        calls.append((path, offset, limit))
        return ReadResult(content=body, total_lines=len(body.splitlines()), file_size=len(body))
    ops = SimpleNamespace(env=None, read_file=read)
    monkeypatch.setattr(file_tools, '_get_file_ops', lambda task_id: ops)
    path = tmp_path / 'plain.py'
    path.write_text('fixture', encoding='utf-8')
    result = json.loads(file_tools.read_file_tool(str(path), offset=1, limit=20, task_id=str(path)))
    assert calls == [(str(path), 1, 20)]
    assert result['content'] == body
    assert result.get('conflict_blocks', 0) == conflicts
    assert ('merge-conflict' in result.get('_hint', '')) == bool(conflicts)
