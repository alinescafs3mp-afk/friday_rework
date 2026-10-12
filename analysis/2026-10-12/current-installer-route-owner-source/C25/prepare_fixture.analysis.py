"""INERT preparation after Root exact admission; never imports Source.

Usage: python -I -B PREPARE-FIXTURE.py original_clock_path bytes sha256
       fresh_private_directory positive|worker_flock
Uses the passed ORIGINAL clock, never creates/restarts an execution budget.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent


def pin(path):
    raw = Path(path).read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def put(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def main():
    assert len(sys.argv) == 6
    clock = {'path': sys.argv[1], 'bytes': int(sys.argv[2]), 'sha256': sys.argv[3]}
    assert pin(clock['path']) == clock
    root = Path(sys.argv[4])
    assert root.is_absolute() and root.is_relative_to(BASE) and '..' not in root.parts
    assert sys.argv[5] in ('positive', 'worker_flock')
    root.mkdir(mode=0o700)
    entry = root / 'entry.py'
    body = ('import fcntl,json,os\nfrom pathlib import Path\ndef perform(p,s):\n'
            ' d=json.loads(Path(p).read_bytes())\n'
            ' if d["case"]=="worker_flock":\n'
            '  mark=os.open(d["phase"],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)\n'
            '  os.write(mark,b"BEFORE_PHYSICAL_FLOCK");os.fsync(mark);os.close(mark)\n'
            '  fd=os.open(d["lock"],os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX)\n'
            '  raise RuntimeError("fixture lock unexpectedly released")\n'
            ' fd=os.open(d["marker"],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)\n'
            ' os.write(fd,b"REAL_FIXTURE_ENTRY_RETURN");os.fsync(fd);os.close(fd)\n'
            ' return {"isolated_fixture":True}\n').encode()
    put(entry, body)
    lock = root / 'outside.lock'
    put(lock, b'')
    descriptor = root / 'descriptor.json'
    put(descriptor, (json.dumps({'source': pin(entry), 'clock': clock, 'case': sys.argv[5],
         'lock': str(lock), 'phase': str(root / 'PHYSICAL-STALL-REACHED'),
         'marker': str(root / 'ENTRY-MARKER')}, sort_keys=True) + '\n').encode())
    spec = {'host': pin(BASE / 'Source/stock_install_host.py'),
            'caller': pin(BASE / 'Source/stock_install_caller.py'),
            'helper': pin(Path('/analysis/NOT_CONNECTED/bounded_install_helper.py')),
            'entry': pin(entry), 'descriptor': pin(descriptor), 'clock': clock,
            'evidence': str(root / 'attempt'), 'fixture_root': str(root), 'record': str(root / 'outside'),
            'wall_cap': 2, 'caller_wall_seconds': 2, 'host_cleanup_seconds': 3, 'outer_timeout_seconds': 10}
    path = root / 'INPUT.json'
    put(path, (json.dumps(spec, sort_keys=True) + '\n').encode())
    print(json.dumps({'input': pin(path), 'command': ['/usr/bin/prlimit', '--as=268435456:268435456',
         '--cpu=60:60', '--fsize=67108864:67108864', '--core=0:0', '/usr/bin/taskset', '-c', '0,1',
         '/usr/bin/timeout', '-s', 'KILL', '10s', '/analysis/NOT_CONNECTED/python', '-I', '-B',
         str(BASE / 'Source/stock_install_host.py'), str(path), str(pin(path)['bytes']), pin(path)['sha256']],
         'worker_flock_requires': 'Root separately holds exact outside.lock via existing stock flock',
         'authority': 'NOT_MINTED; Root external exact invocation review still required'}))


if __name__ == '__main__':
    main()
