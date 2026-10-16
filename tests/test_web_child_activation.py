"""Real cold child entry and PM activation; offline dependency-consumer seam."""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from tests.hermes_cli.test_source_launcher_publication import fixture_tree, select_generation
from pm.environments import install_state_dir

# Explicit disposable source roots; never infer an installed user runtime.
N = Path(os.environ['FRIDAY_TEST_NATIVE']).resolve()
PREVIOUS = Path(os.environ['FRIDAY_TEST_PREVIOUS_NATIVE']).resolve()


def prepared(tmp_path, monkeypatch, browser, generation=1):
    repo, home, interpreter = fixture_tree(tmp_path, monkeypatch)
    selected = select_generation(repo, generation, 'generation-'+str(generation))
    (repo/'agent').mkdir(); (repo/'agent/__init__.py').write_text('')
    (repo/'tools').mkdir(); (repo/'tools/__init__.py').write_text('')
    shutil.copyfile(N/'agent/web_call_context.py', repo/'agent/web_call_context.py')
    name = 'browser_process_child.py' if browser else 'web_process_child.py'
    entry=repo/'tools'/name
    shutil.copyfile(Path(importlib.util.find_spec('tools.' + name[:-3]).origin), entry)
    # All entrypoint/PM bytes are real. Stop at the first third-party consumer:
    # this is a runtime-activation test, not provider or authorization acceptance.
    probe=repo/('hermes_cli/friday_user_scope.py' if browser else 'agent/secret_scope.py')
    probe.write_text('import json, selected_probe\n'
                    'print(json.dumps({"selected":selected_probe.VALUE}), flush=True)\n'
                    'raise SystemExit(23)\n')
    data={'home':str(home),'deadline':time.monotonic()+30,
          **({'start':True} if browser else {'tool':'web_extract','args':{'urls':['https://example.com/']}})}
    env={'HOME':str(tmp_path),'HERMES_HOME':str(home),'PATH':os.defpath,'LANG':'C.UTF-8'}
    return repo,home,interpreter,selected,entry,data,env


@pytest.mark.parametrize('browser', [False,True])
@pytest.mark.parametrize('generation', [1,2])
def test_real_child_activates_committed_dependency_before_consumer(tmp_path,monkeypatch,browser,generation):
    repo,home,interpreter,selected,entry,data,env=prepared(tmp_path,monkeypatch,browser,generation)
    before=entry.read_bytes()
    result=subprocess.run([str(interpreter),'-I','-B',str(entry)],
        input=json.dumps(data)+'\n',env=env,cwd=home,capture_output=True,text=True,timeout=15)
    # The trusted main catches SystemExit too; stdout is the scoped consumer
    # witness, not a claim of a completed provider call.
    assert json.loads(result.stdout)=={'selected':'generation-'+str(generation)}
    assert result.returncode==1
    assert entry.read_bytes()==before
    assert not list(repo.rglob('*.pyc'))


@pytest.mark.parametrize('browser', [False,True])
@pytest.mark.parametrize('fault', ['missing','foreign','expired','wrong-home'])
def test_invalid_dependency_or_input_does_not_reach_consumer(tmp_path,monkeypatch,browser,fault):
    repo,home,interpreter,selected,entry,data,env=prepared(tmp_path,monkeypatch,browser)
    if fault=='missing':
        (selected/'pyvenv.cfg').unlink()
    elif fault=='foreign':
        foreign=tmp_path/'foreign';foreign.mkdir();(foreign/'pyvenv.cfg').write_text('home = fixture\n')
        (install_state_dir(repo)/'facts.json').write_text(json.dumps({'packages':{'venv':{'environment':str(foreign)}}}))
    elif fault=='expired':data['deadline']=time.monotonic()-1
    else:data['home']=str(tmp_path/'other-profile')
    result=subprocess.run([str(interpreter),'-I','-B',str(entry)],
        input=json.dumps(data)+'\n',env=env,cwd=home,capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and not result.stdout
    assert not list(repo.rglob('*.pyc'))


@pytest.mark.parametrize('browser', [False,True])
def test_original_child_cannot_import_selected_dependency(tmp_path,monkeypatch,browser):
    repo,home,interpreter,selected,entry,data,env=prepared(tmp_path,monkeypatch,browser)
    shutil.copyfile(PREVIOUS/'tools'/entry.name,entry)
    result=subprocess.run([str(interpreter),'-I','-B',str(entry)],
        input=json.dumps(data)+'\n',env=env,cwd=home,capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and not result.stdout
