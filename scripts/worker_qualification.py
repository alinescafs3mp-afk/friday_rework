"""One ordinary installed deployment transition, never per-job authority.

The host invokes fixed native observers against an already owned A0 probe.
No caller-supplied readiness report, capability, start or installation is used.
Original preparation and the original install deadline remain immutable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time

from scripts.friday_install import digest, owned_file, pin, publish, read_json, require, project_plugin, _source_runtime_module

FOLDER = 'preparation/worker-qualification'
PROOF = FOLDER + '/observation.json'
ORIGINAL = FOLDER + '/original.json'

# A scope moves this already owned foreground PID into native resource control;
# unlike a service it cannot execute a queued command after this client dies.
# The fixed guard checks the effective cgroup before exec of the existing PID
# namespace. Its descriptor custody and original timeout remain with run().


_observers = _source_runtime_module('runtime_observers')
DSH_SCOPE_GUARD, a0_observe, DSH_NATIVE_SAFETY, DSH_SAFETY_CONTROLS, checked_dsh_safety, dsh_safety_observe, dsh_observe = (
    getattr(_observers, name) for name in ('DSH_SCOPE_GUARD', 'a0_observe', 'DSH_NATIVE_SAFETY',
        'DSH_SAFETY_CONTROLS', 'checked_dsh_safety', 'dsh_safety_observe', 'dsh_observe'))

def original(home, marker):
    """Check the archived pending inventory; never substitute expected hashes."""
    ref = marker.get('worker_qualification')
    require(isinstance(ref, dict) and ref.get('path') == str(home / PROOF),
            'ordinary_worker_qualification_missing')
    pin(ref)
    proof = read_json(home / PROOF)
    require(proof.get('schema') == 'friday.worker-deployment-observation.v1'
            and proof.get('home') == str(home) and proof.get('effects') == 'OBSERVATION_ONLY'
            and proof.get('per_job_authority') == 'NOT_GRANTED'
            and set(proof.get('workers', {})) == {'dsh', 'a0'}, 'worker_observation_not_bound')
    observed = proof['observed']
    require(observed['boot_id'] == marker['original_attempt']['boot_id']
            and type(observed['monotonic']) in (int,float)
            and 0 < observed['monotonic'] <= marker['original_attempt']['deadline_mono'],
            'qualification_original_observation_clock_changed')
    archive = proof['original']
    require(archive['path'] == str(home / ORIGINAL), 'foreign_original_install_archive')
    pin(archive)
    before = read_json(home / ORIGINAL)
    require(before['marker']['original_attempt'] == marker['original_attempt']
            and before['marker']['home'] == str(home)
            and before['marker']['input_sha256'] == marker['input_sha256']
            and before['marker']['worker_state'] == 'BOTH_CONFIGURED_QUALIFICATION_PENDING',
            'original_install_ownership_changed')
    expected = {name: sha for name, sha in before['marker']['profile_files'].items()}
    expected.update({name: sha for name, sha in before['marker']['worker_files'].items()
                     if name.endswith('/runtime-receipt.json')})
    require(before['files'] == expected, 'original_preparation_archive_incomplete')
    for name, sha in expected.items():
        require(digest(owned_file(home / FOLDER / 'original' / name, private=True)) == sha,
                'original_preparation_archive_changed')
    # All original worker inputs/preparation stay at their original paths.
    for name, sha in before['marker']['worker_files'].items():
        if not name.endswith('/runtime-receipt.json'):
            require(digest(owned_file(home / name, private=True)) == sha,
                    'original_worker_input_changed')
    return proof, before['marker']


def original_receipt(home, worker, runtime, marker):
    if marker.get('worker_state') == 'BOTH_DEPLOYMENTS_QUALIFIED':
        original(home, marker)
        path = home / FOLDER / 'original/workers' / worker / 'runtime-receipt.json'
    else:
        path = Path(runtime['runtime_receipt']['path'])
    raw = owned_file(path, private=True)
    require(digest(raw) == runtime['runtime_receipt']['sha256'], 'original_pending_receipt_changed')
    return json.loads(raw)


def checked_product(value, home, product, marker):
    """Qualified receipts must match the single bound observation transaction."""
    proof, before = original(home, marker)
    require(proof['input_sha256'] == marker['input_sha256']
            and proof['profile'] == product['profile'], 'foreign_worker_qualification')
    record_digest = project_plugin('host_record', value).digest
    for worker, runtime in product['runtime']['workers'].items():
        observation = proof['workers'][worker]
        require(observation['runtime_sha256'] == record_digest(
                    {k:v for k,v in runtime.items() if k != 'runtime_receipt'}),
                'qualified_runtime_changed')
        pending = original_receipt(home, worker, runtime, marker)
        expected = dict(pending, ready=True, evidence=[*pending['evidence'], marker['worker_qualification']])
        path = home / 'workers' / worker / 'runtime-receipt.json'
        require(read_json(path) == expected, 'qualified_worker_receipt_changed')
        runtime['runtime_receipt'] = {'path': str(path), 'sha256': digest(owned_file(path, private=True))}
        pin(runtime['runtime_receipt'])
    # Public bootstrap inspection stays dependency-free. Native startup checks
    # the effective config/runtime against this exact returned package before
    # any launch. Static identity remains the original immutable generation.
    require(all(marker['profile_files'][name] == before['profile_files'][name]
                for name in ('SOUL.md','FRIDAY-PROFILE.json')), 'qualified_identity_changed')
    for name in ('.env', 'auth.json'):
        path = home / name
        sha = digest(owned_file(path, private=True)) if path.exists() or path.is_symlink() else None
        require(proof['credentials'][name] == sha, 'qualified_credential_store_changed')
    deployment_health = project_plugin('host_runtime', value).deployment_health
    for runtime in product['runtime']['workers'].values(): deployment_health(runtime)
    return product












def qualify(value, input_hash, plan_ref, budget):
    """Archive first, observe once, publish profile then commit marker last.

    Interrupted publication is fail-closed and cannot be automatically replayed.
    The existing config write transaction is held through observation/publication.
    An explicit existing probe retains its original owner. The ordinary path
    uses the same protected initial producer as user setup and settles its
    native custody before publishing qualified receipts.
    """
    from scripts.friday_install import inspect, MARKER, directory
    from scripts.dsh_prepare import StopUnconfirmed
    from scripts.worker_install import installed_product
    from hermes_constants import get_hermes_home
    from hermes_cli.config import config_write_transaction, atomic_config_write
    from tools.configure_product import compose_product
    home = Path(value['home'])
    require(get_hermes_home() == home and 'worker_install' in value, 'ordinary_native_qualification_required')
    budget.call(inspect, value, input_hash)
    marker = read_json(home / MARKER)
    require(marker.get('worker_state') == 'BOTH_CONFIGURED_QUALIFICATION_PENDING', 'worker_transition_not_pending')
    claim = marker['original_attempt']
    require(claim['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and budget.deadline == claim['deadline_mono'], 'original_qualification_clock_required')
    folder = home / FOLDER
    require(not folder.exists() and not folder.is_symlink(), 'partial_qualification_requires_reconciliation')
    product = budget.call(installed_product, value, home)
    with config_write_transaction(home / 'config.yaml'):
        # No live probes before the unchanged installed ownership is checked.
        budget.call(inspect, value, input_hash)
        bootstrap = project_plugin('a0_bootstrap', value)
        installation_probe, own_probe, checked_custody = bootstrap.installation_probe, bootstrap.own_probe, bootstrap.checked_custody
        probe_owner = None
        folder.mkdir(mode=0o700); directory(folder)
        files = dict(marker['profile_files'])
        files.update({p:h for p,h in marker['worker_files'].items() if p.endswith('/runtime-receipt.json')})
        for name, sha in files.items():
            target = folder / 'original' / name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw = budget.call(owned_file, home / name, private=True)
            require(digest(raw) == sha, 'original_qualification_input_changed')
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            with os.fdopen(fd, 'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        publish(home / ORIGINAL, {'marker': marker, 'files': files}, budget=budget)
        custody = None
        try:
            safety_scratch = folder / 'dsh-safety'; safety_scratch.mkdir(mode=0o700)
            safety = budget.call(dsh_safety_observe,product['runtime']['workers']['dsh'],home,safety_scratch,budget)
            budget.call(inspect,value,input_hash)
            credentials = {name: digest(owned_file(home / name, private=True))
                if (home / name).exists() or (home / name).is_symlink() else None for name in ('.env','auth.json')}
            probe_owner = None if plan_ref is not None else installation_probe(product,home,claim,budget,
                verify=lambda:budget.call(inspect,value,input_hash))
            if probe_owner is not None:
                with own_probe(probe_owner) as plan_ref:
                    a0 = budget.call(a0_observe, product['runtime']['workers']['a0'], plan_ref, budget, probe_owner=probe_owner)
                    budget.call(inspect,value,input_hash)
                custody = checked_custody(home,probe_owner.binding,1,probe_owner.preparations,plan_ref)
            scratch = folder / 'dsh-probe'; scratch.mkdir(mode=0o700)
            dsh = budget.call(dsh_observe, product['runtime']['workers']['dsh'], home, scratch, budget)
            dsh['safety'] = safety
            if probe_owner is None:
                a0 = budget.call(a0_observe, product['runtime']['workers']['a0'], plan_ref, budget)
        except StopUnconfirmed:
            # This finite private record grants no retry or fresh cleanup time.
            # Preserve the typed condition even if evidence storage fails.
            try:
                publish(folder / 'failure.json', {'state': 'STOP_UNCONFIRMED',
                    'original_attempt': claim, 'plan': plan_ref, 'retry_authorized': False})
            except (OSError, ValueError, RuntimeError):
                pass
            raise
        except BaseException:
            try:
                publish(folder / 'failure.json', {'state':'REFUSED_OR_UNCERTAIN',
                    'original_attempt':claim,'plan':plan_ref,'retry_authorized':False})
            except (OSError, ValueError, RuntimeError):
                pass
            raise
        # Observations cannot conceal a source/config/credential change.
        budget.call(inspect, value, input_hash)
        require(credentials == {name: digest(owned_file(home / name, private=True))
            if (home / name).exists() or (home / name).is_symlink() else None for name in credentials},
            'qualification_credentials_changed')
        record_digest = project_plugin('host_record', value).digest
        observed = {'dsh': dsh, 'a0': a0}
        for kind, runtime in product['runtime']['workers'].items():
            observed[kind]['runtime_sha256'] = record_digest({k:v for k,v in runtime.items() if k != 'runtime_receipt'})
        proof = {'schema':'friday.worker-deployment-observation.v1','home':str(home), 'profile':product['profile'],
            'input_sha256':input_hash,'original':{'path':str(home / ORIGINAL),'sha256':digest(owned_file(home / ORIGINAL,private=True))},
            'workers':observed,'credentials':credentials,'effects':'OBSERVATION_ONLY','per_job_authority':'NOT_GRANTED',
            'observed':{'boot_id':claim['boot_id'],'monotonic':time.monotonic(),'unix':time.time()}}
        if custody is not None: proof['bootstrap_custody'] = custody
        # Whole native observation validation precedes ready receipt publication.
        deployment_observations = project_plugin('host_runtime', value).deployment_observations
        for runtime in product['runtime']['workers'].values():
            budget.call(deployment_observations,runtime,proof,claim,folder)
        publish(home / PROOF, proof, budget=budget)
        ref = {'path':str(home / PROOF),'sha256':digest(owned_file(home / PROOF,private=True))}
        for kind, runtime in product['runtime']['workers'].items():
            path = Path(runtime['runtime_receipt']['path']); pending = read_json(path)
            staged = folder / (kind + '-receipt.json')
            publish(staged, dict(pending,ready=True,evidence=[*pending['evidence'],ref]), budget=budget)
            budget.call(os.replace, staged, path)
            runtime['runtime_receipt']['sha256'] = digest(owned_file(path,private=True))
        bundle = compose_product(product)
        # Write only the runtime-dependent config. Friday identity remains exact.
        require(owned_file(home / 'SOUL.md',private=True) == bundle['soul'].encode()
                and read_json(home / 'FRIDAY-PROFILE.json') == bundle['contract'], 'qualification_identity_changed')
        budget.call(atomic_config_write, home / 'config.yaml', bundle['config'])
        final = copy.deepcopy(marker)
        final['worker_state'] = 'BOTH_DEPLOYMENTS_QUALIFIED'
        final['worker_qualification'] = ref
        final['profile_files']['config.yaml'] = digest(owned_file(home / 'config.yaml',private=True))
        final['worker_files'] = {name: digest(owned_file(home / name,private=True)) for name in marker['worker_files']}
        staged = folder / 'installed.json'; publish(staged,final,budget=budget)
        budget.call(os.replace, staged, home / MARKER)
        fd = os.open(home,os.O_RDONLY | os.O_DIRECTORY)
        try: budget.call(os.fsync,fd)
        finally: os.close(fd)
        budget.call(inspect,value,input_hash)
    return {'state':'DEPLOYMENTS_QUALIFIED','ready':False,'per_job_authority':'NOT_GRANTED',
            'live_journeys':'NOT_RUN','a0_probe_cleanup':'ORIGINAL_NATIVE_OWNER'}
