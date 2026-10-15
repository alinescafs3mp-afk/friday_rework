"""Real native first-contact state, signed scope and restart controls; offline only."""
RESTART_SOURCE = "import importlib.util,json,os,sys,weakref\nfrom pathlib import Path\nS=Path(sys.argv[2])\nROOT=Path(sys.argv[1]);os.environ['HERMES_HOME']=str(ROOT);os.environ['HERMES_RUNTIME_DIR']=str(ROOT/'runtime')\nsys.path.insert(0,str(S))\nimport hermes_constants as hc\nhc._PINNED_PROCESS_HERMES_HOME=str(ROOT)\nfrom hermes_cli import friday_user_scope as u\nfrom gateway.config import Platform\nfrom gateway.session import SessionSource\nfrom gateway.session_identity import RoutingIdentity\nfrom agent import onboarding as o\nclass Adapter:pass\nadapter=Adapter();home=ROOT/'profiles/fixture-user-1'\nsource=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id='1',chat_type='dm',profile='fixture-user-1')\nsource._identity=RoutingIdentity('default','fixture-user-1',ROOT,home,multiplexed=True,transport_inferred=False,transport=weakref.ref(adapter))\nwith u.authority(ROOT):u.admit_source(source)\nwith u.authority(home),u.scoped_source(source) as cap:\n    assert all(o.is_seen({},f) for f in (o.BUSY_INPUT_FLAG,o.TOOL_PROGRESS_FLAG,o.OPENCLAW_RESIDUE_FLAG,o.PROFILE_BUILD_FLAG))\n    assert cap.check() is cap\n    assert o.first_contact_turn_note({},home/'config.yaml',session_history_empty=True,install_has_prior_sessions=False)==o.PLAIN_INTRO_NOTE\nprint(json.dumps({'fresh_process_restart_persistence':True,'scope_valid':True,'no_duplicate_offer':True}))\n"

def test_signed_first_contact_state_and_restart(tmp_path, monkeypatch):
    import contextvars,hashlib,importlib.util,json,os,sys,time,weakref
    from pathlib import Path
    from contextlib import contextmanager
    from concurrent.futures import ThreadPoolExecutor
    OUT=tmp_path
    import tempfile
    ROOT=Path(tempfile.mkdtemp(prefix="fixture-",dir=OUT))
    monkeypatch.setenv('HERMES_HOME',str(ROOT))
    monkeypatch.setenv('HERMES_RUNTIME_DIR',str(ROOT/'runtime'))
    import hermes_constants as hc
    monkeypatch.setattr(hc,'_PINNED_PROCESS_HERMES_HOME',str(ROOT))
    from hermes_cli import friday_user_scope as u
    from hermes_cli.friday_product_access import KEY,principal_id
    from hermes_cli.plugins_state import PluginState
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity
    from hermes_state_registry import acquire,_generations
    monkeypatch.setattr(u,'_CURRENT',contextvars.ContextVar('offline-current',default=None));monkeypatch.setattr(u,'_SOURCE',contextvars.ContextVar('offline-source',default=None));monkeypatch.setattr(u,'_ENGAGED',False)
    from agent import onboarding as o
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    def write(p,v):p.write_text(json.dumps(v));p.chmod(0o600)
    bindings=[dict(platform='telegram',transport_profile='default',account_id='synthetic-account',user_id=str(i),runtime_profile='fixture-user-'+str(i),tools=['memory','read_file']) for i in (1,2)]
    settings={'product_access':{'enabled':True,'accounts':[dict(platform='telegram',transport_profile='default',account_id='synthetic-account',runtime_profiles=[b['runtime_profile'] for b in bindings])]},'user_isolation':{'enabled':True,'bindings':bindings}}
    cfg={'plugins':{'enabled':['friday_rework'],'entries':{'friday_rework':{'settings':settings}}},'gateway':{'multiplex_profiles':True,'profile_routes':[{'name':'friday-'+principal_id(*(b[k] for k in ('platform','transport_profile','account_id','user_id'))),'platform':b['platform'],'bot_profile':b['transport_profile'],'user_id':b['user_id'],'profile':b['runtime_profile'],'enabled':True} for b in bindings]}}
    write(ROOT/'config.yaml',cfg)
    rows={principal_id(*(b[k] for k in ('platform','transport_profile','account_id','user_id'))):{k:b[k] for k in ('platform','transport_profile','account_id','user_id')}|dict(enabled=True,role='user') for b in bindings}
    with u.authority(ROOT):PluginState('friday_rework').set(KEY,dict(schema=KEY,users=rows))
    homes=[];sources=[];adapters=[]
    class Adapter:pass
    for b in bindings:
        home=u.provision_new_home(ROOT,b,{'max_iterations':8});homes.append(home)
        (home/'SOUL.md').write_text('Synthetic fixture only.\n');(home/'SOUL.md').chmod(0o600)
        (home/'.env').write_text('SYNTHETIC_FIXTURE_KEY=offline-not-a-secret\n');(home/'.env').chmod(0o600)
        st=home.stat();receipt=dict(schema='friday.onboarding.v1',binding_sha256=u._fingerprint(b),config_sha256=sha(home/'config.yaml'),soul_sha256=sha(home/'SOUL.md'),required_secrets=['SYNTHETIC_FIXTURE_KEY'],directory_identity=[st.st_dev,st.st_ino],template='synthetic',authorization_home=str(ROOT))
        write(home/u.ONBOARDING,receipt)
        marker=json.loads((home/u.MARKER).read_text());marker['onboarding_sha256']=sha(home/u.ONBOARDING);write(home/u.MARKER,marker)
        adapter=Adapter();adapters.append(adapter)
        source=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id=b['user_id'],chat_type='dm',profile=b['runtime_profile'])
        source._identity=RoutingIdentity('default',b['runtime_profile'],ROOT,home,multiplexed=True,transport_inferred=False,transport=weakref.ref(adapter))
        with u.authority(ROOT):u.admit_source(source)
        assert isinstance(source._friday_user_scope,u.UserScope)
        sources.append(source)
    @contextmanager
    def enter(i):
        with u.authority(homes[i]),u.scoped_source(sources[i]) as cap:yield cap
    results={}
    def check(label,condition):assert condition,label;results[label]=True
    def denied(label,fn):
        try:fn()
        except u.ScopeDenied:results[label]=True
        else:raise AssertionError(label)
    snapshots=[(h/'config.yaml').read_bytes() for h in homes]
    flags=(o.BUSY_INPUT_FLAG,o.TOOL_PROGRESS_FLAG,o.OPENCLAW_RESIDUE_FLAG,o.PROFILE_BUILD_FLAG)
    with enter(0) as cap:
        check('first_contact_opt_in_preserved',o.first_contact_turn_note({},homes[0]/'config.yaml',session_history_empty=True,install_has_prior_sessions=False)==o.profile_build_directive().strip())
        for flag in flags:
            check('write_'+flag,o.mark_seen(homes[0]/'config.yaml',flag));check('read_'+flag,o.is_seen({},flag))
        check('config_bytes_intact',(homes[0]/'config.yaml').read_bytes()==snapshots[0]);check('cap_stays_valid',cap.check() is cap)
        check('already_seen_uses_plain_intro',o.first_contact_turn_note({},homes[0]/'config.yaml',session_history_empty=True,install_has_prior_sessions=False)==o.PLAIN_INTRO_NOTE)
        check('old_config_seen_compatible',o.is_seen({'onboarding':{'seen':{'old_flag':True}}},'old_flag'))
        denied('wrong_explicit_path_denied',lambda:o.mark_seen(homes[1]/'config.yaml','wrong'))
        check('valid_after_wrong_path',cap.check() is cap)
        # Retained native owner survives one-shot acquisition/release.
        owner=acquire(homes[0]/'state.db')
        try:o.mark_seen(homes[0]/'config.yaml','shared-owner');check('shared_owner_survives',owner.get_meta('onboarding.seen.shared-owner')=='1')
        finally:owner.close()
        contexts=[contextvars.copy_context() for _ in range(4)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            writes=list(pool.map(lambda pair:pair[0].run(o.mark_seen,homes[0]/'config.yaml',pair[1]),zip(contexts,['parallel-'+str(i) for i in range(4)])))
        check('concurrent_flags_persist',all(writes) and all(o.is_seen({},'parallel-'+str(i)) for i in range(4)))
    with enter(1) as cap:check('user_isolation',not any(o.is_seen({},f) for f in flags));check('second_user_flag',o.mark_seen(homes[1]/'config.yaml','second-user'))
    # New scope and new DB generation represent close/reopen persistence.
    with enter(0):check('reopen_persistence',all(o.is_seen({},f) for f in flags));check('no_foreign_flag',not o.is_seen({},'second-user'))
    with u.authority(homes[0]):
        denied('missing_cap_write_denied',lambda:o.mark_seen(homes[0]/'config.yaml','missing'));denied('missing_cap_read_denied',lambda:o.is_seen({},'missing'))
    u._ENGAGED=False
    with u.authority(homes[0]):denied('cold_missing_cap_marker_denied',lambda:o.mark_seen(homes[0]/'config.yaml','cold'))
    with enter(0) as cap:
        from dataclasses import replace
        wrong=replace(cap)
        token=u._CURRENT.set(wrong)
        try:
            with u.authority(homes[1]):
                denied('wrong_effective_home_write_denied',lambda:o.mark_seen(homes[1]/'config.yaml','wronghome'))
                denied('wrong_effective_home_read_denied',lambda:o.is_seen({},'wronghome'))
        finally:u._CURRENT.reset(token)
        check('original_cap_survives_foreign_copy',cap.check() is cap)
        cap.revoked=True
        denied('revoked_write_denied',lambda:o.mark_seen(homes[0]/'config.yaml','revoked'))
        denied('revoked_read_denied',lambda:o.is_seen({},'revoked'))
        denied('first_contact_denial_not_swallowed',lambda:o.first_contact_turn_note({},homes[0]/'config.yaml',session_history_empty=True,install_has_prior_sessions=False))
    check('all_signed_configs_unchanged',all((h/'config.yaml').read_bytes()==b for h,b in zip(homes,snapshots)))
    check('no_registry_handle_leak',not _generations)
    with enter(1):
        owner=acquire(homes[1]/'state.db')
        try:owner.create_session('foreign-synthetic','telegram',user_id='foreign',profile_name='foreign')
        finally:owner.close()
        before=sha(homes[1]/'state.db')
        denied('foreign_session_store_denied',lambda:o.mark_seen(homes[1]/'config.yaml','foreign-history'))
        check('foreign_session_refusal_no_db_write',sha(homes[1]/'state.db')==before)
    # Standalone native CLI keeps YAML storage, accepts explicit non-default path.
    u._ENGAGED=False
    legacy=Path(tempfile.mkdtemp(prefix='legacy-',dir=OUT));write(legacy/'config.yaml',{'model':{'default':'synthetic'}})
    with u.authority(legacy):
        check('legacy_write',o.mark_seen(legacy/'config.yaml',o.BUSY_INPUT_FLAG));loaded=json.loads('{}')
        from hermes_yaml import safe_load
        loaded=safe_load((legacy/'config.yaml').read_text());check('legacy_roundtrip',o.is_seen(loaded,o.BUSY_INPUT_FLAG));check('legacy_preserves_model',loaded['model']['default']=='synthetic')
        denied('legacy_cannot_target_admitted_home',lambda:o.mark_seen(homes[1]/'config.yaml','foreign'))
    import subprocess
    restart_file=OUT/'restart_probe.py';restart_file.write_text(RESTART_SOURCE)
    child=subprocess.run([sys.executable,'-B',str(restart_file),str(ROOT),str(Path(u.__file__).parents[1])],capture_output=True,text=True,check=True,timeout=30)
    (OUT/'restart.log').write_text(child.stdout+child.stderr)
    check('fresh_process_restart_persistence',json.loads(child.stdout)['fresh_process_restart_persistence'])
    assert len(results)==39
