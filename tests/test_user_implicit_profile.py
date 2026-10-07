"""Implicit source profiles over actual native admission, worker and result glue.
Synthetic systemd/notification/document boundaries only; no child process or live send.
"""
import asyncio, contextvars, copy, hashlib, importlib, json, shutil, sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_user_isolation import users
from test_user_retained_repair import update, fresh
from test_admin_foundation import ROOT
from hermes_cli import friday_user_scope as scope
from hermes_cli.plugins_state import PluginState
from hermes_cli.friday_product_access import KEY, current_access

@pytest.fixture
def wired(users, monkeypatch, request):
    from gateway.session import SessionSource
    from gateway.config import Platform
    from gateway.session_identity import RoutingIdentity
    source_profile, transport = getattr(request, "param", (None, 'default'))
    primary_source, primary_home = users.sources[0], users.homes[0]
    runtime_profile, account = 'user-1', 'bot-A'
    authorization_home = users.root
    if transport != 'default':
        runtime_profile, account = 'user-remote', 'bot-B'
        binding = {**users.bindings[0], 'transport_profile': transport,
                   'account_id': account, 'runtime_profile': runtime_profile}
        authorization_home = users.root / 'profiles' / transport
        authorization_home.mkdir(mode=0o700)
        configuration = {'plugins': {'entries': {'friday_rework': {'settings': {
            'user_isolation': {'enabled': True, 'bindings': [binding]},
            'product_access': {'enabled': True, 'accounts': [dict(platform='telegram',
                transport_profile=transport, account_id=account, runtime_profiles=[runtime_profile])]}}}}}}
        (authorization_home / 'config.yaml').write_text(json.dumps(configuration))
        (authorization_home / 'config.yaml').chmod(0o600)
        from friday_admin_controls.access import ProductAccess
        with scope.authority(authorization_home):
            ProductAccess(PluginState('friday_rework')).set_user(platform='telegram',
                transport_profile=transport, account_id=account, user_id='1', enabled=True, role='user')
        users.homes[0] = scope.provision_new_home(authorization_home, binding, {'max_iterations': 8})
    if source_profile == 'runtime':
        source_profile = runtime_profile
    source = SessionSource(Platform.TELEGRAM, 'shared-chat', user_id='1', chat_type='group',
                           thread_id='same-topic', profile=source_profile)
    source._identity = RoutingIdentity(transport, runtime_profile, authorization_home, users.homes[0])
    assert users.gateway._principal_authorized(source, allow_adapter_delegation=True)
    users.sources[0] = source
    source_profile = source_profile or ''
    from hermes_cli import plugins
    from tools.registry import registry
    with users.enter(0):
        home=users.homes[0]
        destination=home/'plugins/friday_rework'
        shutil.copytree(ROOT,destination,ignore=shutil.ignore_patterns('__pycache__'))
        monkeypatch.setattr(plugins,'get_bundled_plugins_dir',lambda:home/'empty')
        monkeypatch.setattr(plugins.PluginManager,'_scan_entry_points',lambda self:[])
        paths=[home/n for n in ('jobs','staging','cache','payload','toolchain')]
        for p in paths:p.mkdir(mode=0o700)
        jobs,staging,cache,payload,toolchain=paths
        def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        (payload/'apps/cli/lib').mkdir(parents=True, mode=0o700)
        node,cli,patch,nativefile=toolchain/'node',payload/'apps/cli/lib/bin.js',home/'local.yml',payload/'native.js'
        for p in (node,cli,patch,nativefile):p.write_bytes(b'INDEPENDENT SYNTHETIC PIN; NEVER EXECUTED');p.chmod(0o600)
        runtime=dict(enabled=True,runtime_profile=runtime_profile,runtime_home=str(home),workspace_root=str(jobs),staging_root=str(staging),
            cache_roots=[str(cache)],budget_seconds=60,max_file_bytes=1024,max_total_bytes=4096,
            dsh=dict(payload_root=str(payload),toolchain_root=str(toolchain),node=pin(node),cli=pin(cli),patch=pin(patch),native_files=[pin(nativefile)],
                key_name='UNUSED_SYNTHETIC_KEY',profile='headless',memory_bytes=2*1024**3,cpu_percent=200,tasks=64,shutdown_seconds=2,tmp_bytes=64*1024**2))
        from friday_admin_controls.host_record import digest
        evidence=home/'proof.json';evidence.write_text('{"synthetic_offline_admission":true}')
        receipt=home/'receipt.json';receipt.write_text(json.dumps(dict(schema='friday-rework.dsh-runtime.v1',ready=True,
            runtime_sha256=digest(runtime),adapter_sha256=pin(destination/'adapters/dsh.py')['sha256'],evidence=[pin(evidence)])))
        runtime['runtime_receipt']=pin(receipt)
        configuration={'plugins':{'enabled':['friday_rework'],'entries':{'friday_rework':{'allow_gateway_work':True,
            'allow_gateway_control':True,'settings':{'runtime':runtime,'results':{'enabled':True}}}}}}
        (home/'config.yaml').write_text(json.dumps(configuration));(home/'config.yaml').chmod(0o600)
        manager=plugins.PluginManager(scope_key=str(home));manager.discover_and_load()
        assert manager._plugins['friday_rework'].enabled,manager._plugins['friday_rework'].error
        monkeypatch.setattr(plugins,'get_plugin_manager',lambda:manager)
        entry=registry.get_entry('friday_work',scope=manager.scope_key);host=entry.handler.__self__
        scheduled=[]
        def schedule(coro,**kwargs):scheduled.append(kwargs);coro.close()
        monkeypatch.setattr(host.ctx,'schedule_gateway_work',schedule)
        package=manager._plugins['friday_rework'].module.__name__
        admission=importlib.import_module(package+'.admission')
        result=importlib.import_module(package+'.result_tool')
        assert admission.native_call_scope in manager._middleware['tool_execution']
        fields=dict(PLATFORM='telegram',CHAT_ID='shared-chat',CHAT_TYPE='group',THREAD_ID='same-topic',USER_ID='1',
            KEY='independent-key',ID='independent-session',MESSAGE_ID='independent-message',PROFILE=source_profile)
        variables=[contextvars.ContextVar('HERMES_SESSION_'+k) for k in fields]
        tokens=[v.set(fields[k]) for v,k in zip(variables,fields)]
        import weakref
        from dataclasses import replace
        from gateway.admitted_ingress import admitted_ingress
        from gateway.run_plugin_commands import _receipt
        message=dict(bot_id=account,user_id='1',chat_id='shared-chat',thread_id='same-topic',message_id=fields['MESSAGE_ID'],
            platform_update_id='independent-update',reply_to_message_id='',media=[])
        class Adapter:
            def message_provenance(self, event): return copy.deepcopy(message)
        adapter=Adapter()
        native_source=users.sources[0]
        native_source._identity=replace(native_source._identity, transport=weakref.ref(adapter))
        event=SimpleNamespace(internal=False, allow_gateway_control=True, source=native_source, message_id=fields['MESSAGE_ID'])
        runner=SimpleNamespace(_intake_adapter_for=lambda source:adapter, _session_key_for_source=lambda source:fields['KEY'])
        ingress={**admitted_ingress(event,native_source,fields['KEY']), 'chat_type':native_source.chat_type}
        # Use the real post-admission callback registration and receipt writer.
        source=dict(user_id='1',chat_id='shared-chat',thread_id='same-topic',message_id=fields['MESSAGE_ID'],profile=source_profile,chat_type='group')
        for callback in manager._hooks['post_gateway_admission']:
            callback(admitted_ingress=ingress,session_key=fields['KEY'],message_id=fields['MESSAGE_ID'],platform='telegram',source=source)
        call=dict(task_id=fields['ID'],session_id=fields['ID'],turn_id='independent-turn',api_request_id='independent-api',tool_call_id='work-call')
        args=dict(worker='dsh',brief='Independent native admission',goal_check='Check owned original admission without worker execution')
        from model_tools import handle_function_call
        def invoke(name,args,**options):
            identity=options.pop('call',call)
            return json.loads(handle_function_call('tool_call',{'calls':[{'name':name,'arguments':args}]},
                **identity,enabled_toolsets=['friday_rework'],**options))
        value=SimpleNamespace(users=users,host=host,manager=manager,admission=admission,result=result,scheduled=scheduled,
            call=call,args=args,invoke=invoke,ingress=ingress,fields=fields,variables=variables,package=package,
            receipt=lambda command:_receipt(runner,event,native_source,command),
            primary_source=primary_source,primary_home=primary_home)
        from agent.secret_scope import set_secret_scope, reset_secret_scope
        secret_token=set_secret_scope({"UNUSED_SYNTHETIC_KEY": "offline-fixture-only"}, profile_home=str(home))
        try:yield value
        finally:
            reset_secret_scope(secret_token)
            for variable,token in zip(variables,tokens):variable.reset(token)
            # Real manager unload closes the host; the same scheduler boundary
            # closes any cleanup coroutine. No actual worker ever existed.
            manager.unload()
            assert not host._a0_controllers


def offline_execution(w, monkeypatch):
    """Keep the real controller/adapter; replace only native effects."""
    import subprocess
    host_module = importlib.import_module(w.package + '.host')
    supervisor_module = importlib.import_module(w.package + '.supervision')
    observed = SimpleNamespace(launches=[], notifications=[], sends=[], units={})
    invocation = 'a' * 32

    class Supervisor:
        description = staticmethod(supervisor_module.NativeSupervisor.description)

        def observe(self, row):
            present = row['supervisor']['unit'] in observed.units
            if row['native']:
                assert row['native']['invocation_id'] == invocation
            return supervisor_module.UnitObservation(row['supervisor']['unit'], invocation if present else '',
                'inactive', 'dead', 'success', 0, '', False, not present)

        def stop(self, row):
            return self.observe(row)

    for name in ('host', 'host_runtime', 'supervision', 'adapters.dsh'):
        monkeypatch.setattr(importlib.import_module(w.package + '.' + name), 'NativeSupervisor', Supervisor)
    home = w.users.homes[0]
    (home / '.env').write_text('UNUSED_SYNTHETIC_KEY=offline-fixture-only\n')
    (home / '.env').chmod(0o600)

    def launch(argv, **kwargs):
        assert argv[0] == '/usr/bin/systemd-run'
        assert kwargs['env']['UNUSED_SYNTHETIC_KEY'] == 'offline-fixture-only'
        unit = next(a.split('=', 1)[1] for a in argv if a.startswith('--unit='))
        row = next(r for r in w.host.store.snapshot().values() if r['supervisor']['unit'] == unit)
        assert row['submission_observation'] == 'UNKNOWN'
        observed.launches.append(argv); observed.units[unit] = True
        control = Path(row['workspace_reference']) / '.dsh-adapter'
        events = [dict(type='session', sessionId='session-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', cwd='/workspace'),
                  dict(type='status', phase='turn_start', turn=1),
                  dict(type='status', phase='turn_end', turn=1, reason={'kind': 'completed'}),
                  dict(type='final', text='UNTRUSTED OFFLINE FIXTURE')]
        (control / 'events.ndjson').write_text(''.join(json.dumps(e) + '\n' for e in events))
        (control / 'terminal.json').write_text(json.dumps(dict(INVOCATION_ID=invocation,
            SERVICE_RESULT='success', EXIT_CODE='exited', EXIT_STATUS='0')))
        return subprocess.CompletedProcess(argv, 0, b'', ('invocation ID: ' + invocation + '\n').encode())

    def inject(content, **kwargs):
        observed.notifications.append((json.loads(content), kwargs))
        return True

    async def send(**kwargs):
        observed.sends.append(kwargs)
        row = next(iter(w.host.store.snapshot().values()))
        assert row['delivery'] == 'UNKNOWN'
        result_module = importlib.import_module(w.package + '.results')
        return {'state': 'DELIVERED', **result_module._expected_receipt(row, row['result']['artifacts'][0]),
                'message_id': '601'}

    monkeypatch.setattr(subprocess, 'run', launch)
    monkeypatch.setattr(w.host.ctx, 'inject_message', inject)
    monkeypatch.setattr(w.host.ctx, 'deliver_gateway_document', send)
    return observed


ROUTES = [(profile, transport) for profile in (None, '', 'runtime')
          for transport in ('default', 'receiver-b')]


@pytest.mark.parametrize('wired', ROUTES, indirect=True)
def test_actual_owned_lifecycle_preserves_distinct_profiles(wired, monkeypatch):
    w = wired; observed = offline_execution(w, monkeypatch)
    reply = w.invoke('friday_work', w.args)
    assert reply['accepted'] and len(w.scheduled) == 1
    original = w.host.store.snapshot()[reply['reference']]
    assert w.invoke('friday_work', w.args) == reply
    assert w.invoke('friday_result', {'action': 'status', 'reference': reply['reference']})['accepted']
    row = w.host._start(original)  # Real WorkerHost, controller, adapter and native store.
    assert row['host']['terminal']['state'] == 'completed' and row['host']['quiescence']
    assert len(observed.launches) == 1
    original_fields = ('owner', 'created_at_unix', 'budget_seconds', 'deadline_unix', 'stop_intent')
    assert all(row[k] == original[k] for k in original_fields)
    assert row['host']['binding'] == original['host']['binding']
    assert row['owner']['profile'] == scope.current().profile
    assert row['host']['binding']['ingress']['source_profile'] == (w.users.sources[0].profile or '')
    if not w.users.sources[0].profile:
        assert row['owner']['profile'] != row['host']['binding']['ingress']['source_profile']

    async def notify():
        await w.result.notify_finished(w.host, row)
        await w.result.notify_finished(w.host, row)
    asyncio.run(notify())
    assert len(observed.notifications) == 1
    assert observed.notifications[0][1] == {'session_key': row['owner']['session_key'],
                                           'expected_session_id': row['owner']['session_id']}
    workspace = Path(row['workspace_reference']) / 'workspace'
    (workspace / 'answer.txt').write_text('owned offline result\n')
    common = {'reference': row['existing_task_id']}
    assert w.invoke('friday_result', {**common, 'action': 'list'})['files'][0]['path'] == 'answer.txt'
    inspected = w.invoke('friday_result', {**common, 'action': 'inspect', 'paths': ['answer.txt']})
    assert inspected['accepted'] and inspected['artifacts'][0]['preview'] == 'owned offline result\n'
    assert w.invoke('friday_result', {**common, 'action': 'deliver'})['delivery_requested']
    retained = w.host.store.snapshot()[row['existing_task_id']]
    assert asyncio.run(w.result.ResultTool(w.host).deliver(retained)) == 'DELIVERED'
    retained = w.host.store.snapshot()[row['existing_task_id']]
    assert asyncio.run(w.result.ResultTool(w.host).deliver(retained)) == 'DELIVERED'
    assert len(observed.sends) == 1 and observed.sends[0]['data'] == b'owned offline result\n'
    route = observed.sends[0]['route']
    assert route == w.admission.delivery_route(original['host']['binding']['ingress'])
    assert route['transport_profile'] == scope.current().principal[1]
    assert route['runtime_profile'] == scope.current().profile
    assert route['bot_id'] == scope.current().principal[2]
    final = w.host.store.snapshot()[row['existing_task_id']]
    assert final['notification']['state'] == 'OBSERVED'
    assert final['goal_verification'] == 'NOT_RUN'
    assert all(final[k] == original[k] for k in original_fields)
    assert final['host']['binding'] == original['host']['binding']
    assert w.invoke('friday_work', w.args)['accepted'] and len(observed.launches) == 1
    assert len(w.scheduled) == 2  # Original work and explicit delivery; no duplicate work.


@pytest.mark.parametrize('wired', [(None, 'default'), ('', 'receiver-b')], indirect=True)
@pytest.mark.parametrize('field,value', [
    ('source_profile', 'default'), ('source_profile', 'user-2'), ('source_profile', None),
    ('transport_profile', ''), ('transport_profile', 'unknown'), ('runtime_profile', 'default'),
    ('runtime_profile', 'user-2'), ('bot_id', 'foreign-bot'), ('user_id', '2'),
    ('owner_profile', ''), ('owner_profile', 'default'), ('owner_profile', 'user-2'),
    ('owner_bot', 'foreign-bot'), ('authority', None), ('generation', 999)])
def test_retained_join_does_not_guess_or_merge_authority(wired, field, value):
    w = wired
    reply = w.invoke('friday_work', w.args); assert reply['accepted']
    original = w.host.store.snapshot()[reply['reference']]
    forged = copy.deepcopy(original); binding = forged['host']['binding']
    if field == 'owner_profile': forged['owner']['profile'] = value
    elif field == 'owner_bot': forged['owner']['bot_id'] = value
    elif field == 'authority': binding.pop('user_authority')
    elif field == 'generation': binding['user_authority']['generation'] = value
    elif field in ('bot_id', 'user_id'): binding['ingress']['message'][field] = value
    else: binding['ingress'][field] = value
    with pytest.raises(scope.ScopeDenied): scope.check_retained_job(forged)
    assert w.host.store.snapshot()[reply['reference']] == original
    assert w.invoke('friday_result', {'action': 'status', 'reference': reply['reference']})['accepted']


@pytest.mark.parametrize('wired', [(None, 'default'), ('', 'default')], indirect=True)
def test_implicit_job_revocation_denies_start_result_notification_delivery(wired, monkeypatch):
    w = wired; observed = offline_execution(w, monkeypatch)
    reply = w.invoke('friday_work', w.args); original = w.host.store.snapshot()[reply['reference']]
    update(w.users, enabled=False); update(w.users)
    token = scope._CURRENT.set(None)
    try:
        fresh(w.users)
        with scope.scoped_source(w.users.sources[0]):
            assert not w.invoke('friday_work', w.args)['accepted']
            assert not w.invoke('friday_result', {'action': 'status', 'reference': reply['reference']})['accepted']
            with pytest.raises(scope.ScopeDenied): w.host._start(original)
            with pytest.raises(scope.ScopeDenied): asyncio.run(w.result.notify_finished(w.host, original))
            retained = copy.deepcopy(original)
            retained['result'] = {'artifacts': [{'reference': 'synthetic-output'}]}
            with pytest.raises(scope.ScopeDenied): asyncio.run(w.result.ResultTool(w.host).deliver(retained))
            assert not observed.launches and not observed.notifications and not observed.sends
            assert w.host.store.snapshot()[reply['reference']] == original
            # Exact owned stop remains available; no fresh budget or re-admission.
            from hermes_cli.plugin_command_context import _command_context
            receipt = w.receipt('friday-stop')
            assert receipt['source']['profile'] == original['owner']['profile']
            assert receipt['admitted_ingress']['source_profile'] == ''
            with _command_context(w.host.ctx, receipt):
                assert json.loads(w.host.control('friday-stop', reply['reference']))['accepted']
            stopped = w.host.store.snapshot()[reply['reference']]
            assert stopped['deadline_unix'] == original['deadline_unix']
            assert stopped['host']['binding'] == original['host']['binding']
    finally:
        scope._CURRENT.reset(token)


@pytest.mark.parametrize('wired', [(None, 'default'), ('', 'receiver-b')], indirect=True)
@pytest.mark.parametrize('field,value', [('PROFILE', 'default'), ('PROFILE', 'user-2'),
    ('USER_ID', '2'), ('CHAT_ID', 'foreign-chat'), ('THREAD_ID', 'foreign-topic'),
    ('KEY', 'foreign-key'), ('ID', 'foreign-session')])
def test_implicit_job_rejects_foreign_ambient_call(wired, field, value):
    w = wired
    reply = w.invoke('friday_work', w.args); assert reply['accepted']
    original = w.host.store.snapshot()[reply['reference']]
    variable = next(v for v in w.variables if v.name == 'HERMES_SESSION_' + field)
    token = variable.set(value)
    try:
        assert not w.invoke('friday_work', w.args)['accepted']
        assert not w.invoke('friday_result', {'action': 'status', 'reference': reply['reference']})['accepted']
    finally:
        variable.reset(token)
    assert len(w.scheduled) == 1 and w.host.store.snapshot()[reply['reference']] == original
    assert w.invoke('friday_result', {'action': 'status', 'reference': reply['reference']})['accepted']


@pytest.mark.parametrize('profile', ['default', 'user-2', 'unknown'])
def test_explicit_source_profile_cannot_replace_native_runtime(users, profile):
    source = users.sources[0]
    source.profile = profile
    with pytest.raises(scope.ScopeDenied):
        with users.enter(0):
            pytest.fail('foreign source profile entered native runtime scope')


@pytest.mark.parametrize('wired', [(None, 'receiver-b'), ('', 'receiver-b')], indirect=True)
def test_same_user_id_other_receiving_account_cannot_adopt_retained_job(wired):
    w = wired
    reply = w.invoke('friday_work', w.args); assert reply['accepted']
    row = w.host.store.snapshot()[reply['reference']]
    own = scope.current()
    token = scope._CURRENT.set(None)
    try:
        with scope.authority(w.primary_home), scope.scoped_source(w.primary_source) as other:
            assert other.principal[3] == own.principal[3] == '1'
            assert other.key != own.key and other.principal[1:3] != own.principal[1:3]
            with pytest.raises(scope.ScopeDenied): scope.check_retained_job(row)
    finally:
        scope._CURRENT.reset(token)
    assert w.host.store.snapshot()[reply['reference']] == row
    assert w.invoke('friday_result', {'action': 'status', 'reference': reply['reference']})['accepted']
