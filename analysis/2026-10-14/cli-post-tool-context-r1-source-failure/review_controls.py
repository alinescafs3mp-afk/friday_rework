import copy, json, os, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fixture_setup import *
from agent.bounded_context import bounded_preflight_tool_progress, BoundedContextError

results = []
original = copy.deepcopy(rows)

def probe(name, before, after, expected):
    a = SimpleNamespace(_bounded_context_policy=policy, _current_turn_timestamp=123)
    assert bounded_preflight_tool_progress(a, copy.deepcopy(before)) is False
    observed = bounded_preflight_tool_progress(a, copy.deepcopy(after))
    results.append({'case':name, 'expected':expected, 'observed':observed,
                    'matches_required_contract': observed == expected})

probe('genuine_complete_new_group', rows[:5], rows, True)
probe('unchanged_rebuild', rows, rows, False)
probe('stale_terminal_group_prefix_insertion', rows,
      [dict(role='user', content='request-only scaffolding'), *rows], False)
probe('duplicate_stale_complete_group_appended', rows, [*rows, *copy.deepcopy(rows[-2:])], False)
pending = {'role':'assistant','content':'','tool_calls':[{'id':'unfinished','type':'function',
           'function':{'name':'read_file','arguments':'{}'}}]}
probe('incomplete_group_then_complete_group', rows[:5],
      [*rows[:5], pending, *copy.deepcopy(rows[-2:])], False)
foreign = {'role':'tool','tool_call_id':'foreign','content':'foreign unpaired result'}
probe('foreign_unpaired_result_then_complete_group', rows[:5],
      [*rows[:5], foreign, *copy.deepcopy(rows[-2:])], False)

def fresh():
    c = ContextCompressor('dispatcher', config_context_length=40960, provider='custom',
        base_url=policy.base_url, api_mode='chat_completions', max_tokens=4096, quiet_mode=True)
    c.bounded_context_policy=policy; c.abort_on_summary_failure=True
    return c

for name, response in [
    ('empty_summary', {'choices':[{'message':{'content':''},'finish_reason':'stop'}]}),
    ('malformed_summary', {'choices':[]}),
    ('truncated_summary', {'choices':[{'message':{'content':'Partial summary'},'finish_reason':'length'}]}),
    ('oversized_summary', {'choices':[{'message':{'content':'oversized '*10000},'finish_reason':'stop'}]})]:
    c=fresh(); agent.context_compressor=c
    with patch('agent.context_compressor.call_llm',return_value=response) as call:
        compressed=c.compress(copy.deepcopy(rows),current_tokens=38294)
    unchanged = compressed == rows
    try: guard_main_request(agent,wire(compressed))
    except BoundedContextError as e: rejected=True; reason=str(e)
    else: rejected=False; reason=''
    assert rejected, name
    if name != 'oversized_summary': assert unchanged, name
    results.append({'case':name,'backend_only_mock':True,'summary_calls':call.call_count,
                    'original_rows_preserved':unchanged,'final_physical_guard_refused':rejected,
                    'no_fit':True,'reason':reason})

assert rows == original
report={'state':'INDEPENDENT_SOURCE_CONTROLS','results':results,
        'latch_contract_failures':sum(x.get('matches_required_contract') is False for x in results),
        'native_formatter_and_physical_guard':True,'external_summary_backend_mocked':True,
        'runtime_reachability_of_latch_counterexamples_demonstrated':False,
        'all_Go':False,'own_processes_running':False}
with (O/'REVIEW-CONTROLS.json').open('w') as f:
    json.dump(report,f,indent=2); f.write('\n'); f.flush();os.fsync(f.fileno())
print(json.dumps({'cases':len(results),'latch_contract_failures':report['latch_contract_failures']}))
