#!/usr/bin/env python3
"""Finite Linux source regression runner; invoke with the project's venv Python -B."""
import os
import resource
import signal
import sys

sys.dont_write_bytecode = True
os.umask(0o077)
for kind, limit in ((resource.RLIMIT_AS, 512 * 1024**2),
                    (resource.RLIMIT_CPU, 60),
                    (resource.RLIMIT_FSIZE, 64 * 1024**2),
                    (resource.RLIMIT_CORE, 0)):
    resource.setrlimit(kind, (limit, limit))
os.sched_setaffinity(0, {0, 1})
signal.alarm(75)

# Bounds are installed before pathlib, pytest, SDKs or native source imports.
from pathlib import Path
import atexit
import json
import tempfile
import time

HERE = Path(__file__).resolve().parent
NATIVE = Path(os.environ['FRIDAY_NATIVE_SOURCE']).resolve(strict=True)
PROJECT = Path(os.environ['FRIDAY_PROJECT_SOURCE']).resolve(strict=True)
if not (NATIVE / 'tools/browser_scoped.py').is_file():
    raise SystemExit('FRIDAY_NATIVE_SOURCE must identify the native source tree')
if not (PROJECT / 'tests/test_user_onboarding.py').is_file():
    raise SystemExit('FRIDAY_PROJECT_SOURCE must identify the project source tree')

work_parent = Path(os.environ.get('FRIDAY_TEST_WORKDIR', str(HERE))).resolve()
work = tempfile.TemporaryDirectory(prefix='native55-fixtures-', dir=work_parent)
WORK = Path(work.name)
HOME = WORK / 'home'
TMP = WORK / 'tmp'
HOME.mkdir(mode=0o700)
TMP.mkdir(mode=0o700)
os.environ.update(HOME=str(HOME), TMPDIR=str(TMP), HERMES_HOME=str(HOME),
                  FRIDAY_TEST_HOME=str(HOME), FRIDAY_TEST_TMP=str(TMP),
                  HERMES_DISABLE_TELEMETRY='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
                  PYTHONDONTWRITEBYTECODE='1')
os.chdir(WORK)
# Source trees are explicit; installed dependency wheels may be provided separately.
paths = [HERE, PROJECT / 'tests', PROJECT, NATIVE]
if os.environ.get('SDK_SITE'):
    paths.append(Path(os.environ['SDK_SITE']).resolve(strict=True))
sys.path[:0] = [str(path) for path in paths]

suppressed_cleanup = []
register = atexit.register
def guarded_register(function, *args, **kwargs):
    if getattr(function, '__module__', '') == 'tools.browser_tool_lifecycle':
        suppressed_cleanup.append(getattr(function, '__name__', 'unknown'))
        return function
    return register(function, *args, **kwargs)
atexit.register = guarded_register

blocked = []
def audit(event, args):
    forbidden = {'socket.connect', 'socket.bind', 'socket.getaddrinfo',
                 'socket.__new__', 'subprocess.Popen', 'os.system', 'os.fork',
                 'os.forkpty', 'os.posix_spawn', 'os.kill', 'os.killpg'}
    if event in forbidden:
        blocked.append(event)
        raise RuntimeError('source_test_forbidden_effect:' + event)
    if event in {'open', 'os.listdir', 'os.scandir'} and args:
        raw = args[0]
        if isinstance(raw, (str, bytes, os.PathLike)):
            value = os.fsdecode(raw)
            if value == '/proc' or value.startswith('/proc/'):
                blocked.append('proc_probe')
                raise PermissionError('source_test_forbidden_proc_probe')
    if event in {'glob.glob', 'pathlib.Path.glob', 'pathlib.Path.rglob'}:
        if any('agent-browser' in str(arg) for arg in args):
            blocked.append('global_browser_scan')
            raise RuntimeError('source_test_forbidden_global_browser_scan')
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        mode, flags = args[1], args[2]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
        if writing:
            target = Path(os.fsdecode(args[0])).absolute()
            if target != Path('/dev/null') and not target.is_relative_to(WORK):
                blocked.append('external_write')
                raise RuntimeError('source_test_write_outside_fixture')
sys.addaudithook(audit)

import tools
tools.__path__.append(str(PROJECT / 'tools'))
import pytest

# A selective portable readiness slice; original full qualification stays separate.
DEFAULT = [
    'test_browser_native_ipc.py::test_limits_installed_before_imports',
    'test_browser_native_ipc.py::test_success_has_one_frame_one_connect',
    'test_browser_native_ipc.py::test_transient_or_cancel_never_replays_and_poison_is_sticky',
    'test_browser_native_ipc.py::test_original_deadline_after_dispatch_poisoned',
    'test_browser_scoped_lifecycle.py::test_installed_host_before_first_user_never_enters_shared_cleanup',
    'test_browser_scoped_lifecycle.py::test_unconfirmed_owned_cleanup_never_falls_back_to_shared_sweep',
    'test_browser_scoped.py::test_actions_share_original_owner_without_clock_refresh',
    'test_browser_scoped.py::test_foreign_task_never_launches',
    'test_browser_scoped.py::test_opaque_local_credentials_never_reach_child',
    'test_browser_scoped.py::test_unknown_command_effect_stops_exact_owner_and_never_retries',
    'test_browser_configure.py::test_prepare_existing_disabled_preserves_payload_identity_generation',
    'test_browser_configure.py::test_stale_foreign_and_arbitrary_inputs_refuse_before_payload_write',
    'test_assembled_custody.py::test_authenticated_two_principals_seven_actions_and_original_clocks',
    'test_assembled_custody.py::test_actual_native_registry_discovery_direct_and_routed_handlers',
    'test_native55_owned_publication.py',
    'test_gateway_browser_grants.py',
]
selection = sys.argv[1:] or DEFAULT
for item in selection:
    filename = item.split('::', 1)[0]
    if '/' in filename or '\\' in filename or not filename.startswith('test_') or not (HERE / filename).is_file():
        raise SystemExit('Select only this directory\'s test files or node IDs')
started = time.monotonic()
arguments = ['-c', '/dev/null', '-p', 'no:cacheprovider', '--basetemp', str(TMP / 'pytest'),
             '-q', '--tb=short', *[str(HERE / item) for item in selection]]
exit_code = int(pytest.main(arguments))
provenance = {}
for name in ('hermes_cli.friday_user_scope', 'hermes_cli.friday_ordinary_gateway', 'tools.browser_scoped', 'tools.browser_tool',
             'toolsets', 'friday_admin_controls.onboarding', 'scripts.friday_ordinary_install'):
    module = sys.modules.get(name)
    if module is not None:
        filename = Path(module.__file__).resolve()
        if filename.is_relative_to(NATIVE):
            provenance[name] = 'native/' + str(filename.relative_to(NATIVE))
        elif filename.is_relative_to(PROJECT):
            provenance[name] = 'project/' + str(filename.relative_to(PROJECT))
        else:
            raise RuntimeError('source_test_import_provenance_refused:' + name)
print(json.dumps({'exit_code': exit_code, 'elapsed_seconds': round(time.monotonic()-started, 3),
                  'source_imports': provenance, 'suppressed_legacy_cleanup': suppressed_cleanup,
                  'blocked_effects': {event: blocked.count(event) for event in set(blocked)},
                  'scope': 'selective source regression; no browser, worker or live acceptance'}, sort_keys=True))
work.cleanup()
raise SystemExit(exit_code)
