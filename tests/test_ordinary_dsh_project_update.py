"""Finite synthetic project-only update; no SDK, service, process or runtime effects."""
import contextlib
import copy
import os
from pathlib import Path
import stat
import sys
from types import ModuleType

import pytest

from scripts import friday_install as f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget


def put(path, data, mode=0o600):
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in missing:
        directory.chmod(0o700)
    path.write_bytes(data)
    path.chmod(mode)
    return {'path': str(path), 'sha256': f.digest(data)}


def doc(path, value):
    return put(path, o.encoded(value))


def snapshot(home):
    return {str(p.relative_to(home)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
            for p in home.rglob('*') if p.is_file()}


@pytest.fixture
def installed(tmp_path, monkeypatch):
    home = tmp_path/'home'
    home.mkdir(mode=0o700)
    source = home/'hermes-agent'
    source.mkdir(mode=0o700)
    root = tmp_path/'project'
    root.mkdir(mode=0o700)
    monkeypatch.setattr(f, 'ROOT', root)
    monkeypatch.setenv('HERMES_HOME', str(home))
    (home/'preparation').mkdir(mode=0o700)
    after = {name: b'# synthetic reviewed project afterimage '+name.encode()+b'\n'
             for name in o.PROJECT_AFTER}
    monkeypatch.setattr(o, 'PROJECT_AFTER', {n: f.digest(v) for n, v in after.items()})
    before_dsh = b'# synthetic previous DSH adapter\n'
    monkeypatch.setattr(o, 'PROJECT_DSH_BEFORE', f.digest(before_dsh))
    names = (set(after)-{o.PROJECT_POLICY}) | {
        'scripts/friday_ordinary_install.py', 'scripts/friday_native.py',
        'scripts/friday_install.py', 'scripts/friday_start.py',
        'plugins/friday_rework/onboarding.py', 'plugins/friday_rework/unchanged.py',
        'plugins/friday_rework/host_runtime.py', 'plugins/friday_rework/user_worker_join.py',
        'scripts/worker_qualification.py',
        o.DOCX_CREATION_MANIFEST, 'patches/hermes/ordinary-docx-creation.patch'}
    oldproject = {n: put(root/n, before_dsh if n == o.PROJECT_DSH else
                        b'# previous '+n.encode()+b'\n')['sha256'] for n in names}
    for n in range(222-len(oldproject)):
        name = f'config/unchanged-{n}.txt'
        oldproject[name] = put(root/name, b'preserved\n')['sha256']
    previous = {'home': str(home), 'project_files': oldproject,
        'product': {'runtime': {'enabled': False}}, 'seconds': 1,
        'worker_install': {'dsh': {'web': {'egress_evidence': {'policy': 'preserved'}}}},
        'model': 'preserved', 'reasoning': 'preserved', 'original_budget': 'expired-never-reset'}
    prevref = doc(tmp_path/'previous.json', previous)
    files = {}
    for name in sorted(o.DOCX_CREATION_FILES | {'retained.txt'}):
        data = b'native source retained '+name.encode()+b'\n'
        put(source/name, data, 0o644)
        files[name] = {'sha256': f.digest(data), 'bytes': len(data), 'mode': '100644'}
    layers = [{'manifest': f'patches/hermes/prior-{n}.json',
               'manifest_sha256': f.digest(str(n).encode()),
               'patch_sha256': f.digest(('patch'+str(n)).encode())} for n in range(76)]
    layers.append({'manifest': o.DOCX_CREATION_MANIFEST,
                   'manifest_sha256': oldproject[o.DOCX_CREATION_MANIFEST],
                   'patch_sha256': oldproject['patches/hermes/ordinary-docx-creation.patch']})
    receipt = {'commit': 'a'*40, 'base_tree': 'b'*40, 'files': files, 'layers': layers}
    receiptref = doc(home/'hermes-agent.source.json', receipt)
    stampref = doc(source/'install-stamp.json', {'fridaySource': {'baseTree': 'b'*40,
        'layers': layers}, 'original_clock': {'expired': True, 'remaining': 0}})
    doc(home/o.TRANSACTION/'committed.json', {'state': 'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'})
    doc(home/'preparation/ordinary-gateway-archive/retained.json', {'state': 'archived-no-retry'})
    history = {str(p.relative_to(home)): f.digest(p.read_bytes()) for name in
        (o.TRANSACTION, 'preparation/ordinary-gateway-archive')
        for p in (home/name).rglob('*') if p.is_file()}
    prior = None
    generation = doc(tmp_path/'history-input-0.json', {'id': 0})
    for n in range(1, 32):
        nextgen = prevref if n == 31 else doc(tmp_path/f'history-input-{n}.json', {'id': n})
        oldrequest = {'schema': f'friday.ordinary-telegram-source-update.v{n}', 'home': str(home),
            'previous_input': generation, 'current_input': nextgen,
            'transaction_history': copy.deepcopy(history)}
        if prior:
            oldrequest['predecessor_update'] = prior
        prior = doc(tmp_path/f'history-request-{n}.json', oldrequest)
        tx = home/'preparation'/('ordinary-source-update-'+generation['sha256'])
        doc(tx/'intent.json', {'schema': 'friday.ordinary-telegram-source-update-transaction.v1',
            'state': 'SOURCE_UPDATE_CONSUMED_NO_RETRY', 'request_sha256': prior['sha256']})
        doc(tx/'committed.json', {'state': 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
            'previous_input': generation, 'current_input': nextgen,
            'source_receipt_sha256': receiptref['sha256'], 'gateway_started': False,
            'workers_enabled': False})
        put(tx/'before/preserved', b'consumed historical bytes\n')
        history.update({str(p.relative_to(home)): f.digest(p.read_bytes())
                        for p in tx.rglob('*') if p.is_file()})
        generation = nextgen
    configref = put(home/'config.yaml', b'runtime: false\nworkers: {}\n')
    profileref = doc(home/'FRIDAY-PROFILE.json', {'model': 'preserve', 'resources': 'preserve'})
    launchref = put(source/'.hermes/bin/hermes', b'preserved executable\n', 0o700)
    unitref = put(tmp_path/'native.service', b'never started\n')
    for name in oldproject:
        if name.startswith('plugins/'):
            put(home/name, (root/name).read_bytes())
    marker = {'schema': f.SCHEMA, 'state': 'INSTALLED_TEMPLATE_INCOMPLETE',
        'completion_stage': 'TELEGRAM_ORDINARY', 'home': str(home), 'source': str(source),
        'runtime_ready': False, 'worker_state': 'BOTH_WORKERS_PREPARATION_PENDING',
        'input_sha256': prevref['sha256'], 'source_receipt_sha256': receiptref['sha256'],
        'profile_files': {'config.yaml': configref['sha256'], 'FRIDAY-PROFILE.json': profileref['sha256']},
        'plugin_files': {n: sha for n, sha in oldproject.items() if n.startswith('plugins/')},
        'ordinary_gateway': {'operator_entry': {'input': prevref,
            'script': {'path': str(root/'scripts/friday_native.py'),
                       'sha256': oldproject['scripts/friday_native.py']}},
            'configuration_sha256': 'old-normalized', 'source_receipt_sha256': receiptref['sha256'],
            'credential_files': {'.env': None, 'auth.json': None}, 'baseline': {'preserved': True}},
        'original_attempt': {'clock': 'expired', 'accounting': [1, 2, 3]},
        'target_settings': {'preserved': True}}
    markerref = doc(home/f.MARKER, marker)
    put(home/'data/retained.db', b'never open this retained synthetic database\n')
    current = copy.deepcopy(previous)
    current['project_files'].update({n: put(root/n, data)['sha256'] for n, data in after.items()})
    curref = doc(tmp_path/'current.json', current)
    request = {'schema': o.PROJECT_UPDATE_SCHEMA, 'seconds': 180, 'home': str(home),
        'previous_input': prevref, 'current_input': curref, 'marker': markerref,
        'source_receipt': receiptref, 'stamp': stampref, 'configuration': configref,
        'profile': profileref, 'launcher': launchref, 'native_unit': unitref,
        'credential_files': {'.env': None, 'auth.json': None},
        'transaction_history': history, 'predecessor_update': prior}
    requestpath = tmp_path/'request.json'
    doc(requestpath, request)
    events = []
    def spec_checked(value, **kwargs):
        for name, sha in value['project_files'].items():
            assert f.digest(f.owned_file(root/name)) == sha
        events.append('spec')
        return home, {'hermes': {}}
    def composition(value, native, native_receipt, donor):
        assert native_receipt == receipt
        for name, row in native_receipt['files'].items():
            assert f.digest(f.owned_file(native/name)) == row['sha256']
        events.append('composition')
    monkeypatch.setattr(f, 'spec_checked', spec_checked)
    monkeypatch.setattr(f, 'composition_checked', composition)
    monkeypatch.setattr(f, 'native_packages', lambda *a, **kw: None)
    @contextlib.contextmanager
    def stopped(*args):
        events.append('stopped')
        yield lambda: events.append('stopped-proof')
    @contextlib.contextmanager
    def locked(*args):
        events.append('locked')
        yield lambda: events.append('lock-proof')
    monkeypatch.setattr(o, 'stopped_consumers', stopped)
    monkeypatch.setattr(o, 'retained_build_lock', locked)
    gateway = ModuleType('hermes_cli.friday_ordinary_gateway')
    def check(installed_home, role=False):
        assert role is False
        value = f.read_json(installed_home/f.MARKER)
        assert value['runtime_ready'] is False
        assert f.digest((installed_home/'config.yaml').read_bytes()) == configref['sha256']
        events.append('gateway')
    gateway.check = check
    monkeypatch.setitem(sys.modules, gateway.__name__, gateway)
    return locals()


def repin(s):
    s['request']['current_input'] = doc(Path(s['request']['current_input']['path']), s['current'])
    doc(s['requestpath'], s['request'])


def test_project_update_publishes_only_marker_and_dsh(installed):
    s = installed
    before = snapshot(s['home'])
    retained = [s['home']/'hermes-agent.source.json', s['source']/'install-stamp.json',
        s['source']/'retained.txt', s['home']/'config.yaml', s['home']/'FRIDAY-PROFILE.json',
        s['source']/'.hermes/bin/hermes', Path(s['unitref']['path'])]
    states = {p: o.update_file_state(p) for p in retained}
    result = o.update(s['request'], s['requestpath'], Budget(180))
    assert result['state'] == 'TELEGRAM_ORDINARY_PROJECT_UPDATED'
    assert result['source_receipt_sha256'] == s['receiptref']['sha256']
    assert all(o.update_file_state(p) == state for p, state in states.items())
    tx = s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert stat.S_IMODE((tx/'intent.json').stat().st_mode) == 0o400
    assert stat.S_IMODE((tx/'committed.json').stat().st_mode) == 0o400
    assert result['ready'] is result['gateway_started'] is result['workers_enabled'] is False
    after = snapshot(s['home'])
    changed = {n for n in before if before[n] != after[n]}
    assert changed == {f.MARKER, o.PROJECT_DSH}
    assert after[o.PROJECT_DSH][0] == s['after'][o.PROJECT_DSH]
    updated = f.read_json(s['home']/f.MARKER)
    assert updated['input_sha256'] == s['request']['current_input']['sha256']
    assert updated['ordinary_gateway']['operator_entry']['input'] == s['request']['current_input']
    assert updated['original_attempt'] == s['marker']['original_attempt']
    assert updated['target_settings'] == s['marker']['target_settings']
    assert updated['plugin_files'][o.PROJECT_DSH] == o.PROJECT_AFTER[o.PROJECT_DSH]
    assert {k: v for k, v in updated['plugin_files'].items() if k != o.PROJECT_DSH} == {
        k: v for k, v in s['marker']['plugin_files'].items() if k != o.PROJECT_DSH}
    assert 'stopped' in s['events'] and 'locked' in s['events'] and 'gateway' in s['events']
    assert len(f.read_json(s['home']/'hermes-agent.source.json')['layers']) == 77
    with pytest.raises(ValueError):
        o.update(s['request'], s['requestpath'], Budget(180))


@pytest.mark.parametrize('fault', ['offallowlist', 'settings', 'native_bytes', 'configuration',
    'foreign_plugin', 'wrong_after', 'wrong_before', 'missing_policy', 'unknown_field',
    'history_bytes', 'predecessor_receipt', 'native_receipt', 'stamp', 'credentials'])
def test_rejects_before_publication_preserve_all_installed_files(installed, fault):
    s = installed
    r = s['request']
    if fault == 'offallowlist':
        name = 'plugins/friday_rework/unchanged.py'
        s['current']['project_files'][name] = put(s['root']/name, b'foreign project delta\n')['sha256']
    elif fault == 'settings':
        s['current']['model'] = 'changed'
    elif fault == 'native_bytes':
        put(s['source']/'retained.txt', b'foreign native\n', 0o644)
    elif fault == 'configuration':
        put(s['home']/'config.yaml', b'runtime: true\n')
    elif fault == 'foreign_plugin':
        put(s['home']/o.PROJECT_DSH, b'foreign installed adapter\n')
    elif fault == 'wrong_after':
        s['current']['project_files'][o.PROJECT_DSH] = put(s['root']/o.PROJECT_DSH, b'unreviewed\n')['sha256']
    elif fault == 'wrong_before':
        value = copy.deepcopy(s['previous'])
        value['project_files'][o.PROJECT_DSH] = '0'*64
        r['previous_input'] = doc(Path(r['previous_input']['path']), value)
    elif fault == 'missing_policy':
        s['current']['project_files'].pop(o.PROJECT_POLICY)
    elif fault == 'unknown_field':
        r['enable_workers'] = True
    elif fault == 'history_bytes':
        put(s['home']/next(n for n in r['transaction_history'] if n.endswith('/before/preserved')), b'foreign history\n')
    elif fault == 'predecessor_receipt':
        prior = f.read_json(Path(r['predecessor_update']['path']))
        tx = s['home']/'preparation'/('ordinary-source-update-'+prior['previous_input']['sha256'])
        value = f.read_json(tx/'committed.json')
        value['source_receipt_sha256'] = '0'*64
        doc(tx/'committed.json', value)
        r['transaction_history'][str((tx/'committed.json').relative_to(s['home']))] = f.digest((tx/'committed.json').read_bytes())
    elif fault == 'native_receipt':
        put(s['home']/'hermes-agent.source.json', b'foreign receipt\n')
    elif fault == 'stamp':
        put(s['source']/'install-stamp.json', b'foreign stamp\n')
    else:
        put(s['home']/'.env', b'foreign credentials\n')
    repin(s)
    before = snapshot(s['home'])
    with pytest.raises((ValueError, AssertionError)):
        o.update(r, s['requestpath'], Budget(180))
    assert snapshot(s['home']) == before


@pytest.mark.parametrize('publication', [1, 2])
def test_partial_publication_rolls_back_and_consumes_attempt(installed, monkeypatch, publication):
    s = installed
    before = snapshot(s['home'])
    original = o.publish_update_file
    count = 0
    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == publication:
            raise RuntimeError('injected publication failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(o, 'publish_update_file', fail)
    with pytest.raises(RuntimeError, match='injected'):
        o.update(s['request'], s['requestpath'], Budget(180))
    after = snapshot(s['home'])
    assert all(after[n] == value for n, value in before.items())
    assert any(n.endswith('/rolled-back.json') for n in set(after)-set(before))
    with pytest.raises(ValueError):
        o.update(s['request'], s['requestpath'], Budget(180))


def test_same_bytes_on_foreign_inode_are_not_restored(installed, monkeypatch):
    from scripts.dsh_prepare import StopUnconfirmed
    s = installed
    original = o.publish_update_file
    foreign = {}
    def lose_custody(path, *args, **kwargs):
        if foreign:
            raise RuntimeError('injected custody loss')
        result = original(path, *args, **kwargs)
        other = path.with_name(path.name+'.foreign')
        put(other, path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        os.replace(other, path)
        foreign.update(path=path, state=o.update_file_state(path))
        return result
    monkeypatch.setattr(o, 'publish_update_file', lose_custody)
    with pytest.raises(StopUnconfirmed):
        o.update(s['request'], s['requestpath'], Budget(180))
    assert o.update_file_state(foreign['path']) == foreign['state']
    tx = s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert not (tx/'committed.json').exists()
    assert not (tx/'rolled-back.json').exists()
    assert f.read_json(tx/'intent.json')['state'] == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
    assert stat.S_IMODE((tx/'intent.json').stat().st_mode) == 0o400
