# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never use as an installed module.
# Source/export correspondence is structural only after declared substitutions.
def qualified_runtime600(config,value=None):
    need(type(config)is dict and type(config.get('budget_seconds'))is int,'route720_integer_runtime_budget')
    if config['budget_seconds']==600:return copy.deepcopy(config)
    need(config['budget_seconds']==720,'route720_exact_future_budget')
    qualified=document(QUALIFIED_A0)
    need(value is None or value==qualified,'route720_exact_saved_canonical_value')
    need(qualified['schema']=='friday.a0-postboot-revalidation.v1' and qualified['runtime_sha256']==QUALIFIED_RUNTIME_SHA
         and qualified['original_attempt']['budget_seconds']==600 and qualified['effects']=='OBSERVATION_ONLY'
         and qualified['per_job_authority']=='NOT_GRANTED','route720_saved_qualification_required')
    need(config.get('runtime_home')==str(H/'profiles/UNBOUND_PROFILE') and config.get('runtime_profile')=='UNBOUND_PROFILE','route720_exact_current_target')
    expected={'runtime':{'path':str(H/'worker-runtime-source/scripts/a0_runtime.py'),'sha256':'UNBOUND_NATIVE_RUNTIME_SHA'},
              'launcher':{'path':'UNBOUND_LAUNCHER_PATH','sha256':'UNBOUND_NATIVE_LAUNCHER_SHA'},
              'daemon_unit':{'path':'UNBOUND_UNIT_PATH','sha256':'UNBOUND_NATIVE_UNIT_SHA'}}
    need(type(config.get('a0'))is dict and all(config['a0'].get(k)==v for k,v in expected.items()),'route720_exact_native480_tuple')
    shadow=copy.deepcopy(config);shadow['budget_seconds']=600
    runtime={k:v for k,v in shadow.items()if k!='runtime_receipt'}
    need(sha(json.dumps(runtime,sort_keys=True,ensure_ascii=False,allow_nan=False).encode())==QUALIFIED_RUNTIME_SHA,'route720_only_budget_changed_from_qualified600')
    return shadow

def future_runtime720(config):
    need(type(config)is dict and type(config.get('budget_seconds'))is int and config['budget_seconds']in(600,720),'route720_exact_before_or_future_budget')
    future=copy.deepcopy(config);future['budget_seconds']=720
    qualified_runtime600(future)
    return future

