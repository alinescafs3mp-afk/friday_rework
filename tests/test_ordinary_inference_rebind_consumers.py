"""Independent reviewer cases, copied with attribution; adapted only fixture compressor route/name and worker-free ordinary alias. Independent reviewer regression cases retained with attribution; full source-snapshot materialization stays private."""
import copy,hashlib,json,os,shutil
from contextlib import contextmanager
from pathlib import Path
import pytest,yaml
from test_ordinary_inference_rebind import case,run,write,pin,assert_restored,u,f,users,owner,admission,StopUnconfirmed
from hermes_cli.runtime_provider import resolve_runtime_provider

D=Path(f.__file__).resolve().parents[1]
REAL_SOURCE_IDENTITY=owner.source_identity


def existing_capability(case):
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    binding=cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]
    principal=tuple(binding[k] for k in ('platform','transport_profile','account_id','user_id'))
    st=case.user.stat()
    return users.UserScope(case.home,case.user,'dest_telegram',principal,binding,(st.st_dev,st.st_ino),7)


def test_actual_native_per_home_key_and_role_consumers_after_rebind(case,monkeypatch):
    run(case)
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        monkeypatch.delenv(name,raising=False)
    cap=existing_capability(case)
    for home,expected_primary,expected_compression in ((case.home,'SYNTH_SPARK_ROOT','SYNTH_ROOT_27B'),(case.user,'SYNTH_SPARK_USER','SYNTH_USER_27B')):
        token=users._CURRENT.set(cap if home==case.user else None)
        try:
            with admission.scoped(home):
                selected=resolve_runtime_provider(requested='custom:friday-local',target_model='synthetic-spark')
                assert selected['api_key']==expected_primary
                assert selected['base_url']=='http://127.0.0.1:30000/v1'
                assert selected['model']=='synthetic-spark'
                compressed=admission.auxiliary('compression',None,None,None,None)
                assert compressed==('custom:friday-compression','dispatcher','http://192.168.1.78:8001/v1',expected_compression,'chat_completions')
                with pytest.raises(ValueError,match='explicit_foreign_key_refused'):
                    admission.route_inputs('custom:friday-local',api_key=expected_compression)
                with pytest.raises(ValueError,match='compression_context_required'):
                    admission.route_inputs('custom:friday-compression')
                with pytest.raises(ValueError,match='compression_task_required'):
                    admission.auxiliary('title','custom:friday-compression',None,None,None)
                with pytest.raises(ValueError,match='explicit_foreign_key_refused'):
                    admission.route_inputs('custom:friday-local',api_key='SYNTH_OTHER_HOME')
        finally:users._CURRENT.reset(token)




@pytest.mark.parametrize('kind',['keyboard','systemexit'])
def test_cancel_during_publication_restores_own_beforeimages(case,monkeypatch,kind):
    original=u.publish_update_file;fired=False
    def interrupted(path,*a,**kw):
        nonlocal fired
        value=original(path,*a,**kw)
        if path==case.home/'config.yaml' and not fired:
            fired=True
            if kind=='keyboard':raise KeyboardInterrupt('SYNTH_CANCEL')
            raise SystemExit(7)
        return value
    monkeypatch.setattr(u,'publish_update_file',interrupted)
    with pytest.raises(KeyboardInterrupt if kind=='keyboard' else SystemExit):run(case)
    assert_restored(case)
    assert (case.tx/'rolled-back.json').is_file()


def test_custody_exit_failure_retains_original_primary_error(case,monkeypatch):
    @contextmanager
    def custody(*a,**kw):
        try:yield lambda:None
        finally:raise RuntimeError('SYNTH_CUSTODY_RELEASE_FAILURE')
    monkeypatch.setattr(u,'stopped_consumers',custody)
    original=u.publish_update_file;fired=False
    def fail(path,*a,**kw):
        nonlocal fired
        value=original(path,*a,**kw)
        if path==case.home/'config.yaml' and not fired:
            fired=True
            raise RuntimeError('SYNTH_PRIMARY_FAILURE')
        return value
    monkeypatch.setattr(u,'publish_update_file',fail)
    with pytest.raises(BaseException) as caught:run(case)
    primary=getattr(caught.value,'friday_custody_primary',None) or caught.value.__cause__ or caught.value
    assert primary.args==('SYNTH_PRIMARY_FAILURE',)


def test_beforeimage_directories_are_durable_before_first_publication(case,monkeypatch):
    import stat
    opened={}; synced=set(); real_open=os.open; real_close=os.close; real_fsync=os.fsync
    def opened_fd(path,*a,**kw):
        fd=real_open(path,*a,**kw)
        if isinstance(path,(str,bytes,os.PathLike)):opened[fd]=Path(os.fsdecode(path))
        return fd
    def closed_fd(fd):
        opened.pop(fd,None);return real_close(fd)
    def synced_fd(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) and fd in opened:synced.add(opened[fd])
        return real_fsync(fd)
    monkeypatch.setattr(os,'open',opened_fd);monkeypatch.setattr(os,'close',closed_fd);monkeypatch.setattr(os,'fsync',synced_fd)
    original=u.publish_update_file;checked=False
    def publication(path,*a,**kw):
        nonlocal checked
        if not checked:
            checked=True
            expected={case.tx/'before',case.tx/'before/profiles',case.tx/'before/profiles/dest_telegram'}
            assert expected <= synced, 'beforeimage directory entries not fsynced before replacement'
        return original(path,*a,**kw)
    monkeypatch.setattr(u,'publish_update_file',publication)
    run(case)


def test_cli_reports_unknown_rollback_as_stop_unconfirmed(case,monkeypatch,capsys):
    import sys
    primary=RuntimeError('SYNTH_PRIMARY_FAILURE')
    stop=StopUnconfirmed('SYNTH_UNKNOWN_ROLLBACK');stop.__cause__=primary
    def failed(*a,**kw):raise stop
    monkeypatch.setattr(u,'rebind_inference',failed)
    monkeypatch.setattr(sys,'argv',['friday_ordinary_install.py','rebind-inference','--request',str(case.path)])
    with pytest.raises(f.InstallerExit) as caught:u.recovery_main()
    output=capsys.readouterr().err
    assert caught.value.friday_custody_primary is stop
    assert caught.value.code==3 and caught.value.friday_custody_state=='UNCONFIRMED'
    assert output.startswith('STOP_UNCONFIRMED:')


def reseal_changed_fixture(case,cfg,usercfg=None,proof=None):
    from hermes_cli.config_effective import _effective
    from hermes_cli.friday_ordinary_gateway import normalized_configuration
    write(case.home/'config.yaml',yaml.safe_dump(cfg))
    if usercfg is not None:write(case.user/'config.yaml',yaml.safe_dump(usercfg))
    if proof is None:proof=json.loads((case.user/users.ONBOARDING).read_bytes())
    proof['config_sha256']=pin(case.user/'config.yaml')['sha256']
    write(case.user/users.ONBOARDING,json.dumps(proof))
    marker=json.loads((case.user/users.MARKER).read_bytes())
    marker['onboarding_sha256']=pin(case.user/users.ONBOARDING)['sha256'];write(case.user/users.MARKER,json.dumps(marker))
    marker=json.loads((case.home/f.MARKER).read_bytes())
    marker['ordinary_gateway']['configuration_sha256']=normalized_configuration(_effective(cfg))
    marker['profile_files']['config.yaml']=pin(case.home/'config.yaml')['sha256'];write(case.home/f.MARKER,json.dumps(marker))
    for name in case.request['before']:case.request['before'][name]=pin(case.home/name)
    write(case.path,json.dumps(case.request))


def admitted_browser_fixture(case, *, granted=True, private_urls=False):
    """An existing native browser grant, independent of the base template."""
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    usercfg=yaml.safe_load((case.user/'config.yaml').read_bytes())
    binding=cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]
    if granted:
        binding['tools']=sorted(set(binding['tools']) | users.BROWSER_TOOLS)
    usercfg['browser']=copy.deepcopy(users.BROWSER_LOCAL_CONFIG)
    usercfg['browser']['allow_private_urls']=private_urls
    usercfg['toolsets'].append(users.BROWSER_TOOLSET)
    for values in usercfg['platform_toolsets'].values():
        if users.BROWSER_TOOLSET not in values:values.append(users.BROWSER_TOOLSET)
    proof=json.loads((case.user/users.ONBOARDING).read_bytes())
    proof['binding_sha256']=users._fingerprint(binding)
    marker=json.loads((case.user/users.MARKER).read_bytes())
    marker['binding_sha256']=proof['binding_sha256']
    write(case.user/users.MARKER,json.dumps(marker))
    reseal_changed_fixture(case,cfg,usercfg,proof)
    case.before={n:(case.home/n).read_bytes() for n in case.request['before']}
    return binding,copy.deepcopy(usercfg['browser'])


def test_rebind_preserves_existing_browser_grant_outside_base_template(case):
    binding,browser=admitted_browser_fixture(case)
    root_before=yaml.safe_load((case.home/'config.yaml').read_bytes())
    templates=root_before['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    assert not set(templates['friday-local']['tools']) & users.BROWSER_TOOLS
    run(case)
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    usercfg=yaml.safe_load((case.user/'config.yaml').read_bytes())
    assert cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings']==[binding]
    assert usercfg['browser']==browser==users.BROWSER_LOCAL_CONFIG
    users.validate_browser_config(usercfg,binding['tools'],platform='telegram')
    assert usercfg['model']['default']=='synthetic-spark'
    assert usercfg['auxiliary']['compression']['model']=='dispatcher'
    with users.authority(case.home):
        users.check_onboarding_home(case.home,case.user,binding)


@pytest.mark.parametrize('granted,private_urls',[(False,False),(True,True)])
def test_rebind_refuses_ungranted_or_widened_browser_before_publication(case,granted,private_urls):
    admitted_browser_fixture(case,granted=granted,private_urls=private_urls)
    with pytest.raises(users.ScopeDenied):run(case)
    assert not case.tx.exists()
    assert_restored(case)


def remove_legacy_missing_privacy_flags(cfg):
    cfg.get('display',{}).pop('show_reasoning',None)
    cfg.get('display',{}).get('platforms',{}).get('telegram',{}).pop('show_reasoning',None)
    cfg.get('model',{}).pop('reasoning_echo',None)


def test_existing_legacy_absent_privacy_flags_get_explicit_false(case):
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    usercfg=yaml.safe_load((case.user/'config.yaml').read_bytes())
    remove_legacy_missing_privacy_flags(cfg);remove_legacy_missing_privacy_flags(usercfg)
    for template in cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates'].values():
        remove_legacy_missing_privacy_flags(template['config'])
    reseal_changed_fixture(case,cfg,usercfg)
    run(case)
    for home in (case.home,case.user):
        after=yaml.safe_load((home/'config.yaml').read_bytes())
        assert after['display']['show_reasoning'] is False
        assert after['display']['platforms']['telegram']['show_reasoning'] is False
        assert after['model']['reasoning_echo'] is True  # explicit fixture primary request option; display remains hidden


def test_existing_ordinary_alias_receipt_is_supported(case):
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    templates=cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    templates['friday-ordinary-local']=copy.deepcopy(templates['friday-local'])
    templates['friday-ordinary-local'].pop('worker_inputs',None)
    proof=json.loads((case.user/users.ONBOARDING).read_bytes());proof['template']='friday-ordinary-local'
    reseal_changed_fixture(case,cfg,proof=proof)
    run(case)
    after=json.loads((case.user/users.ONBOARDING).read_bytes())
    assert after['template']=='friday-ordinary-local'


def test_both_existing_approved_template_routes_are_rebound(case):
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    templates=cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    templates['friday-ordinary-local']=copy.deepcopy(templates['friday-local'])
    templates['friday-ordinary-local'].pop('worker_inputs',None)
    reseal_changed_fixture(case,cfg)
    run(case)
    after=yaml.safe_load((case.home/'config.yaml').read_bytes())
    templates=after['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    assert set(templates)=={'friday-local','friday-ordinary-local'}
    for template in templates.values():
        assert template['config']['model']['default']=='synthetic-spark'
        assert 'FRIDAY_COMPRESSION_API_KEY' in template['required_secrets']


def test_successful_data_commit_with_failed_custody_exit_is_stop_unconfirmed(case,monkeypatch):
    @contextmanager
    def custody(*a,**kw):
        try:yield lambda:None
        finally:raise RuntimeError('SYNTH_CUSTODY_RELEASE_FAILURE')
    monkeypatch.setattr(u,'stopped_consumers',custody)
    with pytest.raises(StopUnconfirmed) as caught:run(case)
    assert caught.value.__cause__.args==('SYNTH_CUSTODY_RELEASE_FAILURE',)
    # The data commit exists, but this exception must prevent successful return.
    assert (case.tx/'committed.json').is_file()


def test_unknown_template_inventory_fails_closed_before_consumed_effect(case):
    cfg=yaml.safe_load((case.home/'config.yaml').read_bytes())
    templates=cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    templates['unknown-custom-template']=copy.deepcopy(templates['friday-local'])
    reseal_changed_fixture(case,cfg)
    before={n:(case.home/n).read_bytes() for n in case.request['before']}
    with pytest.raises(ValueError,match='ordinary_rebind_exact_existing_templates_required'):run(case)
    assert {n:(case.home/n).read_bytes() for n in case.request['before']}==before
    assert not (case.tx/'intent.json').exists()
