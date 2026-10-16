"""Preserve inactive legacy A0 while splitting explicit main/compression roles."""
import copy
import sys
from pathlib import Path
import pytest
from tools.configure_product import compose_product
from scripts import friday_install as installer
from plugins.friday_rework.adapters.a0_profile import legacy_profile
from test_native_installer import install_input
from test_product_profile import split_inputs


@pytest.fixture
def declared_install_input(install_input,tmp_path,monkeypatch):
    # Existing install_input is a declared source-only inventory. Copy exactly
    # its files to a private canonical ROOT; ambient caches are not inputs.
    value=copy.deepcopy(install_input);root=tmp_path/'declared-project';root.mkdir(mode=0o700)
    for name,expected in value['project_files'].items():
        raw=installer.owned_file(installer.ROOT/name)
        assert installer.digest(raw)==expected
        target=root/name;target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        target.write_bytes(raw);target.chmod(0o600)
    for name in tuple(sys.modules):
        if name=='_friday_install_validation' or name.startswith('_friday_install_validation.'):
            monkeypatch.delitem(sys.modules,name)
    monkeypatch.setattr(installer,'ROOT',root)
    return value


def legacy_split():
    value=split_inputs();value['a0_deployment']=legacy_profile()
    return value


def test_inactive_legacy_a0_is_preserved_while_primary_and_compressor_split():
    value=legacy_split();before=copy.deepcopy(value)
    result=compose_product(value)
    assert value==before and result['config']['a0_deployment']==value['a0_deployment']
    assert result['config']['model']['context_length']==262144
    assert result['config']['auxiliary']['compression']['context_length']==40960
    assert result['config']['plugins']['entries']['friday_rework']['settings']['runtime']=={'enabled':False}
    assert result['contract']['required_scoped_names']['worker_service']==['FRIDAY_EMBEDDINGS_API_KEY','SEARXNG_SECRET']


@pytest.mark.parametrize('fault',['enabled_workers','false_as_zero','compression_mismatch','compression_key','absent_split'])
def test_existing_installer_keeps_a0_route_equality_and_role_guards(declared_install_input,fault):
    value=copy.deepcopy(declared_install_input);value['product']=legacy_split()
    if fault=='enabled_workers':value['product']['runtime']={'enabled':True}
    elif fault=='false_as_zero':value['product']['runtime']={'enabled':0}
    elif fault=='compression_mismatch':value['product']['compression_inference'].update(context=32768,max_input=32768)
    elif fault=='compression_key':value['product']['compression_inference']['key_env']='FRIDAY_LLM_API_KEY'
    else:
        value['product'].pop('compression_inference');value['product'].pop('compression_multipass')
    with pytest.raises((ValueError,TypeError)):installer.spec_checked(value,cli_only=True)


def test_existing_installer_accepts_explicit_inactive_legacy_a0_split(declared_install_input):
    value=copy.deepcopy(declared_install_input);value['product']=legacy_split()
    home,_=installer.spec_checked(value,cli_only=True)
    assert str(home)==value['home']


def test_inactive_a0_zero_is_not_false():
    value=legacy_split();value['runtime']={'enabled':0}
    with pytest.raises(ValueError):compose_product(value)
