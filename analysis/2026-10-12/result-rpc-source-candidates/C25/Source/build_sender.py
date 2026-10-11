"""Pure Source builder: original canonical parser/body preserved for non-RESULT.
No imports of the candidate, native execution, or global writes.
"""
import ast
import hashlib
import json
import os

OLD_SHA = '20604f9f31c5be9cdc77f8ae88be3348f60b0ed3141d2ae1e47ffe0febd6058f'


def build(old, selector_pin, transport_pin):
    if hashlib.sha256(old).hexdigest() != OLD_SHA: raise ValueError('canonical Source drift')
    text = old.decode()
    anchor = '    args = parser.parse_args()\n'
    if text.count(anchor) != 1: raise ValueError('parse boundary')
    # No injected untrusted executable text; repr only on strict JSON pin values.
    for pin in (selector_pin, transport_pin):
        if set(pin) != {'path', 'bytes', 'sha256'} or type(pin['bytes']) is not int:
            raise ValueError('pin shape')
        if not isinstance(pin['path'], str) or not isinstance(pin['sha256'], str): raise ValueError('pin values')
        if (pin['bytes'] <= 0 or pin['bytes'] > 65536 or not os.path.isabs(pin['path'])
                or os.path.normpath(pin['path']) != pin['path'] or '..' in pin['path'].split('/')
                or any(c.isspace() for c in pin['path']) or len(pin['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in pin['sha256'])):
            raise ValueError('pin bounds/canonical path/hash')
    inserted = ("    parser.add_argument('--rpc-grant', type=Path)\n"
                "    parser.add_argument('--rpc-grant-sha')\n" + anchor +
                "    if args.kind == 'RESULT':\n"
                f"        selector_pin = {selector_pin!r}\n"
                "        selector_path = Path(selector_pin['path'])\n"
                "        import stat\n"
                "        selector_stat = selector_path.lstat()\n"
                "        if not stat.S_ISREG(selector_stat.st_mode) or selector_stat.st_uid != os.getuid() or selector_stat.st_nlink != 1 or selector_stat.st_mode & 0o077 or selector_stat.st_size > 65536 or any(p.is_symlink() for p in selector_path.parents):\n"
                "            parser.error('reviewed selector ownership')\n"
                "        selector_fd = os.open(selector_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)\n"
                "        try:\n"
                "            selector_open = os.fstat(selector_fd)\n"
                "            if (selector_stat.st_dev, selector_stat.st_ino, selector_stat.st_ctime_ns, selector_stat.st_mtime_ns) != (selector_open.st_dev, selector_open.st_ino, selector_open.st_ctime_ns, selector_open.st_mtime_ns):\n"
                "                parser.error('reviewed selector race')\n"
                "            selector_bytes = os.read(selector_fd, 65537)\n"
                "        finally:\n"
                "            os.close(selector_fd)\n"
                "        if len(selector_bytes) != selector_pin['bytes'] or hashlib.sha256(selector_bytes).hexdigest() != selector_pin['sha256']:\n"
                "            parser.error('reviewed selector source pin')\n"
                "        selector = {'__file__': str(selector_path), '__name__': 'reviewed_result_selector'}\n"
                "        exec(compile(selector_bytes, str(selector_path), 'exec'), selector)\n"
                f"        return selector['dispatch'](args, parser, {transport_pin!r})\n")
    result = text.replace(anchor, inserted).encode()
    ast.parse(result)
    # Reversibility is a byte-for-byte proof of the untouched original path.
    if result.decode().replace(inserted, anchor).encode() != old: raise ValueError('non-RESULT preservation')
    return result
