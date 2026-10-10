"""Concrete native cache mismatch window under invalid persisted provenance."""
import json
from test_user_onboarding import env,complete
from test_ordinary_skills import entered
from test_prompt_admission import own_db,new_agent,tool_definition
from agent import conversation_loop
from hermes_cli import friday_prompt_scope

def test_extra_provenance_key_and_failed_tool_commit(env,monkeypatch):
    complete(env);db=own_db(env)
    try:
        with entered(env):
            old=new_agent(db);old.tools=[tool_definition('OLD_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(old,None,[])
            before=db.get_session(old.session_id)
            assert 'OLD_DEFINITION' in before['tool_names']
            meta=json.loads(before['model_config'])
            meta[friday_prompt_scope.FIELD]['obsolete_extra_field']=True
            db.update_session_meta(old.session_id,json.dumps(meta))
            row=db.get_session(old.session_id)
            fresh=new_agent(db);fresh.tools=[tool_definition('NEW_DEFINITION')]
            assert not friday_prompt_scope.matches(fresh,row['system_prompt'],row)
            with monkeypatch.context() as m:
                def failed(*a,**kw):raise OSError('synthetic pin commit failure')
                m.setattr(db,'update_session_tool_names',failed)
                conversation_loop._restore_or_build_system_prompt(fresh,None,[{'role':'user','content':'continue'}])
                assert 'NEW_DEFINITION' in json.dumps(fresh.tools)
            committed=db.get_session(old.session_id)
            assert friday_prompt_scope.matches(fresh,committed['system_prompt'],committed)
            resumed=new_agent(db);resumed.tools=[tool_definition('CURRENT_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(resumed,None,[{'role':'user','content':'continue'}])
            observation={'invalid_extra_key_mismatch_confirmed':True,'fresh_tools_before_failed_pin':fresh.tools,
                         'committed_tool_names':committed['tool_names'],'resumed_tools':resumed.tools,
                         'old_pin_restored': 'OLD_DEFINITION' in json.dumps(resumed.tools)}
            assert not observation['old_pin_restored'],'obsolete tool definition restored after invalid-provenance rebuild and failed pin commit'
    finally:db.close()

"""Native DB/restore fault windows for rejected and valid provenance.

Ordinary onboarding, admission and SessionDB are real. The declared tools and
agent prompt builder are fixture inputs; no model or deployed user is involved.
"""
import json
import pytest
from test_user_onboarding import env, complete
from test_ordinary_skills import entered
from test_prompt_admission import own_db, new_agent, tool_definition
from agent import conversation_loop
from hermes_cli import friday_prompt_scope


def corrupt_stamp(db, agent, variant):
    row = db.get_session(agent.session_id)
    meta = json.loads(row['model_config'])
    stamp = meta[friday_prompt_scope.FIELD]
    if variant == 'missing':
        del meta[friday_prompt_scope.FIELD]
    elif variant == 'null':
        meta[friday_prompt_scope.FIELD] = None
    elif variant == 'empty_dict':
        meta[friday_prompt_scope.FIELD] = {}
    elif variant == 'empty_string':
        meta[friday_prompt_scope.FIELD] = ''
    elif variant == 'list':
        meta[friday_prompt_scope.FIELD] = [stamp]
    elif variant == 'missing_field':
        del stamp['schema']
    elif variant == 'extra_field':
        stamp['obsolete_extra_field'] = True
    elif variant == 'bad_digest':
        stamp['prompt_sha256'] = '0' * 64
    else:
        raise AssertionError(variant)
    db.update_session_meta(agent.session_id, json.dumps(meta))


@pytest.mark.parametrize('variant', [
    'missing', 'null', 'empty_dict', 'empty_string', 'list',
    'missing_field', 'extra_field', 'bad_digest',
])
def test_invalid_stamp_clears_pin_in_native_prompt_transaction(env, monkeypatch, variant):
    complete(env)
    db = own_db(env)
    try:
        with entered(env):
            old = new_agent(db)
            old.tools = [tool_definition('OLD_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(old, None, [])
            corrupt_stamp(db, old, variant)
            invalid = db.get_session(old.session_id)
            fresh = new_agent(db)
            fresh.tools = [tool_definition('NEW_DEFINITION')]
            assert not friday_prompt_scope.matches(fresh, invalid['system_prompt'], invalid)
            with monkeypatch.context() as m:
                def fail_pin(*args, **kwargs):
                    raise OSError('synthetic separate pin write failure')
                m.setattr(db, 'update_session_tool_names', fail_pin)
                conversation_loop._restore_or_build_system_prompt(
                    fresh, None, [{'role': 'user', 'content': 'continue'}])
                committed = db.get_session(fresh.session_id)
                assert committed['tool_names'] is None
                assert friday_prompt_scope.matches(fresh, committed['system_prompt'], committed)
                assert 'NEW_DEFINITION' in json.dumps(fresh.tools)
                assert json.loads(committed['model_config'])['keep_native_field'] == 'PRESERVE'
            resumed = new_agent(db)
            resumed.tools = [tool_definition('CURRENT_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(
                resumed, None, [{'role': 'user', 'content': 'continue'}])
            assert 'OLD_DEFINITION' not in json.dumps(resumed.tools)
            assert 'CURRENT_DEFINITION' in json.dumps(resumed.tools)
            assert db.get_messages(old.session_id)[0]['content'] == 'Continue my original task'
    finally:
        db.close()


@pytest.mark.parametrize('caching', [False, True])
def test_valid_stamp_keeps_pin_across_same_admission_prompt_rewrite(env, monkeypatch, caching):
    complete(env)
    db = own_db(env)
    try:
        with entered(env):
            old = new_agent(db, caching)
            old.tools = [tool_definition('SAME_ADMISSION_PIN')]
            conversation_loop._restore_or_build_system_prompt(old, None, [])
            before = db.get_session(old.session_id)
            # Native rewrites within the same valid admission retain their tool
            # freeze even when the prompt bytes change and re-pinning then fails.
            replacement = 'REFRESHED_SAME_ADMISSION_PROMPT'
            db.update_system_prompt(old.session_id, replacement)
            with monkeypatch.context() as m:
                def fail_pin(*args, **kwargs):
                    raise OSError('synthetic separate pin write failure')
                m.setattr(db, 'update_session_tool_names', fail_pin)
                with pytest.raises(OSError):
                    db.update_session_tool_names(old.session_id, [])
            committed = db.get_session(old.session_id)
            assert committed['tool_names'] == before['tool_names']
            assert friday_prompt_scope.matches(old, replacement, committed)
            resumed = new_agent(db, caching)
            resumed.tools = [tool_definition('CHANGED_FIXTURE_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(
                resumed, None, [{'role': 'user', 'content': 'continue'}])
            assert resumed._cached_system_prompt == replacement
            resumed._build_system_prompt.assert_not_called()
            assert 'SAME_ADMISSION_PIN' in json.dumps(resumed.tools)
            assert 'CHANGED_FIXTURE_DEFINITION' not in json.dumps(resumed.tools)
            assert db.get_messages(old.session_id)[0]['content'] == 'Continue my original task'
    finally:
        db.close()


def test_pin_clear_rolls_back_with_failed_native_prompt_write(env, monkeypatch):
    complete(env)
    db = own_db(env)
    try:
        with entered(env):
            old = new_agent(db)
            old.tools = [tool_definition('OLD_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(old, None, [])
            corrupt_stamp(db, old, 'extra_field')
            before = db.get_session(old.session_id)
            with monkeypatch.context() as m:
                def fail_prompt(*args, **kwargs):
                    raise OSError('synthetic native prompt storage failure')
                m.setattr(db, '_store_system_prompt', fail_prompt)
                with pytest.raises(OSError):
                    db.update_system_prompt(old.session_id, 'MUST_NOT_PERSIST')
            after = db.get_session(old.session_id)
            for field in ('system_prompt', 'model_config', 'tool_names'):
                assert after[field] == before[field]
            assert not friday_prompt_scope.matches(old, after['system_prompt'], after)
    finally:
        db.close()
