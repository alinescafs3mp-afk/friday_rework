"""Read-only held-FD static inventory. This module grants no execution authority.

The supplied roots and exact seed files are the complete read authority. No
import resolver, target import, loader hook, package metadata execution, or ELF
execution occurs. Observations are deliberately distinct from qualification.
"""
import ast
import hashlib
import json
import math
import os
import re
import stat
import struct
import time

SCHEMA = 'friday.startup-closure-inventory.v1'
MAX_FILE = 16 * 1024**2
MAX_TOTAL = 96 * 1024**2
MAX_NODES = 1200
MAX_EDGES = 24000
MANDATORY_GAPS = (
    'INDEPENDENT_WHOLE9_ACCEPTANCE', 'BEFORE_STARTUP_HELD_EXECUTION',
    'LOADED_CODE_AND_REFLECTION_CUSTODY', 'ELF_RELOCATION_IFUNC_VDSO',
    'OUTSIDE_OWNER_DESCENDANTS_AGGREGATE_CUSTODY',
    'UNFILTERED_NATIVE19_FINAL_SCHEMA_ACCOUNT_EXECUTION',
    'FINAL_IMMUTABLE_SNAPSHOT_POSITIVE_NEGATIVE_CLEANUP',
)


class Refusal(RuntimeError):
    pass


def need(ok, reason):
    if ok is not True:
        raise Refusal(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_path(path):
    need(type(path) is str and path.startswith('/') and '\x00' not in path
         and all(p not in ('', '.', '..') for p in path.split('/')[1:]), 'EXACT_ABSOLUTE_PATH')
    return path


def file_signature(st):
    return [st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def dir_signature(st):
    return [st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode]


def read_fd(fd, limit=MAX_FILE):
    need(type(limit) is int and 0 < limit <= MAX_FILE, 'FILE_LIMIT')
    pieces = []; offset = 0
    while offset <= limit:
        piece = os.pread(fd, min(65536, limit + 1 - offset), offset)
        if not piece:
            return b''.join(pieces)
        pieces.append(piece); offset += len(piece)
    raise Refusal('FILE_TOO_LARGE')


class HeldCapture:
    """Retains root-through-parent nofollow handles and rechecks every binding.

    Unsafe owner/mode is recorded as missing qualification, never sanitized.
    Hard links, symlinks, special files, drift and bounds violations refuse the
    capture. Content discovered under roots is observational, not an owner pin.
    """
    def __init__(self, roots, exact_files, deadline, *, max_total=MAX_TOTAL):
        need(type(roots) is list and type(exact_files) is list, 'EXPLICIT_ROOTS_FILES')
        self.roots = tuple(exact_path(p) for p in roots)
        self.exact_files = frozenset(exact_path(p) for p in exact_files)
        need(type(deadline) in (int, float) and type(deadline) is not bool
             and math.isfinite(deadline) and deadline > time.monotonic(), 'ORIGINAL_USEFUL_DEADLINE')
        need(type(max_total) is int and 0 < max_total <= MAX_TOTAL, 'AGGREGATE_BYTE_LIMIT')
        self._deadline = deadline; self.max_total = max_total
        self.dirs = {}; self.files = {}; self.scans = {}; self.total = 0; self.closed = False
        try:
            for root in self.roots:
                self.directory(root)
        except BaseException:
            self.close(); raise

    @property
    def deadline(self):
        return self._deadline

    def clock(self):
        need(not self.closed, 'CAPTURE_ALREADY_CLOSED')
        need(type(self.deadline) in (int,float) and math.isfinite(self.deadline)
             and time.monotonic() < self.deadline, 'LATE_INVENTORY')

    def allowed(self, path):
        return path in self.exact_files or any(path == r or path.startswith(r + '/') for r in self.roots)

    def directory(self, path):
        self.clock()
        if path in self.dirs:
            return self.dirs[path][0]
        if path == '/':
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.dirs['/'] = (fd, None, None, dir_signature(os.fstat(fd)))
            return fd
        exact_path(path)
        parent, name = path.rsplit('/', 1); parent = parent or '/'
        pfd = self.directory(parent)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=pfd)
        self.dirs[path] = (fd, pfd, name, dir_signature(os.fstat(fd)))
        return fd

    def capture(self, path, expected=None):
        self.clock(); exact_path(path); need(self.allowed(path), 'OUTSIDE_PINNED_ROOTS:' + path)
        if path in self.files:
            entry = self.files[path]
        else:
            need(len(self.files) < MAX_NODES, 'NODE_LIMIT')
            parent, name = path.rsplit('/', 1); pfd = self.directory(parent or '/')
            # Hold metadata without opening a device/FIFO for data. Only the
            # exact verified regular inode is then opened via its owned O_PATH FD.
            mfd = os.open(name, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=pfd)
            fd = None
            try:
                st = os.fstat(mfd)
                need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                     and not st.st_mode & (stat.S_ISUID | stat.S_ISGID), 'REGULAR_SINGLE_LINK_FILE')
                self.clock()
                fd = os.open('/proc/' + str(os.getpid()) + '/fd/' + str(mfd),
                             os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
                need(file_signature(os.fstat(fd)) == file_signature(st), 'METADATA_BYTE_FD_JOIN')
                need(file_signature(os.stat(name,dir_fd=pfd,follow_symlinks=False)) == file_signature(st), 'METADATA_ALIAS_DRIFT')
                need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                     and not st.st_mode & (stat.S_ISUID | stat.S_ISGID), 'REGULAR_SINGLE_LINK_FILE')
                need(st.st_size <= MAX_FILE, 'FILE_TOO_LARGE')
                raw = read_fd(fd); signature = file_signature(st)
                need(file_signature(os.fstat(fd)) == signature, 'CAPTURE_CHANGED_DURING_READ')
                need(self.total + len(raw) <= self.max_total, 'AGGREGATE_BYTE_LIMIT')
                entry = dict(fd=fd, parent_fd=pfd, name=name, raw=raw, signature=signature,
                             path=path, sha256=sha(raw), bytes=len(raw))
                self.files[path] = entry; self.total += len(raw)
            except BaseException:
                if fd is not None: os.close(fd)
                raise
            finally:
                os.close(mfd)
        if expected is not None:
            need(type(expected) is dict and entry['sha256'] == expected.get('sha256')
                 and type(expected.get('bytes')) is int and entry['bytes'] == expected['bytes'], 'PIN_CHANGED:' + path)
        self.clock()
        return entry

    def names(self, path):
        need(any(path == r or path.startswith(r + '/') for r in self.roots), 'SCAN_OUTSIDE_ROOTS')
        fd = self.directory(path); self.clock()
        values = sorted(os.listdir(fd)); need(len(values) <= 20000, 'DIRECTORY_ENTRY_LIMIT')
        old = self.scans.setdefault(path, values)
        need(old == values, 'ALIAS_DIRECTORY_DRIFT:' + path)
        return values

    def exists(self, path):
        need(self.allowed(path), 'LOOKUP_OUTSIDE_ROOTS')
        parent, name = path.rsplit('/', 1)
        try:
            return name in self.names(parent)
        except (FileNotFoundError, NotADirectoryError):
            return False

    def unsafe_ancestors(self):
        self.clock()
        return sorted(p for p, (_, _, _, sig) in self.dirs.items()
                      if sig[2] not in (0, os.getuid()) or sig[4] & (0o022 | stat.S_ISUID | stat.S_ISGID))

    def verify(self):
        self.clock()
        for path, (fd, pfd, name, signature) in self.dirs.items():
            need(dir_signature(os.fstat(fd)) == signature, 'ANCESTOR_FD_DRIFT:' + path)
            if pfd is not None:
                need(dir_signature(os.stat(name, dir_fd=pfd, follow_symlinks=False)) == signature,
                     'ANCESTOR_ALIAS_DRIFT:' + path)
        for path, entry in self.files.items():
            need(file_signature(os.fstat(entry['fd'])) == entry['signature'], 'HELD_FILE_DRIFT:' + path)
            need(file_signature(os.stat(entry['name'], dir_fd=entry['parent_fd'], follow_symlinks=False)) == entry['signature'], 'FILE_ALIAS_DRIFT:' + path)
            need(sha(read_fd(entry['fd'])) == entry['sha256'], 'HELD_BYTES_DRIFT:' + path)
        for path, values in self.scans.items():
            need(sorted(os.listdir(self.dirs[path][0])) == values, 'RESOLUTION_DIRECTORY_DRIFT:' + path)
        self.clock()
        return True

    def close(self):
        errors = []
        for entry in self.files.values():
            try: os.close(entry['fd'])
            except OSError as e: errors.append(str(e))
        for fd, _, _, _ in reversed(tuple(self.dirs.values())):
            try: os.close(fd)
            except OSError as e: errors.append(str(e))
        self.files.clear(); self.dirs.clear(); self.closed = True
        need(not errors, 'CAPTURE_FD_CLOSE_UNCONFIRMED:' + repr(errors))


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


class GraphCollector:
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
            if entry['signature'][2] not in (0, os.getuid()): issues.append('UNKNOWN_FILE_OWNER')
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
        return dict(origin_scope=getattr(self.capture,'origin_scope','CURRENT_HELD_SOURCE_METADATA'), observer_uid=os.getuid(), roots=list(self.capture.roots),
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


def native19_inventory(validator_raw, compatibility_raw, audit_raw, seeds):
    """Read AST/data only. Nineteen *control inputs*, not 19 passed test cases."""
    tree = ast.parse(validator_raw); controls = []; required = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if 'VALIDATION_CONTROL_PATHS' in names and isinstance(node.value, ast.Dict):
                controls = [ast.literal_eval(key) for key in node.value.keys]
            if 'REQUIRED_METHODS' in names: required = sorted(ast.literal_eval(node.value))
    proof = json.loads(compatibility_raw); audit = json.loads(audit_raw)
    need(len(controls) == 19 and len(set(controls)) == 19, 'EXACT_NATIVE19_CONTROL_COLLECTION')
    need(type(proof.get('validation_controls_sha256')) is dict, 'CURRENT_COMPATIBILITY_CONTROLS')
    rows = []
    aliases = {'updater':'native19_validator', 'native_endpoint':'installed_native_endpoint', 'lifecycle':'installed_lifecycle'}
    for label in controls:
        seed = seeds.get(aliases.get(label, ''))
        rows.append(dict(name=label, compatibility_sha256=proof['validation_controls_sha256'].get(label),
                         authorized_current_pin=seed,
                         pin_matches_compatibility=seed['sha256'] == proof['validation_controls_sha256'].get(label) if seed else None,
                         capture_scope='EXACT_TASK_INPUT' if seed else 'OUTSIDE_TASK_PINNED_ROOTS_NOT_CAPTURED',
                         execution='NOT_RUN', acceptance=False))
    return dict(schema='friday.native19-source-input-inventory.v1', count=19, controls=rows,
                required_methods=required, compatibility_methods=proof.get('required_rpc_methods'),
                required_methods_match=required == sorted(proof.get('required_rpc_methods', [])),
                rpc_case_counts=proof.get('rpc_contract_case_counts'),
                account_graph=dict(paths=audit.get('account_paths'), baseline_hashes=audit.get('expected_baseline',{}).get('account_input_sha256'),
                                   reads=0, status='UNBOUND_NO_CURRENT_TASK_PINNED_ACCOUNT_CAPTURE'),
                schema_graph=dict(generation='NOT_RUN', final_ClientRequest='NOT_PROVIDED', status='UNBOUND'),
                deferred_paths=audit.get('future_evidence_paths'),
                full_validation_execution='NOT_RUN', historical_compatibility_only=True, admission=False)
