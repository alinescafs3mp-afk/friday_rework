"""Pure Source builder: original canonical parser/body preserved for non-RESULT.
No imports of the candidate, native execution, or global writes.
"""
import ast
import hashlib
import json
import os

OLD_SHA = '20604f9f31c5be9cdc77f8ae88be3348f60b0ed3141d2ae1e47ffe0febd6058f'


def build(old, selector_pin, transport_pin, supervisor_source):
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
    supervisor_sha = hashlib.sha256(supervisor_source).hexdigest()
    ast.parse(supervisor_source)
    # Supervisor is embedded accepted Source, no path/import I/O before fork.
    # Every selector/transport/grant import and validation is in the ONE worker.
    loading = """        def run_result(custody):
            import stat
            selector_path = Path(selector_pin['path'])
            selector_stat = selector_path.lstat()
            if not stat.S_ISREG(selector_stat.st_mode) or selector_stat.st_uid != os.getuid() or selector_stat.st_nlink != 1 or selector_stat.st_mode & 0o077 or selector_stat.st_size > 65536 or any(p.is_symlink() for p in selector_path.parents):
                parser.error('reviewed selector ownership')
            selector_fd = os.open(selector_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                selector_open = os.fstat(selector_fd)
                if (selector_stat.st_dev, selector_stat.st_ino, selector_stat.st_ctime_ns, selector_stat.st_mtime_ns) != (selector_open.st_dev, selector_open.st_ino, selector_open.st_ctime_ns, selector_open.st_mtime_ns):
                    parser.error('reviewed selector race')
                selector_bytes = os.read(selector_fd, 65537)
            finally:
                os.close(selector_fd)
            if len(selector_bytes) != selector_pin['bytes'] or hashlib.sha256(selector_bytes).hexdigest() != selector_pin['sha256']:
                parser.error('reviewed selector source pin')
            selector = {'__file__': str(selector_path), '__name__': 'reviewed_result_selector'}
            exec(compile(selector_bytes, str(selector_path), 'exec'), selector)
            return selector['dispatch_in_worker'](args, parser, transport_pin, custody)
"""
    inserted = ("    parser.add_argument('--rpc-grant', type=Path)\n"
                "    parser.add_argument('--rpc-grant-sha')\n"
                "    parser.add_argument('--rpc-custody-dir', type=Path)\n" + anchor +
                "    if args.kind == 'RESULT':\n"
                "        if not args.rpc_grant or not args.rpc_grant_sha or not args.rpc_custody_dir:\n"
                "            parser.error('RESULT requires exact reviewed grant and owned custody; no CLI fallback')\n"
                f"        selector_pin = {selector_pin!r}\n"
                f"        transport_pin = {transport_pin!r}\n"
                + loading +
                "        result = _result_whole_wall['supervise'](run_result, args.rpc_custody_dir)\n"
                "        print(json.dumps(result, sort_keys=True))\n"
                "        return result\n")
    bootstrap = ("_result_whole_wall = {'__name__': 'reviewed_whole_wall'}\n" +
                 f"exec(compile({supervisor_source!r}, 'embedded-whole-wall-{supervisor_sha}', 'exec'), _result_whole_wall)\n")
    main_anchor = 'def main():\n'
    if text.count(main_anchor) != 1: raise ValueError('main bootstrap boundary')
    result = text.replace(anchor, inserted).replace(main_anchor, bootstrap+main_anchor).encode()
    ast.parse(result)
    compile(result, '<uninstalled-canonical-candidate>', 'exec')
    if result.splitlines()[0] != old.splitlines()[0]: raise ValueError('CLI shebang preservation')
    # Reversibility is a byte-for-byte proof of the untouched original path.
    if result.decode().replace(bootstrap, '', 1).replace(inserted, anchor).encode() != old: raise ValueError('non-RESULT preservation')
    return result
