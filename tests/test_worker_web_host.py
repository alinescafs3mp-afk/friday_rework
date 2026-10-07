"""Actual PluginManager factory/readiness; files/transport inputs synthetic."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest
from test_host_native import setup, isolated, native, offline_boundary, pin
from tools.render_dsh_local import build_patch
import tools.web_profile as helper


def test_native_host_factory_requires_source_pins_and_never_manufactures_web_admission(setup,tmp_path):
    config=copy.deepcopy(setup.runtime);dsh=config['dsh'];root=Path(__file__).resolve().parents[1]
    fields={}
    for key,data in [('resolver',b'nameserver 192.0.2.53\n'),('trust_bundle',b'SYNTHETIC CA INPUT\n'),
                     ('egress_evidence',b'FAKE integrity input, no admission\n'),('research_policy',(root/'config/RESEARCH.md').read_bytes())]:
        p=tmp_path/(key+'.input');p.write_bytes(data);fields[key]=pin(p)
    dsh['web']={'profile':'exa-paid',**fields}
    rows=build_patch(purpose='temporary-local-test',api='openai-completions',base_url='http://127.0.0.1:8011/v1',
        model='local-fixture',context_window=40960,max_tokens=4096,summary_max_tokens=2048,headroom_tokens=4096,
        api_key_env=dsh['key_name'],web_profile='exa-paid')
    p=tmp_path/'web-patch.json';p.write_text(json.dumps(rows));dsh['patch']=pin(p)
    module=sys.modules[setup.module.__name__.rsplit('.',1)[0]+'.host_runtime']
    receipt={'schema':'friday-rework.dsh-runtime.v1','ready':True,
        'runtime_sha256':setup.record.digest({k:v for k,v in config.items() if k!='runtime_receipt'}),
        'adapter_sha256':hashlib.sha256(Path(module.__file__).with_name('adapters').joinpath('dsh.py').read_bytes()).hexdigest(),
        'evidence':[fields['egress_evidence']],
        'web_source_pins':{'plugins/friday_rework/worker_web.py':hashlib.sha256(Path(module.__file__).with_name('worker_web.py').read_bytes()).hexdigest(),
                           'tools/web_profile.py':hashlib.sha256(Path(helper.__file__).read_bytes()).hexdigest(),
                           'config/RESEARCH.md':fields['research_policy']['sha256']}}
    p=tmp_path/'web-readiness.json';p.write_text(json.dumps(receipt));config['runtime_receipt']=pin(p)
    assert module.check_runtime(config,setup.host.store)==config
    binding=module.dsh_binding(config,setup.host.store)
    assert binding.adapter.config.web.profile=='exa-paid'
    assert isinstance(binding.adapter.config.verify_web_network,module.DshNetworkCheck)
    assert binding.adapter.config.key_name==setup.runtime['dsh']['key_name']
    for bad in [None, {'unknown':'wrong'}]:
        changed=copy.deepcopy(receipt);changed['web_source_pins']=bad
        p.write_text(json.dumps(changed));config['runtime_receipt']=pin(p)
        with pytest.raises(module.HostUnavailable,match='source_not_verified'):module.check_runtime(config,setup.host.store)
    altered=copy.deepcopy(config);altered['dsh']['web']['inline_key']='FOREIGN'
    with pytest.raises(module.HostUnavailable,match='invalid_worker_web_config'):module.validate_runtime(altered)
