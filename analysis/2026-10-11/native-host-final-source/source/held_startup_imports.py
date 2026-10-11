"""Finite Python/Linux source custody component. SOURCE_ONLY; no admission API.

The importer supports retained pure Python modules/packages and explicitly
qualified existing builtins/frozen modules. It refuses extension execution,
runpy/importlib/ctypes graph escapes and incomplete dynamic manifests. Host
observations do not authenticate bytes already relocated/executed at startup.
No native target is imported by this component's controls.
"""
import os
import sys
import stat
import hashlib
import types
import ast
import builtins


class Unbound(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Unbound(reason)


def bounded_fd(fd, limit):
    require(type(limit) is int and 0 < limit <= 128 * 1024**2, 'BOUNDED_FD_REQUIRED')
    pieces = []; offset = 0
    while offset <= limit:
        part = os.pread(fd, min(65536, limit + 1 - offset), offset)
        if not part:
            return b''.join(pieces)
        pieces.append(part); offset += len(part)
    raise Unbound('FILE_SIZE_LIMIT')


def signature(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def directory_signature(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode)


class HeldFile:
    """Keep all ancestor FDs and original regular-file bytes, with nofollow.

    Names are revalidated using O_NOFOLLOW, but execution never rereads a
    pathname. An immutable expected SHA comes from independent outer custody.
    """
    def __init__(self, path, expected_sha256, *, owners, mode, limit=8*1024**2):
        require(type(path) is str and path.startswith('/') and '\x00' not in path,
                'EXACT_ABSOLUTE_PATH_REQUIRED')
        parts = path.split('/')[1:]
        require(parts and all(p not in ('', '.', '..') for p in parts), 'CANONICAL_PATH_REQUIRED')
        require(type(expected_sha256) is str and len(expected_sha256) == 64
                and all(c in '0123456789abcdef' for c in expected_sha256), 'EXACT_SHA_REQUIRED')
        require(type(owners) in (tuple, frozenset) and owners
                and all(type(u) is int and u >= 0 for u in owners), 'EXACT_OWNER_SET_REQUIRED')
        require(type(mode) is int and not mode & 0o7022, 'SAFE_EXACT_MODE_REQUIRED')
        self.path = path; self.parts = tuple(parts); self.owners = frozenset(owners)
        self.mode = mode; self.limit = limit; self.fds = []; self.closed = False
        self.expected_sha256 = expected_sha256
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            self.fds.append(fd); self.ancestors = [self._safe_dir(fd)]
            for name in parts[:-1]:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=fd)
                self.fds.append(fd); self.ancestors.append(self._safe_dir(fd))
            self.fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            self.fds.append(self.fd)
            st = os.fstat(self.fd)
            require(stat.S_ISREG(st.st_mode) and st.st_uid in self.owners
                    and st.st_nlink == 1 and stat.S_IMODE(st.st_mode) == mode,
                    'SAFE_OWNED_REGULAR_FILE_REQUIRED')
            self.signature = signature(st); self.raw = bounded_fd(self.fd, limit)
            require(hashlib.sha256(self.raw).hexdigest() == expected_sha256, 'STALE_SHA')
            self.verify()
        except BaseException:
            self.close(); raise

    def _safe_dir(self, fd):
        st = os.fstat(fd)
        require(stat.S_ISDIR(st.st_mode) and st.st_uid in self.owners
                and not st.st_mode & (0o022 | stat.S_ISUID | stat.S_ISGID),
                'UNSAFE_ANCESTOR_OWNER_OR_MODE')
        return directory_signature(st)

    @classmethod
    def from_received_fds(cls, path, expected_sha256, *, ancestor_fds, file_fd,
                          expected_signature, owners, mode, limit=8*1024**2):
        """Duplicate already-authenticated SCM_RIGHTS FDs; never infer authority.

        Caller must authenticate sender/receiver birth, private channel and
        manifest before this call. Ancestors are root through direct parent,
        not reconstructed from an untrusted receipt. Namespace is reverified.
        """
        require(type(path) is str and path.startswith('/') and '\x00' not in path,
                'EXACT_RECEIVED_PATH_REQUIRED')
        parts = path.split('/')[1:]
        require(parts and all(p not in ('', '.', '..') for p in parts)
                and type(ancestor_fds) is tuple and len(ancestor_fds) == len(parts)
                and all(type(fd) is int and fd >= 0 for fd in ancestor_fds)
                and type(file_fd) is int and file_fd >= 0,
                'EXACT_RECEIVED_ANCESTOR_CHAIN_REQUIRED')
        require(type(expected_signature) is tuple and len(expected_signature) == 9
                and type(expected_sha256) is str and len(expected_sha256) == 64
                and all(c in '0123456789abcdef' for c in expected_sha256)
                and type(owners) in (tuple, frozenset) and owners
                and all(type(u) is int and u >= 0 for u in owners)
                and type(mode) is int and not mode & 0o7022,
                'EXACT_RECEIVED_MANIFEST_REQUIRED')
        self = object.__new__(cls)
        self.path = path; self.parts = tuple(parts); self.owners = frozenset(owners)
        self.mode = mode; self.limit = limit; self.fds = []; self.closed = False
        self.expected_sha256 = expected_sha256
        try:
            for fd in ancestor_fds: self.fds.append(os.dup(fd))
            self.ancestors = [self._safe_dir(fd) for fd in self.fds]
            self.fd = os.dup(file_fd); self.fds.append(self.fd)
            st = os.fstat(self.fd)
            require(signature(st) == expected_signature and stat.S_ISREG(st.st_mode)
                    and st.st_uid in self.owners and st.st_nlink == 1
                    and stat.S_IMODE(st.st_mode) == mode, 'RECEIVED_FD_SIGNATURE_MISMATCH')
            self.signature = expected_signature; self.raw = bounded_fd(self.fd, limit)
            require(hashlib.sha256(self.raw).hexdigest() == expected_sha256, 'RECEIVED_SHA_MISMATCH')
            self.verify()
            return self
        except BaseException:
            self.close(); raise

    def verify(self):
        require(not self.closed, 'CLOSED_FILE')
        require(signature(os.fstat(self.fd)) == self.signature
                and bounded_fd(self.fd, self.limit) == self.raw, 'HELD_INODE_OR_BYTES_DRIFT')
        require([self._safe_dir(fd) for fd in self.fds[:-1]] == self.ancestors,
                'HELD_ANCESTOR_DRIFT')
        fresh = []
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); fresh.append(fd)
            require(self._safe_dir(fd) == self.ancestors[0], 'ROOT_NAMESPACE_DRIFT')
            for index, name in enumerate(self.parts[:-1], 1):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=fd); fresh.append(fd)
                require(self._safe_dir(fd) == self.ancestors[index], 'ANCESTOR_NAMESPACE_DRIFT')
            fd = os.open(self.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=fd); fresh.append(fd)
            require(signature(os.fstat(fd)) == self.signature, 'FILE_NAMESPACE_DRIFT')
        finally:
            for fd in reversed(fresh):
                os.close(fd)
        return self.expected_sha256

    def close(self):
        if not self.closed:
            self.closed = True
            for fd in reversed(self.fds):
                os.close(fd)
            self.fds.clear()


def absolute_import(name, package, level):
    if not level:
        return name
    require(type(package) is str and package, 'RELATIVE_PACKAGE_REQUIRED')
    pieces = package.split('.')
    require(level <= len(pieces), 'RELATIVE_IMPORT_ABOVE_ROOT')
    return '.'.join(pieces[:len(pieces)-level+1] + ([name] if name else []))


ESCAPES = frozenset({'runpy', 'importlib', 'ctypes', 'cffi', 'pkgutil'})
CALL_ESCAPES = frozenset({'exec', 'eval', 'compile', '__import__', 'import_module',
                          'run_path', 'run_module', 'exec_module', 'load_module',
                          'CDLL', 'PyDLL', 'dlopen'})


def source_import_audit(raw, module_name, package):
    """Static evidence ONLY, never a completeness claim for arbitrary Python."""
    tree = ast.parse(raw, filename='<held:' + module_name + '>')
    imports = set(); gaps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(absolute_import(node.module or '', package, node.level))
            if any(alias.name == '*' for alias in node.names):
                gaps.append('STAR_IMPORT')
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else '')
            if name in CALL_ESCAPES:
                gaps.append('DYNAMIC_CALL:' + name)
    for name in imports:
        if name.split('.')[0] in ESCAPES:
            gaps.append('DYNAMIC_LOADER:' + name)
    return {'static_imports': sorted(imports), 'dynamic_gaps': sorted(set(gaps)),
            'completeness': 'AST_IS_NOT_EXHAUSTIVE; manual exact manifest required'}


def python_function_state(values, module_name=None):
    """Retain executable Python functions, including descriptor wrappers.

    Container contents, arbitrary callable objects and native code remain
    outside this bounded identity proof. Do not invoke descriptors to inspect.
    """
    codes = {}
    def retain(path, value):
        if isinstance(value, types.FunctionType):
            codes[path] = (value, value.__code__)
        elif isinstance(value, (staticmethod, classmethod)):
            require(type(value) in (staticmethod, classmethod), 'UNBOUND_DESCRIPTOR_SUBCLASS')
            codes[path + ('__descriptor__',)] = (value, type(value))
            retain(path + ('__func__',), value.__func__)
        elif isinstance(value, property):
            require(type(value) is property, 'UNBOUND_DESCRIPTOR_SUBCLASS')
            codes[path + ('__descriptor__',)] = (value, type(value))
            for label in ('fget', 'fset', 'fdel'):
                retain(path + (label,), getattr(value, label))
    for name, value in values.items():
        retain((name,), value)
        if module_name is not None and isinstance(value, type) and value.__module__ == module_name:
            for key, member in vars(value).items():
                retain((name, key), member)
    return codes


def same_function_state(current, expected):
    return set(current) == set(expected) and all(
        current[key][0] is expected[key][0] and current[key][1] is expected[key][1]
        for key in expected)


def namespace_state(module):
    """Retain namespace objects and bounded executable Python code identity."""
    values = dict(vars(module))
    return values, python_function_state(values, module.__name__)


def same_namespace(module, expected):
    values, codes = expected
    now, current_codes = namespace_state(module)
    return (set(now) == set(values) and all(now[k] is values[k] for k in values)
            and same_function_state(current_codes, codes))


class HeldImportGraph:
    """One finite, non-threaded import scope; no normal PathFinder fallback.

    source records: {name: {'held': HeldFile, 'package': bool, 'imports': tuple,
                          'dynamic_unbound': tuple}}
    externals: exact already-loaded builtins/frozen objects, NEVER extensions.
    New or cached imports both pass the per-module importer. This is a custody
    mechanism for reviewed trusted code, not a sandbox for malicious Python.
    Mutable containers/data/native code are outside namespace identity proof.
    """
    def __init__(self, records, externals=None):
        require(type(records) is dict and records, 'FINITE_EXACT_SOURCE_GRAPH_REQUIRED')
        self.records = {name: dict(record) for name, record in records.items()}
        self.externals = dict(externals or {})
        self.modules = {}; self.snapshots = {}; self.codes = {}; self.audit = {}
        self.builtin_snapshots = {}
        self.active = False; self.original_import = builtins.__import__
        self.bootstrap = sys.modules['_frozen_importlib']
        for name, record in self.records.items():
            require(type(name) is str and name and all(p.isidentifier() for p in name.split('.')),
                    'EXACT_MODULE_NAME_REQUIRED')
            require(type(record) is dict and set(record) == {'held', 'package', 'imports', 'dynamic_unbound'},
                    'EXACT_RECORD_SCHEMA_REQUIRED')
            require(type(record['held']) is HeldFile and type(record['package']) is bool
                    and type(record['imports']) is tuple and type(record['dynamic_unbound']) is tuple,
                    'HELD_MODULE_SCHEMA_REQUIRED')
            require(not record['held'].mode & 0o111, 'SOURCE_MUST_BE_EXECUTABLE_FREE')
            record['held'].verify()
            require(not record['held'].raw.startswith(b'\x7fELF'), 'UNBOUND_EXTENSION_EXECUTION')
            package = name if record['package'] else name.rpartition('.')[0]
            self.audit[name] = source_import_audit(record['held'].raw, name, package)
            require(not record['dynamic_unbound'] and not self.audit[name]['dynamic_gaps'],
                    'UNBOUND_DYNAMIC_IMPORT_GRAPH:' + name)
            require(set(self.audit[name]['static_imports']) <= set(record['imports']),
                    'DECLARED_IMPORT_EDGE_INCOMPLETE:' + name)
            require(set(record['imports']) <= set(self.records) | set(self.externals),
                    'TRANSITIVE_IMPORT_GRAPH_INCOMPLETE:' + name)
            parent = name.rpartition('.')[0]
            require(not parent or parent in self.records and self.records[parent]['package'],
                    'PARENT_PACKAGE_NOT_HELD:' + name)
            require(name not in sys.modules, 'PRELOADED_SOURCE_MODULE_FORBIDDEN:' + name)
            self.codes[name] = compile(record['held'].raw, '<held:' + name + ':' +
                                       record['held'].expected_sha256 + '>', 'exec',
                                       dont_inherit=True, optimize=0)
        require(not set(self.records) & set(self.externals), 'AMBIGUOUS_GRAPH_ENTRY')
        for name, module in self.externals.items():
            require(sys.modules.get(name) is module and isinstance(module, types.ModuleType),
                    'EXACT_EXISTING_MODULE_OBJECT_REQUIRED')
            spec = getattr(module, '__spec__', None)
            require(spec is not None and spec.origin in ('built-in', 'frozen'),
                    'UNBOUND_EXTENSION_OR_SOURCE_STARTUP_MODULE:' + name)

    def install(self):
        require(not self.active and len(os.listdir('/proc/self/task')) == 1,
                'ONE_FINITE_SINGLE_THREAD_IMPORT_SCOPE_REQUIRED')
        for record in self.records.values(): record['held'].verify()
        self.baseline = dict(sys.modules); self.path = list(sys.path)
        self.old_meta = sys.meta_path; self.old_hooks = sys.path_hooks
        self.meta = [self]; self.hooks = []
        sys.meta_path = self.meta; sys.path_hooks = self.hooks
        self.external_snapshots = {n: namespace_state(m) for n, m in self.externals.items()}
        self.active = True
        return self

    def find_spec(self, fullname, path=None, target=None):
        require(self.active and fullname in self.records, 'UNKNOWN_EXTRA_IMPORT:' + fullname)
        record = self.records[fullname]
        return self.bootstrap.ModuleSpec(fullname, self, is_package=record['package'])

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__; record = self.records[name]
        record['held'].verify()
        module.__file__ = '<held:' + name + '>'
        module.__builtins__ = dict(vars(builtins), __import__=self._importer(name))
        self.builtin_snapshots[name] = (module.__builtins__, dict(module.__builtins__),
                                        python_function_state(module.__builtins__))
        self.modules[name] = module
        try:
            exec(self.codes[name], vars(module))
            record['held'].verify()
            self.snapshots[name] = namespace_state(module)
        except BaseException:
            self.modules.pop(name, None); self.snapshots.pop(name, None)
            raise

    def _importer(self, owner):
        def guarded(name, globals=None, locals=None, fromlist=(), level=0):
            record = self.records[owner]
            package = owner if record['package'] else owner.rpartition('.')[0]
            absolute = absolute_import(name, package, level)
            require(absolute in record['imports'], 'UNDECLARED_IMPORT_EDGE:' + owner + ':' + absolute)
            require(absolute not in self.externals or sys.modules.get(absolute) is self.externals[absolute],
                    'STARTUP_MODULE_OBJECT_DRIFT')
            for item in (fromlist or ()):
                require(item != '*', 'STAR_IMPORT_FORBIDDEN')
                child = absolute + '.' + item
                if child in self.records:
                    require(child in record['imports'], 'UNDECLARED_FROMLIST_EDGE:' + child)
            self.verify_loaded()
            result = self.original_import(name, globals, locals, fromlist, level)
            # A parent package gains attributes when a held child is loaded.
            # Only importlib's exact child object addition is accepted below.
            self._accept_child_bindings()
            self.verify_loaded()
            return result
        return guarded

    def _accept_child_bindings(self):
        for name, module in self.modules.items():
            parent, _, child = name.rpartition('.')
            if parent in self.snapshots:
                values, codes = self.snapshots[parent]
                now = vars(self.modules[parent])
                if child not in values and now.get(child) is module:
                    values[child] = module

    def load(self, name):
        require(self.active and name in self.records, 'EXACT_HELD_ROOT_REQUIRED')
        self.verify_loaded()
        result = self.original_import(name, {}, {}, ('__name__',), 0)
        self._accept_child_bindings(); self.verify_loaded()
        return result

    def verify_loaded(self):
        require(self.active and sys.meta_path is self.meta and self.meta == [self]
                and sys.path_hooks is self.hooks and not self.hooks and sys.path == self.path,
                'IMPORT_ROUTE_OR_PATH_DRIFT')
        require(len(os.listdir('/proc/self/task')) == 1, 'UNBOUND_CONCURRENT_IMPORT_THREAD')
        require(set(sys.modules) == set(self.baseline) | set(self.modules), 'UNKNOWN_LOADED_MODULE')
        require(all(sys.modules.get(n) is m for n, m in self.baseline.items()),
                'STARTUP_LOADED_MODULE_DRIFT')
        for name, module in self.externals.items():
            require(same_namespace(module, self.external_snapshots[name]), 'STARTUP_NAMESPACE_DRIFT')
        for name, module in self.modules.items():
            require(sys.modules.get(name) is module, 'HELD_MODULE_OBJECT_DRIFT')
            if name in self.snapshots:
                require(same_namespace(module, self.snapshots[name]), 'LOADED_NAMESPACE_OR_CODE_DRIFT:' + name)
            held_builtins, expected, expected_codes = self.builtin_snapshots[name]
            require(module.__builtins__ is held_builtins and set(held_builtins) == set(expected)
                    and all(held_builtins[k] is expected[k] for k in expected)
                    and same_function_state(python_function_state(held_builtins), expected_codes),
                    'BUILTINS_IMPORT_GUARD_DRIFT')
            self.records[name]['held'].verify()
        return {'held_module_names': sorted(self.modules), 'bytes_and_object_identity_verified': True,
                'runtime_admission': 'NOT_RUN', 'mutable_data_and_native_code_proof': 'UNBOUND'}

    def close(self):
        if self.active:
            # Restore only routes we still own; never overwrite foreign drift.
            if sys.meta_path is self.meta: sys.meta_path = self.old_meta
            if sys.path_hooks is self.hooks: sys.path_hooks = self.old_hooks
            for name, module in self.modules.items():
                if sys.modules.get(name) is module: del sys.modules[name]
            self.active = False


def interpreter_pt_interp(raw):
    require(raw[:4] == b'\x7fELF' and len(raw) >= 64 and raw[4] == 2 and raw[5] in (1, 2),
            'SUPPORTED_ELF64_REQUIRED')
    order = 'little' if raw[5] == 1 else 'big'
    value = lambda offset, size: int.from_bytes(raw[offset:offset+size], order)
    offset, size, count = value(32, 8), value(54, 2), value(56, 2)
    require(56 <= size <= 256 and 0 < count <= 1024 and offset + size*count <= len(raw),
            'BOUNDED_ELF_PROGRAM_HEADERS_REQUIRED')
    found = []
    for index in range(count):
        entry = offset + index*size
        if value(entry, 4) == 3:
            start, length = value(entry+8, 8), value(entry+32, 8)
            require(1 < length <= 4096 and start+length <= len(raw), 'BOUNDED_PT_INTERP_REQUIRED')
            name = raw[start:start+length]
            require(name[-1:] == b'\0' and b'\0' not in name[:-1], 'EXACT_PT_INTERP_REQUIRED')
            found.append(name[:-1].decode('ascii'))
    require(len(found) <= 1, 'AMBIGUOUS_ELF_INTERPRETER')
    return found[0] if found else None


def proc_read(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        # proc pseudo-files support read, not necessarily pread semantics.
        pieces = []; total = 0
        while total <= maximum:
            part = os.read(fd, min(65536, maximum+1-total))
            if not part: return b''.join(pieces)
            pieces.append(part); total += len(part)
        raise Unbound('PROC_OBSERVATION_OVER_BOUND')
    finally:
        os.close(fd)


class HostProvenance:
    """Concrete retained ELF/map observations; deliberately not loaded-code proof.

    exact_expected_maps is an independent mapping of canonical paths to held
    files, including interpreter/dynamic linker/all executable DSO/extension
    maps. Unexpected/deleted/anonymous executable maps are refused. Linux
    relocation, IFUNC, initial import execution and PT_INTERP alias custody
    remain requirements for independent genuine-host qualification.
    """
    def __init__(self, interpreter, exact_expected_maps, *, expected_sys_path):
        require(type(interpreter) is HeldFile and interpreter.raw[:4] == b'\x7fELF',
                'HELD_REAL_ELF_REQUIRED')
        require(type(exact_expected_maps) is dict and exact_expected_maps
                and all(type(v) is HeldFile and k == v.path for k, v in exact_expected_maps.items()),
                'EXACT_INDEPENDENT_EXECUTABLE_MAP_CATALOG_REQUIRED')
        self.interpreter = interpreter; self.maps = dict(exact_expected_maps)
        self.expected_sys_path = tuple(expected_sys_path)
        self.pt_interp = interpreter_pt_interp(interpreter.raw)
        self.birth = self._birth(); self.initial_maps = self._map_observations()
        self.verify_observations()

    @staticmethod
    def _birth():
        raw = proc_read('/proc/self/stat', 16384)
        fields = raw[raw.rfind(b')')+2:].split()
        return (os.getpid(), int(fields[19]))

    def _map_observations(self):
        rows = []
        for line in proc_read('/proc/self/maps', 512*1024).decode('utf8').splitlines():
            fields = line.split(None, 5)
            require(len(fields) >= 5, 'EXACT_PROC_MAP_ROW_REQUIRED')
            address, permissions, offset, dev, inode = fields[:5]
            if 'x' not in permissions: continue
            path = fields[5] if len(fields) == 6 else ''
            if path in ('[vdso]', '[vsyscall]'):
                require('w' not in permissions, 'WRITABLE_KERNEL_EXECUTABLE_MAP')
                rows.append((address, permissions, offset, dev, inode, path)); continue
            require(path in self.maps and 'w' not in permissions and int(inode) > 0,
                    'UNBOUND_UNKNOWN_OR_WRITABLE_EXECUTABLE_MAP:' + path)
            held = self.maps[path]; held.verify(); st = os.fstat(held.fd)
            major, minor = (int(x, 16) for x in dev.split(':'))
            require((major, minor, int(inode)) == (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino),
                    'EXECUTABLE_MAP_INODE_DRIFT')
            rows.append((address, permissions, offset, dev, inode, path))
        require(any(row[-1] == self.interpreter.path for row in rows), 'INTERPRETER_EXECUTABLE_MAP_MISSING')
        return tuple(rows)

    def verify_observations(self):
        self.interpreter.verify()
        st = os.stat('/proc/self/exe')  # kernel-owned magiclink, never user source path
        held_st = os.fstat(self.interpreter.fd)
        require((st.st_dev, st.st_ino) == (held_st.st_dev, held_st.st_ino),
                'RUNNING_INTERPRETER_INODE_MISMATCH')
        require(self._birth() == self.birth and self._map_observations() == self.initial_maps,
                'PROCESS_OR_EXECUTABLE_MAP_DRIFT')
        require(sys.flags.isolated == 1 and sys.flags.no_site == 1
                and sys.flags.dont_write_bytecode == 1 and tuple(sys.path) == self.expected_sys_path,
                'ISOLATED_NO_SITE_NO_BYTECODE_PATH_REQUIRED')
        require(not any(k.startswith(('PYTHON', 'LD_', 'DYLD_')) for k in os.environ),
                'STARTUP_ENVIRONMENT_NOT_CLEARED')
        return {'pid_birth': self.birth, 'interpreter_sha256': self.interpreter.expected_sha256,
                'pt_interp': self.pt_interp, 'executable_maps': self.initial_maps,
                'actual_loaded_code_proof': 'UNBOUND_RELOCATION_IFUNC_VDSO_STARTUP_HISTORY',
                'pt_interp_alias_custody': 'UNBOUND_INDEPENDENT_ANCESTOR_HELD_STARTUP_EXEC',
                'runtime_admission': 'NOT_RUN'}

    def verify_before_effects(self):
        self.verify_observations()
        raise Unbound('UNBOUND_INDEPENDENT_STARTUP_EXTENSION_RELOCATION_ACCEPTANCE; SOURCE_ONLY')


def verify_before_effects(host, graph):
    require(type(host) is HostProvenance and type(graph) is HeldImportGraph,
            'EXACT_HELD_STARTUP_AND_GRAPH_COMPONENTS_REQUIRED')
    graph.verify_loaded()
    host.verify_before_effects()  # intentionally cannot authorize product effects
