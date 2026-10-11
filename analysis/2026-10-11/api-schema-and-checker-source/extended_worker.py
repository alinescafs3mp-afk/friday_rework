import sys
assert sys.stdin.readline() == 'execute\n'
import ast,pathlib,json,asyncio,copy,os,resource,threading,traceback,time,hashlib,urllib.parse
OUT=pathlib.Path(__file__).resolve().parent
src=(OUT/'framework_worker.py').read_text();tree=ast.parse(src)
stop=next(n.lineno for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='run')
selected=[]
for n in tree.body:
 if n.lineno>=stop:break
 if isinstance(n,(ast.Assert,ast.For,ast.If)):continue
 if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='schema_case':continue
 if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='policy_ready' for t in n.targets):continue
 selected.append(n)
ns={'__file__':str(__file__),'__name__':'independent_extended'}
exec(compile(ast.Module(selected,type_ignores=[]),str(OUT/'framework_worker.py'),'exec'),ns)
api=ns['api'];native=ns['native'];app=ns['app'];calls=ns['calls'];C=ns['C'];session=ns['session'];policy=ns['policy']
MARKER='INERT_REVIEW_API_SECRET_20261011'
rows=[]
def add(name,ok,**kw):rows.append({'name':name,'status':'PASS' if ok else 'FAIL',**kw})
async def raw(name,method,path,body=b'',query=None,s=session,gate=False,expected=422,expected_calls=0,expect_static=True):
 query={'profile':'main'} if query is None else query
 full='/api/plugins/friday_rework'+path
 scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':full,'raw_path':full.encode(),'root_path':'','query_string':urllib.parse.urlencode(query).encode(),'headers':[(b'content-type',b'application/json')],'client':('inert',0),'server':('inert',0),'state':{'session':s},'app':app}
 messages=[];delivered=False;before=len(calls);exception=None
 async def receive():
  nonlocal delivered
  if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
  return {'type':'http.disconnect'}
 async def send(m):messages.append(m)
 try:
  if gate and not native.request_allowed(ns['Request'](scope)):
   messages.extend([{'type':'http.response.start','status':403},{'type':'http.response.body','body':b'{"detail":"native_request_policy_refused"}'}])
  else:await app(scope,receive,send)
 except Exception as e:exception=type(e).__name__
 status=next((m['status'] for m in messages if m['type']=='http.response.start'),None)
 text=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body').decode(errors='replace')
 ok=status==expected and len(calls)-before==expected_calls and MARKER not in text and exception is None
 if expect_static:ok=ok and text=='{"detail":"invalid_product_request"}'
 add(name,ok,status_code=status,backend_calls=len(calls)-before,response=text,marker_reflected=MARKER in text,exception=exception)
 return rows[-1]
def b(data):return json.dumps(data).encode()
async def run():
 original_routes=[{'method':sorted(r.methods),'path':r.path,'class':type(r).__name__} for r in api.router.routes]
 add('all_25_product_routes_use_custom_APIRoute',len(original_routes)==25 and all(isinstance(r,api.ProductAPIRoute) for r in api.router.routes),routes=original_routes,root_app_route_classes=[type(r).__name__ for r in app.routes])
 for name,value in [('dict',{'nested':MARKER}),('list',[MARKER]),('null',None),('bool',True),('int',123),('float',1.5)]:
  await raw('credential_secret_type_'+name,'PUT','/onboarding/credentials',b(C|{'value':value}))
 await raw('attacker_field_key','PUT','/onboarding/credentials',b(C|{MARKER:MARKER}))
 await raw('missing_credential_field_with_marker_body','PUT','/onboarding/credentials',b({k:v for k,v in (C|{'value':MARKER}).items() if k!='name'}))
 await raw('invalid_JSON_marker','PUT','/onboarding/credentials',b'{"value":"'+MARKER.encode()+b'", broken:}')
 await raw('missing_body','PUT','/onboarding/credentials')
 await raw('query_marker_integer_type','GET','/conversations',query={'profile':'main','limit':MARKER})
 await raw('query_marker_length','GET','/conversations',query={'profile':'main','query':MARKER*30})
 await raw('path_marker_integer_type','GET','/attachments/task/'+MARKER)
 await raw('missing_required_query_with_credential_marker','PUT','/onboarding/credentials',b(C|{'value':MARKER}),query={})
 row=await raw('valid_credential_forwarded_once','PUT','/onboarding/credentials',b(C),expected=200,expected_calls=1,expect_static=False)
 row['forwarded_exactly_once']=len(calls)>=1 and calls[-1]['method']=='onboarding_credentials' and calls[-1]['kwargs']['value']=={'secret_forwarded_exactly':True}
 if not row['forwarded_exactly_once']:row['status']='FAIL'
 for label,s in [('anonymous',None),('foreign',ns['other']),('expired',ns['expired'])]:
  await raw('exact_router_'+label+'_valid_refuses_beforebackend','PUT','/onboarding/credentials',b(C),s=s,expected=403,expect_static=False)
  await raw('exact_router_'+label+'_invalid_refuses_beforebackend','PUT','/onboarding/credentials',b(C|{'value':{'nested':MARKER}}),s=s,expected=403,expect_static=False)
  await raw('wrapped_'+label+'_invalid_refuses_beforebackend','PUT','/onboarding/credentials',b(C|{'value':{'nested':MARKER}}),s=s,gate=True,expected=403,expect_static=False)
 # JSON decoding occurs before dependency solving in FastAPI; this does not assert an authentication grant.
 await raw('anonymous_invalid_JSON_static422_before_dependency_parse','PUT','/onboarding/credentials',b'{"value":"'+MARKER.encode()+b'", broken:}',s=None)
 saved=copy.deepcopy(policy);policy['admin']['operators']=[]
 await raw('revoked_exact_router_credential_beforebackend','PUT','/onboarding/credentials',b(C),expected=403,expect_static=False)
 policy.clear();policy.update(saved)
 await raw('foreign_profile_wrapped_beforebackend','PUT','/onboarding/credentials',b(C),query={'profile':'foreign'},gate=True,expected=403,expect_static=False)
 from fastapi import APIRouter
 from fastapi.exceptions import ResponseValidationError,RequestValidationError
 plain=APIRouter()
 @plain.get('/plain-review')
 def plain_review(limit:int):return limit
 app.include_router(plain,prefix='/api/plugins/friday_rework')
 row=await raw('plain_router_validation_not_globally_changed','GET','/plain-review',query={'limit':MARKER},expect_static=False)
 # This unrelated router intentionally still uses the framework default validation details.
 row['status']='PASS' if row['status_code']==422 and row['backend_calls']==0 and row['marker_reflected'] and row['exception'] is None else 'FAIL'
 scoped=APIRouter(route_class=api.ProductAPIRoute)
 @scoped.get('/response-review',response_model=int)
 def response_review():return {'invalid':MARKER}
 app.include_router(scoped,prefix='/api/plugins/friday_rework')
 row=await raw('ResponseValidationError_not_caught_as_request_error','GET','/response-review',expected=500,expect_static=False)
 row['status']='PASS' if row['status_code']==500 and row['exception']=='ResponseValidationError' and row['backend_calls']==0 and not row['marker_reflected'] else 'FAIL'
 add('request_response_exception_types_are_distinct',not issubclass(ResponseValidationError,RequestValidationError))
try:asyncio.run(run())
except Exception as e:rows.append({'name':'fatal','status':'FAIL','exception':type(e).__name__,'traceback':traceback.format_exc()})
result={'claim':'independent extended current-tooling source controls; production API full-module import; same explicit harness policy/session/backend/request-wrapper seams',
        'cases':rows,'failures':[r['name'] for r in rows if r['status']!='PASS'],'audit_denials':ns['events'],
        'resources':{'affinity':list(os.sched_getaffinity(0)),'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'threads':[t.name for t in threading.enumerate()],'children':pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split(),'whole_peak':'UNKNOWN'},
        'setup_source_sha256':hashlib.sha256(src.encode()).hexdigest(),'production_api_full_module':True}
(OUT/'EXTENDED-OBSERVATIONS.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'cases':len(rows),'failures':result['failures'],'audit_denials':result['audit_denials'],'resources':result['resources']}))
if result['failures'] or result['audit_denials'] or result['resources']['children']:sys.exit(1)
