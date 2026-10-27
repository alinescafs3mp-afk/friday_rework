"""Reviewed, per-instance S412 diagnostics over the unchanged installed runtime.

Call bind(runtime) for each genuine Runtime created inside the existing scoped
factory. This changes no source file, plan pin, class, readiness or authority.
"""
import ast
import hashlib
import os
from pathlib import Path
import stat
import types

ORIGINAL_SHA256 = '4111e677a103b93ef3d898757e67cea7dad1da68c34d542689707286b802cdd9'
CANDIDATE_SHA256 = '71ffef25974839c3a0ddae153f65a2134cc890ff767873b796b7376ab59bd333'
SOURCE = Path(__file__).absolute().with_name('a0_runtime.py')
METHODS = ('retain_inspect_failure', 'inspect', 'prepare_startup_logs', 'unit_argv')


def bind(runtime):
    # host_runtime intentionally creates a private module without sys.modules.
    authentic = type(runtime).inspect.__globals__
    if authentic.get('Runtime') is not type(runtime):
        raise RuntimeError('s412_genuine_runtime_module_unknown')
    original = Path(authentic['__file__'])
    if not original.is_absolute() or original.resolve() != original:
        raise RuntimeError('s412_original_runtime_path_changed')
    original_data = original.read_bytes()
    if hashlib.sha256(original_data).hexdigest() != ORIGINAL_SHA256:
        raise RuntimeError('s412_original_runtime_changed')
    compiled = compile(original_data, str(original), 'exec')
    runtime_code = next(c for c in compiled.co_consts
                        if isinstance(c, types.CodeType) and c.co_name == 'Runtime')
    originals = {c.co_name: c for c in runtime_code.co_consts if isinstance(c, types.CodeType)}
    for name in ('inspect', 'unit_argv'):
        current = getattr(type(runtime), name)
        if (name in runtime.__dict__ or current.__globals__ is not authentic
                or current.__code__ != originals[name]):
            raise RuntimeError('s412_runtime_method_changed')
    if any(name in runtime.__dict__ for name in METHODS):
        raise RuntimeError('s412_runtime_already_instrumented')
    if not SOURCE.is_absolute() or SOURCE.resolve() != SOURCE:
        raise RuntimeError('s412_candidate_path_changed')
    for parent in (SOURCE.parent, SOURCE.parent.parent):
        info = parent.lstat()
        if (parent.resolve() != parent or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
            raise RuntimeError('s412_candidate_parent_changed')
    info = SOURCE.lstat()
    if (not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
            or info.st_nlink != 1):
        raise RuntimeError('s412_candidate_identity_changed')
    data = SOURCE.read_bytes()
    after = SOURCE.lstat()
    # A read may legitimately update atime; all identity/content metadata must
    # remain unchanged across the authenticated read.
    fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink',
              'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(after, key) != getattr(info, key) for key in fields) or len(data) != info.st_size:
        raise RuntimeError('s412_candidate_read_changed')
    if hashlib.sha256(data).hexdigest() != CANDIDATE_SHA256:
        raise RuntimeError('s412_candidate_source_changed')
    tree = ast.parse(data, str(SOURCE))
    helper = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                  and x.name == 'inspect_failure_snapshot')
    runtime_class = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'Runtime')
    methods = [next(x for x in runtime_class.body if isinstance(x, ast.FunctionDef) and x.name == name)
               for name in METHODS]
    # A private globals copy preserves authentic checks without modifying module
    # classes/globals, installed source or other concurrent Runtime instances.
    namespace = dict(authentic)
    namespace['STARTUP_LOG_LIMIT'] = 131072
    selected = ast.Module(body=[helper, *methods], type_ignores=[])
    exec(compile(selected, str(SOURCE), 'exec'), namespace)
    for name in METHODS:
        setattr(runtime, name, types.MethodType(namespace[name], runtime))
    return runtime
