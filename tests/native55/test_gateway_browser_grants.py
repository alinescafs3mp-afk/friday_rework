"""Gateway configuration regressions over synthetic identities and actual source.

This exercises admission relationships only; it cannot enable a user, invoke a
browser, pair Telegram, or establish installed/runtime acceptance.
"""
import copy

import pytest
from hermes_cli import friday_ordinary_gateway as gateway
from hermes_cli.friday_product_access import principal_id
from hermes_cli.friday_user_scope import BROWSER_TOOLS, SAFE


def configuration(*, browser=True):
    base = dict(runtime_profiles=['default'], admin_profiles=['default'],
                telegram_allowed_users='')
    account = dict(platform='telegram', transport_profile='default',
                   account_id='synthetic-account', runtime_profiles=['default', 'reader'])
    binding = dict(platform='telegram', transport_profile='default',
                   account_id=account['account_id'], user_id='synthetic-user',
                   runtime_profile='reader', tools=sorted(SAFE | (BROWSER_TOOLS if browser else set())))
    key = principal_id('telegram', 'default', account['account_id'], binding['user_id'])
    route = dict(name='friday-' + key, platform='telegram', bot_profile='default',
                 user_id=binding['user_id'], profile='reader', enabled=True)
    settings = dict(product_access=dict(enabled=True, accounts=[account]),
                    user_isolation=dict(enabled=True, bindings=[binding]),
                    admin=dict(profiles=['default', 'reader']))
    return dict(plugins=dict(entries=dict(friday_rework=dict(settings=settings))),
                gateway=dict(profile_routes=[route])), base


def binding(cfg):
    return cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'][0]


@pytest.mark.parametrize('browser', [True, False], ids=['complete-browser-family', 'SAFE-only'])
def test_complete_browser_family_and_SAFE_only_retain_relations(browser):
    cfg, base = configuration(browser=browser)
    before = copy.deepcopy((cfg, base))
    assert gateway.dynamic_configuration(cfg, base) == ['reader']
    assert (cfg, base) == before
    assert len(BROWSER_TOOLS) == 7


@pytest.mark.parametrize('missing', sorted(BROWSER_TOOLS))
def test_each_partial_browser_family_refused(missing):
    cfg, base = configuration()
    binding(cfg)['tools'].remove(missing)
    with pytest.raises(ValueError, match='^friday_credential_ordinary_gateway_binding_browser_family_mismatch$'):
        gateway.dynamic_configuration(cfg, base)


@pytest.mark.parametrize('fault,code', [
    ('legacy-browser', 'binding_scope_mismatch'),
    ('unknown-tool', 'binding_scope_mismatch'),
    ('duplicate-tool', 'binding_scope_mismatch'),
    ('foreign-account', 'binding_account_mismatch'),
    ('default-profile', 'binding_scope_mismatch'),
    ('foreign-profile', 'onboarding_relations_changed'),
    ('foreign-route-profile', 'onboarding_relations_changed'),
    ('foreign-route-user', 'onboarding_relations_changed'),
    ('missing-route', 'onboarding_relations_changed'),
    ('duplicate-binding', 'binding_scope_mismatch'),
])
def test_unsupported_or_foreign_configuration_refused_without_mutation(fault, code):
    cfg, base = configuration()
    row = binding(cfg)
    if fault == 'legacy-browser': row['tools'].append('browser')
    elif fault == 'unknown-tool': row['tools'].append('terminal')
    elif fault == 'duplicate-tool': row['tools'].append(sorted(BROWSER_TOOLS)[0])
    elif fault == 'foreign-account': row['account_id'] = 'foreign-account'
    elif fault == 'default-profile': row['runtime_profile'] = 'default'
    elif fault == 'foreign-profile': row['runtime_profile'] = 'foreign-profile'
    elif fault == 'foreign-route-profile': cfg['gateway']['profile_routes'][0]['profile'] = 'foreign-profile'
    elif fault == 'foreign-route-user': cfg['gateway']['profile_routes'][0]['user_id'] = 'foreign-user'
    elif fault == 'missing-route': cfg['gateway']['profile_routes'] = []
    elif fault == 'duplicate-binding':
        cfg['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings'].append(copy.deepcopy(row))
    before = copy.deepcopy((cfg, base))
    with pytest.raises(ValueError, match='^friday_credential_ordinary_gateway_' + code + '$'):
        gateway.dynamic_configuration(cfg, base)
    assert (cfg, base) == before
