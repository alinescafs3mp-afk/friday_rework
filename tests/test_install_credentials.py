"""Actual native secret writer with synthetic protected inputs; no network."""
import copy
import json
import os
from pathlib import Path

import pytest

from scripts import install_credentials as creds, friday_native as native
from scripts.install_containment import Budget
from test_native_installer import native_home, install_input
from test_product_profile import inputs


@pytest.fixture
def prepared(tmp_path):
    from plugins.dashboard_auth.basic import hash_password
    home = tmp_path / 'product'; home.mkdir(mode=0o700)
    with native_home(home):
        bundle = native.profile_write(home, inputs())
    values = {name: 'SYNTHETIC-' + name for name in creds.required_names(bundle)}
    values.update(HERMES_DASHBOARD_BASIC_AUTH_USERNAME=bundle['contract']['native_dashboard']['operator']['user_id'],
                  HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH=hash_password('fixture password'))
    source = tmp_path / 'selected.json'; source.write_text(json.dumps(values)); source.chmod(0o600)
    refs = {name: {'path': str(source), 'format': 'json', 'name': name} for name in values}
    return home, bundle, values, source, refs


def test_native_writer_roundtrip_auth_and_scope_preserved(prepared):
    from hermes_cli.friday_credential_admission import owned_values
    from agent.secret_scope import current_secret_scope, current_secret_scope_home
    from plugins.dashboard_auth.basic import BasicAuthProvider
    home, bundle, values, source, refs = prepared
    before = dict(os.environ); scope = current_secret_scope(); scope_home = current_secret_scope_home()
    config = (home / 'config.yaml').read_bytes()
    with native_home(home):
        result = creds.provision(refs, bundle, home, Budget(30))
        actual = owned_values(home)
    assert actual == values and result['stored_names'] == sorted(values)
    assert result['ready'] is False and result['provider_authentication_checked'] is False
    assert os.environ == before and current_secret_scope() is scope
    assert current_secret_scope_home() == scope_home
    assert (home / '.env').stat().st_mode & 0o777 == 0o600
    assert (home / 'config.yaml').read_bytes() == config
    provider = BasicAuthProvider(username=actual['HERMES_DASHBOARD_BASIC_AUTH_USERNAME'],
        password_hash=actual['HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH'],
        secret=actual['HERMES_DASHBOARD_BASIC_AUTH_SECRET'].encode())
    session = provider.complete_password_login(username=actual['HERMES_DASHBOARD_BASIC_AUTH_USERNAME'], password='fixture password')
    assert session is not None
    encoded = json.dumps(result)
    assert all(value not in encoded for key,value in values.items() if not key.endswith('USERNAME'))


@pytest.mark.parametrize('kind', ['extra', 'missing', 'bad_mode', 'symlink', 'hardlink', 'bad_value',
                                  'interpolation', 'newline', 'unicode', 'operator', 'secret', 'duplicate'])
def test_bad_selection_refuses_before_native_writes(prepared, kind):
    home,bundle,values,source,refs = prepared
    key = bundle['contract']['required_scoped_names']['inference_web'][0]
    if kind == 'extra': refs['UNRELATED_API_KEY'] = dict(refs[key])
    elif kind == 'missing': del refs[key]
    elif kind == 'bad_mode': source.chmod(0o644)
    elif kind == 'symlink':
        link=source.with_name('linked.json');link.symlink_to(source)
        for row in refs.values():row['path']=str(link)
    elif kind == 'hardlink': os.link(source,source.with_name('hard.json'))
    else:
        if kind == 'bad_value': values[key]=None
        elif kind == 'interpolation': values[key]='${AMBIENT_SECRET}'
        elif kind == 'newline': values[key]='value\nOTHER=foreign'
        elif kind == 'unicode': values[key]='secreté'
        elif kind == 'operator': values['HERMES_DASHBOARD_BASIC_AUTH_USERNAME']='foreign'
        elif kind == 'secret': values['HERMES_DASHBOARD_BASIC_AUTH_SECRET']='short'
        if kind == 'duplicate': source.write_text('{"DUP":"first","DUP":"second"}')
        else: source.write_text(json.dumps(values))
    with native_home(home), pytest.raises(ValueError,match='native_credential_provisioning_failed'):
        creds.provision(refs,bundle,home,Budget(30))
    assert not (home/'.env').exists() and not (home/'auth.json').exists()


def test_dotenv_selection_does_not_expand_or_import_unselected_values(prepared):
    home,bundle,values,source,refs=prepared
    # Native dotenv syntax, including quoted hash and comment values. No shell.
    lines=[name+'='+json.dumps(value) for name,value in values.items()]
    source.write_text('\n'.join(lines)+'\nUNSELECTED=${AMBIENT_SECRET}\n')
    for row in refs.values():row['format']='dotenv'
    with native_home(home):
        creds.provision(refs,bundle,home,Budget(30))
        from hermes_cli.friday_credential_admission import owned_values
        assert owned_values(home)==values


@pytest.mark.parametrize('name', ['.env', 'auth.json'])
def test_existing_native_credentials_never_replaced(prepared,name):
    home,bundle,values,source,refs=prepared
    target=home/name;target.write_text('owner value');target.chmod(0o600)
    with native_home(home),pytest.raises(ValueError):creds.provision(refs,bundle,home,Budget(30))
    assert target.read_text()=='owner value'


def test_partial_native_save_is_retained_and_cannot_replay(prepared,monkeypatch):
    from hermes_cli import config
    home,bundle,values,source,refs=prepared;save=config.save_env_value_secure;calls=[]
    def fail(name,value):
        calls.append(name)
        if len(calls)==2:raise RuntimeError('SYNTHETIC_SECRET_MUST_NOT_ESCAPE')
        return save(name,value)
    monkeypatch.setattr(config,'save_env_value_secure',fail)
    with native_home(home),pytest.raises(ValueError) as error:creds.provision(refs,bundle,home,Budget(30))
    assert str(error.value)=='native_credential_provisioning_failed'
    retained=(home/'.env').read_bytes();assert retained
    monkeypatch.setattr(config,'save_env_value_secure',save)
    with native_home(home),pytest.raises(ValueError):creds.provision(refs,bundle,home,Budget(30))
    assert (home/'.env').read_bytes()==retained


def test_original_deadline_is_checked_before_secret_read(prepared,monkeypatch):
    from scripts import friday_install
    home,bundle,values,source,refs=prepared
    budget=Budget(30);budget.deadline=0
    monkeypatch.setattr(friday_install,'owned_file',lambda *a,**k:pytest.fail('read after original deadline'))
    with native_home(home),pytest.raises(ValueError):creds.provision(refs,bundle,home,budget)
    assert not (home/'.env').exists()


def test_install_reference_validation_does_not_read_secret_file(install_input,monkeypatch):
    from scripts import friday_install
    source=Path(install_input['home']).parent/'not-created-private.json'
    install_input['credential_sources']={'FRIDAY_LOCAL_KEY':{'path':str(source),'format':'json','name':'KEY'}}
    original=friday_install.owned_file
    def guarded(path,**kwargs):
        assert Path(path)!=source
        return original(path,**kwargs)
    monkeypatch.setattr(friday_install,'owned_file',guarded)
    assert friday_install.commands(install_input)
    assert not source.exists()
