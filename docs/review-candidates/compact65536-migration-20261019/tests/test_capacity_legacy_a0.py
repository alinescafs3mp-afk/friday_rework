"""Synthetic native composer/spec validators; no install or admission effects."""
import copy
import pytest
from tools.configure_product import compose_product
from scripts import friday_install as entry
from plugins.friday_rework.adapters.a0_profile import legacy_profile
from plugins.friday_rework.host_runtime import configured_runtimes


def capacity_spec():
    spec = split_inputs()
    spec['compression_inference'].update(context=65536, max_input=65530)
    spec['a0_deployment'] = legacy_profile()
    return spec


def active_a0(tmp_path, deployment):
    pin = {'path':str(tmp_path/'unqueried-pin'), 'sha256':'a'*64}
    web = dict(profile='searxng-google',timeout_seconds=10,dns=['8.8.8.8'],version='synthetic-v1',image='sha256:'+'b'*64,
        source_pins={'/exe/run_searxng.sh':'a'*64,
        '/usr/local/searxng/searxng-src/searx/webapp.py':'a'*64,
        '/usr/local/searxng/searxng-src/searx/settings_loader.py':'a'*64,
        '/a0/helpers/searxng.py':'4020eca255497dbf95076166ebefaff14a095abafaff69cb6176a8ae31c2fcc2',
        '/a0/tools/search_engine.py':'c13c14560d0ac1947b63ed1ad795bd2fad5e026673d2cc615f34ef6da57a9efb'})
    value=dict(enabled=True,runtime_profile='default',runtime_home=str(tmp_path/'product'),
        workspace_root=str(tmp_path/'workspace'),staging_root=str(tmp_path/'staging'),cache_roots=[str(tmp_path/'cache')],
        budget_seconds=60,max_file_bytes=1024,max_total_bytes=4096,runtime_receipt=copy.deepcopy(pin),
        a0={**{k:copy.deepcopy(pin) for k in ('runtime','launcher','docker','daemon_unit','policy')},
            'git_metadata':{'source':str(tmp_path/'metadata'),'manifest_sha256':'b'*64},
            'expected_files':[{'logical_name':'result.txt','media_type':'text/plain'}],
            'capability':None,'owner_slot':'sol','deployment':copy.deepcopy(deployment),'web':web})
    assert set(configured_runtimes(value)) == {'a0'}
    return value


@pytest.fixture(params=['compose', 'spec_checked'])
def consumer(request, install_input):
    def apply(spec):
        if request.param == 'compose':return compose_product(spec)
        install_input['product'] = spec
        return entry.spec_checked(install_input)
    return apply


def test_exact_retained_inactive_legacy_and_new_capacity(consumer):
    spec=capacity_spec(); before=copy.deepcopy(spec)
    result=consumer(spec)
    assert spec==before
    assert spec['a0_deployment']==legacy_profile()
    if isinstance(result,dict):
        config=result['config']
        assert config['a0_deployment']==legacy_profile()
        assert config['model']['context_length']==262144
        assert config['auxiliary']['compression']['context_length']==65536
        assert config['providers']['friday-compression']['models']['dispatcher']['bounded_context']['server_max_input_tokens']==65530


@pytest.mark.parametrize('fault',['active_a0','other_context','other_input','different_name','different_endpoint','different_model','different_output','different_main_capacity','different_summary','different_margin','different_overhead'])
def test_exception_does_not_admit_active_or_unrelated_legacy(consumer,tmp_path,fault):
    spec=capacity_spec()
    if fault=='active_a0':spec['runtime']=active_a0(tmp_path,spec['a0_deployment'])
    elif fault=='different_name':spec['a0_deployment']['name']='other-historical-deployment'
    elif fault=='different_main_capacity':spec['inference'].update(context=131072,max_input=120000)
    else:
        field,value={'other_context':('context',73728),'other_input':('max_input',65529),
          'different_endpoint':('base_url','http://192.168.1.79:8001/v1'),
          'different_model':('model','other-dispatcher'),'different_output':('main_output',2048),
          'different_summary':('summary_output',2048),'different_margin':('margin',512),
          'different_overhead':('template_overhead',1024)}[fault]
        spec['compression_inference'][field]=value
    with pytest.raises(ValueError,match='a0_product_inference_profile_mismatch'):consumer(spec)


def test_old_inactive_split_route_is_preserved(consumer):
    spec=split_inputs();spec['a0_deployment']=legacy_profile()
    consumer(spec)


def test_new_current_primary_active_a0_route_is_preserved(consumer,tmp_path):
    spec=capacity_spec();profile=spec['a0_deployment'];profile['name']='explicit-current-main'
    for slot in ('chat','utility'):
        profile[slot].update(endpoint=spec['inference']['base_url'],model=spec['inference']['model'],
            context_length=spec['inference']['context'],max_output_tokens=spec['inference']['main_output'])
    spec['runtime']=active_a0(tmp_path,profile)
    consumer(spec)


def test_current_inactive_compressor_route_is_preserved(consumer):
    spec=capacity_spec();profile=spec['a0_deployment'];profile['name']='explicit-current-compressor'
    for slot in ('chat','utility'):profile[slot]['context_length']=65536
    consumer(spec)


import hashlib
from pathlib import Path
def inputs():
    return {'profile': 'default', 'inference': {
        'base_url': 'http://127.0.0.1:9000/v1', 'model': 'explicit-local-fixture',
        'key_env': 'FRIDAY_LOCAL_KEY', 'context': 32768, 'max_input': 30000,
        'main_output': 4096, 'summary_output': 2048, 'margin': 1024, 'template_overhead': 512},
        'web': {'profile': 'exa-paid', 'extract_char_limit': 20000, 'extract_timeout': 30},
        'dashboard': {'host': '127.0.0.1', 'port': 9119, 'public_url': 'https://friday.example:9119',
            'operator': {'provider': 'basic', 'user_id': 'explicit-operator', 'org_id': ''}},
        'accounts': [{'platform': 'telegram', 'transport_profile': 'default', 'account_id': 'bot-A'}],
        'runtime': {'enabled': False}}

def split_inputs():
    """Synthetic explicit bounds, not a currently admitted Spark profile."""
    spec = inputs()
    spec['inference'].update(base_url='http://192.168.1.195:30000/v1',
        model='qwen38-flash-next-abliterated', key_env='FRIDAY_LLM_API_KEY',
        context=262144, max_input=250000, main_output=8192, summary_output=4096,
        request_options={'reasoning_echo': True, 'reasoning_effort': 'xhigh',
            'temperature': 1.0, 'top_p': 0.95, 'presence_penalty': 0.0,
            'extra_body': {'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0,
                'chat_template_kwargs': {'enable_thinking': True, 'preserve_thinking': True}}})
    spec['compression_inference'] = dict(base_url='http://192.168.1.78:8001/v1',
        model='dispatcher', key_env='FRIDAY_COMPRESSION_API_KEY', context=40960,
        max_input=40960, main_output=4096, summary_output=4096, margin=1024,
        template_overhead=2048)
    spec['compression_multipass'] = dict(enabled=True, max_calls=64, max_depth=16,
        max_attempt_seconds=1800, max_call_seconds=180)
    return spec

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def pinned(p):
    return {'path': str(p), 'sha256': sha(p)}


@pytest.fixture
def install_input(tmp_path):
    tmp_path.chmod(0o700)
    script = tmp_path / 'reviewed-hermes-prepare.py'; script.write_text('# synthetic command input, not executed\n')
    python = tmp_path / 'bootstrap-python'; python.write_text('synthetic pinned executable'); python.chmod(0o700)
    root = entry.ROOT
    paths = [p for area in ('scripts', 'tools', 'plugins/friday_rework', 'config', 'patches/hermes')
             for p in (root / area).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    value = {'home': str(tmp_path / 'friday'), 'bootstrap_python': pinned(python),
        'hermes_donor': str(tmp_path / 'hermes-input'), 'hermes_prepare': pinned(script),
        'sources_lock': pinned(root / 'sources.lock.json'), 'dsh_donor': str(tmp_path / 'friday/harness'),
        'a0_donor': str(tmp_path / 'a0-input'), 'product': inputs(),
        'containment': pinned(Path('/usr/bin/bwrap')),
        'project_files': {str(p.relative_to(root)): sha(p) for p in paths}, 'seconds': 1800}
    return value
