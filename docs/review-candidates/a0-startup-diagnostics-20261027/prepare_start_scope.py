"""Pure S412 source preparation only: returns bytes; no reads/writes/effects."""
import ast
import hashlib
BASE_SHA256 = 'be6ed32a41984a76a0aa279330920a63d69812e7c0124e4dedfe4e0ac7b523f2'
LOADER_TEMPLATE = "\n# S412 diagnostic binding adds observation only to the authentic private runtime.\n# These references are source pins, never clock/authority/owner/admission values.\nimport os as _diag_os\nimport stat as _diag_stat\nDIAGNOSTIC_BINDER_REF = __BINDER_REFERENCE_LITERAL__\nDIAGNOSTIC_CANDIDATE_REF = __CANDIDATE_REFERENCE_LITERAL__\n\ndef _diag_read(reference):\n    _require(type(reference) is dict and set(reference)=={'path','sha256'})\n    path=Path(reference['path'])\n    _require(path.is_absolute() and '..' not in path.parts and path.resolve()==path)\n    parents={}\n    for parent in reversed(path.parents):\n        info=parent.lstat()\n        _require(_diag_stat.S_ISDIR(info.st_mode) and info.st_uid in (0,_diag_os.getuid()) and not info.st_mode&0o022)\n        parents[parent]=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)\n    fields=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')\n    fd=_diag_os.open(path,_diag_os.O_RDONLY|_diag_os.O_NOFOLLOW|_diag_os.O_NONBLOCK)\n    with _diag_os.fdopen(fd,'rb') as stream:\n        first=_diag_os.fstat(stream.fileno())\n        _require(_diag_stat.S_ISREG(first.st_mode) and first.st_uid==_diag_os.getuid()\n                 and _diag_stat.S_IMODE(first.st_mode) in (0o400,0o600) and first.st_nlink==1 and first.st_size<=2*1024*1024)\n        raw=stream.read(2*1024*1024+1)\n        last=_diag_os.fstat(stream.fileno()); named=path.lstat()\n        _require(all(getattr(first,k)==getattr(last,k)==getattr(named,k) for k in fields)\n                 and len(raw)==first.st_size and hashlib.sha256(raw).hexdigest()==reference['sha256'])\n    for parent,expected in parents.items():\n        info=parent.lstat()\n        _require((info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)==expected)\n    return raw\n\ndef _diag_bind_runtime(runtime):\n    raw=_diag_read(DIAGNOSTIC_BINDER_REF)\n    _diag_read(DIAGNOSTIC_CANDIDATE_REF)\n    tree=ast.parse(raw,DIAGNOSTIC_BINDER_REF['path'])\n    literals={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body\n              if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)\n              and isinstance(node.value,ast.Constant)}\n    _require(literals.get('ORIGINAL_SHA256')==RUNTIME_SHA\n             and literals.get('CANDIDATE_SHA256')==DIAGNOSTIC_CANDIDATE_REF['sha256']\n             and Path(DIAGNOSTIC_BINDER_REF['path']).with_name('a0_runtime.py')==Path(DIAGNOSTIC_CANDIDATE_REF['path']))\n    namespace={'__name__':'_frw_s412_exact_runtime_diagnostics','__file__':DIAGNOSTIC_BINDER_REF['path']}\n    exec(compile(raw,DIAGNOSTIC_BINDER_REF['path'],'exec'),namespace)\n    _require(namespace['bind'](runtime) is runtime)\n    return runtime\n"

def prepare(base_raw, binder_ref, candidate_ref):
    if type(base_raw) is not bytes or hashlib.sha256(base_raw).hexdigest()!=BASE_SHA256:
        raise ValueError('s412_exact_start_scope_base_required')
    for reference in (binder_ref,candidate_ref):
        if (type(reference) is not dict or set(reference)!={'path','sha256'}
                or type(reference['path']) is not str or not reference['path'].startswith('/home/jericho/.cache/')
                or '..' in reference['path'].split('/') or type(reference['sha256']) is not str
                or len(reference['sha256'])!=64 or any(c not in '0123456789abcdef' for c in reference['sha256'])):
            raise ValueError('s412_exact_source_pin_required')
    before=b'            runtime = module.Runtime(plan, budget=phase_left)\n'
    after=before+b'            _diag_bind_runtime(runtime)\n'
    if base_raw.count(before)!=1:raise ValueError('s412_exact_factory_required')
    loader=LOADER_TEMPLATE.replace('__BINDER_REFERENCE_LITERAL__',repr(binder_ref)).replace('__CANDIDATE_REFERENCE_LITERAL__',repr(candidate_ref)).encode()
    derived=base_raw.replace(before,after,1)+loader
    if derived.replace(after,before,1)[:-len(loader)]!=base_raw:
        raise ValueError('s412_exact_byte_inverse_required')
    compile(derived,'<S412-prepared-start-diagnostics>','exec')
    return derived
