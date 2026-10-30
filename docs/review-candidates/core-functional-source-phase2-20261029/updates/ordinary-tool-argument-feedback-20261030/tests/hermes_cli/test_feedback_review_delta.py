"""Independent finite checks for Source104+argument-feedback composition."""
import contextvars
import json
from types import SimpleNamespace
import pytest
from test_friday_tool_argument_feedback import admitted, invoke, document, write
from hermes_cli import friday_user_scope as scope

@pytest.mark.parametrize('arguments', [
    {'name':'write_file','arguments':'{'},
    {'calls':json.dumps({'name':'write_file','arguments':'['})},
    {'calls':[{'name':'write_file','arguments':{}}, {'name':'read_file','arguments':'{"PRIVATE_SENTINEL":'}]},
    {'calls':[{'name':'write_file','arguments':{}}, False]},
    {'calls':'[{"name":"write_file","arguments":{}},]'},
])
def test_no_prefix_dispatch_or_repair_for_other_supported_envelopes(admitted, monkeypatch, arguments):
    import model_tools
    monkeypatch.setattr(model_tools,'_dispatch_bridge_tool',lambda *a:pytest.fail('malformed call dispatched'))
    payload=invoke('tool_call',arguments)
    assert payload['error_type']=='invalid_arguments' and payload['success'] is False
    assert 'PRIVATE_SENTINEL' not in json.dumps(payload)
    assert set(payload)=={'error','success','error_type','argument','hint'}
    assert list((admitted.home/'workspace').iterdir())==[]

@pytest.mark.parametrize('fault',['cancelled','expired','tool_subset'])
def test_current_delegation_limits_precede_malformed_feedback(admitted,monkeypatch,fault):
    parent=SimpleNamespace()
    scope.capture_agent(parent)
    pin=dict(parent=parent,authority=scope.delegation_authority(),deadline=None,cancelled=False,
             tools={'write_file','read_file'})
    if fault=='cancelled':pin['cancelled']=True
    elif fault=='expired':pin['deadline']=0
    else:pin['tools']={'read_file'}
    monkeypatch.setattr(scope,'_DELEGATION',contextvars.ContextVar('review-delegation',default=pin))
    payload=invoke('tool_call',{'calls':[{'name':'write_file','arguments':'{'}]})
    assert payload['error']==scope.PUBLIC_TOOL_REFUSAL_COPY and 'hint' not in payload
    assert list((admitted.home/'workspace').iterdir())==[]

@pytest.mark.parametrize('fault',['foreign_path','dot_path','suffix','foreign_parent'])
def test_source104_path_denials_precede_structured_feedback(admitted,fault):
    path={'foreign_path':str(admitted.root/'secret.docx'),'dot_path':'../secret.docx',
          'suffix':'secret.txt','foreign_parent':'missing/report.docx'}[fault]
    payload=write(document('{"blocks":[',path))
    assert payload['error']==scope.PUBLIC_TOOL_REFUSAL_COPY and 'hint' not in payload
    assert list((admitted.home/'workspace').iterdir())==[]


def test_sequential_real_docx_dispatch_preserves_feedback(admitted):
    from agent import tool_executor as executor
    agent=SimpleNamespace(_context_engine_tool_names=set(),_memory_manager=None,
        session_id='review-delta',valid_tool_names={'write_file'},enabled_toolsets=['file'],
        disabled_toolsets=None,quiet_mode=False)
    scope.capture_agent(agent)
    args=document('{"blocks":[{"type":"paragraph","text":"PRIVATE_SENTINEL"},')
    ref=executor._ToolCallRef('write_file',args,'review-delta','review-call',[])
    dispatch=executor._resolve_sequential_dispatch(agent,ref,[])
    payload=json.loads(dispatch.execute(args))
    assert payload['error_type']=='invalid_arguments' and payload['argument']=='content'
    assert 'PRIVATE_SENTINEL' not in json.dumps(payload)
    assert list((admitted.home/'workspace').iterdir())==[]


def test_actual_concurrent_batch_excludes_parse_failure_without_relabeling(admitted,monkeypatch):
    from agent import tool_executor as executor
    from agent.transports.types import ToolCall
    from agent.tool_call_batches import expand_local_tool_batches
    agent=SimpleNamespace()
    scope.capture_agent(agent)
    call=ToolCall(id='review-call',name='tool_call',arguments=json.dumps({'calls':'['}))
    original=call.arguments
    expanded=expand_local_tool_batches([call])
    assert expanded==[call] and call.arguments==original
    parsed=executor._parse_tool_call(agent,call)
    assert parsed.parse_error is not None
    batch=executor._ConcurrentBatch(agent,[],'review-delta',[parsed],None)
    monkeypatch.setattr(batch,'submit_all',lambda *a:pytest.fail('parse failure submitted'))
    batch.run()
    slot=batch.results[0]
    assert slot.is_error is True and slot.blocked is True and slot.duration==0
    assert json.loads(slot.result)['error_type']=='invalid_arguments'
    # Existing commit maps blocked=True to unknown. Guidance must not upgrade it.
    assert batch.timed_out_indices==set()

@pytest.mark.parametrize('raw',['{"calls":[PRIVATE_SENTINEL','null','[{}]'])
def test_outer_parser_does_not_repair_or_echo(admitted,raw):
    from agent import tool_executor as executor
    from agent.transports.types import ToolCall
    agent=SimpleNamespace()
    scope.capture_agent(agent)
    parsed=executor._parse_tool_call(agent,ToolCall(id='review-call',name='tool_call',arguments=raw))
    assert parsed.parse_error is not None and parsed.args=={}
    payload=json.loads(parsed.parse_error)
    assert payload['error']=='Invalid tool arguments'
    assert 'PRIVATE_SENTINEL' not in parsed.parse_error
    assert list((admitted.home/'workspace').iterdir())==[]
