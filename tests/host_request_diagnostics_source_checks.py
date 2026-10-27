"""Protected refusal metadata and unchanged public refusal semantics.

Execute exact host helper/handle AST with isolated context and local files.
No native worker or model is started.
"""
from __future__ import annotations
import ast
from contextvars import ContextVar
import copy
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import time
import types

HERE = Path(__file__).parent
CANDIDATE = HERE.parent/'plugins/friday_rework/host.py'
INSTALLED = CANDIDATE
tree = ast.parse(CANDIDATE.read_text())

class HostUnavailable(RuntimeError):
    pass
class AssociationError(RuntimeError):
    pass
class ScopeDenied(PermissionError):
    pass

package = types.ModuleType('offline_host'); package.__path__ = []
admission = types.ModuleType('offline_host.admission')
admission.CALL_FIELDS = ('task_id', 'session_id', 'turn_id', 'api_request_id', 'tool_call_id')
admission._call = ContextVar('test_call', default=None)
sys.modules[package.__name__] = package
sys.modules[admission.__name__] = admission
hermes_cli = types.ModuleType('hermes_cli'); hermes_cli.__path__ = []
scope_module = types.ModuleType('hermes_cli.friday_user_scope')
scope_module.current = lambda: None
scope_module.ScopeDenied = ScopeDenied
scope_module.__file__ = str(HERE/'fake_user_scope.py')
sys.modules['hermes_cli'] = hermes_cli
sys.modules[scope_module.__name__] = scope_module

ns = {'__package__': package.__name__, '__file__': str(INSTALLED), 'Path': Path,
      'HostUnavailable': HostUnavailable, 'AssociationError': AssociationError,
      'json': json, 'time': time, 'copy': copy}
helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_record_request_failure')
host = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'WorkerHost')
handle = next(n for n in host.body if isinstance(n, ast.FunctionDef) and n.name == 'handle')
exec(compile(ast.Module(body=[helper, handle], type_ignores=[]), str(INSTALLED), 'exec'), ns)

results = []
with tempfile.TemporaryDirectory(dir=HERE) as raw:
    directory = Path(raw); directory.chmod(0o700)
    secret = 'SENTINEL_PRIVATE_ARG_7c1c605a'
    ids = ('session-private', 'session-private', 'turn-private', 'api-private', 'call-private')
    token = admission._call.set(ids)
    try:
        try:
            raise ValueError(secret)
        except ValueError as error:
            assert ns['_record_request_failure'](directory, 'native_match', error,
                    public_error='unproved_admission', task_id=ids[0], session_id=ids[1])
            assert not ns['_record_request_failure'](directory, 'native_match', error,
                    public_error='unproved_admission', task_id=ids[0], session_id=ids[1])
        files = list(directory.glob('*.json')); assert len(files) == 1
        data = files[0].read_bytes(); record = json.loads(data)
        assert record['native_scope_valid'] and record['native_task_session_matches']
        assert secret.encode() not in data and all(i.encode() not in data for i in ids)
        assert record['exception_type'] == 'value_error'
        assert record['admission_outcome'] == 'REFUSED'
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600 and files[0].stat().st_nlink == 1
        assert not list(directory.glob('.worker-*'))
        results.append('protected metadata, no raw IDs/text, first-write preservation, mode600, cleanup')
    finally:
        admission._call.reset(token)
    # No native scope still produces a local-correlated failure, never discarded.
    assert ns['_record_request_failure'](directory, 'retained_input_source', KeyError(secret),
              public_error='worker_not_available', task_id='session', session_id='session')
    local = [json.loads(p.read_text()) for p in directory.glob('*.json') if json.loads(p.read_text())['phase']=='retained_input_source'][0]
    assert local['correlation_kind']=='local_only' and local['native_scope_present'] is False
    assert local['admission_outcome']=='PASSED' and local['exception_type']=='key_error'
    assert not ns['_record_request_failure'](directory, 'native_match', ValueError(secret), public_error='worker_not_available')
    results.append('no-scope row-none evidence retained; invalid phase/error pairing rejected')
    linked = directory/'linked'; linked.symlink_to(directory, target_is_directory=True)
    assert not ns['_record_request_failure'](linked, 'request', ValueError(secret), public_error='unproved_admission')
    unsafe = directory/'unsafe'; unsafe.mkdir(); unsafe.chmod(0o755)
    assert not ns['_record_request_failure'](unsafe, 'request', ValueError(secret), public_error='unproved_admission')
    results.append('symlink/nonprivate directories refused')

    # Only exact allowlisted source filenames and bounded frame lines survive.
    frame_ns = {}
    exec(compile("def diagnostic_origin():\n    raise RuntimeError('PRIVATE_EXCEPTION_TEXT')\n",
                 str(CANDIDATE), 'exec'), frame_ns)
    try:
        frame_ns['diagnostic_origin']()
    except RuntimeError as error:
        assert ns['_record_request_failure'](directory, 'scheduler', error,
                  public_error='worker_not_available')
    framed = [json.loads(p.read_text()) for p in directory.glob('*.json')
              if json.loads(p.read_text())['phase']=='scheduler'][0]
    assert framed['source_frames'] == [{'module':'host.py','line':2}]
    assert 'PRIVATE_EXCEPTION_TEXT' not in json.dumps(framed)
    assert str(CANDIDATE) not in json.dumps(framed)
    results.append('allowlisted source frame and bounded line; no path or exception text')

    calls = []
    def record(*args, **kwargs): calls.append((args[1], kwargs['public_error']))
    ns['_record_request_failure'] = record
    brief = types.SimpleNamespace(worker='dsh')
    ns['parse_request'] = lambda args: (brief, {'reference':'prior','paths':['a']})
    ns['bound_owner'] = lambda **kwargs: {'platform':'telegram'}
    scope_module.current = lambda: None
    correlation = {'task_id':'session','session_id':'session'}
    ns['association_address'] = lambda *args: 'address'
    ns['owner_from_ingress'] = lambda *args: {'platform':'telegram'}
    ns['delivery_route'] = lambda *args: {}
    ns['select_runtime'] = lambda *args: {'runtime_profile':'p'}
    def runtime_fail(*args): raise ValueError(secret)
    ns['check_runtime'] = runtime_fail
    store = types.SimpleNamespace(state=types.SimpleNamespace(data_dir=directory),snapshot=lambda:{})
    context = types.SimpleNamespace(get_config=lambda key:{'enabled':True},get_command_context=lambda:None,schedule_gateway_work=lambda:None)
    subject = types.SimpleNamespace(store=store,_state_directory=directory,_closed=False,ctx=context,
        admission=types.SimpleNamespace(match=lambda *args,**kwargs:({'platform':'telegram','runtime_profile':'p'},correlation)))
    result = json.loads(ns['handle'](subject, {'private':secret}, task_id='session',session_id='session'))
    assert result == {'accepted':False,'error':'worker_not_available'} and calls.pop()==('runtime_check','worker_not_available'), (result,calls)
    ns['check_runtime'] = lambda *args:{'runtime_profile':'p'}
    def retained_fail(*args): raise AssociationError(secret)
    subject._retained_input_source = retained_fail
    result = json.loads(ns['handle'](subject, {'private':secret}, task_id='session',session_id='session'))
    assert result == {'accepted':False,'error':'worker_not_available'} and calls.pop()==('retained_input_source','worker_not_available')
    def owner_fail(**kwargs): raise ValueError(secret)
    ns['bound_owner'] = owner_fail
    result = json.loads(ns['handle'](subject, {'private':secret},task_id='session',session_id='session'))
    assert result == {'accepted':False,'error':'unproved_admission'} and calls.pop()==('owner','unproved_admission')
    results.append('exact handle AST: original row-none refusal preserved at owner/runtime_check/retained_input_source')

report = {'test': 'offline exact-helper/handle AST with no product runtime imports', 'result':'PASS',
          'checks':results,'candidate_sha256':hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()}
print(json.dumps(report,indent=2))
