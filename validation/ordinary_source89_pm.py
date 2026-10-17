"""Independent public source-refresh controls with real native copying/locks/facts.

Only dependency-engine effects are stubbed. All root, workspace, generation and
selection state belongs to this script's private fixture directory.
"""
import contextlib
import hashlib
import json
import os
import stat
from pathlib import Path
import shutil
import sys
import threading
import tempfile
from unittest.mock import patch

source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(source))
import pm
import pm.client as client
import pm.environments as envs
import pm.install as install
from pm.lock import Facts
from pm.packages import Venv
import pm.workspace as workspace
import hermes_cli.runtime_state as runtime

AREA = tempfile.TemporaryDirectory(prefix='friday-pm-source-refresh-')
ROOT = Path(AREA.name)
results = []

class Fixture:
    def __init__(self, name):
        self.area = ROOT / name
        if self.area.exists():
            shutil.rmtree(self.area)
        self.root = self.area / 'source'
        self.state = self.area / 'install'
        self.root.mkdir(parents=True)
        self.state.mkdir()
        (self.root / 'app').mkdir()
        (self.root / 'app' / 'dist').mkdir()
        (self.root / 'app' / '__init__.py').write_text("VALUE = 'old'\n")
        (self.root / 'app' / 'dist' / 'asset.js').write_text('original asset\n')
        (self.root / 'pyproject.toml').write_text('''[project]
name = "hermes-agent"
version = "0.0.0"
requires-python = ">=3.11"
[tool.setuptools.packages.find]
include = ["app*"]
''')
        (self.root / 'uv.lock').write_text('version = 1\nrevision = 1\n')
        (self.root / 'pm').mkdir()
        (self.root / 'pm' / 'lock.json').write_text('{"schema":1,"packages":{}}\n')
        self.factsfile = self.state / 'facts.json'
        self.old = self.state / 'environments' / 'legacy'
        self.old.mkdir(parents=True)
        self.work = self.old / 'workspace'
        workspace._generate_pyproject([], self.work, source=self.root)
        (self.work / 'uv.lock').write_bytes((self.root / 'uv.lock').read_bytes())
        (self.old / 'venv').mkdir()
        (self.old / 'venv' / 'pyvenv.cfg').write_text('fixture = true\n')
        self.package = Venv(self.root)
        self.creates = 0
        self.mode = None
        self.pause = threading.Event()
        self.extra_action = None
        self.stack = contextlib.ExitStack()
        for obj, key, value in [
            (pm.paths, 'repo_root', lambda: self.root),
            (pm.paths, 'runtime_facts_path', lambda: self.factsfile),
            (pm.paths, 'lockfile_path', lambda: self.root / 'pm' / 'lock.json'),
            (envs, 'install_state_dir', lambda root: self.state),
            (envs, 'runtime_facts_path', lambda root: self.factsfile),
            (runtime, 'install_state_dir', lambda root: self.state),
            (workspace, 'enabled_member_dirs', lambda: []),
            (pm.registry, 'get_package', lambda name: self.package),
            (client, 'is_runtime', lambda: True),
        ]:
            self.stack.enter_context(patch.object(obj, key, value))
        self.stack.enter_context(patch('pm.native_build.source_build_environment', return_value={}))
        self.stack.enter_context(patch('pm.plugins_state.enabled_plugins_ordered', return_value=[]))
        self.stack.enter_context(patch('pm.environments.flush_before_selecting', side_effect=self.flush))
        self.stack.enter_context(patch('pm.environment.managed_environment', side_effect=self.make_engine))
        self.stamp = self.package.expected_stamp([], plugin_dirs=[])
        Facts(self.factsfile).record_state('venv', self.stamp, [], environment=self.old/'venv', resolved_lock=self.work/'uv.lock')
        self.previous = pm.source_identity(self.work)
        assert 'source_identity' not in self.fact()

    def __enter__(self): return self
    def __exit__(self, *exc): self.stack.close()
    def fact(self): return Facts(self.factsfile, strict=True).get('venv')
    def digest(self): return hashlib.sha256(self.factsfile.read_bytes()).hexdigest()
    def modify(self, value='new'):
        (self.root/'app'/'__init__.py').write_text('VALUE = '+repr(value)+'\n')
    def flush(self):
        if self.mode == 'flush-source-drift': self.modify('changed-during-flush')
    def make_engine(self, candidate, **kw):
        fixture = self
        class Engine:
            executable = Path(candidate) / 'bin' / 'python'
            env = {}
            def create(self):
                fixture.creates += 1
                Path(candidate).mkdir(parents=True)
                (Path(candidate)/'pyvenv.cfg').write_text('fixture = true\n')
            def sync(self, root, **kw):
                assert kw['extras'] == [] and kw['frozen'] is True
                if fixture.mode == 'build-error': raise RuntimeError('independent engine failure')
                if fixture.mode == 'cancel': fixture.pause.set()
                if fixture.mode == 'source-drift': fixture.modify('changed-mid-build')
                if fixture.mode == 'lock-drift':
                    with (fixture.root/'uv.lock').open('a') as out: out.write('\nrequires-python = ">=3.12"\n')
                if fixture.extra_action: fixture.extra_action()
            def check(self): pass
        return Engine()
    def refresh(self, **overrides):
        args={'expected_source':pm.source_identity(self.root),'expected_previous_source':self.previous,
              'expected_environment':str(self.old/'venv'),'project_root':self.root,'pause_event':self.pause}
        args.update(overrides)
        return pm.refresh_source(**args)
    def reject(self, **kwargs):
        before=self.digest()
        generations=set((self.state/'environments').iterdir())
        try: self.refresh(**kwargs)
        except (RuntimeError, ValueError, pm.InstallError) as exc:
            assert self.digest()==before, 'rejected request changed committed selection'
            assert set((self.state/'environments').iterdir())==generations, 'precommit failure leaked an owned candidate'
            return type(exc).__name__,str(exc)
        raise AssertionError('request unexpectedly published')

def check(name, run):
    with Fixture(name) as f:
        detail=run(f)
    results.append({'case':name,'state':'PASS','detail':detail})

def unchanged(f):
    result=f.refresh()
    assert result['state']=='current' and f.creates==0
    return result
check('legacy-unchanged-no-generation', unchanged)

def changed(f):
    before=f.fact(); f.modify()
    assert f.package.expected_stamp([],plugin_dirs=[])==before['stamp']
    result=f.refresh(); after=f.fact()
    assert result['state']=='rebuilt' and after['environment']!=before['environment']
    assert after['stamp']==before['stamp'] and after['extras']==before['extras']
    assert after['source_parent']==f.previous
    assert pm.source_identity(Path(after['resolved_lock']).parent)==pm.source_identity(f.root)
    assert (Path(after['resolved_lock']).parent/'app'/'__init__.py').read_bytes()==(f.root/'app'/'__init__.py').read_bytes()
    assert Path(before['environment']).exists()
    # Stale queued request cannot replace the verified new selection.
    return {'published':result,'stale':f.reject(expected_source=after['source_identity'])}
check('changed-bytes-same-graph-public-selection', changed)
check('forged-candidate-source', lambda f: f.reject(expected_source='0'*64))
check('wrong-previous-source', lambda f: f.reject(expected_previous_source='f'*64))
check('wrong-environment-cas', lambda f: f.reject(expected_environment=str(f.old/'foreign')))

def bad_fact(f):
    row=f.fact(); row['source_identity']='0'*64
    data=json.loads(f.factsfile.read_text());data['packages']['venv']=row
    f.factsfile.write_text(json.dumps(data))
    return f.reject()
check('forged-recorded-source-fact', bad_fact)

def metadata(f):
    with (f.root/'pyproject.toml').open('a') as out:out.write('\n[tool.fixture]\noption = true\n')
    return f.reject()
check('changed-build-options',metadata)

def pre_cancel(f):
    f.modify();f.pause.set();return f.reject()
check('cancel-before-build',pre_cancel)

for mode in ['build-error','cancel','source-drift','lock-drift','flush-source-drift']:
    def run(f,mode=mode):
        f.modify();f.mode=mode
        return f.reject()
    check(mode,run)

def assets(f):
    first=pm.source_identity(f.root)
    (f.root/'ignored.txt').write_text('not a native build input\n')
    assert pm.source_identity(f.root)==first
    (f.root/'app'/'dist'/'asset.js').write_text('new shipped asset\n')
    assert pm.source_identity(f.root)!=first
    return 'nested dist asset changes core identity; unrelated root text excluded'
check('actual-native-input-projection',assets)

def symlink_custody(f):
    moved=f.area/'foreign-workspace'
    f.work.rename(moved);f.work.symlink_to(moved,target_is_directory=True)
    return f.reject()
check('selected-workspace-symlink-ancestry-rejected',symlink_custody)

def metadata_symlink(f):
    metadata=f.root/'pyproject.toml';moved=f.area/'foreign-pyproject.toml'
    metadata.rename(moved);metadata.symlink_to(moved)
    try: pm.source_identity(f.root)
    except ValueError as exc:return str(exc)
    raise AssertionError('symlink metadata identity unexpectedly accepted')
check('source-metadata-symlink-rejected',metadata_symlink)

def uncertain_publication(f):
    import pm.filesystem as fs
    f.modify('postreplace-candidate')
    original_replace=fs.os.replace;original_fsync=fs.os.fsync
    observed={'facts_replaced':False,'fault_injected':False}
    def replace(left,right):
        result=original_replace(left,right)
        if Path(right)==f.factsfile:observed['facts_replaced']=True
        return result
    def fsync(fd):
        if observed['facts_replaced'] and not observed['fault_injected'] and stat.S_ISDIR(os.fstat(fd).st_mode):
            observed['fault_injected']=True
            raise OSError('independent actual facts-directory fsync fault')
        return original_fsync(fd)
    with patch.object(fs.os,'replace',side_effect=replace),patch.object(fs.os,'fsync',side_effect=fsync):
        try:f.refresh()
        except pm.InstallError as exc:assert 'STOP_UNCONFIRMED' in str(exc),str(exc)
        else:raise AssertionError('postreplace fault was not reported')
    assert observed['fault_injected']
    selected=Path(f.fact()['environment']);assert selected!=f.old/'venv'
    assert selected.is_dir() and (selected.parent/'workspace/app/__init__.py').read_bytes()==(f.root/'app/__init__.py').read_bytes()
    assert (f.old/'venv').is_dir()
    count=f.creates;identity=pm.source_identity(f.root)
    reconciled=f.refresh(expected_previous_source=identity,expected_environment=str(selected))
    assert reconciled['state']=='current' and f.creates==count
    return {'fault':observed,'selected_candidate_retained':True,'old_generation_retained':True,'reconciled_without_rebuild':True}
check('actual-postreplace-directory-fsync-uncertainty',uncertain_publication)

for fault in ['receipt','finalize']:
    def run(f,fault=fault):
        from pm import receipt
        f.modify('committed-'+fault)
        function='record_venv_rebuild' if fault=='receipt' else 'finalize'
        original=getattr(receipt,function)
        def fail(*args,**kw):
            original(*args,**kw)
            raise OSError('independent postcommit '+fault+' fault')
        with patch.object(receipt,function,side_effect=fail):
            try:f.refresh()
            except OSError:pass
            else:raise AssertionError('postcommit fault was not reported')
        selected=Path(f.fact()['environment'])
        assert selected!=f.old/'venv' and selected.is_dir() and (f.old/'venv').is_dir()
        assert pm.source_identity(selected.parent/'workspace')==pm.source_identity(f.root)
        return 'verified selected candidate and old generation both retained'
    check('postcommit-'+fault+'-error',run)

def empty_namespace(f):
    empty=f.root/'app/ns/empty';empty.mkdir(parents=True);empty.chmod(0o750)
    destination=f.area/'copy-result';destination.mkdir()
    workspace._copy_core_inputs(f.root,destination)
    copied=destination/'app/ns/empty'
    assert copied.is_dir() and stat.S_IMODE(copied.stat().st_mode)==0o750
    return 'original empty namespace directories/modes preserved'
check('copier-empty-namespace-modes-preserved',empty_namespace)

def nested_destination(f):
    (f.root/'pyproject.toml').write_text('[project]\nname="fixture"\nversion="0.0.0"\n')
    destination=f.root/'nested-destination';destination.mkdir()
    workspace._copy_core_inputs(f.root,destination)
    assert (destination/'app/__init__.py').is_file()
    assert not (destination/'nested-destination').exists()
    return 'default package finder excludes own destination as before'
check('copier-own-nested-destination-excluded',nested_destination)

loaded={}
for name in ['pm', 'pm.client', 'pm.lock', 'pm.source_refresh', 'pm.workspace', 'pm.packages', 'pm.environments']:
    module=sys.modules.get(name)
    if module is None:continue
    path=Path(module.__file__).resolve()
    assert path.is_relative_to(source), (name,str(path),str(source))
    loaded[name]={'source':str(path.relative_to(source)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
print(json.dumps({'schema':'friday.independent-pm-controls.v1','state':'PASS','loaded_source_pins':loaded,'cases':results,
 'seams':['real public pm.refresh_source facade/client direct-runtime route','real native Venv.apply workspace generation and copy','real runtime lock and atomic Facts selection','dependency engine create/sync/check stubbed; no dependency install/model/network','os.sync replaced to avoid host-wide flush; post-flush source drift injected']},indent=2))

AREA.cleanup()
