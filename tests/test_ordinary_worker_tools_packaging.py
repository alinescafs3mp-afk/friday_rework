"""Run against the composed native source, in a fresh process outside the project.

No package path extension is allowed: the existing regular tools package owns
both helpers and their shipped relative research resource.
"""
from pathlib import Path
import hashlib
import json

import pytest
import tools
from tools import render_dsh_local as render, web_profile as web

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=json.loads((ROOT/'patches/hermes/ordinary-worker-tools-packaging-manifest.json').read_text())
ROWS={r['path']:r for r in MANIFEST['files']}
SANDBOX_MANIFEST=ROOT/'patches/hermes/ordinary-dsh-native-sandbox-profile-manifest.json'
if SANDBOX_MANIFEST.is_file():
    sandbox_rows=json.loads(SANDBOX_MANIFEST.read_text())['files']
    expected_before={'tools/render_dsh_local.py':ROWS['tools/render_dsh_local.py']['sha256']}
    if len(sandbox_rows)==2:
        expected_before['gateway/run_turn_runner.py']='0d3c581cdb61bd2da8faedfa798f2419b7c8e59dfcc105ce5b259442db50e11e'
    assert len(sandbox_rows)==len(expected_before)
    assert {r['path']:r['before_sha256'] for r in sandbox_rows}==expected_before
    sandbox_row=next(r for r in sandbox_rows if r['path']=='tools/render_dsh_local.py')
    assert sandbox_row['path']=='tools/render_dsh_local.py'
    assert sandbox_row['before_sha256']==ROWS['tools/render_dsh_local.py']['sha256']
    ROWS[sandbox_row['path']]=sandbox_row
KW=dict(purpose='temporary-local-test',api='openai-completions',base_url='http://127.0.0.1:8011/v1',model='offline-fixture',context_window=40960,max_tokens=4096,summary_max_tokens=2048,headroom_tokens=4096)


def test_existing_regular_package_resolves_exact_shipped_helpers_and_resource():
    root=Path(tools.__file__).resolve().parents[1]
    assert Path(tools.__file__).name=='__init__.py'
    for module,name in ((render,'tools/render_dsh_local.py'),(web,'tools/web_profile.py')):
        assert Path(module.__file__).resolve()==root/name
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()==ROWS[name]['sha256']
    resource=root/'config/RESEARCH.md'
    assert hashlib.sha256(resource.read_bytes()).hexdigest()==ROWS['config/RESEARCH.md']['sha256']
    assert web.research_policy()==resource.read_text().strip()


@pytest.mark.parametrize('profile',['disabled','exa-paid','exa-keyless'])
def test_exact_renderer_profiles_are_native_and_keep_inference_rows(profile):
    rows=render.build_patch(**KW,web_profile=profile)
    baseline=render.build_patch(**KW)
    assert rows[:3]==baseline[:3]
    if SANDBOX_MANIFEST.is_file():
        sandbox={'id':'sandbox','config':{'runnerCommand':['/usr/bin/bwrap'],
                                         'runnerFailureSignatures':['bwrap: ']}}
        assert rows[3]==sandbox
        assert [r for r in rows if r.get('id')=='sandbox']==[sandbox]
    if profile=='disabled':
        assert web.dsh_web_patch(profile)==[]
        assert next(r for r in rows if r.get('id')=='tool-web')['disabled'] is True
    else:
        expected=web.dsh_web_patch(profile)
        assert [r for r in rows if r.get('id') in ('web','web-fetch-http','tool-web') or 'insert' in r]==expected


@pytest.mark.parametrize('change',[{'base_url':'https://public.example/v1'},{'max_tokens':True},{'context_window':100},{'web_profile':'ambient'}])
def test_renderer_refuses_unreviewed_route_profile_or_bounds(change):
    with pytest.raises(ValueError):render.build_patch(**(KW|change))
