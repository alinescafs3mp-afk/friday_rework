#!/usr/bin/env python3
# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""S447 inert, finite Source92 successor producer and read-only verifier.

No installed import, service, canonical store, model, native updater or user IO.
Root supplies real then-current baseline facts and its separate original clock.
Exact S445 bytes stay immutable; three explicit reviewed compatibility files
may accompany them. Unknown baseline source drift refuses, never reverts.
"""
from __future__ import annotations
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

HERE = Path(__file__).resolve().parent
TEMPLATE = {'path': str(HERE/'source92_template.py'), 'sha256': 'PRIVATE_REF_caf1fb1dab410e10'}
ORIGIN_ACCEPTANCE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_2109b1c62178c068/ROOT-INSTALLED-SOURCE-ACCEPTED.json', 'sha256': 'PRIVATE_REF_878c26d4559ddc22'}
ORIGIN_PACKAGE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_174e7fdd15606bc8/publication/source-runtime/PACKAGE.json', 'sha256': 'PRIVATE_REF_5a17b67cf43b7c18'}
S445_BUNDLE = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_a706e46e4c70a975/SOURCE-BUNDLE.json', 'sha256': 'PRIVATE_REF_1dcaa788df6000ed'}
HOME = Path('<INSTALL_HOME>')
EXTRAS = frozenset({'plugins/friday_rework/user_worker_join.py', 'plugins/friday_rework/worker_provision.py', 'plugins/friday_rework/a0_bootstrap.py'})
META_NAMES = ('FRIDAY-INSTALL.json','hermes-agent.source.json','hermes-agent/install-stamp.json')

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def strict_json(raw):
    def pairs(rows):
        result={}
        for key,value in rows:
            need(key not in result,'duplicate_json_key_refused')
            result[key]=value
        return result
    def constant(_value):
        raise RuntimeError('nonfinite_json_constant_refused')
    return getattr(json,'loads')(raw,object_pairs_hook=pairs,parse_constant=constant)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2)+'\n').encode()

def read(ref):
    """Protected owned refs, including historical 0664 under protected parents."""
    need(type(ref) is dict and set(ref)=={'path','sha256'} and type(ref['path']) is str
         and type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']), 'exact_ref_required')
    p=Path(ref['path'])
    need(p.is_absolute() and p.parent.resolve()==p.parent, 'canonical_ref_parent_required')
    for parent in p.parents:
        st=parent.lstat()
        need(stat.S_ISDIR(st.st_mode) and st.st_uid in (0,os.getuid())
             and not st.st_mode & 0o022, 'protected_ref_parent_required')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_gid==os.getgid()
             and a.st_nlink==1 and not a.st_mode & 0o002, 'owned_single_link_ref_required')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(64*1024**2+1)
        b,c=os.fstat(fd),p.lstat()
        fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(len(raw)<=64*1024**2 and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in fields), 'ref_identity_changed')
        need(digest(raw)==ref['sha256'], 'ref_digest_changed')
        return raw
    finally:os.close(fd)

def pin(p):
    p=Path(p)
    # Only callers' own output or an explicit already protected ref is pinned.
    return {'path':str(p),'sha256':digest(p.read_bytes())}

def put(p,raw):
    p=Path(p)
    missing=[];parent=p.parent
    while not parent.exists():missing.append(parent);parent=parent.parent
    need(parent.resolve()==parent,'output_parent_link')
    for d in reversed(missing):d.mkdir(mode=0o700)
    need(p.parent.resolve()==p.parent,'output_parent_link')
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        os.fchmod(f.fileno(),0o600);f.write(raw);f.flush();os.fsync(f.fileno())
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return pin(p)

def literal(value):
    if isinstance(value,Path):return 'Path('+repr(str(value))+')'
    if isinstance(value,frozenset):return 'frozenset('+literal(sorted(value))+')'
    if type(value) is dict:return '{'+', '.join(literal(k)+': '+literal(value[k]) for k in sorted(value))+'}'
    if type(value) is list:return '['+', '.join(literal(v) for v in value)+']'
    return repr(value)

def assignment(text,name,value):
    nodes=[n for n in ast.parse(text).body if isinstance(n,ast.Assign)
           and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    need(len(nodes)==1,'one_assignment_'+name)
    n=nodes[0];lines=text.splitlines(True)
    lines[n.lineno-1:n.end_lineno]=[name+' = '+literal(value)+'\n']
    return ''.join(lines)

def function(text,name,new):
    nodes=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name]
    need(len(nodes)==1,'one_function_'+name)
    n=nodes[0];lines=text.splitlines(True);lines[n.lineno-1:n.end_lineno]=[new+'\n']
    return ''.join(lines)

def selected(binding):
    bundle=strict_json(read(S445_BUNDLE))
    fixed={n:{k:v for k,v in row['after'].items() if k in ('path','sha256')} for n,row in bundle['files'].items()}
    extras=binding.get('extra_sources',{})
    need(type(extras) is dict and set(extras)==EXTRAS, 'exact_three_explicit_compatibility_modules_required')
    need(not extras or binding.get('extra_sources_accepted_by_Root') is True, 'explicit_Root_extra_acceptance_required')
    need(len(fixed)==4 and len(extras)==3 and not set(fixed)&set(extras), 'exact_seven_existing_source_scope_required')
    return dict(fixed,**extras)

def baseline_static(binding):
    """Only immutable refs; safe before or after the intended source update."""
    need(binding.get('schema')=='frw.S447.root-source-binding.v1', 'exact_binding_schema_required')
    need(binding.get('home')==str(HOME), 'exact_existing_home_required')
    origin=strict_json(read(ORIGIN_ACCEPTANCE));family=strict_json(read(ORIGIN_PACKAGE))
    need(origin['accepted'] is True and origin['accepted_source_only'] is True, 'accepted_origin_required')
    previous=binding['previous_input'];raw=read(previous)
    need(previous['sha256']==origin['current_input']['sha256'] and raw==read(origin['current_input']), 'unknown_source_drift_refuse_not_revert')
    current=strict_json(raw)
    need(len(current['project_files'])==328 and sum(n.startswith('plugins/friday_rework/') for n in current['project_files'])==47, 'exact_328_project_47_plugin_inventory_required')
    need(family['current_input']==origin['current_input'], 'origin_package_join_changed')
    accepted=strict_json(read(binding['current_acceptance']))
    need(accepted.get('accepted') is True and accepted.get('accepted_source_only') is True
         and accepted['current_input']['sha256']==previous['sha256']
         and read(accepted['current_input'])==raw
         and accepted['marker']==binding['metadata']['FRIDAY-INSTALL.json']
         and accepted['source_receipt']==binding['metadata']['hermes-agent.source.json']
         and accepted['committed']==binding['source_committed']==origin['committed'], 'actual_current_accepted_source_join_required')
    commit=strict_json(read(binding['source_committed']));plan=strict_json(read(commit['plan']))
    request=strict_json(read(binding['source_request']))
    need(origin['plan']==commit['plan'] and plan['request']==binding['source_request']
         and commit['state']=='SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
         and commit['current_input']==origin['current_input']
         and request['current_input']==origin['current_input'], 'accepted_source_request_commit_join_changed')
    need(set(binding['metadata'])==set(META_NAMES), 'exact_baseline_metadata_required')
    for name,ref in binding['metadata'].items():
        need(ref['path']==str(HOME/name), 'exact_installed_metadata_path_required')
    need(binding['metadata']['hermes-agent.source.json']==origin['source_receipt']
         and binding['metadata']['hermes-agent/install-stamp.json']['sha256']==family['retained_stamp']['sha256'], 'retained_native_metadata_required')
    source=Path(binding['previous_source'])
    need(source.is_absolute() and source.resolve()==source, 'canonical_previous_source_required')
    need(Path(binding['output']).is_absolute() and Path(binding['output']).parent.resolve()==Path(binding['output']).parent, 'canonical_output_required')
    seconds=binding['maintenance_seconds']
    need(type(seconds) is int and 30<=seconds<=180, 'bounded_integer_maintenance_seconds_required')
    files=selected(binding);bundle=strict_json(read(S445_BUNDLE))
    for name,row in bundle['files'].items():
        need(current['project_files'][name]==row['before']['sha256'], 'S445_exact_four_preimages_required')
    for name,ref in files.items():
        need(name in current['project_files'] and ref['sha256']!=current['project_files'][name], 'exact_existing_changed_source_required')
        raw=read(ref)
        if name.endswith('.py'):ast.parse(raw)
    return current,files

BASELINE_FUNCTION = '''def accepted_baseline():
    acceptance = strict_json(pinned(ACCEPTANCE))
    original = strict_json(pinned(ORIGIN_ACCEPTANCE))
    require(acceptance.get('accepted') is True and acceptance.get('accepted_source_only') is True
            and acceptance['current_input']['sha256'] == PREVIOUS['sha256']
            and pinned(acceptance['current_input']) == pinned(PREVIOUS) == pinned(original['current_input'])
            and acceptance['marker'] == {'path':str(HOME/'FRIDAY-INSTALL.json'),'sha256':META['FRIDAY-INSTALL.json']}
            and acceptance['source_receipt'] == {'path':str(HOME/'hermes-agent.source.json'),'sha256':META['hermes-agent.source.json']}
            and acceptance['committed'] == SOURCE_COMMITTED == original['committed'], 's447_actual_accepted_baseline_changed')
    old_commit=strict_json(pinned(SOURCE_COMMITTED));old_plan=strict_json(pinned(old_commit['plan']))
    old_request=strict_json(pinned(PREDECESSOR))
    require(old_plan['request']==PREDECESSOR and old_commit['current_input']==original['current_input']
            and old_request['current_input']==original['current_input'], 's447_accepted_source_ancestry_changed')
    marker=strict_json(pinned(BASELINE_METADATA['FRIDAY-INSTALL.json']))
    receipt=strict_json(pinned(BASELINE_METADATA['hermes-agent.source.json']))
    stamp=strict_json(pinned(BASELINE_METADATA['hermes-agent/install-stamp.json']))
    require(all(BASELINE_METADATA[n]['sha256']==META[n] for n in META), 's447_saved_metadata_changed')
    baseline_links(marker,receipt,stamp,PREVIOUS,strict_json(pinned(PREVIOUS)))
    require(marker['ordinary_source_update_request']==PREDECESSOR, 's447_baseline_request_changed')
    return acceptance'''

VALIDATOR = '''def validate_plugin_delta(previous, current, project_after):
    require(type(project_after) is dict and set(project_after)==PROJECT_PATHS, 's447_exact_reviewed_existing_source_scope_required')
    require(type(previous) is dict and type(current) is dict
            and {k:v for k,v in previous.items() if k!='project_files'} == {k:v for k,v in current.items() if k!='project_files'}, 'operational_settings_changed')
    old,new=previous['project_files'],current['project_files']
    require(len(old)==328 and sum(n.startswith('plugins/friday_rework/') for n in old)==47 and len(project_after)==7, 's447_exact_328_47_seven_inventory_required')
    require(type(old) is dict and type(new) is dict and set(old)==set(new), 'no_project_inventory_additions_or_deletions')
    for name,pin in project_after.items():
        path=Path(name)
        require(type(name) is str and not path.is_absolute() and path.as_posix()==name
                and all(p not in ('.','..') for p in path.parts) and name in old, 'exact_existing_project_path_required')
        require(type(pin) is dict and set(pin)=={'path','sha256'}
                and type(pin['path']) is str and Path(pin['path']).is_absolute()
                and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}',pin['sha256'])
                and new[name]==pin['sha256'] and new[name]!=old[name], 'exact_changed_project_pin_required')
    require({n for n in old if old[n]!=new[n]}==set(project_after), 'unlisted_project_change')
    return sorted(project_after)'''

VERIFY_FUNCTION = '''def verify_successor(package_ref, request_ref, committed_ref):
    """Read-only actual Source92 commit, exact inventory and publication check."""
    package=strict_json(pinned(package_ref));validate_package(package)
    require(package_ref==ref(OUT/'PACKAGE.json') and request_ref==ref(OUT/'bound/REQUEST.json'), 's447_exact_package_request_required')
    request=strict_json(pinned(request_ref));commit=strict_json(pinned(committed_ref))
    plan_ref=ref(OUT/'bound/PLAN.json');plan=strict_json(pinned(plan_ref))
    names=[*sorted(package['plugin_after']),'hermes-agent.source.json','hermes-agent/install-stamp.json','FRIDAY-INSTALL.json']
    require(plan['schema']=='friday.dsh-retained-existing-plugin-overlay-plan.v1'
            and plan['request']==request_ref and plan['helper']==package['adapter']
            and plan['source']==package['source'] and plan['before']==package['baseline']
            and plan['order']==names and set(plan['after'])==set(names), 's447_exact_plan_projection_required')
    require(request['schema']=='friday.ordinary-telegram-source92-feature-update.v1' and request['home']==str(HOME)
            and request['previous_input']==package['previous_input'] and request['current_input']==package['current_input']
            and request['target_frozen']==package['target_frozen'] and request['predecessor_update']==PREDECESSOR
            and request['seconds']==MAINTENANCE_SECONDS
            and request['root_operation']==ref(OUT/'bound/ROOT-OPERATION.json')
            and request['marker']=={'path':str(HOME/'FRIDAY-INSTALL.json'),'sha256':META['FRIDAY-INSTALL.json']}
            and request['source_receipt']=={'path':str(HOME/'hermes-agent.source.json'),'sha256':META['hermes-agent.source.json']}
            and request['stamp']=={'path':str(HOME/'hermes-agent/install-stamp.json'),'sha256':META['hermes-agent/install-stamp.json']}, 's447_exact_request_projection_required')
    review=strict_json(pinned(request['source_review']))
    require(review.get('schema')=='friday.ordinary-source92-feature-source-review.v1'
            and review.get('accepted') is True and review.get('open_HIGH_MEDIUM')==0
            and all(review[k]==package[k] for k in ('target_frozen','current_input','manifest','target_source_receipt')), 's447_real_package_review_required')
    operation=strict_json(pinned(request['root_operation']));clock=strict_json(pinned(operation['original_clock']))
    require(operation['state']=='ADMITTED_ONCE_NO_RETRY' and operation['home']==str(HOME)
            and operation['previous_input']==request['previous_input']
            and operation['source_receipt']==request['source_receipt']
            and operation['source_review']==request['source_review']
            and all(operation[k]==package[k] for k in ('target_frozen','current_input','manifest','target_source_receipt'))
            and operation['request_core_sha256']==sha(encode({k:v for k,v in request.items() if k!='root_operation'})), 's447_original_operation_join_required')
    tx=HOME/'preparation'/('ordinary-source-update-'+request['previous_input']['sha256'])
    require(committed_ref==ref(tx/'committed.json') and commit['state']=='SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and commit['previous_input']==request['previous_input'] and commit['current_input']==request['current_input']
            and commit['source_receipt_sha256']==META['hermes-agent.source.json']
            and commit['gateway_started'] is False and commit['workers_enabled'] is False
            and commit['plan']==plan_ref, 's447_exact_source_commit_required')
    require(read(tx/'request.json')[0]==pinned(request_ref)
            and not any(os.path.lexists(tx/n) for n in ('rolled-back.json','rollback-unconfirmed.json')), 's447_journal_state_changed')
    intent=strict_json(read(tx/'intent.json')[0])
    before={n:{'sha256':r['sha256'],'mode':r['mode']} for n,r in package['baseline'].items()}
    require(intent['schema']=='friday.ordinary-telegram-source-update-transaction.v1'
            and intent['state']=='SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and intent['request_sha256']==request_ref['sha256'] and intent['plan']==plan_ref
            and intent['before']==before and intent['deadline_mono']==operation['deadline_monotonic']
            and intent['boot_id']==clock['boot_id'] and clock['no_reset'] is True
            and clock['origin_monotonic']<intent['deadline_mono']<intent['rollback_deadline_mono']<=clock['deadline_monotonic']
            and intent['deadline_mono']<=clock['origin_monotonic']+MAINTENANCE_SECONDS, 's447_exact_consumed_intent_required')
    pinned(intent['stopped_evidence'])
    require(clock['reserve_seconds']>0 and clock['budget_seconds']>clock['reserve_seconds']
            and abs(clock['deadline_monotonic']-clock['origin_monotonic']-clock['budget_seconds'])<1e-6
            and intent['deadline_mono']<=clock['deadline_monotonic']-clock['reserve_seconds'], 's447_clock_budget_join_changed')
    current=strict_json(pinned(package['current_input']))
    expected_marker=strict_json(pinned(BASELINE_METADATA['FRIDAY-INSTALL.json']))
    expected_marker['input_sha256']=request['current_input']['sha256']
    expected_marker['plugin_files']={n:h for n,h in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
    expected_marker['ordinary_gateway']['operator_entry']={'input':request['current_input'],'script':{'path':str(Path(package['source'])/'scripts/friday_native.py'),'sha256':current['project_files']['scripts/friday_native.py']}}
    expected_marker['ordinary_source_update_request']=request_ref
    require(strict_json(pinned(plan['after']['FRIDAY-INSTALL.json']))==expected_marker, 's447_exact_marker_projection_required')
    require(pinned(plan['after']['hermes-agent.source.json'])==saved_receipt_bytes(package)
            and pinned(plan['after']['hermes-agent/install-stamp.json'])==pinned(package['retained_stamp']), 's447_retained_metadata_changed')
    for name,p in package['plugin_after'].items():require(plan['after'][name]==p,'s447_plugin_plan_changed')
    expected_after={n:{'sha256':p['sha256'],'mode':package['baseline'][n]['mode']} for n,p in plan['after'].items()}
    require(commit['after']==expected_after,'s447_commit_projection_changed')
    for index,name in enumerate(names):
        raw,st=read(HOME/name)
        require(sha(raw)==plan['after'][name]['sha256'] and stat.S_IMODE(st.st_mode)==expected_after[name]['mode'], 's447_installed_after_changed')
        require(sha(read(tx/'before'/name)[0])==package['baseline'][name]['sha256']
                and read(tx/'published'/name)[0]==raw, 's447_journal_images_changed')
        published=strict_json(read(tx/('published-'+str(index)+'.json'))[0])
        require(published=={name:{'sha256':sha(raw),'bytes':len(raw),'mode':stat.S_IMODE(st.st_mode),
                'identity':[st.st_dev,st.st_ino,st.st_uid,st.st_nlink,st.st_mode]}}, 's447_publication_identity_changed')
    expected_plugins=expected_marker['plugin_files']
    actual_names=set()
    for root,dirs,files in os.walk(HOME/'plugins/friday_rework',followlinks=False):
        for d in dirs:
            p=Path(root)/d
            require(not p.is_symlink(),'s447_plugin_directory_link')
        for leaf in files:
            p=Path(root)/leaf
            name=p.relative_to(HOME).as_posix();actual_names.add(name)
            raw,st=read(p)
            require(name in expected_plugins and sha(raw)==expected_plugins[name]
                    and st.st_gid==os.getgid() and not st.st_mode&0o077, 's447_full_installed_plugin_inventory_changed')
    require(actual_names==set(expected_plugins), 's447_plugin_inventory_addition_or_deletion')
    return {'package':package_ref,'request':request_ref,'commit':committed_ref,'plan':plan_ref,
            'previous_input':package['previous_input'],'current_input':package['current_input'],
            'current_marker':ref(HOME/'FRIDAY-INSTALL.json'),'source_receipt':ref(HOME/'hermes-agent.source.json'),
            'changed_plugin_files':[ref(HOME/n) for n in sorted(package['plugin_after'])], 'source':package['source']}
'''

def adapter_text(binding_ref):
    """Deterministic source specialization; no clock or output mutation."""
    binding=strict_json(read(binding_ref));_,files=baseline_static(binding)
    out=Path(binding['output']);text=read(TEMPLATE).decode()
    # Remove only obsolete exact S442 bridge constants; authority is actual Root binding.
    for name in ('S442_NATIVE_REQUEST','S442_NATIVE_RECEIPT','S442_VERIFIER','S442_ORIGINAL_MARKER'):
        nodes=[n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
        need(len(nodes)==1,'one_old_bridge_constant');n=nodes[0];lines=text.splitlines(True);del lines[n.lineno-1:n.end_lineno];text=''.join(lines)
    snapshots={name:{'path':str(out/'baseline-metadata'/name),'sha256':r['sha256']} for name,r in binding['metadata'].items()}
    values={'BASE':Path(binding['previous_source']).parent,'INPUT_SHA':binding['previous_input']['sha256'],
            'INPUT_NAME':'INPUT-S447-COHERENT-SEVEN.NEXT.json','ACCEPTANCE':binding['current_acceptance'],
            'META':{n:r['sha256'] for n,r in binding['metadata'].items()},'PLUGIN_PATHS':frozenset(files),
            'PREDECESSOR':binding['source_request'],'SOURCE_GIDS':{n:os.getgid() for n in set(files)|set(META_NAMES)},
            'PREVIOUS':binding['previous_input'],'PROJECT_PATHS':frozenset(files)}
    for name,value in values.items():text=assignment(text,name,value)
    constants={'BEFORE_SOURCE':Path(binding['previous_source']),'ORIGIN_ACCEPTANCE':ORIGIN_ACCEPTANCE,
               'SOURCE_COMMITTED':binding['source_committed'],'BASELINE_METADATA':snapshots,
               'MAINTENANCE_SECONDS':binding['maintenance_seconds'],'S447_BINDING':binding_ref,
               'S447_PRODUCER':pin(Path(__file__).resolve())}
    text=text.replace('\ndef require(ok, reason):','\n'+''.join(n+' = '+literal(v)+'\n' for n,v in constants.items())+'\ndef require(ok, reason):',1)
    text=text.replace("previous_root = BASE/'source'",'previous_root = BEFORE_SOURCE')
    text=text.replace("str(BASE/'source'/name)",'str(BEFORE_SOURCE/name)')
    text=function(text,'accepted_baseline',BASELINE_FUNCTION)
    text=function(text,'validate_plugin_delta',VALIDATOR)
    text=text.replace('s443_exact_four_plugin_write_set','s447_exact_reviewed_plugin_write_set')
    need(text.count("deadline_monotonic <= clock['origin_monotonic']+180")==1,'one_clock_limit')
    text=text.replace("deadline_monotonic <= clock['origin_monotonic']+180", "deadline_monotonic <= clock['origin_monotonic']+MAINTENANCE_SECONDS")
    need(text.count("'home':str(HOME),'seconds':180")==1,'one_request_limit')
    text=text.replace("'home':str(HOME),'seconds':180", "'home':str(HOME),'seconds':MAINTENANCE_SECONDS")
    needle="'accepted_baseline':ACCEPTANCE, 'native_after':{},"
    need(text.count(needle)==1,'one_package_binding')
    text=text.replace(needle,needle+" 's447_binding':S447_BINDING, 's447_producer':S447_PRODUCER,")
    text=text.replace("if __name__ == '__main__':",VERIFY_FUNCTION+"\n\nif __name__ == '__main__':",1)
    text=text.replace('json.loads(', 'strict_json(')
    helper="def strict_json(raw):\n    def pairs(rows):\n        result={}\n        for key,value in rows:\n            require(key not in result,'duplicate_json_key_refused')\n            result[key]=value\n        return result\n    def constant(_value):\n        raise RuntimeError('nonfinite_json_constant_refused')\n    return getattr(json,'loads')(raw,object_pairs_hook=pairs,parse_constant=constant)\n"
    text=text.replace('def require(ok, reason):',helper+'\n\ndef require(ok, reason):',1)
    ast.parse(text);return text

def prepare(binding_ref):
    """Root-only once; writes only the explicit new source family, no admission."""
    binding=strict_json(read(binding_ref));current,files=baseline_static(binding)
    out=Path(binding['output']);need(not os.path.lexists(out),'source_family_exists_no_replay')
    # Validate complete exact baseline before making any artifact.
    for name,h in current['project_files'].items():read({'path':str(Path(binding['previous_source'])/name),'sha256':h})
    snapshots={n:read(ref) for n,ref in binding['metadata'].items()}
    marker=strict_json(snapshots['FRIDAY-INSTALL.json'])
    need(marker['input_sha256']==binding['previous_input']['sha256']
         and marker['ordinary_source_update_request']==binding['source_request']
         and marker['ordinary_gateway']['operator_entry']=={'input':binding['previous_input'],'script':{'path':str(Path(binding['previous_source'])/'scripts/friday_native.py'),'sha256':current['project_files']['scripts/friday_native.py']}}
         and marker['plugin_files']=={n:h for n,h in current['project_files'].items() if n.startswith('plugins/friday_rework/')}, 'actual_current_marker_input_source_join_changed')
    text=adapter_text(binding_ref)
    out.mkdir(mode=0o700)
    for name,raw in snapshots.items():put(out/'baseline-metadata'/name,raw)
    adapter=put(out/'adapter.py',text.encode())
    ns={'__file__':adapter['path'],'__name__':'_s447_source92_adapter'}
    exec(compile(text,adapter['path'],'exec'),ns)
    package=ns['prepare_source_package'](final_files=files)
    return {'producer':pin(Path(__file__).resolve()),'binding':binding_ref,'adapter':adapter,'package':package,
            'source_only':True,'future_root_clock':None,'future_source_commit':None,'future_installed_acceptance':None,
            'future_readiness':None,'future_runtime':None,'future_user_semantics':None}

def _verified_adapter(package_ref):
    package=strict_json(read(package_ref))
    need(package.get('s447_producer')==pin(Path(__file__).resolve()),'exact_S447_producer_required')
    binding_ref=package['s447_binding'];binding=strict_json(read(binding_ref))
    need(package_ref['path']==str(Path(binding['output'])/'PACKAGE.json')
         and package['adapter']['path']==str(Path(binding['output'])/'adapter.py'), 'exact_bound_source_family_required')
    text=read(package['adapter']).decode()
    need(text==adapter_text(binding_ref),'generated_adapter_algorithm_or_binding_changed')
    ns={'__file__':package['adapter']['path'],'__name__':'_s447_successor_verifier'}
    exec(compile(text,package['adapter']['path'],'exec'),ns)
    return ns

def verify_successor(package_ref,request_ref,committed_ref):
    """Read-only static source/journal/current-files proof; no H module imports."""
    return _verified_adapter(package_ref)['verify_successor'](package_ref,request_ref,committed_ref)

# Compatibility spelling for Root's separate fresh installed import checker.
verify_installed = verify_successor

if __name__=='__main__':
    raise SystemExit('Library only: Root supplies exact actual binding; prepare does not admit an operation.')
