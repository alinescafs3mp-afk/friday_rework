"""INERT C32 Source fixture until Root reviews the exact external invocation.

Exercises captured547 through unchanged3f78/af730 and final70c. No installer
perform, native enter/call, new issuer, model or subprocess. JSON pins confine
the externally reviewed request and never authenticate Root.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import types

LIMIT = 65536
SELF = str(Path(__file__).resolve())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read_pin(ref, maximum=1048576):
    require(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'}, 'pin shape')
    p = Path(ref['path'])
    require(p.is_absolute() and '..' not in p.parts and str(p) == os.path.normpath(str(p)), 'pin path')
    require(type(ref['bytes']) is int and 0 <= ref['bytes'] <= maximum, 'pin size')
    for parent in reversed(p.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode), 'pin ancestor')
    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_nlink == 1 and a.st_uid == os.getuid()
                and not a.st_mode & 0o077 and a.st_size <= maximum, 'private stable regular')
        raw = b''
        while True:
            b = os.read(fd, min(8192, maximum + 1 - len(raw)))
            if not b:
                break
            raw += b
            require(len(raw) <= maximum, 'read bound')
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_mtime_ns, s.st_ctime_ns)
        require(key(a) == key(os.fstat(fd)) == key(p.lstat()), 'pin drift')
        require(len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256'], 'pin mismatch')
        return raw
    finally:
        os.close(fd)


def perform(path, sha):
    descriptor = {'path': path, 'bytes': Path(path).lstat().st_size, 'sha256': sha}
    d = json.loads(read_pin(descriptor, LIMIT))
    require(set(d) == {'source', 'clock', 'installer', 'dependencies', 'routes', 'scope'}, 'descriptor fields')
    require(d['scope'] == 'SOURCE_READONLY_CAPTURED_IMPORTS_NO_NATIVE_RPC_NO_INSTALL', 'readonly scope')
    require(d['source']['path'] == SELF, 'exact entry identity')
    read_pin(d['source'])
    raw = read_pin(d['installer'])
    require(d['installer']['sha256'] == '5473302e6a8475a346e13f43a62ff363f4616e9eb56d01c7f19c79f9029a8f79', 'exact reviewed547')
    M = types.ModuleType('<C32-captured547-readonly>')
    M.__file__ = d['installer']['path']
    exec(compile(raw, M.__file__, 'exec', dont_inherit=True), M.__dict__)
    M.resources()
    M.clock(json.loads(read_pin(d['clock'], LIMIT)))
    # Top-level Source547 imports are stdlib only. Application dependency code
    # and both NativeControl constructors start only after BOTH existing locks.
    for name in M.LOCK_NAMES:
        s = (M.R / name).lstat()
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1
                and not s.st_mode & 0o077, 'existing private advisory lock required')
    held = M.acquire()
    try:
        request = {'dependencies': d['dependencies'], 'routes': d['routes'], '_held_locks': held}
        captured = M.CapturedDependencies(request)
        imported = {name: captured.module(name) for name in M.DEPENDENCIES}
        require(imported['lifecycle_core'].Envelope('fixture', '1', 'fresh', 'turn', {}).key == 'fixture#1', 'actual captured dataclass')
        M.validate_routes(request)
        M.clock(json.loads(read_pin(d['clock'], LIMIT)))
        return {'scope': d['scope'], 'source': d['installer'], 'five_top_level_dependencies': list(imported),
                'actual_NativeControl_constructors': 2, 'native_RPC_install_effects': 0,
                'runtime_install_release_accepted': False, 'outer_owner_acceptance': 'NOT_CLAIMED'}
    finally:
        for fd in reversed(held):
            os.close(fd)
