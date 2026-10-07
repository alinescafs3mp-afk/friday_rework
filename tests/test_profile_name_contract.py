"""Product profile admission uses the native routing identity before effects."""
import json

import pytest

from test_product_profile import inputs, template
from test_user_onboarding import env, grant, row, ident, cas, admitted
from tools.configure_product import compose_product


INVALID = ['MixedProfile', 'Default', 'UPPER', 'test', 'tmp', 'root', 'sudo',
           'hermes', ' user', 'user ', '../user', '', 12, None]


@pytest.mark.parametrize('name', INVALID)
def test_product_identity_rejects_noncanonical_native_profile(name):
    from hermes_cli.friday_product_access import profile_name
    with pytest.raises(ValueError):
        profile_name(name)


@pytest.mark.parametrize('name', INVALID)
def test_compiler_rejects_name_before_materialization(name):
    spec = inputs()
    spec['profile'] = name
    spec['accounts'][0]['transport_profile'] = name
    with pytest.raises(ValueError):
        compose_product(spec)


@pytest.mark.parametrize('name', INVALID)
def test_onboarding_refuses_before_state_or_profile_creation(env, name):
    before = (env.home / 'config.yaml').read_bytes()
    directories = sorted(str(p) for p in env.home.rglob('*') if p.is_dir())
    with pytest.raises(ValueError):
        env.setup.prepare('default', expected_config_sha256=cas(env),
                          template='local', runtime_profile=name, **ident('201'))
    assert (env.home / 'config.yaml').read_bytes() == before
    assert sorted(str(p) for p in env.home.rglob('*') if p.is_dir()) == directories


@pytest.mark.parametrize('name', ['default', 'user-one', 'user_two', 'user3'])
def test_canonical_identity_is_preserved(name):
    from hermes_cli.friday_product_access import profile_name
    from hermes_cli.profiles import normalize_profile_name, validate_profile_name
    assert profile_name(name) == normalize_profile_name(name) == name
    validate_profile_name(name)


def test_protected_onboarding_and_actual_native_route_share_identity(env):
    from gateway.profile_routing import parse_profile_routes, match_profile_route
    from hermes_cli.config import load_config_readonly
    bundle = compose_product(inputs())
    config, plan = bundle['config'], template(bundle)
    config['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['approved-local'] = plan
    (env.home / 'config.yaml').write_text(json.dumps(config), encoding='utf-8')
    (env.home / 'config.yaml').chmod(0o600)
    profile = 'user-201'  # The shared admission fixture derives this native home from uid.
    prepared = env.setup.prepare('default', expected_config_sha256=cas(env),
                                 template='approved-local', runtime_profile=profile, **ident('201'))
    assert prepared['enabled'] is False
    grant(env, '201')
    for name in plan['required_secrets']:
        env.setup.credentials('default', expected_config_sha256=cas(env),
                              generation=row(env, '201')['generation'],
                              **ident('201'), name=name, value='synthetic-' + name)
    activated = env.setup.activate('default', expected_config_sha256=cas(env),
                                   generation=row(env, '201')['generation'], **ident('201'))
    assert activated['state'] == 'ADMITTED_NEXT_NATIVE_REQUEST'
    route = match_profile_route(parse_profile_routes(load_config_readonly()['gateway']['profile_routes']),
                                'telegram', user_id='201', adapter_profile='default')
    assert route.profile == profile
    assert (env.home / 'profiles' / route.profile).is_dir()
    assert admitted(env, '201')[0]
