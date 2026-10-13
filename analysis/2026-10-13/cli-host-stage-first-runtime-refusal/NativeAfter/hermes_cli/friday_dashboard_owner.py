"""Friday's native Dashboard ownership contract, using the host's existing lock.

Source provenance is a complete byte check, not an upstream Git version. The
Basic provider remains the only authentication implementation; no key is
published. This boundary does not admit engineering workers or a whole release.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import stat

SOURCE = Path(__file__).resolve().parents[1]


def require(ok):
    if not ok:
        raise ValueError('friday_dashboard_owner_unproved')


def read_owned(path, *, private=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    owner_uid = getattr(os, 'getuid', None)
    require(callable(owner_uid))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == owner_uid()
                and before.st_nlink == 1 and (not private or not before.st_mode & 0o077))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(64 * 1024**2 + 1)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_nlink')
        require(len(data) <= 64 * 1024**2 and all(getattr(before, k) == getattr(after, k) for k in fields))
        return data
    finally:
        os.close(fd)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_identity(home, *, source=None):
    """Actual complete composed source and truthful native install stamp."""
    source = SOURCE if source is None else Path(source)
    require(source == Path(home) / 'hermes-agent' and source.resolve() == source
            and not (source / '.git').exists())
    raw = read_owned(source.parent / 'hermes-agent.source.json', private=True)
    receipt = json.loads(raw)
    require(receipt.get('schema') == 'friday.hermes-source.v1'
            and receipt.get('status') == 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED')
    files = receipt.get('files'); require(isinstance(files, dict) and len(files) > 1000)
    require('hermes_cli/friday_dashboard_owner.py' in files)
    for name, row in files.items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts and name == str(p))
        data = read_owned(source / name)
        require(sha(data) == row['sha256'] and len(data) == row['bytes']
                and bool((source / name).stat().st_mode & 0o111) == (row['mode'] == '100755'))
    stamp = json.loads(read_owned(source / 'install-stamp.json', private=True))
    require(stamp.get('fridaySource') == {'baseTree': receipt['base_tree'], 'layers': receipt['layers']}
            and stamp.get('commit') == receipt['commit'] and stamp.get('dirty') is True)
    # Generated native dependencies/products are separate from declared source.
    # A hidden source .env or an extra importable Python module is never adopted.
    require(not (source / '.env').exists() and not (source / '.env').is_symlink())
    generated = ('.hermes/', 'node_modules/', 'ui-tui/node_modules/', 'web/node_modules/',
                 'ui-tui/dist/', 'hermes_cli/web_dist/')
    for p in source.rglob('*.py'):
        name = str(p.relative_to(source))
        require(name in files or name.startswith(generated))
    marker = json.loads(read_owned(Path(home) / 'FRIDAY-INSTALL.json', private=True))
    require(marker.get('schema') == 'friday.native-install.v1'
            and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
            and marker.get('home') == str(home) and marker.get('source') == str(source)
            and marker.get('source_receipt_sha256') == sha(raw))
    plugins = marker.get('plugin_files')
    require(isinstance(plugins, dict) and 'plugins/friday_rework/plugin.yaml' in plugins)
    for name, expected in plugins.items():
        require(name.startswith('plugins/friday_rework/') and '..' not in Path(name).parts
                and sha(read_owned(Path(home) / name, private=True)) == expected)
    target = Path(home) / 'plugins/friday_rework'
    require({str(p.relative_to(home)) for p in target.rglob('*') if not p.is_dir()} == set(plugins))
    return {'root': str(source), 'receipt': sha(raw), 'commit': receipt['commit'],
            'baseTree': receipt['base_tree'], 'plugin': sha(json.dumps(plugins, sort_keys=True).encode())}


def declared(home, *, source=None):
    contract = json.loads(read_owned(Path(home) / 'FRIDAY-PROFILE.json', private=True))
    dash = contract['native_dashboard']; operator = dash['operator']
    require(contract['profile'] == 'default' and operator['provider'] == 'basic'
            and operator['org_id'] == '' and bool(operator['user_id']))
    from hermes_cli.friday_dashboard_tls import declared_settings
    tls = declared_settings(home, dash)
    value = {'home': str(home), 'profile': contract['profile'],
            'source': source_identity(home, source=source), 'operator': operator,
            'host': dash['host'], 'port': dash['port'], 'public_url': dash['public_url']}
    if tls is not None:
        from hermes_cli.friday_dashboard_tls import files
        marker = json.loads(read_owned(Path(home) / 'FRIDAY-INSTALL.json', private=True))
        tls_bytes = files(home, dash['tls'])
        require(marker.get('tls_files') == {path: sha(tls_bytes[key])
                for key, path in dash['tls'].items()})
        value['tls'] = tls[0]
    return value


def enabled():
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    # Deleting one marker cannot silently fall back to an ordinary donor launch.
    return ((home / 'FRIDAY-PROFILE.json').exists()
            or (SOURCE.parent / 'hermes-agent.source.json').exists())


def credentials(home, operator):
    """Reuse native settings; require ambient Basic values to belong to this home."""
    from dotenv import dotenv_values
    from plugins.dashboard_auth import basic
    from plugins.dashboard_auth._shared import resolve_env_or_cfg
    env_path = Path(home) / '.env'
    scoped = dotenv_values(stream=io.StringIO(read_owned(env_path, private=True).decode()),
                           interpolate=False) if env_path.exists() or env_path.is_symlink() else {}
    names = ('USERNAME', 'PASSWORD', 'PASSWORD_HASH', 'SECRET', 'TTL_SECONDS')
    for suffix in names:
        name = 'HERMES_DASHBOARD_BASIC_AUTH_' + suffix
        value = os.environ.get(name, '').strip()
        require(not value or scoped.get(name) == value)
    section = basic._load_config_basic_auth_section()
    require(section.get('username') == operator['user_id'])
    secret = resolve_env_or_cfg('HERMES_DASHBOARD_BASIC_AUTH_SECRET', section.get('secret'))
    require(bool(secret))  # Native per-process random signing keys cannot prove reattachment.
    settings = basic._settings()
    require(settings['username'] == operator['user_id'] and len(settings['secret']) >= 16)
    plaintext = os.environ.get('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', '').strip()
    encoded = resolve_env_or_cfg('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH', section.get('password_hash', ''))
    if not encoded and not plaintext:
        plaintext = resolve_env_or_cfg('HERMES_DASHBOARD_BASIC_AUTH_PASSWORD', section.get('password', ''))
    material = 'plaintext:' + plaintext if plaintext else 'scrypt:' + encoded
    require(bool(plaintext or encoded))
    return basic, settings, plaintext, material


def expected(*, registered=False, auth_required=None, host=None, port=None):
    from hermes_constants import get_hermes_home
    from hermes_cli.config_effective import load_user_config_effective
    from hermes_cli.dashboard_auth.prefix import resolve_public_url
    home = get_hermes_home()
    from hermes_cli.friday_credential_admission import cli_host_phase
    cli_host_phase(home, full=True)
    value = declared(home)
    from hermes_yaml import YAMLError
    read_owned(home / 'config.yaml', private=True)
    try:
        cfg = load_user_config_effective(home / 'config.yaml', fail_closed=True)
    except YAMLError:
        raise ValueError('friday_dashboard_config_unreadable') from None
    dash = cfg.get('dashboard') or {}; plugins = cfg.get('plugins') or {}
    require(not os.environ.get('HERMES_DASHBOARD_PUBLIC_URL')
            or os.environ['HERMES_DASHBOARD_PUBLIC_URL'] == value['public_url'])
    admin = plugins.get('entries', {}).get('friday_rework', {}).get('settings', {}).get('admin')
    require(admin == {'enabled': True, 'operators': [value['operator']], 'profiles': [value['profile']]})
    require(dash.get('require_auth') is True
            and dash.get('public_url') == value['public_url']
            and resolve_public_url() == value['public_url']
            and 'dashboard_auth/basic' in plugins.get('enabled', [])
            and not set(plugins.get('disabled', [])).intersection({'basic', 'dashboard_auth/basic'}))
    require(host is None or host == value['host']); require(port is None or port == value['port'])
    basic, settings, plaintext, material = credentials(home, value['operator'])
    if registered:
        from hermes_cli.dashboard_auth import get_provider
        provider = get_provider('basic')
        require(type(provider) is basic.BasicAuthProvider and auth_required is True
                and provider._username == settings['username']
                and hmac.compare_digest(provider._secret, settings['secret']))
        require(basic._verify_password(plaintext, provider._password_hash) if plaintext
                else hmac.compare_digest(provider._password_hash, settings['password_hash']))
    require(dash.get('tls') == value.get('tls', {}).get('files'))
    value['authBinding'] = hmac.new(settings['secret'],
        ('friday-dashboard-v1\0' + material + '\0' + json.dumps(value, sort_keys=True)).encode(),
        hashlib.sha256).hexdigest()
    return value


def prepare_start(app, host, port, *, isolated=False, headless=False, ssh=False):
    """Claim the native serve lock BEFORE uvicorn config, port probe or bind."""
    if not enabled():
        return False
    from gateway import host_rendezvous as hr
    from hermes_cli.process_identity import is_desktop_owned_backend
    require(not isolated and not headless and not ssh and not is_desktop_owned_backend())
    identity = expected(registered=True, auth_required=app.state.auth_required, host=host, port=port)
    from gateway.status import get_process_start_time
    require(get_process_start_time(os.getpid()) is not None)
    outcome, _ = hr.claim_host_lock(hr.ROLE_SERVE)
    require(outcome is hr.HostLockOutcome.ACQUIRED)
    app.state.friday_dashboard_owner = identity
    return True


def live_identity(app):
    boot = getattr(app.state, 'friday_dashboard_owner', None)
    if boot is None:
        require(not enabled())
        return None
    from gateway import host_rendezvous as hr
    require(hr.owns_host_lock(hr.ROLE_SERVE))
    current = expected(registered=True, auth_required=app.state.auth_required,
                       host=app.state.bound_host, port=app.state.bound_port)
    require(current == boot)
    return boot


def check_attachment(record, identity=None):
    """A native record nominates a candidate; authenticated live identity proves it."""
    if not enabled():
        return
    from gateway import host_rendezvous as hr
    value = expected()
    require(record.role == hr.ROLE_SERVE and record.home == value['home']
            and record.start_time is not None and hr.liveness_is_proven(record)
            and record.protocol_version == hr.HOST_PROTOCOL_VERSION
            and value['profile'] in record.profiles
            and record.host == value['host'] and record.port == value['port']
            and record.friday_owner == value and bool(record.token_fingerprint)
            and hr.record_token_is_consistent(record))
    if identity is not None:
        verify_probe(record, identity, identity.get('probeNonce'))
        require(identity.get('protocolVersion') == hr.HOST_PROTOCOL_VERSION
                and identity.get('pid') == record.pid and identity.get('startTime') == record.start_time
                and identity.get('role') == record.role and identity.get('fridayOwner') == value
                and identity.get('auth_required') is True and identity.get('servesSpa') is True)
        require(hr.read_record(hr.ROLE_SERVE, include_stale=True) == record
                and hr.liveness_is_proven(record) and hr.record_token_is_consistent(record))


def cli_guard(args, headless):
    """Run before Desktop/isolation shortcuts or native attach probing."""
    if not enabled():
        return
    from hermes_cli.main_dashboard import _is_desktop_owned_backend
    require(not getattr(args, 'isolated', False) and not headless and not _is_desktop_owned_backend()
            and not getattr(args, 'open_profile', ''))
    expected(host=args.host, port=args.port)


def probe_headers(record):
    """Send only the existing role token; never send an admin bearer to an unproved port."""
    import secrets
    require(enabled()); check_attachment(record)
    from gateway import host_rendezvous as hr
    token = read_owned(hr.token_path(record.role), private=True).decode('utf-8-sig').strip()
    require(hr.token_fingerprint(token) == record.token_fingerprint)
    from hermes_cli.web_server import _SESSION_HEADER_NAME
    return {_SESSION_HEADER_NAME: token, 'X-Hermes-Probe-Nonce': secrets.token_hex(16)}


def proof_mac(identity, nonce, pid, start_time, token, secret):
    import re
    require(isinstance(nonce, str) and re.fullmatch('[0-9a-f]{32}', nonce))
    message = {'identity': identity, 'nonce': nonce, 'pid': pid, 'startTime': start_time,
               'tokenFingerprint': sha(token.encode())[:16]}
    return hmac.new(secret, json.dumps(message, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def verify_probe(record, payload, nonce):
    require(payload.get('probeNonce') == nonce)
    _, settings, _, _ = credentials(Path(record.home), record.friday_owner['operator'])
    from gateway import host_rendezvous as hr
    token = read_owned(hr.token_path(record.role), private=True).decode('utf-8-sig').strip()
    require(hr.token_fingerprint(token) == record.token_fingerprint)
    actual = proof_mac(record.friday_owner, nonce, record.pid, record.start_time, token, settings['secret'])
    require(isinstance(payload.get('ownerProof'), str) and hmac.compare_digest(payload['ownerProof'], actual))


def identity_session(request):
    """Native same-OS-user identity IPC only; all other routes retain Basic login.

    The existing private role token authorizes this single read. A real registered
    Basic provider creates the local request principal; no cookie/token is sent
    back or accepted on another route, and native Friday admin policy still runs.
    """
    from gateway.host_rendezvous import HOST_IDENTITY_PATH
    if request.method != 'GET' or request.url.path != HOST_IDENTITY_PATH or not enabled():
        return False
    from hermes_cli.web_server import _has_valid_session_token
    if not _has_valid_session_token(request):
        return False
    identity = live_identity(request.app)
    from hermes_cli.dashboard_auth import get_provider
    request.state.session = get_provider('basic')._mint_session(identity['operator']['user_id'])
    return True


def identity_proof(app, nonce):
    identity = live_identity(app)
    from hermes_cli.dashboard_auth import get_provider
    from hermes_cli.web_server import _SESSION_TOKEN
    from gateway.status import get_process_start_time
    return {'probeNonce': nonce, 'ownerProof': proof_mac(identity, nonce, os.getpid(),
            get_process_start_time(os.getpid()), _SESSION_TOKEN, get_provider('basic')._secret)}


def cli_check(function, *args):
    import sys
    try:
        return function(*args)
    except (OSError, ValueError, KeyError, TypeError):
        sys.stderr.write("Friday Dashboard ownership unproved; refusing attachment/start\n")
        raise SystemExit(78) from None
