"""Isolated exact-byte recovery; real native YAML/scope/config-lock, synthetic source/root custody.

No services, native installed home, database, model or transport are executed.
"""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import types

import pytest

from scripts import friday_install as f
from scripts.install_containment import Budget
from hermes_cli import friday_user_scope as user, friday_product_access as access
from hermes_cli import friday_ordinary_gateway as ordinary
from hermes_cli.plugins_state import _plugin_data_namespace
from hermes_cli import config as native_config

from scripts import friday_ordinary_install as o


def put(path,data,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_bytes(data);path.chmod(mode)
    return pin(path)


def doc(path,obj):return put(path,o.encoded(obj))
def pin(path):return {'path':str(path),'sha256':f.digest(path.read_bytes())}
def snapshot(home):
    return {str(p.relative_to(home)):(p.read_bytes(),stat.S_IMODE(p.stat().st_mode),p.stat().st_ino)
        for p in home.rglob('*') if p.is_file()}


@pytest.fixture
def setup(tmp_path,monkeypatch):
    home=tmp_path/'home';home.mkdir(mode=0o700);source=home/'hermes-agent';source.mkdir(mode=0o700)
    (home/'preparation').mkdir(mode=0o700);(home/'profiles').mkdir(mode=0o700)
    ph=home/'profiles/member';ph.mkdir(mode=0o700)
    for name in ('memories','workspace','backups','backups/config'):(ph/name).mkdir(mode=0o700)
    binding={'platform':'telegram','transport_profile':'default','account_id':'bot',
        'user_id':'owner','runtime_profile':'member','tools':['read_file']}
    principal=access.principal_id('telegram','default','bot','owner')
    cfg={'gateway':{'multiplex_profiles':True,'profile_routes':[{'name':'friday-'+principal,
        'platform':'telegram','bot_profile':'default','user_id':'owner','profile':'member','enabled':True}]},
        'plugins':{'entries':{'friday_rework':{'settings':{'user_isolation':{'enabled':True,'bindings':[binding]},
        'product_access':{'enabled':True,'accounts':[{'platform':'telegram','transport_profile':'default',
        'account_id':'bot','runtime_profiles':['default','member']}]}}}}}}
    import hermes_yaml
    rootref=put(home/'config.yaml',hermes_yaml.safe_dump(cfg).encode())
    old=b'model: preserved\nstreaming:\n  enabled: false\n'
    bad=old+o.FIRST_CONTACT_CONFIG_SUFFIX
    confref=put(ph/'config.yaml',bad)
    backupref=put(ph/'backups/config/config.yaml.good.20261015-151458',old)
    soulref=put(ph/'SOUL.md',b'preserved soul\n')
    put(ph/'.env',b'EXAMPLE_SECRET=synthetic-secret\n')
    info=ph.stat()
    onboarding={'schema':'friday.onboarding.v1','binding_sha256':user._fingerprint(binding),
        'authorization_home':str(home),'directory_identity':[info.st_dev,info.st_ino],
        'config_sha256':f.digest(old),'soul_sha256':soulref['sha256'],
        'required_secrets':['EXAMPLE_SECRET'],'template':'original-template'}
    onboardref=doc(ph/user.ONBOARDING,onboarding)
    markerref=doc(ph/user.MARKER,{'schema':'friday.user-home.v1','principal':principal,'profile':'member',
        'binding_sha256':user._fingerprint(binding),'onboarding_sha256':onboardref['sha256']})
    state={access.KEY:{'schema':access.KEY,'users':{principal:{'platform':'telegram','transport_profile':'default',
        'account_id':'bot','user_id':'owner','enabled':True,'role':'user','generation':1}}},
        'unchanged-audit':{'consumed':[1,2,3]}}
    stateref=doc(home/'plugin-data'/_plugin_data_namespace('friday_rework','')/'state.json',state)
    # Native PluginState has a preexisting private lock; no state repair is required.
    put(Path(stateref['path']).with_name('.state.json.lock'),b'')
    sourceref=doc(home/'hermes-agent.source.json',{'base_tree':'tree','layers':[]})
    stampref=doc(source/'install-stamp.json',{'fridaySource':{'baseTree':'tree','layers':[]}})
    lockref=doc(tmp_path/'source-lock.json',{'repositories':[{'id':'hermes'}]})
    inputref=doc(tmp_path/'installed-input.json',{'home':str(home),'sources_lock':lockref})
    rootmarker=doc(home/f.MARKER,{'home':str(home),'source':str(source),
        'input_sha256':inputref['sha256'],'source_receipt_sha256':sourceref['sha256']})
    rootprofile=doc(home/'FRIDAY-PROFILE.json',{'preserved':True})
    unitref=put(tmp_path/'native.service',b'never executed\n')
    request={'schema':'friday.ordinary-first-contact-config-recovery.v1','seconds':180,'home':str(home),
        'profile':'member','binding':binding,'generation':1,
        'allowed_delta':'append-onboarding.seen.profile_build_offered=true',
        'configuration_identity':list(o.update_file_state(ph/'config.yaml')['identity']),
        'installed_input':inputref,'root_marker':rootmarker,'source_receipt':sourceref,'stamp':stampref,
        'root_configuration':rootref,'root_profile':rootprofile,'native_unit':unitref,'onboarding':onboardref,
        'user_marker':markerref,'configuration':confref,'backup':backupref,'access_state':stateref}
    reqpath=tmp_path/'request.json';doc(reqpath,request)
    monkeypatch.setenv('HERMES_HOME',str(home))
    # Existing installations have their native skeleton already initialized.
    with user.authority(home):native_config.ensure_hermes_home()
    with user.authority(ph):native_config.ensure_hermes_home()
    put(ph/'config.yaml.lock',b'')
    monkeypatch.setattr(f,'composition_checked',lambda *a,**kw:None)
    monkeypatch.setattr(f,'native_packages',lambda *a:None)
    # Root check is independently retained; source/complex native deployment identity uses fixture.
    root_calls=[]
    def rootcheck(h,role=False):
        assert h==home and role is False
        root_calls.append(True)
        assert pin(home/'config.yaml')==rootref
    monkeypatch.setattr(ordinary,'check',rootcheck)
    custody={'held':False,'config_lock':False,'proves':0}
    def prove():
        assert custody['held'];custody['proves']+=1
    @contextlib.contextmanager
    def stopped(*args):
        custody['held']=True
        try:yield prove
        finally:custody['held']=False
    monkeypatch.setattr(o,'stopped_consumers',stopped)
    @contextlib.contextmanager
    def build(*args):yield prove
    monkeypatch.setattr(o,'retained_build_lock',build)
    actual_config_lock=native_config.config_write_transaction
    @contextlib.contextmanager
    def config_lock(path):
        assert custody['held'];custody['config_lock']=True
        try:
            with actual_config_lock(path):yield
        finally:custody['config_lock']=False
    monkeypatch.setattr(native_config,'config_write_transaction',config_lock)
    actual_publish=o.publish_update_file
    def publish(*args,**kwargs):
        assert custody['held'] and custody['config_lock']
        return actual_publish(*args,**kwargs)
    monkeypatch.setattr(o,'publish_update_file',publish)
    return locals()


def save_request(s):doc(s['reqpath'],s['request'])
def run(s):return o.recover_first_contact_config(s['request'],s['reqpath'],Budget(180))


def test_exact_restore_preserves_receipts_history_and_bad_once(setup):
    s=setup;before=snapshot(s['home']);result=run(s)
    assert result['state']=='EXACT_CONFIG_RESTORED_CONSUMERS_STOPPED'
    assert (s['ph']/'config.yaml').read_bytes()==s['old']
    assert s['custody']['held'] is False and s['custody']['config_lock'] is False
    tx=s['home']/'preparation'/('ordinary-first-contact-config-recovery-'+s['confref']['sha256'])
    assert (tx/'bad-config.yaml').read_bytes()==s['bad']
    assert stat.S_IMODE(tx.stat().st_mode)==0o700
    for name in ('bad-config.yaml','intent.json','committed.json'):
        assert stat.S_IMODE((tx/name).stat().st_mode)==0o600
    after=snapshot(s['home'])
    for name,state in before.items():
        if name!='profiles/member/config.yaml':assert after[name]==state
    assert s['custody']['proves']>=4 and len(s['root_calls'])>=3
    # Original unchanged scope check now admits the exact original profile.
    with user.authority(s['ph']):
        user.UserScope(s['home'],s['ph'],'member',('telegram','default','bot','owner'),
            s['binding'],tuple(s['onboarding']['directory_identity']),1).check()
    committed=snapshot(s['home'])
    with pytest.raises(Exception):run(s)
    assert snapshot(s['home'])==committed


@pytest.mark.parametrize('fault',[
    'cas','backup_bytes','bad_latest','extra_byte','extra_field','flag_false','root','receipt','marker',
    'root_marker','source_receipt','stamp','access_bytes','access_disabled','access_generation','generation',
    'binding','profile_escape','backup_escape','config_symlink','config_hardlink','config_mode','backup_mode',
    'config_inode','directory_identity','unknown_field','unknown_delta','consumer','request_race','config_race'])
def test_refusal_leaves_all_original_bytes_untouched(setup,monkeypatch,fault):
    s=setup;r=s['request'];ph=s['ph']
    def reseal(name,path):r[name]=pin(path)
    if fault=='cas':put(ph/'config.yaml',s['bad']+b'#changed\n')
    elif fault=='backup_bytes':put(Path(r['backup']['path']),s['old']+b'#changed\n')
    elif fault=='bad_latest':r['backup']=put(ph/'backups/config/config.yaml.good.latest',s['bad'])
    elif fault in ('extra_byte','extra_field','flag_false'):
        data=s['bad']+(b'\n' if fault=='extra_byte' else b'unrelated: true\n' if fault=='extra_field' else b'')
        if fault=='flag_false':data=data.replace(b'profile_build_offered: true',b'profile_build_offered: false')
        put(ph/'config.yaml',data);reseal('configuration',ph/'config.yaml')
    elif fault=='root':put(s['home']/'config.yaml',b'changed: true\n')
    elif fault in ('receipt','marker','root_marker','source_receipt','stamp','access_bytes'):
        key={'receipt':'onboarding','marker':'user_marker','access_bytes':'access_state'}.get(fault,fault)
        put(Path(r[key]['path']),b'{}\n')
    elif fault in ('access_disabled','access_generation'):
        state=copy.deepcopy(s['state']);row=state[access.KEY]['users'][s['principal']]
        row['enabled']=False if fault=='access_disabled' else True
        if fault=='access_generation':row['generation']=2
        r['access_state']=doc(Path(r['access_state']['path']),state)
    elif fault=='generation':r['generation']=2
    elif fault=='binding':r['binding']=dict(r['binding'],account_id='foreign')
    elif fault=='profile_escape':r['profile']='../member'
    elif fault=='backup_escape':r['backup']=put(s['home']/'elsewhere',s['old'])
    elif fault in ('config_symlink','config_hardlink'):
        target=s['home']/'external-config';put(target,s['bad']);(ph/'config.yaml').unlink()
        if fault=='config_symlink':(ph/'config.yaml').symlink_to(target)
        else:os.link(target,ph/'config.yaml')
    elif fault=='config_mode':(ph/'config.yaml').chmod(0o644)
    elif fault=='backup_mode':Path(r['backup']['path']).chmod(0o644)
    elif fault=='config_inode':r['configuration_identity'][1]+=1
    elif fault=='directory_identity':
        obj=dict(s['onboarding'],directory_identity=[0,0]);r['onboarding']=doc(ph/user.ONBOARDING,obj)
        obj=f.read_json(ph/user.MARKER);obj['onboarding_sha256']=r['onboarding']['sha256'];r['user_marker']=doc(ph/user.MARKER,obj)
    elif fault=='unknown_field':r['generic_edit']='no'
    elif fault=='unknown_delta':r['allowed_delta']='other'
    elif fault=='consumer':
        @contextlib.contextmanager
        def active(*a):raise ValueError('consumer active');yield
        monkeypatch.setattr(o,'stopped_consumers',active)
    elif fault in ('request_race','config_race'):
        actual=o.first_contact_recovery_inputs;calls=[]
        def racing(*a,**kw):
            out=actual(*a,**kw);calls.append(True)
            if len(calls)==1:
                if fault=='request_race':put(s['reqpath'],b'{}\n')
                else:
                    target=ph/'replacement';put(target,s['bad']);os.replace(target,ph/'config.yaml')
            return out
        monkeypatch.setattr(o,'first_contact_recovery_inputs',racing)
    save_request(s);before=snapshot(s['home'])
    with pytest.raises(Exception):run(s)
    after=snapshot(s['home'])
    # A synthetic adversary in race tests owns its replacement, never recovery.
    if fault=='config_race':
        assert after['profiles/member/config.yaml'][:2]==before['profiles/member/config.yaml'][:2]
        before.pop('profiles/member/config.yaml');after.pop('profiles/member/config.yaml')
    assert after==before
    assert not list((s['home']/'preparation').iterdir())


def test_postpublication_failure_keeps_old_and_bad_evidence(setup,monkeypatch):
    s=setup
    def denied(*a,**kw):raise user.ScopeDenied()
    monkeypatch.setattr(user.UserScope,'check',denied)
    with pytest.raises(user.ScopeDenied):run(s)
    assert (s['ph']/'config.yaml').read_bytes()==s['old']
    tx=next((s['home']/'preparation').iterdir())
    assert (tx/'bad-config.yaml').read_bytes()==s['bad']
    assert not (tx/'committed.json').exists()
    assert f.read_json(tx/'failed.json')['restored_config_retained'] is True
    before=snapshot(s['home'])
    with pytest.raises(Exception):run(s)
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('refname',['backup','user_marker','onboarding','access_state'])
def test_identical_pinned_bytes_on_replaced_inode_refuse_before_journal(setup,monkeypatch,refname):
    s=setup;actual=o.first_contact_recovery_inputs;calls=[]
    def race(*args,**kwargs):
        result=actual(*args,**kwargs);calls.append(True)
        if len(calls)==1:
            path=Path(s['request'][refname]['path']);tmp=path.with_name(path.name+'.foreign')
            put(tmp,path.read_bytes());os.replace(tmp,path)
        return result
    monkeypatch.setattr(o,'first_contact_recovery_inputs',race)
    with pytest.raises(f.Refused,match='pinned_identity_changed'):run(s)
    assert (s['ph']/'config.yaml').read_bytes()==s['bad']
    assert not list((s['home']/'preparation').iterdir())


def test_foreign_owner_refuses_before_native_lock(setup,monkeypatch):
    s=setup;before=snapshot(s['home']);uid=os.getuid()
    monkeypatch.setattr(os,'getuid',lambda:uid+1)
    with pytest.raises(f.Refused,match='owned_private_directory_required'):run(s)
    assert snapshot(s['home'])==before


def test_occupied_staging_path_retained_and_consumed_without_overwrite(setup):
    s=setup;stage=s['ph']/'config.yaml.ordinary-staged';put(stage,b'foreign staging bytes\n')
    with pytest.raises(Exception):run(s)
    assert stage.read_bytes()==b'foreign staging bytes\n'
    assert (s['ph']/'config.yaml').read_bytes()==s['bad']
    tx=next((s['home']/'preparation').iterdir())
    assert (tx/'bad-config.yaml').read_bytes()==s['bad']
    assert f.read_json(tx/'failed.json')['restored_config_retained'] is False


@pytest.mark.parametrize('fault',['symlink','hardlink','mode','payload','missing'])
def test_native_config_lock_unsafe_target_refused_before_pid_stamp(setup,fault):
    s=setup;lock=s['ph']/'config.yaml.lock';secret=s['ph']/'.env'
    if fault in ('symlink','hardlink','missing'):lock.unlink()
    if fault=='symlink':lock.symlink_to(secret)
    elif fault=='hardlink':os.link(secret,lock)
    elif fault=='mode':lock.chmod(0o666)
    elif fault=='payload':put(lock,b'foreign owner pid\n')
    before=snapshot(s['home'])
    with pytest.raises(Exception):run(s)
    assert snapshot(s['home'])==before
    assert not list((s['home']/'preparation').iterdir())


def test_existing_native_0664_lock_preserved_exactly(setup):
    s=setup;lock=s['ph']/'config.yaml.lock';lock.chmod(0o664);info=lock.stat()
    assert run(s)['state']=='EXACT_CONFIG_RESTORED_CONSUMERS_STOPPED'
    assert lock.read_bytes()==b'' and stat.S_IMODE(lock.stat().st_mode)==0o664
    assert (lock.stat().st_dev,lock.stat().st_ino)==(info.st_dev,info.st_ino)


def test_readonly_installed_input_recovery(setup):
    s=setup
    installed=Path(s['request']['installed_input']['path'])
    installed.chmod(0o400)
    result=run(s)
    assert result['state']=='EXACT_CONFIG_RESTORED_CONSUMERS_STOPPED'
    assert stat.S_IMODE(installed.stat().st_mode)==0o400


@pytest.mark.parametrize('mode',[0o444,0o640,0o644])
def test_nonprivate_installed_input_refused_before_write(setup,mode):
    s=setup
    Path(s['request']['installed_input']['path']).chmod(mode)
    before=snapshot(s['home'])
    with pytest.raises(Exception):run(s)
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('mode',[0o755,0o775])
def test_native_backup_directories_preserve_native_mode(setup,mode):
    s=setup
    for parent in (s['ph']/'backups',s['ph']/'backups/config'):parent.chmod(mode)
    assert run(s)['state']=='EXACT_CONFIG_RESTORED_CONSUMERS_STOPPED'
    assert all(stat.S_IMODE(parent.stat().st_mode)==mode for parent in (s['ph']/'backups',s['ph']/'backups/config'))


@pytest.mark.parametrize('mode',[0o773,0o777])
def test_unsupported_native_backup_directory_refused_before_write(setup,mode):
    s=setup
    (s['ph']/'backups/config').chmod(mode)
    before=snapshot(s['home'])
    with pytest.raises(Exception):run(s)
    assert snapshot(s['home'])==before
