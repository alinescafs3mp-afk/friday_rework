import sys, os, runpy
from pathlib import Path
root=Path(os.environ['FRIDAY_TEST_SANDBOX']).resolve()
native=Path(os.environ['FRIDAY_TEST_NATIVE']).resolve()
root.mkdir(mode=0o700, parents=True, exist_ok=True)
Path.home=classmethod(lambda cls: root/'os-home')
for name in ('os-home','cache','runtime','tmp'):(root/name).mkdir(mode=0o700,exist_ok=True)
os.environ['XDG_CACHE_HOME']=str(root/'cache')
os.environ['HERMES_RUNTIME_DIR']=str(root/'runtime')
os.environ['XDG_CONFIG_HOME']=str(root/'os-home'/'config')
os.environ['XDG_DATA_HOME']=str(root/'os-home'/'data')
if os.environ.get('FRIDAY_TEST_EXTRA_SITE'):
    sys.path.append(os.environ['FRIDAY_TEST_EXTRA_SITE'])
sys.executable=os.environ['FRIDAY_TEST_WRAPPER']
sys.dont_write_bytecode=True
os.environ['HERMES_HOME']=str(root/'test-home')
os.environ['TMPDIR']=str(root/'test-tmp')
os.environ['HERMES_GATEWAY_LOCK_DIR']=str(root/'test-locks')
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
for name in ('test-home','test-tmp','test-locks'):
    (root/name).mkdir(exist_ok=True)
sys.path.insert(0,str(native))
sys.path.append(str(native/'tests'))
args=sys.argv[1:]
while args and args[0] in ('-B','-E','-s','-u'):
    args.pop(0)
if args[:1]==['-c']:
    sys.argv=['-c',*args[2:]]
    exec(compile(args[1],'<command>','exec'),{'__name__':'__main__'})
elif args[:1]==['-m']:
    module=args[1]
    sys.argv=[module,*args[2:]]
    if module=='pytest':
        sys.argv += ['-p','pytest_asyncio.plugin','-o','addopts=']
    runpy.run_module(module,run_name='__main__',alter_sys=True)
else:
    sys.argv=args
    runpy.run_path(args[0],run_name='__main__')
