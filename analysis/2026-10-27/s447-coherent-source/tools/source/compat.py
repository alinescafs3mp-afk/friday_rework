# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""One exact S447 source-only descendant; no admission or effects on import.

Original S443 proofs are checked against the authenticated child's beforeimages.
Current source, native custody, rights and owner CAS remain separate consumers.
"""
from pathlib import Path
import copy, hashlib, json, os, stat
ROOT = Path('<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source')
OLD = Path('<PRIVATE_CACHE>/PRIVATE_REF_174e7fdd15606bc8')
H = Path('<INSTALL_HOME>')
FAMILY = Path('<PRIVATE_CACHE>/PRIVATE_REF_676e9e61460bba13/source-runtime')
ACCEPTANCE = Path('<PRIVATE_CACHE>/PRIVATE_REF_821a1c9ac7aeebf2/ROOT-INSTALLED-SOURCE-ACCEPTED.json')
PRODUCER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/producer.py', 'sha256': 'PRIVATE_REF_0aa93e04fba6c1ea'}
OLD_EDGE = {'path':str(OLD/'native-graph/continuity_edge.py'),'sha256':'PRIVATE_REF_8d1ac39416398d28'}
ORIGINAL_ACCEPTANCE = {'path':'<PRIVATE_CACHE>/PRIVATE_REF_2109b1c62178c068/ROOT-INSTALLED-SOURCE-ACCEPTED.json','sha256':'PRIVATE_REF_878c26d4559ddc22'}
BASE = {'user_worker_join.py': {'path':str(OLD/'publication/source-runtime/source/plugins/friday_rework/user_worker_join.py'),'sha256':'PRIVATE_REF_105ecd2efd67b4a2'}, 'worker_provision.py':{'path':str(OLD/'publication/source-runtime/source/plugins/friday_rework/worker_provision.py'),'sha256':'PRIVATE_REF_cda4de0e0c0c96b7'}}
S445 = {'host.py':'PRIVATE_REF_5387ea485b34f915','associations.py':'PRIVATE_REF_48953e694087357c','results.py':'PRIVATE_REF_3a7231760c034114','result_tool.py':'PRIVATE_REF_3366d3c004b8c8d6'}
OLD_NATIVE = {'path':str(OLD/'native-graph/verify_native.py'),'sha256':'PRIVATE_REF_5ac5356545db0451'}
OLD_BRIDGE = {'path':str(OLD/'bridge/verify480.py'),'sha256':'PRIVATE_REF_e7a70461681f57af'}
META=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
def need(ok,code):
    if not ok: raise ValueError(code)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def raw(path):
    p=Path(path);need(p.is_absolute() and p.resolve()==p,'s447_canonical_reference')
    for parent in p.parents:
        s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,os.getuid()) and not s.st_mode&0o022,'s447_protected_parent')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_gid==os.getgid() and before.st_nlink==1 and stat.S_IMODE(before.st_mode) in (0o400,0o600),'s447_private_reference')
        with os.fdopen(os.dup(fd),'rb') as f: data=f.read(32*1024**2+1)
        after=os.fstat(fd);named=p.lstat();need(len(data)<=32*1024**2 and all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in META),'s447_reference_changed');return data
    finally:os.close(fd)
def pin(path):return {'path':str(path),'sha256':sha(raw(path))}
def read(ref):
    need(type(ref) is dict and set(ref)=={'path','sha256'},'s447_exact_reference');data=raw(ref['path']);need(sha(data)==ref['sha256'],'s447_hash_changed');return data
def unique(rows):
    result={}
    for key,value in rows:
        need(key not in result,'s447_duplicate_json_key');result[key]=value
    return result
def parse(data):return json.loads(data,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('s447_nonfinite_json')))
def document(ref):return parse(read(ref))
def module(ref,name):
    ns={'__file__':ref['path'],'__name__':name};exec(compile(read(ref),ref['path'],'exec'),ns);return ns

# Exact reviewed templates are pinned before consumer ref substitution; no digest cycle.
COLD_TEMPLATES = {'a0_bootstrap.py': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/cold/a0_bootstrap.py', 'sha256': 'PRIVATE_REF_52c367ca4c425847'}, 'user_worker_join.py': {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/cold/user_worker_join.template.py', 'sha256': 'PRIVATE_REF_8675644faf2afc89'}}
PREVIOUS_COMPAT = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_b69528d682030fc1/readiness/compat.py', 'sha256': 'PRIVATE_REF_f604387167f54ebf'}
PREVIOUS_NATIVE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_b69528d682030fc1/readiness/verify_native.py', 'sha256': 'PRIVATE_REF_10351b481a4df8ea'}
PREVIOUS_BRIDGE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_b69528d682030fc1/readiness/verify480.py', 'sha256': 'PRIVATE_REF_af2a59fb3d410882'}
def replace_one(text, before, after, code):
    need(text.count(before)==1,code)
    return text.replace(before,after)

def expected_consumers():
    native=pin(ROOT/'verify_native.py');bridge=pin(ROOT/'verify480.py');own=pin(Path(__file__))
    need(set(COLD_TEMPLATES)=={'user_worker_join.py','a0_bootstrap.py'},'s447_exact_cold_templates')
    # Read exact accepted merged source; only the three pinned module refs change.
    joined=read(COLD_TEMPLATES['user_worker_join.py']).decode()
    joined=replace_one(joined,repr(PREVIOUS_NATIVE),repr(native),'s447_one_native_verifier_ref')
    joined=replace_one(joined,repr(PREVIOUS_BRIDGE),repr(bridge),'s447_one_bridge_ref')
    joined=replace_one(joined,repr(PREVIOUS_COMPAT),repr(own),'s447_one_compat_ref')
    provision=read(BASE['worker_provision.py']).decode()
    provision=replace_one(provision,repr(OLD_BRIDGE),repr(bridge),'s447_one_provision_bridge_ref')
    return {'user_worker_join.py':joined.encode(), 'worker_provision.py':provision.encode(),
            'a0_bootstrap.py':read(COLD_TEMPLATES['a0_bootstrap.py'])}


def source_proof():
    producer=module(PRODUCER,'_s447_exact_source92_producer')
    package_ref=pin(FAMILY/'PACKAGE.json');package=document(package_ref)
    request_ref=pin(FAMILY/'bound/REQUEST.json')
    tx=H/'preparation'/('ordinary-source-update-'+package['previous_input']['sha256'])
    proof=producer['verify_successor'](package_ref,request_ref,pin(tx/'committed.json'))
    need(proof['previous_input']==document(ORIGINAL_ACCEPTANCE)['current_input'],'s447_exact_source_ancestor')
    expected=expected_consumers();changed={str(Path(r['path']).relative_to(H)):r['sha256'] for r in proof['changed_plugin_files']}
    wanted={'plugins/friday_rework/'+n:h for n,h in S445.items()}
    wanted.update({'plugins/friday_rework/'+n:sha(data) for n,data in expected.items()})
    need(changed==wanted,'s447_only_exact_seven_existing_consumers')
    need(all(raw(H/'plugins/friday_rework'/n)==data for n,data in expected.items()),'s447_existing_consumer_delta_changed')
    return proof,tx

def projected_edge():
    proof,tx=source_proof();edge=module(OLD_EDGE,'_s447_retained_s443_edge');original_raw=edge['raw']
    names=[str(Path(r['path']).relative_to(H)) for r in proof['changed_plugin_files']]+['FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json']
    projections={str(H/name):tx/'before'/name for name in names}
    def retained_raw(path):return original_raw(projections.get(str(path),path))
    edge['raw']=retained_raw
    return edge,proof,tx

def original_source480(acceptance_ref):
    need(acceptance_ref==ORIGINAL_ACCEPTANCE,'s447_native480_original_source_anchor')
    edge,proof,tx=projected_edge();return edge['verify_source480'](edge['pin'](edge['PACKAGE']),acceptance_ref)

def continuity(staged,current,request_ref,receipt_ref):
    edge,proof,tx=projected_edge();before=parse(edge['raw'](H/'FRIDAY-INSTALL.json'))
    old=edge['verify'](staged,before,request_ref,receipt_ref)
    need(current==parse(raw(H/'FRIDAY-INSTALL.json')),'s447_actual_marker_changed')
    result=dict(old,package=proof['package'],request=proof['request'],commit=proof['commit'],current_input=proof['current_input'],current_marker=proof['current_marker'])
    result['source_only_predecessor']=old
    return result

def current_native_source(old):
    proof,tx=source_proof();result=dict(old)
    result.update({k:proof[k] for k in ('package','request','commit','current_input','current_marker') if k not in ('request',)})
    result['source_marker']=proof['current_marker']
    result['original_source480_anchor']={'current_input':old['current_input'],'current_marker':old['current_marker'],'source_acceptance':old['source_acceptance']}
    if os.path.lexists(ACCEPTANCE):
        accepted_ref=pin(ACCEPTANCE);accepted=document(accepted_ref)
        need(accepted.get('accepted') is True and accepted.get('accepted_source_only') is True and accepted.get('runtime_or_user_semantics_accepted') is False and all(accepted[k]==proof[v] for k,v in (('current_input','current_input'),('committed','commit'),('marker','current_marker'),('plan','plan'),('source_receipt','source_receipt'))),'s447_actual_successor_acceptance_join')
        result['source_acceptance']=accepted_ref
    else:result['source_acceptance']=None
    return result

def retained_a0_observation(c,value,actual):
    """Only a previously published identical observation; new probes use actual pins."""
    proof,tx=source_proof();sidecar=Path(c['runtime_home'])/'workers/a0/postboot-revalidation.json'
    need(sidecar==H/'profiles/telegram-bot-9000000001/workers/a0/postboot-revalidation.json','s447_exact_retained_observation_path')
    need(document(pin(sidecar))==value,'s447_retained_observation_changed')
    expected=copy.deepcopy(actual)
    retained=dict(BASE)
    retained['a0_bootstrap.py']={'path':str(OLD/'publication/source-runtime/source/plugins/friday_rework/a0_bootstrap.py'),'sha256':'PRIVATE_REF_fbf8ffa5d8d216aa'}
    for name,ref in retained.items():
        relative='plugins/friday_rework/'+name
        need(expected[relative]==pin(H/relative),'s447_a0_current_consumer_source_changed')
        need(sha(raw(tx/'before'/relative))==ref['sha256'],'s447_a0_retained_source_changed')
        expected[relative]={'path':str(H/relative),'sha256':ref['sha256']}
    need(value['sources']==expected,'s447_only_exact_retained_observation_sources')
    return True

def retained_a0_producer(c,value,original):
    retained_a0_observation(c,value,source_pins_for_observation())
    need(original['producer']==value['sources']['plugins/friday_rework/user_worker_join.py'],'s447_retained_cold_producer_changed')
    return True

def source_pins_for_observation():
    marker=document(pin(H/'FRIDAY-INSTALL.json'));result={}
    # Exact unchanged existing observer input inventory, independent of runtime imports.
    names=('user_worker_join.py','host_runtime.py','runtime_observers.py','worker_provision.py',
        'a0_bootstrap.py','host_record.py','runtime_process.py','runtime_primitives.py',
        'adapters/a0.py','adapters/a0_native.py','adapters/a0_config.py',
        'adapters/a0_profile.py','adapters/a0_web.py')
    for name in names:
        relative='plugins/friday_rework/'+name;reference={'path':str(H/relative),'sha256':marker['plugin_files'][relative]}
        read(reference);result[relative]=reference
    return result


def current_observation_sources(value):
    """Actual current source gate, usable before any postboot sidecar exists."""
    proof,tx=source_proof()
    need(value['sources']==source_pins_for_observation(),'s447_current_observer_sources_changed')
    return proof
