"""Bounded stable file copies inside existing task-owned storage.

Callers prove source provenance, ownership and worker quiescence separately.
This module neither downloads a file nor chooses a job, owner or destination.
The staging directory must stay outside every worker's writable grants.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid


class ArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class StagedArtifact:
    logical_name: str
    reference: str
    media_type: str
    size_bytes: int
    sha256: str
    origin_reference: str
    complete: bool = True
    verification: str = "verified"


def _label(value, limit):
    if (not isinstance(value, str) or not value or "\x00" in value
            or len(value.encode("utf-8")) > limit):
        raise ArtifactError("invalid_artifact_label")
    return value


def _limit(value):
    if type(value) is not int or value <= 0:
        raise ArtifactError("invalid_artifact_limit")
    return value


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink, info.st_mode, info.st_uid)


@contextmanager
def _root(path, *, private=False):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ArtifactError("noncanonical_artifact_root")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or private and stat.S_IMODE(info.st_mode) != 0o700:
            raise ArtifactError("unsafe_artifact_root")
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _source(root_fd, relative):
    _label(relative, 2048)
    parts = PurePosixPath(relative).parts
    if (not parts or PurePosixPath(relative).is_absolute()
            or any(p in {".", ".."} for p in relative.split("/"))
            or "//" in relative or relative.endswith("/")):
        raise ArtifactError("escaping_artifact_path")
    parent = os.dup(root_fd)
    fd = None
    try:
        for name in parts[:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        # Nonblocking prevents a malicious FIFO from hanging before fstat.
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid()):
            raise ArtifactError("unsafe_artifact_file")
        yield fd, info
        after = os.fstat(fd)
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if _identity(info) != _identity(after) or _identity(after) != _identity(named):
            raise ArtifactError("artifact_changed_during_read")
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def stage_file(*, source_root, relative_path, staging_root, logical_name,
               media_type, origin_reference, max_bytes):
    """Copy one checked source to a collision-safe stable name, with no overwrite.

    max_bytes is the caller's actual configured limit, never a guessed platform
    constant. Original filenames are labels only. Failed copies publish no
    manifest; source data and any prior staged files are preserved.
    """
    max_bytes = _limit(max_bytes)
    logical_name = _label(logical_name, 512)
    media_type = _label(media_type, 256)
    origin_reference = _label(origin_reference, 2048)
    suffix = Path(logical_name).suffix
    suffix = suffix if re.fullmatch(r"\.[a-zA-Z0-9]{1,12}", suffix) else ".bin"
    final = uuid.uuid4().hex + suffix
    temporary = "." + final + ".partial"
    with _root(staging_root, private=True) as destination, _root(source_root) as source:
        output = None
        published = False
        try:
            with _source(source, relative_path) as (input_fd, before):
                if before.st_size > max_bytes:
                    raise ArtifactError("artifact_too_large")
                output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=destination)
                digest, size = hashlib.sha256(), 0
                while data := os.read(input_fd, min(65536, max_bytes - size + 1)):
                    size += len(data)
                    if size > max_bytes:
                        raise ArtifactError("artifact_too_large")
                    digest.update(data)
                    view = memoryview(data)
                    while view:
                        written = os.write(output, view)
                        if written <= 0:
                            raise ArtifactError("short_artifact_write")
                        view = view[written:]
                if size != before.st_size:
                    raise ArtifactError("artifact_changed_during_read")
                os.fchmod(output, 0o400)
                os.fsync(output)
            # link is an atomic no-replace publication inside this same owned
            # filesystem. No window may overwrite an older delivery artifact.
            os.link(temporary, final, src_dir_fd=destination, dst_dir_fd=destination,
                    follow_symlinks=False)
            published = True
            os.unlink(temporary, dir_fd=destination)
            os.fsync(destination)
            return StagedArtifact(logical_name, final, media_type, size, digest.hexdigest(), origin_reference)
        finally:
            if output is not None:
                os.close(output)
                if not published:
                    os.unlink(temporary, dir_fd=destination)


def read_staged(*, staging_root, artifact: StagedArtifact, max_bytes):
    """Read the exact checked bytes for bounded delivery, never a mutable path.

    Returning bytes lets a native upload use the same payload we hashed. Large
    files require the host's separately verified streaming/transfer path.
    """
    max_bytes = _limit(max_bytes)
    if (not isinstance(artifact, StagedArtifact) or not artifact.complete
            or artifact.verification != "verified" or type(artifact.size_bytes) is not int
            or not 0 <= artifact.size_bytes <= max_bytes
            or not re.fullmatch(r"[0-9a-f]{64}", artifact.sha256)):
        raise ArtifactError("unverified_staged_artifact")
    with _root(staging_root, private=True) as root, _source(root, artifact.reference) as (fd, info):
        if info.st_size != artifact.size_bytes or stat.S_IMODE(info.st_mode) != 0o400:
            raise ArtifactError("staged_artifact_changed")
        pieces, size, digest = [], 0, hashlib.sha256()
        while data := os.read(fd, min(65536, max_bytes - size + 1)):
            size += len(data)
            if size > max_bytes:
                raise ArtifactError("artifact_too_large")
            pieces.append(data)
            digest.update(data)
        if size != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
            raise ArtifactError("staged_artifact_changed")
        return b"".join(pieces)
