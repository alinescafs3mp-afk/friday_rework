"""Author combined normal24+skills source wiring controls; no native imports, installation or runtime grant.

The exporter reads actual overlay files. Negative manifests are in-memory
mutations of those files, with no changes to the repository. Configuration
checks execute selected AST bodies and data only; native profile/dashboard/
platform validators are explicit inert boundaries, not configuration acceptance.
"""
import argparse, ast, builtins, copy, enum, hashlib, ipaddress, json, os
from pathlib import Path
import re, resource, runpy, time, types, __future__
from urllib.parse import urlsplit

parser=argparse.ArgumentParser(description=__doc__)
for name in ('repository','source','previous','output'):
    parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args(); rows=[]; pins={}; modules={'__future__':__future__}
S=types.SimpleNamespace

def read(path):
    data=path.read_bytes();pins[str(path)]=hashlib.sha256(data).hexdigest();return data

def check(name,body):
    body();rows.append({'name':name,'status':'PASS'})

def refused(call,reason):
    try:call()
    except Exception as exc:assert str(exc)==reason,(type(exc).__name__,str(exc),reason)
    else:raise AssertionError('Expected refusal '+reason)

exporter=runpy.run_path(str(args.repository/'scripts/hermes_prepare.py'))
read(args.repository/'scripts/hermes_prepare.py')
# Finite source parsing only; no archive/export or product execution is repeated.
budget=exporter['Budget'](time.monotonic()+60)
lock=json.loads(read(args.repository/'sources.lock.json'))
commit=next(r['commit'] for r in lock['repositories'] if r['id']=='hermes')
ordered=exporter['overlay_layers'](args.repository,commit,budget)
assert len(ordered)==25
check('actual_exporter_discovers_25_layers',lambda:None)
last='patches/hermes/user-skills.patch'
assert ordered[-1][0]==last
positions={name:i for i,(name,_) in enumerate(ordered)}
for name,layer in ordered:
    assert all(positions[parent]<positions[name] for parent in layer['requires'])
check('all_exact_dependencies_precede_consumers',lambda:None)
assert set(ordered[-1][1]['requires'])=={name for name,_ in ordered[:-1]}
check('all_24_prior_overlay_prerequisites_required',lambda:None)
old=json.loads(read(args.previous.with_name(args.previous.name+'.source.json')))
new=json.loads(read(args.source.with_name(args.source.name+'.source.json')))
assert new['layers'][:-1]==old['layers']
assert set(old['files'])<=set(new['files']) and len(new['files'])==17639
assert set(new['files'])-set(old['files'])=={'hermes_cli/friday_skill_io.py','hermes_cli/friday_prompt_scope.py','hermes_cli/skill_lock.py'}
check('original_24_layers_and_all_17636_files_retained',lambda:None)
manifest=json.loads(read(args.repository/'patches/hermes/user-skills-manifest.json'))
expected={row['path'] for row in manifest['files']}
changed={rel for rel in new['files'] if new['files'][rel]!=old['files'].get(rel)}
assert changed==expected
for row in manifest['files']:
    data=read(args.source/row['path']);assert hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']
    if row.get('new_file'):assert row['path'] not in old['files']
    else:assert old['files'][row['path']]['sha256']==row['before_sha256']
    ast.parse(data)
check('exact_29_skills_files_no_unrelated_file_delta',lambda:None)
assert new['commit']==old['commit']==commit and new['base_tree']==old['base_tree']
assert new['source_file_count']==old['source_file_count']==17590
assert not new['dependencies_installed'] and not new['services_started']
check('ordinary_donor_identity_and_preparation_only_status',lambda:None)

original_read=exporter['overlay_layers'].__globals__['read_json']
manifest_rel='patches/hermes/user-skills-manifest.json'

def negative(name,reason,mutator,rel=manifest_rel):
    def exercise():
        def changed_read(path):
            value,digest=original_read(path)
            if str(path.relative_to(args.repository))==rel:
                value=copy.deepcopy(value);mutator(value)
            return value,digest
        globals_=exporter['overlay_layers'].__globals__
        globals_['read_json']=changed_read
        try:refused(lambda:exporter['overlay_layers'](args.repository,commit,budget),reason)
        finally:globals_['read_json']=original_read
    check(name,exercise)
negative('base_mismatch_refused','overlay_base_mismatch',lambda v:v.update(base_commit='0'*40))
negative('patch_hash_mismatch_refused','overlay_hash_mismatch',lambda v:v.update(patch_sha256='0'*64))
negative('prerequisite_hash_mismatch_refused','overlay_prerequisite_mismatch',lambda v:v['prerequisites'].update({'patches/hermes/native-delegation-repair.patch':'0'*64}))
negative('missing_dependency_refused','overlay_prerequisite_mismatch',lambda v:v['prerequisites'].update({'patches/hermes/absent.patch':'0'*64}))
negative('dependency_cycle_refused','overlay_dependency_cycle',lambda v:v['prerequisites'].update({last:manifest['patch_sha256']}),rel='patches/hermes/native-delegation-manifest.json')
negative('patch_file_inventory_mismatch_refused','overlay_file_inventory_mismatch',lambda v:v['files'].pop())

# Compile only explicitly selected definitions. No donor module initializer or
# native import is executed; all relative imports stay inside this fixture map.
def importer(name,globals=None,locals=None,fromlist=(),level=0):
    assert name in modules,('forbidden native import',name,level)
    return modules[name]

def selected(path,name,env):
    node=next(n for n in ast.parse(read(path)).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name==name)
    env['__builtins__']={**vars(builtins),'__import__':importer}
    body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),copy.deepcopy(node)]
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(path),'exec'),env)
    return env[name]

# Evaluate the pure configuration data assignments and their _aux helper only.
default_tree=ast.parse(read(args.source/'hermes_cli/config_defaults.py'))
nodes=[]
for node in default_tree.body:
    if isinstance(node,ast.FunctionDef) and node.name=='_aux':nodes.append(copy.deepcopy(node))
    if isinstance(node,ast.Assign):
        nodes.append(copy.deepcopy(node))
        if any(isinstance(t,ast.Name) and t.id=='DEFAULT_CONFIG' for t in node.targets):break
values={'__builtins__':{**vars(builtins),'__import__':importer}}
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'default-config-data','exec'),values)
defaults=values['DEFAULT_CONFIG']; before=copy.deepcopy(defaults)
node=next(n for n in ast.parse(read(args.source/'hermes_cli/friday_user_scope.py')).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SAFE' for t in n.targets))
scope=S(SAFE=frozenset(ast.literal_eval(node.value.args[0])))
assert {'delegate_task','skills_list','skill_view','skill_manage'}<=scope.SAFE
web_env={'Path':Path,'__file__':str(args.repository/'tools/web_profile.py'),'HERMES_PROFILES':('disabled','exa-paid','exa-keyless')}
for name in ['_profile','_bound','research_policy','hermes_web_config']:
    selected(args.repository/'tools/web_profile.py',name,web_env)
local_env={'hermes_web_config':web_env['hermes_web_config'],'research_policy':web_env['research_policy'],'re':re,'ipaddress':ipaddress,'urlsplit':urlsplit}
build=selected(args.repository/'tools/configure_local_test.py','build_config',local_env)
class Platform(enum.Enum):TELEGRAM='telegram';LOCAL='local'
modules['gateway.config']=S(Platform=Platform,PLATFORM_TOKEN_ENV_NAMES={Platform.TELEGRAM:'FIXTURE_BOT_TOKEN'})
modules['gateway.config_env']=S(_ENV_ENABLE_CREDENTIALS={Platform.TELEGRAM:[]})
modules['hermes_cli.friday_product_access']=S(profile_name=lambda x:x)
modules['hermes_cli']=S(friday_user_scope=scope)
modules['hermes_cli.config']=S(DEFAULT_CONFIG=defaults,validate_env_var_name_for_write=lambda name:None if re.fullmatch('[A-Z][A-Z0-9_]*',name) else (_ for _ in ()).throw(ValueError('fixture_ref_name')))
runtime_env={};configured=selected(args.repository/'plugins/friday_rework/host_runtime.py','configured_runtimes',runtime_env)
join_env={'configured_runtimes':configured,'copy':copy}
for name in ['installation_inputs','validate_installation_inputs']:
    selected(args.repository/'plugins/friday_rework/user_worker_join.py',name,join_env)
modules['plugins.friday_rework.user_worker_join']=S(installation_inputs=join_env['installation_inputs'])
modules['user_worker_join']=S(validate_installation_inputs=join_env['validate_installation_inputs'])
onboard_env={'copy':copy,'scope':scope,'re':re,'ipaddress':ipaddress,'urlsplit':urlsplit,'RESOURCE':args.repository/'plugins/friday_rework'}
for name in ['_local','validate_template']:
    selected(args.repository/'plugins/friday_rework/onboarding.py',name,onboard_env)
modules['plugins.friday_rework.onboarding']=S(validate_template=onboard_env['validate_template'])
renderer_env={'copy':copy,'hashlib':hashlib,'ROOT':args.repository,'build_config':build,'hermes_web_config':web_env['hermes_web_config'],'research_policy':web_env['research_policy'],
    'INFERENCE':frozenset({'base_url','model','key_env','context','max_input','main_output','summary_output','margin','template_overhead'}),
    'AUTH_NAMES':('HERMES_DASHBOARD_BASIC_AUTH_USERNAME','HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH','HERMES_DASHBOARD_BASIC_AUTH_SECRET'),
    
    '_dashboard':lambda value:copy.deepcopy(value)}
renderer_tree=ast.parse(read(args.repository/'tools/configure_product.py'))
for constant in ('NORMAL_TOOLSETS','USER_TOOLSETS'):
    assignment=next(n for n in renderer_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==constant for t in n.targets))
    renderer_env[constant]=ast.literal_eval(assignment.value)
assert {'skills','delegation'}<=set(renderer_env['USER_TOOLSETS'])
check('renderer_toolsets_loaded_from_actual_module_constants',lambda:None)
for name in ['_exact','_text','compose_product']:
    selected(args.repository/'tools/configure_product.py',name,renderer_env)
inputs=selected(args.repository/'tests/test_product_profile.py','inputs',{})
for profile in ['exa-paid','exa-keyless']:
    spec=inputs();spec['web']['profile']=profile
    result=renderer_env['compose_product'](spec)
    cfg=result['config'];template=cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']
    assert {'delegate_task','skills_list','skill_view','skill_manage'}<=set(template['tools'])
    assert {'delegation','skills'}<=set(template['config']['toolsets'])
    assert template['config']['skills']['create_dir'] is None
    assert template['config']['skills']['external_dirs']==[] and template['config']['skills']['auto_load']==[]
    assert template['config']['skills']['trusted_project_dirs']==[] and template['config']['skills']['project_discovery'] is False
    assert all({'delegation','skills'}<=set(v) for v in template['config']['platform_toolsets'].values())
    assert cfg['memory']==defaults['memory'] and cfg['skills']==defaults['skills'] and cfg['tools']==defaults['tools'] and cfg['approvals']==defaults['approvals']
    assert cfg['delegation']['base_url']==cfg['model']['base_url'] and cfg['delegation']['fallback_providers']==[]
    assert cfg['delegation']['key_env']==spec['inference']['key_env'] and 'api_key' not in cfg['delegation']
    assert cfg['fallback_providers']==[] and cfg['fallback_model']=={} and cfg['web']['keyless_rescue'] is False
    assert cfg['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}
    assert not result['contract']['ready'] and result['contract']['state']=='TEMPLATE_INCOMPLETE'
    check('actual_selected_renderer_skills_'+profile+'_delegation_capabilities_and_unready_profile',lambda:None)
assert defaults==before
check('native_defaults_not_mutated_by_rendering',lambda:None)
saved=scope.SAFE;scope.SAFE=saved-{'delegate_task'}
try:refused(lambda:renderer_env['compose_product'](inputs()),'scoped_native_delegation_required')
finally:scope.SAFE=saved
check('actual_renderer_refuses_old_scope_without_delegation',lambda:None)
for missing_skill in ('skills_list','skill_view','skill_manage'):
    scope.SAFE=saved-{missing_skill}
    try:refused(lambda:renderer_env['compose_product'](inputs()),'scoped_native_skills_required')
    finally:scope.SAFE=saved
    check('actual_renderer_refuses_scope_without_'+missing_skill,lambda:None)
temporary=build(**inputs()['inference'])
assert temporary['memory']['memory_enabled'] is False and temporary['toolsets']==[]
assert temporary['agent']['api_max_retries']==1 and temporary['auxiliary']['title_generation']['enabled'] is False
check('actual_temporary_local_test_profile_remains_distinct',lambda:None)
result={'kind':'AUTHOR_SOURCE_ONLY','passed':len(rows),'failed':0,'checks':rows,'pins':pins,
    'configuration_validation':'selected AST renderer; inert profile/dashboard/platform boundaries, NOT native acceptance',
    'native_imports':False,'workers_threads':False,'installed_home':False,'grant':False,'network':False,
    'independent_review':False,'runtime_acceptance':False,'affinity':sorted(os.sched_getaffinity(0)),
    'as_limit':resource.getrlimit(resource.RLIMIT_AS)}
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'AUTHOR_SOURCE_PASS':len(rows),'runtime':'NOT_RUN'}))
