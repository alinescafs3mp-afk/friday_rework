"""Current producer join tests on real native config, admission and setup proof."""
import copy,json
from pathlib import Path
import pytest
from test_user_onboarding import env,prepare,complete,secrets,grant,activate,admitted,home,row,cas,ident,sha
from test_admin_foundation import session
from hermes_cli import friday_user_scope as scope
from hermes_cli.config import require_readable_config_before_write
from hermes_constants import set_hermes_home_override,reset_hermes_home_override


def edit(env,kind='operational',**values):
    return env.admin.write_settings('user-1',{'kind':kind,'expected_sha256':sha(home(env)/'config.yaml'),
                                              'values':values or {'key':'agent.max_turns','value':17}},session())


def test_enabled_user_settings_reseal_real_native_admission_and_preserve_generation(env):
    complete(env);before=row(env)['generation'];other=complete(env,'2');foreign=(home(env,'2')/'config.yaml').read_bytes()
    proof=json.loads((home(env)/scope.ONBOARDING).read_text());marker=json.loads((home(env)/scope.MARKER).read_text())
    assert edit(env)['recorded']
    current=json.loads((home(env)/scope.ONBOARDING).read_text());assert current==dict(proof,config_sha256=sha(home(env)/'config.yaml'))
    assert json.loads((home(env)/scope.MARKER).read_text())==dict(marker,onboarding_sha256=sha(home(env)/scope.ONBOARDING))
    assert row(env)['generation']==before and (home(env,'2')/'config.yaml').read_bytes()==foreign
    ok,source=admitted(env);assert ok
    token=set_hermes_home_override(str(home(env)))
    try:
        with scope.scoped_source(source) as cap:
            cap.check();assert cap.home==home(env)
            with pytest.raises(scope.ScopeDenied):scope.check_context_path(home(env,'2')/'workspace/private.txt')
    finally:reset_hermes_home_override(token)
    assert require_readable_config_before_write(home(env)/'config.yaml')['agent']['max_turns']==17


@pytest.mark.parametrize('failure',['receipt_missing','receipt_tampered','marker_tampered','persona_changed','key_missing'])
def test_admin_edit_refuses_changed_setup_without_resealing(env,failure):
    complete(env);h=home(env)
    if failure=='receipt_missing':(h/scope.ONBOARDING).unlink()
    elif failure=='receipt_tampered':(h/scope.ONBOARDING).write_text('{}')
    elif failure=='marker_tampered':(h/scope.MARKER).write_text('{}')
    elif failure=='persona_changed':(h/'SOUL.md').write_text('foreign persona')
    else:(h/'.env').write_text('')
    original=(h/'config.yaml').read_bytes()
    with pytest.raises((PermissionError,ValueError,KeyError)):edit(env)
    assert (h/'config.yaml').read_bytes()==original
    assert admitted(env)[0] is False


@pytest.mark.parametrize('kind,values',[('toolset',{'name':'web','enabled':False}),('web',{'profile':'exa-keyless','extract_timeout':30,'extract_char_limit':15000})])
def test_settings_cannot_drop_required_onboarding_capabilities(env,kind,values):
    complete(env);h=home(env);original={n:(h/n).read_bytes() for n in ['config.yaml',scope.ONBOARDING,scope.MARKER]}
    with pytest.raises((PermissionError,ValueError)):edit(env,kind,**values)
    assert all((h/n).read_bytes()==v for n,v in original.items());assert admitted(env)[0]


def test_pending_settings_stay_disabled_and_resume_original_setup(env):
    prepared=prepare(env);assert edit(env)['recorded'];assert not row(env)['enabled']
    assert not (home(env)/scope.MARKER).exists();assert env.admin.onboarding_templates('default')['pending'][0]['recoverable']
    assert activate(env)['state']=='DISABLED_SCOPED_KEYS_MISSING'
    secrets(env);grant(env);assert activate(env)['enabled'];assert admitted(env)[0]
    assert row(env)['generation']==prepared['generation']


def test_interrupted_admin_proof_commit_leaves_profile_fail_closed(env,monkeypatch):
    complete(env);from friday_admin_controls import onboarding
    original=onboarding.finish_admin_config_edit
    monkeypatch.setattr(onboarding,'finish_admin_config_edit',lambda *a:(_ for _ in ()).throw(OSError('synthetic interrupted proof commit')))
    with pytest.raises(OSError):edit(env)
    assert require_readable_config_before_write(home(env)/'config.yaml')['agent']['max_turns']==17
    assert not admitted(env)[0]
    monkeypatch.setattr(onboarding,'finish_admin_config_edit',original)
    with pytest.raises((PermissionError,ValueError)):edit(env)
    assert not admitted(env)[0]  # No implicit replay/adoption of an uncertain edit.


def test_actual_signed_api_settings_join_and_receiving_access_control(env):
    import asyncio,httpx
    from test_admin_repair import basic_app
    complete(env);complete(env,'2')
    app,token=basic_app(env)
    original_other=(home(env,'2')/'config.yaml').read_bytes()
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic') as c:
            headers={'Authorization':'Bearer '+token}
            body={'kind':'operational','expected_sha256':sha(home(env)/'config.yaml'),'values':{'key':'agent.max_turns','value':21}}
            denied=await c.put('/api/plugins/friday_rework/settings?profile=user-1',json=body,headers={'Authorization':'Bearer forged'})
            assert denied.status_code==401
            changed=await c.put('/api/plugins/friday_rework/settings?profile=user-1',json=body,headers=headers)
            assert changed.status_code==200 and changed.json()['recorded'],changed.text
            users=await c.get('/api/plugins/friday_rework/users?profile=default',headers=headers)
            assert users.status_code==200 and {v['user_id'] for v in users.json()['users']}=={'1','2'}
            disabled=await c.put('/api/plugins/friday_rework/users?profile=default',headers=headers,json={**ident(),'enabled':False,'role':'user'})
            assert disabled.status_code==200 and not admitted(env)[0] and admitted(env,'2')[0]
            enabled=await c.put('/api/plugins/friday_rework/users?profile=default',headers=headers,json={**ident(),'enabled':True,'role':'user'})
            assert enabled.status_code==200 and admitted(env)[0],enabled.text
    asyncio.run(scenario())
    assert (home(env,'2')/'config.yaml').read_bytes()==original_other


def test_onboarding_honors_real_cross_process_native_config_lock_before_state_effect(env):
    from test_admin_controls_transactions import Child,wait_for
    original=(env.home/'config.yaml').read_bytes();child=Child(env,'hold-config')
    try:
        wait_for(env.home/'child-entered')
        with pytest.raises(TimeoutError):prepare(env)
    finally:child.finish()
    assert (env.home/'config.yaml').read_bytes()==original and not home(env).exists()
    from hermes_cli.friday_product_access import current_access
    assert not current_access(env.state)['users']


@pytest.mark.parametrize('damage',['receipt_deleted','config','marker','soul'])
@pytest.mark.parametrize('action',['direct','approve'])
def test_access_enable_and_pairing_approval_cannot_enable_changed_managed_setup(env,monkeypatch,damage,action):
    from gateway import pairing
    from types import SimpleNamespace
    complete(env);env.admin.set_user('default',**ident(),enabled=False,role='user');h=home(env)
    if damage=='receipt_deleted':(h/scope.ONBOARDING).unlink()
    elif damage=='config':(h/'config.yaml').write_text('{}')
    elif damage=='marker':(h/scope.MARKER).write_text('{}')
    else:(h/'SOUL.md').write_text('foreign persona')
    if action=='direct':
        with pytest.raises((PermissionError,ValueError)):
            env.admin.set_user('default',**ident(),enabled=True,role='user')
    else:
        # Advance only this synthetic pairing module's request clock; its real
        # cooldown and salted request approval remain intact. Owner monotonic
        # assignment/job budgets and every other native clock stay unchanged.
        future=pairing.time.time()+601;monkeypatch.setattr(pairing,'time',SimpleNamespace(time=lambda:future))
        store=pairing.PairingStore();assert store.generate_code('telegram','1','same name')
        request=next(r['request_id'] for r in store.list_pending() if r['user_id']=='1')
        with pytest.raises(RuntimeError,match='pairing_grant_may_exist_product_write_unconfirmed'):
            env.admin.approve('default',**{k:v for k,v in ident().items() if k!='user_id'},request_id=request)
        assert store.is_approved('telegram','1')
    assert not row(env)['enabled'] and not admitted(env)[0]


def test_valid_reapproval_keeps_original_revocation_generation_and_does_not_revive_old_source(env,monkeypatch):
    from gateway import pairing
    from types import SimpleNamespace
    complete(env);ok,old=admitted(env);assert ok
    generation=row(env)['generation'];env.admin.set_user('default',**ident(),enabled=False,role='user')
    future=pairing.time.time()+601;monkeypatch.setattr(pairing,'time',SimpleNamespace(time=lambda:future))
    store=pairing.PairingStore();assert store.generate_code('telegram','1','same name')
    request=next(r['request_id'] for r in store.list_pending() if r['user_id']=='1')
    assert env.admin.approve('default',**{k:v for k,v in ident().items() if k!='user_id'},request_id=request)['recorded']
    assert row(env)['generation']==generation+1 and admitted(env)[0]
    token=set_hermes_home_override(str(home(env)))
    try:
        with pytest.raises(scope.ScopeDenied):
            with scope.scoped_source(old):pass
    finally:reset_hermes_home_override(token)
