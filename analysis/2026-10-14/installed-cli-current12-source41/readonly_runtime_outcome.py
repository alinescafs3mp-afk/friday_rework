"""Qualify persisted rows after a new read-only run; no process/model effects."""
import json, math

def strict_json(value):
    def unique(pairs):
        out={}
        for key,item in pairs:
            if key in out:raise ValueError('duplicate JSON key')
            out[key]=item
        return out
    def finite(raw):
        result=float(raw)
        if not math.isfinite(result):raise ValueError('nonfinite JSON value')
        return result
    def constant(raw):raise ValueError('nonfinite JSON value')
    return json.loads(value,object_pairs_hook=unique,parse_float=finite,parse_constant=constant)

def classify_new_readonly_rows(row,messages,binding):
    prior=set(binding['baseline_message_ids'])
    appended=[m for m in messages if m['id'] not in prior]
    # SQL compaction retains archived rows and appends active clones.
    # Qualify the active continuation, while rejecting malformed lifecycle flags.
    lifecycle_ok=all(type(m.get(key,default)) is int and m.get(key,default) in (0,1)
        for m in appended for key,default in (('active',1),('_compressed_summary',0)))
    active=[m for m in appended if type(m.get('active',1)) is int and m.get('active',1)==1]
    calls={}; valid_calls=lifecycle_ok; tool_rows=[]
    for message in active:
        if message['role']=='assistant':
            try:
                declared=message.get('tool_calls')
                declared=[] if declared is None else strict_json(declared) if isinstance(declared,str) else declared
                if type(declared) is not list:raise ValueError('tool call list required')
                for call in declared:
                    function=call['function'];args=strict_json(function['arguments'])
                    ident=call['id']
                    if (call.get('type')!='function' or type(ident) is not str or not ident or ident in calls
                        or function['name']!='read_file' or type(args) is not dict
                        or set(args)-{'path','offset','limit'} or args.get('path')!=binding['output']
                        or ('offset' in args and (type(args['offset']) is not int or not 1<=args['offset']<=1000000))
                        or ('limit' in args and (type(args['limit']) is not int or not 1<=args['limit']<=2000))):
                        raise ValueError('illegal read-only call')
                    calls[ident]=args
            except (ValueError,TypeError,KeyError):valid_calls=False
        elif message['role']=='tool':tool_rows.append(message)
    read_ok=False;linked=True;returned=set()
    for message in tool_rows:
        try:
            data=strict_json(message['content'])
            ident=message.get('tool_call_id')
            if message.get('tool_name')!='read_file' or ident not in calls or ident in returned:
                raise ValueError('unlinked or foreign tool response')
            returned.add(ident)
            if (type(data) is dict and data.get('success') is True and data.get('readonly') is True
                and data.get('path')==binding['output'] and type(data.get('content')) is str
                and data['content'].strip()):read_ok=True
        except (ValueError,TypeError,KeyError):linked=False
    linked=linked and returned==set(calls)
    final=active[-1] if active else {}
    try:
        final_calls=final.get('tool_calls')
        final_calls=[] if final_calls is None else strict_json(final_calls) if isinstance(final_calls,str) else final_calls
        metadata=final.get('display_metadata')
        metadata=strict_json(metadata) if isinstance(metadata,str) else metadata
        final_answer=(final.get('role')=='assistant' and type(final.get('content')) is str
            and not final.get('_compressed_summary',0)
            and bool(final['content'].strip()) and final.get('display_kind') not in ('failed_turn','partial_turn')
            and final.get('finish_reason') not in ('error','length','tool_calls','cancelled')
            and type(final_calls) is list and not final_calls
            and (metadata is None or type(metadata) is dict and not metadata.get('error')))
    except (ValueError,TypeError):final_answer=False
    return {'new_exact_question':any(m['role']=='user' and m['content']==binding['question'] for m in active),
        'read_file_success':read_ok,'only_read_file_calls':valid_calls,
        'tool_calls_linked':linked,'only_read_file_tools':all(m.get('tool_name')=='read_file' for m in tool_rows),
        'new_final_answer':final_answer,
        'persisted_cli_close':row.get('end_reason')=='cli_close' and row.get('ended_at') is not None}
