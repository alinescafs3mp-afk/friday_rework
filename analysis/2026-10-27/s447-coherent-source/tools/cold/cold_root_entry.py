# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.

def native_basic_settings(read,basic):
    """Existing native R488 composition; only three exact private auth keys."""
    import os
    from agent import secret_scope
    env={'path':'<INSTALL_HOME>/.env','sha256':'PRIVATE_REF_c380935e1e528f26'}
    parser={'path':'<INSTALL_HOME>/hermes-agent/agent/secret_scope.py','sha256':'PRIVATE_REF_9de6d4904661fb93'}
    if secret_scope.__file__!=parser['path']:raise RuntimeError('actual_native_auth_parser_required')
    read(parser,private=False)
    configured=secret_scope._parse_env_text(secret_scope._decode_env_bytes(read(env)))
    required=('HERMES_DASHBOARD_BASIC_AUTH_USERNAME','HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH','HERMES_DASHBOARD_BASIC_AUTH_SECRET')
    controlled=(*required,'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD')
    previous={name:os.environ.get(name) for name in controlled}
    try:
        if not all(type(configured.get(name)) is str and configured[name] for name in required):raise RuntimeError('configured_native_auth_keys_required')
        for name in required:os.environ[name]=configured[name]
        os.environ.pop('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD',None)
        return basic._settings()
    finally:
        for name,value in previous.items():
            if value is None:os.environ.pop(name,None)
            else:os.environ[name]=value
        configured.clear()

"""Future Root one-shot, executed by the installed lexical native PM.
ROOT_RUN remains None in the delivered source. This file is never run by Sol.
"""
ROOT_RUN = None

def main():
    import hashlib,importlib.util,json,math,os,signal,stat,sys,time
    from pathlib import Path
    def need(ok,code):
        if not ok: raise RuntimeError(code)
    def read(ref,private=True):
        need(type(ref) is dict and set(ref)=={'path','sha256'},'exact_reference_required')
        p=Path(ref['path']);need(p.is_absolute() and p.resolve()==p,'canonical_reference_required')
        for parent in p.parents:
            s=parent.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid in (0,os.getuid())
                and not s.st_mode&0o022,'protected_parent_required')
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_uid==os.getuid() and a.st_gid==os.getegid()==12345 and a.st_nlink==1
                and not a.st_mode&0o002 and (not private or not a.st_mode&0o077),'protected_file_required')
            raw=os.pread(fd,16*1024**2+1,0);b=os.fstat(fd);c=p.lstat()
            fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
            need(len(raw)<=16*1024**2 and all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in fields)
                and hashlib.sha256(raw).hexdigest()==ref['sha256'],'reference_changed')
            return raw
        finally:os.close(fd)
    def document(ref):
        def unique(rows):
            result={}
            for k,v in rows:need(k not in result,'duplicate_key');result[k]=v
            return result
        return json.loads(read(ref),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    need(type(ROOT_RUN) is dict and set(ROOT_RUN)=={'request'},'unbound_runner')
    request=document(ROOT_RUN['request'])
    need(set(request)=={'schema','native_source','python','launch_home','dashboard_api','installed_join',
        'native_refs','marker','credential_ref','credential_keys','original_clock','once_grant',
        'operation_directory','target','native_request','native_receipt','predecessor_closure','source_acceptance'}
        and request['schema']=='friday.a0-closed-s443-successor-root-once.v1','exact_root_request_required')
    need(type(request['target']) is dict and set(request['target'])=={'profile','expected_config_sha256',
        'generation','platform','transport_profile','account_id','user_id'},'exact_target_required')
    clock=document(request['original_clock']); body={k:v for k,v in request.items() if k!='once_grant'}
    need(document(request['once_grant'])=={'schema':'friday.a0-closed-s443-successor-root-once-grant.v1',
        'request_body_sha256':hashlib.sha256((json.dumps(body,sort_keys=True,allow_nan=False)+'\n').encode()).hexdigest(),
        'operation':'MISSING_COLD_AFTER_CLOSED_S443','retry_authorized':False},'exact_once_grant_required')
    need(set(clock)=={'schema','boot_id','started_monotonic','deadline_monotonic','budget_seconds','reserve_seconds'}
        and clock['schema']=='friday.a0-closed-s443-successor-clock.v1'
        and clock['budget_seconds']==600 and clock['reserve_seconds']==30
        and all(type(clock[k]) in (int,float) and math.isfinite(clock[k]) for k in ('started_monotonic','deadline_monotonic'))
        and clock['deadline_monotonic']==clock['started_monotonic']+600,'future_original_clock_required')
    def check():
        need(clock['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and 0<clock['started_monotonic']<=time.monotonic()<clock['deadline_monotonic']-30,
            'original_clock_exhausted_or_wrong_boot')
    check()
    need(sys.flags.isolated and sys.dont_write_bytecode and sys.executable==request['python'],
         'lexical_native_interpreter_required')
    H=Path('<INSTALL_HOME>')
    source=H/'hermes-agent'
    need(request['launch_home']==str(H) and request['native_source']==str(source)
        and request['dashboard_api']['path']==str(H/'plugins/friday_rework/dashboard/api.py')
        and request['installed_join']['path']==str(H/'plugins/friday_rework/user_worker_join.py')
        and request['marker']['path']==str(H/'FRIDAY-INSTALL.json'),'exact_native_graph_required')
    marker=document(request['marker'])
    need(marker['plugin_files']['plugins/friday_rework/user_worker_join.py']==request['installed_join']['sha256']
        and marker['plugin_files']['plugins/friday_rework/dashboard/api.py']==request['dashboard_api']['sha256'],
        'installed_marker_source_join_required')
    read(request['dashboard_api']);read(request['installed_join'])
    for ref in request['native_refs']: read(ref,private=False)
    sys.path.insert(0,str(source))
    from hermes_constants import get_process_hermes_home,get_routing_process_hermes_home
    need(get_process_hermes_home()==H and get_routing_process_hermes_home()==H,'native_launch_home_required')
    from hermes_cli.friday_dashboard_owner import source_identity
    source_identity(H,source=source)
    import plugins
    need(Path(plugins.__file__).resolve()==source/'plugins/__init__.py','native_plugins_required')
    name='hermes_dashboard_plugin_friday_rework'
    need(name not in sys.modules and '_friday_dashboard_projection' not in sys.modules,'fresh_process_required')
    spec=importlib.util.spec_from_file_location(name,request['dashboard_api']['path'])
    api=importlib.util.module_from_spec(spec);sys.modules[name]=api;spec.loader.exec_module(api)
    from _friday_dashboard_projection.admin import Administration
    from _friday_dashboard_projection.onboarding import Onboarding
    from _friday_dashboard_projection import user_worker_join as join
    from _friday_dashboard_projection.runtime_containment import Budget
    from hermes_cli import friday_user_scope as scope
    from hermes_cli.friday_product_access import admin_policy,session_allowed
    from hermes_cli.dashboard_auth.registry import get_provider,register_global_provider,unregister_global_provider
    from plugins.dashboard_auth import basic
    need(Path(join.__file__).resolve()==Path(request['installed_join']['path'])
        and scope._CURRENT.get() is None and get_provider('basic') is None,'fresh_genuine_operator_graph_required')
    read(request['installed_join']);read(request['marker']);check()
    # Fail before any one-shot claim or authentication effect on source/closure drift.
    join._s447_cold_request(ROOT_RUN['request'])
    operation=Path(request['operation_directory'])
    need(operation.is_absolute() and operation.resolve()==operation and str(operation)==request['operation_directory']
        and operation==Path('<PRIVATE_CACHE>/PRIVATE_REF_79d2ca6c48dd51a8'),
        'exact_Root_private_operation_required')
    scope._private(operation,directory=True)
    intent=operation/'runner-intent.json'
    fd=os.open(intent,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        raw=(json.dumps({'schema':'friday.a0-closed-s443-successor-root-intent.v1','request':ROOT_RUN['request'],
            'clock':request['original_clock'],'retry_authorized':False},sort_keys=True)+'\n').encode()
        with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fsync(fd)
    finally:os.close(fd)
    directory_fd=os.open(operation,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(directory_fd)
    finally:os.close(directory_fd)
    provider=basic.BasicAuthProvider(**native_basic_settings(read,basic));minted=None;registered=False;login_started=False
    result=None;failure=None;cleanup=[];phase='LOGIN'
    previous_handlers={}
    def cancel(signum,frame):
        # Let exact custody cleanup finish after the first cancellation.
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        raise InterruptedError('currentboot_probe_cancelled')
    try:
        for signum in (signal.SIGTERM,signal.SIGINT):
            previous_handlers[signum]=signal.signal(signum,cancel)
        old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,previous_handlers)
        try:
            registered=True
            register_global_provider(provider)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
        values=document(request['credential_ref']);keys=request['credential_keys']
        need(set(keys)=={'username','password'},'exact_credential_keys')
        old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,previous_handlers)
        try:
            login_started=True
            minted=provider.complete_password_login(username=values[keys['username']],password=values[keys['password']])
        finally:
            try:values.clear()
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
        session=provider.verify_session(access_token=minted.access_token)
        need(session is not None and session.provider=='basic' and session.access_token==minted.access_token
            and admin_policy() is not None and session_allowed(session),'genuine_current_operator_session_required')
        admin=Administration();admin._verify_session(request['target']['profile'],session)
        onboarding=Onboarding(admin,storage_readonly=True);check();phase='A0_CURRENT_BOOT'
        read(request['marker']);read(request['installed_join'])
        budget=Budget(600,started=clock['started_monotonic'],deadline=clock['deadline_monotonic'])
        result=join.observe_closed_s443_a0_onboarding(onboarding,successor_request_ref=ROOT_RUN['request'],session=session,budget=budget,
            native_request_ref=request['native_request'],native_receipt_ref=request['native_receipt'],**request['target'])
    except BaseException as exc:
        # Bounded safe location/type metadata; no arbitrary error content.
        failure={'phase':phase,'diagnostic':{'error_kind':'diagnostic_unavailable'}}
        try: failure['diagnostic']=join._failure_diagnostic(exc)
        except Exception: pass
    finally:
        if login_started and minted is None:cleanup.append('EXACT_SESSION_MINT_UNCONFIRMED')
        if minted is not None:
            try:
                provider.revoke_session(refresh_token=minted.refresh_token,access_token=minted.access_token)
                need(provider.verify_session(access_token=minted.access_token) is None,'exact_session_revoke_unconfirmed')
            except BaseException:cleanup.append('EXACT_SESSION_REVOKE_UNCONFIRMED')
        if registered:
            try:need(unregister_global_provider('basic',provider),'provider_teardown_unconfirmed')
            except BaseException:cleanup.append('EXACT_PROVIDER_TEARDOWN_UNCONFIRMED')
        for signum,previous in previous_handlers.items():signal.signal(signum,previous)
    print(json.dumps({'schema':'friday.a0-closed-s443-successor-root-return.v1','result':result,'failure':failure,
        'cleanup':cleanup,'clock':request['original_clock'],'retry_authorized':False},sort_keys=True),flush=True)
    return 0 if failure is None and not cleanup else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        # Request/auth/input data is never included in setup failures.
        raise SystemExit(2)
