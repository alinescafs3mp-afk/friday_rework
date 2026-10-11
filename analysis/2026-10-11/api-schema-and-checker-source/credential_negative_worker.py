"""Changed-boundary negative probes; no repeat of unchanged broad suite."""
import sys
assert sys.stdin.readline()=='execute\n'
import ast, pathlib, json, asyncio, importlib.util, importlib.metadata, hashlib, traceback, threading, os, resource, copy, time, urllib.parse
OUT=pathlib.Path(__file__).resolve().parent
# Reuse exact recorded harness setup only, selecting nodes by source names.
# This projection is of OUR harness; production API is still imported in full.
source=(OUT/'framework_worker.py').read_text();tree=ast.parse(source)
selected=[]
stop_line=next(n.lineno for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='run')
for n in tree.body:
    if n.lineno>=stop_line:break
    if isinstance(n,ast.Assert) or isinstance(n,(ast.For,ast.If)):continue
    if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id in {'schema_case'}:continue
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'policy_ready'} for t in n.targets):continue
    selected.append(n)
ns={'__file__':str(OUT/'credential_negative_worker.py'),'__name__':'credential_negative_worker'}
exec(compile(ast.Module(selected,type_ignores=[]),str(OUT/'framework_worker.py'), 'exec'),ns)
api=ns['api']; native=ns['native']; app=ns['app']; Session=ns['Session']; request=ns['request']; report=ns['report']; calls=ns['calls']
marker='INERT_FRIDAY_CREDENTIAL_REFLECTION_20261011'
class MarkerBackend:
    def __getattr__(self,name):
        def invoke(*args,**kwargs):
            calls.append({'method':name,'inert_exception_probe':True})
            kind=ns['behavior']
            if kind=='permission':raise PermissionError(marker)
            if kind=='reference':raise ValueError(marker)
            if kind=='unavailable':raise RuntimeError(marker)
            raise AssertionError('backend_unexpectedly_reached:'+marker)
        return invoke
api._admin=MarkerBackend()
async def run():
    C=ns['C']
    cases=[('credential_invalid_value_dict',C|{'value':{'nested':marker}}),
           ('credential_invalid_value_list',C|{'value':[marker]}),
           ('credential_forbidden_extra',C|{'extra_secret':marker}),
           ('credential_missing_name',{k:v for k,v in (C|{'value':marker}).items() if k!='name'}),
           ('credential_missing_generation',{k:v for k,v in (C|{'value':marker}).items() if k!='generation'}),
           ('credential_bad_name',C|{'name':'invalid','value':marker}),
           ('credential_secret_field_name',C|{marker:'inert'}),
           ('credential_wrong_top_level',[C|{'value':marker}])]
    for name,data in cases:
        row=await request(name,'PUT','/onboarding/credentials',data,422,expected_calls=0)
        row['inert_marker_reflected_in_422']=marker in row['body']
        if row['inert_marker_reflected_in_422'] or row['body'] != '{"detail":"invalid_product_request"}':row['status']='FAIL'
        row['claim']='synthetic marker reflected or suppressed; no production secrets used'
    await request('anonymous_bad_credential_refuses_before_validation','PUT','/onboarding/credentials',C|{'value':{'nested':marker}},403,s=None,expected_calls=0)
    for kind,status in [('permission',403),('reference',400),('unavailable',503)]:
        ns['behavior']=kind
        row=await request('backend_exception_marker_'+kind,'PUT','/onboarding/credentials',C,status)
        row['inert_marker_in_response']=marker in row['body']
        if row['inert_marker_in_response']:row['status']='FAIL'
try:asyncio.run(run())
except Exception as e:report['fatal']={'exception':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
report['resources']={'affinity':list(os.sched_getaffinity(0)),'RLIMIT_AS':resource.getrlimit(resource.RLIMIT_AS),'threads':[t.name for t in threading.enumerate()],
                     'children':pathlib.Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split(),'whole_peak':'UNKNOWN'}
report['harness_projection']={'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'selected_setup_node_lines':[n.lineno for n in selected],'production_api_full_module':True}
report['defect_observations']=[row['name'] for row in report['asgi_cases'] if row.get('inert_marker_reflected_in_422')]
with open(OUT/'CREDENTIAL-NEGATIVE-OBSERVATIONS.json','x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'cases':len(report['asgi_cases']),'failures':[r['name'] for r in report['asgi_cases'] if r['status']!='PASS'],'inert_marker_reflection_cases':report['defect_observations'],'fatal':report['fatal'],'resources':report['resources']}))
if report['fatal'] or any(r['status']!='PASS' for r in report['asgi_cases']):sys.exit(1)
