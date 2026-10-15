"""Bounded web evidence and scoped file cursors; isolated source fixtures only."""
import asyncio,copy,json,pathlib
from contextlib import contextmanager,ExitStack
from unittest.mock import patch,AsyncMock
from hermes_cli import config as hc,friday_user_scope as us,friday_product_access as pa
from agent import bounded_context as bc
from agent.bounded_context import bounded_tool_result_budget,serialized_bytes
from tools import web_tools as wt,web_tools_truncate as tr,file_tools as ft
import model_tools


def test_bounded_web_originals_cursors_bridge_and_isolation(tmp_path,monkeypatch):
    W=ROOT=tmp_path
    cfg={'bounded_fixture':True,'web':{'extract_char_limit':20000},'tools':{'tool_search':{'defer':['web_search','web_extract']}}}
    # Policy validation is covered separately. This fixture prices the real
    # producer and descriptor I/O in the unchanged 40960/4096/1024 budget.
    policy=bc.BoundedContextPolicy('custom:fixture','fixture','http://127.0.0.1:1/v1',40960,40960,4096,4096,1024,2048)
    monkeypatch.setattr(bc,'configured_policy',lambda:policy if cfg.get('bounded_fixture') else None)
    monkeypatch.setattr(hc,'load_config_readonly',lambda *a,**k:copy.deepcopy(cfg))
    monkeypatch.setattr(hc,'load_config',lambda *a,**k:copy.deepcopy(cfg))
    monkeypatch.setattr(pa,'settings',pa.settings)
    monkeypatch.setattr(pa,'current_access',pa.current_access)
    def blocked(*a,**k):raise AssertionError('effects refused in source fixture')
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
    def produce(results, char_limit=None):
     urls=[r['url'] for r in results]
     with ExitStack() as p:
      p.enter_context(patch.object(wt,'async_is_safe_url',AsyncMock(return_value=True)))
      p.enter_context(patch.object(wt,'_extract_safe_urls',AsyncMock(return_value=copy.deepcopy(results))))
      p.enter_context(patch.object(wt,'_get_extract_backend',lambda:'OWN'))
      p.enter_context(patch.object(wt,'_ensure_web_plugins_loaded',lambda:None))
      p.enter_context(patch.object(wt,'_resolve_extract_provider',lambda _:(object(),None)))
      p.enter_context(patch.object(wt,'_load_web_config',lambda:cfg['web']))
      p.enter_context(patch.object(wt,'_finish_debug',lambda *a,**k:None))
      return asyncio.run(wt.web_extract_tool(urls,char_limit=char_limit))
    budget=bounded_tool_result_budget();assert budget==2112
    with active(a):
     for name,text,count in [('ascii','a'*30000,1),('unicode','🦊я'*30000,1),('escape','"\\\n\t'*10000,5),('override','x'*500000,1)]:
      original=[{'url':'https://example.test/'+str(i),'title':'Finite public source','raw_content':text} for i in range(count)]
      out=produce(original,500000 if name=='override' else None);body=json.loads(out)
      assert serialized_bytes(out)<=budget,(name,serialized_bytes(out))
      for row in body['results']:
       assert row['partial'] is True and row['stored_copy']=='complete'
       path=pathlib.Path(row['read_file']['path']);assert path.read_text()==text
       assert path.stat().st_mode&0o777==0o600 and path.parent==a.home/'workspace'
      checks[name+'_aggregate_embed_bound_private_complete']=True;measurements[name]=serialized_bytes(out)
      (W/('scoped-'+name+'.json')).write_text(out)
     # Content-only providers must retain the original, before native truncation.
     text='content-only-original '+('я'*30000)
     out=produce([{'url':'https://example.test/content-only','content':text}],2000)
     row=json.loads(out)['results'][0]
     assert row['stored_copy']=='complete' and pathlib.Path(row['read_file']['path']).read_text()==text
     checks['content_only_provider_preserves_pre_truncation_original']=True
     out=produce([{'url':'https://example.test/policy','content':'','error':'policy refusal '+('e'*5000),'blocked_by_policy':True}])
     body=json.loads(out);manifest=json.loads(pathlib.Path(body['read_file']['path']).read_text())
     assert manifest['results'][0]['blocked_by_policy'] is True
     checks['policy_refusal_metadata_preserved_in_manifest']=True
     # Metadata alone overflows: an exact manifest retains all five page paths.
     out=produce([{'url':'https://example.test/'+str(i),'title':'я'*5000,'raw_content':'OWN FACT '+str(i)} for i in range(5)])
     body=json.loads(out);assert body['partial'] and body['error'].startswith('capacity:') and serialized_bytes(out)<=budget
     manifest=json.loads(pathlib.Path(body['read_file']['path']).read_text())
     assert len(manifest['results'])==5
     for i,row in enumerate(manifest['results']):assert pathlib.Path(row['read_file']['path']).read_text()=='OWN FACT '+str(i)
     checks['oversized_metadata_manifest_retains_all_page_paths']=True
     # A long line must make cursor progress and reconstruct without dropped chars.
     text='🦊я"\\\t'*1200
     p=a.home/'workspace/long-line.md';p.write_text(text);p.chmod(0o600)
     cursor={'offset':1,'char_offset':0};parts=[];pages=[]
     for _ in range(100):
      args={'path':str(p),'limit':200,**cursor}
      raw=ft._handle_read_file(args);row=json.loads(raw);assert row['success'] and serialized_bytes(raw)<=budget
      parts.append(row['content'].split(': ',1)[1]);pages.append(raw)
      if not row['partial']:break
      nxt={'offset':row['next_offset'],'char_offset':row['next_char_offset']};assert nxt!=cursor;cursor=nxt
     else:raise AssertionError('finite cursor did not reach EOF')
     assert ''.join(parts)==text and p.read_text()==text
     checks['long_line_unicode_escape_cursor_exact_reconstruction']=True;measurements['read_pages']=len(pages)
     (W/'scoped-read-page.json').write_text(pages[0])
     (W/'scoped-read-pages.json').write_text(json.dumps(pages,ensure_ascii=False))
     # Bridge validates the added cursor schema and returns the same underlying args.
     defs=[{'type':'function','function':ft.READ_FILE_SCHEMA}]
     with patch.object(model_tools,'get_tool_definitions',lambda **k:defs):
      bridge=model_tools._dispatch_bridge_tool('tool_call',{'name':'read_file','arguments':args},['file'],[])
      assert bridge[1] is None and 'directly-listed' in bridge[0],bridge
      assert not json.loads(ft._handle_read_file(dict(args,char_offset=-1)))['success']
     checks['read_stays_direct_bridge_refused_bad_cursor_refused']=True
     defs=[{'type':'function','function':wt.WEB_EXTRACT_SCHEMA}]
     with patch.object(model_tools,'get_tool_definitions',lambda **k:defs):
      webargs={'urls':['https://example.test/bridge']}
      bridge=model_tools._dispatch_bridge_tool('tool_call',{'name':'web_extract','arguments':webargs},['web'],[])
      assert bridge==(None,('web_extract',webargs)),bridge
      bad=model_tools._dispatch_bridge_tool('tool_call',{'name':'web_extract','arguments':{'urls':webargs['urls']*6}},['web'],[])
      assert bad[1] is None
     checks['deferred_web_bridge_preserves_args_and_enforces_five_urls']=True
     # Scope, ownership and symlink protections are preserved.
     foreign=b.home/'workspace/foreign';foreign.write_text('foreign');foreign.chmod(0o600)
     assert not json.loads(ft._handle_read_file({'path':str(foreign)}))['success']
     link=a.home/'workspace/link';link.symlink_to(foreign)
     assert not json.loads(ft._handle_read_file({'path':str(link)}))['success'];link.unlink()
     access['users'][a.key]['enabled']=False
     assert not json.loads(ft._handle_read_file({'path':str(p)}))['success']
     access['users'][a.key]['enabled']=True;a.revoked=False
     checks['foreign_symlink_revocation_refused']=True
     # Storage failure is explicit; no fake complete source or silent loss claim.
     with patch.object(tr,'_store_full_text',lambda *a:None):
      row=json.loads(produce([{'url':'https://example.test/fail','raw_content':'z'*30000}]))['results'][0]
      assert row['partial'] and row['stored_copy']=='unavailable' and row['read_file'] is None
     checks['storage_failure_explicit_partial']=True
     huge='я'*600000
     out=produce([{'url':'https://example.test/huge','raw_content':huge}]);row=json.loads(out)['results'][0]
     assert row['stored_copy']=='partial';data=pathlib.Path(row['read_file']['path']).read_bytes()
     assert len(data)<=1000000 and 'stored copy truncated' in data.decode()
     checks['one_mb_storage_ceiling_explicit_partial']=True
     # Runtime enforcement also covers callers bypassing the JSON schema.
     with patch.object(wt,'_extract_safe_urls',blocked):
      out=asyncio.run(wt.web_extract_tool(['https://example.test/'+str(i) for i in range(6)]))
      assert 'one to five' in out
     checks['six_urls_refused_before_fetch']=True
     # Non-bounded profiles preserve existing line behavior and per-page response.
     old_cfg=copy.deepcopy(cfg);cfg.clear();cfg.update({'web':{'extract_char_limit':20000}})
     raw=ft._handle_read_file({'path':str(p),'offset':1,'limit':1});assert 'next_char_offset' not in json.loads(raw)
     cfg.clear();cfg.update(old_cfg)
     checks['legacy_unbounded_read_behavior_preserved']=True
    assert len(checks)==15 and all(checks.values())
