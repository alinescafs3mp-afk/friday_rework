"""Exact full API module + real Pydantic/FastAPI in-memory ASGI evidence.

Not native authentication: Session is a fixture of an already verified identity.
Not native config: product_access.settings is the only policy input seam.
Not backend/native writes: _admin and masked are inert recording adapters.
No dependency override or replacement of exact require_admin/native policy helpers.
"""
import sys
assert sys.stdin.readline()=='execute\n'
import os, pathlib, json, ast, importlib.util, importlib.metadata, hashlib, copy, time, traceback, threading, resource, asyncio, urllib.parse
OUT=pathlib.Path(__file__).resolve().parent
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--candidate',required=True);parser.add_argument('--native',required=True)
args=parser.parse_args()
CANDIDATE=pathlib.Path(args.candidate).resolve(strict=True)
NATIVE=pathlib.Path(args.native).resolve(strict=True);ROOT=NATIVE.parent
events=[]
def audit(event,args):
    if event=='open':
        path,mode,flags=args
        if isinstance(path,(str,bytes,os.PathLike)):
            p=pathlib.Path(os.fsdecode(path)).resolve()
            writable=(flags or 0)&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
            if writable and not p.is_relative_to(OUT):
                events.append({'event':event,'path':str(p),'blocked':'write_outside_OUTPUT'});raise PermissionError('audit_write_outside_OUTPUT')
            if not writable and ('.hermes' in p.parts or '.codex' in p.parts or 'codex-multi' in p.parts):
                events.append({'event':event,'path':str(p),'blocked':'production_HOME_read'});raise PermissionError('audit_production_HOME_read')
    if event in {'subprocess.Popen','os.system','os.fork','os.posix_spawn','socket.connect','socket.bind','socket.getaddrinfo'}:
        events.append({'event':event,'blocked':True});raise PermissionError('audit_forbidden_effect:'+event)
    if event in {'os.mkdir','os.remove','os.rename','os.chmod','os.chown','os.link','os.symlink','os.rmdir','os.truncate'}:
        for arg in args[:2]:
            if isinstance(arg,(str,bytes,os.PathLike)) and not pathlib.Path(os.fsdecode(arg)).resolve().is_relative_to(OUT):
                events.append({'event':event,'blocked':'mutation_outside_OUTPUT'});raise PermissionError('audit_mutation_outside_OUTPUT')
sys.addaudithook(audit)
sys.path.insert(0,str(NATIVE))
from fastapi import FastAPI, Request
from pydantic import ValidationError
from hermes_cli import friday_product_access as native
from hermes_cli.dashboard_auth.base import Session
spec=importlib.util.spec_from_file_location('verified_full_friday_api',CANDIDATE/'plugins/friday_rework/dashboard/api.py')
api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)
baseline_threads=[t.name for t in threading.enumerate()]

report={'claim':'actual installed frameworks on exact frozen full source; policy/backend fixtures explicitly limited; not installed/live/WebUI/native runtime acceptance',
 'seams':{'policy':'full native settings callable replaced by in-memory configuration input; native admin_policy/operator_allowed/session_allowed/profile_name remain exact full-module functions',
          'identity':'exact native Session dataclass fixtures at verified-session handoff; no provider login, token, cookie, CSRF verification',
          'backend':'_admin recording sentinel and masked identity adapter; no actual Administration backend, persistence, workers or configuration executed',
          'request_gate':'harness ASGI wrapper invokes actual native request_allowed; donor full middleware/server not imported'},
 'schema_cases':[],'asgi_cases':[],'native_helper_cases':[],'audit_denials':events,'fatal':None}
H='a'*64
I={'platform':'cli','transport_profile':'main','account_id':'local','user_id':'owner','expected_config_sha256':H}
P=I|{'template':'standard','runtime_profile':'owner_1','uid':1000}
T=P|{'platform':'telegram','account_id':'bot','user_id':'123'};T.pop('uid')
A=I|{'generation':1}
C=A|{'name':'DUMMY_CREDENTIAL','value':'fixture-not-a-secret'}
valid={'UserChange':{'platform':'telegram','transport_profile':'main','account_id':'bot','user_id':'123','enabled':True,'role':'user'},
       'PairApproval':{'platform':'telegram','transport_profile':'main','account_id':'bot','request_id':'request1'},
       'TaskControl':{'action':'status'},'SettingsChange':{'expected_sha256':H,'kind':'model','values':{}},
       'ScheduleChange':{'action':'pause'},'OnboardingIdentity':I,'OnboardingPrepare':P,'OnboardingActivate':A,
       'OnboardingCredential':C,'WorkerPrepare':A|{'worker':'dsh','runtime':{}},
       'WorkerConfigure':A|{'worker':'a0','preparation':{},'runtime_receipt':{}}}
def schema_case(name,model,data,expect):
    try:
        value=getattr(api,model).model_validate(data)
        accepted=True; errors=[]
    except ValidationError as e:
        accepted=False;errors=[{'location':list(x['loc']),'type':x['type']} for x in e.errors(include_input=False,include_context=False)]
    report['schema_cases'].append({'name':name,'model':model,'accepted':accepted,'expected_accepted':expect,'status':'PASS' if accepted==expect else 'FAIL','errors':errors})
    return accepted
for model,data in valid.items():
    schema_case(model+'_positive',model,data,True)
    schema_case(model+'_extra_field',model,data|{'unexpected':'x'},False)
    schema_case(model+'_wrong_container',model,[],False)
schema_case('unchanged_transport_positive','OnboardingPrepare',T,True)
for name,delta,remove,ok in [
 ('cli_missing_uid',{},['uid'],False),('cli_null_uid',{'uid':None},[],False),('cli_bool_uid',{'uid':True},[],False),
 ('cli_string_uid',{'uid':'1000'},[],False),('cli_float_uid',{'uid':1000.0},[],False),('cli_negative_uid',{'uid':-1},[],False),
 ('cli_zero_uid_schema_only',{'uid':0},[],True),('uid_list',{'uid':[]},[],False),
 ('bad_runtime_path',{'runtime_profile':'../escape'},[],False),('bad_runtime_space',{'runtime_profile':'with space'},[],False),
 ('bad_runtime_empty',{'runtime_profile':''},[],False),('bad_runtime_65',{'runtime_profile':'x'*65},[],False),
 ('runtime_64_boundary',{'runtime_profile':'x'*64},[],True),('bad_hash_short',{'expected_config_sha256':'a'*63},[],False),
 ('bad_hash_upper',{'expected_config_sha256':'A'*64},[],False),('bad_hash_nonhex',{'expected_config_sha256':'z'*64},[],False),
 ('bad_hash_number',{'expected_config_sha256':123},[],False),('wrong_platform_type',{'platform':123},[],False),
 ('empty_account_reference',{'account_id':''},[],False),('overlong_user_reference',{'user_id':'x'*513},[],False),
 ('wrong_template_type',{'template':{}},[],False),('null_transport_reference',{'transport_profile':None},[],False)]:
    data=P|delta
    for key in remove:data.pop(key)
    schema_case(name,'OnboardingPrepare',data,ok)
schema_case('transport_numeric_uid_refused','OnboardingPrepare',T|{'uid':1000},False)
schema_case('transport_null_uid_positive','OnboardingPrepare',T|{'uid':None},True)
for gen in [True,'1',1.0,0,-1]:schema_case('generation_wrong_'+repr(gen),'OnboardingActivate',A|{'generation':gen},False)
for name in ['lowercase','1BAD','BAD-NAME','A'*129,'']:
    schema_case('credential_bad_name_'+repr(name),'OnboardingCredential',C|{'name':name},False)
schema_case('credential_name_128_boundary','OnboardingCredential',C|{'name':'A'*128},True)
schema_case('credential_wrong_type','OnboardingCredential',C|{'value':123},False)
for model,field,wrong in [('UserChange','enabled',1),('UserChange','role','owner'),('TaskControl','action','execute'),
 ('SettingsChange','kind','shell'),('SettingsChange','values',{'v'+str(i):i for i in range(9)}),
 ('WorkerPrepare','worker','unknown'),('WorkerPrepare','runtime',[]),('WorkerPrepare','a0_network',[]),
 ('WorkerConfigure','preparation',[]),('WorkerConfigure','runtime_receipt',[])]:
    schema_case(model+'_'+field+'_negative',model,valid[model]|{field:wrong},False)

policy={'admin':{'enabled':True,'operators':[{'provider':'fixture','user_id':'owner','org_id':''}],'profiles':['main']}}
native.settings=lambda:copy.deepcopy(policy)
session=Session(user_id='owner',email='fixture.invalid',display_name='fixture',org_id='',provider='fixture',expires_at=int(time.time())+3600,access_token='fixture',refresh_token='fixture')
other=Session(user_id='other',email='fixture.invalid',display_name='fixture',org_id='',provider='fixture',expires_at=int(time.time())+3600,access_token='fixture',refresh_token='fixture')
expired=Session(user_id='owner',email='fixture.invalid',display_name='fixture',org_id='',provider='fixture',expires_at=1,access_token='fixture',refresh_token='fixture')
def helper_case(name,fn,expect):
    try: value=fn();passed=value==expect; detail={'value':value}
    except Exception as e:passed=False;detail={'exception':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
    report['native_helper_cases'].append({'name':name,'status':'PASS' if passed else 'FAIL','expected':expect,**detail})
    return passed
policy_ready=helper_case('actual_native_policy_with_settings_input_seam',lambda:native.admin_policy()==policy['admin'],True)
if policy_ready:
    for name,s,expected in [('valid_operator',session,True),('anonymous',None,False),('foreign_identity',other,False),('expired_operator',expired,False),('duck_typed_not_Session',type('FakeSession',(),session.__dict__)(),False)]:
        helper_case('native_session_'+name,lambda s=s:native.session_allowed(s),expected)
    saved=copy.deepcopy(policy);policy['admin']['operators']=[]
    helper_case('malformed_revoked_policy_refuses',lambda:native.session_allowed(session),False)
    policy.clear();policy.update(saved)

calls=[]; behavior=None
class RecordingBackend:
    def __getattr__(self,name):
        def invoke(*args,**kwargs):
            rec={'method':name,'args':[{'native_Session_fixture':True} if isinstance(x,Session) else x for x in args],
                 'kwargs':{k:({'native_Session_fixture':True} if isinstance(v,Session) else {'secret_forwarded_exactly':v=='fixture-not-a-secret'} if k=='value' else v) for k,v in kwargs.items()}}
            calls.append(rec)
            if behavior=='permission':raise PermissionError('foreign_product_profile')
            if behavior=='transport':raise PermissionError('receiving_transport_authority_required')
            if behavior=='reference':raise ValueError('invalid_reference')
            if behavior=='key':raise KeyError('invalid_reference')
            if behavior=='index':raise IndexError('invalid_reference')
            if behavior=='unavailable':raise RuntimeError('unconfirmed')
            if name in {'attachment','input_attachment'}:return b'fixture-bytes'
            return {'adapter':'inert_recording_backend','method':name}
        return invoke
original_admin=api._admin; original_masked=api.masked
api._admin=RecordingBackend();api.masked=lambda x:x
app=FastAPI();app.state.auth_required=True;app.include_router(api.router,prefix='/api/plugins/friday_rework')
routes=[('GET','/health',None),('GET','/profiles',None),('GET','/users',None),('PUT','/users',valid['UserChange']),
 ('GET','/pairing',None),('POST','/pairing/approve',valid['PairApproval']),('GET','/conversations',None),
 ('GET','/conversations/session1',None),('GET','/tasks',None),('POST','/tasks/task1/control',valid['TaskControl']),
 ('PUT','/settings',valid['SettingsChange']),('GET','/schedules',None),('POST','/schedules/job1/control',valid['ScheduleChange']),
 ('GET','/attachments/task1/0',None),('GET','/effective',None),('GET','/inputs/task1/0',None),('GET','/onboarding',None),
 ('POST','/onboarding/prepare',P),('PUT','/onboarding/credentials',C),('POST','/onboarding/activate',A),
 ('POST','/onboarding/worker/prepare',valid['WorkerPrepare']),('POST','/onboarding/worker/configure',valid['WorkerConfigure']),
 ('POST','/onboarding/workers/prepare',A),('POST','/onboarding/workers/qualify',A),('POST','/onboarding/workers/state',A)]
async def request(name,method,path,data=None,expected=200,s=session,query=None,auth=True,gate=True,expected_calls=1):
    app.state.auth_required=auth
    query=query if query is not None else {'profile':'main'}
    body=b'' if data is None else json.dumps(data).encode(); messages=[]; delivered=False
    full='/api/plugins/friday_rework'+path
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':full,'raw_path':full.encode(),'root_path':'','query_string':urllib.parse.urlencode(query).encode(),
           'headers':[(b'content-type',b'application/json')],'client':('inert',0),'server':('inert',0),'state':{'session':s},'app':app}
    before=len(calls)
    async def receive():
        nonlocal delivered
        if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
        return {'type':'http.disconnect'}
    async def send(message):messages.append(message)
    # This wrapper is an explicit donor-middleware seam; request_allowed itself
    # is the unchanged real native module function, not a fabricated allow.
    if gate and not native.request_allowed(Request(scope)):
        messages=[{'type':'http.response.start','status':403,'headers':[]},{'type':'http.response.body','body':b'{"detail":"native_request_policy_refused"}'}]
    else: await app(scope,receive,send)
    status=next(x['status'] for x in messages if x['type']=='http.response.start')
    payload=b''.join(x.get('body',b'') for x in messages if x['type']=='http.response.body')
    headers=next(x.get('headers',[]) for x in messages if x['type']=='http.response.start')
    record={'name':name,'method':method,'path':path,'status_code':status,'expected_status_code':expected,'backend_calls':len(calls)-before,'expected_backend_calls':expected_calls,
            'status':'PASS' if status==expected and len(calls)-before==expected_calls else 'FAIL',
            'body':payload.decode(errors='replace')[:1000],'headers':[[a.decode(),b.decode()] for a,b in headers],
            'backend_records':calls[before:]}
    report['asgi_cases'].append(record)
    return record
async def run():
    if not policy_ready:
        report['asgi_not_run']='actual_native_profile_helper_prerequisite_unavailable; inspect native_helper_cases';return
    for method,path,data in routes:await request('route_positive_'+method+'_'+path,method,path,data)
    await request('unchanged_transport_ASGI_positive','POST','/onboarding/prepare',T)
    for label,s,auth in [('anonymous',None,True),('foreign_identity',other,True),('expired',expired,True),('auth_disabled',session,False)]:
        for method,path,data in routes:
            await request('refusal_'+label+'_'+method+'_'+path,method,path,data,403,s=s,auth=auth,expected_calls=0)
    # Bypass only donor wrapper to observe exact router require_admin dependency.
    for label,s,auth in [('anonymous',None,True),('foreign_identity',other,True),('expired',expired,True),('auth_disabled',session,False)]:
        await request('exact_router_auth_'+label,'POST','/onboarding/prepare',P,403,s=s,auth=auth,gate=False,expected_calls=0)
    await request('foreign_profile_native_request_guard','POST','/onboarding/prepare',P,403,query={'profile':'foreign'},expected_calls=0)
    policy['admin']['operators']=[{'provider':'fixture','user_id':'replacement','org_id':''}]
    await request('retained_identity_policy_revoked','POST','/onboarding/prepare',P,403,expected_calls=0)
    await request('retained_identity_revoked_exact_router','POST','/onboarding/prepare',P,403,gate=False,expected_calls=0)
    policy['admin']['operators']=[{'provider':'fixture','user_id':'owner','org_id':''}]
    for model,path,method in [('UserChange','/users','PUT'),('PairApproval','/pairing/approve','POST'),('TaskControl','/tasks/task1/control','POST'),
       ('SettingsChange','/settings','PUT'),('ScheduleChange','/schedules/job1/control','POST'),('OnboardingPrepare','/onboarding/prepare','POST'),
       ('OnboardingCredential','/onboarding/credentials','PUT'),('OnboardingActivate','/onboarding/activate','POST'),('WorkerPrepare','/onboarding/worker/prepare','POST'),('WorkerConfigure','/onboarding/worker/configure','POST')]:
        await request('ASGI_extra_'+model,method,path,valid[model]|{'unexpected':1},422,expected_calls=0)
        await request('ASGI_wrong_container_'+model,method,path,[],422,expected_calls=0)
    for name,data in [('uid_bool',P|{'uid':True}),('uid_string',P|{'uid':'1000'}),('uid_missing',{k:v for k,v in P.items() if k!='uid'}),
                      ('runtime_bad',P|{'runtime_profile':'../escape'}),('hash_bad',P|{'expected_config_sha256':'bad'}),
                      ('reference_empty',P|{'user_id':''}),('foreign_transport_uid',T|{'uid':1000})]:
        await request('ASGI_'+name,'POST','/onboarding/prepare',data,422,expected_calls=0)
    await request('ASGI_credential_name_bad','PUT','/onboarding/credentials',C|{'name':'invalid'},422,expected_calls=0)
    await request('ASGI_generation_bool','POST','/onboarding/activate',A|{'generation':True},422,expected_calls=0)
    await request('ASGI_profile_missing','POST','/onboarding/prepare',P,422,query={},expected_calls=0)
    await request('ASGI_query_limit_bad','GET','/conversations',None,422,query={'profile':'main','limit':201},expected_calls=0)
    await request('ASGI_query_offset_negative','GET','/conversations',None,422,query={'profile':'main','offset':-1},expected_calls=0)
    await request('ASGI_query_text_overlong','GET','/conversations',None,422,query={'profile':'main','query':'x'*513},expected_calls=0)
    await request('ASGI_attachment_index_type','GET','/attachments/task1/not-int',None,422,expected_calls=0)
    global behavior
    for failure,expected in [('permission',403),('transport',403),('reference',400),('key',400),('index',400),('unavailable',503)]:
        behavior=failure;await request('adapter_exception_map_'+failure,'POST','/onboarding/prepare',P,expected)
    for failure,expected in [('permission',403),('reference',400),('unavailable',400)]:
        behavior=failure
        await request('attachment_adapter_exception_'+failure,'GET','/attachments/task1/0',None,expected)
        await request('input_adapter_exception_'+failure,'GET','/inputs/task1/0',None,expected)
    behavior=None
try: asyncio.run(run())
except Exception as e:
    report['fatal']={'exception':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
finally:api._admin=original_admin;api.masked=original_masked
source=(CANDIDATE/'plugins/friday_rework/dashboard/api.py').read_text();tree=ast.parse(source)
report['exact_AST_inventory']=[{'name':n.name,'type':type(n).__name__,'line_start':n.lineno,'line_end':n.end_lineno,'source_sha256':hashlib.sha256(ast.get_source_segment(source,n).encode()).hexdigest()} for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]
report['frameworks']=[{'distribution':name,'version':importlib.metadata.version(name)} for name in ['pydantic','pydantic_core','fastapi','starlette','httpx','typing_extensions','anyio']]
report['interpreter']={'executable':sys.executable,'version':sys.version,'resolved':str(pathlib.Path(sys.executable).resolve()),'sha256':hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest()}
report['loaded_files']=[{'module':k,'path':str(pathlib.Path(v.__file__).resolve()),'sha256':hashlib.sha256(pathlib.Path(v.__file__).read_bytes()).hexdigest()} for k,v in list(sys.modules.items()) if getattr(v,'__file__',None) and pathlib.Path(v.__file__).is_file() and (pathlib.Path(v.__file__).resolve().is_relative_to(NATIVE) or pathlib.Path(v.__file__).resolve().is_relative_to(CANDIDATE) or '/site-packages/' in str(v.__file__))]
report['resources']={'affinity':list(os.sched_getaffinity(0)),'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'baseline_threads':baseline_threads,'final_threads':[t.name for t in threading.enumerate()],
                     'zero_retained_thread_drift':baseline_threads==[t.name for t in threading.enumerate()], 'children':pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split(),'whole_peak':'UNKNOWN'}
report['summary']={k:{'total':len(report[k]),'PASS':sum(c['status']=='PASS' for c in report[k]),'FAIL':sum(c['status']=='FAIL' for c in report[k])} for k in ['schema_cases','asgi_cases','native_helper_cases']}
with open(OUT/'FRAMEWORK-OBSERVATIONS.json','x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'summary':report['summary'],'fatal':report['fatal'],'resources':report['resources'],'audit_denials':events}))
if report['fatal'] or events or any(s['FAIL'] for s in report['summary'].values()) or not report['resources']['zero_retained_thread_drift']:sys.exit(1)
