"""Real native offline channel/file journey controls; no model/transport acceptance."""
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from test_ordinary_dialogue_continuation import env, entered, home, own_db
from test_tool_result_context import actor
from test_ordinary_private_reply_compression import actor as stream_actor
from hermes_cli import friday_user_scope as scope
from agent import session_persistence as persistence, tool_executor as te
from agent.tool_result_classification import tool_effects_unknown
from tools.budget_config import DEFAULT_BUDGET
from tui_gateway.server import _history_to_messages

pytestmark = pytest.mark.parametrize('env', ['write-file-boundary'], indirect=True)

PRIVATE_FIELDS = ('reasoning', 'reasoning_content', 'reasoning_details', 'codex_reasoning_items')


def tool_row(name, cid, args, **extra):
    return dict(role='assistant', content=None, tool_calls=[dict(id=cid, type='function',
        function=dict(name=name, arguments=json.dumps(args)))], **extra)


def execute(a, row, fn):
    call = row['tool_calls'][0]
    ref = te._ToolCallRef(call['function']['name'], json.loads(call['function']['arguments']),
                          'native-task', call['id'], [])
    def scoped(args):
        scope.guard_tool(ref.name, args)
        return fn(args)
    result = te._run_sequential_tool_execution_middleware(a, **ref.middleware_kwargs(), execute=scoped)
    assert result.dispatched and not result.blocked
    return ref, result


@pytest.mark.parametrize('field', PRIVATE_FIELDS + ('codex_analysis',))
def test_private_reasoning_survives_real_storage_and_model_replay(env, field):
    db = own_db(env)
    try:
        with entered(env):
            a = actor(db)
            private = 'Own service '+str(home(env))+' workspace '+str(home(env)/'workspace')
            value = private if field in ('reasoning', 'reasoning_content') else [{'type':'reasoning','summary':private,'encrypted_content':'private-sealed-replay'}]
            row = dict(role='assistant',content='Safe public answer')
            if field == 'codex_analysis':
                row['codex_message_items']=[dict(type='message', role='assistant', phase='analysis', content=[dict(type='output_text',text=private)])]
            else:
                row[field]=value
            original=copy.deepcopy(row)
            assert a._flush_messages_to_session_db([row])
            assert not getattr(a,'_friday_reply_withheld',False)
            assert all(row[k]==v for k,v in original.items())
            replay = db.get_messages_as_conversation(a.session_id)[-1]
            key = 'codex_message_items' if field == 'codex_analysis' else field
            assert replay[key] == original[key]
            assert db.get_meta('friday.private_reply.latest') is None
    finally:
        db.close()


def test_actual_describe_write_file_answer_media_journey_with_hidden_own_paths(env):
    from tools.tool_search import dispatch_tool_describe,ToolSearchConfig
    from gateway.platforms.base import BasePlatformAdapter
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db)
            schema={'type':'function','function':{'name':'write_file','description':'Write a user file',
                'parameters':{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content']}}}
            private='Need my own workspace '+str(home(env)/'workspace')+'; service '+str(home(env))
            messages=[tool_row('tool_describe','describe-call',{'names':['write_file']},reasoning_content=private)]
            assert a._flush_messages_to_session_db(messages)
            assert not getattr(a,'_friday_reply_withheld',False)
            ref,out=execute(a,messages[-1],lambda args:dispatch_tool_describe(args,current_tool_defs=[schema],config=ToolSearchConfig.from_raw({'defer':['write_file']}),connector_describe=lambda *a,**kw:pytest.fail('remote describe forbidden')))
            assert 'write_file' in json.loads(out.result)['tools']
            assert te._commit_tool_result(a,messages,ref,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None)
            # Current execution has no no-effect proof for wrappers/callbacks. A
            # catalog tool name alone must never manufacture an authoritative none.
            assert messages[-1].get('effect_disposition') is None
            assert tool_effects_unknown(messages)
            target=home(env)/'workspace'/'report.txt'
            row=tool_row('write_file','write-call',{'path':str(target),'content':'Useful user report\n'},reasoning_content=private)
            messages.append(row)
            assert a._flush_messages_to_session_db(messages)
            assert json.loads(row['tool_calls'][0]['function']['arguments'])['path']=='report.txt'
            ref,out=execute(a,row,lambda args:scope.scoped_file('write_file',args,task_id='native-task'))
            assert json.loads(out.result)['bytes_written']==19
            assert te._commit_tool_result(a,messages,ref,out.result,budget=DEFAULT_BUDGET,tool_duration=.01,is_error=False,blocked=False,effect_disposition=None)
            public,blocked=scope.guard_generated_reply(a,'Your report MEDIA:'+str(target))
            assert not blocked and public=='Your report MEDIA:"./report.txt"'
            messages.append(dict(role='assistant',content=public,reasoning=private))
            assert a._flush_messages_to_session_db(messages)
            media,text=BasePlatformAdapter.extract_media(public)
            assert media==[(str(target),False)] and text=='Your report'
            assert target.read_text()=='Useful user report\n'
            assert not getattr(a,'_friday_reply_withheld',False)
            assert db.get_messages_as_conversation(a.session_id)[-1]['reasoning']==private
    finally:
        db.close()


@pytest.mark.parametrize('channel',['content','api_content','codex_commentary','codex_final','structured_content'])
def test_public_disclosure_still_refuses_even_with_benign_private_reasoning(env,channel):
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db);secret=str(home(env)/'config.yaml')
            row=dict(role='assistant',content='Safe',reasoning_content='Benign private scratchpad')
            if channel.startswith('codex_'):
                row['codex_message_items']=[dict(type='message',role='assistant',phase=channel.split('_')[1],content=[dict(type='output_text',text=secret)])]
            elif channel=='structured_content':row['content']=[dict(type='text',text=secret)]
            else:row[channel]=secret
            assert a._flush_messages_to_session_db([row])
            assert a._friday_reply_withheld and row['content']==scope.PRIVATE_REPLY_COPY
            assert row['reasoning_content'] is None
            assert secret not in json.dumps(db.get_messages(a.session_id))
    finally:
        db.close()


@pytest.mark.parametrize('phase',['commentary','final','final_answer',None])
def test_visible_codex_self_claim_is_guarded(env,phase):
    with entered(env):
        a=stream_actor();row=dict(role='assistant',content='Safe',codex_message_items=[dict(type='message',role='assistant',phase=phase,content=[dict(type='output_text',text='Моя модель — private-router.')])])
        scope.guard_generated_rows(a,[row],[row])
        assert a._friday_reply_withheld


@pytest.mark.parametrize('escape',['absolute','dotdot','symlink','escaped_json'])
def test_private_tool_path_and_authority_escape_still_refused(env,escape):
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db);target=home(env)/'workspace'/'link';target.symlink_to(home(env)/'config.yaml')
            raw={'absolute':str(home(env)/'config.yaml'),'dotdot':'../config.yaml','symlink':'link','escaped_json':str(home(env)/'config.yaml')}[escape]
            row=tool_row('write_file','escaped',{'path':raw,'content':'DO NOT WRITE'},reasoning_content='Private '+str(home(env)))
            if escape=='escaped_json':
                args=row['tool_calls'][0]['function']['arguments']
                row['tool_calls'][0]['function']['arguments']=args.replace('/', '\\/')
            flushed=a._flush_messages_to_session_db([row])
            if escape in ('absolute','escaped_json'):
                assert not flushed and a._friday_reply_withheld
                assert a._friday_no_dispatch_tool_calls==[('escaped','write_file')]
            else:
                assert flushed and not getattr(a,'_friday_reply_withheld',False)
            # Persistence preflight and the actual descriptor boundary are distinct.
            with pytest.raises((scope.ScopeDenied, OSError)):
                scope.scoped_file('write_file',{'path':raw,'content':'DO NOT WRITE'})
            assert 'DO NOT WRITE' not in (home(env)/'config.yaml').read_text()
    finally:
        db.close()


def test_actual_reasoning_callbacks_progress_tts_and_finalizer_result_are_private(env):
    from agent.turn_response_intake import _relay_thinking
    from agent.chat_completion_helpers import _assistant_reasoning_text
    from agent import turn_finalizer as tf
    from agent.agent_runtime_helpers import strip_think_blocks
    with entered(env):
        a=stream_actor();seen=[];reason=[];tts=[];progress=[]
        a.reasoning_callback=reason.append;a._stream_callback=tts.append;a.stream_delta_callback=seen.append
        a.tool_progress_callback=lambda *args:progress.append(args)
        a._strip_think_blocks=lambda text:strip_think_blocks(None,text)
        private=str(home(env)/'config.yaml')
        a._fire_reasoning_delta(private)
        a._fire_stream_delta('<think>'+private[:10]);a._fire_stream_delta(private[10:]+'</think>Safe answer')
        _relay_thinking(a,'<think>'+private+'</think>')
        a._extract_reasoning=lambda msg:msg.reasoning;a.verbose_logging=False
        a.stream_delta_callback=a._stream_callback=None
        assert _assistant_reasoning_text(a,NS(reasoning=private))==private
        assert reason==progress==seen==tts==[]
        # Reuse the real finalizer fixture's setup, with a genuine private
        # reasoning row. Existing finalizer guards and one-time delivery execute.
        a.stream_delta_callback=seen.append;a._stream_callback=tts.append
        a.max_iterations=8;a.platform='telegram';a.model='public-test';a.provider='custom';a.base_url='http://localhost';a.context_compressor=NS(last_prompt_tokens=0);a._tool_guardrail_halt_decision=None;a._skill_nudge_interval=0;a._iters_since_skill=0;a.valid_tool_names=set();a._persist_disabled=True;a.request_overrides={};a._drain_pending_steer=lambda:None;a.clear_interrupt=lambda:None;a._sync_external_memory_for_turn=lambda **kw:None
        for key in tf._SESSION_TOKEN_KEYS+tf._SESSION_COST_KEYS:setattr(a,'session_'+key,0)
        with patch.object(tf,'_resolve_budget_fallback',return_value=('Safe answer','text_response(stop)',False,False)),patch.object(tf,'_rollback_interrupted_preflight_display'),patch.object(tf,'_guarded_cleanup'),patch.object(tf,'_log_turn_exit'),patch('hermes_cli.observability.shared_metrics_harness.finish_turn'),patch.object(tf,'_invoke_hook_safely',return_value=[]):
            rows=[dict(role='user',content='Task'),dict(role='assistant',content='Safe answer',reasoning=private)]
            result=tf.finalize_turn(a,final_response='Safe answer',api_call_count=1,interrupted=False,failed=False,messages=rows,conversation_history=[],effective_task_id=None,turn_id='turn',user_message='Task',original_user_message='Task',_should_review_memory=False,_turn_exit_reason='text_response(stop)')
        assert result['completed'] and not result['failed'] and result['last_reasoning'] is None
        assert result['messages'][-1]['reasoning']==private
        assert seen==tts==['Safe answer'] and reason==progress==[]


@pytest.mark.asyncio
async def test_actual_public_administration_history_and_openai_response_projections(env):
    from aiohttp import web
    from aiohttp.test_utils import TestClient,TestServer
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter,_project_client_message
    from gateway.platforms.api_server_openai_routes import _turn_reasoning_text
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db);private='PRIVATE_REASONING '+str(home(env))
            row=dict(role='assistant',content='Safe answer',reasoning=private,reasoning_content=private,reasoning_details=[dict(text=private)],codex_reasoning_items=[dict(type='reasoning',encrypted_content=private)],codex_message_items=[dict(type='message',role='assistant',phase='analysis',content=[dict(type='output_text',text=private)])],api_content='Safe answer',display_reasoning=private)
            db.append_message(a.session_id,'assistant',row['content'],**{key:row[key] for key in PRIVATE_FIELDS+('codex_message_items','api_content')})
            original=copy.deepcopy(row)
            adapter=APIServerAdapter(PlatformConfig(enabled=True,extra={}))
            adapter._session_db=db
            assert private not in json.dumps(_project_client_message(row))
            assert private not in json.dumps(adapter._message_response(row))
            result=dict(final_response='Safe answer',completed=True,messages=[dict(role='user',content='q'),row])
            assert _turn_reasoning_text([], 'q',result)==''
            assert private not in json.dumps(adapter._extract_output_items(result))
            assert private not in json.dumps(adapter._turn_transcript_messages([], 'q',result))
            app=web.Application();app['api_server_adapter']=adapter
            app.router.add_get('/api/sessions/{session_id}/messages',adapter._handle_session_messages)
            app.router.add_post('/v1/chat/completions',adapter._handle_chat_completions)
            app.router.add_post('/v1/responses',adapter._handle_responses)
            app.router.add_get('/v1/responses/{response_id}',adapter._handle_get_response)
            async def run(**kwargs):return result,{}
            with patch.object(adapter,'_run_agent',side_effect=run):
                async with TestClient(TestServer(app)) as client:
                    response=await client.get('/api/sessions/'+a.session_id+'/messages')
                    assert response.status==200,await response.text()
                    assert private not in await response.text()
                    response=await client.post('/v1/chat/completions',json=dict(model='test',messages=[dict(role='user',content='q')]))
                    assert response.status==200,await response.text()
                    assert private not in await response.text()
                    response=await client.post('/v1/responses',json=dict(model='test',input='q',store=True))
                    assert response.status==200,await response.text()
                    data=await response.json();assert private not in json.dumps(data)
                    response=await client.get('/v1/responses/'+data['id']);assert response.status==200
                    assert private not in await response.text()
                    store=adapter._current_response_store();stored=store.get(data['id'])
                    stored['response']['output'].insert(0,dict(type='reasoning',summary=[dict(type='summary_text',text=private)]))
                    store.put(data['id'],stored)
                    response=await client.get('/v1/responses/'+data['id']);assert response.status==200
                    assert private not in await response.text()
                    assert private in json.dumps(store.get(data['id']))
            assert all(row[k]==v for k,v in original.items())
            assert db.get_messages_as_conversation(a.session_id)[-1]['reasoning']==private
    finally:
        db.close()


def test_unmanaged_native_diagnostics_preserved(env,monkeypatch):
    from gateway.platforms.api_server import APIServerAdapter
    from gateway.platforms.api_server_openai_routes import _turn_reasoning_text
    monkeypatch.setattr(scope,'ordinary_presentation',lambda *args:False)
    row=dict(role='assistant',content='Answer',reasoning='Native operator diagnostic')
    assert APIServerAdapter._message_response(row)['reasoning']==row['reasoning']
    assert _turn_reasoning_text([], 'q',dict(messages=[dict(role='user',content='q'),row]))==row['reasoning']

@pytest.mark.parametrize('codex',[False,True])
def test_real_public_admin_and_tui_history_projection_preserves_private_db(env,codex):
    from hermes_cli.web_routers.sessions import _project_for_display
    from agent.history_commentary import project_history_commentary
    with entered(env):
        private='Private history '+str(home(env))
        row=dict(role='assistant',content='Safe answer',reasoning=private,reasoning_content=private,api_content='Safe answer')
        if codex:
            row['codex_message_items']=[dict(type='message',role='assistant',phase='commentary',content=[dict(type='output_text',text='Safe commentary')])]
        original=copy.deepcopy(row)
        for view in (project_history_commentary([row],home=home(env)),_project_for_display([row],home=home(env)),_history_to_messages([row],profile_home=home(env))):
            assert private not in json.dumps(view)
            assert 'Safe answer' in json.dumps(view)
        assert row==original


@pytest.mark.asyncio
async def test_real_public_admin_export_does_not_emit_reasoning(env):
    from hermes_cli.web_routers import sessions
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db);private='Private export '+str(home(env))
            assert a._flush_messages_to_session_db([dict(role='assistant',content='Safe answer',reasoning=private)])
            # The exact endpoint, native streaming encoder and real DB pagination
            # run; only the admin database locator is bound to this private fixture.
            class Borrowed:
                def get_messages(self,*args,**kwargs):return db.get_messages(*args,**kwargs)
                def close(self):pass
            def withdb(profile,fn,**kwargs):return fn(db)
            with patch.object(sessions,'_with_db',side_effect=withdb),patch.object(sessions,'_open_session_db_for_profile',return_value=Borrowed()):
                response=await sessions.export_session_endpoint(a.session_id)
                parts=[]
                async for part in response.body_iterator:parts.append(part.decode() if isinstance(part,bytes) else part)
                exported=''.join(parts)
            assert private not in exported and 'Safe answer' in exported
            assert db.get_messages_as_conversation(a.session_id)[-1]['reasoning']==private
    finally:
        db.close()


def test_real_normalizer_keeps_reasoning_for_tools_and_strips_inline_public_text(env):
    from agent.chat_completion_helpers import build_assistant_message
    from agent.agent_runtime_helpers import strip_think_blocks
    db=own_db(env)
    try:
        with entered(env):
            a=actor(db);a.verbose_logging=False;a.reasoning_callback=lambda *a:pytest.fail('private callback');a.stream_delta_callback=a._stream_callback=None
            private='Need own workspace '+str(home(env)/'workspace')
            a._extract_reasoning=lambda msg:None;a._strip_think_blocks=lambda text:strip_think_blocks(None,text)
            row=build_assistant_message(a,NS(content='<think>'+private+'</think>Safe answer',tool_calls=None),'stop')
            assert row['content']=='Safe answer' and row['reasoning']==row['reasoning_content']==private
            assert a._flush_messages_to_session_db([row])
            assert not getattr(a,'_friday_reply_withheld',False)
            assert db.get_messages_as_conversation(a.session_id)[-1]['reasoning_content']==private
    finally:
        db.close()
