import json, copy
from unittest.mock import patch
import pytest
from test_ordinary_dialogue_continuation import env, entered, home, own_db
from test_tool_result_context import actor
from hermes_cli import friday_user_scope as scope
from tui_gateway.server import _history_to_messages

@pytest.mark.parametrize('surface',['history','admin','tui','api'])
def test_fresh_process_managed_child_history_keeps_reasoning_private(env,monkeypatch,surface):
    from agent.history_commentary import project_history_commentary
    from hermes_cli.web_routers.sessions import _project_for_display
    from gateway.platforms.api_server import APIServerAdapter
    private='SYNTHETIC_PRIVATE_HISTORY_REASONING'
    row=dict(role='assistant',content='Safe answer',reasoning=private)
    original=copy.deepcopy(row)
    # The fixture previously provisions/admitted sources; reset the process-global
    # latch to its actual startup value to model a separate history-only process.
    monkeypatch.setattr(scope,'_ENGAGED',False)
    assert scope.current() is None and (home(env)/scope.MARKER).is_file()
    assert scope.policy(env.root) is not None
    assert scope.policy(home(env)) is None
    with scope.authority(home(env)):
        result={
            'history':lambda:project_history_commentary([row],home=home(env)),
            'admin':lambda:_project_for_display([row],home=home(env)),
            'tui':lambda:_history_to_messages([row],profile_home=home(env)),
            'api':lambda:APIServerAdapter._message_response(row),
        }[surface]()
    assert row==original
    assert private not in json.dumps(result), 'Managed child reasoning leaked on '+surface+' in fresh history-only process'

@pytest.mark.asyncio
async def test_managed_profile_export_uses_owning_profile_without_active_turn(env,tmp_path,monkeypatch):
    from hermes_cli.web_routers import sessions
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db);private='SYNTHETIC_PRIVATE_EXPORT_REASONING'
            assert a._flush_messages_to_session_db([dict(role='assistant',content='Safe answer',reasoning=private)])
        unmanaged=tmp_path/'unmanaged-dashboard';unmanaged.mkdir();(unmanaged/'config.yaml').write_text('{}')
        class Borrowed:
            def get_messages(self,*args,**kwargs):return db.get_messages(*args,**kwargs)
            def close(self):pass
        def withdb(profile,fn,**kwargs):return fn(db)
        monkeypatch.setattr(scope,'_ENGAGED',False)
        with scope.authority(unmanaged):
            assert scope.current() is None and scope.ordinary_presentation() is False
            with patch.object(sessions,'_with_db',side_effect=withdb),patch.object(sessions,'_open_session_db_for_profile',return_value=Borrowed()),patch.object(sessions,'_cron_profile_home',return_value=('fixture-user-1',home(env))):
                response=await sessions.export_session_endpoint(a.session_id,profile='fixture-user-1')
                parts=[]
                async for part in response.body_iterator:parts.append(part.decode() if isinstance(part,bytes) else part)
            assert private not in ''.join(parts), 'Managed-profile reasoning leaked by mixed-profile dashboard export'
    finally:db.close()

def test_unmanaged_history_diagnostics_remain_available(env,tmp_path,monkeypatch):
    from agent.history_commentary import project_history_commentary
    unmanaged=tmp_path/'unmanaged';unmanaged.mkdir();(unmanaged/'config.yaml').write_text('{}')
    monkeypatch.setattr(scope,'_ENGAGED',False)
    row=dict(role='assistant',content='Safe answer',reasoning='operator diagnostic')
    assert project_history_commentary([row],home=unmanaged)==[row]

@pytest.mark.parametrize('evidence',['missing_marker','invalid_marker','dangling_marker','marker_directory','invalid_parent_policy'])
def test_failed_admission_evidence_stays_private_without_minting_capability(env,monkeypatch,evidence):
    from agent.history_commentary import project_history_commentary
    marker=home(env)/scope.MARKER
    monkeypatch.setattr(scope,'_ENGAGED',False)
    assert scope.current() is None
    if evidence in ('missing_marker','dangling_marker','marker_directory','invalid_parent_policy'):
        marker.unlink()
    if evidence=='invalid_marker':marker.write_text('INVALID MARKER')
    elif evidence=='dangling_marker':marker.symlink_to(home(env)/'missing-marker-target')
    elif evidence=='marker_directory':marker.mkdir(mode=0o700)
    elif evidence=='invalid_parent_policy':
        config=json.loads((env.root/'config.yaml').read_text())
        config['plugins']['entries']['friday_rework']['settings']['user_isolation']['enabled']=False
        (env.root/'config.yaml').write_text(json.dumps(config))
    row=dict(role='assistant',content='Safe answer',reasoning='Private failed-admission reasoning')
    original=copy.deepcopy(row)
    with scope.authority(home(env)):
        assert scope.ordinary_presentation() is True
        assert scope.ordinary_message_view(row)==dict(role='assistant',content='Safe answer')
        assert project_history_commentary([row],home=home(env))==[dict(role='assistant',content='Safe answer')]
        assert scope.current() is None
        with pytest.raises(scope.ScopeDenied):scope.current(required=True)
    assert row==original and scope._ENGAGED is False


def test_explicit_profile_audience_preserves_ambient_home_and_unmanaged_diagnostics(env,tmp_path,monkeypatch):
    from hermes_constants import get_hermes_home
    unmanaged=tmp_path/'unmanaged-explicit';unmanaged.mkdir();(unmanaged/'config.yaml').write_text('{}')
    monkeypatch.setattr(scope,'_ENGAGED',False)
    row=dict(role='assistant',content='Answer',reasoning='Operator/private detail')
    original=copy.deepcopy(row)
    with scope.authority(unmanaged):
        before=get_hermes_home()
        assert scope.ordinary_presentation() is False
        assert scope.ordinary_message_view(row,home=home(env))==dict(role='assistant',content='Answer')
        assert get_hermes_home()==before and scope.current() is None
    with scope.authority(home(env)):
        before=get_hermes_home()
        assert scope.ordinary_presentation() is True
        assert scope.ordinary_message_view(row,home=unmanaged)==row
        assert get_hermes_home()==before and scope.current() is None
    assert row==original and scope._ENGAGED is False


def test_unmarked_unbound_native_sibling_preserves_diagnostics_and_safe_answer(env,monkeypatch):
    from types import SimpleNamespace
    from agent.history_commentary import project_history_commentary
    sibling=home(env).parent/'unmanaged-operator'
    sibling.mkdir(mode=0o700);(sibling/'config.yaml').write_text('{}')
    monkeypatch.setattr(scope,'_ENGAGED',False)
    assert not (sibling/scope.MARKER).exists()
    assert sibling.name not in {binding['runtime_profile'] for binding in scope.policy(env.root)['bindings']}
    row=dict(role='assistant',content='Safe answer',reasoning='Operator diagnostic')
    original=copy.deepcopy(row)
    with scope.authority(sibling):
        assert scope.current() is None and scope.policy(sibling) is None
        assert scope.ordinary_presentation() is False
        assert scope.ordinary_message_view(row)==row
        assert project_history_commentary([row],home=sibling)==[row]
        assert scope.guard_generated_reply(SimpleNamespace(),'Safe answer')==('Safe answer',False)
    assert row==original and scope._ENGAGED is False
