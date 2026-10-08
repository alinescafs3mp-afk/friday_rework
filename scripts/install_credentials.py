"""Explicit protected inputs into the installed Hermes credential lifecycle.

No credential store, ambient fallback, service admission or source-value receipt.
This runs only inside fresh native install completion and its original budget.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import re


def references(value):
    """Validate references without reading any credential source."""
    from scripts.friday_install import canonical, require
    require(isinstance(value, dict) and 0 < len(value) <= 64,
            'explicit_credential_references_required')
    for target, source in value.items():
        require(isinstance(target, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', target),
                'credential_reference_name_invalid')
        require(isinstance(source, dict) and set(source) == {'path', 'format', 'name'},
                'credential_reference_fields_invalid')
        require(isinstance(source['path'], str), 'credential_source_path_invalid')
        canonical(source['path'])
        require(source['format'] in ('dotenv', 'json') and isinstance(source['name'], str)
                and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', source['name']),
                'credential_source_selection_invalid')
    return value


def required_names(bundle):
    domains = bundle['contract']['required_scoped_names']
    return set(domains['inference_web']) | set(domains['dashboard']) | {
        name for names in domains['channels'].values() for name in names}


def load_selected(sources, bundle, budget):
    from scripts.friday_install import owned_file, require, unique
    from dotenv.parser import parse_stream
    budget.call(references, sources)
    require(set(sources) == required_names(bundle), 'credential_selection_mismatch')
    cache = {}; selected = {}
    for target, row in sources.items():
        key = (row['path'], row['format'])
        if key not in cache:
            raw = budget.call(owned_file, Path(row['path']), private=True)
            require(len(raw) <= 1024 * 1024, 'credential_source_too_large')
            try:
                if row['format'] == 'json':
                    values = json.loads(raw, object_pairs_hook=unique)
                else:
                    values = {}
                    for item in parse_stream(io.StringIO(raw.decode('utf-8-sig'))):
                        require(not item.error, 'credential_source_invalid')
                        if item.key is not None:
                            require(item.key not in values, 'duplicate_credential_source_name')
                            values[item.key] = item.value
                require(isinstance(values, dict), 'credential_source_invalid')
            except (UnicodeError, ValueError, TypeError):
                raise ValueError('credential_source_invalid') from None
            cache[key] = values
        value = cache[key].get(row['name'])
        # Native save deliberately sanitizes these characters. Refuse instead
        # of changing an operator's key or printing its invalid characters.
        require(isinstance(value, str) and 0 < len(value) <= 16384 and value.isascii()
                and value == value.strip() and '${' not in value
                and not any(ord(c) < 32 or ord(c) == 127 for c in value),
                'credential_value_missing_or_invalid')
        selected[target] = value
    require(selected['HERMES_DASHBOARD_BASIC_AUTH_USERNAME'] ==
            bundle['contract']['native_dashboard']['operator']['user_id'],
            'credential_operator_mismatch')
    require(len(selected['HERMES_DASHBOARD_BASIC_AUTH_SECRET']) >= 16,
            'credential_auth_secret_too_short')
    budget.check()
    return selected


def provision(sources, bundle, home, budget):
    from scripts.friday_install import Refused
    from scripts.dsh_prepare import StopUnconfirmed
    try:
        return _provision(sources, bundle, home, budget)
    except (StopUnconfirmed, Refused):
        raise
    except ValueError as exc:
        if exc.args == ('original_install_budget_exhausted',):
            raise
        raise Refused('native_credential_provisioning_failed') from None
    except Exception:
        # Native/file errors must not expose source contents, paths or keys in
        # completion's stderr. Preserve the partial home for reconciliation.
        raise Refused('native_credential_provisioning_failed') from None


def _provision(sources, bundle, home, budget):
    """Fresh home only. Partial failures stay PARTIAL; no automatic replay."""
    from scripts.friday_install import require
    from hermes_constants import get_hermes_home
    from hermes_cli.config import (get_env_path, _env_write_lock,
                                   require_env_writable, save_env_value_secure)
    from hermes_cli.friday_credential_admission import owned_values
    from agent.secret_scope import (set_secret_scope, reset_secret_scope,
                                    set_multiplex_context, reset_multiplex_context)
    require(get_hermes_home() == home and get_env_path() == home / '.env',
            'credential_receiving_home_mismatch')
    selected = load_selected(sources, bundle, budget)
    for name in selected:
        budget.call(require_env_writable, name, 'set')
    env = home / '.env'
    # Reuse the native reentrant lock for the complete batch. Never overwrite
    # an operator's existing file or a previous partially provisioned attempt.
    with _env_write_lock(env):
        budget.check()
        require(not env.exists() and not env.is_symlink(), 'existing_credentials_not_replaced')
        for name in ('auth.json',):
            require(not (home / name).exists() and not (home / name).is_symlink(),
                    'existing_credential_pool_not_adopted')
        scoped = set_secret_scope({}, profile_home=str(home))
        multiplex = set_multiplex_context(True)
        try:
            for name, value in selected.items():
                result = budget.call(save_env_value_secure, name, value)
                require(result.get('success') is True, 'native_credential_save_failed')
            require(budget.call(owned_values, home) == selected,
                    'native_credential_roundtrip_failed')
        finally:
            reset_multiplex_context(multiplex)
            reset_secret_scope(scoped)
    budget.check()
    return {'state': 'STORED_IN_NATIVE_PROFILE', 'ready': False,
            'stored_names': sorted(selected), 'provider_authentication_checked': False}
