
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

"""Exact future Root authentication composition for S447 publication only.
No cold worker invocation. Import is inert; ROOT_RUN remains unbound in package.
"""
ROOT_RUN=None
ENTRY = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_2311aa4637a52b04/publication/root_use.py', 'sha256': 'PRIVATE_REF_07c909b55458ab0a'}
PUBLISHER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_2311aa4637a52b04/publication/publish_fourlink.py', 'sha256': 'PRIVATE_REF_e1dc3a302a261973'}
def main():
    import hashlib,importlib.util,json,os,signal,stat,sys
    from pathlib import Path
    def need(ok,code):
        if not ok:raise ValueError(code)
    def read(ref,private=True):
        need(type(ref)is dict and set(ref)=={'path','sha256'},'exact_reference')
        p=Path(ref['path']);need(p.is_absolute()and p.resolve()==p,'canonical_reference')
        parents={}
        for q in p.parents:
            a=q.lstat();need(stat.S_ISDIR(a.st_mode)and a.st_uid in(0,os.getuid())and not a.st_mode&0o022,'protected_parent');parents[q]=(a.st_dev,a.st_ino,a.st_mode,a.st_uid,a.st_gid)
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            a=os.fstat(fd);need(stat.S_ISREG(a.st_mode)and a.st_uid==os.getuid()and a.st_gid==os.getgid()and a.st_nlink==1 and not a.st_mode&(0o077 if private else 0o022),'reference_custody')
            raw=os.pread(fd,32*1024**2+1,0);b=os.fstat(fd);c=p.lstat();fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
            need(len(raw)<=32*1024**2 and all(getattr(a,k)==getattr(b,k)==getattr(c,k)for k in fields)and hashlib.sha256(raw).hexdigest()==ref['sha256'],'reference_changed')
        finally:os.close(fd)
        need(all((q.lstat().st_dev,q.lstat().st_ino,q.lstat().st_mode,q.lstat().st_uid,q.lstat().st_gid)==v for q,v in parents.items()),'reference_parent_changed')
        return raw
    def document(ref):
        def unique(rows):
            out={}
            for k,v in rows:need(k not in out,'duplicate_key');out[k]=v
            return out
        return json.loads(read(ref),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    need(type(ROOT_RUN)is dict and set(ROOT_RUN)=={'request'},'UNBOUND_NO_EFFECT')
    request=document(ROOT_RUN['request'])
    need(set(request)=={'schema','native_source','python','launch_home','dashboard_api','installed_join','native_refs','marker','credential_ref','credential_keys','clock','parent_clock','operation_directory','target','operation','inputs'}and request['schema']=='frw.Root.S447.publication-native-entry.v1','exact_publication_entry_request')
    need(request['operation']in('complete','bind','apply'),'only_publication_bind_or_apply')
    need(set(request['target'])=={'profile','expected_config_sha256','generation','platform','transport_profile','account_id','user_id'},'current_target_fields')
    if request['operation']=='bind':
        need(set(request['inputs'])=={'source','postboot_proof_ref','output_directory','clock_ref','parent_clock_ref'}and request['inputs']['clock_ref']==request['clock']and request['inputs']['parent_clock_ref']==request['parent_clock'],'bind_clock_join')
    elif request['operation']=='complete':
        need(set(request['inputs'])=={'source','closure_ref','clock_ref','parent_clock_ref'} and request['inputs']['clock_ref']==request['clock'] and request['inputs']['parent_clock_ref']==request['parent_clock'],'completion_clock_join')
    else:
        need(set(request['inputs'])=={'request_ref'},'apply_input_fields')
        applied=document(request['inputs']['request_ref']);need(applied['clock']==request['clock']and applied['parent_clock']==request['parent_clock']and applied['publisher']==PUBLISHER,'apply_clock_publisher_join')
    pub={'__file__':PUBLISHER['path'],'__name__':'_s447_reviewed_publication'}
    exec(compile(read(PUBLISHER),PUBLISHER['path'],'exec'),pub)
    budget=pub['StageBudget'](request['clock'],request['parent_clock']);budget.check()
    H=Path('<INSTALL_HOME>');source=H/'hermes-agent'
    PM=H/'installs/45eb40fd2d5351a9/environments/PRIVATE_REF_f236aa5525a8c3d7/venv/bin/python'
    need(sys.flags.isolated and sys.dont_write_bytecode and sys.executable==request['python']==str(PM),'native_lexical_python')
    need(request['launch_home']==str(H)and request['native_source']==str(source)and request['dashboard_api']['path']==str(H/'plugins/friday_rework/dashboard/api.py')and request['installed_join']['path']==str(H/'plugins/friday_rework/user_worker_join.py')and request['marker']['path']==str(H/'FRIDAY-INSTALL.json'),'exact_native_graph')
    marker=document(request['marker'])
    need(all(marker['plugin_files']['plugins/friday_rework/'+n]==request[k]['sha256']for n,k in(('user_worker_join.py','installed_join'),('dashboard/api.py','dashboard_api'))),'marker_source_join')
    for ref in(request['dashboard_api'],request['installed_join']):read(ref)
    for ref in request['native_refs']:read(ref,private=False)
    sys.path.insert(0,str(source))
    from hermes_constants import get_process_hermes_home,get_routing_process_hermes_home
    need(get_process_hermes_home()==H and get_routing_process_hermes_home()==H,'actual_launch_home')
    from hermes_cli.friday_dashboard_owner import source_identity
    source_identity(H,source=source)
    import plugins
    need(Path(plugins.__file__).resolve()==source/'plugins/__init__.py','actual_native_plugins')
    name='hermes_dashboard_plugin_friday_rework'
    need(name not in sys.modules and '_friday_dashboard_projection'not in sys.modules,'fresh_trusted_projection')
    api=importlib.util.module_from_spec(importlib.util.spec_from_file_location(name,request['dashboard_api']['path']));sys.modules[name]=api
    exec(compile(read(request['dashboard_api']),request['dashboard_api']['path'],'exec'),api.__dict__)
    from hermes_cli import friday_user_scope as scope
    from hermes_cli.friday_product_access import admin_policy,session_allowed
    from hermes_cli.dashboard_auth.registry import get_provider,register_global_provider,unregister_global_provider
    from plugins.dashboard_auth import basic
    need(scope._CURRENT.get()is None and get_provider('basic')is None,'fresh_operator_context')
    entry={'__file__':ENTRY['path'],'__name__':'_s447_exact_publication_entry'}
    exec(compile(read(ENTRY),ENTRY['path'],'exec'),entry)
    operation=Path(request['operation_directory']);need(operation.is_absolute()and operation.resolve()==operation and str(operation)==request['operation_directory']and operation.is_relative_to(Path('<PRIVATE_CACHE>'))and operation.name.startswith('PRIVATE_REF_59b980eaff34c118'),'exact_Root_private_operation');scope._private(operation,directory=True)
    for parent in operation.parents:
        info=parent.lstat();need(stat.S_ISDIR(info.st_mode)and info.st_uid in(0,os.getuid())and not info.st_mode&0o022,'protected_operation_parent')
    budget.check();read(ROOT_RUN['request']);read(request['marker'])
    fd=os.open(operation/'runner-intent.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as f:f.write((json.dumps({'schema':'frw.Root.S447.publication-native-intent.v1','request':ROOT_RUN['request'],'clock':request['clock'],'no_retry':True},sort_keys=True)+'\n').encode());f.flush();os.fsync(f.fileno())
    fd=os.open(operation,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    handlers={n:signal.getsignal(n)for n in(signal.SIGTERM,signal.SIGINT)}
    def cancelled(signum,frame):raise InterruptedError('S447_publication_cancelled')
    provider=basic.BasicAuthProvider(**native_basic_settings(read,basic));minted=None;registered=False;login_started=False;result=None;failure=None;cleanup=[]
    try:
        for n in handlers:signal.signal(n,cancelled)
        budget.check()
        old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,handlers)
        try:
            registered=True
            register_global_provider(provider)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
        values=document(request['credential_ref']);keys=request['credential_keys']
        need(set(keys)=={'username','password'},'exact_credential_keys')
        old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,handlers)
        try:
            login_started=True
            minted=provider.complete_password_login(username=values[keys['username']],password=values[keys['password']])
        finally:
            try:values.clear()
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)
        session=provider.verify_session(access_token=minted.access_token)
        need(session is not None and session.provider=='basic'and session.access_token==minted.access_token and admin_policy()is not None and session_allowed(session),'actual_current_operator_session')
        budget.check();read(request['marker']);read(request['installed_join'])
        result=entry['invoke_current'](dashboard_api=api,session=session,arguments=request['target'],operation=request['operation'],inputs=request['inputs'])
    except BaseException as exc:failure={'exception_class':type(exc).__name__}
    finally:
        try:
            if login_started and minted is None:cleanup.append('EXACT_SESSION_MINT_UNCONFIRMED')
            if minted is not None:
                try:
                    provider.revoke_session(refresh_token=minted.refresh_token,access_token=minted.access_token)
                    need(provider.verify_session(access_token=minted.access_token)is None,'session_revoke_unconfirmed')
                except BaseException:cleanup.append('EXACT_SESSION_REVOKE_UNCONFIRMED')
            if registered:
                try:need(unregister_global_provider('basic',provider),'provider_teardown_unconfirmed')
                except BaseException:cleanup.append('EXACT_PROVIDER_TEARDOWN_UNCONFIRMED')
        finally:
            for n,handler in handlers.items():signal.signal(n,handler)
    print(json.dumps({'schema':'frw.Root.S447.publication-native-return.v1','operation':request['operation'],'result':result,'failure':failure,'cleanup':cleanup,'clock':request['clock'],'no_retry':True},sort_keys=True),flush=True)
    return 0 if failure is None and not cleanup else 2
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit(2)
