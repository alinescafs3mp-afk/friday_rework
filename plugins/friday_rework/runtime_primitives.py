"""Pinned private input primitives shared by runtime observers and installer."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat


class Refused(ValueError):
    """A reason supplied by this source, rather than arbitrary exception text."""
    def __init__(self, reason):
        self.reason = reason if re.fullmatch('[a-z][a-z0-9_]{0,127}', reason) else 'invalid_input'
        super().__init__(self.reason)



def require(condition, reason):
    if not condition:
        raise Refused(reason)



def canonical(value):
    p = Path(value)
    require(p.is_absolute() and str(p) == value and '..' not in p.parts
            and p != Path('/') and p.resolve() == p, 'real_absolute_path_required')
    return p



def owned_file(path, *, private=False):
    p = canonical(str(path))
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and info.st_nlink == 1
                and (not private or not info.st_mode & 0o077), 'owned_regular_input_required')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read(64 * 1024**2 + 1)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_nlink')
        require(len(data) <= 64 * 1024**2 and all(getattr(info, k) == getattr(after, k) for k in fields),
                'input_changed_or_too_large')
        return data
    finally:
        os.close(fd)



def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate_input_field')
        out[key] = value
    return out



def read_json(path):
    return json.loads(owned_file(path, private=True), object_pairs_hook=unique)



def digest(data):
    return hashlib.sha256(data).hexdigest()



def pin(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and isinstance(value['sha256'], str)
            and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'exact_input_pin_required')
    require(digest(owned_file(value['path'])) == value['sha256'], 'input_pin_changed')
    return canonical(value['path'])

