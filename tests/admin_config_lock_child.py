"""Finite subprocess for real native config/cron lock regression tests only."""
import os,sys,pathlib,time,json,signal,resource
mode,root,native=sys.argv[1:]
home=pathlib.Path(root).resolve();native=pathlib.Path(native).resolve()
assert home.is_dir() and home.stat().st_uid==os.getuid() and not home.stat().st_mode & 0o077
assert home.name=='home' and (home/'config.yaml').is_file()
os.umask(0o077);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('finite_native_fixture')));signal.alarm(18)
os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME=str(home),HERMES_HOME=str(home),LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
sys.dont_write_bytecode=True;sys.path.insert(0,str(native))
def allowed(path):return pathlib.Path(os.fsdecode(path)).resolve().is_relative_to(home)
def guard(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.posix_spawn','os.fork'):
        raise OSError('native_lock_fixture_effect_refused')
    if event=='open' and isinstance(args[0],(str,bytes)):
        path=pathlib.Path(os.fsdecode(args[0])).resolve();flags=args[2] or 0
        if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC) and not allowed(path):raise OSError('outside_fixture_write')
        if path.name in ('.env','auth.json','credentials.json') and not allowed(path):raise OSError('real_credentials_refused')
    if event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.chown','os.utime') and isinstance(args[0],(str,bytes)) and not allowed(args[0]):raise OSError('outside_fixture_mutation')
    if event in ('os.rename','os.link') and any(isinstance(p,(str,bytes)) and not allowed(p) for p in args[:2]):raise OSError('outside_fixture_mutation')
    if event=='os.symlink' and not allowed(args[1]):raise OSError('outside_fixture_symlink')
sys.addaudithook(guard)
from hermes_cli import version_info, banner
version_info._resolve_repo_dir=lambda:None
banner.prefetch_update_check=lambda:None
from hermes_constants import set_hermes_home_override
set_hermes_home_override(str(home))
from hermes_cli import config
path=home/'config.yaml';(home/'child-attempt').touch()
def release(maximum=8):
    end=time.monotonic()+maximum
    while not (home/'child-release').exists():
        if time.monotonic()>end:raise TimeoutError('finite fixture release timeout')
        time.sleep(.01)
if mode in ('transaction-writer','hold-config','revoke-config','expire-config'):
    with config.config_write_transaction(path):
        (home/'child-entered').touch()
        cfg=config.require_readable_config_before_write(path)
        if mode=='transaction-writer':
            (home/'child-observed.json').write_text(json.dumps(cfg['agent']))
            cfg['web']['extract_timeout']=99;config.atomic_config_write(path,cfg)
        elif mode=='revoke-config':
            time.sleep(.3)
            cfg['plugins']['entries']['friday_rework']['settings']['admin']['operators']=[{'provider':'basic','user_id':'replacement-owner','org_id':''}]
            config.atomic_config_write(path,cfg)
        elif mode=='expire-config':time.sleep(1.3)
        else:release()
elif mode=='plugin-writer':
    original=config.atomic_config_replace
    def marked(*args,**kwargs):
        (home/'child-entered').touch()
        return original(*args,**kwargs)
    config.atomic_config_replace=marked
    from hermes_cli.plugins_state import save_plugin_setting
    save_plugin_setting('friday_rework',('unrelated_review_flag',),True)
elif mode=='hold-cron':
    from cron import jobs
    with jobs._jobs_lock():
        (home/'child-entered').touch();release()
else:raise ValueError(mode)
(home/'child-done').touch()
print(json.dumps({'mode':mode,'pid':os.getpid(),'finished':True}))
