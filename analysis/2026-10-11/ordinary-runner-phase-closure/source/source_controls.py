#!/usr/bin/env python3
"""AUTHOR source-only controls, not independent acceptance or runtime tests."""
import ast
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys
import threading
import time

OUT = Path(sys.argv[1]).absolute()
INPUT = Path(sys.argv[2]).absolute()
PKG = Path(__file__).parent
CPUS = sorted(os.sched_getaffinity(0))[:2]
os.sched_setaffinity(0, CPUS)
resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))
STAT = Path('/proc/self/stat').read_text()
START_TICKS = int(STAT[STAT.rfind(')') + 2:].split()[19])
(OUT / 'READY.json').write_text(json.dumps({'pid': os.getpid(), 'start_ticks': START_TICKS,
    'affinity': CPUS, 'address_space_bytes': resource.getrlimit(resource.RLIMIT_AS)[0]}))
while not (OUT / 'BARRIER.json').exists():
    time.sleep(0.01)
barrier = json.loads((OUT / 'BARRIER.json').read_text())
assert barrier['pid'] == os.getpid() and barrier['start_ticks'] == START_TICKS
BEGIN = time.monotonic()
FD_START = len(list(Path('/proc/self/fd').iterdir()))


def audit(event, args):
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'subprocess.Popen',
                 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork', 'pty.spawn'):
        raise AssertionError('forbidden_effect:' + event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        mode, flags = args[1] or '', args[2] or 0
        if any(c in mode for c in 'wax+') or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            assert Path(os.fsdecode(args[0])).absolute().is_relative_to(OUT), ('outside_write', args[0])


sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location('author_gate_inputs', PKG / 'gate_inputs.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
CONTROLS = []


def save(name, value):
    gate.dump(OUT / name, value)


def check(name, fn):
    assert time.monotonic() < barrier['hard_monotonic'], 'original_deadline'
    result = fn()
    CONTROLS.append({'name': name, 'status': 'AUTHOR_SOURCE_PASS', 'observation': result})


def denied(name, fn, expected):
    def run():
        try:
            fn()
        except (ValueError, OSError, KeyError, TypeError) as error:
            assert expected in str(error), (expected, str(error))
            return {'refusal': str(error)}
        raise AssertionError('did_not_refuse:' + name)
    check(name, run)


inputs = gate.input_document(INPUT)
catalog = gate.collect(inputs)
save('CATALOG.json', catalog)
check('actual_no_import_collection_and_owner_definition_preservation', lambda: catalog['summary'])
check('main_effect_signals_are_admission_free_lower_bounds', lambda: all(not f['safe_to_import'] for f in catalog['repo_files']))
check('owner_47_useful_56_daily_two_AC055_rows', lambda: {'counts': catalog['acceptance']['cumulative_records'],
    'workers': [r['worker'] for r in catalog['acceptance']['rows'] if r['check_id'] == 'AC055']})
coverage={'schema':'friday.whole-source-coverage.v1','catalog_sha256':gate.digest(gate.canonical(catalog)),
    'independent_acceptance':True,'runtime_grant':False,'files':[]}
denied('full_gate_source_coverage_omissions_refuse',lambda:gate.coverage_preflight(catalog,coverage),'mandatory_source_files_omitted_or_foreign')
bad_coverage=dict(coverage,catalog_sha256='0'*64)
denied('full_gate_stale_catalog_refuses',lambda:gate.coverage_preflight(catalog,bad_coverage),'stale_coverage_catalog')
bad_coverage=dict(coverage,independent_acceptance=False)
denied('full_gate_author_coverage_refuses',lambda:gate.coverage_preflight(catalog,bad_coverage),'coverage_unaccepted')
runner_spec=importlib.util.spec_from_file_location('author_source_runner',PKG/'source_runner.py')
runner=importlib.util.module_from_spec(runner_spec);runner_spec.loader.exec_module(runner)
denied('source_runner_runtime_kind_refuses_before_grant_or_process',lambda:runner.admit(inputs,{}, {}, {}, {}, {},'normal-install',OUT/'none'),'unknown_or_runtime_runner')
for module in ['gate_inputs.py','source_runner.py','runner_worker.py','owned_supervisor.py','source_controls.py']:
    check('compile_'+module+'_no_execution',lambda module=module: bool(compile((PKG/module).read_text(),str(PKG/module),'exec')))
for kind, relative in gate.CHECKERS.items():
    source = gate.bytes_at(Path(inputs['native_fixture_root']) / relative).decode()
    replacements = {inputs['native_fixture_root']: str(OUT / 'relocation'),
        str(Path(inputs['native_fixture_root']) / 'candidate'): str(OUT / 'fixture-current-project'),
        str(Path(inputs['native_fixture_root']) / 'hermes'): str(OUT / 'fixture-current-native'),
        str(Path(inputs['native_fixture_root']).parent / 'ordinary-cli-tui-onboarding-integration/candidate'): str(OUT / 'fixture-current-project')}
    moved, edits = gate.relocate_checker(source, replacements)
    expanded, _ = gate.relocate_checker(source, replacements, expanded=True)
    target = OUT / ('relocated_' + kind + '.py')
    expanded_target = OUT / ('expanded_' + kind + '.py')
    target.write_text(moved)
    expanded_target.write_text(expanded)
    before, after = gate.classify(Path(inputs['native_fixture_root']) / relative), gate.classify(target)
    assert before['registrations'] == after['registrations']
    expanded_catalog = gate.classify(expanded_target)
    assert [r['name_expression'] for r in before['registrations']] == [r['name_expression'] for r in expanded_catalog['registrations']]
    save('RELOCATION-' + kind + '.json', {'original': gate.ref(Path(inputs['native_fixture_root']) / relative),
        'relocated': gate.ref(target), 'expanded': gate.ref(expanded_target), 'root_edits': edits,
        'normalized_AST_equal': True, 'scenario_and_threshold_body_AST_equal': True,
        'full_registration_expressions_retained': True, 'old_filter': before['accepted_control_filter'],
        'registration_expressions': before['registrations'], 'execution': 'NOT_RUN',
        'expanded_admission': 'NOT_READY_EFFECT_REVIEW_AND_AUXILIARY_INPUTS_REQUIRED'})
    check('relocate_' + kind + '_known_roots_same_AST_registration_thresholds', lambda edits=edits: len(edits))
    check('expanded_' + kind + '_all_registered_bodies_preserved_unexecuted', lambda before=before: len(before['registrations']))
    denied('changed_' + kind + '_selector_body_refused',
        lambda source=source, replacements=replacements: gate.relocate_checker(source.replace('SKIPPED.append(name);return', 'SKIPPED.append(name);return None'), replacements, expanded=True),
        'selector_body_changed')

fixtures = OUT / 'fixtures'
fixtures.mkdir(mode=0o700)
receipt_path = fixtures / 'receipt.json'
receipt_path.write_text('{}\n')
good_ref = gate.ref(receipt_path)
check('actual_exact_ref_positive', lambda: gate.check_ref(good_ref))
bad = dict(good_ref, sha256='0' * 64)
denied('actual_stale_receipt_SHA_refuses', lambda: gate.check_ref(bad), 'changed_ref')
denied('missing_ref_refuses', lambda: gate.check_ref(dict(good_ref, path=str(fixtures / 'missing.json'))), 'missing_input')
denied('wrong_schema_refuses', lambda: gate.check_ref(dict(good_ref, extra=True)), 'invalid_ref_schema')
receipt_path.write_text('{"changed":true}\n')
denied('changed_after_pin_refuses', lambda: gate.check_ref(good_ref), 'changed_ref')
link = fixtures / 'symlink.json'
link.symlink_to(receipt_path)
denied('symlink_receipt_refuses', lambda: gate.ref(link), 'symlink_input')
dupe = fixtures / 'duplicate.json'
dupe.write_text('{"status":false,"status":true}')
denied('duplicate_receipt_fields_refuse', lambda: gate.document(dupe), 'duplicate_json_key')
denied('missing_final_owner_binding_refuses', lambda: gate.source_preflight(inputs, {}, {}), 'binding_schema')
denied('runtime_without_genuine_grant_refuses', lambda: gate.runtime_admission(), 'runtime_requires_genuine')
denied('author_JSON_runtime_grant_cannot_admit', lambda: gate.runtime_admission({'granted':True,'source_accepted':True}), 'runtime_requires_genuine')

# These deliberately synthetic receipts only exercise byte/association checking.
# They are author fixtures and are never promoted to a real trust anchor.
cli = {'schema':'friday.owner-output-final-source.v1','assignment':'FRW-ORDINARY-CLI-OWNER-OUTPUT-PATH-SOL',
    'generation':1,'status':'INDEPENDENT_SOURCE_ACCEPTED','whole_owner_output_path':True,
    'project_changes':{},'native_changes':{},'AUTHOR_FIXTURE_ONLY':True}
cli_path = fixtures / 'cli.json'; gate.dump(cli_path, cli)
owner = {'independent_acceptance':True,'source_accepted':True,'runtime_grant':False,
    'CLI_source_manifest':gate.ref(cli_path),'AUTHOR_FIXTURE_ONLY':True}
owner_path = fixtures / 'owner.json'; gate.dump(owner_path, owner)
acceptance = {'schema':'friday.final-source-acceptance-root-received.v1','independent_acceptance':True,
    'source_accepted':True,'runtime_grant':False,'project_manifest':inputs['API_project_manifest'],
    'native_inventory':inputs['native_inventory'],'owner_output_acceptance':gate.ref(owner_path),'AUTHOR_FIXTURE_ONLY':True}
acceptance_path=fixtures/'acceptance.json';gate.dump(acceptance_path,acceptance)
binding={'schema':gate.SCHEMA,'main':inputs['main'],'preparation_inputs_sha256':gate.INPUT_SHA,
    'project_root':inputs['API_candidate_root'],'project_manifest':inputs['API_project_manifest'],
    'native_root':inputs['native_root'],'native_inventory':inputs['native_inventory'],'native_layers':30,
    'API_sha256':'c8e830aaffa75fc6f12f3569b89b80888c0218b5bc60221d170b569a22c8e7e3',
    'CLI_source_manifest':gate.ref(cli_path),'owner_output_acceptance':gate.ref(owner_path),
    'candidate_source_acceptance':gate.ref(acceptance_path),'retained_stops':gate.STOPS}
def seal(value):
    value=copy.deepcopy(value)
    value['binding_sha256']=gate.digest(gate.canonical({k:v for k,v in value.items() if k!='binding_sha256'}))
    return value
binding=seal(binding)
for name,key,value,cause in [('stale_main','main','0'*40,'stale_main'),
    ('stale_API','API_sha256','0'*64,'stale_API'),
    ('wrong_binding_schema','schema','foreign','binding_schema'),
    ('changed_stops','retained_stops',{},'stop_policy_changed'),
    ('foreign_native_root','native_root',str(fixtures),'foreign_unchanged_native'),
    ('foreign_acceptance','candidate_source_acceptance',good_ref,'foreign_acceptance_anchor')]:
    altered=copy.deepcopy(binding);altered[key]=value;altered=seal(altered)
    denied(name,lambda altered=altered:gate.source_preflight(inputs,altered,gate.ref(acceptance_path)),cause)
original_cli=copy.deepcopy(cli)
cli['status']='AUTHOR_PASS_PENDING_REVIEW';gate.dump(cli_path,cli)
altered=copy.deepcopy(binding);altered['CLI_source_manifest']=gate.ref(cli_path);altered=seal(altered)
denied('author_only_owner_output_refused',lambda:gate.source_preflight(inputs,altered,gate.ref(acceptance_path)),'unaccepted_owner_output')
gate.dump(cli_path,original_cli)
cli=copy.deepcopy(original_cli);cli['project_changes']={'plugins/friday_rework/dashboard/api.py':'0'*64};gate.dump(cli_path,cli)
altered=copy.deepcopy(binding);altered['CLI_source_manifest']=gate.ref(cli_path);altered=seal(altered)
denied('stale_CLI_delta_refused',lambda:gate.source_preflight(inputs,altered,gate.ref(acceptance_path)),'stale_or_foreign_project')
gate.dump(cli_path,original_cli)
# Restoring a fixture yields its same byte hash; no source or external receipt changed.
denied('complete_byte_consistent_AUTHOR_receipts_never_actual_acceptance',
    lambda: gate.source_preflight(inputs,binding,gate.ref(acceptance_path)), 'author_fixture_not_authority')
check('actual_pinned_project132_inventory_positive_read_only',
    lambda: len(gate.inventory(inputs['API_candidate_root'], gate.check_ref(inputs['API_project_manifest']))))
check('actual_pinned_native17649_inventory_positive_read_only',
    lambda: len(gate.inventory(inputs['native_root'], gate.check_ref(inputs['native_inventory'])['files'])))
save('BINDING-AUTHOR-FIXTURE.json',binding)
save('AUTHOR-CONTROLS.json', {'status':'AUTHOR_SOURCE_CONTROLS_ONLY','count':len(CONTROLS),
    'controls':CONTROLS,'independent_acceptance':False,'runtime_grant':False,
    'tests_or_native_modules_imported':0,'target_checkers_executed':0,
    'native_source_files_hash_read_only':17649,'OS_FD_runtime_controls':'NOT_RUN',
    'resources':{'affinity':CPUS,'address_space_bytes':resource.getrlimit(resource.RLIMIT_AS)[0],
                 'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
    'elapsed_seconds':time.monotonic()-BEGIN,'FD_start':FD_START,
    'FD_end':len(list(Path('/proc/self/fd').iterdir())),
    'children':Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip(),
    'threads':[t.name for t in threading.enumerate()]})
assert len(list(Path('/proc/self/fd').iterdir()))==FD_START
assert not Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().strip()
assert len(threading.enumerate())==1
print(json.dumps({'status':'AUTHOR_SOURCE_CONTROLS_PASS','count':len(CONTROLS),'collection':catalog['summary']}))
