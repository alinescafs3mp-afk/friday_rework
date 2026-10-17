#!/usr/bin/env python3
"""Run synthetic manual-compression controls against an explicit composed source.

Use a Python environment with the native dependencies and pytest installed:
  python -B tests/run_manual_ordinary_compress.py --repository . \
    --source /path/to/composed-source --baseline-source /path/to/before-source \
    --workdir /path/to/new-fixture-directory

The source must include ordinary-manual-compression.patch. All seven patched files
are checked against both sides of its manifest before and after testing; the existing composition receipt/gate remains
responsible for the rest of the source. No installed entrypoint, model, bot or
service runs. Local synthetic SQLite is allowed only below the new workdir.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--baseline-source', type=Path, required=True, help='Separate before-image checkout for before_sha256 validation')
    parser.add_argument('--manifest', type=Path,
                        help='Defaults to repository ordinary-manual-compression-manifest.json')
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    source = args.source.resolve(strict=True)
    tests = Path(__file__).resolve().parent
    manifest = args.manifest or repository / 'patches/hermes/ordinary-manual-compression-manifest.json'
    value = json.loads(manifest.read_text())
    baseline = args.baseline_source.resolve(strict=True)
    if source == baseline or source.samefile(baseline):
        parser.error('source and baseline-source must be separate directories')
    rows = value['files']
    required = {
        'gateway/platforms/base.py', 'gateway/run_agent_cache.py',
        'gateway/run_busy.py', 'gateway/run_shutdown.py',
        'gateway/slash_commands.py', 'gateway/slash_commands_session.py',
        'hermes_cli/friday_user_scope.py',
    }
    if len(rows) != 7 or {row['path'] for row in rows} != required:
        parser.error('manual-compression manifest must contain exactly the seven final file rows')
    for row in rows:
        for field in ('before_sha256', 'sha256'):
            digest = row.get(field, '')
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                parser.error('manifest requires canonical before/after SHA256 values')
        if row.get('new_file'):
            parser.error('manual-compression manifest must describe seven existing files')

    def verify_source_bytes():
        for row in rows:
            relative = Path(row['path'])
            if relative.is_absolute() or '..' in relative.parts or str(relative) != row['path']:
                parser.error('manifest file path must be canonical and relative')
            after = (source / relative).resolve(strict=True)
            before = (baseline / relative).resolve(strict=True)
            if not after.is_relative_to(source) or not before.is_relative_to(baseline):
                parser.error('manifest files must remain inside their source directories')
            data = after.read_bytes()
            if hashlib.sha256(data).hexdigest() != row['sha256'] or ('bytes' in row and len(data) != row['bytes']):
                parser.error('composed source does not match manual-compression manifest: ' + row['path'])
            if hashlib.sha256(before.read_bytes()).hexdigest() != row['before_sha256']:
                parser.error('before-image does not match manual-compression manifest: ' + row['path'])

    verify_source_bytes()
    work = args.workdir.resolve()
    if any(work == tree or tree.is_relative_to(work) or work.is_relative_to(tree) for tree in (source, baseline)):
        parser.error('source, baseline-source and workdir must be separate directories')
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in ('home', 'tmp', 'cache', 'config', 'data'):
        (work / name).mkdir(mode=0o700)
    for key in list(os.environ):
        if any(part in key for part in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'CREDENTIAL')) or key.startswith('HERMES_'):
            del os.environ[key]
    os.environ.update(HOME=str(work / 'home'), HERMES_HOME=str(work / 'home'),
                      TMPDIR=str(work / 'tmp'), XDG_CACHE_HOME=str(work / 'cache'),
                      XDG_CONFIG_HOME=str(work / 'config'), XDG_DATA_HOME=str(work / 'data'),
                      PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    os.chdir(work)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(tests), str(source), str(repository / 'tests')]

    def confined(path):
        return isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).resolve().is_relative_to(work)

    def audit(event, items):
        if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.sendmsg', 'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
            raise AssertionError('offline fixture forbids network and subprocess execution: ' + event)
        if event == 'sqlite3.connect' and str(items[0]) != ':memory:':
            path = items[0]
            if str(path).startswith('file:'):
                parsed = urlsplit(str(path))
                if parsed.netloc:
                    raise AssertionError('SQLite URI authorities are forbidden')
                path = unquote(parsed.path)
            if not confined(path):
                raise AssertionError('SQLite is restricted to the synthetic workdir')
        if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.chown', 'os.truncate', 'os.utime'}:
            if not isinstance(items[0], int) and not confined(items[0]):
                raise AssertionError('filesystem changes are restricted to the synthetic workdir')
        if event in {'os.rename', 'os.link'} and not all(confined(path) for path in items[:2]):
            raise AssertionError('filesystem changes are restricted to the synthetic workdir')
        if event == 'os.symlink' and not confined(items[1]):
            raise AssertionError('symlinks are restricted to the synthetic workdir')
        if event == 'open':
            path, mode, flags = items
            writes = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writes and not isinstance(path, int) and os.fsdecode(path) != os.devnull and not confined(path):
                raise AssertionError('writes are restricted to the synthetic workdir')

    sys.addaudithook(audit)
    import pytest
    try:
        return pytest.main(['-c', os.devnull, '--confcutdir', str(tests),
                            '--basetemp', str(work / 'pytest'), '-p', 'no:cacheprovider', '-q',
                            str(tests / 'test_manual_ordinary_compress.py'),
                            str(tests / 'test_manual_compression_owned_cancel.py'),
                            str(tests / 'test_manual_compression_submit_failure.py'),
                            str(tests / 'test_manual_compression_final_boundaries.py'),
                            str(tests / 'test_compression_watermark_commit.py'),
                            str(tests / 'test_compression_lease_refresh_before_publish.py'),
                            str(tests / 'test_ordinary_first_contact_copy.py')])
    finally:
        verify_source_bytes()



if __name__ == '__main__':
    raise SystemExit(main())
