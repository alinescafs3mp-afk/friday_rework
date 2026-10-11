"""Inert canonical RESULT-only selector. No child CLI, retry, queue/start.

Future canonical sender supplies independently reviewed exact transport pin.
Existing arguments remain; two optional --rpc-grant flags supply fresh grant.
Non-RESULT messages continue through the unchanged original main body.
"""
from pathlib import Path
import asyncio
import hashlib
import json
import os
import stat
import runpy


def dispatch_in_worker(args, parser, transport, custody):
    if custody is None or not custody.active: parser.error("whole-entry supervisor required")
    # Refuse before importing/effectful entries for every mismatch.
    if args.kind != 'RESULT': parser.error('RESULT selector direction')
    if not args.rpc_grant or not args.rpc_grant_sha: parser.error('RESULT requires exact reviewed RPC grant; no CLI fallback')
    # Only independently accepted transport bytes, never arbitrary grant-selected code.
    p = Path(transport['path']); s = p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1 or s.st_mode & 0o077:
        parser.error('transport ownership')
    for a in p.parents:
        if a.is_symlink(): parser.error('transport ancestor')
    if s.st_size > 65536: parser.error('transport bound')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        current = os.fstat(fd)
        if (s.st_dev, s.st_ino, s.st_ctime_ns, s.st_mtime_ns) != (current.st_dev, current.st_ino, current.st_ctime_ns, current.st_mtime_ns):
            parser.error('transport race')
        b = os.read(fd, 65537)
    finally: os.close(fd)
    if len(b) != transport['bytes'] or hashlib.sha256(b).hexdigest() != transport['sha256']:
        parser.error('transport exact source pin')
    ns = {'__file__': str(p), '__name__': 'reviewed_result_rpc'}
    exec(compile(b, str(p), 'exec'), ns)
    ref = {'path': str(args.rpc_grant), 'bytes': args.rpc_grant.lstat().st_size, 'sha256': args.rpc_grant_sha}
    grant = ns['loads'](ns['pinned'](ref))
    if (grant.get('source') != transport or grant.get('custody_dir') != str(args.rpc_custody_dir) or grant.get('event') != args.event
            or grant.get('assignment') != args.assignment_id or grant.get('generation') != args.assignment_generation
            or args.assignment_action not in (None, 'complete') or args.large_reason
            or grant.get('notice', {}).get('path') != str(args.ref)
            or grant.get('dependencies', {}).get('sender', {}).get('path') != str(args.sender_binding)
            or grant.get('dependencies', {}).get('recipient', {}).get('path') != str(args.recipient_binding)):
        parser.error('CLI/grant exact selector binding')
    result = asyncio.run(ns['deliver_in_worker'](args.rpc_grant, args.rpc_grant_sha, custody))
    return result
