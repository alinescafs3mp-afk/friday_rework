"""Offline source harness: actual qualify, Budget and exclusive receipt writer.

Imports are isolated fixtures; no native workers, profile config, DB or /proc.
As in existing source checks, only selected pure/file helpers are loaded by AST.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/friday_rework'
CANDIDATE = Path(__file__).resolve().parents[1] / 'plugins/friday_rework/user_worker_join.py'
SECRET = 'private_secret_canary'


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    alias = '_qualification_receipt_fixture'
    package = ModuleType(alias); package.__path__ = [str(PLUGIN)]
    monkeypatch.setitem(sys.modules, alias, package)
    def stub(name, **values):
        m = ModuleType(name); m.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, m)
        return m
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, m); spec.loader.exec_module(m)
        return m
    process = load(alias+'.runtime_process', PLUGIN/'runtime_process.py')
    primitives = load(alias+'.runtime_primitives', PLUGIN/'runtime_primitives.py')
    load(alias+'.runtime_containment', PLUGIN/'runtime_containment.py')
    class HostUnavailable(RuntimeError): pass
    stub(alias+'.host_runtime', HostUnavailable=HostUnavailable, _pin=None,
         configured_runtimes=None, validate_runtime=None)
    stub(alias+'.host_record', digest=None)
    configs = {'dsh': {'budget_seconds': 215}, 'a0': {'budget_seconds': 215,
        'a0': {'deployment': {}, 'policy': {}}}}
    stub(alias+'.worker_provision', own_runtime=None, pin=None,
        preparation=lambda home, profile, kind, ref: (None, configs[kind]),
        prepare_inputs=lambda *a, **kw: None)
    onboarding = stub(alias+'.onboarding', os=os)
    for file, names in [('associations.py', {'_sync_directory'}), ('onboarding.py', {'_new_file'})]:
        tree = ast.parse((PLUGIN/file).read_text())
        selected = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
        exec(compile(selected, str(PLUGIN/file), 'exec'), onboarding.__dict__)
    observers = stub(alias+'.runtime_observers', dsh_safety_observe=None,
        dsh_observe=lambda *a: pytest.fail('later DSH observer reached'),
        a0_observe=lambda *a: pytest.fail('A0 observer reached'))
    stub(alias+'.a0_bootstrap', InitialProbe=lambda *a, **kw: pytest.fail('initial probe reached'),
        own_probe=None, checked_custody=None)
    stub(alias+'.adapters', __path__=[])
    stub(alias+'.adapters.a0_profile', endpoint_urls=lambda *a: [])
    scope = stub('hermes_cli.friday_user_scope', _private=lambda *a: None, ONBOARDING='synthetic-onboarding.json')
    stub('hermes_cli', friday_user_scope=scope, __path__=[])
    stub('hermes_cli.config', require_readable_config_before_write=lambda *a: {})
    join = load(alias+'.user_worker_join', CANDIDATE)
    def path(value):
        if value == '/proc/sys/kernel/random/boot_id': return SimpleNamespace(read_text=lambda: 'fixture-boot')
        return Path(value)
    monkeypatch.setattr(join, 'Path', path)
    home = tmp_path/'home'; home.mkdir(mode=0o700)
    (home/'workers').mkdir(mode=0o700)
    return SimpleNamespace(join=join, process=process, primitives=primitives, observers=observers,
        writer=onboarding, home=home, original=time.monotonic()-5, calls=[])


def fail(s, exc):
    def safety(*args):
        s.calls.append('safety'); raise exc
    s.observers.dsh_safety_observe=safety
    def run():
        return s.join.qualify(s.home, {'runtime_profile':'fixture','tools':[]}, 1,
            {'dsh':{},'a0':{}}, verify=lambda: None, accepted_monotonic=s.original)
    s.run=run
    with pytest.raises(type(exc)) as caught: run()
    assert caught.value is exc
    p=s.home/s.join.FOLDER/'failure.json'
    return p, json.loads(p.read_text()) if p.exists() else None


def command(s, **changes):
    obs=dict(returncode=7, elapsed_seconds=1.25, timeout=False, stdout_sha256='a'*64,
        stderr_sha256='b'*64, stdout_bytes=17, stderr_bytes=31, pid=123, starttime_ticks=456,
        reaped=True, namespace_init_exit_verified=True, reason=SECRET, argv=[SECRET],
        env={'TOKEN':SECRET}, stdout=SECRET, stderr=SECRET)
    obs.update(changes)
    return s.process.CommandFailed(obs)


@pytest.mark.parametrize('timeout,returncode', [(False, 7), (True, -9)])
def test_retained_command_metadata_and_original_clock_without_replay(fixture, timeout, returncode):
    s=fixture;p,value=fail(s,command(s,timeout=timeout,returncode=returncode))
    assert value['error_kind']=='command_failed' and value['state']=='REFUSED_OR_UNCERTAIN'
    obs=value['command_observation']
    assert obs==dict(returncode=returncode,elapsed_seconds=1.25,timeout=timeout,stdout_sha256='a'*64,
        stderr_sha256='b'*64,stdout_bytes=17,stderr_bytes=31,pid=123,starttime_ticks=456,
        reaped=True,namespace_init_exit_verified=True)
    assert SECRET not in p.read_text() and value['retry_authorized'] is False
    assert value['original_attempt']==dict(boot_id='fixture-boot',started_mono=s.original,
        deadline_mono=s.original+215,budget_seconds=215)
    retained=p.read_bytes()
    with pytest.raises(s.join.HostUnavailable,match='qualification_attempt_requires_inspection'):s.run()
    assert s.calls==['safety'] and p.read_bytes()==retained
    assert p.stat().st_mode & 0o777 == 0o600
    assert not (s.home/s.join.PROOF).exists()


@pytest.mark.parametrize('kind,expected', [('refused','source_refused'),('other','internal_error'),('stop','stop_unconfirmed')])
def test_fixed_error_kinds_never_serialize_reason_message_or_class(fixture,kind,expected):
    s=fixture
    class SensitiveSecret(RuntimeError):pass
    exc={'refused':s.primitives.Refused(SECRET),'other':SensitiveSecret(SECRET),
        'stop':s.process.StopUnconfirmed(SECRET)}[kind]
    p,value=fail(s,exc)
    assert value['error_kind']==expected
    assert value['state']==('STOP_UNCONFIRMED' if kind=='stop' else 'REFUSED_OR_UNCERTAIN')
    assert 'command_observation' not in value and 'reason' not in value
    assert SECRET not in p.read_text() and 'SensitiveSecret' not in p.read_text()


def test_untrusted_safe_field_names_still_require_typed_bounded_values(fixture):
    s=fixture
    exc=command(s,returncode=SECRET,elapsed_seconds=float('nan'),stdout_sha256=SECRET,
        stderr_sha256='G'*64,stdout_bytes=-1,stderr_bytes=True,pid=2**31,
        starttime_ticks=2**63,reaped=SECRET,namespace_init_exit_verified=1)
    exc.observation['timeout']=SECRET
    p,value=fail(s,exc)
    assert value['command_observation']=={} and SECRET not in p.read_text()


def test_receipt_io_failure_preserves_primary_exception(fixture):
    s=fixture
    def denied(*a):raise OSError(SECRET)
    s.writer._new_file=denied
    p,value=fail(s,command(s))
    assert value is None and not p.exists() and s.calls==['safety']


def test_missing_command_observation_preserves_primary_exception_and_receipt(fixture):
    s=fixture;exc=command(s);del exc.observation
    p,value=fail(s,exc)
    assert value['error_kind']=='command_failed' and value['command_observation']=={}
    assert value['state']=='REFUSED_OR_UNCERTAIN' and SECRET not in p.read_text()


@pytest.mark.parametrize('stop', [False, True])
def test_diagnostic_failure_preserves_primary_exception_and_stop_state(fixture,stop):
    s=fixture
    def broken(exc):raise TypeError(SECRET)
    s.join._failure_diagnostic=broken
    exc=s.process.StopUnconfirmed(SECRET) if stop else command(s)
    p,value=fail(s,exc)
    assert value['error_kind']=='diagnostic_unavailable'
    assert value['state']==('STOP_UNCONFIRMED' if stop else 'REFUSED_OR_UNCERTAIN')
    assert value['retry_authorized'] is False and SECRET not in p.read_text()


def test_existing_exclusive_failure_receipt_cannot_be_overwritten(fixture):
    s=fixture;original=s.writer._new_file
    def racing(path,data):
        original(path,b'original failure evidence\n')
        original(path,data)
    s.writer._new_file=racing
    def safety(*a):s.calls.append('safety');raise s.process.StopUnconfirmed(SECRET)
    s.observers.dsh_safety_observe=safety
    with pytest.raises(s.process.StopUnconfirmed):
        s.join.qualify(s.home,{'runtime_profile':'fixture','tools':[]},1,{'dsh':{},'a0':{}},
            verify=lambda:None,accepted_monotonic=s.original)
    assert (s.home/s.join.FOLDER/'failure.json').read_bytes()==b'original failure evidence\n'
