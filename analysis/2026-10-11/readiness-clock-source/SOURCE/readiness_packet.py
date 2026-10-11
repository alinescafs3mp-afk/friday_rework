"""SOURCE-only native input census. Target modules are parsed, never imported.

HeldCapture is an exact separately pinned collector dependency. A packet records current
bytes and static input relationships; it never authorizes their execution.
"""
import ast
import hashlib
import json
import math
import re
from datetime import datetime
import os
import stat
import time
from startup_inventory import HeldCapture, Refusal, canonical, exact_path, need, sha

SCHEMA = 'friday.native19.input-readiness.v1'
GAPS = (
    'INDEPENDENT_COLLECTOR_AND_PACKET_ACCEPTANCE',
    'INDEPENDENT_WHOLE9_R2_ACCEPTANCE',
    'BEFORE_STARTUP_HELD_EXECUTION_AND_BOOTSTRAP_HISTORY',
    'DYNAMIC_REFLECTION_IMPORTS_AND_LOADED_CODE_CUSTODY',
    'ELF_DT_NEEDED_RELOCATION_IFUNC_VDSO_MAP_ALIAS_CUSTODY',
    'OUTSIDE_OWNER_DESCENDANTS_AGGREGATE_CUSTODY',
    'FINAL_GENERATED_SCHEMA_AND_UNFILTERED_GATE_EXECUTION',
    'EXPLICIT_GLOBAL_GUARD_INSTALLATION_AUTHORITY_AND_ACCEPTANCE',
    'FINAL_IMMUTABLE_POSITIVE_NEGATIVE_STOP_CLEANUP',
)
MAX_PACKET = 16 * 1024**2
MAX_SCHEMA_REFS = 50000


def closed_json(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_PACKET, 'BOUNDED_JSON_BYTES')
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    def bad(_):
        raise Refusal('NONFINITE_JSON')
    def finite_float(token):
        value = float(token)
        need(math.isfinite(value), 'NONFINITE_JSON')
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad, parse_float=finite_float)
    except (UnicodeError, ValueError, RecursionError):
        raise Refusal('INVALID_BOUNDED_JSON') from None


def validate_clock(clock, *, now_epoch=None):
    """Validate the complete original clock before any capture or consumption."""
    fields = {'accepted_msk', 'start_epoch', 'native_turn_id', 'original_seconds',
              'seconds', 'cleanup_seconds', 'useful_epoch', 'hard_epoch',
              'hard_deadline_epoch', 'no_reset'}
    need(type(clock) is dict and set(clock) == fields, 'CLOSED_ORIGINAL_CLOCK')
    ints = ('start_epoch', 'original_seconds', 'seconds', 'cleanup_seconds',
            'useful_epoch', 'hard_epoch', 'hard_deadline_epoch')
    need(all(type(clock[k]) is int and clock[k] >= 0 for k in ints), 'CLOCK_TYPES')
    need(type(clock['no_reset']) is bool and clock['no_reset'] is True, 'CLOCK_NO_RESET')
    # The pinned native protocol declares generated Turn IDs as UUIDv7.
    # This is syntax validation only; genuine native-turn authority remains unbound.
    need(type(clock['native_turn_id']) is str and re.fullmatch(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-7[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}', clock['native_turn_id']) is not None,
        'CLOCK_NATIVE_TURN_UUIDV7')
    need(clock['seconds'] == clock['original_seconds'] == 1800
         and clock['cleanup_seconds'] == 120
         and clock['useful_epoch'] == clock['start_epoch'] + 1680
         and clock['hard_deadline_epoch'] == clock['hard_epoch'] == clock['start_epoch'] + 1800,
         'ORIGINAL1800_CLEANUP120_CLOCK_ALIASES')
    accepted = clock['accepted_msk']
    need(type(accepted) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\+03:00', accepted) is not None,
        'CLOCK_ACCEPTED_MSK_FORMAT')
    try:
        stamp = datetime.fromisoformat(accepted).timestamp()
    except (ValueError, OverflowError, OSError):
        raise Refusal('CLOCK_ACCEPTED_MSK_PARSE') from None
    need(math.isfinite(stamp) and stamp == clock['start_epoch'], 'CLOCK_ACCEPTED_START_JOIN')
    now = time.time() if now_epoch is None else now_epoch
    need(type(now) in (int, float) and math.isfinite(now)
         and clock['start_epoch'] <= now < clock['useful_epoch'], 'LATE_OR_INVALID_CONSUMPTION')
    return clock


def pin_refs(value):
    if type(value) is dict:
        if {'path', 'bytes', 'sha256'} <= value.keys():
            yield {k: value[k] for k in ('path', 'bytes', 'sha256')}
        else:
            for child in value.values():
                yield from pin_refs(child)
    elif type(value) is list:
        for child in value:
            yield from pin_refs(child)


def expected_refs(inputs, collector_refs, native_r2):
    need(type(inputs) is dict and inputs.get('assignment') == 'FRW-NATIVE19-INPUT-READINESS-PACKET-SOL#1', 'EXACT_ASSIGNMENT')
    need(len(inputs.get('current_control_inputs19', {})) == 19, 'EXACT19_CONTROLS')
    need(set(inputs.get('private_account_inputs4', {})) == {'astra/config.toml', 'astra/hooks.json', 'sol/config.toml', 'sol/hooks.json'}, 'EXACT4_PRIVATE_INPUTS')
    need(type(collector_refs) is list and len(collector_refs) == 3 and type(native_r2) is dict and len(native_r2) == 9, 'EXACT_SOURCE_DEPENDENCIES')
    result = {}
    for ref in [*pin_refs(inputs), *pin_refs(collector_refs), *pin_refs(native_r2)]:
        path = exact_path(ref['path'])
        need(path.rsplit('/', 1)[-1] != 'auth.json' and type(ref['bytes']) is int and 0 <= ref['bytes'] <= 16 * 1024**2, 'AUTH_EXCLUDED_BOUNDED_PIN')
        need(type(ref['sha256']) is str and len(ref['sha256']) == 64 and all(x in '0123456789abcdef' for x in ref['sha256']), 'EXACT_SHA256')
        old = result.setdefault(path, ref)
        need(old == ref, 'CONFLICTING_PIN')
    need(len(result) <= 1200, 'INPUT_NODE_LIMIT')
    return result


def literal(node, env):
    """Evaluate a tiny data grammar, never compile/eval/import updater code."""
    if isinstance(node, ast.Constant) and type(node.value) in (str, int, bool, type(None)):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [literal(x, env) for x in node.elts]
        return set(values) if isinstance(node, ast.Set) else values
    if isinstance(node, ast.Dict):
        out = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                child = literal(value, env); need(type(child) is dict, 'STATIC_DICT_UNPACK')
                need(not set(out) & set(child), 'STATIC_DUPLICATE_KEYS'); out.update(child)
            else:
                key = literal(key, env); need(key not in out, 'STATIC_DUPLICATE_KEYS'); out[key] = literal(value, env)
        return out
    if isinstance(node, ast.Subscript):
        container = literal(node.value, env); key = literal(node.slice, env)
        need(type(container) is dict and key in container, 'STATIC_SUBSCRIPT')
        return container[key]
    if isinstance(node, ast.BinOp):
        left, right = literal(node.left, env), literal(node.right, env)
        if isinstance(node.op, ast.Div) and type(left) is str and type(right) is str:
            return left.rstrip('/') + '/' + right
        if isinstance(node.op, ast.Add) and type(left) is str and type(right) is str:
            return left + right
        if isinstance(node.op, ast.Mult) and type(left) is str and type(right) is int and 0 <= right <= 4096:
            return left * right
    if isinstance(node, ast.Call) and not node.keywords:
        if isinstance(node.func, ast.Name) and node.func.id in ('str', 'Path') and len(node.args) == 1:
            value = literal(node.args[0], env); need(type(value) is str, 'STATIC_STRING_PATH'); return value
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'resolve' and not node.args:
            value = literal(node.func.value, env); need(value == env['__file__'], 'ONLY_EXACT_UPDATER_RESOLVE'); return value
    raise Refusal('UNSUPPORTED_STATIC_DATA_GRAMMAR')


def assignments(tree, updater_path):
    env = {'__file__': updater_path}
    selected = {'RUNTIME', 'REPO', 'RECONNECT', 'LIFECYCLE', 'NATIVE_QUEUE', 'IDLE_GATE', 'ASTRA_PROFILE_HELPER',
                'SLOTS', 'VALIDATION_CONTROL_PATHS', 'REQUIRED_METHODS', 'RPC_COMPAT_PARAMS',
                'RPC_COMPAT_VARIANTS', 'READ_ONLY_PROBE_METHODS'}
    for node in tree.body:
        name = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        if name in selected:
            env[name] = literal(node.value, env)
    need(selected <= env.keys(), 'MISSING_STATIC_GATE_DECLARATION')
    return env


def call_name(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return call_name(node.value) + '.' + node.attr
    if isinstance(node, ast.Subscript): return '<subscript>'
    return '<computed>'


def source_record(raw_text, node):
    text = ast.get_source_segment(raw_text, node)
    need(type(text) is str, 'EXACT_AST_SOURCE_SEGMENT')
    return dict(line=node.lineno, column=node.col_offset, end_line=node.end_lineno,
                expression_bytes=len(text.encode()), expression_sha256=sha(text.encode()), expression=text[:512],
                truncated=len(text) > 512)


def gate_inventory(raw, updater_path, expected_controls):
    try:
        text = raw.decode('utf-8'); tree = ast.parse(text, filename=updater_path)
    except (UnicodeError, SyntaxError, RecursionError):
        raise Refusal('UPDATER_AST_PARSE') from None
    env = assignments(tree, updater_path)
    paths = env['VALIDATION_CONTROL_PATHS']
    need(type(paths) is dict and len(paths) == 19 and paths == {k: v['path'] for k, v in expected_controls.items()}, 'ACTUAL19_CONTROL_PATHS_JOIN')
    required = sorted(env['REQUIRED_METHODS']); params = env['RPC_COMPAT_PARAMS']; variants = env['RPC_COMPAT_VARIANTS']
    need(type(params) is dict and set(required) == set(params) and set(variants) <= set(params), 'UNFILTERED_RPC_CASES')
    cases = []
    for method in sorted(params):
        values = [params[method], *variants.get(method, [])]
        for number, value in enumerate(values, 1):
            need(type(value) is dict, 'RPC_PARAMS_OBJECT')
            cases.append(dict(method=method, case=number, params=value, params_sha256=sha(canonical(value)), execution='NOT_RUN'))
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    need('validate_candidate' in funcs and 'validate_rpc_contract' in funcs, 'ACTUAL_FULL_GATE_ROOT')
    reachable = set(); pending = ['validate_candidate']
    while pending:
        name = pending.pop()
        if name in reachable: continue
        reachable.add(name)
        for node in ast.walk(funcs[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs:
                pending.append(node.func.id)
    functions = []; calls = []; branches = []; guards = []
    for name in sorted(reachable):
        root = funcs[name]; functions.append(dict(name=name, **source_record(text, root)))
        for node in ast.walk(root):
            if isinstance(node, ast.Call):
                calls.append(dict(function=name, target=call_name(node.func), **source_record(text, node), execution='NOT_RUN'))
            elif isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.ExceptHandler)):
                branches.append(dict(function=name, kind=type(node).__name__, **source_record(text, node), coverage='STATIC_ALL_BRANCHES_NOT_EXECUTED'))
            elif isinstance(node, (ast.Raise, ast.Assert)):
                guards.append(dict(function=name, kind=type(node).__name__, **source_record(text, node), execution='NOT_RUN'))
    order = lambda r: (r['function'], r['line'], r['column'], r.get('target', r.get('kind', '')))
    labels = []
    for name in sorted(reachable):
        for node in ast.walk(funcs[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'require_success':
                label = node.args[1] if len(node.args) > 1 else None
                labels.append(dict(function=name, line=node.lineno, label=source_record(text, label)['expression'] if label else '<missing>', execution='NOT_RUN'))
    return dict(updater_sha256=sha(raw), control_files_count=19, control_paths=paths,
                required_rpc_methods=required, rpc_cases=cases, rpc_cases_count=len(cases),
                read_only_probe_methods=env['READ_ONLY_PROBE_METHODS'], strict_config_slots=sorted(env['SLOTS']),
                functions=functions, call_sites=sorted(calls, key=order), branch_sites=sorted(branches, key=order),
                refusal_sites=sorted(guards, key=order), require_success_stages=labels,
                root='validate_candidate', traversal='ALL_STATIC_DIRECT_HELPER_CALLS_ALL_BRANCHES_NO_FILTER',
                tests_executed=0, full_gate='NOT_RUN_NOT_ACCEPTED',
                dynamic_inputs='ROLE_PROFILES_CANDIDATE_BINARY_HOST_RELEASE_AND_GENERATED_SCHEMA_NOT_CAPTURED_OR_EXECUTED',
                startup_history='UNKNOWN_NOT_AUTHENTICATED')


def pointer(document, fragment):
    need(type(fragment) is str and (fragment == '' or fragment.startswith('/')), 'ONLY_JSON_POINTER_FRAGMENT')
    value = document
    if fragment:
        for part in fragment[1:].split('/'):
            need('%' not in part and all(part[i:i+2] in ('~0', '~1') for i, x in enumerate(part) if x == '~'), 'STRICT_JSON_POINTER_ESCAPE')
            part = part.replace('~1', '/').replace('~0', '~')
            if type(value) is dict:
                need(part in value, 'SCHEMA_REF_MISSING'); value = value[part]
            elif type(value) is list:
                need(part.isascii() and part.isdigit() and (part == '0' or not part.startswith('0')) and int(part) < len(value), 'SCHEMA_REF_INDEX'); value = value[int(part)]
            else: raise Refusal('SCHEMA_REF_SCALAR')
    return value


def walk_refs(value, location=''):
    if type(value) is dict:
        for key in sorted(value):
            child = value[key]; at = location + '/' + key.replace('~', '~0').replace('/', '~1')
            if key == '$ref':
                need(type(child) is str, 'SCHEMA_REF_STRING'); yield at, child
            yield from walk_refs(child, at)
    elif type(value) is list:
        for index, child in enumerate(value): yield from walk_refs(child, location + '/' + str(index))


def resolve_ref(file, ref, documents):
    need(ref.count('#') <= 1 and '%' not in ref and '\\' not in ref and ':' not in ref and '?' not in ref, 'LOCAL_SCHEMA_REFS_ONLY')
    target, _, fragment = ref.partition('#')
    if not target: target = file
    else:
        need(not target.startswith('/') and all(p not in ('', '.', '..') for p in target.split('/')), 'EXPLICIT_SCHEMA_FILE_REF')
        parent = file.rsplit('/', 1)[0] + '/' if '/' in file else ''
        target = parent + target
    need(target in documents, 'UNPINNED_SCHEMA_REF')
    value = pointer(documents[target], fragment)
    return target, fragment, value


def schema_inventory(buffers, refs, required_methods):
    need(type(refs) is dict and 'ClientRequest.json' in refs and 0 < len(refs) <= 600, 'PINNED_SCHEMA_FILES')
    documents = {name: closed_json(buffers[ref['path']]) for name, ref in sorted(refs.items())}
    for value in documents.values(): need(type(value) is dict, 'SCHEMA_DOCUMENT_OBJECT')
    edges = []; gaps = []; refs_count = 0
    for name, document in documents.items():
        for location, ref in walk_refs(document):
            refs_count += 1
            need(refs_count <= MAX_SCHEMA_REFS, 'SCHEMA_REF_COUNT_BOUND')
            try:
                target, fragment, value = resolve_ref(name, ref, documents)
                edges.append(dict(file=name, location=location, ref=ref, target_file=target, target_pointer=fragment,
                                  resolved_value_sha256=sha(canonical(value)), status='RESOLVED_PINNED_DATA'))
            except Refusal as error:
                gaps.append(dict(file=name, location=location, ref=ref, reason=str(error), status='UNBOUND'))
    client = documents['ClientRequest.json']; branches = client.get('oneOf'); definitions = client.get('definitions')
    need(type(branches) is list and type(definitions) is dict, 'CLIENT_REQUEST_ROOT')
    methods = {}; method_gaps = []
    for index, branch in enumerate(branches):
        need(type(branch) is dict, 'CLIENT_REQUEST_BRANCH')
        prop = branch.get('properties', {}); method = prop.get('method', {}) if type(prop) is dict else {}
        enum = method.get('enum') if type(method) is dict else None
        if not (type(enum) is list and len(enum) == 1 and type(enum[0]) is str):
            method_gaps.append(dict(branch=index, reason='UNKNOWN_METHOD_BRANCH')); continue
        name = enum[0]; need(name not in methods, 'DUPLICATE_CLIENT_REQUEST_METHOD')
        param = prop.get('params', {}); ref = param.get('$ref') if type(param) is dict else None
        record = dict(branch=index, method=name, branch_sha256=sha(canonical(branch)), params_ref=ref, execution='NOT_RUN')
        if type(ref) is str:
            try:
                target, fragment, value = resolve_ref('ClientRequest.json', ref, documents)
                record.update(params_file=target, params_pointer=fragment, params_schema_sha256=sha(canonical(value)), status='PINNED_DATA_REF_RESOLVED')
            except Refusal as error: record.update(status='UNBOUND', reason=str(error))
        else: record.update(status='UNBOUND', reason='NO_DIRECT_PARAMS_REF')
        methods[name] = record
    missing = sorted(set(required_methods) - set(methods))
    client_nodes = set(); pending = [('ClientRequest.json', '')]
    while pending:
        file, fragment = pending.pop(); key = (file, fragment)
        if key in client_nodes: continue
        need(len(client_nodes) < MAX_SCHEMA_REFS, 'CLIENT_SCHEMA_GRAPH_BOUND'); client_nodes.add(key)
        value = pointer(documents[file], fragment)
        for _, ref in walk_refs(value):
            try:
                target, ptr, _ = resolve_ref(file, ref, documents); pending.append((target, ptr))
            except Refusal: pass
    return dict(files_count=len(documents), client_request_sha256=refs['ClientRequest.json']['sha256'],
                edges=edges, edges_count=len(edges), gaps=gaps, methods=[methods[k] for k in sorted(methods)],
                required_methods_missing=missing, method_gaps=method_gaps,
                client_graph_nodes=[dict(file=f, pointer=p) for f, p in sorted(client_nodes)],
                client_graph_complete_data_refs=not missing and not gaps and not method_gaps,
                provenance='EXACT_PINNED_SAVED_SCHEMA_NOT_FRESH_GENERATION', semantic_request_validation='NOT_RUN', execution='NOT_RUN')


def guard_delta(actual, candidate):
    try:
        old = ast.parse(actual); new = ast.parse(candidate)
    except (SyntaxError, UnicodeError): raise Refusal('GUARD_AST_PARSE') from None
    def funcs(tree):
        return {node.name: sha(ast.dump(node, include_attributes=False).encode()) for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    before, after = funcs(old), funcs(new)
    return dict(installed_sha256=sha(actual), candidate_sha256=sha(candidate),
                changed_functions=[k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)],
                candidate='UNINSTALLED', actual_global_guard='UNCHANGED',
                independent_review='PINNED_SEPARATE_SOURCE_RECEIPT_NO_EXECUTION_CREDIT', runtime_grant=False)


def derived(buffers, inputs, collector_refs, native_r2):
    controls = inputs['current_control_inputs19']; private = inputs['private_account_inputs4']; schemas = inputs['current_pinned_schema_files']
    gate = gate_inventory(buffers[controls['updater']['path']], controls['updater']['path'], controls)
    graph = schema_inventory(buffers, schemas, gate['required_rpc_methods'])
    # Config/hooks are intentionally opaque private bytes; no values enter wire/logs.
    accounts = [dict(name=k, path=v['path'], bytes=v['bytes'], sha256=v['sha256'], privacy='PRIVATE_OPAQUE_CAPTURE_ONLY',
                     settings_changed=False, execution='NOT_RUN') for k, v in sorted(private.items())]
    return dict(gate=gate, schema_graph=graph, private_inputs=accounts,
                candidate_atomic_guard=guard_delta(buffers[controls['lifecycle']['path']], buffers[inputs['candidate_lifecycle_guard']['path']]),
                whole9_r2=[dict(name=k, path=v['path'], bytes=v['bytes'], sha256=v['sha256'], execution='NOT_RUN') for k, v in sorted(native_r2.items())],
                collector=[dict(path=v['path'], bytes=v['bytes'], sha256=v['sha256']) for v in sorted(collector_refs, key=lambda r:r['path'])],
                counts=dict(control_files=19, private_inputs=4, schema_files=len(schemas), whole9_r2=9,
                            rpc_methods=len(gate['required_rpc_methods']), rpc_cases=gate['rpc_cases_count'], executed_tests=0))


def collect(inputs, collector_refs, native_r2, clock, input_ref, *, deadline):
    validate_clock(clock)
    refs = expected_refs(inputs, collector_refs, native_r2)
    capture = HeldCapture([], list(refs), deadline)
    try:
        records = []
        for path, ref in sorted(refs.items()):
            entry = capture.capture(path, ref); sig = entry['signature']
            records.append(dict(path=path, bytes=entry['bytes'], sha256=entry['sha256'], signature=sig,
                                private=path in {v['path'] for v in inputs['private_account_inputs4'].values()},
                                unsafe_file_metadata=bool(sig[2] not in (0, os.getuid()) or sig[4] & 0o022),
                                capture='HELD_NOFOLLOW_BYTES_CURRENT_BINDING', startup_history='UNKNOWN_NOT_AUTHENTICATED'))
        buffers = {p: e['raw'] for p, e in capture.files.items()}
        data = derived(buffers, inputs, collector_refs, native_r2)
        capture.verify()
        ancestors = [dict(path=p, signature=v[3]) for p, v in sorted(capture.dirs.items())]
        packet = dict(schema=SCHEMA, assignment=inputs['assignment'], input_ref=input_ref,
                      clock=clock, records=records, ancestors=ancestors, unsafe_ancestors=capture.unsafe_ancestors(),
                      data=data, captured_files_count=len(records), captured_bytes=sum(r['bytes'] for r in records),
                      admission=False, independent_acceptance=False, runtime='UNBOUND_NOT_RUN', fullgate='NOT_RUN_NOT_ACCEPTED',
                      missing_proofs=list(GAPS), readonly_capture_verified=True)
        packet['payload_sha256'] = sha(canonical(packet))
        raw = canonical(packet); need(len(raw) <= MAX_PACKET, 'PACKET_BYTE_LIMIT')
        return raw, buffers, dict(signatures={p: list(e['signature']) for p, e in capture.files.items()}, ancestors={p: list(v[3]) for p, v in capture.dirs.items()})
    finally:
        capture.close()
