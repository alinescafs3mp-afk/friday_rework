import copy
from unittest.mock import MagicMock
import pytest
from test_ordinary_dialogue_continuation import env,entered,home,native_agent,protected,own_db
from hermes_cli import friday_prompt_scope as ps, friday_user_scope as scope
from agent import system_prompt as sp, conversation_loop as loop, prompt_builder as pb


def test_typed_ordinary_metadata_projection_preserves_schema_content_and_date(env,monkeypatch):
    monkeypatch.chdir(home(env)/'workspace')
    with entered(env):
        a=native_agent();a.model='PRIVATE_MODEL_69';a.provider='alibaba';a.platform='telegram';a.pass_session_id=True
        a._environment_probe=True;a._platform_hint_overrides={'telegram':'PRIVATE_PLATFORM_OVERRIDE_69'}
        from hermes_cli.plugins import RenderedPluginSystemPromptSection
        a._plugin_system_prompt_sections_snapshot=(RenderedPluginSystemPromptSection(plugin='fixture',id='user-section',position='after_memory',content='USER_PLUGIN_TEXT_69'),)
        monkeypatch.setattr(pb,'build_environment_hints',lambda:'PRIVATE_OS_HOME_69')
        tools=copy.deepcopy(a.tools);before=protected(home(env))
        prompt=sp.build_system_prompt(a,'USER_CONTENT Hermes Linux Alice.py')
        for token in ('PRIVATE_MODEL_69','PRIVATE_PLATFORM_OVERRIDE_69','PRIVATE_OS_HOME_69',str(home(env)),'Model:','Provider:','Session ID:','Hermes runtime environment','hermes-agent:'):
            assert token not in prompt,token
        assert 'USER_CONTENT Hermes Linux Alice.py' in prompt
        assert 'USER_PLUGIN_TEXT_69' in prompt
        assert 'Conversation started:' in prompt or 'Current date:' in prompt
        assert loop._stored_prompt_matches_runtime(a,prompt)
        assert a.tools==tools and protected(home(env))==before
        assert ps.DIALOGUE_GUIDANCE in prompt and ps.CONFIDENTIALITY_GUIDANCE in prompt
        assert ps.PRODUCT_HELP_GUIDANCE in prompt


def test_shipped_personality_view_and_unknown_user_personality_are_exact():
    suffix='\n\nПользовательский стиль и личные факты: имя Лена; язык Rust.'
    assert ps.ordinary_identity(ps._SHIPPED_IDENTITY+suffix)==ps.ORDINARY_IDENTITY+suffix
    assert 'Jericho' not in ps.ordinary_identity(ps._SHIPPED_IDENTITY+suffix)
    custom='My custom personality: Hermes is the title of my document.'
    assert ps.ordinary_identity(custom)==ps.ORDINARY_IDENTITY+'\n\n'+custom
    assert ps.ordinary_identity(None)==ps.ORDINARY_IDENTITY


def test_context_truncation_anchor_relative_preserves_user_text(env,monkeypatch):
    monkeypatch.chdir(home(env)/'workspace')
    with entered(env):
        p=home(env)/'workspace'/'AGENTS.md';p.write_text('USER_DOCUMENT')
        captured={}
        def truncate(body,warn_name,**kwargs):captured.update(kwargs);return body
        monkeypatch.setattr(pb,'_truncate_content',truncate)
        result=pb._context_section('USER_DOCUMENT','AGENTS.md','fixture',p,32768)
        assert 'USER_DOCUMENT' in result and captured['read_path']=='AGENTS.md'


def test_current_revision_reuses_cache_with_old_assistant_claims_preserved(env,monkeypatch):
    monkeypatch.chdir(home(env)/'workspace');db=own_db(env)
    try:
        with entered(env):
            a=native_agent(db);before=protected(home(env))
            for i in range(13):db.append_message(a.session_id,'assistant' if i%2==0 else 'user','Prior assistant internal claim 69 '+str(i))
            history=copy.deepcopy(db.get_messages(a.session_id))
            db.update_system_prompt(a.session_id,'OLD_PRIVATE_RUNTIME_69')
            row=db.get_session(a.session_id)
            import json
            meta=json.loads(row['model_config']);meta[ps.FIELD]['dialogue_revision']='friday.natural-dialogue.v1';db.update_session_meta(a.session_id,json.dumps(meta))
            loop._restore_or_build_system_prompt(a,'Continue my own actual question',history)
            a._build_system_prompt.assert_called_once();prompt=a._cached_system_prompt
            assert loop._stored_prompt_matches_runtime(a,prompt)
            for i in range(2):
                resumed=native_agent(db);loop._restore_or_build_system_prompt(resumed,None,history)
                resumed._build_system_prompt.assert_not_called();assert resumed._cached_system_prompt==prompt
            assert len(history)==14 and db.get_messages(a.session_id)==history
            assert protected(home(env))==before
    finally:db.close()


def test_workspace_metadata_projection_preserves_user_git_content(env):
    from agent.coding_context import WORKSPACE_BLOCK_HEADER
    with entered(env):
        a=native_agent();own=WORKSPACE_BLOCK_HEADER+'\n- Root: '+str(home(env)/'workspace'/'project')+'\nUSER COMMIT Hermes Linux'
        foreign=WORKSPACE_BLOCK_HEADER+'\n- Root: /foreign/secret\nPRIVATE FOREIGN'
        result=ps.ordinary_workspace_parts(a,(['PREFIX'],[own,foreign,'CUSTOM_USER_TEXT'],['TAIL']))
        assert result==(['PREFIX'],[WORKSPACE_BLOCK_HEADER+'\n- Root: project\nUSER COMMIT Hermes Linux','CUSTOM_USER_TEXT'],['TAIL'])
