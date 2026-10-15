"""Native onboarding and admission; synthetic homes, no listener or model run."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_user_onboarding import env, prepare, complete, home, admitted, activate, secrets, grant, row
from hermes_cli import friday_credential_admission as admission
from hermes_cli import friday_user_scope as user
from hermes_cli import friday_ordinary_gateway as ordinary
from hermes_constants import set_hermes_home_override, reset_hermes_home_override


@pytest.fixture
def inventory(env, monkeypatch):
    monkeypatch.setattr(admission, 'SOURCE', env.home / 'hermes-agent')
    (env.home/'hermes-agent.source.json').write_text('{}')
    # Compose the current complete protected template through the real producer;
    # the older generic env template predates explicit native key/auth routing.
    from test_product_profile import inputs,template
    from tools.configure_product import compose_product
    spec=inputs();spec['dashboard']['operator']['user_id']='owner'
    spec['inference'].update(model='observed-local',key_env='LOCAL_KEY')
    bundle=compose_product(spec);env.cfg=bundle['config'];env.template=template(bundle)
    # This regression isolates ordinary inference: the existing native template
    # contract supports runtime-disabled profiles without worker declarations.
    # Current installed normal worker provisioning/activation is a separate gate.
    env.template.pop('worker_inputs',None)
    env.cfg['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local']=env.template
    publish(env.home/'config.yaml',env.cfg)
    calls=[]
    # Process/systemd deployment verification is intentionally isolated here.
    # The helper MUST call the unchanged full verifier at the authorization home.
    def check(root):
        from hermes_constants import get_hermes_home
        from agent.secret_scope import current_secret_scope_home
        assert root == env.home == get_hermes_home()
        assert current_secret_scope_home() == str(root)
        calls.append(root)
    monkeypatch.setattr(ordinary, 'check', check)
    env.verifier_calls=calls
    return env


def publish(p,value):
    p.write_text(json.dumps(value));p.chmod(0o600)


def receipt_change(h, **updates):
    p=h/user.ONBOARDING;v=json.loads(p.read_text());v.update(updates);publish(p,v)


def load(h):
    from gateway.config import load_gateway_config
    with admission.scoped(h): return load_gateway_config()


def test_native_prepared_disabled_inventory_is_inert_without_install_or_keys(inventory, monkeypatch):
    e=inventory;prepare(e);h=home(e)
    assert not (h/'FRIDAY-INSTALL.json').exists() and not (h/user.MARKER).exists() and not (h/'.env').exists()
    before=(e.home/'config.yaml').read_bytes(),(h/user.ONBOARDING).read_bytes(),row(e).copy()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','999999:AMBIENT_MUST_NOT_START')
    assert admission.onboarded_gateway_profile(h)
    assert load(h).platforms == {}
    assert user._CURRENT.get() is None
    assert not admitted(e)[0]
    with admission.scoped(h),pytest.raises((ValueError,OSError)):
        admission.route_inputs()
    assert before == ((e.home/'config.yaml').read_bytes(),(h/user.ONBOARDING).read_bytes(),row(e).copy())
    assert len(e.verifier_calls) >= 2


def test_native_restart_inventory_then_normal_activation_and_two_user_credentials(inventory):
    from hermes_cli.runtime_provider import resolve_runtime_provider
    e=inventory
    for uid in ('1','2'):
        prepare(e,uid);assert admission.onboarded_gateway_profile(home(e,uid))
        secrets(e,uid);grant(e,uid);assert activate(e,uid)['enabled']
    for uid in ('1','2'):
        h=home(e,uid);assert admission.onboarded_gateway_profile(h)
        assert load(h).platforms == {}
        ok,source=admitted(e,uid);assert ok
        with admission.scoped(h),user.scoped_source(source):
            result=resolve_runtime_provider(requested='custom:friday-local',target_model='observed-local')
            assert result['api_key'] == 'synthetic-'+uid+'-LOCAL_KEY'
            assert result['base_url'] == 'http://127.0.0.1:9000/v1'
            with pytest.raises(admission.CredentialDenied):admission.channel_identity('telegram','bot-A')


@pytest.mark.parametrize('change',['config','soul','receipt','directory','foreign_root','unknown_profile',
                                  'install','product','legacy','public','symlink','missing_marker','changed_marker'])
def test_tampered_or_foreign_inventory_refuses(inventory,change,tmp_path):
    e=inventory;complete(e);h=home(e)
    if change in ('config','soul'):
        p=h/('config.yaml' if change=='config' else 'SOUL.md');p.write_text(p.read_text()+'\n')
    elif change=='receipt':receipt_change(h,binding_sha256='0'*64)
    elif change=='directory':receipt_change(h,directory_identity=[0,0])
    elif change=='foreign_root':receipt_change(h,authorization_home=str(tmp_path))
    elif change=='unknown_profile':
        import shutil
        other=e.home/'profiles/unknown';shutil.copytree(h,other);other.chmod(0o700);h=other
    elif change in ('install','product','legacy'):
        publish(h/{'install':'FRIDAY-INSTALL.json','product':'FRIDAY-PROFILE.json','legacy':'gateway.json'}[change],{})
    elif change=='public':(h/user.ONBOARDING).chmod(0o644)
    elif change=='symlink':
        p=h/user.ONBOARDING;p.rename(h/'receipt-saved');p.symlink_to(h/'receipt-saved')
    elif change=='missing_marker':(h/user.MARKER).unlink()
    elif change=='changed_marker':publish(h/user.MARKER,{'schema':'forged'})
    with pytest.raises((ValueError,OSError,PermissionError)):admission.onboarded_gateway_profile(h)


def test_root_verifier_failure_is_never_downgraded(inventory,monkeypatch):
    e=inventory;prepare(e)
    def reject(root):raise admission.CredentialDenied('root_source_or_configuration_changed')
    monkeypatch.setattr(ordinary,'check',reject)
    with pytest.raises(admission.CredentialDenied,match='root_source_or_configuration_changed'):
        admission.onboarded_gateway_profile(home(e))


def test_default_root_loader_keeps_original_admission_path(inventory,monkeypatch):
    e=inventory;seen=[]
    assert admission.onboarded_gateway_profile(e.home) is False
    def reject():seen.append('original');raise admission.CredentialDenied('root_channel_check')
    monkeypatch.setattr(admission,'channel_inputs',reject)
    with admission.scoped(e.home),pytest.raises(admission.CredentialDenied,match='root_channel_check'):load(e.home)
    assert seen==['original']


def test_secondary_inventory_precedes_hydration_plugin_discovery_and_hooks(inventory,monkeypatch):
    e=inventory;prepare(e)
    from gateway.run_adapters import GatewayAdapterLifecycleMixin
    from hermes_cli import env_loader,plugins
    from gateway import run_startup
    def forbidden(*a,**kw):pytest.fail('secondary inventory performed a setup/plugin/hook effect')
    import sys
    monkeypatch.setitem(sys.modules,'gateway.run',SimpleNamespace(
        MultiplexConfigError=ValueError,_load_gateway_config=forbidden,
        _own_policy_open_startup_violation=forbidden,_profile_runtime_scope=forbidden))
    monkeypatch.setattr(env_loader,'hydrate_profile_secret_sources',forbidden)
    monkeypatch.setattr(plugins,'discover_plugins',forbidden)
    monkeypatch.setattr(run_startup,'recover_left_core_in',forbidden)
    runner=SimpleNamespace(_subscribe_plugin_rewire=forbidden,_register_config_hooks=forbidden,
                           _snapshot_profile_busy_modes=forbidden)
    cfg=asyncio.run(GatewayAdapterLifecycleMixin._load_secondary_profile_config(runner,'user-1',home(e)))
    assert cfg.platforms=={}
    assert not admitted(e)[0]


def test_retained_generation_stays_revoked_after_disable_and_reenable(inventory):
    from hermes_cli.friday_product_access import KEY,current_access,principal_id
    e=inventory;complete(e);ok,s=admitted(e);assert ok
    with admission.scoped(home(e)),user.scoped_source(s) as cap:
        assert admission.onboarded_gateway_profile(home(e))
    key=principal_id('telegram','default','bot-A','1')
    # Exercise the real native durable access writer and its authoritative
    # generation advancement; operator HTTP control is outside this scope.
    with user.authority(e.home):
        document=copy.deepcopy(current_access(e.state));document['users'][key]['enabled']=False
        e.state.set(KEY,document)
    assert not admitted(e)[0]
    assert admission.onboarded_gateway_profile(home(e))
    with admission.scoped(home(e)),pytest.raises(user.ScopeDenied):cap.check()
    with user.authority(e.home):
        document=copy.deepcopy(current_access(e.state));document['users'][key]['enabled']=True
        e.state.set(KEY,document)
    with admission.scoped(home(e)),pytest.raises(user.ScopeDenied):cap.check()
    assert admitted(e)[0]


def test_cross_user_retained_scope_cannot_inventory_another_home(inventory):
    e=inventory
    complete(e,'1');complete(e,'2')
    ok,source=admitted(e,'1');assert ok
    with admission.scoped(home(e,'1')),user.scoped_source(source):
        with pytest.raises(admission.CredentialDenied,match='user_inventory_scope_mismatch'):
            admission.onboarded_gateway_profile(home(e,'2'))
        with pytest.raises(admission.CredentialDenied,match='user_inventory_scope_mismatch'):
            load(home(e,'2'))
    assert admitted(e,'2')[0]
