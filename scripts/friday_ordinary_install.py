"""Finite ordinary Telegram source activation; native owners retain the receiver.

There is one explicit reviewed deployment transaction. It never resets a CLI
clock, executes a consumed query, enables a worker, approves a user or starts a
consumer. Subsequent service starts use the installed native CLI and unit.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path
import stat

MANIFEST = 'patches/hermes/ordinary-telegram-manifest.json'
TRANSACTION = 'preparation/ordinary-gateway'
UPDATE_MANIFEST = 'patches/hermes/ordinary-native-repair-manifest.json'
UPDATE_FILES = {'hermes_cli/friday_dashboard_owner.py', 'hermes_cli/friday_credential_admission.py'}
PRIVATE_STATE_MANIFEST = 'patches/hermes/ordinary-private-state-manifest.json'
PRIVATE_STATE_FILES = {'hermes_cli/plugins_state.py', 'utils.py'}
FILE_CONTINUATION_MANIFEST = 'patches/hermes/ordinary-file-continuation-manifest.json'
FILE_CONTINUATION_FILES = {'hermes_cli/friday_user_scope.py', 'gateway/run_inbound_media.py',
    'gateway/platforms/base.py', 'gateway/run_notifications.py', 'gateway/run_plugin_delivery.py',
    'gateway/run_turn.py', 'plugins/platforms/telegram/adapter.py'}
WORKER_ATTACH_PLUGIN_FILES = {'plugins/friday_rework/onboarding.py',
    'plugins/friday_rework/worker_provision.py', 'plugins/friday_rework/dashboard/api.py',
    'plugins/friday_rework/dashboard/index.js'}


def api():
    from scripts import friday_install
    return friday_install


def write(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def replace(path, data, mode=0o600):
    temporary = path.with_name(path.name + '.ordinary-staged')
    fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        os.fchmod(fd,mode)  # Preserve the exact beforeimage mode under any umask.
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()
    fd = os.open(path.parent, os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def inputs(request, budget):
    f = api()
    f.require(type(request) is dict and set(request) == {'schema','seconds','home','installation_input','previous_input','current_input',
        'marker','source_receipt','configuration','pending_configuration','profile','launcher','tool_search_defer','credential_files'} |
        ({'prior_rolled_back'} if request.get('schema') == 'friday.ordinary-telegram-activation.v2' else set())
        and request['schema'] in ('friday.ordinary-telegram-activation.v1','friday.ordinary-telegram-activation.v2')
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180, 'ordinary_explicit_request_required')
    home = f.directory(f.canonical(request['home'])); source = home/'hermes-agent'
    paths = {name:budget.call(f.pin, request[name]) for name in request if name not in ('schema','seconds','home','tool_search_defer','credential_files','prior_rolled_back')}
    f.require(paths['marker'] == home/f.MARKER and paths['source_receipt'] == home/'hermes-agent.source.json'
        and paths['configuration'] == home/'config.yaml' and paths['profile'] == home/'FRIDAY-PROFILE.json'
        and paths['launcher'] == source/'.hermes/bin/hermes', 'ordinary_exact_installed_inputs_required')
    credentials=request['credential_files']
    f.require(type(credentials) is dict and set(credentials)=={'.env','auth.json'}, 'ordinary_credential_pins_required')
    for name,ref in credentials.items():
        path=home/name
        if ref is None:
            f.require(not os.path.lexists(path),'ordinary_credential_absence_changed')
        else:
            f.require(f.pin(ref)==path and f.digest(f.owned_file(path,private=True))==ref['sha256'],'ordinary_credential_pin_changed')
    previous = budget.call(f.read_json, paths['previous_input'])
    current = budget.call(f.read_json, paths['current_input'])
    marker = budget.call(f.read_json, paths['marker'])
    f.require(marker.get('completion_stage') == 'CLI_HOST_ONLY' and marker.get('runtime_ready') is False
        and marker.get('gateway_installed') is False and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and marker.get('input_sha256') == request['installation_input']['sha256']
        and marker.get('postinstall_source_input') == request['previous_input'], 'ordinary_cli_history_required')
    original = budget.call(f.read_json, paths['installation_input'])
    f.require({k:v for k,v in original.items() if k != 'project_files'} ==
        {k:v for k,v in previous.items() if k != 'project_files'}, 'ordinary_original_installation_scope_changed')
    f.require(request['previous_input'] != request['current_input'], 'ordinary_update_new_input_required')
    f.require({k:v for k,v in previous.items() if k != 'project_files'} ==
        {k:v for k,v in current.items() if k != 'project_files'} and current['home'] == str(home),
        'ordinary_deployment_scope_changed')
    f.require(f.cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
        and (marker.get('cli_segment') is None or f.cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1')),
        'ordinary_previous_scope_not_closed')
    f.spec_checked(current, cli_only=True)
    # The current source is an exact ordered prefix; the only new layer is this
    # reviewed manifest. No old layer, consumed intent or historical pin moves.
    receipt = budget.call(f.read_json, paths['source_receipt'])
    donors = {r['id']:r for r in f.read_json(f.pin(current['sources_lock']))['repositories']}
    f.composition_checked(previous, source, receipt, donors['hermes'])
    manifest = f.read_json(f.ROOT/MANIFEST)
    f.require(current['project_files'][MANIFEST] == f.digest(f.owned_file(f.ROOT/MANIFEST))
        and set(current['project_files']) == set(previous['project_files']) | {MANIFEST, manifest['patch'], 'scripts/friday_ordinary_install.py'}
        and all(current['project_files'][name] == pin for name,pin in previous['project_files'].items()
                if name not in ('scripts/friday_install.py','scripts/friday_native.py','scripts/friday_start.py','plugins/friday_rework/onboarding.py')),
        'ordinary_additive_source_required')
    f.require(manifest['base_commit'] == receipt['commit'], 'ordinary_manifest_required')
    f.require(set(manifest['installed_prefix']) == {r['manifest'] for r in receipt['layers']}
        and all(manifest['installed_prefix'][r['manifest']] == r['manifest_sha256'] for r in receipt['layers']),
        'ordinary_exact_prefix_required')
    # Overlay manifests use patch prerequisites for composition. Prefix manifests
    # are pinned separately so old private scopes cannot be silently rewritten.
    for row in manifest['files']:
        p = source/row['path']
        if row['new_file']:
            f.require(not p.exists() and not p.is_symlink(), 'ordinary_new_source_exists')
        else:
            f.require(f.digest(f.owned_file(p)) == row['before_sha256']
                and receipt['files'][row['path']]['sha256'] == row['before_sha256'], 'ordinary_source_changed')
    f.require(f.digest(f.owned_file(f.ROOT/manifest['patch'])) == manifest['patch_sha256'], 'ordinary_patch_changed')
    raw = f.owned_file(paths['pending_configuration'], private=True)
    # Native YAML parser is imported only after the complete old source inventory.
    f.native_packages(source)
    from hermes_cli.friday_dashboard_owner import source_identity
    source_identity(home,source=source)
    f.require(all(f.digest(f.owned_file(home/name,private=True))==pin for name,pin in marker['profile_files'].items()),'ordinary_profile_history_changed')
    from hermes_cli.config_effective import read_user_config_effective_readonly
    cfg = budget.call(read_user_config_effective_readonly, paths['pending_configuration'])
    old_cfg = budget.call(read_user_config_effective_readonly, home/'config.yaml')
    import copy
    changed = copy.deepcopy(old_cfg)
    changed['platforms']['telegram'].setdefault('extra', {})['drop_pending_on_cold_boot'] = False
    changed['platforms']['telegram']['extra']['unauthorized_dm_behavior'] = 'pair'
    changed['gateway']['systemd_watchdog_seconds'] = 30
    deferred = request['tool_search_defer']
    f.require(type(deferred) is list and bool(deferred) and len(deferred) == len(set(deferred))
        and all(isinstance(n,str) and n.isidentifier() for n in deferred)
        and not {'read_file','session_search','clarify'}.intersection(deferred), 'ordinary_progressive_tools_required')
    plans = changed['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    f.require(bool(plans), 'ordinary_worker_free_template_required')
    # Keep the full worker template intact. An explicit ordinary template uses
    # the same local model, personality, tools and required scoped credentials.
    ordinary_name = 'friday-ordinary-local'
    f.require('friday-local' in plans and ordinary_name not in plans,
              'ordinary_explicit_template_required')
    template = copy.deepcopy(plans['friday-local'])
    template.pop('worker_inputs', None)
    own = template['config']['plugins']['entries']['friday_rework']['settings']
    f.require(own.get('runtime') == {'enabled':False} and 'worker_requirements' not in own,
              'ordinary_worker_free_template_required')
    template['config'].setdefault('tools',{}).setdefault('tool_search',{})['defer'] = deferred
    plans[ordinary_name] = template
    f.require(cfg == changed, 'ordinary_only_pending_and_progressive_tools_change_required')
    settings = cfg['plugins']['entries']['friday_rework']['settings']
    f.require(settings.get('runtime') == {'enabled':False} and 'worker_requirements' not in settings
        and settings.get('user_isolation') is None and cfg['gateway'].get('profile_routes',[]) == []
        and len(settings['product_access']['accounts']) == 1
        and settings['product_access']['accounts'][0]['platform'] == 'telegram', 'ordinary_worker_free_bootstrap_required')
    if request['schema'] == 'friday.ordinary-telegram-activation.v1':
        f.require(not os.path.lexists(home/TRANSACTION)
            and not os.path.lexists(home/'preparation/ordinary-gateway-archive'), 'ordinary_transaction_already_exists')
    else:
        recovery_checked(request, home, manifest)
    return home, source, paths, previous, current, marker, receipt, manifest, raw, cfg


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def saved_names(manifest):
    return ['FRIDAY-INSTALL.json','hermes-agent.source.json','config.yaml','hermes-agent/install-stamp.json'] + [
        'hermes-agent/'+r['path'] for r in manifest['files'] if not r['new_file']] + ['plugins/friday_rework/onboarding.py']


def no_consumer(home):
    # Same native ownership boundary as explicit source rollback: never stop,
    # uninstall or wake a service to manufacture eligibility for continuation.
    f = api(); f.native_packages(home/'hermes-agent')
    from gateway import host_rendezvous as hr
    from hermes_cli import gateway as gw
    f.require(not gw.get_systemd_unit_path(system=False).exists()
        and not gw.get_systemd_unit_path(system=True).exists()
        and hr.read_record(hr.ROLE_GATEWAY,include_stale=True) is None
        and not gw.find_gateway_pids(), 'ordinary_recovery_no_consumer_required')


def recovery_checked(request, home, manifest):
    """One explicit corrected host candidate after a proven source-only refusal."""
    f=api(); ref=request['prior_rolled_back']; tx=home/TRANSACTION
    f.require(type(ref) is dict and set(ref)=={'request','intent','rollback','archive'},
              'ordinary_recovery_exact_references_required')
    f.directory(tx); before=f.directory(tx/'before')
    f.require({p.name for p in tx.iterdir()} == {'before','intent.json','rolled-back.json'},
              'ordinary_recovery_uncommitted_rollback_required')
    for key,name in [('intent','intent.json'),('rollback','rolled-back.json')]:
        f.require(f.pin(ref[key])==tx/name,'ordinary_recovery_exact_references_required')
    intent=f.read_json(tx/'intent.json'); rollback=f.read_json(tx/'rolled-back.json')
    old=f.read_json(f.pin(ref['request']))
    f.require(intent.get('schema')=='friday.ordinary-telegram-transaction.v1'
        and intent.get('state')=='SOURCE_TRANSACTION_STARTED_NOT_RUNTIME'
        and intent.get('request_sha256')==ref['request']['sha256']
        and rollback=={'state':'ROLLED_BACK_SOURCE_ONLY_NO_RUNTIME_STARTED'},
        'ordinary_recovery_closed_rollback_required')
    f.require(old.get('schema')=='friday.ordinary-telegram-activation.v1'
        and {k:v for k,v in request.items() if k not in ('schema','current_input','prior_rolled_back')} ==
            {k:v for k,v in old.items() if k not in ('schema','current_input')},
        'ordinary_recovery_scope_changed')
    old_input=f.read_json(f.pin(old['current_input']))
    new_input=f.read_json(f.pin(request['current_input']))
    f.require({k:v for k,v in old_input.items() if k!='project_files'} ==
              {k:v for k,v in new_input.items() if k!='project_files'},'ordinary_recovery_scope_changed')
    a=old_input['project_files']; b=new_input['project_files']
    changed={name for name in set(a)|set(b) if a.get(name)!=b.get(name)}
    f.require(changed=={'scripts/friday_ordinary_install.py'} and set(a)==set(b)
        and b['scripts/friday_ordinary_install.py']==f.digest(f.owned_file(f.ROOT/'scripts/friday_ordinary_install.py')),
        'ordinary_recovery_corrected_host_candidate_required')
    f.require(set(intent.get('before',{}))==set(saved_names(manifest))
        and intent.get('new_files')==[r['path'] for r in manifest['files'] if r['new_file']],
        'ordinary_recovery_beforeimage_scope_changed')
    # Validate the complete retained tree, including absence of untracked files.
    expected=set(intent['before'])
    actual=set()
    for path in before.rglob('*'):
        if path.is_dir(): f.directory(path)
        else:
            f.owned_file(path,private=True); actual.add(str(path.relative_to(before)))
    f.require(actual==expected,'ordinary_recovery_beforeimage_scope_changed')
    for name,row in intent['before'].items():
        f.require(type(row) is dict and set(row)=={'sha256','mode'}
            and type(row['mode']) is int and row['mode'] in (0o600,0o644,0o700,0o755),
            'ordinary_recovery_beforeimage_mode_changed')
        f.require(f.digest(f.owned_file(before/name,private=True))==row['sha256']
            and f.digest(f.owned_file(home/name))==row['sha256']
            and stat.S_IMODE((home/name).stat().st_mode)==row['mode'],
            'ordinary_recovery_beforeimage_changed')
    for name in intent['new_files']:
        f.require(not os.path.lexists(home/'hermes-agent'/name),'ordinary_recovery_new_source_present')
    archive=home/'preparation/ordinary-gateway-archive'/ref['request']['sha256']
    f.require(ref['archive']==str(archive) and not os.path.lexists(archive)
        and not os.path.lexists(archive.with_name(archive.name+'.json')),
              'ordinary_recovery_archive_required')
    if os.path.lexists(archive.parent): f.directory(archive.parent)
    no_consumer(home)
    return archive


def archive_rollback(request, home, manifest):
    f=api(); archive=recovery_checked(request,home,manifest); tx=home/TRANSACTION
    if not archive.parent.exists():
        archive.parent.mkdir(mode=0o700); sync_directory(archive.parent.parent)
    # The retained transaction is never edited or deleted. The sibling receipt
    # and directory rename are durable before the new standard-path journal.
    receipt=archive.with_name(archive.name+'.json')
    f.require(not os.path.lexists(receipt),'ordinary_recovery_archive_required')
    os.rename(tx,archive); sync_directory(archive.parent); sync_directory(tx.parent)
    write(receipt,encoded({'schema':'friday.ordinary-telegram-rollback-archive.v1',
        'state':'ROLLED_BACK_TRANSACTION_RETAINED_NOT_REPLAYED',
        'prior_rolled_back':request['prior_rolled_back'],'archive':str(archive)}))
    sync_directory(archive.parent)


def activate(request, request_path, budget):
    """Journal beforeimages, apply exact layer, publish native marker last.

    Exclusive file lock plus exact rechecks protect this transaction. Before any
    consumer starts, exceptions restore its own bytes; the journal is retained
    and never blindly retried. Ambiguous external service effects are outside
    this source-only action and are handled by the native service handoff.
    """
    f = api()
    home = f.directory(f.canonical(request['home']))
    fd = os.open(home, os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        prepared = inputs(request, budget)
        home, source, paths, previous, current, marker, receipt, manifest, config_raw, cfg = prepared
        f.require(f.read_json(request_path) == request, 'ordinary_request_changed')
        # Read and validate every saved owner/mode before creating any journal.
        names = saved_names(manifest)
        saved = {}; history = {}; beforeimages = {}
        for name in names:
            path=home/name
            data=f.owned_file(path,private=name != 'hermes-agent/install-stamp.json' and not name.startswith('hermes-agent/hermes_cli/'))
            mode=stat.S_IMODE(path.stat().st_mode)
            f.require(mode in (0o600,0o644,0o700,0o755),'ordinary_beforeimage_mode_required')
            beforeimages[name]=data; saved[name]={'sha256':f.digest(data),'mode':mode}
        if request.get('schema') == 'friday.ordinary-telegram-activation.v2':
            archive_rollback(request,home,manifest)
        transaction = home/TRANSACTION
        transaction.mkdir(mode=0o700)
        before = transaction/'before'; before.mkdir(mode=0o700)
        for name in names:
            data = beforeimages[name]
            target = before/name; target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            write(target,data)
            if name == 'FRIDAY-INSTALL.json': history[str(target.relative_to(home))] = f.digest(data)
        for path in home.glob('FRIDAY-INSTALL.*'):
            if path.name != f.MARKER and path.is_file(): history[path.name] = f.digest(f.owned_file(path,private=True))
        write(transaction/'intent.json',encoded({'schema':'friday.ordinary-telegram-transaction.v1',
            'state':'SOURCE_TRANSACTION_STARTED_NOT_RUNTIME','request_sha256':f.digest(f.owned_file(request_path,private=True)),
            'before':saved,'new_files':[r['path'] for r in manifest['files'] if r['new_file']]}))
        touched = []
        try:
            for name,ref in request['credential_files'].items():
                f.require((not os.path.lexists(home/name)) if ref is None else f.digest(f.owned_file(home/name,private=True))==ref['sha256'],'ordinary_credential_pin_changed')
            from scripts.dsh_prepare import run
            apply_env = f.clean_environment(home)
            apply_env['GIT_CEILING_DIRECTORIES'] = str(source.parent)
            for checking in (True,False):
                command = ['git','--no-optional-locks','apply','--whitespace=nowarn']
                if checking: command.append('--check')
                command.append(str(f.ROOT/manifest['patch']))
                run(command, source, timeout=min(20,budget.check(reserve=1)),env=apply_env,deadline=budget.deadline)
            for row in manifest['files']:
                p = source/row['path']; data = f.owned_file(p)
                f.require(f.digest(data) == row['sha256'] and len(data) == row['bytes'], 'ordinary_patch_output_changed')
                receipt['files'][row['path']] = {k:row[k] for k in ('sha256','bytes','mode')}
            receipt['layers'].append({'manifest':MANIFEST,'manifest_sha256':current['project_files'][MANIFEST],
                'patch_sha256':manifest['patch_sha256']})
            f.composition_checked(current,source,receipt, {r['id']:r for r in f.read_json(f.pin(current['sources_lock']))['repositories']}['hermes'])
            plugin_name = 'plugins/friday_rework/onboarding.py'
            f.require(f.digest(f.owned_file(home/plugin_name,private=True)) == previous['project_files'][plugin_name], 'ordinary_installed_plugin_changed')
            replace(home/plugin_name,f.owned_file(f.ROOT/plugin_name),saved[plugin_name]['mode']); touched.append(plugin_name)
            stamp = f.read_json(source/'install-stamp.json')
            stamp['fridaySource'] = {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            for name, data in [('hermes-agent.source.json',encoded(receipt)), ('hermes-agent/install-stamp.json',encoded(stamp)), ('config.yaml',config_raw)]:
                budget.check(); replace(home/name,data); touched.append(name)
            # Reload the changed installed modules in a fresh interpreter at
            # normal launch. This installer uses pure binding helpers only.
            import importlib.util
            spec = importlib.util.spec_from_file_location('_friday_ordinary_binding',source/'hermes_cli/friday_ordinary_gateway.py')
            ordinary = importlib.util.module_from_spec(spec); spec.loader.exec_module(ordinary)
            settings = cfg['plugins']['entries']['friday_rework']['settings']
            binding = {'schema':ordinary.SCHEMA,'scope':'TELEGRAM_RECEIVER_AND_AUTHENTICATED_ONBOARDING_ONLY',
                'configuration_sha256':ordinary.normalized_configuration(cfg),
                'credential_files':{n:(ordinary.credential_identity(home)[0] if n == '.env' else f.digest(f.owned_file(home/n,private=True)) if os.path.lexists(home/n) else None) for n in ('.env','auth.json')},
                'profile_sha256':f.digest(f.owned_file(home/'FRIDAY-PROFILE.json',private=True)),
                'source_receipt_sha256':f.digest(encoded(receipt)),
                'baseline':{'runtime_profiles':settings['product_access']['accounts'][0]['runtime_profiles'],
                            'admin_profiles':settings['admin']['profiles'],'telegram_allowed_users':ordinary.credential_identity(home)[1]}, 'history':history,
                'operator_entry':{'script':{'path':str(f.ROOT/'scripts/friday_native.py'),'sha256':current['project_files']['scripts/friday_native.py']},
                    'input':request['current_input']}}
            updated = dict(marker,completion_stage=ordinary.STAGE,input_sha256=request['current_input']['sha256'],
                source_receipt_sha256=binding['source_receipt_sha256'],ordinary_gateway=binding)
            updated['profile_files'] = dict(marker['profile_files'],**{'config.yaml':f.digest(config_raw)})
            updated['plugin_files'] = dict(marker['plugin_files'],**{plugin_name:current['project_files'][plugin_name]})
            budget.check(); replace(home/f.MARKER,encoded(updated)); touched.append(f.MARKER)
            write(transaction/'committed.json', encoded({'state':'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED','workers_enabled':False,
                'source_receipt_sha256':binding['source_receipt_sha256'],'gateway_started':False}))
            return {'state':'TELEGRAM_ORDINARY_SOURCE_ACTIVATED','ready':False,'workers_enabled':False,'gateway_started':False,
                'ordinary_onboarding':'AUTHENTICATED_NATIVE_API_AND_PAIRING_REQUIRED','full_release_accepted':False}
        except BaseException as original:
            # No service or message effect belongs to this transaction. Restore
            # exact owned beforeimages and only the newly introduced source files.
            try:
                for row in manifest['files']:
                    path = source/row['path']
                    if row['new_file'] and path.exists():
                        f.require(f.digest(f.owned_file(path))==row['sha256'],'ordinary_new_source_ownership_changed')
                        path.unlink()
                for name,row in saved.items():
                    replace(home/name,f.owned_file(before/name,private=True),row['mode'])
                write(transaction/'rolled-back.json',encoded({'state':'ROLLED_BACK_SOURCE_ONLY_NO_RUNTIME_STARTED'}))
            except BaseException as restoration:
                from scripts.dsh_prepare import StopUnconfirmed
                f.remember_secondary(original,restoration)
                raise StopUnconfirmed('ordinary source restoration requires reconciliation') from original
            raise
    finally:
        os.close(fd)


def update_history(home, expected, predecessor=None):
    """Pin the complete original activation transaction and rollback archive."""
    f = api(); actual = {}
    roots = [TRANSACTION, 'preparation/ordinary-gateway-archive']
    if predecessor is not None:
        # This is the already committed 46->47 transaction, never an operation
        # to rerun. Its exact request and all beforeimages remain pinned.
        old = f.read_json(f.pin(predecessor))
        if old.get('schema') == 'friday.ordinary-telegram-source-update.v2':
            # Exact historical47 and48 journals both survive this49 transition.
            actual = update_history(home, old['transaction_history'], old['predecessor_update'])
            roots = []
        f.require(old.get('schema') in ('friday.ordinary-telegram-source-update.v1',
            'friday.ordinary-telegram-source-update.v2'),
            'ordinary_update_exact_predecessor_required')
        f.pin(old['previous_input']); f.pin(old['current_input'])
        name = 'preparation/ordinary-source-update-'+old['previous_input']['sha256']
        tx = f.directory(home/name)
        intent = f.read_json(tx/'intent.json'); committed = f.read_json(tx/'committed.json')
        f.require(intent.get('schema') == 'friday.ordinary-telegram-source-update-transaction.v1'
            and intent.get('state') == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and intent.get('request_sha256') == predecessor['sha256']
            and committed.get('state') == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and committed.get('previous_input') == old['previous_input']
            and committed.get('current_input') == old['current_input']
            and committed.get('gateway_started') is False and committed.get('workers_enabled') is False
            and not os.path.lexists(tx/'rolled-back.json'), 'ordinary_update_committed_predecessor_required')
        roots.append(name)
    for name in roots:
        root = f.directory(home/name)
        for path in root.rglob('*'):
            f.require(not path.is_symlink(), 'ordinary_update_history_link_refused')
            if path.is_dir():
                f.directory(path)
            else:
                actual[str(path.relative_to(home))] = f.digest(f.owned_file(path,private=True))
    f.require(type(expected) is dict and actual == expected
        and TRANSACTION+'/committed.json' in actual, 'ordinary_update_transaction_history_changed')
    f.require(f.read_json(home/TRANSACTION/'committed.json').get('state') ==
        'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED', 'ordinary_update_committed_history_required')
    return actual


def checked_plugin_inventory(home, expected):
    """The installed private package, including all unchanged source files."""
    f = api(); actual = set(); root = f.directory(home/'plugins/friday_rework')
    for path in root.rglob('*'):
        f.require(not path.is_symlink(), 'ordinary_update_plugin_link_refused')
        if path.is_dir():
            f.directory(path)
        else:
            name = str(path.relative_to(home)); actual.add(name)
            f.require(name in expected and f.digest(f.owned_file(path,private=True)) == expected[name],
                'ordinary_update_installed_plugin_changed')
    f.require(actual == set(expected), 'ordinary_update_plugin_inventory_changed')


def update_inputs(request, budget):
    f = api()
    fields = {'schema','seconds','home','previous_input','current_input','marker','source_receipt',
        'stamp','configuration','profile','launcher','credential_files','native_unit','transaction_history'}
    source49 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v3'
    source48 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v2'
    f.require(type(request) is dict and set(request) == fields | ({'predecessor_update'} if source48 or source49 else set())
        and request['schema'] in ('friday.ordinary-telegram-source-update.v1','friday.ordinary-telegram-source-update.v2','friday.ordinary-telegram-source-update.v3')
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180,
        'ordinary_update_explicit_request_required')
    home = f.directory(f.canonical(request['home'])); source = f.directory(home/'hermes-agent')
    f.require(os.environ.get('HERMES_HOME') == str(home), 'ordinary_update_exact_environment_required')
    paths = {name:budget.call(f.pin,request[name]) for name in
        ('previous_input','current_input','marker','source_receipt','stamp','configuration','profile','launcher','native_unit')}
    for name, path in {'marker':home/f.MARKER,'source_receipt':home/'hermes-agent.source.json',
        'stamp':source/'install-stamp.json','configuration':home/'config.yaml',
        'profile':home/'FRIDAY-PROFILE.json','launcher':source/'.hermes/bin/hermes'}.items():
        f.require(paths[name] == path, 'ordinary_update_exact_installed_inputs_required')
    previous = f.read_json(paths['previous_input']); current = f.read_json(paths['current_input'])
    f.require(request['previous_input'] != request['current_input'], 'ordinary_update_new_input_required')
    f.require({k:v for k,v in previous.items() if k != 'project_files'} ==
        {k:v for k,v in current.items() if k != 'project_files'} and current['home'] == str(home),
        'ordinary_update_operational_settings_changed')
    _, donors = budget.call(f.spec_checked,current,cli_only=True)
    marker = f.read_json(paths['marker']); receipt = f.read_json(paths['source_receipt'])
    f.require(marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
        and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
        and marker.get('schema') == f.SCHEMA and marker.get('home') == str(home)
        and marker.get('source') == str(source) and marker.get('runtime_ready') is False
        and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
        and marker.get('input_sha256') == request['previous_input']['sha256']
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and current['product']['runtime'] == {'enabled':False}, 'ordinary_update_committed_phase_required')
    budget.call(f.composition_checked,previous,source,receipt,donors['hermes'])
    manifest_name = FILE_CONTINUATION_MANIFEST if source49 else PRIVATE_STATE_MANIFEST if source48 else UPDATE_MANIFEST
    native_files = FILE_CONTINUATION_FILES if source49 else PRIVATE_STATE_FILES if source48 else UPDATE_FILES
    manifest = json.loads(f.owned_file(f.ROOT/manifest_name),object_pairs_hook=f.unique)
    old = previous['project_files']; new = current['project_files']
    patch = manifest['patch']
    f.require(patch == ('patches/hermes/ordinary-file-continuation.patch' if source49 else 'patches/hermes/ordinary-private-state.patch' if source48 else 'patches/hermes/ordinary-native-repair.patch')
        and set(new) == set(old) | {manifest_name,patch}
        and all(new[name] == pin for name,pin in old.items()
                if name not in ({'scripts/friday_install.py','scripts/friday_ordinary_install.py'} |
                                ({'scripts/friday_start.py'} if source48 else set()) |
                                (WORKER_ATTACH_PLUGIN_FILES if source49 else set()))),
        'ordinary_update_only_reviewed_source_required')
    f.require(manifest.get('base_commit') == receipt['commit']
        and len(receipt['layers']) == (48 if source49 else 47 if source48 else 46) and manifest_name not in {r['manifest'] for r in receipt['layers']}
        and manifest.get('installed_prefix') == {r['manifest']:r['manifest_sha256'] for r in receipt['layers']}
        and new[manifest_name] == f.digest(f.owned_file(f.ROOT/manifest_name))
        and manifest['patch_sha256'] == new[patch] == f.digest(f.owned_file(f.ROOT/patch)),
        'ordinary_update_exact_prefix_required')
    rows = manifest['files']
    f.require(type(rows) is list and len(rows) == len(native_files) and {r['path'] for r in rows} == native_files,
        'ordinary_update_exact_native_files_required')
    for row in rows:
        f.require(row.get('new_file') is False and row.get('mode') == '100644'
            and row['before_sha256'] == receipt['files'][row['path']]['sha256']
            and row['before_sha256'] == f.digest(f.owned_file(source/row['path'])),
            'ordinary_update_source_changed')
    # Reuse the shipped preparer's Git parser before any mutation. An extra
    # patch target must never escape this transaction's five-file rollback.
    from scripts.hermes_prepare import overlay_layers, Budget as SourceBudget
    layers = budget.call(overlay_layers,f.ROOT,receipt['commit'],SourceBudget(budget.deadline))
    f.require(layers[-1][1]['manifest'] == manifest_name,
        'ordinary_update_final_layer_required')
    predecessor = request.get('predecessor_update')
    update_history(home,request['transaction_history'],predecessor)
    if source48 or source49:
        old_request = f.read_json(f.pin(predecessor))
        f.require(old_request['schema'] == ('friday.ordinary-telegram-source-update.v2' if source49
            else 'friday.ordinary-telegram-source-update.v1'), 'ordinary_update_predecessor_version_changed')
        old_tx = home/'preparation'/('ordinary-source-update-'+old_request['previous_input']['sha256'])
        committed = f.read_json(old_tx/'committed.json')
        f.require(old_request['home'] == str(home) and old_request['current_input'] == request['previous_input']
            and committed['source_receipt_sha256'] == request['source_receipt']['sha256'],
            'ordinary_update_predecessor_binding_changed')
    # Complete native identity/configuration/credential validation is reused;
    # no consumed query or historical installer phase is ever invoked.
    f.native_packages(source)
    from hermes_cli.friday_ordinary_gateway import check
    check(home,role=False)
    f.require(all(f.digest(f.owned_file(home/name,private=True)) == pin
        for name,pin in marker['profile_files'].items() if not (source49 and name == 'config.yaml')),
        'ordinary_update_profile_changed')
    if source49:
        before_plugins = {n:p for n,p in previous['project_files'].items() if n.startswith('plugins/friday_rework/')}
        after_plugins = {n:p for n,p in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
        f.require(marker.get('plugin_files') == before_plugins and set(before_plugins) == set(after_plugins)
            and {n for n in before_plugins if before_plugins[n] != after_plugins[n]} == WORKER_ATTACH_PLUGIN_FILES,
            'ordinary_update_exact_worker_plugin_delta_required')
        checked_plugin_inventory(home, before_plugins)
    credentials = request['credential_files']
    f.require(type(credentials) is dict and set(credentials) == {'.env','auth.json'},
        'ordinary_update_credential_pins_required')
    for name,ref in credentials.items():
        f.require(not os.path.lexists(home/name) if ref is None else f.pin(ref) == home/name,
            'ordinary_update_credential_pin_changed')
    tx = home/'preparation'/('ordinary-source-update-'+request['previous_input']['sha256'])
    f.require(not os.path.lexists(tx), 'ordinary_update_consumed_no_retry')
    return home, source, previous, current, marker, receipt, manifest, donors, tx


@contextlib.contextmanager
def stopped_consumers(home, unit_ref, budget):
    """Prove native stop, then retain standard native custody for all three roles."""
    f = api()
    from gateway import host_rendezvous as hr
    from gateway.status import get_running_pid_identity_strict
    from hermes_cli import gateway as gw
    f.require(gw.get_systemd_unit_path(system=False) == f.pin(unit_ref)
        and not os.path.lexists(gw.get_systemd_unit_path(system=True)),
        'ordinary_update_exact_native_user_unit_required')
    runtime = f.directory(Path('/run/user')/str(os.getuid())); bus = runtime/'bus'; info = bus.lstat()
    f.require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
        'ordinary_update_owned_user_bus_required')
    unit = gw.get_service_name()+'.service'
    command = ['/usr/bin/env','XDG_RUNTIME_DIR='+str(runtime),
        'DBUS_SESSION_BUS_ADDRESS=unix:path='+str(bus),'/usr/bin/systemctl','--user','show',unit,
        '--property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID']
    from scripts.dsh_prepare import run
    def prove():
        output = run(command,f.ROOT,timeout=min(15,budget.check(reserve=1)),
            env=f.clean_environment(home),deadline=budget.deadline)[0]
        pairs = [line.split('=',1) for line in output.splitlines() if line]
        f.require(len(pairs) == 6 and all(len(row) == 2 for row in pairs)
            and dict(pairs) == {'Id':unit,'LoadState':'loaded','ActiveState':'inactive',
                'SubState':'dead','MainPID':'0','ControlPID':'0'}, 'ordinary_update_native_stop_required')
        f.require(get_running_pid_identity_strict(home/'gateway.pid') is None,
            'ordinary_update_gateway_pid_present')
        for role in (hr.ROLE_GATEWAY,hr.ROLE_SERVE,hr.ROLE_DESKTOP_SERVE):
            f.require(not os.path.lexists(hr.record_path(role))
                and hr.read_record(role,include_stale=True) is None,
                'ordinary_update_no_native_consumer_required')
    claimed = []
    try:
        prove()
        f.directory(hr.host_state_dir())
        for role in (hr.ROLE_GATEWAY,hr.ROLE_SERVE,hr.ROLE_DESKTOP_SERVE):
            path = hr.lock_path(role)
            f.require(path.parent == hr.host_state_dir() and not hr.owns_host_lock(role),
                'ordinary_update_native_lock_scope_changed')
            before = None
            if os.path.lexists(path):
                f.owned_file(path); info = path.stat(); before = (info.st_dev,info.st_ino)
            outcome,_ = hr.claim_host_lock(role)
            f.require(outcome is hr.HostLockOutcome.ACQUIRED,
                'ordinary_update_native_lock_held_or_unavailable')
            claimed.append(role)
            # Native claim may create its ordinary empty lock; it never
            # publishes a role record or starts a gateway/dashboard consumer.
            f.owned_file(path); info = path.stat()
            f.require(hr.owns_host_lock(role) and (before is None or before == (info.st_dev,info.st_ino)),
                'ordinary_update_native_lock_identity_changed')
        prove()
        yield prove
    finally:
        for role in reversed(claimed): hr.release_host_lock(role)
        f.require(not any(hr.owns_host_lock(role) for role in claimed),
            'ordinary_update_native_lock_release_unconfirmed')


@contextlib.contextmanager
def retained_build_lock(source):
    """Retain the exact existing native build lock; never create or replace it."""
    f = api(); path = source/'.web_ui_build.lock'
    if not os.path.lexists(path):
        yield lambda: f.require(not os.path.lexists(path),'ordinary_update_web_build_lock_appeared')
        return
    f.require(f.owned_file(path) == b'', 'ordinary_update_native_build_lock_required')
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); held = False
    try:
        before = os.fstat(fd)
        def prove():
            current = os.fstat(fd); named = path.lstat()
            fields = ('st_dev','st_ino','st_mode','st_uid','st_nlink','st_size','st_mtime_ns')
            f.require(stat.S_ISREG(current.st_mode) and current.st_uid == os.getuid()
                and current.st_nlink == 1 and current.st_size == 0
                and stat.S_IMODE(current.st_mode) in (0o600,0o644,0o664)
                and all(getattr(before,k) == getattr(current,k) == getattr(named,k) for k in fields),
                'ordinary_update_native_build_lock_changed')
        prove()
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); held = True
        prove(); yield prove
    finally:
        try:
            if held:
                try: prove()
                except BaseException as exc:
                    from scripts.dsh_prepare import StopUnconfirmed
                    raise StopUnconfirmed('native build lock custody requires reconciliation') from exc
        finally: os.close(fd)



def update(request, request_path, budget):
    """One finite committed-phase source update; original activation stays intact."""
    f = api(); home = f.directory(f.canonical(request['home']))
    fd = os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        home,source,previous,current,marker,receipt,manifest,donors,tx = update_inputs(request,budget)
        with stopped_consumers(home,request['native_unit'],budget) as native_prove, retained_build_lock(source) as build_prove:
            def prove(): native_prove(); build_prove()
            f.require(f.read_json(request_path) == request, 'ordinary_update_request_changed')
            # Recheck every explicit pin immediately before the source-only journal.
            update_inputs(request,budget)
            source49 = request['schema'] == 'friday.ordinary-telegram-source-update.v3'
            plugin_changes = sorted(WORKER_ATTACH_PLUGIN_FILES) if source49 else []
            names = [f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'] + [
                'hermes-agent/'+row['path'] for row in manifest['files']] + plugin_changes
            saved = {name:{'data':f.owned_file(home/name),
                'mode':stat.S_IMODE((home/name).stat().st_mode)} for name in names}
            f.require(all(row['mode'] in (0o600,0o644) for row in saved.values()),
                'ordinary_update_beforeimage_mode_required')
            import copy
            receipt = copy.deepcopy(receipt)
            for row in manifest['files']:
                receipt['files'][row['path']] = {k:row[k] for k in ('sha256','bytes','mode')}
            manifest_name = FILE_CONTINUATION_MANIFEST if source49 else PRIVATE_STATE_MANIFEST if request['schema'].endswith('.v2') else UPDATE_MANIFEST
            receipt['layers'].append({'manifest':manifest_name,
                'manifest_sha256':current['project_files'][manifest_name],'patch_sha256':manifest['patch_sha256']})
            stamp = f.read_json(source/'install-stamp.json')
            stamp['fridaySource'] = {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            receipt_data = encoded(receipt); receipt_sha = f.digest(receipt_data)
            updated = copy.deepcopy(marker)
            updated['input_sha256'] = request['current_input']['sha256']
            updated['source_receipt_sha256'] = receipt_sha
            if source49:
                updated['plugin_files'] = {n:p for n,p in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
            updated['ordinary_gateway']['source_receipt_sha256'] = receipt_sha
            updated['ordinary_gateway']['operator_entry'] = {'input':request['current_input'],
                'script':{'path':str(f.ROOT/'scripts/friday_native.py'),
                    'sha256':current['project_files']['scripts/friday_native.py']}}
            publication = [('hermes-agent.source.json',receipt_data),
                ('hermes-agent/install-stamp.json',encoded(stamp)),(f.MARKER,encoded(updated))]
            after = {name:f.digest(data) for name,data in publication}
            after.update({'hermes-agent/'+row['path']:row['sha256'] for row in manifest['files']})
            plugin_data = {name:f.owned_file(f.ROOT/name) for name in plugin_changes}
            f.require(all(f.digest(data) == current['project_files'][name] for name,data in plugin_data.items()),
                'ordinary_update_worker_plugin_source_changed')
            after.update({name:f.digest(data) for name,data in plugin_data.items()})
            tx.mkdir(mode=0o700); before = tx/'before'; before.mkdir(mode=0o700)
            for name,row in saved.items():
                target = before/name; target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                write(target,row['data'])
            write(tx/'intent.json',encoded({'schema':'friday.ordinary-telegram-source-update-transaction.v1',
                'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':f.digest(f.owned_file(request_path,private=True)),
                'before':{name:{'sha256':f.digest(row['data']),'mode':row['mode']} for name,row in saved.items()}}))
            sync_directory(before); sync_directory(tx); sync_directory(tx.parent)
            try:
                prove()
                from scripts.dsh_prepare import run
                env = f.clean_environment(home); env['GIT_CEILING_DIRECTORIES'] = str(source.parent)
                for checking in (True,False):
                    command = ['git','--no-optional-locks','apply','--whitespace=nowarn']
                    if checking: command.append('--check')
                    command.append(str(f.ROOT/manifest['patch']))
                    run(command,source,timeout=min(20,budget.check(reserve=1)),env=env,deadline=budget.deadline)
                for row in manifest['files']:
                    data = f.owned_file(source/row['path'])
                    f.require(f.digest(data) == row['sha256'] and len(data) == row['bytes'],
                        'ordinary_update_patch_output_changed')
                for name,data in plugin_data.items():
                    # Same owned exact-byte private publication used by the native installer.
                    f.require(f.digest(f.owned_file(home/name,private=True)) == f.digest(saved[name]['data']),
                        'ordinary_update_worker_plugin_preimage_changed')
                    replace(home/name,data,saved[name]['mode'])
                if source49:
                    checked_plugin_inventory(home, updated['plugin_files'])
                budget.call(f.composition_checked,current,source,receipt,donors['hermes'])
                for name,data in publication:
                    budget.check(); replace(home/name,data,saved[name]['mode'])
                # The ordinary binding and complete native source identity must
                # agree before the update can commit. No service is launched.
                from hermes_cli.friday_ordinary_gateway import check
                check(home,role=False)
                if source49:
                    checked_plugin_inventory(home, updated['plugin_files'])
                update_history(home,request['transaction_history'],request.get('predecessor_update')); prove(); budget.check()
                write(tx/'committed.json',encoded({'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
                    'previous_input':request['previous_input'],'current_input':request['current_input'],
                    'source_receipt_sha256':receipt_sha,'gateway_started':False,'workers_enabled':False}))
                sync_directory(tx)
                return {'state':'TELEGRAM_ORDINARY_SOURCE_UPDATED','ready':False,'gateway_started':False,
                    'workers_enabled':False,'full_release_accepted':False,'source_receipt_sha256':receipt_sha}
            except BaseException as original:
                try:
                    prove()
                    # Unknown concurrent bytes are never overwritten by rollback.
                    f.require(all(f.digest(f.owned_file(home/name)) in
                        {f.digest(row['data']),after[name]} for name,row in saved.items()),
                        'ordinary_update_restore_ownership_changed')
                    # Restore only this transaction's exact Native/plugin/metadata beforeimages.
                    for name,row in reversed(list(saved.items())):
                        replace(home/name,row['data'],row['mode'])
                    f.require(all(f.digest(f.owned_file(home/name)) == f.digest(row['data'])
                        and stat.S_IMODE((home/name).stat().st_mode) == row['mode'] for name,row in saved.items()),
                        'ordinary_update_restore_failed')
                    update_history(home,request['transaction_history'],request.get('predecessor_update'))
                    write(tx/'rolled-back.json',encoded({'state':'ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'}))
                    sync_directory(tx)
                except BaseException as restoration:
                    from scripts.dsh_prepare import StopUnconfirmed
                    f.remember_secondary(original,restoration)
                    raise StopUnconfirmed('ordinary source update restoration requires reconciliation') from original
                raise
    finally:
        os.close(fd)


def start(value,input_path,input_hash,budget):
    """Re-exec the exact native PM generation for the ordinary service handoff."""
    f = api()
    home,donors = budget.call(f.spec_checked,value,cli_only=True)
    marker = budget.call(f.read_json,home/f.MARKER)
    f.require(marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
        and marker.get('input_sha256') == input_hash
        and f.digest(f.owned_file(input_path,private=True)) == input_hash,
        'ordinary_current_installation_required')
    source = home/'hermes-agent'
    f.composition_checked(value,source,f.read_json(home/'hermes-agent.source.json'),donors['hermes'])
    from scripts.install_containment import Containment
    custody = Containment(value['containment'],budget,f.clean_environment(home))
    selected = custody.run([value['bootstrap_python']['path'],'-B','-c',
        'from pm.environments import project_python;from pathlib import Path;print(project_python(Path.cwd()))'],
        source,timeout=15)[0]
    f.require(Path(selected).is_absolute() and Path(selected).is_file(),'native_pm_python_missing')
    budget.check()
    os.execve(selected,[selected,'-B',str(f.ROOT/'scripts/friday_native.py'),'start-telegram',
        '--input',str(input_path),'--deadline',str(budget.deadline)],f.clean_environment(home))


def rollback(request,budget):
    """Restore this transaction only after native stop/uninstall is proved.

    Product/user/session data are retained. Unknown service ownership or changed
    beforeimages refuse restoration; this is never a gateway stop/retry command.
    """
    f=api()
    f.require(type(request) is dict and set(request)=={'schema','seconds','home','current_input'}
        and request['schema']=='friday.ordinary-telegram-rollback.v1'
        and type(request['seconds']) is int and 30<=request['seconds']<=180,'ordinary_rollback_request_required')
    home=f.directory(f.canonical(request['home']));source=home/'hermes-agent'
    value=f.read_json(f.pin(request['current_input']));f.spec_checked(value,cli_only=True)
    marker=f.read_json(home/f.MARKER)
    f.require(marker.get('completion_stage')=='TELEGRAM_ORDINARY'
        and marker.get('input_sha256')==request['current_input']['sha256'],'ordinary_rollback_current_source_required')
    donors={r['id']:r for r in f.read_json(f.pin(value['sources_lock']))['repositories']}
    f.composition_checked(value,source,f.read_json(home/'hermes-agent.source.json'),donors['hermes'])
    f.native_packages(source)
    from gateway import host_rendezvous as hr
    from hermes_cli import gateway as gw
    f.require(not gw.get_systemd_unit_path(system=False).exists()
        and not gw.get_systemd_unit_path(system=True).exists()
        and hr.read_record(hr.ROLE_GATEWAY,include_stale=True) is None
        and not gw.find_gateway_pids(),'ordinary_rollback_native_stop_and_uninstall_required')
    tx=home/TRANSACTION;before=tx/'before';intent=f.read_json(tx/'intent.json')
    committed=f.read_json(tx/'committed.json')
    f.require(committed['state']=='SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'
        and not os.path.lexists(tx/'source-rollback.intent.json'),'ordinary_rollback_once_required')
    manifest=f.read_json(f.ROOT/MANIFEST)
    expected={'FRIDAY-INSTALL.json','hermes-agent.source.json','config.yaml','hermes-agent/install-stamp.json',
              'plugins/friday_rework/onboarding.py'}|{'hermes-agent/'+r['path'] for r in manifest['files'] if not r['new_file']}
    f.require(set(intent['before'])==expected and intent['new_files']==[r['path'] for r in manifest['files'] if r['new_file']],
        'ordinary_rollback_scope_changed')
    for name,row in intent['before'].items():
        f.require(f.digest(f.owned_file(before/name,private=True))==row['sha256'], 'ordinary_rollback_beforeimage_changed')
    fd=os.open(home,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        budget.check()
        rollback_before=tx/'rollback-before';rollback_before.mkdir(mode=0o700)
        retained={}
        for name in ('config.yaml','FRIDAY-INSTALL.json'):
            raw=f.owned_file(home/name,private=True);write(rollback_before/name,raw);retained[name]={'path':str(rollback_before/name),'sha256':f.digest(raw)}
        write(tx/'source-rollback.intent.json',encoded({'state':'CONSUMED_SOURCE_ROLLBACK','retained_current_configuration':retained}))
        for row in manifest['files']:
            if row['new_file']:
                budget.check();(source/row['path']).unlink()
        for name,row in intent['before'].items():
            if name==f.MARKER:continue
            budget.check();replace(home/name,f.owned_file(before/name,private=True),row['mode'])
        row=intent['before'][f.MARKER];replace(home/f.MARKER,f.owned_file(before/f.MARKER,private=True),row['mode'])
        f.require(all(f.digest(f.owned_file(home/name))==row['sha256'] for name,row in intent['before'].items()),'ordinary_rollback_verification_failed')
        write(tx/'source-rollback.done.json',encoded({'state':'SOURCE_ROLLED_BACK','runtime_data_retained':True}))
        return {'state':'ORDINARY_SOURCE_ROLLED_BACK','ready':False,'runtime_data_retained':True}
    finally:os.close(fd)
