"""Actual source options -> shipped UI -> mounted API -> typed edit; private synthetic stores.

Native config/auth/skills contracts and SDK transport are explicit fixtures; no
native import, real identity, SDK/auth acceptance, network socket or DB is used.
"""
import asyncio
import contextlib
import copy
import importlib.util
import json
import subprocess
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]


def projection_modules():
    return {name:module for name,module in sys.modules.items()
            if name == '_friday_dashboard_projection' or name.startswith('_friday_dashboard_projection.')}


@contextlib.contextmanager
def isolated_projection_modules():
    previous=projection_modules()
    for name in previous:sys.modules.pop(name,None)
    try:
        yield
    finally:
        for name in projection_modules():sys.modules.pop(name,None)
        sys.modules.update(previous)

@pytest.fixture
def contract(tmp_path, monkeypatch):
    home = tmp_path / 'synthetic-home'; home.mkdir(mode=0o700)
    cfg = {'model': {'provider': 'custom:fixture', 'default': 'fixture-model'},
           'providers': {'fixture': {'transport': 'chat_completions', 'api': 'http://127.0.0.1:8001/v1',
                'key_env': 'SYNTHETIC_LOCAL_KEY', 'models': {'fixture-model': {}}}},
           'agent': {'max_turns': 30}, 'streaming': {'enabled': False},
           'tools': {'tool_search': {'enabled': 'off', 'defer': ['fixture_existing_tool']}},
           'original_budget': {'expired': True, 'seconds': 180},
           'retained_canary': {'model': 'unchanged', 'clock': 'original-closed-clock'}}
    path = home / 'config.yaml'
    def write(p, v): p.write_text(json.dumps(v, sort_keys=True)); p.chmod(0o600)
    write(path, cfg)
    def mod(name, **attrs):
        m = ModuleType(name); m.__dict__.update(attrs); monkeypatch.setitem(sys.modules, name, m); return m
    native = mod('hermes_cli'); native.__path__ = []
    config = mod('hermes_cli.config', is_managed=lambda:False,
        config_write_transaction=lambda p:contextlib.nullcontext(),
        require_readable_config_before_write=lambda p=path:json.loads(p.read_text()),
        load_config_readonly=lambda:json.loads(path.read_text()),
        atomic_config_write=write, DEFAULT_CONFIG={},
        _merge_managed_overlay=lambda v:(v,{}), _expand_env_vars=lambda v:v,
        _canonicalize_config=lambda v:v, _deep_merge=lambda a,b:copy.deepcopy(b),
        redact_config_value=lambda v:v)
    native.config=config
    native.managed_scope=mod('hermes_cli.managed_scope', is_key_managed=lambda k:False)
    access=mod('hermes_cli.friday_product_access', KEY='synthetic-key',
        admin_policy=lambda:{'profiles':['default']}, access_policy=lambda:None,
        current_access=lambda state:{'users':{}}, principal_id=lambda *a:'synthetic',
        validate_access=lambda v:None, profile_name=lambda p:p, settings=lambda:{},
        session_allowed=lambda s:s == 'native-verified-synthetic-session')
    mod('hermes_cli.profiles', get_profile_dir=lambda p:home)
    mod('hermes_constants', get_process_hermes_home=lambda:home, get_hermes_home=lambda:home,
        set_hermes_home_override=lambda p:None, reset_hermes_home_override=lambda token:None)
    mod('toolsets', get_toolset_names=lambda:['web'])
    mod('tools.skills_tool', _find_all_skills=lambda **kw:[])
    agent=mod('agent');agent.__path__=[]
    mod('agent.skill_utils', ESSENTIAL_SKILLS=set())
    mod('agent.redact', redact_for_egress=lambda v:v)
    class ToolSearchConfig:
        @staticmethod
        def from_raw(raw):return SimpleNamespace(effective_defer_tools=set((raw or {}).get('defer',[])))
    mod('tools.tool_search',ToolSearchConfig=ToolSearchConfig)
    with isolated_projection_modules():
        # Load the complete production API, Administration, options and edit code.
        spec=importlib.util.spec_from_file_location('source_v5_dashboard_api',ROOT/'plugins/friday_rework/dashboard/api.py')
        api=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,api);spec.loader.exec_module(api)
        onboarding=ModuleType('_friday_dashboard_projection.onboarding')
        onboarding.prepare_admin_config_edit=lambda h,v:None
        onboarding.finish_admin_config_edit=lambda h,v:None
        sys.modules[onboarding.__name__]=onboarding
        app=FastAPI();app.state.auth_required=True
        app.include_router(api.router,prefix='/api/plugins/friday_rework')
        @app.middleware('http')
        async def synthetic_native_session(request, call_next):
            request.state.session='native-verified-synthetic-session' if request.headers.get('X-Synthetic-Native-Session')=='verified' else None
            return await call_next(request)
        yield SimpleNamespace(home=home,path=path,api=api,app=app,config=config,access=access)

def ui(effective, fields, force=False):
    payload={'action':'settings','kind':'operational','fields':fields,'effective':effective,
        'force_disabled_save':force}
    node=shutil.which('node') or str(Path.home()/'.local/bin/node')
    result=subprocess.run([node,'--disable-wasm-trap-handler',
        '--max-old-space-size=256',str(ROOT/'tests/dashboard_v5_source_driver.cjs'),
        str(ROOT/'plugins/friday_rework/dashboard/index.js')],input=json.dumps(payload),
        capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    output=json.loads(result.stdout)
    return output,[r for r in output['requests'] if r['method']=='PUT']

def scenario(contract, callback):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=contract.app),
                base_url='http://synthetic.invalid',headers={'X-Synthetic-Native-Session':'verified'}) as client:
            effective=await client.get('/api/plugins/friday_rework/effective?profile=default')
            assert effective.status_code==200,effective.text
            await callback(client,effective.json())
    asyncio.run(run())

@pytest.mark.parametrize('key,value,expected',[
    ('agent.max_turns','1',1),('agent.max_turns','200',200),
    ('streaming.enabled',True,True),('streaming.enabled',False,False),
    ('tools.tool_search.enabled',None,'off'),
    ('tools.tool_search.defer',None,['fixture_existing_tool','read_file','session_search'])])
def test_source_producer_shipped_control_real_api_and_writer(contract,key,value,expected):
    async def check(client,effective):
        before=json.loads(contract.path.read_text());fields={'key':key}
        if value is not None:fields['enabled' if type(value)is bool else 'value']=value
        output,writes=ui(effective,fields);assert len(writes)==1
        body=json.loads(writes[0]['body']);assert body=={'kind':'operational',
            'expected_sha256':effective['config_sha256'],'values':{'key':key,'value':expected}}
        response=await client.put(writes[0]['url'],json=body);assert response.status_code==200,response.text
        answer=response.json();assert answer['recorded']is True and answer['observed_live_reload']is False
        assert answer['active_worker_binding']=='UNCHANGED_ORIGINAL_BUDGET'
        after=json.loads(contract.path.read_text());cursor=after
        for part in key.split('.'):cursor=cursor[part]
        assert cursor==expected and type(cursor)is type(expected)
        assert after['original_budget']==before['original_budget'] and after['retained_canary']==before['retained_canary']
        # A second identical write may be a legitimate no-op; verify stale CAS
        # against a distinct subsequent native synthetic change.
        after['retained_canary']['clock']='later-foreign-state';contract.config.atomic_config_write(contract.path,after)
        retained=contract.path.read_bytes();again=await client.put(writes[0]['url'],json=body)
        assert again.status_code==400 and contract.path.read_bytes()==retained
    scenario(contract,check)

@pytest.mark.parametrize('key,value',[
    ('agent.max_turns',True),('agent.max_turns',0),('agent.max_turns',201),
    ('streaming.enabled',0),('streaming.enabled','false'),
    ('tools.tool_search.enabled','on'),('tools.tool_search.defer',['read_file','session_search']),
    ('tools.tool_search.defer',['fixture_existing_tool','read_file','session_search','read_file']),
    ('tools.tool_search.defer',['fixture_existing_tool','read_file','session_search','arbitrary_tool'])])
def test_real_api_refuses_typed_tampering_without_publication(contract,key,value):
    async def check(client,effective):
        before=contract.path.read_bytes();response=await client.put('/api/plugins/friday_rework/settings?profile=default',
            json={'kind':'operational','expected_sha256':effective['config_sha256'],'values':{'key':key,'value':value}})
        assert response.status_code==400 and contract.path.read_bytes()==before
    scenario(contract,check)

@pytest.mark.parametrize('fault',['missing_specs','wrong_bool','wide_enum','missing_required_defer','duplicate_defer','missing_sha'])
def test_producer_metadata_tamper_blocks_shipped_ui_even_forced(contract,fault):
    async def check(client,effective):
        key='tools.tool_search.enabled';specs=effective['typed_options']['operational_specs']
        if fault=='missing_specs':effective['typed_options'].pop('operational_specs')
        elif fault=='wrong_bool':key='streaming.enabled';specs[key]={'type':'string'}
        elif fault=='wide_enum':specs[key]['enum'].append('on')
        elif fault=='missing_required_defer':key='tools.tool_search.defer';specs[key]['const']=['read_file']
        elif fault=='duplicate_defer':key='tools.tool_search.defer';specs[key]['const'].append('read_file')
        else:effective.pop('config_sha256')
        before=contract.path.read_bytes();output,writes=ui(effective,{'key':key},force=fault!='missing_sha')
        assert writes==[] and contract.path.read_bytes()==before
    scenario(contract,check)

@pytest.mark.parametrize('fault',['unauthorized','ungated','foreign_profile','missing_cas','extra_top_field'])
def test_existing_source_authority_and_request_schema_fail_closed(contract,fault):
    async def check(client,effective):
        url='/api/plugins/friday_rework/settings?profile='+('foreign' if fault=='foreign_profile' else 'default')
        body={'kind':'operational','expected_sha256':effective['config_sha256'],
            'values':{'key':'agent.max_turns','value':17}}
        if fault=='unauthorized':client.headers['X-Synthetic-Native-Session']='denied'
        elif fault=='ungated':contract.app.state.auth_required=False
        elif fault=='missing_cas':body.pop('expected_sha256')
        elif fault=='extra_top_field':body['identity']='invented'
        before=contract.path.read_bytes();response=await client.put(url,json=body)
        assert response.status_code==(422 if fault in ('missing_cas','extra_top_field') else 403)
        assert contract.path.read_bytes()==before
    scenario(contract,check)


@pytest.mark.parametrize('prior',['absent','existing'])
def test_fixture_teardown_restores_exact_projection_namespace(tmp_path,monkeypatch,prior):
    original=projection_modules()
    # Exercise the complete fixture lifecycle, including plain source imports.
    # Existing objects must survive with their identity; newly imported source
    # modules must release the synthetic home and native fixture references.
    try:
        for name in projection_modules():sys.modules.pop(name,None)
        if prior=='existing':
            for name in ('_friday_dashboard_projection','_friday_dashboard_projection.admin',
                         '_friday_dashboard_projection.onboarding'):
                sys.modules[name]=ModuleType(name)
        expected=projection_modules()
        with monkeypatch.context() as native_contract:
            fixture=contract.__wrapped__(tmp_path,native_contract)
            env=next(fixture)
            assert env.api._admin.launch_home==env.home
            assert projection_modules() and all(module not in expected.values() for module in projection_modules().values())
            with pytest.raises(StopIteration):next(fixture)
            actual=projection_modules()
            assert actual.keys()==expected.keys()
            assert all(actual[name]is module for name,module in expected.items())
        # Native-stub monkeypatch undo must not delete restored projection leaves.
        actual=projection_modules()
        assert actual.keys()==expected.keys()
        assert all(actual[name]is module for name,module in expected.items())
    finally:
        for name in projection_modules():sys.modules.pop(name,None)
        sys.modules.update(original)
