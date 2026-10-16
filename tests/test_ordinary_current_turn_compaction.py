import copy,json
from types import SimpleNamespace as NS
from unittest.mock import patch
import httpx,pytest
from openai import OpenAI
from agent import bounded_context as bc,bounded_summary_output as bo,turn_context_compaction as tcc
from agent.context_compressor import ContextCompressor
from tests.agent.test_bounded_native_envelope import native_agent,history_rows
from tests.agent.test_bounded_local_context import BASE,MODEL


def test_turn_start_defers_stale_bounded_inputs(native_agent):
 a,db,soul=native_agent
 rows=[{'role':'user','content':'same','timestamp':1},{'role':'assistant','content':'old'},{'role':'user','content':'same','timestamp':2}]
 a._bounded_compaction_request_context={'incoming':{'role':'user','content':'previous turn'}}
 with patch.object(tcc,'_idle_compaction',side_effect=AssertionError('early idle')),patch.object(tcc,'_preflight_compression',side_effect=AssertionError('early preflight')):
  out=tcc.run_turn_start_compaction(a,messages=rows,system_message=None,active_system_prompt='authority',conversation_history=rows[:-1],current_turn_user_idx=2,user_message='same',effective_task_id='offline')
 assert out.messages is rows and out.current_turn_user_idx==2 and not out.compressed and not out.blocked
 assert not hasattr(a,'_bounded_compaction_request_context')
 # The existing path remains active for nonbounded runtime.
 a._bounded_context_policy=None
 with patch.object(tcc,'_idle_compaction') as idle,patch.object(tcc,'_preflight_compression') as pre:
  tcc.run_turn_start_compaction(a,messages=rows,system_message=None,active_system_prompt='authority',conversation_history=rows[:-1],current_turn_user_idx=2,user_message='same',effective_task_id='offline')
 assert idle.call_count==pre.call_count==1


def test_complete_request_anchors_exact_current_duplicate(native_agent):
 a,db,soul=native_agent;a._current_turn_timestamp=0;a._empty_content_retries=0;a._thinking_prefill_retries=0;a._cached_system_prompt='Canonical authority'
 rows=[{'role':'user','content':'same request','timestamp':1},{'role':'assistant','content':'earlier answer'},{'role':'user','content':'same request','timestamp':2,'api_content':'same request\nCurrent injected context'}]
 bc.remember_bounded_compaction_context(a,rows,2,'current retrieval','current plugin',None,'same request')
 before=copy.deepcopy(rows)
 variants=bc.bounded_compaction_request(a,rows,a._cached_system_prompt,summary_probe=True)
 assert rows==before
 for req in variants:
  assert req['messages'][-1]['content']=='same request\nCurrent injected context'
  assert req['messages'][1]['content']=='same request'
  assert req['tools']==a.tools
  a._bounded_context_policy.check_request(req)
 # Same canonical row repeated twice remains a real ambiguity and fails closed.
 duplicate=rows+[copy.deepcopy(rows[-1])]
 with pytest.raises(bc.BoundedContextError,match='ambiguous'):
  bc.bounded_compaction_request(a,duplicate,a._cached_system_prompt,summary_probe=True)
 mutated=copy.deepcopy(rows);mutated[-1]['api_content']='rewritten'
 with pytest.raises(bc.BoundedContextError,match='ambiguous'):
  bc.bounded_compaction_request(a,mutated,a._cached_system_prompt,summary_probe=True)


def test_normal_deferred_lane_native_summary_and_full_fit(native_agent,monkeypatch):
 from agent import auxiliary_client
 a,db,soul=native_agent
 # Native session_search is a normal tool lane, not the special read_file-only lane.
 original_tools=copy.deepcopy(a.tools)
 history=history_rows();a._ensure_db_session();a._flush_messages_to_session_db(history,[]);original=copy.deepcopy(history);calls=[]
 def respond(req):
  body=json.loads(req.content);calls.append(body)
  if body['messages'][0]['role']!='system':
   schema=body['response_format']['json_schema']['schema'];limit=schema['properties']['summary']['maxLength'];assert limit>20
   # Complete truthful fixture; no claim that a real model produced it.
   text=json.dumps({'summary':'Earlier turns retained the read-only test objective and recorded disposable engineering observations.'})
  else:text='The read-only test objective is retained.'
  if body.get('stream'):
   chunk={'id':'offline','choices':[{'index':0,'delta':{'role':'assistant','content':text},'finish_reason':'stop'}]}
   return httpx.Response(200,headers={'content-type':'text/event-stream'},content='data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n')
  return httpx.Response(200,json={'id':'offline','object':'chat.completion','model':MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':text},'finish_reason':'stop'}]})
 def client():return OpenAI(base_url=BASE,api_key='offline',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(respond)))
 c=client();a.client=c
 monkeypatch.setattr(a,'_create_request_openai_client',lambda **kw:client())
 monkeypatch.setattr(auxiliary_client,'resolve_provider_client',lambda *args,**kw:(c,MODEL))
 monkeypatch.setattr(auxiliary_client,'_get_cached_client',lambda *args,**kw:(c,MODEL))
 from agent import turn_context as tc
 monkeypatch.setattr(tc,'_collect_pre_llm_call_context',lambda *args,**kw:'CURRENT_PLUGIN_SENTINEL')
 monkeypatch.setattr(tc,'_memory_turn_start_and_prefetch',lambda *args,**kw:'CURRENT_RETRIEVAL_SENTINEL')
 result=a.run_conversation('What objective do earlier turns retain?',conversation_history=history)
 assert result['completed'],{k:v for k,v in result.items() if k in ['error','completed','failure_reason']}
 summaries=[b for b in calls if b['messages'][0]['role']!='system'];main=[b for b in calls if b['messages'][0]['role']=='system']
 assert len(summaries)==1 and len(main)==1
 assert summaries[0]['max_tokens']==4096
 assert summaries[0]['response_format']['type']=='json_schema'
 assert main[0]['tools']==original_tools
 assert [t['function']['name'] for t in main[0]['tools']]==['session_search']
 assert history==original
 assert soul.strip() in main[0]['messages'][0]['content']
 assert main[0]['messages'][-1]['content'].startswith('What objective do earlier turns retain?')
 assert main[0]['messages'][-1]['content'].count('CURRENT_PLUGIN_SENTINEL')==1
 assert main[0]['messages'][-1]['content'].count('CURRENT_RETRIEVAL_SENTINEL')==1
 assert bc.serialized_bytes(main[0])+2048<=a._bounded_context_policy.trigger_tokens
 a._bounded_context_policy.check_request(main[0])
 # Same cached agent begins with the prior complete request context; a new ask
 # must be bound by assembly before the next pressure-triggered summary.
 assert a._bounded_compaction_request_context['incoming']['content']=='What objective do earlier turns retain?'
 second_history=copy.deepcopy(result['messages'])+history_rows()
 second=a.run_conversation('What is the current objective now?',conversation_history=second_history)
 assert second['completed']
 assert a._bounded_compaction_request_context['incoming']['content']=='What is the current objective now?'
 summaries=[b for b in calls if b['messages'][0]['role']!='system'];main=[b for b in calls if b['messages'][0]['role']=='system']
 assert len(summaries)==len(main)==2
 for body in main:
  assert body['messages'][-1]['content'].count('CURRENT_PLUGIN_SENTINEL')==1
  assert body['messages'][-1]['content'].count('CURRENT_RETRIEVAL_SENTINEL')==1
  assert bc.serialized_bytes(body)+2048<=a._bounded_context_policy.trigger_tokens
 c.close()


@pytest.mark.parametrize('kind',['oversized','length','format','second_call','tools','duplicate_keys'])
def test_normal_lane_negative_output_controls(kind):
 c=NS(_bounded_summary_json_headroom=600,_bounded_summary_readonly_strategy=False)
 bo.allocate(c,'mandatory provenance')
 request={'model':'fixture','messages':[{'role':'user','content':'summarize'}],'response_format':bo.response_format(c)}
 response={'choices':[{'index':0,'finish_reason':'stop','message':{'content':json.dumps({'summary':'complete factual summary'})}}]}
 with bo.output_scope(c):
  if kind=='format':
   request.pop('response_format')
   with pytest.raises(bc.BoundedContextError):bo.guard_format(request,physical=True)
  elif kind=='second_call':
   bo.guard_format(request,physical=True)
   with pytest.raises(bc.BoundedContextError):bo.guard_format(request,physical=True)
  else:
   if kind=='oversized':response['choices'][0]['message']['content']=json.dumps({'summary':'x'*101})
   elif kind=='length':response['choices'][0]['finish_reason']='length'
   elif kind=='tools':response['choices'][0]['message']['tool_calls']=[{}]
   else:response['choices'][0]['message']['content']='{"summary":"a","summary":"b"}'
   with pytest.raises(bc.BoundedContextError):bo.parse_response(c,response)


def test_noncompressible_minimum_before_summary():
 policy=bc.BoundedContextPolicy('fixture','fixture','http://127.0.0.1:1',40960,40954,4096,4096,1024,2048,4096)
 a=NS(_bounded_context_policy=policy,context_compressor=NS())
 request={'model':'fixture','messages':[{'role':'system','content':''}],'max_tokens':4096}
 fill=policy.trigger_tokens-2048-bc.serialized_bytes(request)-5
 request['messages'][0]['content']='x'*fill
 from hermes_cli import friday_credential_admission as adm
 with patch.object(bc,'bounded_compaction_request',return_value=(request,)),patch.object(adm,'ordinary_readonly_request',return_value=False):
  with pytest.raises(bc.BoundedSummaryHeadroomError):bc.bounded_summary_headroom(a,[],'authority')
