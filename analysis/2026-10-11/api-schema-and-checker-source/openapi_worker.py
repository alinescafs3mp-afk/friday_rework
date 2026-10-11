"""Full product import; schema/body contract checks with explicit prior seams.

Only OUR setup harness is AST projected. Production API is imported in full.
The causal control removes only APIRouter.responses, retaining privacy code.
"""
import sys
assert sys.stdin.readline()=='execute\n'
import ast,pathlib,json,asyncio,copy,hashlib,os,resource,threading,importlib.util,importlib.metadata,traceback,urllib.parse
OUT=pathlib.Path(__file__).resolve().parent
setup=(OUT/'framework_worker.py').read_text();tree=ast.parse(setup)
stop=next(n.lineno for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='run')
selected=[]
for n in tree.body:
 if n.lineno>=stop:break
 if isinstance(n,(ast.Assert,ast.For,ast.If)):continue
 if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='schema_case':continue
 if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='policy_ready' for t in n.targets):continue
 selected.append(n)
ns={'__file__':str(__file__),'__name__':'openapi_contract'}
exec(compile(ast.Module(selected,type_ignores=[]),str(OUT/'framework_worker.py'),'exec'),ns)
api=ns['api'];app=ns['app'];calls=ns['calls'];rows=[];MARKER='INERT_OPENAPI_CONTRACT_MARKER'
PREFIX='/api/plugins/friday_rework'
def add(name,ok,**data):
 rows.append({'name':name,'status':'PASS' if ok else 'FAIL',**data})
 return rows[-1]
def deref(schema,doc):
 while '$ref' in schema:schema=doc['components']['schemas'][schema['$ref'].split('/')[-1]]
 return schema
def matches(value,schema,doc):
 """Small validator ONLY for explicitly observed schemas; unsupported keywords fail closed."""
 schema=deref(schema,doc)
 allowed={'type','properties','required','additionalProperties','title','description','const','items'}
 if set(schema)-allowed:raise AssertionError('unsupported_schema_keywords:'+repr(set(schema)-allowed))
 if 'const' in schema and value!=schema['const']:return False
 typ=schema.get('type')
 if typ=='object':
  if not isinstance(value,dict):return False
  if not set(schema.get('required',[]))<=set(value):return False
  props=schema.get('properties',{})
  if schema.get('additionalProperties') is False and set(value)-set(props):return False
  return all(matches(v,props[k],doc) for k,v in value.items() if k in props)
 if typ=='array':return isinstance(value,list) and all(matches(v,schema['items'],doc) for v in value)
 if typ=='string':return isinstance(value,str)
 if typ=='integer':return isinstance(value,int) and not isinstance(value,bool)
 if typ is None:return True
 raise AssertionError('unsupported_schema_type:'+repr(typ))
async def raw(name,method,path,body=b'',query=None,target=app,declared_doc=None,expected=422,compatible=True,exception_expected=None):
 query={'profile':'main'} if query is None else query
 scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':PREFIX+path,'raw_path':(PREFIX+path).encode(),'root_path':'','query_string':urllib.parse.urlencode(query).encode(),'headers':[(b'content-type',b'application/json')],'client':('inert',0),'server':('inert',0),'state':{'session':ns['session']},'app':target}
 messages=[];delivered=False;before=len(calls);exc=None
 async def receive():
  nonlocal delivered
  if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
  return {'type':'http.disconnect'}
 async def send(m):messages.append(m)
 try:await target(scope,receive,send)
 except Exception as e:exc=type(e).__name__
 status=next((m['status'] for m in messages if m['type']=='http.response.start'),None)
 text=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body').decode(errors='replace')
 parsed=json.loads(text) if text.startswith('{') else None
 contract=None
 if declared_doc:
  doc,pattern=declared_doc
  schema=doc['paths'][PREFIX+pattern][method.lower()]['responses']['422']['content']['application/json']['schema']
  contract=matches(parsed,schema,doc)
 ok=status==expected and len(calls)==before and exc==exception_expected and MARKER not in text
 if expected==422:ok=ok and text=='{"detail":"invalid_product_request"}' and MARKER not in text
 if contract is not None:ok=ok and contract is compatible
 return add(name,ok,method=method,path=path,status_code=status,response=text,backend_calls=len(calls)-before,exception=exc,response_contract_match=contract)
def data_for(operation):
 if 'requestBody' not in operation:return b''
 model=operation['requestBody']['content']['application/json']['schema']['$ref'].split('/')[-1]
 return json.dumps(ns['valid'][model]).encode()
def actual_path(pattern):return pattern.replace('{session_id}','session1').replace('{task_id}','task1').replace('{job_id}','job1').replace('{index}','0')
async def run():
 doc=app.openapi();(OUT/'OPENAPI.json').write_text(json.dumps(doc,sort_keys=True,indent=2)+'\n')
 routes=api.router.routes
 add('product_route_inventory_25',len(routes)==25 and all(isinstance(r,api.ProductAPIRoute) for r in routes),routes=[r.path for r in routes])
 for route in routes:
  for method in sorted(route.methods):
   operation=doc['paths'][PREFIX+route.path][method.lower()]
   decl=operation['responses']['422']['content']['application/json']['schema']
   model=deref(decl,doc)
   add('declared_exact422_'+method+'_'+route.path,model==api.ProductRequestError.model_json_schema() and matches({'detail':'invalid_product_request'},decl,doc) and not matches({'detail':[]},decl,doc) and not matches({'detail':'other'},decl,doc) and not matches({'detail':'invalid_product_request','extra':MARKER},decl,doc),schema=decl,component=model)
   path=actual_path(route.path)
   if any(p.get('required') for p in operation.get('parameters',[]) if p['in']=='query'):
    await raw('invalid_required_query_'+method+'_'+route.path,method,path,body=data_for(operation),query={},declared_doc=(doc,route.path))
   if 'requestBody' in operation:
    for kind,body in [('invalid_body',json.dumps({MARKER:MARKER}).encode()),('wrong_container',json.dumps([MARKER]).encode()),('malformed_JSON',b'{"value":"'+MARKER.encode()+b'",broken:}')]:
     await raw(kind+'_'+method+'_'+route.path,method,path,body=body,declared_doc=(doc,route.path))
   if any(p['schema'].get('type')=='integer' for p in operation.get('parameters',[]) if p['in']=='path'):
    await raw('invalid_path_'+method+'_'+route.path,method,path.rsplit('/',1)[0]+'/'+MARKER,declared_doc=(doc,route.path))
 for key,value in [('limit',MARKER),('limit','201'),('offset','-1'),('query',MARKER*30),('platform',MARKER*30),('user_id',MARKER*30),('account_id',MARKER*30),('chat_id',MARKER*30),('thread_id',MARKER*30)]:
  await raw('bounded_query_'+key+'_'+value[:5],'GET','/conversations',query={'profile':'main',key:value},declared_doc=(doc,'/conversations'))
 from fastapi import APIRouter,FastAPI
 plain=APIRouter()
 @plain.get('/plain-default')
 def plain_default(limit:int):return limit
 app.include_router(plain,prefix=PREFIX);app.openapi_schema=None;plain_doc=app.openapi()
 plain_schema=plain_doc['paths'][PREFIX+'/plain-default']['get']['responses']['422']['content']['application/json']['schema']
 add('unrelated_router_schema_default_unchanged',plain_schema=={'$ref':'#/components/schemas/HTTPValidationError'} and deref(plain_schema,plain_doc)['properties']['detail']['type']=='array',schema=plain_schema)
 # The baseline body is independently exercised by unchanged extended_worker.
 scoped=APIRouter(route_class=api.ProductAPIRoute)
 @scoped.get('/response-invalid',response_model=int)
 def response_invalid():return {'invalid':MARKER}
 app.include_router(scoped,prefix=PREFIX)
 await raw('response_validation_remains500','GET','/response-invalid',expected=500,exception_expected='ResponseValidationError')
 source=(ns['CANDIDATE']/'plugins/friday_rework/dashboard/api.py').read_text()
 declaration=',\n                   responses={422: {"model": ProductRequestError, "description": "Invalid product request"}}'
 assert source.count(declaration)==1
 mutation=source.replace(declaration,'')
 before_ast=ast.parse(source);after_ast=ast.parse(mutation)
 changed=[]
 for a,b in zip(before_ast.body,after_ast.body):
  if ast.dump(a)!=ast.dump(b):changed.append(a)
 add('mutation_changes_only_router_response_declaration',len(before_ast.body)==len(after_ast.body) and len(changed)==1 and isinstance(changed[0],ast.Assign) and changed[0].targets[0].id=='router',changed_AST_nodes=len(changed))
 mutation_path=OUT/'causal-mutation-api.py';mutation_path.write_text(mutation)
 spec=importlib.util.spec_from_file_location('causal_product_api',mutation_path);mutant=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mutant;spec.loader.exec_module(mutant)
 mutant._admin=api._admin;mutant.masked=api.masked
 mutated_app=FastAPI();mutated_app.state.auth_required=True;mutated_app.include_router(mutant.router,prefix=PREFIX)
 mutated_doc=mutated_app.openapi();(OUT/'CAUSAL-MUTATION-OPENAPI.json').write_text(json.dumps(mutated_doc,sort_keys=True,indent=2)+'\n')
 schema=mutated_doc['paths'][PREFIX+'/onboarding/credentials']['put']['responses']['422']['content']['application/json']['schema']
 add('mutation_restores_actual_default_array_schema',schema=={'$ref':'#/components/schemas/HTTPValidationError'} and deref(schema,mutated_doc)['properties']['detail']['type']=='array',schema=schema)
 for name,method,path,body,query in [('body','PUT','/onboarding/credentials',json.dumps({MARKER:MARKER}).encode(),{'profile':'main'}),('query','GET','/conversations',b'',{'profile':'main','limit':MARKER}),('path','GET','/attachments/task/'+MARKER,b'',{'profile':'main'}),('malformed_JSON','PUT','/onboarding/credentials',b'{"value":"'+MARKER.encode()+b'",broken:}',{'profile':'main'})]:
  pattern='/attachments/{task_id}/{index}' if name=='path' else path
  await raw('causal_declaration_removed_'+name,method,path,body=body,query=query,target=mutated_app,declared_doc=(mutated_doc,pattern),compatible=False)
baseline_threads=[t.name for t in threading.enumerate()]
fatal=None
try:asyncio.run(run())
except Exception as e:fatal={'exception':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
result={'schema':'friday.openapi422-source-contract-controls.v1','cases':rows,'executed_controls':len(rows),'failures':[r['name'] for r in rows if r['status']!='PASS'],'fatal':fatal,'audit_denials':ns['events'],'seams':ns['report']['seams'],'production_API_full_module':True,'setup_source_sha256':hashlib.sha256(setup.encode()).hexdigest(),'candidate_api_sha256':hashlib.sha256((ns['CANDIDATE']/'plugins/friday_rework/dashboard/api.py').read_bytes()).hexdigest(),'resources':{'affinity':sorted(os.sched_getaffinity(0)),'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'baseline_threads':baseline_threads,'final_threads':[t.name for t in threading.enumerate()],'children':pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split(),'whole_peak':'UNKNOWN'},'frameworks':{n:importlib.metadata.version(n) for n in ['fastapi','starlette','pydantic','pydantic_core','anyio','httpx']},'runtime_or_release_grant':False}
(OUT/'OPENAPI-CONTRACT-OBSERVATIONS.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['executed_controls','failures','fatal','audit_denials','resources','frameworks']}))
if fatal or result['failures'] or result['audit_denials'] or result['resources']['children'] or baseline_threads!=result['resources']['final_threads']:sys.exit(1)
