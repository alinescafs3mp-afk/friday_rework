#!/usr/bin/env python3
"""Exact admitted known source runner. Source observations require review.

The CLI can prepare/admit source; --execute requires a genuine adapter supplied
out of band by the existing host. No adapter is installed by this package.
There is no import-from-receipt, arbitrary argv, new broker or runtime grant.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PKG = Path(__file__).absolute().parent

def _load(name):
    retained = globals().get('__gate_loader__')
    if retained is not None:
        # Concrete controlled bootstrap consumes already retained immutable
        # buffers. Default imports remain preparatory, never live authority.
        return retained.load_dependency(name)
    path = PKG / (name + '.py')
    data = path.read_bytes()
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module, data

contract, _contract_bytes = _load('runner_contract')
gate, _gate_bytes = _load('gate_inputs')
LOADED = {'runner_contract.py': contract.digest(_contract_bytes), 'gate_inputs.py': contract.digest(_gate_bytes)}
KINDS = {'onboard-filtered', 'cli-filtered', 'catalog-filtered',
         'onboard-expanded', 'cli-expanded', 'catalog-expanded'}
pid_start = contract.pid_start

def implementation_pins(values, *, loader=None, phase='parent_implementation', binding=None, worker=None):
    names = {'source_runner.py', 'gate_inputs.py', 'runner_worker.py', 'runner_contract.py', 'interpreter'}
    contract.need(isinstance(values, dict) and set(values) == names, 'implementation_pin_schema')
    for name, ref in values.items():
        expected = str(Path(sys.executable).resolve()) if name == 'interpreter' else str(PKG / name)
        contract.need(ref['path'] == expected, 'foreign_implementation:' + name)
        data = contract.verify(ref, 'implementation:' + name)
        if name in LOADED:
            contract.need(contract.digest(data) == LOADED[name], 'loaded_implementation_changed:' + name)
    return contract.loaded_implementation(loader, values, phase, 'parent', globals(), binding, worker)

def admit(inputs, binding, source_anchor, relocation_ref, grant_ref, trusted_grant, kind, output, *, loader=None):
    gate.need(kind in KINDS, 'unknown_or_runtime_runner')
    contract.require_loader(loader)  # no preflight or output without the actual loader
    gate.source_preflight(inputs, binding, source_anchor)
    contract.need(grant_ref == trusted_grant, 'foreign_run_grant_anchor')
    grant = contract.document(grant_ref, 'parent_source_run_grant')
    contract.need(grant.get('schema') == 'friday.known-source-checker-grant-root-received.v2', 'run_grant_schema')
    contract.need(grant.get('independent_source_accepted') is True and grant.get('runtime_grant') is False and
                  not grant.get('AUTHOR_FIXTURE_ONLY'), 'source_grant_not_independently_accepted')
    contract.need(grant.get('binding_sha256') == binding['binding_sha256'], 'stale_run_grant_binding')
    contract.need(grant.get('relocation') == relocation_ref, 'stale_run_grant_relocation')
    output = contract.canonical_path(output)
    contract.need(kind in grant.get('allowed_kinds', []) and grant.get('output_root') == str(output), 'ungranted_checker_or_output')
    contract.need(grant.get('root_only_output_relocation_accepted') is True, 'output_rebinding_not_reviewed')
    contract.budget_limits(grant.get('original_budget'))
    limits = contract.resources(grant.get('resources'))
    slot = grant.get('exclusive_slot', {})
    contract.need(set(slot) == {'receipt', 'owner_pid', 'owner_start_ticks'}, 'exclusive_slot_schema')
    observed = contract.document(slot['receipt'], 'exclusive_slot_receipt')
    contract.need(observed.get('state') == 'HELD' and observed.get('binding_sha256') == binding['binding_sha256'] and
                  observed.get('owner_pid') == slot['owner_pid'] and observed.get('owner_start_ticks') == slot['owner_start_ticks'], 'slot_not_held')
    contract.need(pid_start(slot['owner_pid']) == slot['owner_start_ticks'], 'slot_owner_identity_missing')
    # Slot JSON/PID is only a preparation check. execute requires retained kernel
    # custody from the EXISTING host, before any output/worker effect.
    implementation = grant.get('implementation')
    loaded_identity = implementation_pins(implementation, loader=loader, phase='before_admission', binding={'binding_sha256': binding['binding_sha256'], 'grant': grant_ref}).decode('utf-8')
    approved_affinity = contract.cpu_affinity(grant.get('approved_affinity'), limits['CPUs'])
    scope = contract.read_scope(grant.get('read_scope'))
    relocation = contract.document(relocation_ref, 'independently_reviewed_relocation')
    contract.need(relocation.get('binding_sha256') == binding['binding_sha256'], 'relocation_binding_mismatch')
    key, mode = kind.split('-')
    rows = [r for r in relocation['checkers'] if r['kind'] == key]
    contract.need(len(rows) == 1, 'required_checker_omitted_or_duplicated')
    target = rows[0]['expanded']['ref'] if mode == 'expanded' else rows[0]['after']
    contract.verify(target, 'exact_selected_checker')
    if mode == 'expanded':
        contract.need(grant.get('all_expanded_effects_independently_reviewed') is True, 'expanded_effect_review_missing')
    auxiliary = grant.get('auxiliary_inputs', {})
    contract.need(isinstance(auxiliary, dict), 'auxiliary_schema')
    if key == 'cli' and mode == 'expanded':
        contract.need('CLI-COMPOSITION-PINS.json' in auxiliary, 'mandatory_CLI_composition_pins_missing')
    for name, ref in auxiliary.items():
        contract.need(isinstance(name, str) and Path(name).name == name and '..' not in name.split('/') and name.endswith('.json'), 'escaping_auxiliary')
        contract.verify(ref, 'auxiliary:' + name)
    scope_paths = {r['path']: r for r in scope['files']}
    for name, ref in {'checker': target, **auxiliary, **implementation}.items():
        contract.need(scope_paths.get(ref['path']) == ref, 'required_input_outside_pinned_read_scope:' + name)
    # Deep immutable snapshot: callers cannot mutate grant dictionaries later.
    admission = {'schema': 'friday.source-run-admission.v2', 'kind': kind,
        'binding_sha256': binding['binding_sha256'], 'binding': binding, 'inputs': inputs,
        'source_anchor': source_anchor, 'checker': target, 'relocation': relocation,
        'pins': {'grant': grant_ref, 'relocation': relocation_ref, 'source_anchor': source_anchor,
                 'slot_receipt': slot['receipt'], 'clock': grant['original_budget']['clock_ref'],
                 **{'implementation:' + n: r for n, r in implementation.items()}},
        'auxiliary': auxiliary, 'implementation': implementation, 'loaded_identity': loaded_identity,
        'approved_affinity': approved_affinity, 'read_scope': scope,
        'exclusive_slot': slot, 'budget': grant['original_budget'], 'resources': limits,
        'output_root': str(output), 'runtime_grant': False, 'independent_acceptance': False}
    return contract.canonical(admission)  # bytes are the admission token, not authority

def decode_admission(token):
    contract.need(isinstance(token, bytes), 'admission_snapshot_required')
    result = contract.parse(token)
    contract.need(result.get('schema') == 'friday.source-run-admission.v2', 'admission_schema')
    contract.need(result['kind'] in KINDS and result['runtime_grant'] is False, 'unknown_or_runtime_runner')
    return result

def revalidate(token, *, loader=None, phase='parent_revalidation', worker=None):
    a = decode_admission(token)
    contract.revalidate_inputs(a)
    observed = implementation_pins(a['implementation'], loader=loader, phase=phase, binding={'binding_sha256': a['binding_sha256'], 'grant': a['pins']['grant']}, worker=worker)
    contract.need(observed.decode('utf-8') == a.get('loaded_identity'), 'admitted_loaded_identity_changed')
    contract.cpu_affinity(a.get('approved_affinity'), a['resources']['CPUs'])
    gate.source_preflight(a['inputs'], a['binding'], a['source_anchor'])
    return a

def prepare_job(token, *, loader=None):
    """Exact original pins survive copy/rebinding; source-only helper, no launch."""
    a = revalidate(token, loader=loader, phase='before_materialize')
    return materialize_job(a)

def materialize_job(a):
    """Pure owned-output preparation; does not confer admission or effects."""
    contract.revalidate_inputs(a)
    out = contract.canonical_path(a['output_root'])
    contract.need(not out.exists(), 'owned_run_output_exists_no_replay')
    # Assemble bounded immutable buffers/pins before any output effect. Pins
    # describe the deterministic accepted relocation, never fresh authority.
    contract.need(out.parent.is_dir(), 'owned_output_parent_missing')
    source = contract.verify(a['checker'], 'admitted_checker').decode('utf-8')
    selected = next(r for r in a['relocation']['checkers'] if r['kind'] == a['kind'].split('-')[0])
    audit_root = str(Path(selected['after']['path']).parent.parent)
    moved, edits = gate.relocate_checker(source, {audit_root: str(out)})
    buffers = {Path(a['checker']['path']).name: moved.encode('utf-8')}
    contract.need(len(a['auxiliary']) <= 64, 'auxiliary_membership_bound')
    auxiliary = {}
    def derived(name, data):
        return {'path': str(out / name), 'bytes': len(data), 'sha256': contract.digest(data)}
    checker = derived(Path(a['checker']['path']).name, buffers[Path(a['checker']['path']).name])
    for name, ref in a['auxiliary'].items():
        contract.need(name not in buffers and name not in {'JOB.json', 'READY.json', 'BARRIER.json', 'IDENTITY.json',
                      'WORKER-CLOSURE.json', 'RUN-RESULT.json', 'runner.log'}, 'auxiliary_reserved_or_duplicate_name')
        data = contract.verify(ref, 'auxiliary:' + name)
        contract.need(sum(map(len, buffers.values())) + len(data) <= a['resources']['output_bytes'] - 65536,
                      'preparation_aggregate_output_bound')
        buffers[name] = data
        auxiliary[name] = derived(name, data)
        contract.need(auxiliary[name]['sha256'] == ref['sha256'] and auxiliary[name]['bytes'] == ref['bytes'], 'auxiliary_copy_changed')
    job = contract.job_payload(a, checker, auxiliary, edits)
    buffers['JOB.json'] = contract.canonical(job) + b'\n'
    contract.need(sum(map(len, buffers.values())) <= a['resources']['output_bytes'] - 65536, 'preparation_aggregate_output_bound')
    contract.revalidate_inputs(a)
    out.mkdir(mode=0o700)
    for name, data in buffers.items():
        written = contract.rooted_write(out, name, data)
        contract.need(written == derived(name, data), 'private_copy_changed')
    job_ref = derived('JOB.json', buffers['JOB.json'])
    contract.verify_job(job_ref, out, contract.digest(contract.canonical(a)))
    return job_ref

def cleanup_provenance(a, *, custody, loader, phase, worker, job_ref):
    """Observe each original obligation independently; never gate owned stop.

    Loaded buffers are observed before fresh input verification, so changed
    inputs or an expired clock cannot hide the loaded/context observation.
    Every refusal is secondary evidence, not permission to leave effects live.
    """
    observations = {'phase': phase, 'refusals': []}
    def observe(name, callback):
        try:
            callback()
            observations[name] = 'OBSERVED'
        except BaseException as error:
            observations[name] = 'REFUSED'
            observations['refusals'].append({'obligation': name,
                'cause': type(error).__name__ + ':' + str(error)})
    def loaded():
        value = contract.loaded_implementation(loader, a['implementation'], phase,
            'parent', globals(), {'binding_sha256': a['binding_sha256'],
            'grant': a['pins']['grant']}, worker)
        contract.need(value.decode('utf-8') == a['loaded_identity'],
                      'admitted_loaded_identity_changed')
    observe('loaded_implementation_interpreter_context', loaded)
    observe('original_inputs_budget_resources', lambda: contract.revalidate_inputs(a))
    observe('retained_host_context', lambda: contract.require_custody(
        custody, a, phase, worker, job_ref))
    return observations

def execute(token, *, custody=None, loader=None):
    """Existing-host adapter owns launch/fences/closure; no JSON/PID fallback.

    Adapter API is an integration dependency, not an implemented native grant.
    launch_owned_source_worker receives only exact fixed worker/job/interpreter
    pins and immutable admission, never user argv. Its worker must call the
    exact runner_worker.run with its authenticated retained live verifier.
    """
    a = revalidate(token, loader=loader, phase='before_launch')
    contract.require_custody(custody, a, 'before_launch')  # BEFORE mkdir/write
    contract.need(callable(getattr(custody, 'launch_owned_source_worker', None)) and
                  callable(getattr(custody, 'capture_worker_closure', None)) and
                  callable(getattr(custody, 'stop_owned', None)), 'existing_host_worker_adapter_unavailable')
    job_ref = prepare_job(token, loader=loader)
    out = Path(a['output_root']); child = None; worker = None
    hard, useful = contract.budget_limits(a['budget'])
    record = {'full_gate_started': False, 'runtime_grant': False, 'independent_acceptance': False,
              'kind': a['kind'], 'job': job_ref, 'source_evidence_requires_review': True, 'success': False}
    try:
        revalidate(token, loader=loader, phase='parent_boundary', worker=worker)
        contract.verify(job_ref, 'job_before_launch')
        contract.require_custody(custody, a, 'immediately_before_launch', job_ref=job_ref)
        child = custody.launch_owned_source_worker(admission=token, job_ref=job_ref)
        worker = {'pid': child.pid, 'start_ticks': pid_start(child.pid)}
        contract.need(worker['start_ticks'] is not None, 'worker_identity_missing')
        record['worker'] = worker
        contract.save(out, 'IDENTITY.json', record)
        while not (out / 'READY.json').exists():
            contract.need(child.poll() is None and time.time() < useful, 'source_worker_ready_timeout')
            time.sleep(.01)
        ready_ref = contract.pin(out / 'READY.json'); ready = contract.document(ready_ref, 'ready')
        contract.need(contract.canonical(ready.get('worker')) == contract.canonical(worker) and contract.canonical(ready.get('job')) == contract.canonical(job_ref), 'ready_identity_or_job_mismatch')
        contract.need(ready.get('resources') == a['resources'], 'ready_resources_changed')
        contract.need(contract.cpu_affinity(ready.get('affinity'), a['resources']['CPUs']) == a['approved_affinity'], 'ready_affinity_changed')
        contract.need(pid_start(worker['pid']) == worker['start_ticks'], 'worker_birth_changed_before_barrier')
        revalidate(token, loader=loader, phase='parent_boundary', worker=worker)
        contract.verify_job(job_ref, out, contract.digest(token))
        contract.require_custody(custody, a, 'before_barrier', worker, job_ref)
        barrier = {'worker': worker, 'job': job_ref, 'admission_sha256': contract.digest(token),
                   'useful_epoch': useful, 'hard_epoch': hard, 'approved_affinity': a['approved_affinity']}
        contract.save(out, 'BARRIER.json', barrier)
        child.wait(timeout=max(.001, useful - time.time()))
        record['exit_code'] = child.returncode
        # A target-authored closure file alone is NOT trusted: the existing host
        # must capture its exact ref and independently observe owned obligations.
        observation = custody.capture_worker_closure(worker=worker, job_ref=job_ref)
        contract.need(isinstance(observation, dict) and observation.get('worker') == worker and
                      observation.get('job') == job_ref and observation.get('owned_obligations_observed') is True,
                      'trusted_worker_closure_unavailable')
        closure_ref = observation['closure_ref']
        contract.need(closure_ref['path'] == str(out / 'WORKER-CLOSURE.json'), 'foreign_worker_closure')
        closure = contract.document(closure_ref, 'trusted_worker_closure')
        contract.require_custody(custody, a, 'after_reap', worker, job_ref)
        revalidate(token, loader=loader, phase='parent_boundary', worker=worker)
        contract.verify_job(job_ref, out, contract.digest(token))
        record['worker_reaped'] = child.poll() is not None
        children = Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()
        absent = pid_start(worker['pid']) is None
        contract.completion(record, closure, job_ref, worker, a['budget'], a['resources'], time.time(), absent, children,
                            trusted_resources=observation.get('resource_observation'), approved_affinity=a['approved_affinity'])
        record['outputs'] = contract.output_inventory(out, a['resources']['output_bytes'])
        record.update(success=True, status='SOURCE_RUN_OBSERVED_REQUIRES_INDEPENDENT_REVIEW', closure=closure_ref)
    except BaseException as error:
        record.update(failure=type(error).__name__ + ':' + str(error), status='SOURCE_RUN_FAILED')
    finally:
        def stop_and_reap():
            # Stop first on an existing failure: input/provenance reads must
            # never withhold the exact original owned stop, even if they refuse.
            record['host_cleanup_attempted'] = True
            try:
                stop = custody.stop_owned(worker=worker, job_ref=job_ref)
                contract.need(isinstance(stop, dict) and stop.get('status') == 'STOP_CONFIRMED', 'STOP_UNCONFIRMED')
                record['host_cleanup'] = stop
            except BaseException as stop_error:
                record.update(success=False, status='STOP_UNCONFIRMED',
                              cleanup_failure=type(stop_error).__name__ + ':' + str(stop_error))
            finally:
                # Reap the retained exact child handle even if stop observation
                # refuses. No guessed PID, alternate kill, or repeated launch.
                if child is not None:
                    try:
                        child.wait(timeout=max(.001, hard - time.time()))
                    except BaseException as reap_error:
                        record.update(success=False, status='STOP_UNCONFIRMED',
                            reap_failure=type(reap_error).__name__ + ':' + str(reap_error))
        if not record.get('success'):
            stop_and_reap()
            record['cancel_provenance'] = cleanup_provenance(a, custody=custody,
                loader=loader, phase='parent_cancel', worker=worker, job_ref=job_ref)
        record['cleanup_provenance'] = cleanup_provenance(a, custody=custody,
            loader=loader, phase='parent_cleanup', worker=worker, job_ref=job_ref)
        secondary = [r for key in ('cancel_provenance', 'cleanup_provenance')
                     for r in record.get(key, {}).get('refusals', [])]
        if secondary:
            record['provenance_refusals'] = secondary
            record.setdefault('failure', 'cleanup_provenance_refused')
            record['success'] = False
            if record.get('status') != 'STOP_UNCONFIRMED':
                record['status'] = 'SOURCE_RUN_FAILED'
        # The retained existing host owns the full kernel subtree and uncertain
        # launch, even when no child handle returned. A PID-only local kill is
        # insufficient and must never replace that exact-owned cleanup.
        if not record.get('success') and not record.get('host_cleanup_attempted'):
            stop_and_reap()
        record['worker_reaped'] = child is not None and child.poll() is not None
        record['worker_identity_absent'] = worker is not None and pid_start(worker['pid']) is None
        record['supervisor_children'] = Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').read_text().split()
        if not record['worker_reaped'] or not record['worker_identity_absent'] or record['supervisor_children']:
            record.update(success=False, status='STOP_UNCONFIRMED')
        result_bytes = contract.canonical(record) + b'\n'
        inventory = contract.output_inventory(out, a['resources']['output_bytes'])
        if inventory['total_bytes'] + len(result_bytes) > a['resources']['output_bytes']:
            record.update(success=False, status='SOURCE_RUN_FAILED', failure='final_result_aggregate_output_bound')
            # Retained real custody must preserve closure even when its output
            # quota cannot store another receipt. No success is returned.
        else:
            contract.rooted_write(out, 'RUN-RESULT.json', result_bytes)
    return record

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'binding', 'source-anchor', 'relocation-ref', 'grant-ref', 'trusted-grant', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--kind', required=True); p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    try:
        token = admit(gate.input_document(a.inputs), gate.document(a.binding), gate.document(a.source_anchor),
                      gate.document(a.relocation_ref), gate.document(a.grant_ref), gate.document(a.trusted_grant), a.kind, a.output)
        if a.execute:
            result = execute(token)  # default intentionally cannot grant host effects
            print(json.dumps(result)); return 0 if result.get('success') is True else 1
        print(json.dumps({'status': 'EXACT_SOURCE_PREPARED_NOT_RUN_HOST_CUSTODY_REQUIRED', 'kind': a.kind,
                          'admission_sha256': contract.digest(token), 'runtime_grant': False}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'NOT_RUN', 'cause': str(error), 'runtime_grant': False, 'full_gate_started': False}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
