"""Full production middleware/cookie/provider-scan/API integration; synthetic identities only."""
import sys
assert sys.stdin.readline()=='execute\n'
import argparse,asyncio,copy,hashlib,importlib.metadata,importlib.util,json,os,resource,socket,subprocess,threading,time,traceback
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--profile',required=True)
parser.add_argument('--candidate',required=True);parser.add_argument('--native',required=True);parser.add_argument('--overlay',required=True);args=parser.parse_args()
OUT=Path(__file__).resolve().parent
CANDIDATE=Path(args.candidate).resolve()
NATIVE=Path(args.native).resolve()
OVERLAY=Path(args.overlay).resolve()
READ_ROOTS=[OUT,CANDIDATE,NATIVE,OVERLAY,Path(sys.prefix),Path('/usr/lib/python3.14')]
READ_FILES={Path('/usr/lib/python314.zip'),Path(f'/proc/{os.getpid()}/stat'),Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children')}
events=[];read_paths=set()
def audit(event,values):
 def deny(reason):
  events.append({'event':event,'reason':reason});raise PermissionError(reason)
 if event=='open':
  path,mode,flags=values
  if isinstance(path,(str,bytes,os.PathLike)):
   p=Path(os.fsdecode(path)).resolve();write=(flags or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
   if write and not p.is_relative_to(OUT):deny('write_outside_OUTPUT')
   if not write:
    read_paths.add(str(p))
    if any(x in p.parts for x in ['.hermes','.codex','.ssh','codex-multi']) or (p.name in ['.env','credentials.json','auth.json'] and not p.is_relative_to(OUT)):deny('production_HOME_credentials_read')
    if p not in READ_FILES and not any(p.is_relative_to(root) for root in READ_ROOTS):deny('read_outside_declared_source_dependency_OUTPUT_procself')
 if event in {'subprocess.Popen','os.system','os.fork','os.posix_spawn','socket.connect','socket.bind','socket.getaddrinfo','socket.sendto','ctypes.dlopen'}:
  # CPython extension import uses dlopen internally without this ctypes event.
  deny('forbidden_effect:'+event)
 if event=='socket.__new__' and values[1] not in (-1,socket.AF_UNIX):deny('network_socket_creation')
 if event in {'os.mkdir','os.remove','os.rename','os.chmod','os.chown','os.link','os.symlink','os.rmdir','os.truncate','os.utime'}:
  for v in values[:2]:
   if isinstance(v,(str,bytes,os.PathLike)) and not Path(os.fsdecode(v)).resolve().is_relative_to(OUT):deny('mutation_outside_OUTPUT')
sys.addaudithook(audit)
sys.path.insert(0,str(NATIVE))
if args.profile=='fastapi01331':sys.path.insert(0,str(OVERLAY))
report={'profile':args.profile,'claim':'SOURCE_NATIVE_MIDDLEWARE_INTEGRATION_ONLY; owned synthetic in-memory providers/policy/backend, no genuine login/runtime/installed acceptance',
 'cases':[],'isolation_controls':[],'audit_denials':events,'fatal':None,'full_import_complete':False}
def dump(name,value):
 with open(OUT/(args.profile+'-'+name),'x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
baseline_threads=[t.name for t in threading.enumerate()]
try:
 from fastapi import FastAPI,Request
 from fastapi.responses import Response
 from fastapi.routing import APIRoute
 import httpx
 from hermes_cli import friday_product_access as policy_module
 from hermes_cli.dashboard_auth import register_provider,clear_providers,list_providers
 from hermes_cli.dashboard_auth.base import DashboardAuthProvider,Session,TokenPrincipal,ProviderError,RefreshExpiredError
 from hermes_cli.dashboard_auth.middleware import gated_auth_middleware
 from hermes_cli.dashboard_auth import cookies,registry,request_utils,token_auth,middleware
 from hermes_cli.dashboard_auth import refresh_singleflight
 spec=importlib.util.spec_from_file_location('exact_full_product_api',CANDIDATE/'plugins/friday_rework/dashboard/api.py')
 api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)
 report['full_import_complete']=True
 report['versions']={n:importlib.metadata.version(n) for n in ['fastapi','starlette','pydantic','pydantic_core','httpx','anyio']}
 report['fastapi_actual_file']=sys.modules['fastapi'].__file__
 report['fastapi_runtime_version']=sys.modules['fastapi'].__version__
 expected_fastapi='0.133.1' if args.profile=='fastapi01331' else '0.139.2'
 assert report['versions']['fastapi']==report['fastapi_runtime_version']==expected_fastapi, 'framework_profile_version_pin_mismatch'
 report['module_pins']={m.__name__:{'path':m.__file__,'sha256':hashlib.file_digest(open(m.__file__,'rb'),'sha256').hexdigest()} for m in [api,policy_module,middleware,cookies,registry,request_utils,token_auth,refresh_singleflight]}
 provider_calls=[];backend_calls=[]
 synthetic_tokens={'owner':('owner','',3600),'foreign':('foreign','',3600),'wrong-org':('owner','foreign-org',3600),'expired-issued':('owner','',-3600)}
 class SyntheticProvider(DashboardAuthProvider):
  name='fixture-one';display_name='SYNTHETIC one';supports_token=True
  def start_login(self,**kw):raise AssertionError('genuine_login_forbidden')
  def complete_login(self,**kw):raise AssertionError('genuine_login_forbidden')
  def revoke_session(self,**kw):raise AssertionError('revocation_contact_forbidden')
  def session(self,token,user='owner',org='',delta=3600):return Session(user,'fixture.invalid','Synthetic only',org,self.name,int(time.time())+delta,token,'')
  def verify_session(self,*,access_token):
   provider_calls.append({'provider':self.name,'phase':'verify','token':access_token})
   if access_token in ['outage','outage-then-owner-two']:raise ProviderError('synthetic-offline-outage')
   data=synthetic_tokens.get(access_token)
   return self.session(access_token,*data) if data else None
  def refresh_session(self,*,refresh_token):
   provider_calls.append({'provider':self.name,'phase':'refresh','token':refresh_token})
   if refresh_token.startswith('refresh-outage'):raise ProviderError('synthetic-refresh-outage')
   if refresh_token.startswith('refresh-valid'):return self.session('rotated-owner')
   raise RefreshExpiredError('synthetic-unrecognized')
  def verify_token(self,*,token):
   provider_calls.append({'provider':self.name,'phase':'service-token','token':token})
   return TokenPrincipal('synthetic-service',self.name,('admin',)) if token=='service' else None
 class SyntheticSecond(SyntheticProvider):
  name='fixture-two';display_name='SYNTHETIC two';supports_token=False
  def verify_session(self,*,access_token):
   provider_calls.append({'provider':self.name,'phase':'verify','token':access_token})
   return self.session(access_token) if access_token in ['owner-two','outage-then-owner-two'] else None
  def refresh_session(self,*,refresh_token):
   provider_calls.append({'provider':self.name,'phase':'refresh','token':refresh_token})
   raise RefreshExpiredError('synthetic-unrecognized')
 clear_providers();register_provider(SyntheticProvider());register_provider(SyntheticSecond());token_auth.clear_token_routes()
 policy={'admin':{'enabled':True,'operators':[{'provider':n,'user_id':'owner','org_id':''} for n in ['fixture-one','fixture-two']],'profiles':['main']}}
 baseline_policy=copy.deepcopy(policy);policy_module.settings=lambda:copy.deepcopy(policy)
 class Backend:
  def __getattr__(self,name):
   def invoke(*a,**kw):
    backend_calls.append({'method':name,'args_count':len(a),'kwargs':list(kw),'session_user':next((x.user_id for x in list(a)+list(kw.values()) if isinstance(x,Session)),None)})
    return b'fixture-bytes' if name in ['attachment','input_attachment'] else {'synthetic_backend':name}
   return invoke
 api._admin=Backend();api.masked=lambda value:value
 def appmake(include_gate=True):
  app=FastAPI();app.state.auth_required=True;app.include_router(api.router,prefix='/api/plugins/friday_rework')
  if include_gate:app.middleware('http')(gated_auth_middleware)
  app.middleware('http')(token_auth.token_auth_middleware)
  return app
 app=appmake()
 def cookie_header(at='',rt='',hint='',https=False,prefix=''):
  response=Response();cookies.set_session_cookies(response,access_token=at,refresh_token=rt,access_token_expires_in=3600,use_https=https,prefix=prefix,provider=hint)
  return '; '.join(value.decode().split(';',1)[0] for key,value in response.raw_headers if key.lower()==b'set-cookie')
 async def request(name,expected,expected_calls=0,method='GET',path='/users',cookie=None,bearer=None,data=None,raw=None,query='profile=main',use_app=None,check=None,root_path='',scheme='http'):
  actual_app=use_app or app;headers={}
  if cookie is not None:headers['cookie']=cookie
  if bearer is not None:headers['authorization']='Bearer '+bearer
  if data is not None or raw is not None:headers['content-type']='application/json'
  url='/api/plugins/friday_rework'+path if path.startswith('/') else path
  if query is not None:url+='?'+query
  before=len(backend_calls);pbefore=len(provider_calls)
  transport=httpx.ASGITransport(app=actual_app,root_path=root_path)
  async with httpx.AsyncClient(transport=transport,base_url=scheme+'://fixture.invalid') as client:
   response=await client.request(method,url,headers=headers,content=raw if raw is not None else json.dumps(data).encode() if data is not None else None)
  value={'name':name,'status_code':response.status_code,'expected_status':expected,'backend_calls':backend_calls[before:],'expected_backend_calls':expected_calls,
   'provider_calls':provider_calls[pbefore:],'body':response.text,'set_cookie':response.headers.get_list('set-cookie')}
  good=response.status_code==expected and len(backend_calls)-before==expected_calls
  if check is not None:
   try:value['specific_check']=bool(check(response,value));good=good and value['specific_check']
   except Exception as e:value['specific_check_error']=repr(e);good=False
  value['status']='PASS' if good else 'FAIL';report['cases'].append(value);return response,value
 async def main():
  owner=cookie_header('owner');foreign=cookie_header('foreign')
  await request('anonymous_no_cookie',401,check=lambda r,v:not v['provider_calls'])
  await request('valid_cookie_exact_one_backend',200,1,cookie=owner,check=lambda r,v:v['provider_calls']==[{'provider':'fixture-one','phase':'verify','token':'owner'}])
  await request('valid_bearer_exact_one_backend',200,1,bearer='owner',check=lambda r,v:not v['set_cookie'])
  for token,status in [('foreign',403),('wrong-org',403),('expired-issued',403),('rejected-expired',401),('unknown',401)]:
   await request('cookie_'+token,status,cookie=cookie_header(token),check=lambda r,v:bool(v['provider_calls']))
   await request('bearer_'+token,status,bearer=token,check=lambda r,v:not v['set_cookie'])
  await request('provider_hint_orders_but_is_not_identity',200,1,cookie=cookie_header('owner',hint='fixture-two'),check=lambda r,v:[x['provider'] for x in v['provider_calls']]==['fixture-two','fixture-one'])
  await request('unknown_hint_scan_still_verifies',200,1,cookie=cookie_header('owner',hint='unregistered'))
  await request('forged_owner_hint_foreign_session_denied',403,cookie=cookie_header('foreign',hint='fixture-one'))
  await request('owner_two_native_scan',200,1,cookie=cookie_header('owner-two'))
  await request('provider_failure_503_cookie',503,cookie=cookie_header('outage'),check=lambda r,v:not v['set_cookie'])
  await request('provider_failure_503_bearer',503,bearer='outage')
  await request('outage_does_not_abort_later_provider',200,1,bearer='outage-then-owner-two',check=lambda r,v:[x['provider'] for x in v['provider_calls']]==['fixture-one','fixture-two'])
  await request('bearer_owner_wins_foreign_cookie',200,1,bearer='owner',cookie=foreign,check=lambda r,v:all(x['token']=='owner' for x in v['provider_calls']))
  await request('bearer_foreign_wins_owner_cookie',403,bearer='foreign',cookie=owner)
  await request('invalid_bearer_no_valid_cookie_fallback',401,bearer='unknown',cookie=owner)
  await request('bearer_outage_no_cookie_fallback',503,bearer='outage',cookie=owner)
  await request('empty_bearer_native_cookie_fallback',200,1,bearer='',cookie=owner)
  await request('https_host_cookie_actual_reader',200,1,cookie=cookie_header('owner',https=True),scheme='https')
  await request('https_secure_cookie_actual_reader',200,1,cookie=cookie_header('owner',https=True,prefix='/fixture'),scheme='https')
  await request('stricter_cookie_variant_precedes_bare',403,cookie=cookie_header('owner')+'; '+cookie_header('foreign',https=True))
  await request('hint_missing_native_response_sets_hint',200,1,cookie=owner,check=lambda r,v:any('hermes_session_provider=fixture-one' in x for x in v['set_cookie']))
  await request('hint_present_native_response_no_rewrite',200,1,cookie=cookie_header('owner',hint='fixture-one'),check=lambda r,v:not v['set_cookie'])
  policy['admin']['operators']=[{'provider':'fixture-one','user_id':'different','org_id':''}]
  await request('policy_revoked_between_requests',403,cookie=owner)
  policy.clear();policy.update(copy.deepcopy(baseline_policy))
  await request('same_cookie_after_policy_restoration',200,1,cookie=owner)
  policy['admin']['operators']=[]
  await request('malformed_policy_fail_closed',403,cookie=owner)
  policy.clear();policy.update(copy.deepcopy(baseline_policy))
  await request('foreign_profile_gate_denied',403,cookie=owner,query='profile=foreign')
  app.state.auth_required=False
  await request('auth_required_false_fail_closed',403,cookie=owner,check=lambda r,v:not v['provider_calls'])
  app.state.auth_required=True
  await request('native_unreviewed_route_denied',403,cookie=owner,path='api/native/config')
  await request('service_unregistered_not_interactive_session',401,bearer='service')
  token_auth.register_token_route('/api/plugins/friday_rework/users')
  await request('registered_service_no_operator_bypass',403,bearer='service',check=lambda r,v:v['provider_calls']==[{'provider':'fixture-one','phase':'service-token','token':'service'}])
  await request('service_with_owner_cookie_still_no_bypass',403,bearer='service',cookie=owner)
  await request('registered_service_route_missing_token',401,cookie=owner)
  token_auth.clear_token_routes()
  marker='SYNTHETIC_SECRET_NEVER_REFLECT'
  exact=lambda r,v:r.json()=={'detail':'invalid_product_request'} and marker not in r.text
  for auth in ['cookie','bearer']:
   kw={'cookie':owner} if auth=='cookie' else {'bearer':'owner'}
   await request(auth+'_invalid_body_private_exact422',422,method='PUT',path='/onboarding/credentials',data={'value':marker},check=exact,**kw)
   await request(auth+'_invalid_query_private_exact422',422,path='/users',query=None,check=exact,**kw)
   await request(auth+'_invalid_path_private_exact422',422,path='/attachments/task/notint',check=exact,**kw)
   await request(auth+'_malformedJSON_private_exact422',422,method='PUT',path='/onboarding/credentials',raw=('{"value":"'+marker+'",').encode(),check=exact,**kw)
  credential={'platform':'cli','transport_profile':'main','account_id':'local','user_id':'owner','expected_config_sha256':'a'*64,'generation':1,'name':'FIXTURE_CREDENTIAL','value':marker}
  await request('authorized_valid_credential_exact_one_backend',200,1,method='PUT',path='/onboarding/credentials',data=credential,cookie=owner,check=lambda r,v:marker not in r.text and v['backend_calls'][0]['session_user']=='owner')
  await request('foreign_invalid_body_auth_first',403,method='PUT',path='/onboarding/credentials',data={'value':marker},cookie=foreign)
  await request('anonymous_invalid_body_auth_first',401,method='PUT',path='/onboarding/credentials',data={'value':marker})
  await request('expired_access_no_refresh_deletes_cookie',401,cookie=cookie_header('rejected-expired'),check=lambda r,v:any('Max-Age=0' in x for x in v['set_cookie']))
  await request('valid_native_refresh_and_rotated_cookie',200,1,cookie=cookie_header('rejected-expired','refresh-valid-'+args.profile,hint='fixture-one'),check=lambda r,v:any('hermes_session_at=rotated-owner' in x for x in v['set_cookie']))
  await request('rejected_native_refresh_401',401,cookie=cookie_header('rejected-expired','refresh-invalid-'+args.profile),check=lambda r,v:any('Max-Age=0' in x for x in v['set_cookie']))
  await request('refresh_only_cookie_native_path',200,1,cookie=cookie_header('', 'refresh-valid-only-'+args.profile,hint='fixture-one'))
  await request('refresh_failure503_keeps_cookies',503,cookie=cookie_header('rejected-expired','refresh-outage-'+args.profile),check=lambda r,v:not v['set_cookie'])
  # Causal controls change explicit input/provider/backend seams, never protected production functions.
  clear_providers()
  await request('causal_remove_registry_valid_token_rejected',401,cookie=owner,check=lambda r,v:not v['provider_calls'])
  register_provider(SyntheticProvider());register_provider(SyntheticSecond())
  await request('causal_restore_registry_same_token_accepted',200,1,cookie=owner)
  # Isolation control: full require_admin still refuses without gate/session establishment.
  no_gate=appmake(include_gate=False)
  await request('causal_omit_middleware_require_admin_still_denies',403,cookie=owner,use_app=no_gate,check=lambda r,v:not v['provider_calls'])
  # Product OpenAPI generation only checks this exact artifact through imported route definitions.
  schema=app.openapi();decl=schema['paths']['/api/plugins/friday_rework/onboarding/credentials']['put']['responses']['422']['content']['application/json']['schema']
  model=schema['components']['schemas']['ProductRequestError']
  report['contract']={'declared422':decl,'model':model,'status':'PASS' if decl=={'$ref':'#/components/schemas/ProductRequestError'} and model.get('properties',{}).get('detail',{}).get('const')=='invalid_product_request' else 'FAIL'}
 asyncio.run(main())
 clear_providers();token_auth.clear_token_routes()
 for name,fn in [
  ('write_outside_output',lambda:open('/tmp/friday-middleware-forbidden','w')),
 ('production_home_credentials_read',lambda:open('/home/fixture/.hermes/.env')),
  ('production_home_generic_read',lambda:open('/home/fixture/friday-forbidden-fixture')),
  ('network_socket',lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM)),
  ('provider_network_lookup',lambda:socket.getaddrinfo('fixture.invalid',443)),
  ('native_socket_contact',lambda:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM).connect('/tmp/friday-middleware-no-socket')),
  ('worker_subprocess',lambda:subprocess.run(['/bin/true']))]:
  n=len(events)
  try:fn();ok=False;detail='unexpected_allowed'
  except PermissionError as e:ok=len(events)==n+1;detail=str(e)
  except Exception as e:ok=False;detail=repr(e)
  report['isolation_controls'].append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
 report['registry_after_clear']=[p.name for p in list_providers()]
except BaseException as e:
 report['fatal']={'exception':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
finally:
 # asyncio.run closes loop/sockets and AnyIO workers are signalled on loop close.
 until=time.monotonic()+5
 for t in list(threading.enumerate()):
  if t is not threading.current_thread() and t.name not in baseline_threads:t.join(timeout=max(0,until-time.monotonic()))
 report['closure']={'baseline_threads':baseline_threads,'final_threads':[t.name for t in threading.enumerate()],
  'thread_drift':[t.name for t in threading.enumerate() if t.name not in baseline_threads],
  'children':Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split(),
  'open_fds':{n:os.readlink('/proc/self/fd/'+n) for n in os.listdir('/proc/self/fd') if os.path.exists('/proc/self/fd/'+n)},
  'pid':os.getpid(),'start_ticks':int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),
  'affinity':sorted(os.sched_getaffinity(0)),'AS_limit':resource.getrlimit(resource.RLIMIT_AS)}
 report['read_paths']=sorted(read_paths)
 report['counts']={'requests':len(report['cases']),'isolation_controls':len(report['isolation_controls']),'contract_controls':1 if 'contract' in report else 0,
  'PASS':sum(x['status']=='PASS' for x in report['cases']+report['isolation_controls']),'FAIL':sum(x['status']=='FAIL' for x in report['cases']+report['isolation_controls']),'executions_not_unique':True}
 report['status']='PASS' if report['fatal'] is None and report['counts']['FAIL']==0 and report.get('contract',{}).get('status')=='PASS' and not report['closure']['thread_drift'] and not report['closure']['children'] else 'FAIL'
 dump('OBSERVATIONS.json',report)
 print(json.dumps({'status':report['status'],'counts':report['counts'],'fatal':report['fatal']}))
 if report['status']!='PASS':sys.exit(1)
