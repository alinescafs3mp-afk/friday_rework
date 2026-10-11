"""Concrete immutable source loader; host attachment/interpreter trust is external.

This module implements the formerly missing capture_loaded_implementation
counterpart. It does not authenticate its caller, acquire a slot, or establish
kernel custody. An existing controlled host must supply pre-load interpreter
provenance and the original binding. A fixture can exercise these mechanics,
but cannot establish that its interpreter provenance came from that host.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import types

NAMES = frozenset({'source_runner.py', 'runner_worker.py', 'gate_inputs.py', 'runner_contract.py'})

class LoaderRefusal(ValueError):
    pass

def need(ok, cause):
    if not ok:
        raise LoaderRefusal(cause)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()

def birth(pid):
    need(type(pid) is int and pid > 0, 'loader_process_type')
    try:
        s = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        return None
    return int(s[s.rfind(')') + 2:].split()[19])

def value_identity(value, depth=0):
    """Detect ordinary namespace/code/default drift; not a malicious-code fence."""
    if value is None or type(value) in (str, int, float, bool, bytes):
        return (type(value).__name__, value)
    if depth < 8 and type(value) in (tuple, list):
        return (type(value).__name__, tuple(value_identity(v, depth+1) for v in value))
    if depth < 8 and type(value) is dict:
        return ('dict', tuple(sorted((repr(k), value_identity(v, depth+1)) for k,v in value.items())))
    if isinstance(value, types.FunctionType):
        # Retain the actual immutable compiled code object and its identity.
        # marshal byte streams can change with CPython intern-reference state;
        # they are not a stable executing-code identity. Strong references also
        # prevent an old object ID being recycled after namespace replacement.
        return ('function', value, value.__code__, id(value.__code__), id(value.__globals__),
                value_identity(value.__defaults__, depth+1), value_identity(value.__kwdefaults__, depth+1),
                tuple(value_identity(c.cell_contents, depth+1) for c in (value.__closure__ or ())))
    if isinstance(value, (staticmethod, classmethod)):
        return (type(value).__name__, value_identity(value.__func__, depth+1))
    if isinstance(value, property):
        return ('property', tuple(value_identity(v, depth+1) for v in (value.fget, value.fset, value.fdel)))
    if isinstance(value, type) and depth < 8:
        return ('class', value, id(value), tuple(sorted((k,value_identity(v,depth+1)) for k,v in vars(value).items()
                                               if not k.startswith('__'))))
    if isinstance(value, Path):
        return ('path', str(value))
    return ('identity', type(value).__name__, id(value))

def namespace_identity(namespace):
    return tuple(sorted((key, value_identity(value)) for key,value in namespace.items()
                        if key not in {'__builtins__'}))

class RetainedLoader:
    """One process/actor/binding, four original buffers, one-shot module loads.

    buffers must be captured/verified by the controlled host before construction
    and before any source exec. interpreter_provenance must be its independently
    retained observation of the actual interpreter, not a fresh __file__/exe pin.
    The object itself is a source component, never a proof of host authentication.
    """
    def __init__(self, *, buffers, implementation, interpreter_provenance, binding, actor):
        need(actor in ('parent', 'worker'), 'loader_actor')
        need(type(buffers) is dict and set(buffers) == NAMES, 'loader_source_membership')
        need(type(implementation) is dict and set(implementation) == NAMES | {'interpreter'}, 'loader_implementation_membership')
        need(type(interpreter_provenance) is bytes and
             interpreter_provenance == canonical(implementation['interpreter']), 'preload_interpreter_provenance_required')
        interpreter = implementation['interpreter']
        need(type(interpreter) is dict and set(interpreter)=={'path','sha256','bytes'} and
             type(interpreter['path']) is str and interpreter['path']==str(Path(sys.executable).resolve()) and
             type(interpreter['bytes']) is int and 0<interpreter['bytes']<=8*1024**2 and
             type(interpreter['sha256']) is str and len(interpreter['sha256'])==64 and
             all(c in '0123456789abcdef' for c in interpreter['sha256']), 'preload_interpreter_pin_schema')
        # Path/shape joins the requested executable only. It cannot prove the
        # already loaded ELF/interpreter image; that provenance remains the
        # independently retained controlled-host requirement documented above.
        need(type(binding) is dict and set(binding) == {'binding_sha256','grant'}, 'loader_binding_required')
        self._buffers = tuple((name, implementation[name]['path'], buffers[name]) for name in sorted(NAMES))
        for name,path,data in self._buffers:
            need(type(path) is str and Path(path).is_absolute() and Path(path).name == name,
                 'loader_source_path')
            need(type(data) is bytes and len(data) <= 8*1024**2, 'immutable_preload_buffer_required')
            need(implementation[name] == {'path':path,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},
                 'preload_source_pin_changed:'+name)
        roots = {str(Path(path).parent) for _,path,_ in self._buffers}
        need(len(roots) == 1, 'loader_foreign_source_root')
        self._implementation = canonical(implementation)
        self._binding = canonical(binding)
        self._interpreter = interpreter_provenance
        self.actor = actor
        self._process = {'pid':os.getpid(), 'start_ticks':birth(os.getpid())}
        need(self._process['start_ticks'] is not None, 'loader_process_absent')
        self._modules = {}
        self._identities = {}
        self._loading = set()

    def _process_live(self):
        need(self._process == {'pid':os.getpid(),'start_ticks':birth(os.getpid())}, 'retained_loader_process_changed')

    def load_dependency(self, name):
        """Used by exact parent/worker injected bootstrap; never reopen a path."""
        self._process_live()
        filename = name + '.py'
        allowed = {'runner_contract.py','gate_inputs.py'} if self.actor == 'parent' else {'runner_contract.py'}
        need(filename in allowed, 'unapproved_loader_dependency')
        module = self._load(filename)
        return module, next(b for n,p,b in self._buffers if n == filename)

    def _load(self, filename):
        self._process_live()
        if filename in self._modules:
            self._verify_modules()
            return self._modules[filename]
        need(filename in NAMES and filename not in self._loading, 'unapproved_or_recursive_module')
        name,path,data = next(x for x in self._buffers if x[0] == filename)
        self._loading.add(filename)
        module = types.ModuleType('retained_'+name[:-3])
        module.__dict__.update(__file__=path, __gate_loader__=self, __package__='', __spec__=None)
        try:
            code = compile(data, path, 'exec')  # same immutable bytes retained BEFORE exec
            exec(code, module.__dict__)
            self._modules[name] = module
            self._identities[name] = namespace_identity(module.__dict__)
        finally:
            self._loading.remove(filename)
        return module

    def load_entrypoint(self):
        filename = 'source_runner.py' if self.actor == 'parent' else 'runner_worker.py'
        need(filename not in self._modules, 'loader_entrypoint_already_loaded')
        return self._load(filename)

    def _verify_modules(self):
        for name,module in self._modules.items():
            need(namespace_identity(module.__dict__) == self._identities[name], 'retained_loaded_namespace_changed:'+name)

    def verify_original_attachment(self, *, implementation, binding):
        """Concrete adapter join before any effects; no fresh file authority."""
        entry='source_runner.py' if self.actor=='parent' else 'runner_worker.py'
        need(entry in self._modules, 'loader_entrypoint_not_loaded')
        context=dict(phase='host_attachment',actor=self.actor,process=self._process,
                     worker=self._process if self.actor=='worker' else None,
                     implementation=implementation,binding=binding)
        self.capture_loaded_implementation(context=context,namespace=self._modules[entry].__dict__)
        return True

    def capture_loaded_implementation(self, *, context, namespace):
        self._process_live()
        need(type(context) is dict and set(context) == {'phase','actor','process','worker','implementation','binding'},
             'loader_context_schema')
        need(context['actor'] == self.actor and canonical(context['process']) == canonical(self._process),
             'loader_actor_process_mismatch')
        need(type(context['phase']) is str and context['phase'], 'loader_phase_required')
        need(canonical(context['implementation']) == self._implementation, 'loader_original_implementation_changed')
        need(canonical(context['binding']) == self._binding, 'loader_original_binding_changed')
        entry = 'source_runner.py' if self.actor == 'parent' else 'runner_worker.py'
        expected = {'source_runner.py','gate_inputs.py','runner_contract.py'} if self.actor == 'parent' else {'runner_worker.py','runner_contract.py'}
        need(set(self._modules) == expected, 'loader_actual_loaded_membership')
        need(namespace is self._modules[entry].__dict__, 'loader_foreign_executing_namespace')
        if self.actor == 'worker':
            need(canonical(context['worker']) == canonical(self._process), 'loader_worker_birth_mismatch')
        self._verify_modules()
        sources = tuple((n,p,b,'loaded' if n in expected else 'retained_launch_image') for n,p,b in self._buffers)
        return canonical(context), sources, self._interpreter
