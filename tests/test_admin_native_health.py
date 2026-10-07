"""Behavior at the native health-refactor boundaries; synthetic stores and owner only."""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from test_admin_foundation import env  # noqa: F401


@pytest.mark.parametrize('outcome', ['accepted', 'owner-failure', 'scheduling-failure'])
def test_gateway_control_preserves_secret_safe_unknown_and_owner_scope(env, monkeypatch, outcome):
    from hermes_cli import plugins, profiles, plugins_gateway_control
    from hermes_constants import get_hermes_home

    secret = 'synthetic-SDK-token-must-never-be-returned'
    seen = []

    def owner(raw):
        seen.append((get_hermes_home(), json.loads(raw)))
        if outcome == 'owner-failure':
            raise LookupError(secret)
        return {'accepted': True, 'execution': 'CONFIRMED'}

    manager = SimpleNamespace(
        _plugins={'fixture': SimpleNamespace(enabled=True)},
        _gateway_verb_handlers={'fixture:stop': {'plugin_key': 'fixture', 'handler': owner}},
    )
    monkeypatch.setattr(plugins, 'get_plugin_manager', lambda: manager)
    monkeypatch.setattr(profiles, 'get_profile_dir', lambda name: env.satellite)
    runner = SimpleNamespace(served_profile_names=lambda: ['satellite'])
    loop = asyncio.new_event_loop()
    started = threading.Event()

    def serve():
        loop.call_soon(started.set)
        loop.run_forever()

    thread = threading.Thread(target=serve)
    thread.start()
    assert started.wait(3)
    before = get_hermes_home()
    try:
        if outcome == 'scheduling-failure':
            def refuse(coro, event_loop):
                coro.close()
                raise RuntimeError(secret)
            monkeypatch.setattr(plugins_gateway_control.asyncio, 'run_coroutine_threadsafe', refuse)
        result = plugins_gateway_control.plugin_control_verb(runner, loop)({
            'profile': 'satellite', 'plugin': 'fixture', 'control': 'stop', 'arguments': {'task_id': 'owned'},
        })
        assert secret not in json.dumps(result)
        assert get_hermes_home() == before
        if outcome == 'accepted':
            assert result == {'accepted': True, 'execution': 'CONFIRMED'}
        else:
            assert result == {
                'accepted': False, 'execution': 'UNKNOWN',
                'error': 'owning_control_unconfirmed' if outcome == 'owner-failure' else 'owning_gateway_unavailable',
            }
        assert seen == ([] if outcome == 'scheduling-failure' else [
            (env.satellite, {'profile': 'satellite', 'task_id': 'owned'}),
        ])
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=3)
        assert not thread.is_alive()
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()


@pytest.mark.parametrize('replacement', [{'section': {}}, {'section': 'scalar'}, {}])
def test_native_config_omission_guard_keeps_exact_bytes(env, replacement):
    from hermes_cli import config
    path = env.home / 'guarded.yaml'
    original = '# preserve my settings\nsection:\n  a: 1\n  b: 2\n'
    path.write_text(original, encoding='utf-8')
    with pytest.raises(RuntimeError, match='would lose settings'):
        config.atomic_config_write(path, replacement)
    assert path.read_text(encoding='utf-8') == original
    config.atomic_config_write(path, {'section': {'a': 3, 'b': 2}})
    assert config.require_readable_config_before_write(path)['section'] == {'a': 3, 'b': 2}


@pytest.mark.parametrize('declared,fail', [('fixture-tool', False), (['fixture-tool'], True)])
def test_skill_view_activates_dependencies_without_losing_content(env, monkeypatch, declared, fail):
    import pm
    from tools import skills_tool
    path = env.home / 'skills' / 'fixture-deps'
    path.mkdir(parents=True)
    (path / 'SKILL.md').write_text(
        '---\nname: fixture-deps\ndescription: synthetic dependency control\ndeps: '
        + json.dumps(declared) + '\n---\nUSEFUL_DEPENDENT_CONTENT\n', encoding='utf-8')
    attempts = []

    def ensure(package):
        attempts.append(package)
        if fail:
            raise RuntimeError('synthetic package unavailable')

    monkeypatch.setattr(pm, 'ensure', ensure)
    skills_tool.clear_skills_cache()
    skills_tool.reset_skill_view_dedup()
    result = json.loads(skills_tool.skill_view('fixture-deps', preprocess=False))
    assert result['success'] and 'USEFUL_DEPENDENT_CONTENT' in result['content']
    assert attempts == ['fixture-tool']
    if fail:
        assert 'synthetic package unavailable' in result['deps_note']
        assert 'hermes pm install fixture-tool' in result['deps_note']
    else:
        assert 'deps_note' not in result


@pytest.mark.parametrize('metadata,expected', [
    ({'hermes': {'tags': ['nested'], 'related_skills': ['nested-peer']}}, (['nested'], ['nested-peer'])),
    ({'hermes': {}}, (['fallback'], ['fallback-peer'])),
    ('legacy-scalar', (['fallback'], ['fallback-peer'])),
])
def test_skill_view_preserves_metadata_precedence_and_legacy_fallback(env, metadata, expected):
    from tools import skills_tool
    path = env.home / 'skills' / 'fixture-metadata'
    path.mkdir(parents=True)
    (path / 'SKILL.md').write_text(
        '---\nname: fixture-metadata\ndescription: synthetic metadata control\n'
        'tags: [fallback]\nrelated_skills: [fallback-peer]\nmetadata: '
        + json.dumps(metadata) + '\n---\nUSEFUL_METADATA_CONTENT\n', encoding='utf-8')
    skills_tool.clear_skills_cache()
    result = json.loads(skills_tool.skill_view('fixture-metadata', preprocess=False))
    assert result['success'] and 'USEFUL_METADATA_CONTENT' in result['content']
    assert (result['tags'], result['related_skills']) == expected
    assert result.get('metadata') == (metadata if isinstance(metadata, dict) else None)
