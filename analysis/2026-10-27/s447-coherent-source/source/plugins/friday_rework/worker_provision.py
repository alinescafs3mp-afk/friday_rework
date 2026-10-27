"""Protected per-profile inputs for the existing worker admission contract.

No receipt producer, launch, capability, account store or automatic adoption.
The operator supplies intact pinned sources and original limits; readiness is
checked by host_runtime, not inferred from rendered configuration.
"""
import builtins
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import hashlib
import json
from pathlib import Path

from .host_runtime import HostUnavailable, validate_runtime, _pin
from .host_record import digest



# One private helper graph per operation. Native tools/plugins/scripts keep
# their original search paths and module identities; no project sys.path entry.
_WORKER_SOURCES = ContextVar('friday_worker_product_sources', default=None)


class _WorkerSources:
    """Exact canonical product helpers, never a worker/native authority grant."""
    def __init__(self, project, pins, *, budget=None):
        from .runtime_primitives import canonical, owned_file
        self.project = canonical(str(project))
        self.pins, self.budget = dict(pins), budget
        self.modules, self.raw = {}, {}
        # Existing installer private validators use these source files too.
        # Authenticate the complete declared product before executing helpers.
        for name, expected in self.pins.items():
            self.check()
            path = canonical(str(self.project / name))
            if not path.is_relative_to(self.project) or '..' in Path(name).parts:
                raise HostUnavailable('worker_product_source_path_changed')
            raw = owned_file(path)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise HostUnavailable('worker_product_source_changed')
            self.raw[name] = raw

    def check(self):
        if self.budget is not None: self.budget.check()

    def module(self, name):
        from types import ModuleType
        self.check()
        if name in self.modules: return self.modules[name]
        # Only product scripts and the two existing pure rendering helpers.
        if (not name.startswith('scripts.') or name.count('.') != 1) and name not in (
                'tools.render_dsh_local', 'tools.web_profile'):
            raise HostUnavailable('worker_product_helper_refused')
        relative = name.replace('.', '/') + '.py'
        if relative not in self.raw:
            raise HostUnavailable('worker_product_helper_pin_required')
        module = ModuleType('_friday_worker_source.' + name)
        module.__file__ = str(self.project / relative)
        module.__package__ = name.rpartition('.')[0]
        # Redirect this module's imports only. Never replace or claim a native
        # module in sys.modules, even when native tools/scripts already exist.
        module.__dict__['__builtins__'] = dict(vars(builtins), __import__=self._import)
        self.modules[name] = module
        try:
            exec(compile(self.raw[relative], module.__file__, 'exec'), module.__dict__)
            self.check()
        except BaseException:
            self.modules.pop(name, None)
            raise
        return module

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and (name == 'scripts' or name.startswith('scripts.')
                or name in ('tools.render_dsh_local', 'tools.web_profile')):
            from types import ModuleType
            family, _, _ = name.partition('.')
            package = self.modules.get(family)
            if package is None:
                package = ModuleType('_friday_worker_source.' + family)
                self.modules[family] = package
            if name == family:
                for member in fromlist:
                    setattr(package, member, self.module(family + '.' + member))
                return package
            module = self.module(name)
            setattr(package, name.split('.')[1], module)
            return module if fromlist else package
        return builtins.__import__(name, globals, locals, fromlist, level)


def _installed_worker_sources(*, budget=None):
    from .runtime_primitives import canonical, owned_file, unique
    from hermes_cli.friday_dashboard_owner import source_identity
    home = canonical(str(Path(__file__).resolve().parents[2]))
    # Existing native ownership validation: exact installed plugin, complete
    # native source and its truthful source receipt, rather than a cache label.
    identity = source_identity(home, source=home / 'hermes-agent')
    marker_raw = owned_file(home / 'FRIDAY-INSTALL.json', private=True)
    marker = json.loads(marker_raw, object_pairs_hook=unique)
    entry = marker['ordinary_gateway']['operator_entry']
    def read(ref):
        if type(ref) is not dict or set(ref) != {'path', 'sha256'}:
            raise HostUnavailable('worker_product_source_reference_required')
        raw = owned_file(canonical(ref['path']), private=True)
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise HostUnavailable('worker_product_source_reference_changed')
        return raw
    raw = read(entry['input'])
    current = json.loads(raw, object_pairs_hook=unique)
    script = canonical(entry['script']['path'])
    project = script.parents[1]
    if (script != project / 'scripts/friday_native.py' or current['home'] != str(home)
            or entry['input']['sha256'] != marker['input_sha256']
            or marker['source_receipt_sha256'] != identity['receipt']
            or current['project_files'].get('scripts/friday_native.py') != entry['script']['sha256']
            or {n:h for n,h in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
                != marker['plugin_files']):
        raise HostUnavailable('worker_product_source_owner_changed')
    read(entry['script'])
    graph = _WorkerSources(project, current['project_files'], budget=budget)
    # No mutable ownership or current-source observation is memoized.
    if owned_file(home / 'FRIDAY-INSTALL.json', private=True) != marker_raw:
        raise HostUnavailable('worker_product_source_owner_changed')
    return graph


@contextmanager
def worker_source_scope(*, budget=None):
    """Keep one canonical module/type graph, only for this original operation."""
    previous = _WORKER_SOURCES.get()
    if previous is not None:
        yield
        return
    token = _WORKER_SOURCES.set({'graph': None, 'budget': budget})
    try: yield
    finally: _WORKER_SOURCES.reset(token)


def source_module(name):
    current = _WORKER_SOURCES.get()
    if current is not None and current['graph'] is not None:
        return current['graph'].module(name)
    project = Path(__file__).resolve().parents[2]
    if (not (project / 'FRIDAY-INSTALL.json').exists()
            and not (project / 'FRIDAY-INSTALL.json').is_symlink()
            and (project / 'scripts/friday_install.py').is_file()):
        # Source-tree/operator use retains the existing canonical graph. Check
        # resolution before executing a helper, including preloaded modules.
        import importlib
        import importlib.util
        spec = importlib.util.find_spec(name)
        expected = project / (name.replace('.', '/') + '.py')
        if spec is None or spec.origin != str(expected):
            raise HostUnavailable('worker_product_helper_origin_changed')
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() != expected:
            raise HostUnavailable('worker_product_helper_origin_changed')
        return module
    current = _WORKER_SOURCES.get()
    if current is None:
        return _installed_worker_sources().module(name)
    if current['graph'] is None:
        current['graph'] = _installed_worker_sources(budget=current['budget'])
    return current['graph'].module(name)


def pin(path):
    from hermes_cli import friday_user_scope as scope
    scope._private(path)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def own_runtime(home, profile, worker, runtime):
    c = validate_runtime(runtime)
    if worker not in ('dsh', 'a0') or (worker == 'a0') != ('a0' in c):
        raise HostUnavailable('worker_runtime_mismatch')
    root = home / 'workers' / worker
    if c['runtime_home'] != str(home) or c['runtime_profile'] != profile:
        raise HostUnavailable('foreign_worker_runtime_home')
    # Configuration preparation has a fixed exclusive per-worker private tree.
    # Shared source/toolchain mounts remain read-only through the native adapter.
    expected = {'workspace_root': root / 'jobs', 'staging_root': root / 'staging'}
    if any(c[k] != str(p) for k, p in expected.items()) or c['cache_roots'] != [str(root / 'cache')]:
        raise HostUnavailable('exclusive_user_worker_roots_required')
    receipt = Path(c['runtime_receipt']['path'])
    if receipt != root / 'runtime-receipt.json':
        raise HostUnavailable('own_worker_receipt_required')
    for p in [root, *expected.values(), root / 'cache', root / 'inputs', receipt]:
        if p.resolve() != p:
            raise HostUnavailable('unsafe_user_worker_path')
    return c, root


def declared_a0_policy(runtime, root, files):
    """Only the exact own policy may be consumed before its planned write."""
    from .adapters.dsh import PinnedFile
    reference = _pin(runtime['a0']['policy'])
    if not files:
        return reference
    path = root / 'inputs/a0-policy.nft'
    if set(files) != {path} or reference.path != path:
        raise HostUnavailable('unexpected_declared_a0_input')
    from .host_runtime import a0_runtime_module
    from .adapters.a0_profile import network_endpoints
    from .adapters.a0_web import route_web
    a = runtime['a0']
    launcher = a0_runtime_module(runtime).checked_launcher(a['launcher']['sha256'])
    expected = launcher['policy'](route_web(a['web']), network_endpoints(a['deployment'])).encode()
    raw = files[path]
    if raw != expected or hashlib.sha256(raw).hexdigest() != reference.sha256:
        raise HostUnavailable('declared_a0_policy_changed')
    class DeclaredPolicy(PinnedFile):
        def read(self):
            return raw
    return DeclaredPolicy(reference.path, reference.sha256)


def prepare_inputs(home, profile, worker, runtime, config, *, a0_network=None, declared_files=None, tools=None, _history_walk=None, _current_main=None):
    """Return an explicit plan before any write; never read/copy readiness."""
    from .onboarding import validate_template
    from hermes_cli import friday_user_scope as scope
    # Validate the actual profile, including local routes and accepted SAFE tools.
    # The protected caller supplies its already checked binding grants.
    # Legacy non-browser callers retain their original validation contract.
    profile_names = [config['providers']['friday-local']['key_env']]
    compressor = config['providers'].get('friday-compression')
    if isinstance(compressor, dict):
        profile_names.append(compressor.get('key_env'))
    if not config['web']['keyless_fallback']:
        profile_names.append('EXA_API_KEY')
    _, _, profile_names = validate_template({
        'config': config, 'tools': sorted(scope.SAFE) if tools is None else tools,
        'required_secrets': profile_names})
    c, root = own_runtime(home, profile, worker, runtime)
    files = dict(declared_files or {}); names = []; unobserved = ['native execution', 'model', 'network', 'runtime receipt', 'independent review']
    for path, raw in files.items():
        if not path.is_relative_to(root / 'inputs') or path.resolve() != path or not isinstance(raw, bytes):
            raise HostUnavailable('foreign_declared_worker_input')
    if worker == 'dsh':
        if a0_network is not None:
            raise HostUnavailable('unexpected_a0_inputs')
        d = c['dsh']; provider = config['providers']['friday-local']; model = config['model']
        if d['key_name'] != provider['key_env'] or d['web']['profile'] != ('exa-keyless' if config['web']['keyless_fallback'] else 'exa-paid'):
            raise HostUnavailable('own_worker_credential_and_web_required')
        build_patch = source_module('tools.render_dsh_local').build_patch
        capacity = provider['models'][model['default']]; bounds = capacity['bounded_context']
        rows = build_patch(purpose='temporary-local-test', api='openai-completions',
            base_url=model['base_url'], model=model['default'], api_key_env=d['key_name'],
            context_window=capacity['context_length'], max_tokens=bounds['main_max_output_tokens'],
            summary_max_tokens=bounds['compression_max_output_tokens'],
            headroom_tokens=bounds['safety_margin_tokens'] + bounds['template_overhead_tokens'], web_profile=d['web']['profile'])
        data = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
        expected = {'path': str(root / 'inputs/dsh-local.json'), 'sha256': hashlib.sha256(data).hexdigest()}
        if d['patch'] != expected:
            raise HostUnavailable('rendered_user_worker_patch_mismatch')
        files[Path(expected['path'])] = data
        from .worker_web import DshWebInputs
        # Read every pinned source/web input; no shared receipt or key is read.
        for p in (d['node'], d['cli'], *d['native_files']): _pin(p).read()
        def declared_pin(ref):
            checked = _pin(ref)
            if checked.path not in files: return checked
            raw = files[checked.path]
            if hashlib.sha256(raw).hexdigest() != checked.sha256:
                raise HostUnavailable('declared_worker_input_changed')
            # Byte-only future declaration, used solely by the trusted planner.
            from types import SimpleNamespace
            return SimpleNamespace(path=checked.path, sha256=checked.sha256, read=lambda: raw)
        web = DshWebInputs(*(declared_pin(d['web'][k]) for k in ('resolver', 'trust_bundle', 'egress_evidence', 'research_policy')), profile=d['web']['profile'])
        web.checked_patch(data)
        names = [d['key_name'], *([] if d['web']['profile'] == 'exa-keyless' else ['EXA_API_KEY'])]
    else:
        if _current_main is not None and (_current_main.get('home') != str(home)
                or _current_main.get('profile') != profile):
            raise HostUnavailable('foreign_current_main_source_target')
        checked_installed_a0_source_successor(c, _history_walk=_history_walk, _current_main=_current_main)
        if not isinstance(a0_network, dict) or set(a0_network) != {'name', 'endpoints', 'policy'}:
            raise HostUnavailable('explicit_a0_local_network_inputs_required')
        from .adapters.a0_config import LocalNetwork, local_profile, KEY_REFERENCES
        from .adapters.a0_web import service_files
        from .worker_web import a0_web_files
        deployment = c['a0'].get('deployment')
        if deployment != config.get('a0_deployment'):
            raise HostUnavailable('a0_configured_deployment_profile_mismatch')
        if a0_network['policy'] != c['a0']['policy']:
            raise HostUnavailable('a0_declared_network_policy_mismatch')
        policy = declared_a0_policy(c, root, files)
        network = LocalNetwork(a0_network['name'], tuple(a0_network['endpoints']), policy, deployment)
        native = local_profile(network)
        chat = native['plugins/_model_config/presets.yaml'][0]['chat']
        capacity = config['providers']['friday-local']['models'][config['model']['default']]
        if (chat['api_base'] != config['model']['base_url'] or chat['name'] != config['model']['default']
                or chat['ctx_length'] != capacity['context_length']
                or chat['kwargs']['max_tokens'] != capacity['bounded_context']['main_max_output_tokens']):
            raise HostUnavailable('a0_original_local_profile_mismatch')
        utility = native['plugins/_model_config/presets.yaml'][0]['utility']
        if (utility['api_base'] != chat['api_base'] or utility['name'] != chat['name']
                or utility['ctx_length'] != chat['ctx_length']
                or utility['kwargs']['max_tokens'] != chat['kwargs']['max_tokens']):
            # Native chat and utility share API_KEY_OPENAI. A separate protected
            # compressor route cannot borrow the primary credential.
            raise HostUnavailable('a0_scoped_utility_profile_mismatch')
        if deployment is not None:
            if config['providers']['friday-local']['key_env'] != KEY_REFERENCES['API_KEY_OPENAI']:
                raise HostUnavailable('a0_scoped_profile_key_mismatch')
        for k in ('runtime', 'launcher', 'docker', 'daemon_unit'): _pin(c['a0'][k]).read()
        policy.read()
        # Explicit native file contents only. Installation/network/capability are
        # intentionally unobserved. Nothing is installed into a donor or service.
        files[root / 'inputs/a0-native-files.json'] = (json.dumps({**native, **(service_files(c['a0']['web']) if 'web' in c['a0'] else a0_web_files('searxng-google'))}, sort_keys=True, indent=2) + '\n').encode()
        names = list(KEY_REFERENCES.values()) + ([] if config['web']['keyless_fallback'] else ['EXA_API_KEY'])
        if 'web' in c['a0']: names.append('SEARXNG_SECRET')
        unobserved.append('A0 reconciliation and current per-job capability')
    for k in ('workspace_root', 'staging_root', 'cache_roots', 'runtime_home'):
        if k in c[worker]: raise HostUnavailable('duplicate_worker_roots')
    # Retain every validated ordinary inference/web reference in protected
    # capture joins, including an optional separately scoped compressor.
    names = list(dict.fromkeys([*names, *profile_names]))
    return c, root, files, names, unobserved


def preparation(home, profile, worker, reference, *, private_check=None):
    """Read exact private preparation bytes and recheck original ownership."""
    p = _pin(reference); expected = home / 'workers' / worker / 'runtime-input.json'
    if p.path != expected: raise HostUnavailable('foreign_worker_preparation')
    if private_check is None:
        from hermes_cli import friday_user_scope as scope
        private_check = scope._private
    private_check(p.path)
    v = json.loads(p.read())
    fields={'runtime', 'inputs', 'principal_binding_sha256', 'generation', 'state', 'unobserved'}
    if (not isinstance(v, dict) or set(v) not in (fields,fields|{'attachment'})
            or v['state'] != 'PREPARED_RUNTIME_UNOBSERVED'):
        raise HostUnavailable('invalid_worker_preparation')
    if 'attachment' in v:
        attachment=_pin(v['attachment'])
        if attachment.path!=home / 'workers/attachment.json':
            raise HostUnavailable('foreign_worker_attachment')
        private_check(attachment.path); attachment.read()
    c, root = own_runtime(home, profile, worker, v['runtime'])
    for f in v['inputs']:
        q = _pin(f)
        if not q.path.is_relative_to(root / 'inputs'): raise HostUnavailable('foreign_worker_inputs')
        private_check(q.path); q.read()
    return v, c


def checked_installed_a0_source_successor(runtime, *, _history_walk=None, _current_main=None):
    """Consume maintenance and authenticated ordinary descendants before setup.

    The ordinary marker remains pending. This check grants neither readiness
    nor a native capability; existing probe/custody observers remain mandatory.
    Later source publications must retain the same exact worker service pins.
    """
    # Separate exact480 native receipt; old120 historical readers remain below.
    if runtime.get('a0',{}).get('runtime',{}).get('sha256') == 'PRIVATE_REF_8916093c39ce1493':
        if _current_main is not None and (_current_main.get('home') != runtime.get('runtime_home')
                or _current_main.get('profile') != runtime.get('runtime_profile')):
            raise HostUnavailable('foreign_current480_source_target')
        from .runtime_primitives import owned_file, canonical
        verifier = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/verify480.py', 'sha256': 'PRIVATE_REF_8140e0cd6deb0e06'}
        path = canonical(verifier['path'])
        raw = owned_file(path,private=True)
        if hashlib.sha256(raw).hexdigest() != verifier['sha256']:
            raise HostUnavailable('current480_verifier_source_changed')
        namespace={'__file__':str(path),'__name__':'_s443_worker480_source'}
        exec(compile(raw,str(path),'exec'),namespace)
        current=namespace['current480']()
        proof=namespace['verify480'](current['request'],current['receipt'],config=runtime)
        # This independent source proof grants no old SourceMaintenance reattach.
        return {'schema':'friday.worker-current480-source.v1','native480':current,
                'proof':proof,'reattachment_authority':False}
    source = Path(runtime['a0']['runtime']['path'])
    suffix = ('worker-runtime-source', 'scripts', 'a0_runtime.py')
    if tuple(source.parts[-3:]) != suffix:
        return None
    installed_home = source.parents[2]
    marker_path = installed_home / 'FRIDAY-INSTALL.json'
    attempts = installed_home / 'preparation'
    maintained = attempts.is_dir() and any(p.name.startswith('worker-declarations-successor-') for p in attempts.iterdir())
    if not marker_path.exists() and not marker_path.is_symlink():
        if maintained: raise HostUnavailable('installed_a0_successor_marker_required')
        return None
    installer = source_module('scripts.friday_install')
    marker = installer.read_json(marker_path)
    reference = marker.get('a0_service_source_successor')
    if reference is None:
        if maintained: raise HostUnavailable('installed_a0_successor_receipt_required')
        return None
    registration = source_module('scripts.friday_ordinary_a0_registration')
    checked_source_maintenance_successor = registration.checked_source_maintenance_successor
    _checked_source_maintenance_successor = registration._checked_source_maintenance_successor
    checked = (checked_source_maintenance_successor(installed_home, reference, _current_main=_current_main) if _history_walk is None
        else _checked_source_maintenance_successor(installed_home, reference, _walk=_history_walk, _current_main=_current_main))
    plan = checked['receipt']['new_plan']; declaration = runtime['a0']
    expected = {'runtime': {'path': str(source), 'sha256': plan['source_files']['scripts/a0_runtime.py']},
        'launcher': checked['receipt']['launcher'],
        'daemon_unit': {'path': plan['unit_source'], 'sha256': plan['source_files']['scripts/friday-rework-docker.service']}}
    if any(declaration.get(name) != ref for name, ref in expected.items()):
        raise HostUnavailable('installed_a0_successor_declaration_changed')
    return checked
