"""Exact alias/unwind source excerpts for offline study.

NEW SCAFFOLD: the installed allowlist and loader are omitted. Tests provide
synthetic rows and an inert sys-shaped object. This is not an operational patch.
"""

# BEGIN NEW SCAFFOLD: fail-closed defaults, replaced only by inert tests.
_NATIVE_PROVIDER_BUNDLED_ROOTS = {}
PACKAGE_NAME = "_example_private_package"
sys = None
# END NEW SCAFFOLD

# BEGIN EXACT SOURCE: need
def need(ok,reason):
    if not ok:raise ValueError('root_project_only_'+reason)
# END EXACT SOURCE: need

# BEGIN EXACT SOURCE: _native_provider_alias_relative
def _native_provider_alias_relative(name, is_package, files):
    prefix = 'plugins.model_providers.'
    if not name.startswith(prefix):
        return None
    parts = name[len(prefix):].split('.')
    need(parts and parts[0] in _NATIVE_PROVIDER_BUNDLED_ROOTS
        and (len(parts) > 1 or is_package)
        and all(p.isidentifier() for p in parts),
        'owned_native_provider_alias_name_refused')
    # Use only genuine immediate receipt package directories and the exact
    # discovery normalization; reject ambiguity even for identical source bytes.
    roots = {path.split('/')[2] for path in files
        if type(path) is str and path.startswith('plugins/model-providers/')
        and len(path.split('/')) == 4 and path.endswith('/__init__.py')}
    matches = [root for root in roots if root.replace('-', '_') == parts[0]]
    pinned = _NATIVE_PROVIDER_BUNDLED_ROOTS[parts[0]]
    need(len(matches) == 1 and matches[0] == pinned['directory'],
        'owned_native_provider_alias_ambiguous_or_foreign')
    root = 'plugins/model-providers/' + pinned['directory']
    row = files.get(root + '/__init__.py', {})
    need(type(row) is dict and row.get('sha256') == pinned['sha256']
        and row.get('bytes') == pinned['bytes'] and row.get('mode') == pinned['mode'],
        'owned_native_provider_alias_root_not_pinned')
    relative = root + ('/' + '/'.join(parts[1:]) if len(parts) > 1 else '')
    relative += '/__init__.py' if is_package else '.py'
    descendant = files.get(relative)
    need(type(descendant) is dict and descendant.get('mode') == '100644'
        and type(descendant.get('bytes')) is int and descendant['bytes'] >= 0
        and type(descendant.get('sha256')) is str and len(descendant['sha256']) == 64
        and all(c in '0123456789abcdef' for c in descendant['sha256']),
        'owned_native_provider_alias_descendant_not_pinned')
    return relative
# END EXACT SOURCE: _native_provider_alias_relative

# BEGIN EXACT SOURCE: managed module roots
_MANAGED_MODULE_ROOTS = ('scripts', 'tools', 'plugins', PACKAGE_NAME,
    '_friday_install_validation_plugins', '_friday_install_validation')
# END EXACT SOURCE: managed module roots

# BEGIN EXACT SOURCE: _OwnedModuleUnwind
class _OwnedModuleUnwind:
    """Opt-in, cold-namespace, exact identity CAS for one loader context.

    No preexisting namespace is evicted. Authentication is supplied by the
    existing held-FD reader; unrelated modules are never changed.
    """
    def __init__(self, authenticate):
        self.authenticate = authenticate
        self.original_modules = sys.modules
        self.original_path_object = sys.path
        self.original_path = list(sys.path)
        self.original_bytecode = sys.dont_write_bytecode
        self.expected_paths = [list(sys.path)]
        self.observed = {}
        need(not self.graph(), 'owned_unwind_requires_cold_namespaces')

    @staticmethod
    def graph():
        return {name: module for name, module in tuple(sys.modules.items())
            if any(name == root or name.startswith(root + '.')
                for root in _MANAGED_MODULE_ROOTS)}

    @staticmethod
    def signature(module):
        spec = getattr(module, '__spec__', None)
        return (id(module), getattr(module, '__file__', None),
            id(spec), getattr(spec, 'origin', None),
            id(getattr(module, '__loader__', None)),
            getattr(module, '__package__', None),
            tuple(getattr(module, '__path__', ())),
            tuple(getattr(spec, 'submodule_search_locations', ()) or ()))

    def checkpoint(self):
        need(sys.modules is self.original_modules and sys.path is self.original_path_object,
            'owned_global_container_identity_changed')
        graph = self.graph()
        need(set(self.observed) <= set(graph), 'owned_module_removed_before_unwind')
        for name, (module, signature) in self.observed.items():
            need(graph[name] is module and self.signature(module) == signature,
                'owned_module_identity_or_namespace_changed')
        for name, module in graph.items():
            self.authenticate(name, module)
            self.observed.setdefault(name, (module, self.signature(module)))
        # Existing packages must expose the exact module object for each child.
        for name, module in graph.items():
            parent, _, child = name.rpartition('.')
            if parent in graph:
                need(getattr(graph[parent], child, None) is module,
                    'owned_parent_child_identity_changed')

    def close(self):
        self.checkpoint()
        need(any(sys.path == expected for expected in self.expected_paths),
            'owned_sys_path_CAS_changed')
        need(sys.dont_write_bytecode is True, 'owned_bytecode_policy_changed')
        graph = self.graph()
        need(set(graph) == set(self.observed) and all(graph[name] is module
            and self.signature(module) == signature
            for name, (module, signature) in self.observed.items()),
            'owned_module_final_CAS_changed')
        # All checks precede any mutation. Every removed key was absent on entry.
        for name in sorted(graph, key=lambda value: value.count('.'), reverse=True):
            del sys.modules[name]
        sys.path[:] = self.original_path
        sys.dont_write_bytecode = self.original_bytecode
# END EXACT SOURCE: _OwnedModuleUnwind

