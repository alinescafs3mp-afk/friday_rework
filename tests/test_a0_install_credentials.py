"""Declared A0 installation keys precede, and never grant, worker admission."""
import copy
import json

import pytest

from scripts import friday_native, install_credentials
from scripts.install_containment import Budget
from test_a0_profile_portability import future, product
from test_native_installer import native_home
from plugins.friday_rework.adapters.a0_profile import legacy_profile


@pytest.mark.parametrize('tier', ['exa-paid', 'exa-keyless'])
@pytest.mark.parametrize('deployment', ['legacy', 'future'])
def test_declared_a0_keys_provision_before_runtime_admission(tmp_path, tier, deployment):
    from hermes_cli import friday_credential_admission as admission
    from plugins.dashboard_auth.basic import hash_password

    spec = product(legacy_profile() if deployment == 'legacy' else future())
    spec['web']['profile'] = tier
    home = tmp_path / 'fresh'; home.mkdir(mode=0o700)
    with native_home(home):
        bundle = friday_native.profile_write(home, spec)
        assert bundle['contract']['ready'] is False
        assert bundle['config']['plugins']['entries']['friday_rework']['settings']['runtime'] == {'enabled': False}
        services = ['FRIDAY_EMBEDDINGS_API_KEY', 'SEARXNG_SECRET']
        assert bundle['contract']['required_scoped_names']['worker_service'] == services
        assert admission.profile_policy(home, bundle['config']) == bundle['contract']
        values = {name: 'SYNTHETIC-' + name for name in install_credentials.required_names(bundle)}
        values['HERMES_DASHBOARD_BASIC_AUTH_USERNAME'] = spec['dashboard']['operator']['user_id']
        values['HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH'] = hash_password('synthetic-password')
        source = tmp_path / 'keys.json'; source.write_text(json.dumps(values)); source.chmod(0o600)
        refs = {name: {'path': str(source), 'format': 'json', 'name': name} for name in values}
        for missing in services:
            incomplete = copy.deepcopy(refs); del incomplete[missing]
            with pytest.raises(ValueError, match='credential_selection_mismatch'):
                install_credentials.provision(incomplete, bundle, home, Budget(30))
            assert not (home / '.env').exists()
        result = install_credentials.provision(refs, bundle, home, Budget(30))
        assert admission.owned_values(home) == values
        assert result['ready'] is False and result['provider_authentication_checked'] is False
        # The native consumer also rejects a template contract that drops these
        # keys while preserving the declared A0 deployment in configuration.
        contract = copy.deepcopy(bundle['contract'])
        contract['required_scoped_names']['inference_web'] = [n for n in contract['required_scoped_names']['inference_web'] if n not in services]
        contract['required_scoped_names']['worker_service'] = []
        (home / 'FRIDAY-PROFILE.json').write_text(json.dumps(contract))
        with pytest.raises(ValueError, match='inference_contract_mismatch'):
            admission.profile_policy(home, bundle['config'])
