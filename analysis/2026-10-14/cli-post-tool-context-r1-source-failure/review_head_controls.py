import copy, importlib.util, json, os, sys
from unittest.mock import patch
from fixture_setup import *

before_path=os.environ['FRIDAY_SOURCE37_COMPRESSOR']
spec=importlib.util.spec_from_file_location('before_head',before_path)
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)

def fresh(cls):
    c=cls('dispatcher',config_context_length=40960,provider='custom',base_url=policy.base_url,
          api_mode='chat_completions',max_tokens=4096,quiet_mode=True)
    c.bounded_context_policy=policy;c.abort_on_summary_failure=True
    return c

cases=[]
for n in [0,1,2,3]:
    x=[{'role':'system','content':'Essential authority '+str(i)} for i in range(n)]+copy.deepcopy(rows)
    newc=fresh(ContextCompressor);oldc=fresh(old.ContextCompressor)
    start,end=newc._compress_window(x);ostart,oend=oldc._compress_window(x)
    new_head=newc._protect_head_size(x);old_head=oldc._protect_head_size(x)
    with patch.object(newc,'_call_summary_llm',return_value='Only previously completed facts.'):
        after=newc.compress(copy.deepcopy(x),current_tokens=38294)
    cases.append({'leading_system_rows':n,'new_window':[start,end],'old_window':[ostart,oend],
      'new_head_before_compress':new_head,'old_head_before_compress':old_head,
      'system_authorities_retained_as_system':[any(z.get('role')=='system' and
         z.get('content','').startswith(a['content']) for z in after) for a in x[:n]],
      'opening_user_preserved_verbatim':any(z.get('message_uid')==rows[0].get('message_uid') and
         z.get('role')=='user' and z.get('content')==rows[0].get('content') for z in after),
      'current_user_preserved_verbatim':any(z.get('message_uid')==rows[4].get('message_uid') and
         z.get('role')=='user' and z.get('content')==rows[4].get('content') for z in after)})

assert cases[0]['opening_user_preserved_verbatim']
assert cases[1]['system_authorities_retained_as_system']==[True]
assert not cases[2]['opening_user_preserved_verbatim']
assert cases[3]['system_authorities_retained_as_system']==[True,True,False]
report={'cases':cases,'summary_model_mocked':True,'runtime_reachability':False,
        'old37_head_preserves_all_leading_system_and_opening_user_for_reproducer':True,
        'new38_head_violation':True}
with (O/'HEAD-CONTROLS.json').open('w') as f:
    json.dump(report,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps({'cases':len(cases),'new38_head_violation':True}))
