"""Strict bounded consumer for SOURCE inventory. No admission capability."""
import ast
import hashlib
import json
import math
import re
import stat
import struct

SCHEMA = 'friday.startup-closure-inventory.v1'
REQUIRED_GAPS = {
    'INDEPENDENT_WHOLE9_ACCEPTANCE', 'BEFORE_STARTUP_HELD_EXECUTION',
    'LOADED_CODE_AND_REFLECTION_CUSTODY', 'ELF_RELOCATION_IFUNC_VDSO',
    'OUTSIDE_OWNER_DESCENDANTS_AGGREGATE_CUSTODY',
    'UNFILTERED_NATIVE19_FINAL_SCHEMA_ACCOUNT_EXECUTION',
    'FINAL_IMMUTABLE_SNAPSHOT_POSITIVE_NEGATIVE_CLEANUP',
}


class Refusal(RuntimeError): pass


def need(ok, reason):
    if ok is not True: raise Refusal(reason)


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'DUPLICATE_JSON_KEY'); result[key] = value
    return result


def exact_keys(v, keys, reason):
    need(type(v) is dict and set(v) == set(keys), reason)


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'SHA256_FORMAT')


def strings(v, reason):
    need(type(v) is list and all(type(x) is str for x in v) and len(v) == len(set(v)), reason)


def dotted(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return dotted(node.value) + '.' + node.attr
    return '<computed>'


def consume(raw, *, expected_source, expected_roots, expected_modules, expected_deadline,
            held_bytes, now_monotonic, held_metadata):
    need(type(raw) is bytes and 0 < len(raw) <= 8*1024**2, 'BOUNDED_INVENTORY_BYTES')
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda s: (_ for _ in ()).throw(Refusal('NONFINITE_JSON')))
    need(canonical(value) == raw, 'CANONICAL_EXACT_INVENTORY')
    exact_keys(value, ('schema','scope','admission','runtime','complete_observation','custody','roots','seeds','root_modules','nodes','edges','gaps','capture','original_deadline_monotonic','graph_sha256'), 'EXACT_INVENTORY_FIELDS')
    need(value['schema'] == SCHEMA and value['scope'] == 'SOURCE_ONLY' and value['admission'] is False
         and value['runtime'] == 'UNBOUND_NOT_RUN' and value['complete_observation'] is True, 'SOURCE_SCOPE_NO_GRANT')
    deadline = value['original_deadline_monotonic']
    need(type(deadline) in (int,float) and type(deadline) is not bool and math.isfinite(deadline)
         and type(now_monotonic) in (int,float) and type(now_monotonic) is not bool
         and math.isfinite(now_monotonic) and now_monotonic < deadline, 'LATE_OR_UNKNOWN_INVENTORY')
    need(type(expected_deadline) is type(deadline) and deadline == expected_deadline, 'ORIGINAL_DEADLINE_BINDING')
    need(type(held_bytes) is dict, 'INDEPENDENT_HELD_BUFFERS_REQUIRED')
    validate_metadata(held_metadata,held_bytes,expected_roots,expected_source)
    need(canonical(value['custody']) == canonical(held_metadata), 'INDEPENDENT_HELD_METADATA_JOIN')
    for key in ('roots','seeds','root_modules'): strings(value[key], 'EXACT_STRING_LIST:' + key)
    need(value['roots'] == expected_roots and value['seeds'] == sorted(expected_source)
         and value['root_modules'] == sorted(expected_modules), 'CONSUMER_ROOT_SEED_BINDING')
    need(type(value['nodes']) is list and 0 < len(value['nodes']) <= 1200, 'BOUNDED_NODES')
    need(type(value['edges']) is list and len(value['edges']) <= 24000
         and type(value['gaps']) is list and len(value['gaps']) <= 96000, 'BOUNDED_GRAPH')
    node_map = {}; total = 0; paths = {}; required_node_gaps = []
    for node in value['nodes']:
        exact_keys(node, ('name','kind','path','sha256','bytes','signature','package','static_imports','issues','elf'), 'EXACT_NODE_FIELDS')
        need(type(node['name']) is str and node['name'] and node['name'] not in node_map, 'UNIQUE_NODE')
        need(node['kind'] in ('python','json','elf','extension','builtin') and type(node['package']) is bool, 'NODE_KIND_PACKAGE')
        need(type(node['bytes']) is int and 0 <= node['bytes'] <= 16*1024**2, 'STRICT_NODE_BYTES')
        strings(node['issues'], 'NODE_ISSUES')
        need(type(node['static_imports']) is list, 'STATIC_IMPORTS_LIST')
        if node['kind'] == 'builtin':
            need(node['path'] is None and node['sha256'] is None and node['signature'] is None
                 and node['bytes'] == 0 and node['elf'] is None
                 and 'BUILTIN_STARTUP_CODE_UNBOUND' in node['issues'], 'BUILTIN_UNBOUND')
        else:
            path = node['path']; need(type(path) is str and path.startswith('/') and all(p not in ('','.','..') for p in path.split('/')[1:]), 'EXACT_NODE_PATH')
            digest(node['sha256']); sig = node['signature']
            buffer = held_bytes.get(path)
            need(type(buffer) is bytes and len(buffer) == node['bytes']
                 and hashlib.sha256(buffer).hexdigest() == node['sha256'], 'INDEPENDENT_HELD_BYTES_SHA')
            need(type(sig) is list and len(sig) == 9 and all(type(n) is int and n >= 0 for n in sig), 'STRICT_FILE_SIGNATURE')
            need(sig[6] == node['bytes'] and sig[5] == 1 and stat.S_ISREG(sig[4])
                 and not sig[4] & (stat.S_ISUID | stat.S_ISGID), 'FILE_SIZE_NLINK_MODE_JOIN')
            if path in paths: need(paths[path] == (node['sha256'],node['bytes'],sig), 'PATH_ALIAS_INCONSISTENCY')
            else: paths[path] = (node['sha256'],node['bytes'],sig); total += node['bytes']
            if node['name'] not in expected_source:
                need(any(path == r or path.startswith(r + '/') for r in expected_roots)
                     or any(ref['path'] == path for ref in expected_source.values()), 'NODE_OUTSIDE_PINNED_ROOTS')
            if node['kind'] in ('extension','elf'):
                elf = node['elf']
                exact_keys(elf, ('elf_class','byte_order','type','machine','pt_interp','needed','runpaths','dynamic_tags','writable_executable_segment','program_headers','relocation_ifunc_loaded_code','alias_custody','executed'), 'EXACT_ELF_FIELDS')
                need(type(elf['elf_class']) is int and elf['elf_class'] == 64 and elf['byte_order'] == 'little'
                     and all(type(elf[k]) is int and elf[k] >= 0 for k in ('type','machine'))
                     and type(elf['writable_executable_segment']) is bool, 'STRICT_ELF_TYPES')
                strings(elf['needed'],'ELF_NEEDED'); strings(elf['runpaths'],'ELF_RUNPATHS')
                need(type(elf['dynamic_tags']) is list and all(type(x) is int for x in elf['dynamic_tags']), 'ELF_DYNAMIC_TAGS')
                need(type(elf['program_headers']) is list and 0 < len(elf['program_headers']) < 4096, 'ELF_PROGRAM_HEADERS')
                for header in elf['program_headers']:
                    exact_keys(header, ('type','flags','offset','bytes'),'ELF_PROGRAM_HEADER_FIELDS')
                    need(all(type(x) is int and x >= 0 for x in header.values())
                         and header['offset'] + header['bytes'] <= len(buffer), 'ELF_PROGRAM_HEADER_BOUNDS')
                need(elf['pt_interp'] is None or (type(elf['pt_interp']) is str and elf['pt_interp'].startswith('/')), 'ELF_PT_INTERP_TYPE')
                need(node['elf'].get('executed') is False
                     and node['elf'].get('relocation_ifunc_loaded_code') == 'UNBOUND'
                     and node['elf'].get('alias_custody') == 'UNBOUND', 'ELF_UNBOUND')
                need(canonical(elf) == canonical(elf_inventory(buffer)), 'ELF_EXACT_HELD_BYTES_OBSERVATION_JOIN')
                required_node_gaps.append((node['name'], 'NATIVE_EXTENSION_EXECUTION_UNBOUND' if node['kind']=='extension' else 'ELF_STARTUP_EXECUTION_UNBOUND', None))
        for imp in node['static_imports']:
            exact_keys(imp, ('module','kind','line','symbols'), 'EXACT_IMPORT_FIELDS')
            need(type(imp['module']) is str and imp['kind'] in ('import','from')
                 and type(imp['line']) is int and imp['line'] > 0, 'STRICT_STATIC_IMPORT')
            strings(imp['symbols'], 'IMPORT_SYMBOLS')
        if node['kind'] == 'python':
            tree = ast.parse(held_bytes[node['path']], filename=node['name'])
            observed_imports = []
            package = node['name'] if node['package'] else node['name'].rpartition('.')[0]
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    observed_imports.extend(dict(module=a.name,kind='import',line=item.lineno,symbols=[]) for a in item.names)
                elif isinstance(item, ast.ImportFrom):
                    base = item.module or ''
                    if item.level:
                        required_node_gaps.append((node['name'],'RELATIVE_IMPORT',item.lineno))
                        parts = package.split('.') if package else []
                        if item.level > len(parts):
                            required_node_gaps.append((node['name'],'UNRESOLVED_RELATIVE_IMPORT',item.lineno)); continue
                        base = '.'.join(parts[:len(parts)-item.level+1]+([base] if base else []))
                    if base: observed_imports.append(dict(module=base,kind='from',line=item.lineno,symbols=[a.name for a in item.names]))
                elif isinstance(item, ast.Call):
                    target = dotted(item.func)
                    if target.split('.')[0] in ('__import__','eval','exec','compile','getattr','setattr','delattr','globals','locals','vars','importlib','runpy','ctypes','marshal'):
                        required_node_gaps.append((node['name'],'DYNAMIC_IMPORT_OR_REFLECTION:'+target,item.lineno))
                elif isinstance(item, ast.Attribute) and item.attr in ('__code__','__globals__','__builtins__','__loader__','__spec__','meta_path','path_hooks','modules'):
                    required_node_gaps.append((node['name'],'REFLECTION_OR_IMPORT_STATE:'+dotted(item),item.lineno))
            need(canonical(observed_imports) == canonical(node['static_imports']), 'STATIC_IMPORTS_MATCH_HELD_AST')
        node_map[node['name']] = node
    need(list(node_map) == sorted(node_map), 'CANONICAL_NODE_ORDER')
    for name, ref in expected_source.items():
        node = node_map.get(name); need(node is not None, 'MISSING_WHOLE9_OR_SEED:' + name)
        need(type(ref['bytes']) is int and node['path'] == ref['path'] and node['sha256'] == ref['sha256']
             and node['bytes'] == ref['bytes'], 'EXACT_WHOLE9_OR_SEED_PIN:' + name)
    gap_reasons = set()
    for gap in value['gaps']:
        need(type(gap) is dict and set(gap) <= {'owner','reason','line','target','path','library','cycle'}
             and set(('owner','reason')) <= set(gap) and type(gap['owner']) is str
             and type(gap['reason']) is str and bool(gap['reason']), 'EXACT_GAP')
        if 'line' in gap: need(type(gap['line']) is int and gap['line'] >= 0, 'GAP_LINE')
        for k in ('target','path','library'):
            if k in gap: need(type(gap[k]) is str, 'GAP_STRING')
        if 'cycle' in gap: need(type(gap['cycle']) is list and all(type(x) is str for x in gap['cycle']), 'GAP_CYCLE')
        gap_reasons.add(gap['reason'])
    need(REQUIRED_GAPS <= gap_reasons, 'MISSING_MANDATORY_UNBOUND_PROOF')
    proof_gaps = {(g['owner'],g['reason'],g.get('line')) for g in value['gaps']}
    for gap in required_node_gaps: need(gap in proof_gaps, 'INCOMPLETE_AST_NATIVE_PROOF_GAPS')
    for node in value['nodes']:
        for reason in node['issues']: need((node['name'],reason,None) in proof_gaps, 'MISSING_NODE_ISSUE_GAP')
    edges = {}
    for edge in value['edges']:
        exact_keys(edge, ('owner','target','kind','line','symbols','resolution'), 'EXACT_EDGE_FIELDS')
        need(type(edge['owner']) is str and (edge['owner'] in node_map or edge['owner'] == '<requested>')
             and type(edge['target']) is str and edge['target'] and type(edge['line']) is int
             and edge['line'] >= 0 and edge['kind'] in ('import','from','requested','package_parent','from_submodule')
             and edge['resolution'] in ('python','extension','builtin','UNBOUND'), 'STRICT_EDGE')
        strings(edge['symbols'], 'EDGE_SYMBOLS')
        if edge['resolution'] != 'UNBOUND': need(edge['target'] in node_map and node_map[edge['target']]['kind'] == edge['resolution'], 'MISSING_RESOLVED_EDGE_NODE')
        else: need(any(g['owner'] == edge['owner'] and g.get('target') == edge['target'] for g in value['gaps']), 'MISSING_EDGE_REFUSAL')
        edges.setdefault((edge['owner'],edge['target'],edge['kind'],edge['line'],tuple(edge['symbols'])),[]).append(edge)
    for node in value['nodes']:
        for imp in node['static_imports']:
            need((node['name'],imp['module'],imp['kind'],imp['line'],tuple(imp['symbols'])) in edges, 'INCOMPLETE_STATIC_GRAPH')
    for module in expected_modules:
        need(('<requested>',module,'requested',0,()) in edges, 'MISSING_REQUESTED_MODULE')
    # Cycles are facts in the static graph, never an implicit successful loader.
    adjacency = {name:set() for name in node_map}; active = []; visited = set()
    for edge in value['edges']:
        if edge['owner'] in adjacency and edge['target'] in node_map and edge['resolution'] != 'UNBOUND':
            adjacency[edge['owner']].add(edge['target'])
    def visit(name):
        if name in active:
            cycle = active[active.index(name):]
            need(any(g['reason']=='IMPORT_CYCLE' and g['owner'] in cycle for g in value['gaps']), 'INCOMPLETE_CYCLE_PROOF')
            return
        if name in visited: return
        active.append(name)
        for child in sorted(adjacency[name]): visit(child)
        active.pop(); visited.add(name)
    for name in sorted(adjacency): visit(name)
    capture = value['capture']
    exact_keys(capture, ('bytes','file_count','nofollow_held_fds','bindings_and_bytes_reverified','origin_bindings_current','target_imports','target_execution','startup_history_proven'), 'EXACT_CAPTURE_FIELDS')
    need(type(capture['bytes']) is int and capture['bytes'] == total and total <= 96*1024**2
         and type(capture['file_count']) is int and capture['file_count'] == len(paths), 'CAPTURE_TOTAL_JOIN')
    need(set(held_bytes) == set(paths), 'EXACT_HELD_BUFFER_CATALOG')
    need(type(capture['origin_bindings_current']) is bool and capture['origin_bindings_current']==(held_metadata['origin_scope']=='CURRENT_HELD_SOURCE_METADATA'),'ORIGIN_BINDING_SCOPE_JOIN')
    need(capture['nofollow_held_fds'] is True and capture['bindings_and_bytes_reverified'] is True
         and type(capture['target_imports']) is int and capture['target_imports'] == 0
         and type(capture['target_execution']) is int and capture['target_execution'] == 0
         and capture['startup_history_proven'] is False, 'NO_TARGET_EXECUTION_NO_STARTUP_PROOF')
    reconstructed = reconstruct(held_bytes,held_metadata,expected_source,expected_modules,deadline,now_monotonic)
    for field in ('nodes','edges','gaps'):
        need(canonical(value[field]) == canonical(reconstructed[field]), 'COMPLETE_DERIVED_'+field.upper())
    digest(value['graph_sha256'])
    graph = {k:value[k] for k in ('roots','seeds','root_modules','nodes','edges','gaps')}
    need(hashlib.sha256(canonical(graph)).hexdigest() == value['graph_sha256'], 'GRAPH_DIGEST')
    return dict(status='SOURCE_INVENTORY_VALIDATED', nodes=len(node_map), edges=len(value['edges']),
                gaps=len(value['gaps']), source_seed_pins=len(expected_source), admission=False,
                independent_acceptance=False, runtime='UNBOUND_NOT_RUN', graph_sha256=value['graph_sha256'])


def qualify(*args, **kwargs):
    consume(*args, **kwargs)
    raise Refusal('UNBOUND_INDEPENDENT_STARTUP_NATIVE19_AND_WHOLE9_ACCEPTANCE; SOURCE_ONLY')

MAX_FILE=16*1024**2
MAX_NODES=1200
MAX_EDGES=24000
MANDATORY_GAPS=tuple(('INDEPENDENT_WHOLE9_ACCEPTANCE', 'BEFORE_STARTUP_HELD_EXECUTION', 'LOADED_CODE_AND_REFLECTION_CUSTODY', 'ELF_RELOCATION_IFUNC_VDSO', 'OUTSIDE_OWNER_DESCENDANTS_AGGREGATE_CUSTODY', 'UNFILTERED_NATIVE19_FINAL_SCHEMA_ACCOUNT_EXECUTION', 'FINAL_IMMUTABLE_SNAPSHOT_POSITIVE_NEGATIVE_CLEANUP'))
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def exact_path(p):
    need(type(p) is str and p.startswith('/') and '\x00' not in p and all(x not in ('','.','..') for x in p.split('/')[1:]),'EXACT_ABSOLUTE_PATH')
    return p
def dotted(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return dotted(node.value) + '.' + node.attr
    return '<computed>'


def python_edges(raw, name, package):
    tree = ast.parse(raw, filename=name); edges = []; gaps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(dict(module=alias.name, kind='import', line=node.lineno, symbols=[]))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                gaps.append(dict(reason='RELATIVE_IMPORT', line=node.lineno))
                parts = package.split('.') if package else []
                if node.level > len(parts):
                    gaps.append(dict(reason='UNRESOLVED_RELATIVE_IMPORT', line=node.lineno)); continue
                base = '.'.join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
            if base:
                edges.append(dict(module=base, kind='from', line=node.lineno,
                                  symbols=[a.name for a in node.names]))
            else:
                gaps.append(dict(reason='EMPTY_IMPORT_ORIGIN', line=node.lineno))
        elif isinstance(node, ast.Call):
            target = dotted(node.func)
            if target.split('.')[0] in ('__import__', 'eval', 'exec', 'compile', 'getattr', 'setattr', 'delattr', 'globals', 'locals', 'vars', 'importlib', 'runpy', 'ctypes', 'marshal'):
                gaps.append(dict(reason='DYNAMIC_IMPORT_OR_REFLECTION:' + target, line=node.lineno))
        elif isinstance(node, ast.Attribute) and node.attr in ('__code__', '__globals__', '__builtins__', '__loader__', '__spec__', 'meta_path', 'path_hooks', 'modules'):
            gaps.append(dict(reason='REFLECTION_OR_IMPORT_STATE:' + dotted(node), line=node.lineno))
    # Static analysis cannot establish the absence of aliases/computed dispatch.
    return tree, edges, sorted(gaps, key=lambda g: (g['line'], g['reason']))


def elf_inventory(raw):
    need(len(raw) >= 64 and raw[:4] == b'\x7fELF' and raw[4] == 2 and raw[5] == 1
         and raw[6] == 1, 'SUPPORTED_ELF64_LITTLE_ENDIAN_ONLY')
    typ, machine = struct.unpack_from('<HH', raw, 16)
    phoff, shoff = struct.unpack_from('<QQ', raw, 32)
    ehsize, phsize, phnum, shsize, shnum = struct.unpack_from('<HHHHH', raw, 52)
    need(ehsize == 64 and phsize == 56 and 0 < phnum < 4096
         and phoff + phsize * phnum <= len(raw), 'ELF_PROGRAM_TABLE_BOUNDS')
    sections = []; interp = None; dynamic = None; loads = []; writable_exec = False
    for i in range(phnum):
        ptype, flags, offset, vaddr, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', raw, phoff + i * phsize)
        need(offset + size <= len(raw), 'ELF_SEGMENT_BOUNDS')
        sections.append(dict(type=ptype, flags=flags, offset=offset, bytes=size))
        if ptype == 1:
            loads.append((vaddr, offset, size)); writable_exec |= bool(flags & 1 and flags & 2)
        if ptype == 3:
            need(interp is None and 1 < size <= 4096, 'ONE_BOUNDED_PT_INTERP')
            value = raw[offset:offset+size]; need(value.endswith(b'\0') and b'\0' not in value[:-1], 'PT_INTERP_NUL')
            interp = value[:-1].decode('ascii'); exact_path(interp)
        if ptype == 2:
            need(dynamic is None and size % 16 == 0, 'ONE_DYNAMIC_TABLE'); dynamic = (offset, size)
    needed = []; runpaths = []; tags = []
    if dynamic:
        offset, size = dynamic; entries = []; terminated = False
        for at in range(offset, offset + size, 16):
            tag, value = struct.unpack_from('<qQ', raw, at)
            if tag == 0: terminated = True; break
            entries.append((tag, value)); tags.append(tag)
        need(terminated, 'DYNAMIC_TABLE_UNTERMINATED')
        strings = [v for t, v in entries if t == 5]; sizes = [v for t, v in entries if t == 10]
        if any(t in (1, 15, 29) for t, v in entries):
            need(len(strings) == len(sizes) == 1 and 0 < sizes[0] <= MAX_FILE, 'EXACT_ELF_STRTAB')
            matches = [off + strings[0] - va for va, off, sz in loads if va <= strings[0] and strings[0] + sizes[0] <= va + sz]
            need(len(matches) == 1, 'UNAMBIGUOUS_ELF_STRTAB_MAPPING')
            table = raw[matches[0]:matches[0]+sizes[0]]
            for tag, value in entries:
                if tag in (1, 15, 29):
                    need(value < len(table) and b'\0' in table[value:], 'ELF_STRING_BOUNDS')
                    text = table[value:table.index(b'\0', value)].decode('ascii')
                    (needed if tag == 1 else runpaths).append(text)
    need(shnum == 0 or (shsize == 64 and shoff + shsize * shnum <= len(raw)), 'ELF_SECTION_TABLE_BOUNDS')
    return dict(elf_class=64, byte_order='little', type=typ, machine=machine,
                pt_interp=interp, needed=needed, runpaths=runpaths, dynamic_tags=sorted(set(tags)),
                writable_executable_segment=writable_exec, program_headers=sections,
                relocation_ifunc_loaded_code='UNBOUND', alias_custody='UNBOUND', executed=False)



def validate_metadata(m,buffers,roots,seeds):
    exact_keys(m,('origin_scope','observer_uid','roots','exact_files','builtins','explicit_modules','files','directories','scans'),'EXACT_CUSTODY_FIELDS')
    need(m['origin_scope'] in ('CURRENT_HELD_SOURCE_METADATA','PINNED_CAPTURED_METADATA_NOT_CURRENT_ORIGIN_BINDING'),'CUSTODY_ORIGIN_SCOPE')
    need(type(m['observer_uid']) is int and m['observer_uid']>=0,'CUSTODY_UID')
    need(m['roots']==roots,'CUSTODY_ROOTS')
    for k in ('roots','exact_files','builtins'): strings(m[k],'CUSTODY_STRINGS')
    for p in m['roots']+m['exact_files']:exact_path(p)
    need(type(m['explicit_modules']) is dict and all(type(k) is str and type(v) is str for k,v in m['explicit_modules'].items()),'CUSTODY_MODULES')
    for p in m['explicit_modules'].values():exact_path(p)
    need(type(m['files']) is dict and set(m['files'])==set(buffers),'CUSTODY_FILE_CATALOG')
    need(type(m['directories']) is dict and '/' in m['directories'] and len(m['directories'])<=20000,'CUSTODY_DIRECTORIES')
    for p,sig in m['directories'].items():
        exact_path(p) if p!='/' else None
        need(type(sig) is list and len(sig)==5 and all(type(x) is int and x>=0 for x in sig) and stat.S_ISDIR(sig[4]),'CUSTODY_DIRECTORY_SIGNATURE')
        need(p=='/' or (p.rsplit('/',1)[0] or '/') in m['directories'],'CUSTODY_ANCESTOR_CHAIN')
    for p,sig in m['files'].items():
        exact_path(p)
        need(type(sig) is list and len(sig)==9 and all(type(x) is int and x>=0 for x in sig),'CUSTODY_FILE_SIGNATURE')
        need(stat.S_ISREG(sig[4]) and sig[5]==1 and sig[6]==len(buffers[p]) and not sig[4]&(stat.S_ISUID|stat.S_ISGID),'CUSTODY_SAFE_REGULAR')
        need((p.rsplit('/',1)[0] or '/') in m['directories'],'CUSTODY_FILE_PARENT')
    need(type(m['scans']) is dict,'CUSTODY_SCANS')
    for p,names in m['scans'].items():
        need(p in m['directories'] and any(p==r or p.startswith(r+'/') for r in roots),'CUSTODY_SCAN_SCOPE')
        strings(names,'CUSTODY_SCAN_NAMES')
        need(names==sorted(names) and len(names)<=20000 and all(x and '/' not in x and x not in ('.','..') for x in names),'CUSTODY_SCAN_ORDER')

class _Snapshot:
    def __init__(self,buffers,m,deadline,now):
        self.origin_scope=m['origin_scope'];self.buffers=buffers;self.m=m;self.uid=m['observer_uid'];self.roots=m['roots'];self.exact_files=m['exact_files'];self.deadline=deadline;self.now=now
        self.files={};self.total=0;self.dirs={p:(None,None,None,s) for p,s in m['directories'].items()};self.scans=m['scans']
    def clock(self):need(type(self.deadline) in (int,float) and math.isfinite(self.deadline) and self.now<self.deadline,'LATE_INVENTORY')
    def allowed(self,p):return p in self.exact_files or any(p==r or p.startswith(r+'/') for r in self.roots)
    def names(self,p):
        need(any(p==r or p.startswith(r+'/') for r in self.roots),'SCAN_OUTSIDE_ROOTS')
        if p not in self.scans:raise FileNotFoundError(2,'No such file or directory')
        return self.scans[p]
    def exists(self,p):
        need(self.allowed(p),'LOOKUP_OUTSIDE_ROOTS');parent,name=p.rsplit('/',1)
        try:return name in self.names(parent)
        except (FileNotFoundError,NotADirectoryError):return False
    def capture(self,p,expected=None):
        self.clock();need(self.allowed(p),'OUTSIDE_PINNED_ROOTS:'+p)
        need(p in self.buffers,'MISSING_HELD_RESOLVED_ORIGIN:'+p)
        if p not in self.files:
            b=self.buffers[p];e=dict(raw=b,path=p,signature=self.m['files'][p],sha256=sha(b),bytes=len(b));self.files[p]=e;self.total+=len(b)
        e=self.files[p]
        if expected is not None:need(e['sha256']==expected['sha256'] and e['bytes']==expected['bytes'],'PIN_CHANGED:'+p)
        return e
    def verify(self):self.clock();return True
    def unsafe_ancestors(self):return sorted(p for p,s in self.m['directories'].items() if s[2] not in (0,self.uid) or s[4]&(0o022|stat.S_ISUID|stat.S_ISGID))

def reconstruct(buffers,m,seeds,modules,deadline,now):
    c=_Snapshot(buffers,m,deadline,now);g=_Reconstructor(c,builtins=m['builtins'],explicit_modules=m['explicit_modules'])
    result=g.collect(seeds,modules)
    need(set(c.files)==set(buffers),'COMPLETE_RECONSTRUCTED_BUFFER_CATALOG')
    return result
class _Reconstructor:
    def __init__(self, capture, *, builtins=(), explicit_modules=None):
        self.capture = capture; self.builtins = frozenset(builtins)
        self.explicit_modules = dict(explicit_modules or {})
        self.nodes = {}; self.edges = []; self.gaps = []; self.visiting = []; self.done = set()
        self.module_paths = {}; self.seeds = []; self.root_modules = []

    def gap(self, owner, reason, **data):
        self.capture.clock()
        need(len(self.gaps) < 96000, 'GAP_LIMIT')
        self.gaps.append(dict(owner=owner, reason=reason, **data))

    def resolve(self, module):
        self.capture.clock()
        need(type(module) is str and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)*', module) is not None, 'MODULE_NAME')
        candidates = []
        if module in self.explicit_modules:
            candidates.append((self.explicit_modules[module], False, 'python'))
        for root in self.capture.roots:
            stem = root + '/' + module.replace('.', '/')
            for path, package in ((stem + '.py', False), (stem + '/__init__.py', True)):
                if self.capture.exists(path): candidates.append((path, package, 'python'))
            parent, base = stem.rsplit('/', 1)
            try:
                for filename in self.capture.names(parent):
                    if (filename == base + '.so' or filename.startswith(base + '.')) and filename.endswith('.so'):
                        candidates.append((parent + '/' + filename, False, 'extension'))
            except (FileNotFoundError, NotADirectoryError): pass
        if len(candidates) > 1: raise Refusal('AMBIGUOUS_MODULE_ORIGIN:' + module)
        if candidates: return candidates[0]
        if module in self.builtins: return (None, False, 'builtin')
        raise Refusal('MISSING_EXPLICIT_IMPORT:' + module)

    def add_edge(self, owner, module, kind, line=0, symbols=None):
        need(len(self.edges) < MAX_EDGES, 'EDGE_LIMIT'); self.capture.clock()
        row = dict(owner=owner, target=module, kind=kind, line=line, symbols=symbols or [], resolution='PENDING')
        self.edges.append(row)
        try:
            path, package, typ = self.resolve(module)
            row['resolution'] = typ; self.module_paths[module] = path
            if typ == 'builtin':
                need(module in self.nodes or len(self.nodes) < MAX_NODES, 'NODE_LIMIT')
                self.nodes.setdefault(module, dict(name=module, kind='builtin', path=None, sha256=None, bytes=0,
                     signature=None, package=False, static_imports=[], issues=['BUILTIN_STARTUP_CODE_UNBOUND'], elf=None))
                self.gap(module, 'BUILTIN_STARTUP_CODE_UNBOUND'); return
            self.visit(module, path, package, typ)
            # Parent package initializers are executable dependency edges.
            for end in range(1, len(module.split('.'))):
                parent = '.'.join(module.split('.')[:end])
                if parent != owner and not any(e['owner'] == module and e['target'] == parent and e['kind'] == 'package_parent' for e in self.edges):
                    self.add_edge(module, parent, 'package_parent')
            if kind == 'from' and package:
                for symbol in symbols or []:
                    if symbol == '*': self.gap(owner, 'STAR_IMPORT_SYMBOL_GRAPH', line=line); continue
                    child = module + '.' + symbol
                    try: self.resolve(child)
                    except Refusal as e:
                        if str(e).startswith('MISSING_EXPLICIT_IMPORT:'):
                            self.gap(owner, 'FROM_SYMBOL_BINDING_UNPROVEN:' + child, line=line); continue
                        raise
                    self.add_edge(owner, child, 'from_submodule', line)
        except (Refusal, OSError, SyntaxError, UnicodeError, ValueError) as e:
            if isinstance(e,Refusal) and str(e) in ('NODE_LIMIT','EDGE_LIMIT','LATE_INVENTORY','AGGREGATE_BYTE_LIMIT','CAPTURE_ALREADY_CLOSED'):
                raise
            row['resolution'] = 'UNBOUND'; self.gap(owner, type(e).__name__ + ':' + str(e), target=module, line=line)

    def visit(self, name, path, package=False, kind='python', expected=None):
        self.capture.clock()
        if name in self.visiting:
            self.gap(name, 'IMPORT_CYCLE', cycle=self.visiting[self.visiting.index(name):] + [name]); return
        if name in self.done:
            need(self.nodes[name]['path'] == path, 'MODULE_ALIAS_REPLACEMENT:' + name); return
        need(len(self.nodes) < MAX_NODES, 'NODE_LIMIT'); entry = self.capture.capture(path, expected)
        raw = entry['raw']; issues = []
        node = dict(name=name, kind=kind, path=path, sha256=entry['sha256'], bytes=entry['bytes'],
                    signature=entry['signature'], package=package, static_imports=[], issues=issues, elf=None)
        self.nodes[name] = node; self.visiting.append(name)
        try:
            if entry['signature'][4] & 0o022: issues.append('GROUP_OR_WORLD_WRITABLE_FILE')
            if entry['signature'][2] not in (0, self.capture.uid): issues.append('UNKNOWN_FILE_OWNER')
            if raw.startswith(b'\x7fELF') or kind in ('elf', 'extension'):
                node['elf'] = elf_inventory(raw)
                issues.append('NATIVE_EXTENSION_EXECUTION_UNBOUND' if kind == 'extension' else 'ELF_STARTUP_EXECUTION_UNBOUND')
                for alias in ([node['elf']['pt_interp']] if node['elf']['pt_interp'] else []):
                    self.gap(name, 'PT_INTERP_ALIAS_NOT_HELD_BEFORE_STARTUP', path=alias)
                for library in node['elf']['needed']: self.gap(name, 'DT_NEEDED_ORIGIN_RELOCATION_UNBOUND', library=library)
            elif kind == 'json': json.loads(raw)
            else:
                _, imports, found = python_edges(raw, name, name if package else name.rpartition('.')[0])
                node['static_imports'] = imports
                for issue in found: self.gap(name, **issue)
                for item in imports: self.add_edge(name, item['module'], item['kind'], item['line'], item['symbols'])
            for reason in issues: self.gap(name, reason)
        finally:
            self.visiting.pop(); self.done.add(name)

    def metadata(self):
        self.capture.verify()
        return dict(origin_scope=getattr(self.capture,'origin_scope','CURRENT_HELD_SOURCE_METADATA'), observer_uid=self.capture.uid, roots=list(self.capture.roots),
            exact_files=sorted(self.capture.exact_files), builtins=sorted(self.builtins),
            explicit_modules=self.explicit_modules,
            files={p:e['signature'] for p,e in sorted(self.capture.files.items())},
            directories={p:e[3] for p,e in sorted(self.capture.dirs.items())},
            scans={p:names for p,names in sorted(self.capture.scans.items())})

    def collect(self, seeds, modules=()):
        need(type(seeds) is dict and seeds and len(seeds) <= 64, 'EXPLICIT_PINNED_SEEDS')
        self.seeds = sorted(seeds); self.root_modules = sorted(modules)
        for name, ref in sorted(seeds.items()):
            kind = 'json' if ref['path'].endswith('.json') else 'elf' if name == 'actual_interpreter' else 'python'
            self.visit(name, ref['path'], kind=kind, expected=ref)
        for module in sorted(modules): self.add_edge('<requested>', module, 'requested')
        self.capture.verify()
        for path in self.capture.unsafe_ancestors(): self.gap('<ancestors>', 'UNSAFE_OWNER_OR_GROUP_WORLD_WRITABLE_ANCESTOR', path=path)
        for reason in MANDATORY_GAPS: self.gap('<qualification>', reason)
        payload = dict(schema=SCHEMA, scope='SOURCE_ONLY', admission=False, runtime='UNBOUND_NOT_RUN',
                       complete_observation=True, custody=self.metadata(), roots=list(self.capture.roots), seeds=self.seeds,
                       root_modules=self.root_modules, nodes=sorted(self.nodes.values(), key=lambda n:n['name']),
                       edges=self.edges, gaps=self.gaps, capture=dict(bytes=self.capture.total,
                       file_count=len(self.capture.files), nofollow_held_fds=True,
                       bindings_and_bytes_reverified=True,
                       origin_bindings_current=getattr(self.capture,'origin_scope','CURRENT_HELD_SOURCE_METADATA')=='CURRENT_HELD_SOURCE_METADATA', target_imports=0, target_execution=0,
                       startup_history_proven=False), original_deadline_monotonic=self.capture.deadline)
        payload['graph_sha256'] = sha(canonical({k:payload[k] for k in ('roots','seeds','root_modules','nodes','edges','gaps')}))
        return payload

