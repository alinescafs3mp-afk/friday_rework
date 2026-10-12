import os, sys, json, subprocess, signal, resource, select
from pathlib import Path

O = Path(__file__).parent
AS = 268435456
assert resource.getrlimit(resource.RLIMIT_AS) == (AS, AS)

def birth(pid):
    try:
        return Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()[19]
    except FileNotFoundError:
        return None

def put(name, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(O / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())

put('PARENT-BIRTH.json', {'pid': os.getpid(), 'birth': birth(os.getpid()),
                        'outer_pid': os.getppid(), 'outer_birth': birth(os.getppid()),
                        'AS': list(resource.getrlimit(resource.RLIMIT_AS)),
                        'limits': Path('/proc/self/limits').read_text(),
                        'Source_caller_worker_hard_AS_sum': 2 * AS,
                        'outer_guard_AS_additional': AS})
p = subprocess.Popen([sys.executable, '-I', '-B', str(O / 'worker.py')],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
ticks = birth(p.pid)
pfd = os.pidfd_open(p.pid)
try:
    assert select.select([p.stdout], [], [], 3)[0]
    row = json.loads(p.stdout.readline())
    assert row['pid'] == p.pid and row['birth'] == ticks and row['AS'] == [AS, AS] and len(row['affinity']) == 2
    put('BEFORE-GO.json', {'owned': row, 'Source_caller_worker_hard_AS_sum': 2 * AS,
                         'hard_before_Python_and_GO': True, 'actual_readonly_scope': True})
    p.stdin.write(b'G')
    p.stdin.flush()
    p.stdin.close()
    p.stdin = None
    out, err = p.communicate(timeout=10)
except BaseException as exc:
    if birth(p.pid) == ticks:
        signal.pidfd_send_signal(pfd, signal.SIGKILL)
    out, err = p.communicate(timeout=3)
    put('REFUSAL.json', {'class': type(exc).__name__, 'message': str(exc)[:300], 'no_retry': True})
finally:
    os.close(pfd)
code = p.returncode
put('DIRECT-RETURN.json', {'pid': p.pid, 'birth': ticks, 'returncode': code,
                         'direct_wait': True, 'fresh_exact_birth_absent': birth(p.pid) != ticks,
                         'stdout': out[:16000].decode(), 'stderr': err[:4000].decode(),
                         'SourceScope': 'readonly metadata only; no installation/native RPC grant'})
print(json.dumps({'returncode': code, 'fresh_absent': birth(p.pid) != ticks}))
sys.exit(code if code >= 0 else 128 - code)
