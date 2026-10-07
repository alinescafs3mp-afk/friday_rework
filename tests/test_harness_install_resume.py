"""Explicit continuation controls; synthetic filesystem, no build or network."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import friday_install as entry, install_containment as custody, dsh_prepare
from test_native_installer import install_input


def pinned(path):
    return {'path': str(path), 'sha256': entry.digest(path.read_bytes())}


def put(path, value):
    entry.publish(path, value)
    return pinned(path)


@pytest.fixture
def attempt(install_input, tmp_path):
    value = copy.deepcopy(install_input)
    old = copy.deepcopy(value)
    for name in ('scripts/friday_install.py', 'scripts/dsh_prepare.py'):
        old['project_files'][name] = '0' * 64
    original = put(tmp_path / 'original-input.json', old)
    current = put(tmp_path / 'current-input.json', value)
    home = Path(value['home']); home.mkdir(mode=0o700)
    claim = entry.partial_claim(original['sha256'], custody.Budget(1800))
    failure = {'schema': 'friday.native-install-failure.v1', 'original_attempt': claim,
               'resume_allowed': False, 'diagnostic': {
                   'phase': 'harness_build', 'reason': 'command_nonzero_exit', 'returncode': 1,
                   'timeout': False, 'reaped': True, 'namespace_init_exit_verified': True,
                   'cessation': 'REAPED'}}
    request = {'original_input': original, 'current_input': current,
               'original_claim': put(home / entry.MARKER, claim),
               'original_failure': put(home / entry.FAILURE, failure)}
    path = tmp_path / 'resume.json'; put(path, request)
    return request, path, value, home, claim, failure


def rewrite(attempt, name, value):
    request, path, *_ = attempt
    p = Path(request[name]['path']); p.write_text(json.dumps(value)); p.chmod(0o600)
    request[name] = pinned(p); path.write_text(json.dumps(request))


def snapshot(home):
    return {str(p.relative_to(home)): p.read_bytes() for p in home.rglob('*') if p.is_file()}


def test_valid_intake_inherits_exact_original_clock_without_effects(attempt):
    request, _, value, home, claim, _ = attempt; before = snapshot(home)
    checked, _, retained, budget = entry.resume_inputs(request)
    assert checked == value and retained == claim and budget.deadline == claim['deadline_mono']
    assert snapshot(home) == before and not (home / entry.RESUME).exists()


@pytest.mark.parametrize('field,value', [
    ('phase', 'compose'), ('phase', 'harness_smoke'), ('reason', 'command_timeout'),
    ('reason', 'stop_unconfirmed'), ('returncode', 0), ('returncode', True),
    ('timeout', True), ('timeout', 0), ('reaped', False), ('reaped', 1),
    ('namespace_init_exit_verified', False), ('namespace_init_exit_verified', 1),
    ('cessation', 'UNCONFIRMED')])
def test_uncertain_or_different_failure_refuses_before_consumption(attempt, field, value):
    request, _, _, home, _, failure = attempt
    failure['diagnostic'][field] = value; rewrite(attempt, 'original_failure', failure)
    before = snapshot(home)
    with pytest.raises(ValueError, match='settled_harness_build_failure_required'):
        entry.resume_inputs(request)
    assert snapshot(home) == before


@pytest.mark.parametrize('change', ['expired', 'boot', 'claim_hash', 'failure_claim', 'failure_allowed'])
def test_original_clock_boot_and_failure_binding_cannot_be_reset(attempt, change):
    request, _, _, home, claim, failure = attempt
    if change == 'expired': claim['deadline_mono'] = 1
    elif change == 'boot': claim['boot_id'] = 'another-boot'
    elif change == 'claim_hash': claim['input_sha256'] = 'f' * 64
    elif change == 'failure_claim': failure['original_attempt'] = dict(claim, deadline_mono=claim['deadline_mono'] + 30)
    else: failure['resume_allowed'] = True
    if change in ('expired', 'boot', 'claim_hash'):
        rewrite(attempt, 'original_claim', claim)
    else: rewrite(attempt, 'original_failure', failure)
    before = snapshot(home)
    with pytest.raises(ValueError): entry.resume_inputs(request)
    assert snapshot(home) == before and not (home / entry.RESUME).exists()


@pytest.mark.parametrize('change', ['home', 'seconds', 'product', 'bootstrap', 'lock', 'other_source', 'inventory'])
def test_rebind_only_two_reviewed_helpers_preserves_operational_settings(attempt, change):
    request, _, value, home, *_ = attempt
    if change == 'home': value['home'] += '-new'
    elif change == 'seconds': value['seconds'] += 30
    elif change == 'product': value['product']['web']['extract_timeout'] = 999
    elif change == 'bootstrap': value['bootstrap_python']['sha256'] = 'f' * 64
    elif change == 'lock': value['sources_lock']['sha256'] = 'f' * 64
    elif change == 'other_source': value['project_files']['scripts/install_containment.py'] = 'f' * 64
    else: value['project_files']['unexpected'] = 'f' * 64
    rewrite(attempt, 'current_input', value); before = snapshot(home)
    with pytest.raises(ValueError): entry.resume_inputs(request)
    assert snapshot(home) == before


@pytest.mark.parametrize('kind', ['hash', 'symlink', 'public', 'hardlink'])
def test_protected_exact_resume_inputs(attempt, kind, tmp_path):
    request, _, _, home, *_ = attempt; p = Path(request['current_input']['path'])
    if kind == 'hash': p.write_text(p.read_text() + ' ')
    elif kind == 'public': p.chmod(0o644)
    elif kind == 'hardlink': os.link(p, tmp_path / 'second-name')
    else:
        alias = tmp_path / 'alias'; alias.symlink_to(p); request['current_input']['path'] = str(alias)
    before = snapshot(home)
    with pytest.raises((ValueError, OSError)): entry.resume_inputs(request)
    assert snapshot(home) == before


def prepare_synthetic_completion(attempt, monkeypatch):
    request, path, value, home, claim, failure = attempt
    source = home / 'hermes-agent'; source.mkdir()
    entry.publish(home / 'hermes-agent.source.json', {'synthetic': True})
    for name in ('config.yaml', 'SOUL.md', 'FRIDAY-PROFILE.json'):
        (home / name).write_text('preserved ' + name); (home / name).chmod(0o600)
    prep = home / 'preparation/harness'; prep.mkdir(parents=True)
    old = {'source': {'commit': 'synthetic'}, 'donor': value['dsh_donor'],
           'toolchain': {'node': 'v22.23.2', 'node_sha256': 'a' * 64, 'observed_pnpm': '11.7.0'}}
    entry.publish(prep / 'dsh-toolchain.json', old)
    (prep / 'dsh-install.stderr').write_text('original failed log')
    monkeypatch.setattr(entry, 'composition_checked', lambda *a: None)
    monkeypatch.setattr(entry, 'stage_keyless_provider', lambda *a: None)
    calls = []
    def run(self, command, cwd, **kw):
        assert self.budget.deadline == claim['deadline_mono']
        calls.append(command)
        if 'pm.environments' in ' '.join(command): return value['bootstrap_python']['path'], {}
        if len(command) > 3 and command[3] == 'check':
            current = copy.deepcopy(old); del current['toolchain']['observed_pnpm']
            entry.publish(home / 'preparation/harness-resume/dsh-check.json', current)
        return '', {}
    monkeypatch.setattr(custody.Containment, 'run', run)
    return calls


def test_explicit_resume_runs_only_remaining_normal_path_once_and_retains_raw_evidence(attempt, monkeypatch):
    request, path, _, home, claim, _ = attempt
    calls = prepare_synthetic_completion(attempt, monkeypatch)
    original_claim = (home / entry.MARKER).read_bytes()
    original_failure = (home / entry.FAILURE).read_bytes()
    result = entry.resume_harness(request, path)
    assert result['original_attempt'] == claim and result['input_sha256'] == request['current_input']['sha256']
    assert result['state'] == 'INSTALLED_TEMPLATE_INCOMPLETE' and result['runtime_ready'] is False
    assert (home / (entry.MARKER + '.original')).read_bytes() == original_claim
    assert (home / entry.FAILURE).read_bytes() == original_failure
    assert (home / 'preparation/harness/dsh-install.stderr').read_text() == 'original failed log'
    phases = [c[3] for c in calls if len(c) > 3 and c[2].endswith('dsh_prepare.py')]
    assert phases == ['check', 'build', 'smoke']
    assert len(calls) == 6 and calls[-1][3] == 'prepare'


def test_completed_preflight_is_read_only_with_private_native_logs(attempt, monkeypatch):
    request, path, _, home, *_ = attempt
    prepare_synthetic_completion(attempt, monkeypatch)
    original = custody.Containment.run
    options = []
    def observed(self, command, cwd, **kw):
        options.append(kw)
        return original(self, command, cwd, **kw)
    monkeypatch.setattr(custody.Containment, 'run', observed)
    entry.resume_harness(request, path)
    for phase, call in zip(('pm_python', 'completed_native_check'), options[:2]):
        assert call['read_only'] is True
        assert call['log'] == home / 'preparation/harness-resume' / phase
    assert all('read_only' not in call and 'log' not in call for call in options[2:])
    assert '--deadline' not in calls[0]  # original budget is carried by containment
    assert str(claim['deadline_mono']) in calls[1]
    before = snapshot(home)
    with pytest.raises(ValueError): entry.resume_harness(request, path)
    assert len(calls) == 6 and snapshot(home) == before


def test_failed_preflight_is_consumed_with_separate_failure_without_replay(attempt, monkeypatch):
    request, path, _, home, claim, _ = attempt
    prepare_synthetic_completion(attempt, monkeypatch)
    old_failure = (home / entry.FAILURE).read_bytes()
    def failed(*a, **k): raise entry.Refused('completed_profile_changed')
    monkeypatch.setattr(custody.Containment, 'run', failed)
    with pytest.raises(ValueError): entry.resume_harness(request, path)
    assert (home / entry.FAILURE).read_bytes() == old_failure
    assert (home / entry.MARKER).read_bytes() == (home / (entry.MARKER + '.original')).read_bytes()
    assert entry.read_json(home / 'FRIDAY-INSTALL.harness-resume.failure.json')['original_attempt'] == claim
    with pytest.raises(ValueError, match='already_consumed'): entry.resume_harness(request, path)


def test_existing_consumption_refuses_without_commands(attempt):
    request, _, _, home, *_ = attempt
    entry.publish(home / entry.RESUME, {'state': 'CONSUMED_NOT_COMPLETE'}); before = snapshot(home)
    with pytest.raises(ValueError, match='already_consumed'): entry.resume_inputs(request)
    assert snapshot(home) == before


def test_fixed_node_flag_replaces_ambient_injection_without_model_keys(tmp_path, monkeypatch):
    monkeypatch.setenv('NODE_OPTIONS', '--require /private/owner.js')
    monkeypatch.setenv('OPENAI_API_KEY', 'PRIVATE_KEY_CANARY')
    env = dsh_prepare.clean_environment(tmp_path)
    assert env['NODE_OPTIONS'] == '--disable-wasm-trap-handler'
    assert 'PRIVATE_' not in json.dumps(env) and '/private/' not in json.dumps(env)
    assert env['GIT_OPTIONAL_LOCKS'] == '0' and env['npm_config_child_concurrency'] == '4'


@pytest.mark.parametrize('change', ['valid', 'config', 'contract', 'soul', 'plugin', 'tls', 'public_key'])
def test_completed_profile_plugin_and_tls_are_revalidated_before_skipping(tmp_path, change):
    import hermes_yaml as yaml
    from tools.configure_product import compose_product
    from test_product_profile import inputs
    value = {'product': inputs(), 'project_files': {}, 'dashboard_tls': {}}
    bundle = compose_product(value['product'])
    # Synthetic TLS bytes, never a real credential.
    key = tmp_path / 'test-only.key'; key.write_text('FIXTURE_KEY'); key.chmod(0o600)
    value['product']['dashboard']['tls'] = {'keyfile': key.name}
    value['dashboard_tls'] = {'keyfile': pinned(key)}
    entry.publish(tmp_path / 'FRIDAY-PROFILE.json', bundle['contract'])
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(bundle['config'])); (tmp_path / 'config.yaml').chmod(0o600)
    (tmp_path / 'SOUL.md').write_text(bundle['soul']); (tmp_path / 'SOUL.md').chmod(0o600)
    plugin = tmp_path / 'plugins/friday_rework/__init__.py'; plugin.parent.mkdir(parents=True)
    plugin.write_text('# exact synthetic installed plugin\n')
    value['project_files']['plugins/friday_rework/__init__.py'] = entry.digest(plugin.read_bytes())
    if change == 'config': (tmp_path / 'config.yaml').write_text('fallback_providers: [cloud]\n')
    elif change == 'contract': (tmp_path / 'FRIDAY-PROFILE.json').write_text('{}')
    elif change == 'soul': (tmp_path / 'SOUL.md').write_text('changed')
    elif change == 'plugin': plugin.write_text('changed')
    elif change == 'tls': key.write_text('changed')
    elif change == 'public_key': key.chmod(0o644)
    before = snapshot(tmp_path)
    if change == 'valid': entry.completed_profile_checked(value, tmp_path, bundle, custody.Budget(30))
    else:
        with pytest.raises(ValueError): entry.completed_profile_checked(value, tmp_path, bundle, custody.Budget(30))
    assert snapshot(tmp_path) == before


def test_changed_harness_preflight_does_not_admit_build(attempt, monkeypatch):
    request, path, _, home, *_ = attempt
    calls = prepare_synthetic_completion(attempt, monkeypatch)
    original = custody.Containment.run
    def changed(self, command, cwd, **kw):
        result = original(self, command, cwd, **kw)
        if len(command) > 3 and command[3] == 'check':
            p = home / 'preparation/harness-resume/dsh-check.json'
            v = entry.read_json(p); v['toolchain']['node_sha256'] = 'b' * 64
            p.write_text(json.dumps(v))
        return result
    monkeypatch.setattr(custody.Containment, 'run', changed)
    with pytest.raises(ValueError, match='completed_harness_identity_changed'):
        entry.resume_harness(request, path)
    assert len(calls) == 3 and (home / entry.RESUME).exists()
    assert (home / entry.MARKER).read_bytes() == (home / (entry.MARKER + '.original')).read_bytes()


def test_changed_original_input_blocks_next_step_and_retains_consumption(attempt, monkeypatch):
    request, path, _, home, *_ = attempt
    calls = prepare_synthetic_completion(attempt, monkeypatch)
    original = custody.Containment.run
    def changed(self, command, cwd, **kw):
        result = original(self, command, cwd, **kw)
        Path(request['original_input']['path']).write_text('{}')
        return result
    monkeypatch.setattr(custody.Containment, 'run', changed)
    with pytest.raises(ValueError, match='input_pin_changed'): entry.resume_harness(request, path)
    assert len(calls) == 1 and (home / entry.RESUME).exists()


def test_uncertain_continuation_retains_typed_stop_and_separate_evidence(attempt, monkeypatch):
    request, path, _, home, _, _ = attempt
    prepare_synthetic_completion(attempt, monkeypatch)
    original = (home / entry.FAILURE).read_bytes()
    def uncertain(*a, **kw): raise dsh_prepare.StopUnconfirmed('private error not printed')
    monkeypatch.setattr(custody.Containment, 'run', uncertain)
    with pytest.raises(dsh_prepare.StopUnconfirmed) as stopped: entry.resume_harness(request, path)
    assert stopped.value.friday_diagnostic['reason'] == 'stop_unconfirmed'
    assert stopped.value.friday_diagnostic['cessation'] == 'UNCONFIRMED'
    assert (home / entry.FAILURE).read_bytes() == original and (home / entry.RESUME).exists()
    assert entry.read_json(home / 'FRIDAY-INSTALL.harness-resume.failure.json')['diagnostic']['cessation'] == 'UNCONFIRMED'
    with pytest.raises(ValueError, match='already_consumed'): entry.resume_harness(request, path)


@pytest.mark.parametrize('name', ['original_input', 'current_input', 'original_claim', 'original_failure'])
def test_malformed_document_has_controlled_refusal(attempt, name):
    rewrite(attempt, name, [])
    with pytest.raises(ValueError, match='invalid_resume_input_shape'): entry.resume_inputs(attempt[0])


@pytest.mark.parametrize('change', ['expired', 'uncertain', 'changed_settings'])
def test_real_cold_cli_refuses_before_any_install_effect(attempt, change, tmp_path):
    request, path, value, home, claim, failure = attempt
    if change == 'expired': claim['deadline_mono'] = 1; rewrite(attempt, 'original_claim', claim)
    elif change == 'uncertain':
        failure['diagnostic']['namespace_init_exit_verified'] = False; rewrite(attempt, 'original_failure', failure)
    else: value['seconds'] += 30; rewrite(attempt, 'current_input', value)
    before = snapshot(home); evidence = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE'])
    result = subprocess.run([sys.executable, '-B', str(evidence / 'cli_guard.py'),
        str(entry.ROOT / 'scripts/friday_install.py'), 'resume-harness', '--input', str(path)],
        cwd=tmp_path, env={'PATH': os.defpath, 'HOME': str(tmp_path), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=8)
    assert result.returncode == 2 and 'Friday entry refused:' in result.stderr and not result.stdout
    assert snapshot(home) == before and 'Traceback' not in result.stderr
