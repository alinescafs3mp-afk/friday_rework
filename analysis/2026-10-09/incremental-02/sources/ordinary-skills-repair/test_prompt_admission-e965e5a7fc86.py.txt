"""Effective native stored-prompt restore across actual product re-admission."""
import json
from unittest.mock import MagicMock
import pytest
from test_user_onboarding import env,complete,home,ident,save
from test_ordinary_skills import entered,document
from test_skill_privacy import install_document,revoke
from hermes_cli import friday_user_scope as scope
from hermes_cli import friday_prompt_scope as prompt_scope
from hermes_state import SessionDB
from agent import conversation_loop,system_prompt


def new_agent(db, caching=False):
    agent=MagicMock()
    agent._cached_system_prompt=None
    agent._cached_system_prompt_static=None
    agent.session_id='actual-native-own-session'
    agent.model='local-test';agent.provider='custom';agent.platform='cli'
    agent._session_db=db;agent._use_prompt_caching=caching
    agent.enabled_toolsets=agent.disabled_toolsets=None
    agent._auto_load_skills_resolved=False
    agent._persist_disabled=False
    agent.skip_context_files=False
    agent.valid_tool_names=['skill_view']
    agent.tools=[]
    agent._platform_hint_overrides=None
    agent._session_title_hint=''
    agent._surface_switch_note='';agent._gateway_turn_context_notes=''
    agent._build_system_prompt=MagicMock(side_effect=lambda _msg: 'NATIVE PROMPT\n'+''.join(system_prompt._auto_load_parts(agent)))
    scope.capture_agent(agent)
    return agent


def own_db(env):
    db=SessionDB(home(env)/'state.db')
    db.create_session('actual-native-own-session','telegram',user_id='1',profile_name='user-1',
        origin_json=json.dumps({'friday_account_origin':{'schema':'friday.account_origin.v1',
            'platform':'telegram','transport_profile':'default','account_id':'bot-A'}}),
        model_config={'keep_native_field':'PRESERVE'})
    db.append_message('actual-native-own-session','user','Continue my original task')
    return db


@pytest.mark.parametrize('caching',[False,True])
def test_real_session_reuses_same_admission_but_rebuilds_after_readmission(env,caching):
    env.template['config']['skills'].update({'auto_load':['procedure']})
    save(env,env.cfg)
    complete(env);p=install_document(home(env),document(body='OLD_AUTOLOAD_INSTRUCTIONS'))
    db=own_db(env)
    try:
        with entered(env) as first_cap:
            first=new_agent(db,caching)
            conversation_loop._restore_or_build_system_prompt(first,None,[])
            old=first._cached_system_prompt
            assert 'OLD_AUTOLOAD_INSTRUCTIONS' in old
            saved=db.get_session(first.session_id)
            stored=json.loads(saved['model_config'])
            assert stored['keep_native_field']=='PRESERVE'
            assert stored[prompt_scope.FIELD]['generation']==first_cap.admission_generation
            second=new_agent(db,caching)
            conversation_loop._restore_or_build_system_prompt(second,None,[{'role':'user','content':'continue'}])
            assert second._cached_system_prompt==old
            second._build_system_prompt.assert_not_called()
            revoke(env)
            with pytest.raises(scope.ScopeDenied):conversation_loop._restore_or_build_system_prompt(second,None,[{'role':'user','content':'continue'}])
        # Authorized operator reenables the same real principal; this is a new
        # native admission, not resetting the retained revoked capability.
        env.admin.set_user('default',**ident(),enabled=True,role='user')
        p.write_text(document(body='NEW_AUTOLOAD_INSTRUCTIONS'));p.chmod(0o600)
        with entered(env) as fresh_cap:
            assert fresh_cap.admission_generation!=first_cap.admission_generation
            third=new_agent(db,caching)
            conversation_loop._restore_or_build_system_prompt(third,None,[{'role':'user','content':'continue'}])
            effective=third._cached_system_prompt
            assert 'NEW_AUTOLOAD_INSTRUCTIONS' in effective and 'OLD_AUTOLOAD_INSTRUCTIONS' not in effective
            third._build_system_prompt.assert_called_once()
            saved=db.get_session(third.session_id)
            assert saved['system_prompt']==effective
            assert json.loads(saved['model_config'])[prompt_scope.FIELD]['generation']==fresh_cap.admission_generation
            assert db.get_messages(third.session_id)[0]['content']=='Continue my original task'
    finally:db.close()


def test_native_prompt_and_provenance_write_rolls_back_as_one_transaction(env):
    complete(env);db=own_db(env)
    try:
        with entered(env):
            db.update_system_prompt('actual-native-own-session','FIRST')
            before=db.get_session('actual-native-own-session')
            # Native preexisting malformed metadata must not be overwritten or
            # allow a prompt write without matching ownership provenance.
            db.update_session_meta('actual-native-own-session','malformed: [')
            with pytest.raises(Exception):db.update_system_prompt('actual-native-own-session','MUST_NOT_PERSIST')
            after=db.get_session('actual-native-own-session')
            assert after['system_prompt']==before['system_prompt']=='FIRST'
            assert after['model_config']=='malformed: ['
    finally:db.close()


def tool_definition(description):
    return {'type':'function','function':{'name':'skill_view','description':description,
            'parameters':{'type':'object','properties':{}}}}


@pytest.mark.parametrize('missing',[None,''])
def test_readmission_missing_prompt_never_restores_prior_tool_definitions(env,missing):
    complete(env);db=own_db(env)
    try:
        with entered(env):
            old=new_agent(db);old.tools=[tool_definition('OLD_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(old,None,[])
            assert 'OLD_DEFINITION' in db.get_session(old.session_id)['tool_names']
            db.update_system_prompt(old.session_id,missing)
            revoke(env)
        env.admin.set_user('default',**ident(),enabled=True,role='user')
        with entered(env):
            fresh=new_agent(db);fresh.tools=[tool_definition('NEW_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(fresh,None,[{'role':'user','content':'continue'}])
            assert 'OLD_DEFINITION' not in json.dumps(fresh.tools)
            assert 'NEW_DEFINITION' in json.dumps(fresh.tools)
    finally:db.close()


def test_transition_clears_old_pin_atomically_when_later_pin_write_fails(env,monkeypatch):
    complete(env);db=own_db(env)
    try:
        with entered(env):
            old=new_agent(db);old.tools=[tool_definition('OLD_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(old,None,[])
            same=new_agent(db);same.tools=[tool_definition('SAME_ADMISSION_DIFFERENT_BYTES')]
            conversation_loop._restore_or_build_system_prompt(same,None,[{'role':'user','content':'continue'}])
            assert 'OLD_DEFINITION' in json.dumps(same.tools)
            revoke(env)
        env.admin.set_user('default',**ident(),enabled=True,role='user')
        with entered(env):
            fresh=new_agent(db);fresh.tools=[tool_definition('NEW_DEFINITION')]
            with monkeypatch.context() as m:
                def failed(*a,**kw):raise OSError('synthetic pin commit failure')
                m.setattr(db,'update_session_tool_names',failed)
                conversation_loop._restore_or_build_system_prompt(fresh,None,[{'role':'user','content':'continue'}])
                assert db.get_session(fresh.session_id)['tool_names'] is None
            resumed=new_agent(db);resumed.tools=[tool_definition('CURRENT_DEFINITION')]
            conversation_loop._restore_or_build_system_prompt(resumed,None,[{'role':'user','content':'continue'}])
            assert 'OLD_DEFINITION' not in json.dumps(resumed.tools)
            assert 'CURRENT_DEFINITION' in json.dumps(resumed.tools)
    finally:db.close()
