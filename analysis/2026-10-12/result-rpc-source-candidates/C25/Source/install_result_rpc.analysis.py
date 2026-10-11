"""Private inert installer candidate. No CLI, network, subprocess or import effects.

The caller authenticates the independent review/grant issuer. File hashes alone
do not authenticate that issuer. C25 authorizes OFFLINE fixtures only.
Multi-file installation is journalled, NOT a multi-file atomic transaction.
All writers must honour the retained advisory installation locks.
"""
from __future__ import annotations
import builtins
import types
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import stat
import time

R = Path('/analysis/NOT_CONNECTED/runtime')
LIMIT = 65536
MAX = 67108864
SOURCE_MAX = 1048576
NAMES = {'sol-link-native-send.py', 'sol-link-result-rpc.py', 'sol-link-result-selector.py'}
LOCK_NAMES = ('friday-codex-auto-update.lock', 'sol-link-native-send.install.lock')
DEPENDENCIES = {'control': 'sol-link-native-control.py', 'reconnect': 'sol-link-native-reconnect.py',
                'lifecycle': 'subagent-lifecycle/lifecycle.py',
                'lifecycle_core': 'subagent-lifecycle/lifecycle_core.py', 'native_endpoint': 'native_endpoint.py'}


class Refusal(ValueError):
    pass


def loads(raw):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d: raise Refusal('duplicate JSON field')
            d[k] = v
        return d
    def bad(_): raise Refusal('nonfinite JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def encode(value):
    b = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if len(b) > LIMIT: raise Refusal('receipt bound')
    return b


def ancestors(p):
    p = Path(p)
    if not p.is_absolute() or '..' in p.parts or str(p) != os.path.normpath(str(p)):
        raise Refusal('absolute canonical path required')
    for a in reversed(p.parents):
        s = a.lstat()
        if not stat.S_ISDIR(s.st_mode): raise Refusal('symlink/non-directory ancestor')


def private_dir(p):
    p = Path(p); ancestors(p); s = p.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise Refusal('private owned directory required')


def identity(s):
    return [s.st_dev, s.st_ino, s.st_mtime_ns, s.st_ctime_ns, s.st_size, stat.S_IMODE(s.st_mode)]


def read(p, maximum=SOURCE_MAX):
    p = Path(p); ancestors(p); before = p.lstat()
    if not stat.S_ISREG(before.st_mode): raise Refusal('regular before open')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1
                or s.st_mode & 0o077 or not 0 <= s.st_size <= maximum
                or identity(before) != identity(s)):
            raise Refusal('owned private single-link stable regular required')
        parts = []; size = 0
        while True:
            b = os.read(fd, min(1048576, maximum + 1 - size))
            if not b: break
            parts.append(b); size += len(b)
            if size > maximum: raise Refusal('file bound')
        after = os.fstat(fd)
        if identity(s) != identity(after) or identity(p.lstat()) != identity(s):
            raise Refusal('file changed during read')
        return b''.join(parts), s
    finally: os.close(fd)


def pin(ref, maximum=SOURCE_MAX):
    if not isinstance(ref, dict) or set(ref) != {'path', 'bytes', 'sha256'}:
        raise Refusal('pin shape')
    if type(ref['bytes']) is not int or ref['bytes'] < 0:
        raise Refusal('pin bytes type')
    h = ref['sha256']
    if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
        raise Refusal('pin hash syntax')
    b, s = read(ref['path'], maximum)
    if len(b) != ref['bytes'] or hashlib.sha256(b).hexdigest() != h:
        raise Refusal('pin mismatch')
    return b, s


def reference(p):
    b, _ = read(p)
    return {'path': str(p), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}


def sync_dir(p):
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def exclusive(p, b, mode=0o400):
    private_dir(Path(p).parent)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        offset = 0
        while offset < len(b):
            count = os.write(fd, b[offset:])
            if count <= 0: raise OSError('zero/negative write')
            offset += count
        os.fchmod(fd, mode); os.fsync(fd)
    finally: os.close(fd)
    sync_dir(Path(p).parent)


def receipt(p, v): exclusive(p, encode(v))


def resources():
    for k, cap in ((resource.RLIMIT_AS, 268435456), (resource.RLIMIT_CPU, 60),
                   (resource.RLIMIT_FSIZE, MAX)):
        soft, hard = resource.getrlimit(k)
        if not 0 < soft <= hard <= cap: raise Refusal('finite helper limits')
    if resource.getrlimit(resource.RLIMIT_CORE) != (0, 0) or not 0 < len(os.sched_getaffinity(0)) <= 2:
        raise Refusal('CPU/core boundary')


def clock(value):
    fields = ('started_at_unix', 'started_at_monotonic', 'original_seconds',
              'cleanup_seconds', 'useful_deadline_unix', 'final_deadline_unix')
    if any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) for k in fields):
        raise Refusal('clock types')
    start = value['started_at_unix']; seconds = value['original_seconds']; clean = value['cleanup_seconds']
    elapsed = time.monotonic() - value['started_at_monotonic']
    if (seconds <= clean or clean < 3 or elapsed < 0 or time.time() < start
            or abs(time.time() - start - elapsed) > 2
            or value['useful_deadline_unix'] != start + seconds - clean
            or value['final_deadline_unix'] != start + seconds
            or time.time() >= value['useful_deadline_unix'] - 3
            or value['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip()):
        raise Refusal('expired/reset/foreign clock')


class CapturedDependencies:
    """Execute only same-read authenticated application bytes, including runpy/import edges.

    Trusted Python/stdlib/site-package runtime remains an external prerequisite.
    This is provenance enforcement, not a sandbox for malicious reviewed Python.
    No application dependency is imported through sys.path or reopened by runpy.
    """
    def __init__(self, d):
        self.d = d
        self.raw = {name: pin(ref)[0] for name, ref in d['dependencies'].items()}
        self.paths = {str(R / rel): name for name, rel in DEPENDENCIES.items()}
        self.modules = {}
        self.active = set()
        self.runpy = types.ModuleType('runpy')
        self.runpy.run_path = self.run_path
        self.sys = types.ModuleType('sys')
        import sys
        self.sys.__dict__.update(sys.__dict__)
        self.sys.path = list(sys.path)  # reconnect's insertion is closure-local.

    def check(self):
        lock_check(self.d['_held_locks'])

    def importer(self, name, globals=None, locals=None, fromlist=(), level=0):
        self.check()
        if level: raise Refusal('relative dependency import not admitted')
        if name == 'runpy': return self.runpy
        if name == 'sys': return self.sys
        if name in ('native_endpoint', 'lifecycle_core'):
            return self.module(name)
        # Only the reviewed dependency's runtime imports are admitted here.
        roots = {'argparse','asyncio','json','os','pathlib','websockets','contextlib',
                 'fcntl','hashlib','re','select','signal','stat','subprocess','time',
                 'typing','datetime','math','collections','dataclasses','errno'}
        if name.split('.')[0] not in roots:
            raise Refusal('unlisted transitive dependency import')
        return builtins.__import__(name, globals, locals, fromlist, level)

    def module(self, name):
        self.check()
        if name in self.modules: return self.modules[name]
        if name in self.active: raise Refusal('cyclic dependency load')
        if name not in self.raw: raise Refusal('uncaptured dependency')
        self.active.add(name)
        try:
            module = types.ModuleType(name)
            ns = module.__dict__
            ns.update(__file__=str(R / DEPENDENCIES[name]), __name__='<captured_dependency>',
                      __package__=None, __builtins__={**vars(builtins), '__import__':self.importer})
            exec(compile(self.raw[name], ns['__file__'], 'exec'), ns)
            self.modules[name] = module
            return module
        finally: self.active.remove(name)

    def run_path(self, path, init_globals=None, run_name=None):
        if init_globals is not None or run_name not in (None, '<run_path>'):
            raise Refusal('dependency runpy arguments not admitted')
        name = self.paths.get(str(path))
        if name is None: raise Refusal('uncaptured dependency run_path')
        return self.module(name).__dict__


def validate_routes(d):
    """Construct the actual reviewed local class; never enter/connect/call native RPC."""
    captured = CapturedDependencies(d)
    control = captured.module('control').NativeControl
    if set(d['routes']) != {'sol', 'astra'}: raise Refusal('route coverage')
    pids = set()
    for slot, expected in d['routes'].items():
        if set(expected) != {'binding', 'home', 'thread', 'generation', 'endpoint', 'births'}:
            raise Refusal('route shape')
        if expected['binding']['path'] != str(R / ('sol-link-' + slot + '.binding.json')):
            raise Refusal('binding path')
        b = loads(pin(expected['binding'])[0]); captured.check(); c = control(slot)
        endpoint = str(Path(expected['home']) / 'app-server-control/app-server-control.sock')
        if (b.get('role') != ('Sol' if slot == 'sol' else 'Astra')
                or b.get('account_home') != expected['home'] or b.get('thread_id') != expected['thread']
                or b.get('generation') != expected['generation'] or expected['endpoint'] != endpoint
                or b.get('backend_endpoint') not in (endpoint, 'unix://' + endpoint)
                or c.home != expected['home'] or c.thread != expected['thread'] or str(c.endpoint) != endpoint):
            raise Refusal('route drift')
        if set(expected['births']) != {str(b['pid']), str(b['backend_pid'])}:
            raise Refusal('solewriter birth coverage')
        for pid, birth in expected['births'].items():
            if Path('/proc/' + pid + '/stat').read_text().rsplit(')', 1)[1].split()[19] != birth:
                raise Refusal('solewriter birth drift')
            pids.add(pid)
    if len(pids) != 4 or d['routes']['sol']['thread'] == d['routes']['astra']['thread']:
        raise Refusal('separate solewriter slots')


def descriptor(p, sha):
    resources()
    b, _ = read(p, LIMIT)
    if hashlib.sha256(b).hexdigest() != sha: raise Refusal('descriptor SHA')
    d = loads(b)
    fields = {'schema', 'decision', 'mode', 'operation', 'transaction', 'source', 'review',
              'clock', 'routes', 'dependencies', 'files', 'audit', 'backup', 'installation'}
    if set(d) != fields or d['schema'] != 'friday.result-rpc.install.v1': raise Refusal('descriptor fields')
    if d['mode'] != 'LIVE' or d['decision'] != 'APPROVE_REVIEWED_RESULT_RPC_' + d['operation']:
        raise Refusal('explicit approved operation required')
    if d['operation'] not in ('INSTALL', 'ROLLBACK'): raise Refusal('operation')
    tx = d['transaction']
    if not isinstance(tx, str) or not 1 <= len(tx) <= 80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in tx):
        raise Refusal('transaction syntax')
    sb, _ = pin(d['source'], LIMIT)
    if Path(d['source']['path']) != Path(__file__).absolute(): raise Refusal('installer source identity')
    review = loads(pin(d['review'], LIMIT)[0])
    # Descriptor omits review from its digest to avoid a circular review hash.
    core = {k: v for k, v in d.items() if k != 'review'}
    if (set(review) != {'decision', 'descriptor_core_sha256', 'installer_sha256', 'accepted_sources'}
            or review['decision'] != 'ACCEPT_RESULT_RPC_INSTALL_DESCRIPTOR'
            or review['descriptor_core_sha256'] != hashlib.sha256(encode(core)).hexdigest()
            or review['installer_sha256'] != d['source']['sha256']):
        raise Refusal('independent descriptor/source review')
    clock(loads(pin(d['clock'], LIMIT)[0]))
    private_dir(R)
    # Targets are an explicit three-file surface, never receipts, bindings or guards.
    if not isinstance(d['files'], list) or not 1 <= len(d['files']) <= 3:
        raise Refusal('target count')
    seen = set()
    for f in d['files']:
        if set(f) != {'name', 'old', 'new', 'mode'} or f['name'] not in NAMES or f['name'] in seen:
            raise Refusal('target scope/duplicate')
        seen.add(f['name'])
        if type(f['mode']) is not int or f['mode'] not in (0o400, 0o600, 0o700): raise Refusal('target mode')
        new, _ = pin(f['new'])
        if review['accepted_sources'].get(f['name']) != f['new']['sha256']:
            raise Refusal('new bytes independent acceptance')
        if f['old'] is not None and f['old']['path'] != str(R / f['name']):
            raise Refusal('old target path')
        if f['name'] == 'sol-link-native-send.py' and f['old'] is None:
            raise Refusal('canonical old bytes required')
    if set(review['accepted_sources']) != seen: raise Refusal('accepted source coverage')
    if not isinstance(d['dependencies'], dict) or set(d['dependencies']) != set(DEPENDENCIES):
        raise Refusal('dependency closure')
    for name, ref in d['dependencies'].items():
        if ref['path'] != str(R / DEPENDENCIES[name]): raise Refusal('dependency path')
        pin(ref)
    for name in ('audit', 'backup'):
        path = Path(d[name]); ancestors(path)
        expected = R / ('sol-link-result-install-evidence' if name == 'audit' else 'subagent-lifecycle/backups')
        if path.parent != expected or path.name != tx: raise Refusal('exclusive evidence/backup namespace')
        private_dir(expected)
    if d['operation'] == 'INSTALL' and d['installation'] is not None: raise Refusal('unexpected install receipt')
    return d, sha


def recheck(d):
    lock_check(d['_held_locks'])
    pin(d['source'], LIMIT); pin(d['review'], LIMIT); clock(loads(pin(d['clock'], LIMIT)[0]))
    for ref in d['dependencies'].values(): pin(ref)
    for f in d['files']: pin(f['new'])
    validate_routes(d)


def target(f, installed=None):
    p = R / f['name']
    if installed is not None:
        b, s = read(p)
        if (hashlib.sha256(b).hexdigest() != f['new']['sha256'] or len(b) != f['new']['bytes']
                or stat.S_IMODE(s.st_mode) != f['mode'] or identity(s) != installed['installed_identity']):
            raise Refusal('installed bytes/identity changed; preserve owner changes')
        return b, s
    if f['old'] is None:
        if os.path.lexists(p): raise Refusal('new target collision')
        return None, None
    b, s = pin(f['old'])
    if stat.S_IMODE(s.st_mode) != f['mode']: raise Refusal('old/new mode must be preserved')
    return b, s


def acquire():
    held = []
    try:
        for name in LOCK_NAMES:
            p = R / name; ancestors(p)
            fd = os.open(p, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            held.append(fd); s = os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1 or s.st_mode & 0o077:
                raise Refusal('lock ownership')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return held
    except BaseException:
        for fd in reversed(held): os.close(fd)
        raise


def lock_check(held):
    for name, fd in zip(LOCK_NAMES, held):
        s = os.fstat(fd); current = (R / name).lstat()
        if ((s.st_dev, s.st_ino) != (current.st_dev, current.st_ino) or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid() or current.st_nlink != 1 or current.st_mode & 0o077):
            raise Refusal('held lock name replaced')


def completed_check(completed):
    for f, raw, ident in completed:
        p = R / f['name']
        if raw is None:
            if os.path.lexists(p): raise Refusal('removed file recreated concurrently')
        else:
            b, s = read(p)
            if b != raw or identity(s) != ident: raise Refusal('completed replacement changed concurrently')


class AuditJournal:
    """Retain directory inode and bind every journal write and readback with openat."""
    def __init__(self, path):
        self.path = Path(path)
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.history = {}
        self.closed = False
        try: self.check()
        except BaseException:
            os.close(self.fd); self.closed = True
            raise

    def check(self):
        private_dir(self.path)
        a, b = os.fstat(self.fd), self.path.lstat()
        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
            raise Refusal('audit directory inode changed')

    def read(self, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                    or st.st_nlink != 1 or st.st_mode & 0o077 or st.st_size > LIMIT):
                raise Refusal('audit regular owned bounded file required')
            chunks = []; count = 0
            while True:
                b = os.read(fd, min(8192, LIMIT + 1 - count))
                if not b: break
                count += len(b); chunks.append(b)
                if count > LIMIT: raise Refusal('audit read bound')
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            if identity(st) != identity(os.fstat(fd)) or identity(st) != identity(named):
                raise Refusal('audit file changed during read')
            return b''.join(chunks), identity(st)
        finally: os.close(fd)

    def verify(self):
        self.check()
        if set(os.listdir(self.fd)) != set(self.history):
            raise Refusal('audit history coverage changed')
        for name, expected in self.history.items():
            if self.read(name) != expected: raise Refusal('audit history bytes/identity changed')
        self.check()

    def receipt(self, name, value, stop=False):
        if not stop: self.verify()
        if '/' in name or not name.endswith('.json'): raise Refusal('audit leaf')
        raw = encode(value)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o400, dir_fd=self.fd)
        try:
            off = 0
            while off < len(raw):
                count = os.write(fd, raw[off:])
                if count <= 0: raise OSError('audit zero write')
                off += count
            os.fchmod(fd, 0o400); os.fsync(fd)
        finally: os.close(fd)
        os.fsync(self.fd)
        observed = self.read(name)
        if observed[0] != raw: raise Refusal('audit readback mismatch')
        self.history[name] = observed
        if not stop: self.verify()

    def close(self):
        if not self.closed:
            os.close(self.fd); self.closed = True


def perform(p, sha):
    """Future bounded host entry. C25 calls only against relocated owned fixtures."""
    resources()
    held = acquire()  # No dependency module/constructor may run before BOTH locks.
    mutation = False; journal = None
    try:
        lock_check(held)
        d, digest = descriptor(p, sha)
        d['_held_locks'] = held
        audit = Path(d['audit']); backup = Path(d['backup'])
        recheck(d)
        # Existing reservation/evidence always stops: never resume/replay implicitly.
        audit.mkdir(mode=0o700)
        journal = AuditJournal(audit); sync_dir(audit.parent)
        journal.receipt('RESERVED.json', {'state': 'UNKNOWN_NO_REPLAY', 'descriptor_sha256': digest,
                                        'operation': d['operation'], 'transaction': d['transaction']})
        originals = []; entries = []
        if d['operation'] == 'INSTALL':
            for f in d['files']:
                old, s = target(f); originals.append((f, old, s))
            backup.mkdir(mode=0o700); sync_dir(backup.parent)
            for f, old, s in originals:
                bp = backup / f['name']
                if old is not None: exclusive(bp, old, stat.S_IMODE(s.st_mode))
                entries.append({'file': f, 'old_identity': identity(s) if s else None,
                                'backup': reference(bp) if old is not None else None})
            receipt(backup / 'MANIFEST.json', {'descriptor_sha256': digest, 'files': entries})
            backup_ref = reference(backup / 'MANIFEST.json')
        else:
            if not isinstance(d['installation'], dict): raise Refusal('exact installed receipt required')
            installed = loads(pin(d['installation'], LIMIT)[0])
            if installed.get('state') != 'INSTALLED_DURABLE' or installed.get('files_descriptor') != d['files']:
                raise Refusal('installed receipt binding')
            prior = loads(pin(installed['backup_manifest'], LIMIT)[0])
            bp = Path(installed['backup_manifest']['path'])
            if bp.name != 'MANIFEST.json' or bp.parent.parent != R / 'subagent-lifecycle/backups':
                raise Refusal('original exclusive backup namespace')
            entries = prior['files']; backup_ref = installed['backup_manifest']
            if [e['file'] for e in entries] != d['files'] or len(installed['files']) != len(entries):
                raise Refusal('backup/installed exact coverage')
            for e, i in zip(entries, installed['files']):
                if i['file'] != e['file']: raise Refusal('installed ordered coverage')
                f = e['file']; old_ref = f['old']; saved_ref = e['backup']
                if (old_ref is None) != (saved_ref is None): raise Refusal('original absent/backup mismatch')
                if saved_ref is not None:
                    if (saved_ref['bytes'] != old_ref['bytes'] or saved_ref['sha256'] != old_ref['sha256']
                            or Path(saved_ref['path']) != bp.parent / f['name']
                            or stat.S_IMODE(pin(saved_ref)[1].st_mode) != f['mode']):
                        raise Refusal('exact original backup bytes/mode')
                old = pin(e['backup'])[0] if e['backup'] else None
                target(e['file'], i); originals.append((e['file'], old, i))
        stages = []
        for f, old, s in originals:
            raw = pin(f['new'])[0] if d['operation'] == 'INSTALL' else old
            stage = R / ('.' + f['name'] + '.' + d['transaction'] + '.stage')
            if raw is not None: exclusive(stage, raw, f['mode'])
            stages.append((f, stage, raw, s))
        journal.receipt('PREPARED.json', {'backup_manifest': backup_ref, 'files': entries,
                                         'multi_file_atomic': False, 'no_automatic_rollback': True})
        completed = []
        for f, stage, raw, old_state in stages:
            recheck(d); lock_check(held); completed_check(completed)
            if d['operation'] == 'INSTALL':
                _, now = target(f)
                if old_state is not None and identity(now) != identity(old_state): raise Refusal('owner change before rename')
            else: target(f, old_state)
            if raw is not None:
                staged, ss = read(stage)
                if staged != raw or stat.S_IMODE(ss.st_mode) != f['mode']: raise Refusal('staging drift')
            # Last comparison precedes atomic rename while advisory locks are held.
            # POSIX has no content-CAS rename: noncooperating writers are unproven.
            mutation = True
            if raw is None: os.unlink(R / f['name'])
            elif d['operation'] == 'INSTALL' and f['old'] is None:
                os.link(stage, R / f['name'], follow_symlinks=False)
                stage.unlink()
            else: os.replace(stage, R / f['name'])
            sync_dir(R)
            if raw is None:
                if os.path.lexists(R / f['name']): raise Refusal('removed target recreated')
                ident = None
            else:
                actual, ns = read(R / f['name'])
                if actual != raw or stat.S_IMODE(ns.st_mode) != f['mode']: raise Refusal('post-replace drift')
                ident = identity(ns)
            journal.receipt(f['name'] + '.DURABLE.json', {'file': f, 'installed_identity': ident})
            completed.append((f, raw, ident))
        recheck(d); lock_check(held); completed_check(completed)
        final = {'state': 'INSTALLED_DURABLE' if d['operation'] == 'INSTALL' else 'ROLLED_BACK_DURABLE',
                 'descriptor_sha256': digest, 'files_descriptor': d['files'], 'backup_manifest': backup_ref,
                 'files': [loads(journal.read(f['name'] + '.DURABLE.json')[0]) for f in d['files']],
                 'no_replay': True, 'multi_file_atomic': False, 'native_effects': 0}
        journal.verify()
        journal.receipt('FINAL.json', final)
        journal.verify(); lock_check(held); completed_check(completed)
        return final
    except BaseException as exc:
        # Even a failed fsync/rename can have taken effect. No retry/auto rollback.
        if journal is not None:
            try: journal.receipt('STOP.json', {'state': 'UNKNOWN_NO_REPLAY',
                                 'exception_class': type(exc).__name__,
                                 'mutation_may_have_started': mutation,
                                 'preserve_owner_changes': True}, stop=True)
            except BaseException: pass
        raise
    finally:
        try:
            if journal is not None: journal.close()
        finally:
            for fd in reversed(held): os.close(fd)  # Locks and lock inode names persist.
