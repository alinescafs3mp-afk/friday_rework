"""Own Linux sealed memfd and strict main-ELF map observations. SOURCE only.

This is deliberately separate from pathname HeldFile/HostProvenance. It neither
executes bytes nor grants startup, loader, import, cgroup or native authority.
Caller bytes/digest are inputs, not independently established source provenance.
Synthetic map text establishes only consistency, never actual loaded-code proof.
"""
import fcntl
import hashlib
import os
import re
import stat
import struct
from dataclasses import dataclass

MAX_BYTES = 8 * 1024 * 1024
MAX_MAP_BYTES = 65536
TERMINAL_SEALS = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                  fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)


class Refused(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Refused(reason)


def birth():
    with open('/proc/self/stat', 'rb') as stream:
        data = stream.read(16385)
    require(len(data) <= 16384, 'BIRTH_SIZE')
    fields = data[data.rfind(b')') + 2:].split()
    return (os.getpid(), int(fields[19]))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fd_signature(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read_exact(fd, size):
    require(type(size) is int and 0 < size <= MAX_BYTES, 'BYTE_LIMIT')
    parts = []
    offset = 0
    while offset < size:
        part = os.pread(fd, min(65536, size - offset), offset)
        require(bool(part), 'SHORT_FD')
        parts.append(part)
        offset += len(part)
    require(os.pread(fd, 1, size) == b'', 'LONG_FD')
    return b''.join(parts)


@dataclass(frozen=True)
class ExecutableSegment:
    offset: int
    virtual_address: int
    file_size: int
    memory_size: int
    flags: int


def main_elf(raw):
    """Bounded ELF64 little-endian x86-64 ET_EXEC, static LOAD/NULL/STACK only.

    This conservative subset rejects PT_INTERP and all PT_DYNAMIC, including
    DT_NEEDED, and executable zero-fill. It does not qualify ELF execution.
    """
    require(type(raw) is bytes and 64 <= len(raw) <= MAX_BYTES, 'ELF_SIZE')
    require(raw[:7] == b'\x7fELF\x02\x01\x01' and raw[7:16] == b'\0' * 9,
            'ELF_IDENT')
    h = struct.unpack_from('<HHIQQQIHHHHHH', raw, 16)
    typ, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, *_ = h
    require((typ, machine, version, flags, ehsize, phsize) == (2, 62, 1, 0, 64, 56),
            'ELF_PLATFORM_OR_TYPE')
    require(1 <= phnum <= 16 and phoff >= 64 and phoff + phnum * 56 <= len(raw),
            'ELF_PROGRAM_HEADERS')
    page = os.sysconf('SC_PAGE_SIZE')
    require(type(page) is int and page > 0 and page & (page - 1) == 0, 'PAGE_SIZE')
    loads = []
    for i in range(phnum):
        pt, pf, po, va, pa, fs, ms, align = struct.unpack_from('<IIQQQQQQ', raw, phoff + i * 56)
        require(pt not in (2, 3), 'UNBOUND_DYNAMIC_LOADER')
        require(pt in (0, 1, 0x6474e551), 'UNBOUND_PROGRAM_HEADER')
        if pt == 0:
            continue
        require(pf & ~7 == 0 and not (pf & 2 and pf & 1), 'ELF_WRITABLE_EXECUTABLE')
        if pt == 0x6474e551:
            require(not pf & 1 and fs == 0 and ms == 0, 'ELF_EXECUTABLE_STACK')
            continue
        require(0 < fs <= ms and po + fs <= len(raw) and va + ms < 2**63,
                'ELF_SEGMENT_BOUNDS')
        require(align >= page and align & (align - 1) == 0 and po % align == va % align,
                'ELF_SEGMENT_ALIGNMENT')
        require(not pf & 1 or (pf == 5 and fs == ms), 'ELF_EXECUTABLE_SEGMENT')
        loads.append(ExecutableSegment(po, va, fs, ms, pf))
    require(loads and any(s.flags & 1 and s.virtual_address <= entry < s.virtual_address + s.file_size
                          for s in loads), 'ELF_EXECUTABLE_ENTRY')
    intervals = sorted((s.virtual_address // page * page,
                        ((s.virtual_address + s.memory_size + page - 1) // page) * page)
                       for s in loads)
    require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'ELF_SEGMENT_OVERLAP')
    file_intervals = sorted((s.offset // page * page, ((s.offset + s.file_size + page - 1) // page) * page) for s in loads)
    require(all(a[1] <= b[0] for a, b in zip(file_intervals, file_intervals[1:])), 'ELF_FILE_ALIAS')
    return tuple(s for s in loads if s.flags & 1)


@dataclass(frozen=True)
class DescriptorObservation:
    process_birth: tuple
    fd: int
    signature: tuple
    seals: int
    sha256: str
    kernel_label: str


@dataclass(frozen=True)
class MappingObservation:
    descriptor: DescriptorObservation
    maps_sha256: str
    rows: tuple
    status: str = 'SOURCE_ONLY_OBSERVATION_NO_RUNTIME_ADMISSION'


class SealedExecutable:
    """Create and retain ONE own FD; no pathname conversion or received authority.

    Kernel seals freeze content/size, not mode/ownership. Every use revalidates
    mode, uid/gid, nlink0, birth, exact FD slot, seals, label and bounded hash.
    Callers must not close/reassign its FD or mutate this object's internals.
    Arbitrary in-process code is not constrained by this Python library.
    """
    def __init__(self, raw, expected_sha256):
        require(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_sha256),
                'EXACT_SHA')
        require(type(raw) is bytes and 64 <= len(raw) <= MAX_BYTES, 'BYTE_LIMIT')
        require(digest(raw) == expected_sha256, 'INPUT_SHA')
        segments = main_elf(raw)
        self._fd = None
        self._closed = False
        self._birth = birth()
        self._sha = expected_sha256
        self._segments = segments
        self._size = len(raw)
        try:
            name = 'friday-main-' + os.urandom(12).hex()
            self._fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            offset = 0
            while offset < len(raw):
                count = os.pwrite(self._fd, raw[offset:offset + 65536], offset)
                require(count > 0, 'MEMFD_SHORT_WRITE')
                offset += count
            os.fchmod(self._fd, 0o500)
            require(read_exact(self._fd, len(raw)) == raw, 'MEMFD_COPY')
            fcntl.fcntl(self._fd, fcntl.F_ADD_SEALS, TERMINAL_SEALS)
            self._seals = fcntl.fcntl(self._fd, fcntl.F_GET_SEALS)
            require(self._seals & TERMINAL_SEALS == TERMINAL_SEALS, 'TERMINAL_SEALS')
            self._signature = fd_signature(os.fstat(self._fd))
            self._label = os.readlink('/proc/self/fd/' + str(self._fd))
            require(self._label == '/memfd:' + name + ' (deleted)', 'KERNEL_MEMFD_LABEL')
            self.verify()
        except BaseException:
            self.close()
            raise

    @property
    def fd(self):
        require(not self._closed, 'CLOSED')
        return self._fd

    @property
    def segments(self):
        return self._segments

    def verify(self):
        require(not self._closed and type(self._fd) is int, 'CLOSED')
        require(birth() == self._birth, 'PROCESS_BIRTH_DRIFT')
        try:
            st = os.fstat(self._fd)
            require(fd_signature(st) == self._signature, 'FD_SIGNATURE_DRIFT')
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 0 and
                    st.st_uid == os.getuid() and st.st_gid == os.getgid() and
                    stat.S_IMODE(st.st_mode) == 0o500, 'OWNED_MEMFD_STAT')
            require(fcntl.fcntl(self._fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC, 'FD_CLOEXEC_DRIFT')
            seals = fcntl.fcntl(self._fd, fcntl.F_GET_SEALS)
            require(seals == self._seals and seals & TERMINAL_SEALS == TERMINAL_SEALS,
                    'SEALS_DRIFT')
            require(os.readlink('/proc/self/fd/' + str(self._fd)) == self._label, 'FD_LABEL_DRIFT')
            require(digest(read_exact(self._fd, self._size)) == self._sha, 'FD_SHA_DRIFT')
        except OSError as error:
            raise Refused('FD_KERNEL_REFUSAL:' + str(error.errno)) from error
        return DescriptorObservation(self._birth, self._fd, self._signature, seals, self._sha, self._label)

    def close(self):
        """Idempotent owned closure; never close a foreign replacement FD slot."""
        if self._closed:
            return
        self._closed = True
        if self._fd is None:
            return
        try:
            st = os.fstat(self._fd)
        except OSError:
            return
        # Before signature capture during construction this slot was just created
        # and has not escaped. Later only matching dev/inode is our owned inode.
        sig = getattr(self, '_signature', None)
        if sig is not None and (st.st_dev, st.st_ino) != sig[:2]:
            raise Refused('CLOSE_FOREIGN_FD_REFUSED')
        require(birth() == self._birth, 'CLOSE_FOREIGN_PROCESS_REFUSED')
        os.close(self._fd)

    def observe_maps(self, raw, *, process_birth, descriptor):
        """Consume caller map bytes; refuse every unowned executable mapping.

        The own memfd's exact kernel deleted label is accepted only with its
        current retained FD identity/seals/SHA. Other deleted names, aliases,
        duplicate/split/overlapping segments and all foreign executable mappings
        are refused. Real whole-process Python maps normally refuse by design.
        """
        current = self.verify()
        require(type(descriptor) is DescriptorObservation and descriptor == current,
                'MAP_DESCRIPTOR_DRIFT')
        require(type(process_birth) is tuple and process_birth == current.process_birth,
                'MAP_PROCESS_BIRTH')
        require(type(raw) is bytes and 0 < len(raw) <= MAX_MAP_BYTES, 'MAP_BYTE_LIMIT')
        try:
            text = raw.decode('ascii')
        except UnicodeError as error:
            raise Refused('MAP_ENCODING') from error
        # Only LF separates kernel map rows. Other ASCII controls must not
        # become implicit rows or hide inside caller-supplied labels.
        require(text.endswith('\n') and
                all(ch == '\n' or ' ' <= ch <= '~' for ch in text), 'MAP_TEXT')
        lines = text[:-1].split('\n')
        require(1 <= len(lines) <= 1024, 'MAP_ROW_LIMIT')
        page = os.sysconf('SC_PAGE_SIZE')
        expected = {((s.virtual_address // page) * page,
                     ((s.virtual_address + s.memory_size + page - 1) // page) * page,
                     s.offset // page * page, 'r-xp') for s in self._segments}
        require(len(expected) == len(self._segments), 'AMBIGUOUS_ELF_SEGMENTS')
        found = set()
        rows = []
        intervals = []
        st = os.fstat(self._fd)
        pattern = re.compile(r'([0-9a-f]{1,16})-([0-9a-f]{1,16}) ([r-][w-][x-][ps]) ([0-9a-f]{1,16}) ([0-9a-f]{1,8}):([0-9a-f]{1,8}) ([0-9]{1,20})(?: (.+))?')
        for line in lines:
            m = pattern.fullmatch(line)
            require(m is not None, 'MAP_SYNTAX')
            start, end, perms, offset, major, minor, ino, label = m.groups()
            start, end, offset, major, minor, ino = (int(start, 16), int(end, 16),
                int(offset, 16), int(major, 16), int(minor, 16), int(ino))
            require(0 <= start < end < 2**63 and start % page == end % page == offset % page == 0,
                    'MAP_RANGE_OR_ALIGNMENT')
            intervals.append((start, end))
            own = (major, minor, ino) == (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
            if own:
                require(label == self._label, 'MAP_OWN_ALIAS_OR_DELETED')
                require('w' not in perms, 'MAP_OWN_WRITABLE')
                require('x' in perms, 'MAP_UNEXPECTED_OWN_ALIAS')
            if 'x' not in perms:
                continue
            require(own, 'MAP_FOREIGN_EXECUTABLE')
            key = (start, end, offset, perms)
            require(key in expected, 'MAP_SEGMENT_DRIFT')
            require(key not in found, 'MAP_AMBIGUOUS_DUPLICATE')
            found.add(key)
            rows.append((start, end, perms, offset, major, minor, ino, label))
        intervals.sort()
        require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'MAP_OVERLAP')
        require(found == expected, 'MAP_MISSING_EXECUTABLE_SEGMENT')
        require(self.verify() == current, 'MAP_FD_DRIFT_DURING_OBSERVATION')
        return MappingObservation(current, digest(raw), tuple(rows))
