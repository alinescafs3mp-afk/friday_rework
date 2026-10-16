"""Finite SOURCE fixtures only: real Git application and owned publication.

Native identity/config/service admission is synthetic, never an installed home.
The Native78 predecessor is genuinely executed once in this fixture, including
its recursive source/project/keyless history, before preparing the v33 request.
Final native pins are substituted only for these explicitly synthetic bytes.
"""
import copy
import difflib
import fcntl
import os
from pathlib import Path

import pytest

from support_spark_source_update import installed as native77, doc, put, pin, snapshot, o, f
from scripts.install_containment import Budget


@pytest.fixture
def installed(native77, monkeypatch, tmp_path):
    s = native77
    home, source, root = s['home'], s['source'], s['root']
    # Closed qualification, two preparations, and sessions are retained data.
    closed = home/'profiles/dest_telegram/workers/qualification'
    for n in range(21): put(closed/f'closed-{n}.json', b'consumed; no retry\n')
    assert len([p for p in closed.rglob('*') if p.is_file()]) == 23
    for name, seconds in [('original', 300), ('second', 660)]:
        doc(home/f'preparation/retained-{name}/intent.json', {
            'state':'CONSUMED_NO_RETRY','seconds':seconds,'resume_allowed':False})
        put(home/f'profiles/{name}/workers/preparation.json', b'workers OFF\n')
        put(home/f'profiles/{name}/sessions/existing.json', b'existing session\n')
    o.update(s['request'], s['requestpath'], Budget(180))
    previous = copy.deepcopy(s['current'])
    prevref = s['request']['current_input']
    predecessor = pin(s['requestpath'])
    history = copy.deepcopy(s['request']['transaction_history'])
    prior_tx = home/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    history.update({str(p.relative_to(home)): f.digest(p.read_bytes())
                    for p in prior_tx.rglob('*') if p.is_file()})
    receipt = f.read_json(home/'hermes-agent.source.json')
    marker = f.read_json(home/f.MARKER)
    rows, patches = [], []
    for name in sorted(o.SPARK_MULTIPASS_FILES):
        added = name in o.SPARK_MULTIPASS_NEW_FILES
        before = b'' if added else (source/name).read_bytes()
        after = before+b'# reviewed optional Native79 source\n'
        (source/name).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        rows.append({'path':name, 'before_sha256':None if added else f.digest(before),
            'sha256':f.digest(after), 'bytes':len(after), 'mode':'100644', 'new_file':added})
        patches.append('diff --git a/'+name+' b/'+name+'\n'+('new file mode 100644\n' if added else '')+
            ''.join(difflib.unified_diff([] if added else before.decode().splitlines(True),
                after.decode().splitlines(True), fromfile='/dev/null' if added else 'a/'+name, tofile='b/'+name)))
    patchref = put(root/o.SPARK_MULTIPASS_PATCH, ''.join(patches).encode())
    manifest = {'base_commit':receipt['commit'], 'patch':o.SPARK_MULTIPASS_PATCH,
        'patch_sha256':patchref['sha256'],
        'installed_prefix':{r['manifest']:r['manifest_sha256'] for r in receipt['layers']}, 'files':rows}
    manref = doc(root/o.SPARK_MULTIPASS_MANIFEST, manifest)
    beforepins = {n:previous['project_files'][n] for n in o.SPARK_MULTIPASS_PROJECT_BEFORE}
    current = copy.deepcopy(previous)
    current['project_files'].update({o.SPARK_MULTIPASS_PATCH:patchref['sha256'],
        o.SPARK_MULTIPASS_MANIFEST:manref['sha256']})
    afterpins = {}
    for name in o.SPARK_MULTIPASS_PROJECT_AFTER:
        data = b'# reviewed optional producer source '+name.encode()+b'\n'
        afterpins[name] = put(root/name, data)['sha256']
        current['project_files'][name] = afterpins[name]
    candidate = Path(o.__file__).read_bytes()
    current['project_files']['scripts/friday_ordinary_install.py'] = put(
        root/'scripts/friday_ordinary_install.py', candidate)['sha256']
    curref = doc(tmp_path/'input231.json', current)
    request = {'schema':'friday.ordinary-telegram-source-update.v33', 'seconds':180, 'home':str(home),
        'previous_input':prevref, 'current_input':curref, 'marker':pin(home/f.MARKER),
        'source_receipt':pin(home/'hermes-agent.source.json'), 'stamp':pin(source/'install-stamp.json'),
        'configuration':s['configref'], 'profile':s['profileref'], 'launcher':s['launchref'],
        'credential_files':{'.env':None, 'auth.json':None}, 'native_unit':s['unitref'],
        'transaction_history':history, 'predecessor_update':predecessor}
    requestpath = tmp_path/'v33-request.json'; doc(requestpath, request)
    monkeypatch.setattr(o, 'SPARK_MULTIPASS_PREVIOUS_INPUT', prevref['sha256'])
    monkeypatch.setattr(o, 'SPARK_MULTIPASS_PROJECT_BEFORE', beforepins)
    monkeypatch.setattr(o, 'SPARK_MULTIPASS_PROJECT_AFTER', afterpins)
    monkeypatch.setattr(o, 'SPARK_MULTIPASS_NATIVE_FILES', len(receipt['files']))
    monkeypatch.setattr(o, 'SPARK_MULTIPASS_MANIFEST_SHA256', manref['sha256'])
    monkeypatch.setattr(o, 'SPARK_MULTIPASS_PATCH_SHA256', patchref['sha256'])
    recovery_tx, recovery = s['recovery_tx'], s['recovery']
    return locals()


def repin(s, *, manifest=False):
    if manifest:
        sha = doc(s['root']/o.SPARK_MULTIPASS_MANIFEST, s['manifest'])['sha256']
        s['current']['project_files'][o.SPARK_MULTIPASS_MANIFEST] = sha
    s['request']['current_input'] = doc(Path(s['request']['current_input']['path']), s['current'])
    doc(s['requestpath'], s['request'])


def test_one_layer_only_exact_owned_write_set_and_all_retained_inodes(installed):
    s = installed; before = snapshot(s['home'])
    states = {n:o.update_file_state(s['home']/n) for n in before}
    result = o.update(s['request'], s['requestpath'], Budget(180))
    assert result['ready'] is result['gateway_started'] is result['workers_enabled'] is False
    receipt = f.read_json(s['home']/'hermes-agent.source.json')
    assert len(receipt['layers']) == 79 and receipt['layers'][:-1] == s['receipt']['layers']
    assert set(receipt['files']) == set(s['receipt']['files']) | o.SPARK_MULTIPASS_NEW_FILES
    assert len(s['previous']['project_files']) == 229 and len(s['current']['project_files']) == 231
    marker = f.read_json(s['home']/f.MARKER)
    assert len(marker['plugin_files']) == 45
    assert marker['plugin_files'] == {n:h for n,h in s['current']['project_files'].items() if n.startswith('plugins/')}
    changed = {f.MARKER, 'hermes-agent.source.json', 'hermes-agent/install-stamp.json'} | \
        o.SPARK_MULTIPASS_PLUGIN_FILES | {'hermes-agent/'+n for n in o.SPARK_MULTIPASS_FILES}
    assert len(changed) == 17
    for n, state in states.items():
        if n not in changed: assert o.update_file_state(s['home']/n) == state
    assert marker['original_attempt'] == s['marker']['original_attempt']
    assert f.read_json(s['source']/'install-stamp.json')['original_clock'] == {'expired':True, 'remaining':0}
    assert len([p for p in (s['home']/'profiles/dest_telegram/workers/qualification').rglob('*') if p.is_file()]) == 23
    with pytest.raises(ValueError): o.update(s['request'], s['requestpath'], Budget(180))


@pytest.mark.parametrize('fault', ['pending_manifest', 'pending_patch', 'wrong_final_manifest', 'wrong_final_patch',
    'wrong_before_input', 'extra_project', 'producer_pin', 'producer_unchanged', 'second_plugin',
    'onboarding_pin', 'native_missing', 'native_extra', 'new_file_present', 'beforeimage', 'wrong_new_flag',
    'prefix', 'history_missing', 'history_bytes', 'wrong_predecessor', 'keyless_request_extra',
    'config', 'profile', 'credential', 'runtime', 'worker_helper', 'symlink_addition'])
def test_invalid_boundary_has_no_consumption_or_publication(installed, monkeypatch, fault):
    s = installed; r = s['request']; root = s['root']; home = s['home']
    if fault in ('pending_manifest', 'pending_patch', 'wrong_final_manifest', 'wrong_final_patch'):
        name = 'SPARK_MULTIPASS_MANIFEST_SHA256' if 'manifest' in fault else 'SPARK_MULTIPASS_PATCH_SHA256'
        monkeypatch.setattr(o, name, None if fault.startswith('pending') else '0'*64)
    elif fault == 'wrong_before_input': monkeypatch.setattr(o, 'SPARK_MULTIPASS_PREVIOUS_INPUT', '0'*64)
    elif fault == 'extra_project': s['current']['project_files']['config/extra'] = put(root/'config/extra', b'extra')['sha256']
    elif fault in ('producer_pin', 'second_plugin', 'onboarding_pin', 'worker_helper'):
        name = {'producer_pin':'tools/configure_product.py', 'second_plugin':'plugins/friday_rework/unchanged.py',
            'onboarding_pin':'plugins/friday_rework/onboarding.py', 'worker_helper':'scripts/friday_worker_preparation.py'}[fault]
        s['current']['project_files'][name] = put(root/name, b'foreign source\n')['sha256']
    elif fault == 'producer_unchanged':
        name = 'tools/configure_local_test.py'; (root/name).write_bytes(b'# old source\n')
        s['current']['project_files'][name] = s['previous']['project_files'][name]
    elif fault == 'native_missing': s['manifest']['files'].pop()
    elif fault == 'native_extra': s['manifest']['files'].append(dict(s['manifest']['files'][0], path='foreign.py'))
    elif fault == 'new_file_present': put(s['source']/next(iter(o.SPARK_MULTIPASS_NEW_FILES)), b'foreign', 0o644)
    elif fault == 'beforeimage': put(s['source']/'agent/bounded_context.py', b'foreign native\n', 0o644)
    elif fault == 'wrong_new_flag': next(row for row in s['manifest']['files'] if row['new_file'])['new_file'] = False
    elif fault == 'prefix': s['manifest']['installed_prefix'].pop(next(iter(s['manifest']['installed_prefix'])))
    elif fault == 'history_missing': r['transaction_history'].pop(next(iter(r['transaction_history'])))
    elif fault == 'history_bytes': put(home/next(n for n in r['transaction_history'] if n.endswith('before/preserved')), b'foreign history')
    elif fault == 'wrong_predecessor': r['predecessor_update'] = s['s']['prior']
    elif fault == 'keyless_request_extra': r['keyless_recovery'] = s['s']['recovery_pin']
    elif fault == 'config': put(home/'config.yaml', b'changed config\n')
    elif fault == 'profile': put(home/'FRIDAY-PROFILE.json', b'changed profile\n')
    elif fault == 'credential': put(home/'.env', b'foreign credential\n')
    elif fault == 'runtime': s['current']['product']['runtime']['enabled'] = True
    elif fault == 'symlink_addition':
        path = s['source']/next(iter(o.SPARK_MULTIPASS_NEW_FILES)); path.symlink_to(home/'config.yaml')
    repin(s, manifest=fault in ('native_missing', 'native_extra', 'wrong_new_flag', 'prefix'))
    before = snapshot(home)
    with pytest.raises((ValueError, FileNotFoundError, AssertionError, KeyError)):
        o.update(r, s['requestpath'], Budget(180))
    assert snapshot(home) == before
    assert not (home/'preparation'/('ordinary-source-update-'+r['previous_input']['sha256'])).exists()


@pytest.mark.parametrize('publication', range(1, 18))
def test_every_publication_failure_restores_beforeimages_and_consumes_once(installed, monkeypatch, publication):
    s = installed; before = snapshot(s['home']); original = o.publish_update_file; count = 0
    def fail(*args):
        nonlocal count
        count += 1
        if count == publication: raise RuntimeError('injected publication failure')
        return original(*args)
    monkeypatch.setattr(o, 'publish_update_file', fail)
    with pytest.raises(RuntimeError, match='injected'): o.update(s['request'], s['requestpath'], Budget(180))
    after = snapshot(s['home'])
    for n, state in before.items(): assert after[n] == state
    assert all(not (s['source']/n).exists() for n in o.SPARK_MULTIPASS_NEW_FILES)
    tx = s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert f.read_json(tx/'rolled-back.json')['state'] == 'ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'
    assert not (tx/'committed.json').exists()
    with pytest.raises(ValueError): o.update(s['request'], s['requestpath'], Budget(180))


@pytest.mark.parametrize('gate', ['composition', 'final_identity'])
def test_postpublication_validation_failure_restores_all_owned_files(installed, monkeypatch, gate):
    s = installed; before = snapshot(s['home'])
    if gate == 'composition':
        original = f.composition_checked
        def fail(value, *args, **kwargs):
            result = original(value, *args, **kwargs)
            if value == s['current']: raise RuntimeError('postpublication composition failure')
            return result
        monkeypatch.setattr(f, 'composition_checked', fail)
    else:
        import sys
        gateway = sys.modules['hermes_cli.friday_ordinary_gateway']; original = gateway.check
        def fail(home, **kwargs):
            result = original(home, **kwargs)
            if f.read_json(home/f.MARKER)['input_sha256'] == s['request']['current_input']['sha256']:
                raise RuntimeError('postpublication identity failure')
            return result
        monkeypatch.setattr(gateway, 'check', fail)
    with pytest.raises(RuntimeError, match='postpublication'):
        o.update(s['request'], s['requestpath'], Budget(180))
    after = snapshot(s['home'])
    for name, state in before.items(): assert after[name] == state
    assert all(not (s['source']/n).exists() for n in o.SPARK_MULTIPASS_NEW_FILES)
    tx = s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert (tx/'rolled-back.json').is_file() and not (tx/'committed.json').exists()


@pytest.mark.parametrize('kind', ['new', 'existing', 'plugin'])
def test_foreign_inode_is_never_adopted_or_restored(installed, monkeypatch, kind):
    from scripts.dsh_prepare import StopUnconfirmed
    s = installed; original = o.publish_update_file; foreign = None
    name = {'new':'hermes-agent/'+next(iter(o.SPARK_MULTIPASS_NEW_FILES)),
        'existing':'hermes-agent/agent/bounded_context.py', 'plugin':'plugins/friday_rework/onboarding.py'}[kind]
    def lose(path, *args):
        nonlocal foreign
        result = original(path, *args)
        if str(path.relative_to(s['home'])) == name:
            other = path.with_name('foreign-new'); put(other, path.read_bytes(), path.stat().st_mode & 0o777)
            os.replace(other, path); foreign = o.update_file_state(path)
            raise RuntimeError('lost custody')
        return result
    monkeypatch.setattr(o, 'publish_update_file', lose)
    with pytest.raises(StopUnconfirmed): o.update(s['request'], s['requestpath'], Budget(180))
    assert o.update_file_state(s['home']/name) == foreign


@pytest.mark.parametrize('which', ['home', 'build'])
def test_existing_writer_locks_refuse_before_consumption(installed, which):
    s = installed; path = s['home'] if which == 'home' else s['source']/'.web_ui_build.lock'
    if which == 'build': put(path, b'', 0o644)
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); before = snapshot(s['home'])
        with pytest.raises(BlockingIOError): o.update(s['request'], s['requestpath'], Budget(180))
        assert snapshot(s['home']) == before
    finally: os.close(fd)


@pytest.mark.parametrize('field,value', [('workers_enabled',True), ('resume_allowed',True),
    ('old_attempt_retry_authorized',True), ('new_runtime_authority','GRANTED'), ('original_attempt',{'deadline_mono':999999})])
def test_transitive_keyless_semantics_survive_coherent_outer_history(installed, field, value):
    s = installed; target = s['recovery_tx']/'committed.json'
    body = f.read_json(target); body[field] = value; doc(target, body)
    # Re-pin both v32's historical map and v33's outer map. The semantic check
    # must reject the consumed recovery even when byte inventories agree.
    prior = f.read_json(s['request']['predecessor_update']['path'])
    name = str(target.relative_to(s['home'])); sha = f.digest(target.read_bytes())
    prior['transaction_history'][name] = sha
    priorref = doc(Path(s['request']['predecessor_update']['path']), prior)
    prior_tx = s['home']/'preparation'/('ordinary-source-update-'+prior['previous_input']['sha256'])
    intent = f.read_json(prior_tx/'intent.json'); intent['request_sha256'] = priorref['sha256']
    doc(prior_tx/'intent.json', intent)
    s['request']['predecessor_update'] = priorref
    s['request']['transaction_history'][name] = sha
    s['request']['transaction_history'][str((prior_tx/'intent.json').relative_to(s['home']))] = f.digest((prior_tx/'intent.json').read_bytes())
    repin(s); before = snapshot(s['home'])
    with pytest.raises(ValueError, match='ordinary_update_committed_keyless_predecessor_required'):
        o.update(s['request'], s['requestpath'], Budget(180))
    assert snapshot(s['home']) == before
