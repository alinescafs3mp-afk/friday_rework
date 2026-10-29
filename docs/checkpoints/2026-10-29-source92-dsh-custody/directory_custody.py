"""Exact Source92 analysis excerpt; no installer, receipt or authority bootstrap.

This uses POSIX directory descriptors and Linux no-follow flags. Import only
provides the archived functions; integration and authentication remain external.
"""
import contextlib
import os
from pathlib import Path
import stat

IDENTITY_FIELDS = ('st_uid','st_gid','st_mode','st_nlink','st_dev','st_ino',
                   'st_size','st_mtime_ns','st_ctime_ns')

CUSTODY_FIELDS = ('st_uid','st_gid','st_mode','st_dev','st_ino')

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def identity(info):
    return {key:getattr(info,key) for key in IDENTITY_FIELDS}

def custody(value):
    return {key:value[key] for key in CUSTODY_FIELDS}

def safe_directory(info, protected):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.getuid())
            and info.st_gid in (0,os.getgid()) and not info.st_mode & 0o7002
            and (protected or not info.st_mode & 0o020), 'unsafe parent custody')
    return protected or (info.st_uid == os.getuid() and info.st_gid == os.getgid()
                         and not info.st_mode & 0o077)

@contextlib.contextmanager
def protected_parent(path):
    """Keep directory fd/path custody while allowing unrelated entry churn.

    Directory size, times and nlink describe entries, not identity or access.
    Full directory metadata remains in the yielded rows for existing consumers.
    Every retained fd and each parent-relative pathname edge are checked again.
    Regular-file metadata, link count, bytes and pins remain the original checks.
    """
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(str(path)),
            'noncanonical absolute path')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fds, parents, names = [], [], []
    protected = False
    try:
        fd = os.open('/',flags); fds.append(fd); names.append('/')
        current = Path('/')
        for part in ('',*path.parts[1:]):
            if part:
                fd = os.open(part,flags,dir_fd=fd)
                fds.append(fd); names.append(part); current /= part
            info = os.fstat(fd)
            protected = safe_directory(info,protected)
            parents.append({'path':str(current),'identity':identity(info)})
        require(protected,'no protected owning parent')
        yield fd, parents
        protected = False
        for index,row in enumerate(parents):
            held = os.fstat(fds[index])
            reached = (os.stat('/',follow_symlinks=False) if index == 0 else
                       os.stat(names[index],dir_fd=fds[index-1],follow_symlinks=False))
            expected = custody(row['identity'])
            require(custody(identity(held)) == expected
                    and custody(identity(reached)) == expected,
                    'parent custody changed while reading: '+row['path'])
            protected = safe_directory(held,protected)
            safe_directory(reached,protected)
        require(protected,'protected owning parent changed while reading')
    finally:
        for fd in reversed(fds):
            os.close(fd)
