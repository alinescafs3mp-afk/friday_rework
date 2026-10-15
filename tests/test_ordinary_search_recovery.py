"""Oversized native search keeps ranked evidence and bounded private recovery."""
import asyncio,copy,json,pathlib
from contextlib import contextmanager,ExitStack
from unittest.mock import patch,AsyncMock
from hermes_cli import config as hc,friday_user_scope as us,friday_product_access as pa
from agent import bounded_context as bc
from agent.bounded_context import bounded_tool_result_budget,serialized_bytes
from tools import web_tools as wt,web_tools_truncate as tr,file_tools as ft
import model_tools


def test_search_shortlist_original_cursor_capacity_and_isolation(tmp_path,monkeypatch):
    W=ROOT=tmp_path
    cfg={'bounded_fixture':True,'web':{'extract_char_limit':20000,'keyless_rescue':False},'tools':{'tool_search':{'defer':['web_search','web_extract']}}}
    # This producer/I/O fixture uses the existing policy. Config validation
    # and actual tokenizer/endpoint acceptance are separate requirements.
    policy=bc.BoundedContextPolicy('custom:fixture','fixture','http://127.0.0.1:1/v1',40960,40960,4096,4096,1024,2048)
    monkeypatch.setattr(bc,'configured_policy',lambda:policy if cfg.get('bounded_fixture') else None)
    monkeypatch.setattr(hc,'load_config_readonly',lambda *a,**k:copy.deepcopy(cfg))
    monkeypatch.setattr(hc,'load_config',lambda *a,**k:copy.deepcopy(cfg))
    monkeypatch.setattr(pa,'settings',pa.settings)
    monkeypatch.setattr(pa,'current_access',pa.current_access)
    checks={};measurements={}
    def cap_for(label,uid):
     home=ROOT/label;home.mkdir(mode=0o700)
     for n in ('workspace','memories'):(home/n).mkdir(mode=0o700)
     principal=('telegram','transport','fixture-bot',uid)
     binding=dict(zip(('platform','transport_profile','account_id','user_id'),principal))|{'runtime_profile':label,'tools':['web_search','web_extract','read_file','write_file']}
     marker={'schema':'friday.user-home.v1','principal':pa.principal_id(*principal),'profile':label,'binding_sha256':us._fingerprint(binding)}
     (home/us.MARKER).write_text(json.dumps(marker));(home/us.MARKER).chmod(0o600)
     st=home.stat();return us.UserScope(ROOT,home,label,principal,binding,(st.st_dev,st.st_ino),admission_generation=1)
    a=cap_for('user_a','a');b=cap_for('user_b','b');caps=[a,b]
    settings={'user_isolation':{'enabled':True,'bindings':[c.binding for c in caps]},'product_access':{'enabled':True,'accounts':[{'platform':'telegram','transport_profile':'transport','account_id':'fixture-bot','runtime_profiles':['user_a','user_b']}]}}
    access={'schema':'product_access.v1','users':{c.key:{'platform':c.principal[0],'transport_profile':c.principal[1],'account_id':c.principal[2],'user_id':c.principal[3],'enabled':True,'role':'user','generation':1} for c in caps}}
    pa.settings=lambda:settings;pa.current_access=lambda:access
    @contextmanager
    def active(cap):
     token=us._CURRENT.set(cap)
     try:
      with us.authority(cap.home):yield
     finally:us._CURRENT.reset(token)

    from types import SimpleNamespace
    import agent.web_search_registry as sr
    checks={};measurements={}
    QUESTION='Finite public search fixture with recoverable evidence'
    def produce(payload):
     seen=[]
     provider=SimpleNamespace(name='OWN',supports_search=lambda:True,search=lambda query,limit:(seen.append((query,limit)) or copy.deepcopy(payload)))
     with ExitStack() as p:
      p.enter_context(patch.object(wt,'_ensure_web_plugins_loaded',lambda:None));p.enter_context(patch.object(wt,'_get_search_backend',lambda:'OWN'))
      p.enter_context(patch.object(sr,'get_provider',lambda _:provider));p.enter_context(patch.object(wt,'_load_web_config',lambda:dict(cfg['web'],cache_enabled=False)))
      p.enter_context(patch.object(wt,'_finish_debug',lambda *a,**k:None))
      out=wt.web_search_tool(QUESTION,limit=20)
     assert seen==[(QUESTION,20)],seen
     return out
    budget=bounded_tool_result_budget();assert budget==2112
    payload={'success':True,'provider':'OWN','citations':['https://example.test/19'],'policy':{'allowed':True},'data':{'web':[{'title':'OWN search '+str(i),'url':'https://example.test/'+str(i),'description':'я'*1000,'position':i+1} for i in range(20)]}}
    with active(a):
     small={'success':True,'data':{'web':[{'url':'https://example.test','description':'small','position':1}]}}
     assert produce(small)==json.dumps(small,indent=2,ensure_ascii=False);checks['small_format_exact']=True
     output=produce(payload);body=json.loads(output);assert body['result_count']==20 and body['partial'] and serialized_bytes(output)<=budget
     assert body['inline_result_count']==len(body['data']['web']) and 0<body['inline_result_count']<20
     for index,row in enumerate(body['data']['web']):
      source=payload['data']['web'][index]
      assert row['url']==source['url'] and row['title']==source['title'] and row['position']==index+1 and row['description']==source['description'][:96]
     checks['ordered_useful_shortlist_separate_actual20_count']=True;measurements['inline_result_count']=body['inline_result_count']
     path=pathlib.Path(body['read_file']['path']);assert json.loads(path.read_text())==payload and path.parent==a.home/'workspace' and path.stat().st_mode&0o777==0o600
     assert body['stored_copy']=='complete';checks['all20_original_metadata_private_exact']=True
     (W/'search-output.json').write_text(output);measurements['output_embedded_units']=serialized_bytes(output)
     args=body['read_file'].copy();parts={};pages=0
     while True:
      raw=ft._handle_read_file(args);page=json.loads(raw);assert page['success'] and serialized_bytes(raw)<=budget,(args,page)
      if pages==0:(W/'search-read-page.json').write_text(raw)
      for line in page['content'].split('\n'):
       number,text=line.split(': ',1);number=int(number)
       parts[number]=parts.get(number,'')+text
      pages+=1
      if not page.get('partial'):break
      args.update(offset=page['next_offset'],char_offset=page['next_char_offset'])
      assert pages<200
     assert '\n'.join(parts[n] for n in sorted(parts))==path.read_text();checks['real_read_cursor_reconstructs_complete_original']=True;measurements['read_pages']=pages
     output2=produce(payload);assert json.loads(output2)['read_file']['path']!=str(path) and path.exists();checks['repeat_unique_no_overwrite']=True
     for name,text in [('escape','"\\\n\t'*2000),('emoji','🦊'*1000)]:
      p=copy.deepcopy(payload);p['data']['web'][0]['description']=text;out=produce(p);assert serialized_bytes(out)<=budget
      saved=pathlib.Path(json.loads(out)['read_file']['path']);assert json.loads(saved.read_text())==p;checks[name+'_exact_original_and_bound']=True
     huge=copy.deepcopy(payload);huge['data']['web'][0]['description']='🦊'*260000
     out=produce(huge);row=json.loads(out);saved=pathlib.Path(row['read_file']['path']);assert row['stored_copy']=='partial' and len(saved.read_bytes())<=1000000 and 'incomplete' in row['note'];checks['one_mb_explicit_incomplete']=True
     with patch.object(tr,'_store_full_text',lambda *a:None):
      out=produce(payload);row=json.loads(out);assert row['stored_copy']=='unavailable' and row['read_file'] is None and row['partial'] and serialized_bytes(out)<=budget
     checks['storage_failure_explicit']=True
     oversized=copy.deepcopy(payload);oversized['data']['web'][0]['url']='https://example.test/'+('x'*5000)
     out=produce(oversized);row=json.loads(out);assert row['inline_result_count']==0 and row['result_count']==20 and serialized_bytes(out)<=budget
     assert json.loads(pathlib.Path(row['read_file']['path']).read_text())==oversized;checks['huge_first_metadata_explicit_zero_preview_full_recovery']=True
     fail={'success':False,'error':'policy denied '+('z'*10000),'blocked_by_policy':True,'provider':'OWN'}
     out=produce(fail);row=json.loads(out);assert row['success'] is False and row['blocked_by_policy'] is True and json.loads(pathlib.Path(row['read_file']['path']).read_text())==fail;checks['huge_provider_error_and_policy_retained']=True
     with patch('agent.bounded_context.bounded_tool_result_budget',lambda:None):
      assert produce(payload)==json.dumps(payload,indent=2,ensure_ascii=False)
     checks['unbounded_format_exact']=True
    with active(b):
     refused=json.loads(ft._handle_read_file({'path':str(path),'offset':1,'limit':200}));assert not refused.get('success');checks['cross_user_recovery_denied']=True
    assert len(checks)==13 and all(checks.values())
