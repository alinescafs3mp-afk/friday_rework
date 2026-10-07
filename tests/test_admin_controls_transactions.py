import copy,hashlib,json,pathlib,subprocess,sys,threading,time
import pytest
from test_admin_foundation import env,session
from test_admin_controls import local_config,body
R=pathlib.Path(__file__).resolve().parent

def wait_for(path,seconds=5):
    end=time.monotonic()+seconds
    while not path.exists():
        if time.monotonic()>end:raise TimeoutError(str(path))
        time.sleep(.01)

class Child:
    def __init__(self,env,mode):
        from hermes_cli import config
        self.env=env;self.results=[];self.errors=[]
        def run():
            try:self.results.append(subprocess.run([sys.executable,'-B',str(R/'admin_config_lock_child.py'),mode,str(env.home),str(pathlib.Path(config.__file__).parents[1])],capture_output=True,text=True,timeout=20))
            except BaseException as exc:self.errors.append(exc)
        self.thread=threading.Thread(target=run);self.thread.start()
    def finish(self):
        (self.env.home/'child-release').touch();self.thread.join(22)
        assert not self.thread.is_alive();assert not self.errors,self.errors
        assert self.results[0].returncode==0,self.results[0].stderr


def test_cross_process_native_transaction_writer(env,monkeypatch):
    from hermes_cli import config,managed_scope
    local_config(env);children=[]
    def interleave(key):
        if not children:
            children.append(Child(env,'transaction-writer'));wait_for(env.home/'child-attempt')
            assert not (env.home/'child-entered').exists()
        return False
    monkeypatch.setattr(managed_scope,'is_key_managed',interleave)
    try:answer=env.admin.write_settings('default',body(env,'operational',key='agent.max_turns',value=17),session())
    finally:
        for child in children:child.finish()
    assert answer['recorded']
    assert json.loads((env.home/'child-observed.json').read_text())['max_turns']==17
    cfg=config.require_readable_config_before_write();assert cfg['agent']['max_turns']==17 and cfg['web']['extract_timeout']==99


def test_existing_native_plugin_writer_preserves_intervening_admin_edit(env,monkeypatch):
    from hermes_cli import config,managed_scope
    local_config(env);cfg=config.require_readable_config_before_write();cfg['agent']['max_turns']=12;config.atomic_config_write(env.home/'config.yaml',cfg)
    children=[]
    def interleave(key):
        if not children:
            children.append(Child(env,'plugin-writer'));wait_for(env.home/'child-attempt')
            assert not (env.home/'child-done').exists()
        return False
    monkeypatch.setattr(managed_scope,'is_key_managed',interleave)
    try:answer=env.admin.write_settings('default',body(env,'operational',key='agent.max_turns',value=17),session())
    finally:
        for child in children:child.finish()
    current=config.require_readable_config_before_write();assert answer['recorded']
    assert current['plugins']['entries']['friday_rework']['settings']['unrelated_review_flag'] is True
    assert current['agent']['max_turns']==17, 'Existing save_plugin_setting lost unrelated successful admin max_turns=17; final value='+str(current['agent']['max_turns'])

@pytest.mark.parametrize('mode',['hold-config','revoke-config','expire-config'])
def test_config_wait_revalidates_timeout_revocation_expiry(env,mode):
    from hermes_cli import config
    local_config(env);original=(env.home/'config.yaml').read_bytes()
    request=body(env,'operational',key='agent.max_turns',value=17)
    owner=session(expires_at=int(time.time())+1) if mode=='expire-config' else session()
    child=Child(env,mode)
    try:
        wait_for(env.home/'child-entered');start=time.monotonic()
        with pytest.raises(TimeoutError if mode=='hold-config' else PermissionError):
            env.admin.write_settings('default',request,owner)
        if mode=='hold-config':assert 1.8<=time.monotonic()-start<3.5
    finally:child.finish()
    cfg=config.require_readable_config_before_write();assert cfg['agent'].get('max_turns')!=17
    if mode!='revoke-config':assert (env.home/'config.yaml').read_bytes()==original


def test_cron_kernel_lock_timeout_refuses_administrative_write(env,monkeypatch):
    from cron import jobs
    local_config(env);job=jobs.create_job(prompt='Synthetic never executed',schedule='every 1h',paused=True)
    child=Child(env,'hold-cron')
    try:
        wait_for(env.home/'child-entered');monkeypatch.setattr(jobs,'_JOBS_LOCK_TIMEOUT_SECONDS',.1)
        try:answer=env.admin.schedules('default','resume',job['id'],session())
        except TimeoutError:answer=None
        assert not jobs.get_job(job['id'])['enabled'], 'Administrative resume wrote without actual cross-process cron lock; response='+repr(answer)
    finally:child.finish()


def test_cron_expired_at_locked_native_save_is_refused(env,monkeypatch):
    from cron import jobs
    local_config(env);job=jobs.create_job(prompt='Synthetic never executed',schedule='every 1h',paused=True)
    who=session();original=jobs._fill_missing_next_run
    def expire(row):original(row);object.__setattr__(who,'expires_at',1)
    monkeypatch.setattr(jobs,'_fill_missing_next_run',expire)
    with pytest.raises(PermissionError):env.admin.schedules('default','resume',job['id'],who)
    assert not jobs.get_job(job['id'])['enabled']


def test_native_cron_legacy_signatures_continue(env):
    from cron import jobs
    local_config(env);job=jobs.create_job(prompt='Synthetic never executed',schedule='every 1h',paused=True)
    assert jobs.resume_job(job['id'])['enabled']
    assert not jobs.pause_job(job['id'],'plain-native-reason')['enabled']
    assert jobs.update_job(job['id'],{'name':'ordinary-native'})['name']=='ordinary-native'


def test_native_config_nested_write_replace_and_plugin_api(env):
    from hermes_cli import config
    from hermes_cli.plugins_state import save_plugin_setting
    local_config(env);path=env.home/'config.yaml'
    with config.config_write_transaction(path):
        with config.config_write_transaction(path):
            cfg=config.require_readable_config_before_write(path);cfg['agent']['max_turns']=22;config.atomic_config_write(path,cfg)
            cfg['agent']['max_turns']=23;config.atomic_config_replace(path,cfg)
    save_plugin_setting('friday_rework',('ordinary',),7)
    cfg=config.require_readable_config_before_write(path);assert cfg['agent']['max_turns']==23
    assert cfg['plugins']['entries']['friday_rework']['settings']['ordinary']==7


def test_raw_secret_env_reference_is_preserved(env,monkeypatch):
    from hermes_cli import config
    local_config(env);cfg=config.require_readable_config_before_write();cfg['plugins']['entries']['friday_rework']['settings']['synthetic_secret']='${REVIEW_SYNTHETIC_SECRET}';config.atomic_config_write(env.home/'config.yaml',cfg)
    monkeypatch.setenv('REVIEW_SYNTHETIC_SECRET','UNIQUE-REVIEW-CANARY-7723')
    env.admin.write_settings('default',body(env,'web',profile='exa-paid',extract_timeout=12,extract_char_limit=6000),session())
    assert config.load_config_readonly()['plugins']['entries']['friday_rework']['settings']['synthetic_secret']=='UNIQUE-REVIEW-CANARY-7723'
    raw=(env.home/'config.yaml').read_text();assert '${REVIEW_SYNTHETIC_SECRET}' in raw and 'UNIQUE-REVIEW-CANARY-7723' not in raw

@pytest.mark.parametrize('override',[{'model':{'provider':'${REVIEW_ROUTE}'}},{'auxiliary':{'goal_judge':{'provider':'${REVIEW_ROUTE}'}}},{'fallback_providers':[{'provider':'${REVIEW_ROUTE}','model':'synthetic'}]}])
def test_effective_managed_env_cloud_refused(env,monkeypatch,override):
    from hermes_cli import managed_scope
    local_config(env);directory=env.home/'managed';directory.mkdir();(directory/'config.yaml').write_text(json.dumps(override))
    monkeypatch.setenv('HERMES_MANAGED_DIR',str(directory));monkeypatch.setenv('REVIEW_ROUTE','openrouter');managed_scope.invalidate_managed_cache()
    before=(env.home/'config.yaml').read_bytes()
    with pytest.raises((ValueError,PermissionError)):
        env.admin.write_settings('default',body(env,'web',profile='exa-paid',extract_timeout=12,extract_char_limit=6000),session())
    assert (env.home/'config.yaml').read_bytes()==before

@pytest.mark.parametrize('kind,override,values',[
    ('skill',{'skills':{'disabled':['fixture']}},{'name':'fixture','enabled':True}),
    ('skill',{'skills':{'platform_disabled':{'telegram':['fixture']}}},{'name':'fixture','enabled':True}),
    ('toolset',{'agent':{'disabled_toolsets':['terminal']}},{'name':'terminal','enabled':True}),
    ('toolset',{'platform_toolsets':{'telegram':['web']}},{'name':'terminal','enabled':True})])
def test_managed_capability_deny_cannot_be_reported_enabled(env,monkeypatch,kind,override,values):
    from hermes_cli import managed_scope
    local_config(env);skill=env.home/'skills/fixture';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('Synthetic skill')
    directory=env.home/'managed';directory.mkdir();(directory/'config.yaml').write_text(json.dumps(override))
    monkeypatch.setenv('HERMES_MANAGED_DIR',str(directory));managed_scope.invalidate_managed_cache();before=(env.home/'config.yaml').read_bytes()
    try:answer=env.admin.write_settings('default',body(env,kind,**values),session())
    except (ValueError,PermissionError):
        assert (env.home/'config.yaml').read_bytes()==before;return
    from tools.skills_tool import _find_all_skills
    monkeypatch.setenv('HERMES_PLATFORM','telegram')
    visible=[row['name'] for row in _find_all_skills()]
    assert 'fixture' in visible, 'Acknowledged enabling skill despite effective managed Telegram deny: '+repr(answer)+' visible='+repr(visible)


def test_every_pinned_auxiliary_has_valid_local_effective_route(env):
    from hermes_cli import config
    from friday_admin_controls.admin_settings import _local_inference
    local_config(env);raw=config.require_readable_config_before_write();effective=config.load_config_readonly()
    roles={k for k,v in config.DEFAULT_CONFIG['auxiliary'].items() if isinstance(v,dict)}
    assert len(roles)==18 and roles<={k for k,v in raw['auxiliary'].items() if isinstance(v,dict)}
    _local_inference(effective)
    for role in roles:
        assert raw['auxiliary'][role]['provider']=='custom:friday-local'
        assert raw['auxiliary'][role]['fallback_chain']==[]
    cfg=copy.deepcopy(raw);del cfg['auxiliary']['goal_judge'];config.atomic_config_replace(env.home/'config.yaml',cfg)
    with pytest.raises(ValueError):env.admin.write_settings('default',body(env,'operational',key='agent.max_turns',value=17),session())


@pytest.mark.parametrize('failure',['missing','error','nested-degraded'])
def test_strict_cron_unavailable_lock_refuses_and_cleans_up(env,monkeypatch,failure):
    from cron import jobs
    local_config(env);job=jobs.create_job(prompt='Synthetic never executed',schedule='every 1h',paused=True)
    def acquire(*args):
        if failure=='error':raise OSError('synthetic-unavailable')
        return None
    monkeypatch.setattr(jobs,'_acquire_flock',acquire)
    if failure=='nested-degraded':
        with jobs._jobs_lock():
            with pytest.raises(RuntimeError):env.admin.schedules('default','resume',job['id'],session())
    else:
        with pytest.raises((RuntimeError,OSError)):env.admin.schedules('default','resume',job['id'],session())
    assert not jobs.get_job(job['id'])['enabled']
    assert jobs._jobs_lock_state.depth==0 and not jobs._jobs_lock_state.cross_process



def test_native_managed_save_refuses_before_lock_file_creation(env,monkeypatch):
    from hermes_cli import config
    local_config(env);path=env.home/'config.yaml';before=path.read_bytes();called=[]
    monkeypatch.setattr(config,'is_managed',lambda:True)
    monkeypatch.setattr(config,'managed_error',lambda *args:called.append(args))
    def forbidden(*args):raise AssertionError('managed save attempted file lock')
    monkeypatch.setattr(config,'config_write_transaction',forbidden)
    config.save_config({'agent':{'max_turns':17}},merge_existing=True)
    assert called and path.read_bytes()==before
