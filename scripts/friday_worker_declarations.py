"""Native stopped declaration transaction, or private non-authorizing staging.

This entry never invokes historical recovery/rebind commands. Staging does
not consume an attempt, change a deployment marker, or qualify a worker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from plugins.friday_rework.worker_declarations import (
    DeclarationError, NATIVE_GAPS, _absolute, _read_reference, _same,
    load_declaration_source, plan_declaration_delta, require,
    validate_declaration_source,
)


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
        indent=2, allow_nan=False) + '\n').encode()


def apply_declarations(request, *, request_path=None, request_sha256=None):
    """The native writer requires exact request custody and original clock."""
    from plugins.friday_rework.worker_declaration_writer import apply_declarations as apply_native
    return apply_native(request, request_path=request_path, request_sha256=request_sha256)


def stage(request, *, output):
    """Produce private proposed JSON configs after exact current-byte CAS.

    Native config parsing is reused, not reimplemented. Output is not an
    installation request and no apply path consumes these candidate files.
    """
    require(type(request) is dict and set(request) == {'schema', 'source',
        'root_configuration', 'profile_configuration'} and request['schema'] ==
        'friday.worker-declarations.stage.v1', 'worker_declaration_stage_request_required')
    bundle, inputs, identity = load_declaration_source(request['source'])
    require(_same(request['root_configuration'], bundle.get('root_before'))
        and _same(request['profile_configuration'], bundle.get('profile_before')),
        'worker_declaration_stage_raw_cas_changed')
    root_raw = _read_reference(request['root_configuration'], json_document=False)
    own_raw = _read_reference(request['profile_configuration'], json_document=False)
    # Reuse the actual native YAML parser on the authenticated bytes. Reopening
    # mutable config paths through a loader would introduce a second read race.
    # This neither writes config nor creates a native operator session.
    from hermes_cli.config import fast_safe_load
    root = fast_safe_load(root_raw.decode('utf-8-sig'))
    own = fast_safe_load(own_raw.decode('utf-8-sig'))
    profile_home = Path(identity['profile'])
    joined = validate_declaration_source(request['source'], root, own,
        root_home=profile_home.parent.parent, profile_home=profile_home)
    plan = plan_declaration_delta(root, own, inputs, identity, bundle)
    require(_read_reference(request['root_configuration'], json_document=False) == root_raw
        and _read_reference(request['profile_configuration'], json_document=False) == own_raw,
        'worker_declaration_stage_source_changed')
    target = _absolute(str(output))
    # A new direct child of an existing private owned directory only. Refuse
    # an installed home or one of its ancestors/descendants as output.
    home = profile_home.parent.parent
    require(target != home and home not in target.parents and target not in home.parents,
        'worker_declaration_stage_external_output_required')
    parent = target.parent
    info = parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700 and parent.resolve() == parent,
        'worker_declaration_private_stage_parent_required')
    files = {'root-config.proposed.json': _encoded(plan['root_config']),
        'profile-config.proposed.json': _encoded(plan['profile_config']),
        'declaration-source-join.json': _encoded(joined),
        'request.json': _encoded(request)}
    summary = {'schema': 'friday.worker-declaration-stage.v1',
        'state': 'STAGED_ONLY_NOT_NATIVE_AUTHORITY', 'ready': False,
        'native_migration': 'NOT_INVOKED', 'workers_enabled': False,
        'source': request['source'], 'missing_native_prerequisites': list(NATIVE_GAPS),
        'files': {name: {'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'mode': '0o600'} for name, data in files.items()}}
    files['stage.json'] = _encoded(summary)
    parent_fd = os.open(parent, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY)
    stage_fd = None
    try:
        require(os.fstat(parent_fd).st_ino == info.st_ino
            and os.fstat(parent_fd).st_dev == info.st_dev,
            'worker_declaration_stage_parent_changed')
        # Exclusive claim, independent of wall time. Never overwrite/replay.
        os.mkdir(target.name, 0o700, dir_fd=parent_fd)
        stage_fd = os.open(target.name, os.O_RDONLY | os.O_CLOEXEC
            | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=parent_fd)
        for name, data in files.items():
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=stage_fd)
            try:
                view = memoryview(data)
                while view:
                    count = os.write(fd, view)
                    require(count > 0, 'worker_declaration_stage_write_failed')
                    view = view[count:]
                os.fchmod(fd, 0o600)
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(stage_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        raise DeclarationError('worker_declaration_stage_consumed_no_overwrite') from None
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(parent_fd)
    return summary


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            raise DeclarationError('worker_declaration_cli_arguments_invalid')
    parser = SafeParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'apply'))
    parser.add_argument('--request', required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--output')
    try:
        args = parser.parse_args()
        request = _read_reference({'path': args.request, 'sha256': args.request_sha256})
        if args.action == 'apply':
            require(args.output is None, 'worker_declaration_apply_output_forbidden')
            result = apply_declarations(request, request_path=args.request,
                request_sha256=args.request_sha256)
        else:
            require(args.output is not None, 'worker_declaration_stage_output_required')
            result = stage(request, output=args.output)
        public = {key: result[key] for key in
            ('state', 'ready', 'native_migration', 'workers_enabled')}
        if 'files' in result:
            public['files'] = result['files']
        print(json.dumps(public, sort_keys=True))
        return 0
    except Exception as error:
        # Full private input/path details never become a public traceback.
        # A late failure can follow publication. Never imply that nothing
        # changed just because the CLI returned an error.
        native = sys.modules.get('scripts.dsh_prepare')
        uncertain_type = getattr(native, 'StopUnconfirmed', None)
        uncertain = uncertain_type is not None and isinstance(error, uncertain_type)
        print(json.dumps({'state': 'STOP_UNCONFIRMED' if uncertain else
                'FAILED_CLOSED_RECONCILE_EXACT_JOURNAL', 'ready': False,
            'error': error.code if isinstance(error, DeclarationError)
                else 'worker_declaration_stop_unconfirmed' if uncertain
                else 'worker_declaration_request_failed_closed',
            'native_migration': 'NO_ACCEPTANCE_CLAIM'}, sort_keys=True))
        return 3 if uncertain else 2


if __name__ == '__main__':
    raise SystemExit(main())
