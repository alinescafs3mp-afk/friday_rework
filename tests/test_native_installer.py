"""Offline native contracts and fail-before-effect controls, no installation."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from scripts import friday_install as entry
from scripts import friday_native as native
from test_product_profile import inputs


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pinned(p):
    return {'path': str(p), 'sha256': sha(p)}


@pytest.fixture
def install_input(tmp_path):
    tmp_path.chmod(0o700)
    script = tmp_path / 'reviewed-hermes-prepare.py'; script.write_text('# synthetic command input, not executed\n')
    python = tmp_path / 'bootstrap-python'; python.write_text('synthetic pinned executable'); python.chmod(0o700)
    root = entry.ROOT
    paths = [p for area in ('scripts', 'tools', 'plugins/friday_rework', 'config', 'patches/hermes')
             for p in (root / area).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    value = {'home': str(tmp_path / 'friday'), 'bootstrap_python': pinned(python),
        'hermes_donor': str(tmp_path / 'hermes-input'), 'hermes_prepare': pinned(script),
        'sources_lock': pinned(root / 'sources.lock.json'), 'dsh_donor': str(tmp_path / 'friday/harness'),
        'a0_donor': str(tmp_path / 'a0-input'), 'product': inputs(),
        'containment': pinned(Path('/usr/bin/bwrap')),
        'project_files': {str(p.relative_to(root)): sha(p) for p in paths}, 'seconds': 1800}
    return value


def test_native_complete_install_commands_parse_in_real_donor(install_input):
    commands = entry.commands(install_input)
    assert commands['tools'][3:] == ['pm.cli', 'install', '--tools-only']
    assert commands['dependencies'][3:] == ['pm.cli', 'install', '--extra', 'all', '--extra',
                                            'telegram', '--extra', 'web', '--extra', 'exa']
    assert [a[2:4] for a in commands['harness']] == [[str(entry.ROOT / 'scripts/dsh_prepare.py'), phase]
                                                  for phase in ('source', 'toolchain', 'build', 'smoke')]
    from hermes_cli.subcommands.gateway import build_gateway_parser
    from hermes_cli.subcommands.dashboard import build_dashboard_parser
    parser = argparse.ArgumentParser(); subs = parser.add_subparsers(); noop = lambda *a: None
    build_gateway_parser(subs, cmd_gateway=noop, cmd_proxy=noop, cmd_gateway_enroll=noop)
    build_dashboard_parser(subs, cmd_dashboard=noop, cmd_dashboard_register=noop)
    parsed = parser.parse_args(commands['gateway_install'][3:])
    assert parsed.start_now is False and parsed.start_on_login is False
    assert parser.parse_args(commands['gateway_start'][3:]).gateway_command == 'start'
    dash = parser.parse_args(commands['dashboard'][3:]); assert dash.host == '127.0.0.1' and dash.port == 9119
    assert dash.no_open and not dash.insecure and not dash.isolated and not dash.skip_build
    assert all(x not in json.dumps(commands) for x in ('--force', '--replace', '--all', 'install.sh', 'hermes update'))


@pytest.mark.parametrize('field', ['home', 'bootstrap_python', 'hermes_prepare', 'sources_lock',
                                  'dsh_donor', 'a0_donor', 'product', 'project_files', 'seconds', 'containment'])
def test_missing_mandatory_install_input_refuses_before_effect(install_input, field):
    value = copy.deepcopy(install_input); del value[field]
    with pytest.raises((ValueError, KeyError)): entry.commands(value)
    assert not Path(install_input['home']).exists()


@pytest.mark.parametrize('field,value', [('seconds', True), ('seconds', 0), ('seconds', 7201),
                                       ('home', '/'), ('home', '/tmp/../Friday'),
                                       ('dsh_donor', '/tmp/foreign-existing-harness')])
def test_ambiguous_foreign_or_unbounded_input_refuses(install_input, field, value):
    install_input[field] = value
    with pytest.raises(ValueError): entry.commands(install_input)


@pytest.mark.parametrize('name', ['scripts/friday_install.py', 'scripts/friday_native.py',
                                'tools/configure_product.py', 'plugins/friday_rework/plugin.yaml'])
def test_incomplete_project_or_changed_source_pin_refuses(install_input, name):
    install_input['project_files'][name] = '0' * 64
    with pytest.raises(ValueError, match='project_source_changed'): entry.commands(install_input)
    del install_input['project_files'][name]
    with pytest.raises(ValueError, match='complete_installer_plugin_inventory'): entry.commands(install_input)


def test_pinned_composer_unavailable_refuses(install_input):
    Path(install_input['hermes_prepare']['path']).unlink()
    with pytest.raises(OSError): entry.commands(install_input)


def test_existing_foreign_home_not_adopted_even_if_empty(install_input, tmp_path):
    home = Path(install_input['home']); home.mkdir(mode=0o700)
    input_path = tmp_path / 'input.json'; input_path.write_text(json.dumps(install_input)); input_path.chmod(0o600)
    with pytest.raises(OSError): entry.install(install_input, input_path)
    assert list(home.iterdir()) == []


def test_partial_install_never_replayed_or_cleaned(install_input, tmp_path, monkeypatch):
    home = Path(install_input['home']); input_path = tmp_path / 'input.json'
    input_path.write_text(json.dumps(install_input)); input_path.chmod(0o600)
    from scripts import dsh_prepare
    calls = []
    def failed(*a, **kw):
        calls.append((a, kw))
        if len(calls) == 1: return 'FRIDAY_PID_NAMESPACE_OK', {}
        raise RuntimeError('synthetic finite preparer failure')
    monkeypatch.setattr(dsh_prepare, 'run', failed)
    with pytest.raises(RuntimeError): entry.install(install_input, input_path)
    assert entry.read_json(home / entry.MARKER)['state'] == 'PARTIAL'
    (home / 'retained-work.txt').write_text('preserve')
    with pytest.raises(ValueError, match='partial_install_requires_reconciliation'):
        entry.install(install_input, input_path)
    assert len(calls) == 2 and (home / 'retained-work.txt').read_text() == 'preserve'


def test_install_process_environment_has_no_ambient_keys_or_routing(tmp_path, monkeypatch):
    for k in ('OPENAI_API_KEY', 'EXA_API_KEY', 'TELEGRAM_BOT_TOKEN', 'HERMES_RUNTIME_DIR',
              'HERMES_GATEWAY_LOCK_DIR', 'HERMES_PROFILE', 'PYTHONPATH',
              'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', 'HERMES_DASHBOARD_PUBLIC_URL'):
        monkeypatch.setenv(k, 'OWNER_SECRET_CANARY')
    os_home = os.environ['HOME']; env = entry.clean_environment(tmp_path)
    assert env['HOME'] == os_home and env['HERMES_HOME'] == str(tmp_path)
    assert 'OWNER_SECRET_CANARY' not in json.dumps(env)


@pytest.mark.parametrize('kind', ['public', 'hardlink', 'symlink'])
def test_private_input_provenance(kind, tmp_path):
    p = tmp_path / 'input'; p.write_text('{}'); p.chmod(0o600)
    if kind == 'public': p.chmod(0o644)
    elif kind == 'hardlink': os.link(p, tmp_path / 'alias')
    else:
        alias = tmp_path / 'alias'; alias.symlink_to(p); p = alias
    with pytest.raises((ValueError, OSError)): entry.read_json(p)


def test_duplicate_fields_and_inline_yaml_are_not_adopted(tmp_path):
    p = tmp_path / 'input'; p.write_text('{"home":1,"home":2}'); p.chmod(0o600)
    with pytest.raises(ValueError): entry.read_json(p)
    p.write_text('home: /tmp/unsafe')
    with pytest.raises(ValueError): entry.read_json(p)


def test_source_receipt_checks_actual_complete_pinned_native(tmp_path):
    # Existing frozen full native fixture, bytes verified by the outer guard.
    e = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']); source = (e / 'native').resolve()
    files = {str(p.relative_to(source)): {'sha256': sha(p), 'bytes': p.stat().st_size,
                                        'mode': '100755' if p.stat().st_mode & 0o111 else '100644'}
             for p in source.rglob('*') if p.is_file()}
    donor = json.loads((entry.ROOT / 'sources.lock.json').read_text())['repositories'][0]
    receipt = {'schema': 'friday.hermes-source.v1', 'status': 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED',
               'commit': donor['commit'], 'base_tree': donor['tree'], 'files': files}
    assert len(entry.source_checked(source, receipt, donor)) > 17000
    receipt['files']['hermes_constants.py']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='composed_source_changed'): entry.source_checked(source, receipt, donor)


@pytest.mark.parametrize('change', ['status', 'commit', 'tree', 'short', 'traversal'])
def test_untrusted_status_and_source_identity_refuse(change, tmp_path):
    receipt = {'schema': 'friday.hermes-source.v1', 'status': 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED',
               'commit': 'a' * 40, 'base_tree': 'b' * 40, 'files': {}}
    if change == 'status': receipt['status'] = 'READY'
    elif change == 'commit': receipt['commit'] = 'c' * 40
    elif change == 'tree': receipt['base_tree'] = 'c' * 40
    elif change == 'traversal': receipt['files'] = {'../escape': {}} | {str(n): {} for n in range(1001)}
    with pytest.raises(ValueError): entry.source_checked(tmp_path, receipt, {'commit': 'a' * 40, 'tree': 'b' * 40})


def native_home(home):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    class Selected:
        def __enter__(self): self.token = set_hermes_home_override(str(home))
        def __exit__(self, *a): reset_hermes_home_override(self.token)
    return Selected()


def test_real_native_config_writer_and_readonly_consumer(tmp_path):
    home = tmp_path / 'owned-home'; home.mkdir(mode=0o700)
    from hermes_cli.config import load_config
    with native_home(home):
        bundle = native.profile_write(home, inputs())
        assert native.native_profile_check(bundle, home)['ready'] is False
        actual = load_config()
    assert actual['model'] == bundle['config']['model']
    assert actual['memory'] == bundle['config']['memory']
    assert actual['dashboard']['public_url'] == inputs()['dashboard']['public_url']
    assert (home / 'SOUL.md').read_text() == (entry.ROOT / 'config/SOUL.md').read_text()
    assert entry.read_json(home / 'FRIDAY-PROFILE.json')['state'] == 'TEMPLATE_INCOMPLETE'
    assert not (home / '.env').exists() and not (home / 'auth.json').exists()
    before = (home / 'config.yaml').read_bytes()
    with native_home(home), pytest.raises(ValueError, match='existing_profile_config_not_replaced'):
        native.profile_write(home, inputs())
    assert (home / 'config.yaml').read_bytes() == before


@pytest.mark.parametrize('mutation', ['authoff', 'provider', 'operator', 'cloudfallback', 'webdisabled'])
def test_actual_native_auth_web_and_local_fallback_negative(mutation, tmp_path):
    from tools.configure_product import compose_product
    bundle = compose_product(inputs()); c = bundle['config']; d = bundle['contract']['native_dashboard']
    if mutation == 'authoff': d['public_url'] = 'http://127.0.0.1:9119'
    elif mutation == 'provider': c['plugins']['enabled'].remove('dashboard_auth/basic')
    elif mutation == 'operator': c['dashboard']['basic_auth']['username'] = 'foreign-user'
    elif mutation == 'cloudfallback': c['fallback_providers'] = [{'provider': 'openai'}]
    else: c['web']['keyless_rescue'] = True
    with native_home(tmp_path), pytest.raises(ValueError): native.native_profile_check(bundle, tmp_path)


@pytest.mark.parametrize('field,value', [('home', '/tmp/foreign-home'), ('profiles', ('foreign',)),
    ('start_time', None), ('protocol_version', 0), ('host', '0.0.0.0'), ('port', 1)])
def test_actual_native_host_record_foreign_home_and_authority_refused(field, value, tmp_path):
    from gateway.host_rendezvous import HostRecord
    data = dict(role='serve', pid=12345, create_time=1.0, host='127.0.0.1', port=9119,
                protocol_version=1, token_fingerprint='synthetic', profiles=('default',),
                updated_at='synthetic', home=str(tmp_path), start_time=123)
    data[field] = value
    with pytest.raises(ValueError): native.host_owner(HostRecord(**data), tmp_path, 'default',
                                                     dashboard=inputs()['dashboard'])


def test_matching_record_is_policy_only_not_readiness(tmp_path):
    from gateway.host_rendezvous import HostRecord
    record = HostRecord(role='serve', pid=12345, create_time=1.0, host='127.0.0.1', port=9119,
        protocol_version=1, token_fingerprint='synthetic', profiles=('default',),
        updated_at='synthetic', home=str(tmp_path), start_time=123)
    from tools.configure_product import compose_product
    with native_home(tmp_path):
        out = native.native_profile_check(compose_product(inputs()), tmp_path, records=(record,))
    assert out == {'state': 'TEMPLATE_INCOMPLETE', 'ready': False, 'credentials_checked': False}


def test_renderer_status_cannot_be_promoted_to_launch_grant(install_input, monkeypatch):
    calls = []
    monkeypatch.setattr(entry, 'inspect', lambda *a: {'state': 'READY', 'ready': True})
    from scripts import dsh_prepare
    monkeypatch.setattr(dsh_prepare, 'run', lambda *a, **kw: calls.append(a))
    with pytest.raises(ValueError, match='mandatory_a0_web_kernel_and_final_native_dashboard_owner_not_admitted'):
        entry.start(install_input, 'synthetic')
    assert not calls


def test_a0_fixed_runtime_not_retried_and_portable_gap_explicit(install_input):
    command = entry.commands(install_input)['a0_inventory']
    assert command[2].endswith('/a0_prepare.py') and command[3] == 'prepare'
    assert '--reviewed-plan-sha256' not in command and not any('a0_runtime.py' in x for x in command)
    assert any('separately admitted' in gap for gap in entry.gaps())


def test_parser_does_not_echo_secret_inputs(tmp_path, monkeypatch, capsys):
    p = tmp_path / 'bad-input'; p.write_text('{"password":"PRIVATE_SECRET_CANARY"}'); p.chmod(0o600)
    monkeypatch.setattr('sys.argv', ['friday', 'plan', '--input', str(p)])
    with pytest.raises(SystemExit) as error: entry.main()
    assert error.value.code == 2
    assert 'PRIVATE_SECRET_CANARY' not in capsys.readouterr().err


@pytest.mark.parametrize('path,value', [('inference.base_url', 'https://api.openai.com/v1'),
    ('inference.model', 'auto'), ('inference.context', True), ('inference.main_output', 32768),
    ('web.profile', 'exa-keyless'), ('web.extract_timeout', None),
    ('dashboard.host', 'SECRET_CANARY_HOST'), ('dashboard.port', True),
    ('dashboard.public_url', 'https://user:SECRET_CANARY@friday.example:9119'),
    ('dashboard.public_url', 'http://friday.example:9119'),
    ('dashboard.public_url', 'https://friday.example:9119/path')])
def test_nonlocal_or_secret_authority_refuses_plan_before_effect(install_input, path, value):
    node = install_input['product']; pieces = path.split('.')
    for name in pieces[:-1]: node = node[name]
    node[pieces[-1]] = value
    with pytest.raises((ValueError, TypeError)): entry.commands(install_input)
    assert not Path(install_input['home']).exists()


def test_install_input_bytes_bind_the_executed_plan(install_input, tmp_path):
    p = tmp_path / 'input.json'; other = copy.deepcopy(install_input); other['seconds'] = 1200
    p.write_text(json.dumps(other)); p.chmod(0o600)
    with pytest.raises(ValueError, match='install_input_changed'): entry.install(install_input, p)
    assert not Path(install_input['home']).exists()


def test_private_parent_and_foreign_home_symlink_refused(install_input, tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match='owned_private_directory'): entry.commands(install_input)
    tmp_path.chmod(0o700); target = tmp_path / 'foreign'; target.mkdir()
    Path(install_input['home']).symlink_to(target)
    with pytest.raises(ValueError, match='real_absolute_path'): entry.commands(install_input)
    assert not list(target.iterdir())


def test_actual_custom_persona_is_never_replaced(tmp_path):
    home = tmp_path / 'home'; home.mkdir(mode=0o700)
    soul = home / 'SOUL.md'; soul.write_text('owner-customized-persona'); soul.chmod(0o600)
    with native_home(home), pytest.raises(ValueError, match='existing_custom_persona_not_replaced'):
        native.profile_write(home, inputs())
    assert soul.read_text() == 'owner-customized-persona' and not (home / 'config.yaml').exists()


@pytest.mark.parametrize('change', ['lock', 'set', 'manifest', 'patch'])
def test_composition_is_bound_to_reviewed_lock_and_exact_overlays(install_input, change):
    files = install_input['project_files']
    rows = []
    for name, sha256 in files.items():
        if name.startswith('patches/hermes/') and name.endswith('.json'):
            body = json.loads((entry.ROOT / name).read_text())
            rows.append({'manifest': name, 'manifest_sha256': sha256, 'patch_sha256': body['patch_sha256']})
    receipt = {'sources_lock_sha256': install_input['sources_lock']['sha256'], 'layers': rows}
    if change == 'lock': receipt['sources_lock_sha256'] = '0' * 64
    elif change == 'set': rows.pop()
    elif change == 'manifest': rows[0]['manifest_sha256'] = '0' * 64
    else: rows[0]['patch_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='composition_'):
        entry.composition_checked(install_input, Path(install_input['home']), receipt, {})


def test_whole_finite_composition_and_completed_idempotence_with_native_config(install_input, tmp_path, monkeypatch):
    """Commands are intercepted; native config/files are real. No PM acceptance."""
    p = tmp_path / 'input.json'; p.write_text(json.dumps(install_input)); p.chmod(0o600)
    home = Path(install_input['home']); calls = []
    from scripts import dsh_prepare
    e = Path(os.environ['FRIDAY_FIXTURE_EVIDENCE']); source = home / 'hermes-agent'
    def intercepted(argv, cwd, **kw):
        assert argv[:4] == ['/usr/bin/bwrap', '--unshare-pid', '--die-with-parent', '--new-session']
        argv = argv[argv.index('--') + 1:]
        if '-c' in argv and 'FRIDAY_PID_NAMESPACE_OK' in argv[-1]:
            return 'FRIDAY_PID_NAMESPACE_OK', {}
        calls.append({'argv': argv, 'cwd': str(cwd), 'timeout': kw['timeout'], 'env': kw['env']})
        if '--destination' in argv:
            shutil.copytree(e / 'native', source, copy_function=shutil.copy2)
            files = {str(f.relative_to(source)): {'sha256': sha(f), 'bytes': f.stat().st_size,
                'mode': '100755' if f.stat().st_mode & 0o111 else '100644'}
                for f in source.rglob('*') if f.is_file()}
            donor = json.loads((entry.ROOT / 'sources.lock.json').read_text())['repositories'][0]
            rows = []
            for name, h in install_input['project_files'].items():
                if name.startswith('patches/hermes/') and name.endswith('.json'):
                    b = json.loads((entry.ROOT / name).read_text())
                    rows.append({'manifest': name, 'manifest_sha256': h, 'patch_sha256': b['patch_sha256']})
            entry.publish(home / 'hermes-agent.source.json', {'schema': 'friday.hermes-source.v1',
                'status': 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED', 'commit': donor['commit'],
                'base_tree': donor['tree'], 'files': files, 'layers': rows,
                'sources_lock_sha256': install_input['sources_lock']['sha256']})
        elif '-c' in argv:
            return str(Path(os.sys.executable)), {'synthetic': True}
        elif str(entry.ROOT / 'scripts/friday_native.py') in argv:
            with native_home(home): native.profile_write(home, install_input['product'])
            target = home / 'plugins/friday_rework'; target.parent.mkdir(mode=0o700)
            shutil.copytree(entry.ROOT / 'plugins/friday_rework', target)
            for f in target.rglob('*'):
                f.chmod(0o700 if f.is_dir() else 0o600)
        return '', {'synthetic': True}
    monkeypatch.setattr(dsh_prepare, 'run', intercepted)
    result = entry.install(install_input, p)
    assert result['state'] == 'INSTALLED_TEMPLATE_INCOMPLETE' and result['runtime_ready'] is False
    assert result['gateway_installed'] is False
    assert len(calls) == 10  # composer, tools, dependencies, selected-Python, completion, Harness4, A0
    before = list(calls)
    inspected = entry.install(install_input, p)
    assert calls == before and inspected['ready'] is False
    assert all(0 < r['timeout'] <= 1800 for r in calls)
    assert all(r['env']['HERMES_HOME'] == str(home) for r in calls)
    assert not any('gateway' in r['argv'] or 'dashboard' in r['argv'] for r in calls)
    with pytest.raises(ValueError, match='mandatory_a0_web_kernel'):
        entry.start(install_input, entry.digest(entry.owned_file(p)))
    assert calls == before
    (home / 'config.yaml').write_text('foreign-edit: retained\n')
    with pytest.raises(ValueError, match='installed_profile_changed'):
        entry.inspect(install_input, entry.digest(entry.owned_file(p)))
    assert (home / 'config.yaml').read_text() == 'foreign-edit: retained\n'


def test_actual_native_stamp_reports_overlay_as_dirty_external(monkeypatch):
    from scripts import write_install_stamp
    monkeypatch.setattr(write_install_stamp, '_run_git', lambda *a, **kw: None)
    receipt = {'commit': 'a' * 40, 'base_tree': 'b' * 40,
               'layers': [{'manifest': 'synthetic', 'manifest_sha256': 'c' * 64, 'patch_sha256': 'd' * 64}]}
    stamp = native.install_stamp(receipt)
    assert stamp['commit'] == receipt['commit'] and stamp['dirty'] is True
    assert stamp['updateMechanism'] == 'external' and stamp['distribution'] == 'friday-rework'
    assert stamp['displayVersion'] == 'git.aaaaaaa.dirty'
    assert stamp['baseVersion'] is None and stamp['commitDate'] is None
    assert stamp['fridaySource']['layers'] == receipt['layers']
