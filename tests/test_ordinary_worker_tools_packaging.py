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
    if profile=='disabled':
        assert web.dsh_web_patch(profile)==[]
        assert next(r for r in rows if r.get('id')=='tool-web')['disabled'] is True
    else:
        expected=web.dsh_web_patch(profile)
        assert [r for r in rows if r.get('id') in ('web','web-fetch-http','tool-web') or 'insert' in r]==expected


@pytest.mark.parametrize('change',[{'base_url':'https://public.example/v1'},{'max_tokens':True},{'context_window':100},{'web_profile':'ambient'}])
def test_renderer_refuses_unreviewed_route_profile_or_bounds(change):
    with pytest.raises(ValueError):render.build_patch(**(KW|change))
