"""Product principal capability over native admission and exclusive native homes.

No user database, history mirror, shell or environment-derived identity. An
operator prepares a NEW native profile; adoption of an existing home is refused.
This source seam does not authorize installation or workers/network execution.
"""
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from hermes_cli.friday_product_access import principal_id, profile_name, text

_CURRENT = ContextVar('friday_authenticated_user_scope', default=None)
_SOURCE = ContextVar('friday_authenticated_file_source', default=None)
_ENGAGED = False
_DELEGATION = ContextVar('friday_native_delegation', default=None)
MARKER = '.friday-user-scope.json'
SAFE = frozenset({'memory', 'session_search', 'read_file', 'write_file',
                  'web_search', 'web_extract', 'friday_work', 'friday_result', 'delegate_task',
                  'skills_list', 'skill_view', 'skill_manage'})
# Explicit, narrow family. SAFE retains its existing ordinary capabilities;
# configuration may prepare this family while execution remains fail closed.
BROWSER_TOOLS = frozenset({'browser_navigate', 'browser_snapshot', 'browser_click',
    'browser_type', 'browser_scroll', 'browser_back', 'browser_press'})
BROWSER_TOOLSET = 'browser_scoped'
BROWSER_LOCAL_CONFIG = {
    'backend': 'off', 'cloud_provider': 'local', 'engine': 'chrome',
    'headed': False, 'cdp_url': '', 'use_real_profile': False,
    'record_sessions': False, 'allow_private_urls': False,
    'auto_local_for_private_urls': False,
    'extension_control': {'enabled': False, 'developer_mode': False},
    'command_timeout': 30, 'inactivity_timeout': 120,
}


def validate_browser_config(config, tools, platform=None):
    """Reject ambient browser selection or authority wider than the named family."""
    granted = set(tools) & BROWSER_TOOLS
    if not granted and 'browser' not in config:
        return
    if (granted != BROWSER_TOOLS or not isinstance(config.get('browser'), dict)
            or _fingerprint(config['browser']) != _fingerprint(BROWSER_LOCAL_CONFIG)):
        raise ScopeDenied()
    selected = config.get('toolsets', [])
    platforms = config.get('platform_toolsets', {})
    if (not isinstance(selected, list) or BROWSER_TOOLSET not in selected
            or 'browser' in selected or not isinstance(platforms, dict)):
        raise ScopeDenied()
    for values in platforms.values():
        if not isinstance(values, list) or 'browser' in values:
            raise ScopeDenied()
    if platform is not None and BROWSER_TOOLSET not in platforms.get(platform, []):
        raise ScopeDenied()


def browser_admission_error(tools):
    # Configuration is a named family, not a daemon/network grant. Actual
    # execution requires authenticated context and verified native custody at
    # browser_scoped.execute; missing placement/packages fail that action only.
    return None


BRIDGES = frozenset({'tool_search', 'tool_describe', 'tool_call'})


class ScopeDenied(PermissionError):
    def __init__(self):
        super().__init__('product_user_scope_refused')


def _owner_uid():
    """Refuse unsupported owner verification; names cannot prove numeric ownership."""
    getuid = getattr(os, 'getuid', None)
    if not callable(getuid):
        raise ScopeDenied()
    return getuid()


def _private(path, *, directory=False):
    st = path.lstat()
    if (stat.S_ISLNK(st.st_mode) or st.st_uid != _owner_uid()
            or st.st_mode & 0o077 or (directory and not stat.S_ISDIR(st.st_mode))
            or (not directory and (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1))):
        raise ScopeDenied()
    return st


@contextmanager
def authority(home):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    token = set_hermes_home_override(str(home))
    try:
        yield
    finally:
        reset_hermes_home_override(token)


def policy(home):
    from hermes_cli.friday_product_access import settings, access_policy
    with authority(home):
        value = settings().get('user_isolation')
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) != {'enabled', 'bindings'}
                or value['enabled'] is not True or access_policy() is None
                or not isinstance(value['bindings'], list) or not 0 < len(value['bindings']) <= 10000):
            raise ScopeDenied()
        keys, profiles = set(), set()
        for row in value['bindings']:
            if not isinstance(row, dict) or set(row) != {
                'platform', 'transport_profile', 'account_id', 'user_id', 'runtime_profile', 'tools'}:
                raise ScopeDenied()
            key = principal_id(*(row[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')))
            profile = profile_name(row['runtime_profile'])
            if (profile == 'default' or key in keys or profile in profiles
                    or not isinstance(row['tools'], list) or not row['tools']
                    or len(set(row['tools'])) != len(row['tools']) or not set(row['tools']) <= SAFE | BROWSER_TOOLS):
                raise ScopeDenied()
            keys.add(key); profiles.add(profile)
        return value


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _same_scope(left, right):
    return (isinstance(left, UserScope) and isinstance(right, UserScope)
            and left.principal == right.principal and left.home == right.home
            and left.authorization_home == right.authorization_home and left.binding == right.binding
            and left.admission_generation == right.admission_generation
            and left.directory_identity == right.directory_identity
            and getattr(left, "session_authority", None) == getattr(right, "session_authority", None))


@dataclass
class UserScope:
    authorization_home: Path
    home: Path
    profile: str
    principal: tuple
    binding: dict
    directory_identity: tuple
    admission_generation: int = None
    revoked: bool = False

    @property
    def key(self):
        return principal_id(*self.principal)

    def check(self):
        # Revocation is sticky for this retained capability; a later enable does
        # not resume an old turn/job or reset any existing task budget.
        try:
            if self.revoked:
                raise ScopeDenied()
            from hermes_constants import get_hermes_home
            if get_hermes_home() != self.home:
                raise ScopeDenied()
            current = policy(self.authorization_home)
            rows = [] if current is None else [r for r in current['bindings']
                if principal_id(*(r[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id'))) == self.key]
            if len(rows) != 1 or rows[0] != self.binding:
                raise ScopeDenied()
            from hermes_cli.friday_product_access import current_access, access_policy
            with authority(self.authorization_home):
                access = current_access()['users'].get(self.key)
                accounts = access_policy()['accounts']
            if (not access or access['enabled'] is not True
                    or type(self.admission_generation) is not int or self.admission_generation < 1
                    or access.get('generation') != self.admission_generation):
                raise ScopeDenied()
            matches = [r for r in accounts if (r['platform'], r['transport_profile'], r['account_id']) == self.principal[:3]
                       and self.profile in r['runtime_profiles']]
            if len(matches) != 1:
                raise ScopeDenied()
            st = _private(self.home, directory=True)
            if (st.st_dev, st.st_ino) != self.directory_identity:
                raise ScopeDenied()
            _private(self.home / MARKER)
            marker = json.loads((self.home / MARKER).read_text(encoding="utf-8-sig"))
            expected = {'schema': 'friday.user-home.v1', 'principal': self.key,
                        'profile': self.profile, 'binding_sha256': _fingerprint(self.binding)}
            if 'onboarding_sha256' in marker:
                _private(self.home / ONBOARDING)
                expected['onboarding_sha256'] = hashlib.sha256((self.home / ONBOARDING).read_bytes()).hexdigest()
            if marker != expected:
                raise ScopeDenied()
            check_onboarding_home(self.authorization_home, self.home, self.binding)
            for name in ('memories', 'workspace'):
                _private(self.home / name, directory=True)
            for name in ('state.db', 'config.yaml', '.env', 'auth.json', 'SOUL.md'):
                if (self.home / name).exists() or (self.home / name).is_symlink():
                    _private(self.home / name)
            return self
        except Exception:  # health: allow BLE001 -- Revoke on any authority failure; config/plugin exceptions may contain secrets.
            self.revoked = True
            raise ScopeDenied() from None

    def _require_owner_identity(self, owner, ingress):
        self.check()
        expected = {'platform': self.principal[0], 'user_id': self.principal[3]}
        if any(owner.get(k) != v for k, v in expected.items()):
            raise ScopeDenied()
        message = ingress.get('message', {})
        if (ingress.get('platform') != self.principal[0]
                or ingress.get('transport_profile') != self.principal[1]
                or ingress.get('runtime_profile') != self.profile
                or ingress.get('source_profile') not in ('', self.profile)
                or message.get('bot_id') != self.principal[2]
                or any(message.get(k) != owner.get(k) for k in ('user_id', 'chat_id', 'thread_id'))):
            raise ScopeDenied()

    def require_owner(self, owner, ingress):
        """Ambient native call owner keeps the serialized source profile."""
        self._require_owner_identity(owner, ingress)
        if owner.get('profile') != ingress.get('source_profile'):
            raise ScopeDenied()

    def require_retained_owner(self, owner, ingress):
        """Association owner keeps runtime identity, independently of source.

        Native scoped_source accepts an unset source profile with an explicit
        RoutingIdentity. Its admitted receipt serializes that value as empty;
        neither that receipt nor the original association is relabelled here.
        """
        self._require_owner_identity(owner, ingress)
        if (owner.get('profile') != self.profile
                or owner.get('bot_id') != self.principal[2]):
            raise ScopeDenied()


def admit_source(source):
    """Called ONLY after the existing native principal authorization succeeded."""
    from gateway.session_identity import identity_of
    identity = identity_of(source)
    if identity is None:
        from hermes_constants import get_hermes_home
        if policy(get_hermes_home()) is not None:
            raise ScopeDenied()
        return
    active = policy(identity.authorization_home)
    if active is None:
        return
    global _ENGAGED
    _ENGAGED = True
    if identity.transport_inferred or not identity.multiplexed:
        raise ScopeDenied()
    from hermes_cli.friday_product_access import access_policy, current_access
    with authority(identity.authorization_home):
        accounts = access_policy()['accounts']
        admitted_access = current_access()['users']
    accounts = [r for r in accounts if r['platform'] == source.platform.value
                and r['transport_profile'] == identity.transport_profile]
    if len(accounts) != 1:
        raise ScopeDenied()
    principal = (source.platform.value, identity.transport_profile, accounts[0]['account_id'], text(source.user_id))
    access = admitted_access.get(principal_id(*principal))
    if (not access or access['enabled'] is not True
            or type(access.get('generation')) is not int or access['generation'] < 1):
        raise ScopeDenied()
    rows = [r for r in active['bindings'] if tuple(r[k] for k in
        ('platform', 'transport_profile', 'account_id', 'user_id')) == principal]
    if len(rows) != 1 or rows[0]['runtime_profile'] != identity.runtime_profile:
        raise ScopeDenied()
    # Caller-requested source.profile/home cannot grant a different native home.
    from hermes_constants import get_default_hermes_root
    root = get_default_hermes_root(home=identity.authorization_home)
    home = root / 'profiles' / identity.runtime_profile
    if identity.runtime_home != home or home.resolve() != home:
        raise ScopeDenied()
    previous = getattr(source, '_friday_user_scope', None)
    if isinstance(previous, UserScope):
        if (previous.principal != principal or previous.home != home
                or previous.binding != rows[0] or previous.authorization_home != identity.authorization_home):
            previous.revoked = True
            raise ScopeDenied()
        with authority(home):
            previous.check()
        return
    st = _private(home, directory=True)
    capability = UserScope(identity.authorization_home, home, identity.runtime_profile,
                           principal, dict(rows[0]), (st.st_dev, st.st_ino), access['generation'])
    with authority(home):
        capability.check()
    source._friday_user_scope = capability


@contextmanager
def scoped_source(source):
    """Enter after native profile routing, before prompt/history/tool readers."""
    from gateway.session_identity import identity_of
    identity = identity_of(source)
    from hermes_constants import get_hermes_home
    home = identity.authorization_home if identity is not None else get_hermes_home()
    if policy(home) is None:
        if _CURRENT.get() is not None:
            raise ScopeDenied()  # child cannot silently clear an inherited user
        yield
        return
    cap = getattr(source, '_friday_user_scope', None)
    if (not isinstance(cap, UserScope) or identity is None
            or cap.principal[0] != source.platform.value or cap.principal[3] != source.user_id
            or cap.profile != identity.runtime_profile or cap.home != identity.runtime_home
            or cap.authorization_home != identity.authorization_home
            or cap.principal[1] != identity.transport_profile
            or source.profile not in (None, '', cap.profile)
            or identity.transport_inferred or not identity.multiplexed):
        raise ScopeDenied()
    parent = _CURRENT.get()
    if parent is not None:
        if not _same_scope(parent, cap):
            raise ScopeDenied()
        parent.check()
    cap.check()
    token = _CURRENT.set(cap)
    source_token = _SOURCE.set(source)
    try:
        check_database(cap)
        yield cap
    finally:
        _SOURCE.reset(source_token)
        _CURRENT.reset(token)


@contextmanager
def native_source_scope(source, native):
    with native:
        with scoped_source(source) as cap:
            yield cap


@asynccontextmanager
async def async_native_source_scope(source, native):
    async with native:
        with scoped_source(source) as cap:
            yield cap


def current(required=False):
    cap = _CURRENT.get()
    if cap is not None:
        return cap.check()
    if required or _ENGAGED:
        raise ScopeDenied()
    return None


def slash_allowed(source, command):
    """Native slash/quick/plugin dispatch keeps the same authenticated boundary."""
    if not command:
        return True
    try:
        from gateway.session_identity import identity_of
        from hermes_constants import get_hermes_home
        identity = identity_of(source)
        authorization_home = identity.authorization_home if identity is not None else get_hermes_home()
        if policy(authorization_home) is None:
            return not _ENGAGED
        cap = getattr(source, '_friday_user_scope', None)
        if not isinstance(cap, UserScope) or identity is None:
            return False
        with authority(identity.runtime_home):
            with scoped_source(source):
                cap.check()
        return command in {'help', 'status', 'stop', 'cancel', 'new', 'reset', 'queue', 'memory', 'compress'}
    except Exception:  # health: allow BLE001 -- Slash admission fails closed without exposing policy or plugin secrets.
        return False


def check_context_path(path):
    cap = current()
    if cap is None:
        return
    check_database(cap)
    path = Path(path)
    if path != cap.home / 'SOUL.md' and not path.is_relative_to(cap.home / 'workspace'):
        raise ScopeDenied()
    if path.resolve() != path:
        raise ScopeDenied()
    if path.exists():
        _private(path)


def guard_tool(name, args, registry_scope=None, *, execution=True):
    from hermes_cli.friday_credential_admission import session_artifact_tool, ordinary_readonly_tool, CredentialDenied
    try:
        ordinary_readonly_tool(name,args)
        session_artifact_tool(name,args)
    except CredentialDenied:
        raise ScopeDenied() from None
    from agent.web_call_context import web_retry_refused
    # Opaque worker launches have no machine no-web declaration. Existing
    # result readback, safe tools, and native delegated work remain available.
    if execution and web_retry_refused() and name in BROWSER_TOOLS | {
            'web_search', 'web_extract', 'friday_work'}:
        raise ScopeDenied()
    cap = current()
    if cap is None:
        return
    if registry_scope is not None and str(registry_scope) != str(cap.home):
        raise ScopeDenied()
    check_database(cap)
    if name in {'tool_search', 'tool_describe'}:
        return  # catalog visibility is not permission to execute
    if name == 'tool_call':
        # Use the donor's actual normalizer for advertised/legacy/JSON forms.
        # Preflight the entire envelope before native expansion or dispatch.
        from tools.tool_search_validation import normalize_tool_call_entries
        from tools.connectors.gateway.config import MAX_CALLS_PER_DISPATCH
        if not isinstance(args, dict):
            raise ScopeDenied()
        entries, error = normalize_tool_call_entries(args)
        if error or not 1 <= len(entries) <= MAX_CALLS_PER_DISPATCH:
            raise ScopeDenied()
        for entry in entries:
            if entry['name'] in BRIDGES:
                raise ScopeDenied()
            # Envelope preflight proves authority only; actual per-call dispatch
            # reads the native fence, so safe siblings are not rejected as a batch.
            guard_tool(entry['name'], entry['arguments'], registry_scope, execution=False)
        return
    if name not in cap.binding['tools']:
        raise ScopeDenied()
    if name in BROWSER_TOOLS:
        from hermes_cli.config import require_readable_config_before_write
        validate_browser_config(require_readable_config_before_write(cap.home / 'config.yaml'),
                                cap.binding['tools'], cap.principal[0])
        if browser_admission_error(cap.binding['tools']):
            raise ScopeDenied()
    delegated = _DELEGATION.get()
    if delegated is not None:
        check_delegation(delegated)
        if name not in delegated['tools']:
            raise ScopeDenied()


def check_memory(store=None):
    cap = current()
    retained = getattr(store, '_friday_user_scope', None) if store is not None else None
    if retained is not cap and (retained is not None or cap is not None):
        if not _same_scope(retained, cap):
            raise ScopeDenied()
        retained.check()
    if cap is not None:
        check_database(cap)
        for name in ('MEMORY.md', 'USER.md', 'MEMORY.md.lock', 'USER.md.lock'):
            path = cap.home / 'memories' / name
            if path.exists() or path.is_symlink():
                _private(path)


def capture_agent(agent):
    agent._friday_user_scope = current()
    agent._friday_delegation = _DELEGATION.get()
    if agent._friday_delegation is not None:
        check_delegation(agent._friday_delegation)


def check_retained_job(row):
    """Original association keeps its admission; a new event cannot adopt it.

    Administrative read-all and exact-owned stop are separate native paths.
    Ordinary legacy jobs without a retained generation require reconciliation.
    """
    binding = row['host']['binding']
    retained = binding.get('user_authority')
    cap = current()
    if cap is None:
        from hermes_constants import get_default_hermes_root
        home = Path(binding['runtime']['runtime_home'])
        if retained is not None or (home / MARKER).exists() or policy(get_default_hermes_root(home=home)) is not None:
            raise ScopeDenied()
        return
    owner = dict(row['owner'])
    # Native association owners keep platform in the original ingress binding;
    # ambient tool owners additionally have the platform field themselves.
    owner.setdefault('platform', binding['ingress']['platform'])
    cap.require_retained_owner(owner, binding['ingress'])
    if (Path(binding['runtime']['runtime_home']) != cap.home
            or retained != {'principal_id': cap.key, 'generation': cap.admission_generation}):
        raise ScopeDenied()


def check_agent(agent):
    cap = current()
    retained = getattr(agent, '_friday_user_scope', None)
    if retained is not cap:
        if not _same_scope(retained, cap):
            raise ScopeDenied()
        retained.check()
    if cap is not None:
        delegated = getattr(agent, '_friday_delegation', None)
        if delegated is not None:
            hard = getattr(agent, '_hard_interrupt_requested', None)
            if getattr(agent, '_interrupt_requested', False) or (hard is not None and hard.is_set()):
                delegated['cancelled'] = True
            check_delegation(delegated)
        check_database(cap)



def delegation_authority():
    """Nonsecret retained identity in the EXISTING native delegation record."""
    cap = current()
    if cap is None:
        return None
    value = {'principal': list(cap.principal), 'profile': cap.profile,
            'home': str(cap.home), 'authorization_home': str(cap.authorization_home),
            'binding_sha256': _fingerprint(cap.binding),
            'generation': cap.admission_generation}
    if cap.principal[0] == 'cli':
        from hermes_cli.friday_cli_principal import cli_session_authority
        value['native_cli'] = cli_session_authority(cap)
    return value


def delegation_visible(pin):
    """An ambient new grant cannot adopt an old or foreign delegation."""
    try:
        cap = current()
        if cap is None:
            from hermes_constants import get_hermes_home
            return pin is None and not (get_hermes_home() / MARKER).exists()
        return pin is not None and pin == delegation_authority()
    except ScopeDenied:
        return False


def check_delegation(delegated):
    import time
    if (not isinstance(delegated, dict)
            or not delegation_visible(delegated.get('authority'))):
        raise ScopeDenied()
    if delegated.get('cancelled') is True:
        raise ScopeDenied()
    parent = delegated['parent']
    check_agent(parent)
    hard = getattr(parent, '_hard_interrupt_requested', None)
    if (getattr(parent, '_interrupt_requested', False)
            or (hard is not None and hard.is_set())):
        delegated['cancelled'] = True
        raise ScopeDenied()
    deadline = delegated['deadline']
    if deadline is not None and time.monotonic() >= deadline:
        raise ScopeDenied()


@contextmanager
def child_construction(parent, runtime):
    """Bind identity and original budget BEFORE child DB/client construction."""
    cap = current()
    if cap is None:
        yield {}
        return
    check_agent(parent)
    from tools.delegate_tool_toolsets import DELEGATE_BLOCKED_TOOLS
    from hermes_cli.friday_credential_admission import route_inputs, runtime_checked
    route = route_inputs(
        runtime.get('provider'), runtime.get('base_url'), runtime.get('api_key'), runtime.get('model'))
    runtime_checked(runtime, route)  # actual three-value route + checked local key/transport
    if (runtime.get('fallback_model')
            or runtime.get('acp_command') or runtime.get('acp_args')
            or runtime.get('command') or runtime.get('args')
            or getattr(parent, '_user_id', None) != cap.principal[3]
            or not getattr(parent, 'session_id', None)
            or Path(getattr(getattr(parent, '_session_db', None), 'db_path', '')) != cap.home / 'state.db'):
        raise ScopeDenied()
    names = set(getattr(parent, 'valid_tool_names', ()))
    tools = frozenset((names & set(cap.binding['tools'])) - set(DELEGATE_BLOCKED_TOOLS))
    delegated = {'parent': parent, 'authority': delegation_authority(), 'tools': tools,
                 # A delegated task shares the parent's original web capability;
                 # a fresh child turn must not bypass its native failure fence.
                 'web_turn': getattr(parent, '_web_turn', None),
                 'deadline': getattr(parent, '_web_run_deadline', None),
                 'started_at': getattr(parent, '_run_budget_started_at', None),
                 'iteration_budget': getattr(parent, 'iteration_budget', None), 'cancelled': False}
    if getattr(parent, 'run_budget_seconds', None) and (
            delegated['deadline'] is None or delegated['started_at'] is None):
        raise ScopeDenied()
    check_delegation(delegated)
    token = _DELEGATION.set(delegated)
    try:
        identity = {k: getattr(parent, '_' + k, None) for k in
                    ('user_id', 'user_id_alt', 'user_name', 'chat_id', 'chat_name', 'chat_type', 'thread_id')}
        if delegated['iteration_budget'] is None:
            raise ScopeDenied()
        identity.update(iteration_budget=delegated['iteration_budget'],
                        run_budget_seconds=getattr(parent, 'run_budget_seconds', None))
        yield identity
    finally:
        _DELEGATION.reset(token)


@contextmanager
def delegated_agent(agent):
    check_agent(agent)
    delegated = getattr(agent, '_friday_delegation', None)
    if delegated is None:
        check_agent(agent)
        yield
        return
    check_delegation(delegated)
    token = _DELEGATION.set(delegated)
    try:
        yield
    finally:
        _DELEGATION.reset(token)


def restrict_child_tools(child):
    check_agent(child)
    delegated = getattr(child, '_friday_delegation', None)
    if delegated is None:
        return
    check_delegation(delegated)
    allowed = delegated['tools'] | BRIDGES
    child.tools = [row for row in child.tools if row.get('function', {}).get('name') in allowed]
    child.valid_tool_names = {row['function']['name'] for row in child.tools}


def delegation_session_origin(agent, raw):
    cap = current()
    if cap is None:
        return raw
    check_agent(agent)
    if getattr(agent, '_user_id', None) != cap.principal[3]:
        raise ScopeDenied()
    origin = json.loads(raw or '{}')
    origin['friday_account_origin'] = {'schema': 'friday.account_origin.v1',
        'platform': cap.principal[0], 'transport_profile': cap.principal[1], 'account_id': cap.principal[2]}
    if getattr(agent, '_friday_delegation', None) is not None:
        origin['friday_delegation_authority'] = delegation_authority()
    if cap.principal[0] == 'cli':
        from hermes_cli.friday_cli_principal import cli_session_authority
        origin['friday_cli_authority'] = cli_session_authority(cap)
    origin['platform'] = cap.principal[0]
    origin['profile'] = cap.profile
    return json.dumps(origin)


def check_search(profile=None, session_id=None, db=None):
    cap = current()
    if cap is None:
        return
    if profile not in (None, '', cap.profile):
        raise ScopeDenied()
    if isinstance(session_id, str) and '/' in session_id:
        prefix, _, identifier = session_id.partition('/')
        if prefix != cap.profile or not identifier or '/' in identifier:
            raise ScopeDenied()
    # A caller-supplied DB cannot substitute a sibling/administrative store.
    if db is not None and Path(db.db_path) != cap.home / 'state.db':
        raise ScopeDenied()
    check_database(cap)


def check_database(cap=None):
    """Refuse legacy/unproved/mixed stores before transcript/preview/FTS bytes.

    Native account origin stays authoritative and unchanged. This is an
    integrity check, not migration or permission from a guessed current route.
    """
    cap = current() if cap is None else cap.check()
    if cap is None or not (cap.home / 'state.db').exists():
        return
    import sqlite3
    path = cap.home / 'state.db'
    _private(path)
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.2)
    try:
        connection.execute('PRAGMA query_only=ON')
        _check_database_rows(cap, connection)
    except (ScopeDenied, sqlite3.Error, ValueError, TypeError, AttributeError):
        cap.revoked = True
        raise ScopeDenied() from None
    finally:
        connection.close()



def _check_database_rows(cap, connection):
    """Validate native session ownership on a caller-pinned read transaction."""
    try:
        rows = connection.execute('SELECT user_id, origin_json, profile_name FROM sessions LIMIT 10001').fetchall()
        if len(rows) > 10000:
            raise ScopeDenied()  # integrity inspection bound, never skip later rows
        for user, raw, profile in rows:
            origin = json.loads(raw or '{}')
            if cap.principal[0] == 'cli':
                from hermes_cli.friday_cli_principal import cli_session_authority
                if origin.get('friday_cli_authority') != cli_session_authority(cap):
                    raise ScopeDenied()
            account = origin.get('friday_account_origin')
            if (str(user) != cap.principal[3] or profile != cap.profile
                    or account != {'schema': 'friday.account_origin.v1', 'platform': cap.principal[0],
                                   'transport_profile': cap.principal[1], 'account_id': cap.principal[2]}):
                raise ScopeDenied()
    except (ScopeDenied, ValueError, TypeError, AttributeError):
        cap.revoked = True
        raise ScopeDenied() from None


def provision_new_home(authorization_home, binding, native_config, *, publish=True, verify=None):
    """Operator-only preparation primitive; never called by a model/tool.

    No clone/import. Native profile name must be declared by protected policy;
    only explicit non-secret model/tool settings, no plugin/code/context import.
    """
    _owner_uid()  # Refuse unsupported hosts before creating any profile state.
    root = Path(authorization_home)
    active = policy(root)
    if active is None or binding not in active['bindings'] or not isinstance(native_config, dict):
        raise ScopeDenied()
    if not set(native_config) <= {'model', 'toolsets', 'max_iterations'}:
        raise ScopeDenied()
    model = native_config.get('model', {})
    if not isinstance(model, dict) or not set(model) <= {'default', 'base_url', 'provider'}:
        raise ScopeDenied()
    if model:
        from urllib.parse import urlsplit
        import ipaddress
        try:
            endpoint = urlsplit(model['base_url'])
            address = ipaddress.ip_address(endpoint.hostname)
            networks = [ipaddress.ip_network(n) for n in ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128')]
            if (not any(address in n for n in networks) or endpoint.scheme not in {'http', 'https'}
                    or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                    or endpoint.path.rstrip('/') != '/v1' or model.get('provider') != 'custom'):
                raise ScopeDenied()
        except (KeyError, ValueError, TypeError):
            raise ScopeDenied() from None
    # Exact current config is an operator input, not copied from another profile.
    from hermes_constants import get_default_hermes_root
    home = get_default_hermes_root(home=root) / 'profiles' / binding['runtime_profile']
    home.parent.mkdir(mode=0o700, exist_ok=True)
    if home.parent.resolve() != home.parent:
        raise ScopeDenied()
    home.mkdir(mode=0o700)  # EEXIST refuses owner/legacy profile adoption
    try:
        for name in ('memories', 'workspace'):
            (home / name).mkdir(mode=0o700)
        marker = {'schema': 'friday.user-home.v1',
                  'principal': principal_id(*(binding[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id'))),
                  'profile': binding['runtime_profile'], 'binding_sha256': _fingerprint(binding)}
        from hermes_cli.config import atomic_config_write, config_write_transaction
        with authority(home), config_write_transaction(home / 'config.yaml'):
            # Onboarding retains its existing verified operator across this
            # first native write too; callers cannot skip the actual lock wait.
            if verify is not None: verify()
            atomic_config_write(home / 'config.yaml', native_config)
        files = [(MARKER, marker)] if publish else []
        for name, value in files:
            fd = os.open(home / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(value, f); f.write('\n'); f.flush(); os.fsync(f.fileno())
    except (OSError, ValueError, TypeError):
        # An incomplete home remains unaccepted; never erase uncertain user data.
        raise ScopeDenied() from None
    return home


def scoped_file(name, args, *, task_id="default"):
    """Existing native file tool entrypoint, confined descriptor operations.

    ShellFileOperations cannot confine arbitrary shell reads. Product text I/O
    uses the same tool names but a descriptor-only local backend; complex native
    file/shell operations stay explicitly unaccepted until sandbox composition.
    """
    from hermes_cli.friday_credential_admission import session_artifact_file, ordinary_readonly_file, CredentialDenied
    try:
        artifact = ordinary_readonly_file(name,args)
        if artifact is None:
            artifact = session_artifact_file(name,args) if current() is None else None
    except (CredentialDenied,OSError,ValueError):
        raise ScopeDenied() from None
    if artifact is not None:
        return artifact
    cap = current()
    if cap is None:
        return None
    guard_tool(name, args)
    raw = args.get('path')
    if not isinstance(raw, str) or not raw or '\x00' in raw:
        raise ScopeDenied()
    root = cap.home / 'workspace'
    path = Path(raw)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            raise ScopeDenied() from None
    parts = path.parts
    if not parts or any(p in ('.', '..') or p.startswith('.') for p in parts):
        raise ScopeDenied()
    fd = _workspace_directory(cap)
    try:
        for component in parts[:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = next_fd
            st = os.fstat(fd)
            if st.st_uid != _owner_uid() or st.st_mode & 0o077:
                raise ScopeDenied()
        cap.check()
        if name == 'read_file':
            from hermes_cli import friday_workspace_revision as revision
            document_format = path.suffix.lower().lstrip('.') if path.suffix.lower() in {'.docx', '.pdf'} else None
            if document_format:
                from tools.read_extract import extract_scoped_document_bytes, ScopedExtractionError
                data, _ = workspace_document(str(root / path), max_bytes=1000000)
                revision.check(cap)
                try:
                    text = extract_scoped_document_bytes(data, document_format)
                except ScopedExtractionError as exc:
                    revision.check(cap)
                    return json.dumps({'success': False, 'error': 'document_extraction_failed',
                                       'format': document_format, 'reason': exc.code})
                revision.check(cap)
                lines = text.splitlines()
            else:
                data, version = revision.snapshot(fd, parts[-1])
                cap.check()
                lines = data.decode('utf-8').splitlines()
            starts=[]; cursor=1
            for line in lines:
                starts.append(cursor); cursor += len(line)+1
            total_units=max(1,cursor-1)
            seen=[]
            def record_read(rendered):
                if document_format:
                    revision.check(cap)
                    return  # Extracted text never grants raw binary overwrite coverage.
                revision.note_read(cap,task_id,path.as_posix(),version,
                                   seen if lines else [(1,1)],total_units,rendered)

            offset = args.get('offset', 1); limit = args.get('limit', 2000)
            if type(offset) is not int or type(limit) is not int or not 1 <= offset <= 1000000 or not 1 <= limit <= 2000:
                raise ScopeDenied()
            from agent.bounded_context import bounded_tool_result_budget, serialized_bytes
            budget = bounded_tool_result_budget()
            if document_format and budget is None:
                budget = 100000
            char_offset = args.get('char_offset', 0)
            if type(char_offset) is not int or not 0 <= char_offset <= 1000000:
                raise ScopeDenied()
            if budget is not None:
                if offset <= len(lines) and char_offset > len(lines[offset-1]):
                    raise ScopeDenied()
                result = {'success': True, 'content': '', 'total_lines': len(lines),
                          'path': path.as_posix(), 'scope': 'own_user_workspace',
                          'partial': offset <= len(lines), 'next_offset': offset,
                          'next_char_offset': char_offset}
                if document_format:
                    result.update(extracted_document=True, format=document_format,
                                  coverage='text_only; images_and_layout_not_covered')
                encode = lambda: json.dumps(result, ensure_ascii=False, separators=(',', ':'))
                if serialized_bytes(encode()) > budget:
                    if document_format: revision.check(cap)
                    return json.dumps({'success': False, 'error': 'capacity: file metadata exceeds inline budget'})
                for n in range(offset-1, min(len(lines), offset-1+limit)):
                    start = char_offset if n == offset-1 else 0
                    text = lines[n][start:]
                    prefix = ('\n' if result['content'] else '') + f'{n+1}: '
                    prior = result['content']
                    low, high = 0, len(text)
                    while low < high:
                        mid = (low + high + 1) // 2
                        result.update(content=prior+prefix+text[:mid], partial=True,
                                      next_offset=n+1, next_char_offset=start+mid)
                        if serialized_bytes(encode()) <= budget:
                            low = mid
                        else:
                            high = mid-1
                    complete = low == len(text)
                    result.update(content=prior+prefix+text[:low],
                                  next_offset=n+2 if complete else n+1,
                                  next_char_offset=0 if complete else start+low,
                                  partial=not (complete and n+1 == len(lines)))
                    if serialized_bytes(encode()) > budget or (not complete and low == 0):
                        result.update(content=prior, partial=True, next_offset=n+1, next_char_offset=start)
                        if not prior:
                            if document_format: revision.check(cap)
                            return json.dumps({'success': False, 'error': 'capacity: no text character fits'})
                        break
                    if low or complete:
                        seen.append((starts[n]+start, starts[n]+start+low-1+(1 if complete else 0)))
                    if not complete:
                        break
                rendered = encode()
                record_read(rendered)
                return rendered
            if char_offset:
                raise ScopeDenied()
            content = '\n'.join(f'{n+1}: {s}' for n,s in enumerate(lines) if offset-1 <= n < offset-1+limit)[:100000]
            rendered = '\n'.join(f'{n+1}: {line}' for n,line in enumerate(lines) if offset-1 <= n < offset-1+limit)
            if len(rendered) <= 100000:
                seen.extend((starts[n],starts[n]+len(lines[n])) for n in range(offset-1,min(len(lines),offset-1+limit)))
            rendered = json.dumps({'success': True, 'content': content, 'total_lines': len(lines),
                                   'path': path.as_posix(), 'scope': 'own_user_workspace'})
            record_read(rendered)
            return rendered
        if name != 'write_file':
            raise ScopeDenied()
        output_format = args.get('format', 'text')
        if output_format not in ('text', 'docx'):
            raise ScopeDenied()
        if output_format == 'docx':
            if path.suffix.lower() != '.docx':
                raise ScopeDenied()
            from hermes_cli.friday_workspace_docx import create
            return create(cap, fd, parts[-1], path.as_posix(), args.get('content'))
        if path.suffix.lower() in {'.docx', '.pdf'}:
            return json.dumps({'success': False, 'error': 'document_write_unsupported',
                               'format': path.suffix.lower().lstrip('.')})
        content = args.get('content')
        if not isinstance(content, str) or len(content.encode()) > 1000000:
            raise ScopeDenied()
        from hermes_cli.friday_workspace_revision import write
        return write(cap,fd,parts[-1],path.as_posix(),content,task_id)
    except (OSError, ValueError):
        raise ScopeDenied() from None
    finally:
        os.close(fd)


ONBOARDING = '.friday-onboarding.json'


def check_onboarding_home(root, home, binding):
    """Managed new homes stay unusable until their whole native setup is intact.

    Existing reviewed homes without this preparation receipt retain their old
    contract. No alternate identity store or ambient credential fallback.
    """
    path = home / ONBOARDING
    if not path.exists() and not path.is_symlink():
        return
    _private(path)
    receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    required = {'schema', 'binding_sha256', 'config_sha256', 'soul_sha256',
                'required_secrets', 'directory_identity', 'template', 'authorization_home'}
    if binding['platform'] == 'cli': required.add('cli_admission_sha256')
    st = _private(home, directory=True)
    if (not isinstance(receipt, dict) or set(receipt) != required
            or receipt['schema'] != 'friday.onboarding.v1'
            or receipt['binding_sha256'] != _fingerprint(binding)
            or receipt['authorization_home'] != str(root)
            or receipt['directory_identity'] != [st.st_dev, st.st_ino]):
        raise ScopeDenied()
    for name, field in [('config.yaml', 'config_sha256'), ('SOUL.md', 'soul_sha256')]:
        _private(home / name)
        if hashlib.sha256((home / name).read_bytes()).hexdigest() != receipt[field]:
            raise ScopeDenied()
    from agent.secret_scope import load_env_file
    names = receipt['required_secrets']
    if not isinstance(names, list) or not names or any(not isinstance(k, str) for k in names):
        raise ScopeDenied()
    _private(home / '.env')
    values = load_env_file(home / '.env')
    if any(not values.get(k) for k in names):
        raise ScopeDenied()
    from hermes_cli.config import load_config_readonly
    if binding['platform'] == 'cli':
        # Local ingress has no messaging route or pairing grant. Reuse the
        # exact frozen OS-UID map and generic product account policy instead.
        from hermes_cli.friday_cli_principal import cli_policy, numeric_os_uid
        from hermes_cli.friday_product_access import access_policy
        key = principal_id(*(binding[k] for k in
                           ('platform', 'transport_profile', 'account_id', 'user_id')))
        rows = [r for r in cli_policy(root)['principals'] if
                principal_id('cli', r['transport_profile'], r['account_id'], r['user_id']) == key]
        with authority(root):
            accounts = access_policy()['accounts']
            gateway = load_config_readonly().get('gateway', {})
        matches = [a for a in accounts if
                   (a['platform'], a['transport_profile'], a['account_id']) ==
                   (binding['platform'], binding['transport_profile'], binding['account_id'])
                   and binding['runtime_profile'] in a['runtime_profiles']]
        if (len(rows) != 1 or rows[0]['uid'] != numeric_os_uid()
                or receipt['cli_admission_sha256'] != _fingerprint(rows[0]) or len(matches) != 1
                or any(r.get('platform') == 'cli' for r in gateway.get('profile_routes', []))):
            raise ScopeDenied()
        return
    with authority(root):
        gateway = load_config_readonly().get('gateway', {})
    route = {'name': 'friday-' + principal_id(*(binding[k] for k in
             ('platform', 'transport_profile', 'account_id', 'user_id'))),
             'platform': binding['platform'], 'bot_profile': binding['transport_profile'],
             'user_id': binding['user_id'], 'profile': binding['runtime_profile'], 'enabled': True}
    routes = gateway.get('profile_routes', [])
    competing = [r for r in routes if isinstance(r, dict)
                 and r.get('platform') == binding['platform']
                 and (r.get('bot_profile') or 'default') == binding['transport_profile']
                 and r.get('user_id') == binding['user_id']]
    if gateway.get('multiplex_profiles') is not True or competing != [route]:
        raise ScopeDenied()


def onboarding_profile_routes(existing):
    """Refresh committed onboarding routes at native per-event resolution only.

    A running primary multiplexer must not admit through cached pre-setup routes.
    Ordinary gateways and previously reviewed profiles keep the native contract.
    """
    from hermes_constants import get_routing_process_hermes_home
    from hermes_cli.friday_product_access import settings
    from hermes_cli.config import load_config_readonly
    from gateway.profile_routing import parse_profile_routes
    root = get_routing_process_hermes_home()
    with authority(root):
        if settings().get('onboarding') is None:
            return existing
        _private(root, directory=True)
        _private(root / 'config.yaml')
        gateway = load_config_readonly().get('gateway', {})
        if gateway.get('multiplex_profiles') is not True:
            raise ScopeDenied()
        return parse_profile_routes(gateway.get('profile_routes', []))


def ordinary_file_source():
    """Current admitted native source; unmanaged profiles retain native behavior."""
    cap = ordinary_file_scope()
    if cap is None:
        return None
    source = _SOURCE.get()
    if source is None or not _same_scope(getattr(source, '_friday_user_scope', None), cap):
        raise ScopeDenied()
    return source


def workspace_document(raw, *, max_bytes=1000000):
    """Snapshot a private own-workspace file without following any path symlink.

    Callers send these immutable bytes, never reopen the model-selected pathname.
    Before/after descriptor and named identity checks reject concurrent mutation.
    """
    cap = current(required=True)
    if not isinstance(raw, str) or not raw or '\x00' in raw:
        raise ScopeDenied()
    root = cap.home / 'workspace'
    path = Path(raw)
    if not path.is_absolute():
        raise ScopeDenied()
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ScopeDenied() from None
    parts = relative.parts
    if not parts or any(c in ('.', '..') or c.startswith('.') for c in parts):
        raise ScopeDenied()
    parent = _workspace_directory(cap)
    item = None
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode, info.st_nlink, info.st_uid)
    try:
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
            st = os.fstat(parent)
            if st.st_uid != _owner_uid() or st.st_mode & 0o077:
                raise ScopeDenied()
        item = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(item)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != _owner_uid() or before.st_mode & 0o077
                or before.st_size > max_bytes):
            raise ScopeDenied()
        pieces, size = [], 0
        while chunk := os.read(item, min(65536, max_bytes-size+1)):
            pieces.append(chunk); size += len(chunk)
            if size > max_bytes:
                raise ScopeDenied()
        after = os.fstat(item)
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if size != before.st_size or identity(before) != identity(after) or identity(after) != identity(named):
            raise ScopeDenied()
        cap.check()
        return b''.join(pieces), str(relative)
    except (OSError, ValueError):
        raise ScopeDenied() from None
    finally:
        if item is not None: os.close(item)
        os.close(parent)


def _workspace_directory(cap):
    """Pin the admitted home inode before opening its workspace by descriptor."""
    home = os.open(cap.home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        before = os.fstat(home)
        if (before.st_dev, before.st_ino) != cap.directory_identity:
            raise ScopeDenied()
        _private(cap.home, directory=True)
        workspace = os.open('workspace', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home)
        info = os.fstat(workspace)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != _owner_uid() or info.st_mode & 0o077:
            os.close(workspace)
            raise ScopeDenied()
        return workspace
    finally:
        os.close(home)


def ordinary_file_scope():
    """Narrow media seam: preserve unmanaged profiles in a mixed gateway.

    An active managed policy without an admitted native source still refuses;
    another profile's earlier admission cannot grant or remove legacy authority.
    """
    cap = _CURRENT.get()
    if cap is not None:
        return cap.check()
    from hermes_constants import get_hermes_home
    if policy(get_hermes_home()) is not None:
        raise ScopeDenied()
    return None


def ordinary_presentation(source=None, *, home=None):
    """Conservative audience selection, never an authorization or a chat role claim.

    Managed child homes retain their audience before admission and in fresh
    history-only processes. Missing/revoked managed capabilities receive the
    same minimal public copy; unscoped operator homes retain diagnostics.
    """
    try:
        if current() is not None:
            return True
        from hermes_constants import get_hermes_home, get_default_hermes_root
        if home is None:
            if isinstance(getattr(source, '_friday_user_scope', None), UserScope):
                return True
            from gateway.session_identity import identity_of
            identity = identity_of(source) if source is not None else None
            home = identity.authorization_home if identity is not None else get_hermes_home()
        home = Path(home)
        # Evidence selects a restricted display only. Do not deserialize a
        # marker/receipt or follow its claimed authorization path into authority.
        marker = home / MARKER
        if marker.exists() or marker.is_symlink():
            return True
        if policy(home) is not None:
            return True
        root = get_default_hermes_root(home=home)
        if root == home:
            return False
        parent_policy = policy(root)
        # A shared root may also contain native operator profiles. Only the
        # actual child declared in validated bindings inherits this audience.
        return parent_policy is not None and any(
            home == root / 'profiles' / binding['runtime_profile']
            for binding in parent_policy['bindings'])
    except Exception:  # A failed audience check must never enable diagnostic disclosure.
        return True


def pending_stop_copy(source=None, *, reset=False):
    if ordinary_presentation(source):
        return ("Остановка ещё не подтверждена. Новый разговор пока не начат. Проверьте /status; не повторяйте действие." if reset else
                "Остановка ещё не подтверждена. Задача может продолжаться. Проверьте /status; не повторяйте действие.")
    return "Reset pending: native web process cessation is unconfirmed." if reset else "Stop pending: native web process cessation is unconfirmed."


def empty_response_copy():
    return 'Ответ не получен. Часть действий могла выполниться; проверьте результат перед повтором. Если ошибка повторяется, сообщите администратору.'
# Exact existing registry.dispatch public wording, kept as the single source.
PUBLIC_TOOL_REFUSAL_COPY = 'Это действие недоступно.'
PUBLIC_WEB_STOPPED_COPY = 'Проверка в интернете остановлена.'
PUBLIC_FILE_EXISTS_COPY = 'Файл уже существует; изменение не выполнено.'
# Dedicated ordinary file-mutation footer copy: no tool identifiers, no execution
# instructions, no host path prefixes. Counts stay truthful.
PUBLIC_FILE_MUTATION_HEADER = 'Не все изменения файлов выполнены: {count}.'
PUBLIC_FILE_MUTATION_FAILED = 'изменение не выполнено'
PUBLIC_FILE_MUTATION_MORE = 'И ещё: {count}.'

# Selected B21 six-symbol support delta on accepted B19R2 scope (K20-H2): the two
# failure constants and four ordinary web/tool boundary helpers the web/executor
# repair calls, with H1-safe semantics for non-string provider failure values.
PUBLIC_TOOL_FAILURE_COPY = 'Не удалось выполнить действие. Возможен частичный результат; проверьте его перед повтором.'
PUBLIC_WEB_FAILURE_COPY = 'Не удалось проверить сведения в интернете.'


def ordinary_tool_error_json(code):
    """Public JSON for an exact known machine refusal at the ordinary tool boundary.

    Machine codes stay in private receipts and unmanaged diagnostics. Access
    refusal is never translated as absence, and an uncertain operation is never
    reported completed. Returns None outside ordinary presentation so callers
    keep their existing raw result.
    """
    if code == 'product_user_scope_refused' and ordinary_presentation():
        return json.dumps({'error': PUBLIC_TOOL_REFUSAL_COPY, 'success': False}, ensure_ascii=False)
    return None


def ordinary_exception_error_text(cause):
    """Public status for an exact known boundary cause; arbitrary exception text stays private.

    Only the exact 'web_call_stopped' fence keeps its specific truthful status;
    every other cause falls back to the generic partial-result wording. Returns
    None outside ordinary presentation so callers keep their existing copy.
    """
    if not ordinary_presentation():
        return None
    if cause == 'web_call_stopped':
        return PUBLIC_WEB_STOPPED_COPY
    return PUBLIC_TOOL_FAILURE_COPY


def ordinary_web_error_text(cause):
    """Public text for a returned web/provider failure cause at the ordinary boundary.

    The exact 'web_call_stopped' fence (bare or provider-prefixed, e.g.
    'Exa search failed: web_call_stopped') keeps its specific truthful stopped
    status; every other provider cause falls back to the generic web failure
    wording. Returns None outside ordinary presentation or for an empty cause.
    """
    if not ordinary_presentation() or not cause:
        return None
    if cause == 'web_call_stopped' or cause.endswith(': web_call_stopped'):
        return PUBLIC_WEB_STOPPED_COPY
    return PUBLIC_WEB_FAILURE_COPY


def ordinary_public_web_failure(payload):
    """Project a returned provider failure envelope at the ordinary public boundary.

    Returns ``(public_payload, raw_cause)``. Only the public ``error`` value is
    replaced; success/state/data and any recovered partial content stay
    byte-identical. ``raw_cause`` is the exact original typed error value for the
    private best-effort diagnostic path (None when nothing was projected). The
    payload passes through unchanged outside ordinary presentation, when it is
    not a failure dict, or when it carries no error value.

    K20-H1: a non-string provider failure value (dict/list/other) NEVER survives
    into the public envelope and is never blindly stringified into public
    output; it is replaced with the generic public web failure copy while the
    typed value is returned for private best-effort diagnostics.
    """
    if not ordinary_presentation() or not isinstance(payload, dict):
        return payload, None
    if payload.get('success') is not False:
        return payload, None
    cause = payload.get('error')
    if cause is None:
        return payload, None
    public = dict(payload)
    if isinstance(cause, str) and cause:
        public['error'] = ordinary_web_error_text(cause)
    else:
        public['error'] = PUBLIC_WEB_FAILURE_COPY
    return public, cause


_PUBLIC_PREVIEW_CODES = {
    'document_already_exists': PUBLIC_FILE_EXISTS_COPY,
    'product_user_scope_refused': PUBLIC_TOOL_REFUSAL_COPY,
    'web_call_stopped': PUBLIC_WEB_STOPPED_COPY,
}


def ordinary_failure_preview(preview, *, failed_copy):
    """Bounded public preview for the managed file-mutation verifier footer.

    Exact known machine codes keep their truthful public status; anything else
    (provider bodies, host paths, credentials) stays in private receipts and the
    entry falls back to the generic failed marker. Filenames stay visible.
    """
    if preview in _PUBLIC_PREVIEW_CODES:
        return _PUBLIC_PREVIEW_CODES[preview]
    return failed_copy




def ordinary_tool_metadata(name, result):
    """Project only native typed metadata; never rewrite user text or tool artifacts.

    Native skill dedup has already consumed its private fingerprint at this boundary.
    Session IDs and message anchors remain internal native follow-up capabilities.
    """
    if name not in {'skill_view', 'session_search', 'memory'} or not ordinary_presentation():
        return result
    value = json.loads(result) if isinstance(result, str) else result
    if not isinstance(value, dict):
        return result
    if name == 'skill_view':
        value = {k:v for k,v in value.items() if k not in {'skill_dir', '_source_path', '_skill_identity'}}
    elif name == 'session_search':
        def metadata(v):
            return {k:x for k,x in v.items() if k not in {'source', 'model'}} if isinstance(v,dict) else v
        value = metadata(value)
        if isinstance(value.get('session_meta'), dict):
            value['session_meta'] = metadata(value['session_meta'])
        if isinstance(value.get('results'), list):
            value['results'] = [metadata(v) for v in value['results']]
    elif value.get('_friday_memory_outcome') == 'unconfirmed':
        import logging
        logging.getLogger(__name__).warning('Managed memory unconfirmed diagnostic: %r', value)
        value = {k:v for k,v in value.items() if k != '_friday_memory_outcome'}
        value['error'] = 'Изменение памяти не подтверждено. Часть действий могла выполниться; проверьте содержимое памяти перед повтором. Если состояние неясно, сообщите администратору.'
        value['effect_unknown'] = True
    elif 'drift_backup' in value:
        import logging
        logging.getLogger(__name__).warning('Managed memory drift diagnostic: %r', value)
        value = {k:v for k,v in value.items() if k not in {'drift_backup', 'remediation'}}
        value['error'] = 'Изменения памяти отклонены: обнаружен конфликт содержимого. Исходные данные сохранены; требуется помощь администратора.'
    return json.dumps(value, ensure_ascii=False) if isinstance(result,str) else value


PRIVATE_REPLY_COPY = 'Я не раскрываю внутренние настройки и служебные пути.'
PRIVATE_REPLY_FAILURE_COPY = 'Не удалось безопасно подготовить ответ. Если ошибка повторяется, сообщите администратору.'


def private_reply_copy(*, effect_unknown=False):
    return PRIVATE_REPLY_COPY + (' Часть действий могла выполниться. Проверьте результат перед повтором.' if effect_unknown else '')


def is_privacy_refusal(agent):
    return getattr(agent, '_friday_reply_withheld_reason', None) in {
        'unsupported_self_deployment_claim', 'restricted_deployment_value'}


def _withheld_reply_copy(agent):
    unknown = bool(getattr(agent, '_friday_reply_effect_unknown', False))
    if is_privacy_refusal(agent):
        return private_reply_copy(effect_unknown=unknown)
    return PRIVATE_REPLY_FAILURE_COPY + (' Часть действий могла выполниться. Проверьте результат перед повтором.' if unknown else '')


def managed_reply_stream(agent):
    """Audience selection is sticky within this turn; it never grants tool authority."""
    value = getattr(agent, '_friday_private_stream', None)
    if value is None:
        value = ordinary_presentation()
        agent._friday_private_stream = value
    return value


def _restricted_reply_values(agent):
    cap = current(required=True)
    cap.check()
    if agent is not None:
        check_agent(agent)
    roots = [cap.home, cap.authorization_home]
    # Native profile aliases are typed deployment locations, not generic software words.
    user_home = Path.home()
    roots.append(user_home / '.hermes' / 'profiles' / cap.profile)
    values = {str(p) for p in roots}
    for path in roots:
        try: values.add('~/' + path.relative_to(user_home).as_posix())
        except ValueError: pass
    values.add('~/.hermes/profiles/' + cap.profile)
    for value in (cap.profile, cap.key):
        if not isinstance(value, str) or len(value) < 4:
            raise ScopeDenied()
        values.add(value)
    if any(not isinstance(v, str) or not v or v in ('/', '~', '.') for v in values):
        raise ScopeDenied()
    return cap, tuple(sorted(values, key=len, reverse=True))


def _retain_private_reply(cap, candidate, reason, *, effect_unknown=True):
    """Bounded latest rejected candidate in existing private state_meta, never public history."""
    import hashlib
    from hermes_state_registry import acquire
    raw = candidate.encode('utf-8', errors='replace')
    record = json.dumps({'schema':'friday.private-reply.v1', 'reason':reason,
        'sha256':hashlib.sha256(raw).hexdigest(), 'utf8_bytes':len(raw),
        'candidate_prefix':raw[:8192].decode('utf-8', errors='ignore'),
        'truncated':len(raw)>8192, 'tool_effects_may_have_occurred':effect_unknown}, ensure_ascii=False)
    db = acquire(cap.home / 'state.db')
    try:
        db.set_meta('friday.private_reply.latest', record)
    finally:
        db.close()
    cap.check()


# Public identity is product source, not a chat assertion or an ambient runtime field.
PUBLIC_IDENTITY = {'name': 'Пятница (Friday)', 'kind': 'ИИ-помощник'}
LEGACY_SELF_CLAIM_VIEW = '[Не подтверждено.]'


def self_deployment_claim_spans(text):
    """Bounded RU/EN assertion grammar, never a software-name blacklist.

    Match a relationship to THIS assistant, or an unqualified deployment-slot
    block. Ordinary third-person research and fenced/inline user code keep
    their exact text. This is not an arbitrary-language semantic classifier.
    Offsets refer to the original text so a request copy can replace only the
    unsupported assertion; canonical history is never edited.
    """
    import re
    if not isinstance(text, str):
        return ()
    # Code is task evidence, not the narrator asserting its deployment. An
    # explicit own-configuration introduction outside a fence is still a claim.
    visible = list(text)
    fenced = False
    for line in re.finditer(r'.*(?:\n|$)', text):
        raw = line.group()
        if not raw:
            continue
        fence = raw.lstrip().startswith(('```', '~~~'))
        if fenced or fence:
            for i in range(line.start(), line.end()):
                if visible[i] != '\n': visible[i] = ' '
        if fence: fenced = not fenced
    prose = ''.join(visible)
    labelled_prose = text  # Fences/inline formatting cannot authenticate deployment slots.
    prose = re.sub(r'`[^`\n]*`', lambda m:' ' * len(m.group()), prose)
    # These are deployment RELATIONS, not forbidden values. A newly configured
    # model/provider or an invented router receives the same treatment.
    subject = r'(?:\bI\b|\bI[’\x27]m\b|\bя\b|\bменя\b)'
    slots = r'(?:backend|engine|core|kernel|runtime|model|provider|deployment|hosting|server|router|ядро|рантайм|движ(?:ок|ке|ка)|модел[ьиь]|провайдер\w*|бэкенд\w*|бекенд\w*|маршрутизатор\w*|сервер\w*|разв[её]ртывани\w*)'
    patterns = [
        r'\b(?:my|our|мой|моя|мо[её]|мои|наш\w*)\s+(?:(?:actual|underlying|internal|реальн\w*|внутренн\w*)\s+){0,2}' + slots + r'\s*(?:is|are|runs?|uses?|—|–|:|это|явля\w*|работа\w*|использу\w*|[A-ZА-Я0-9])',
        r'\b(?:у\s+меня|для\s+меня|this\s+assistant[’\x27]s|this\s+assistant\s+uses)\b[^.!?;\n]{0,48}' + slots,
        subject + r'\s+(?:(?:am|was|have\s+been)\s+)?(?:run(?:ning)?|hosted|powered|built|based|served)\s+(?:on|by|with|under)\b',
        r'\b(?:я\s+)?(?:запущена|разв[её]рнута|основана|построена|базируюсь)\s+(?:на|под|в\s+среде)\b',
        r'\b(?:я\s+)?работаю\s+(?:на|под|в\s+среде)\s+(?:(?:движк\w*|рантайм\w*|платформ\w*|модел\w*|сервер\w*|базе|управлением)\b|(?:Hermes|Linux|Windows|OpenAI|dispatcher|custom)\b)',
        subject + r'[^.!?;\n]{0,40}\b(?:use|using|использую|работаю\s+через)\b[^.!?;\n]{0,40}' + slots,
        r'\b(?:меня\s+(?:обслуживает|запускает)|мной\s+управляет)\b',
        r'\b(?:my|мои|моя|мо[её])\s+(?:technical\s+details|configuration|технически\w*\s+параметр\w*|конфигураци\w*)\s*[:—]',
    ]
    claim = re.compile('|'.join('(?:'+p+')' for p in patterns), re.IGNORECASE)
    # An explicit refusal/uncertainty is not a positive backend assertion.
    nonassertion = re.compile(r'(?:\b(?:do\s+not|don[’\x27]t|cannot|can[’\x27]t)\s+(?:know|disclose|confirm)|\bне\s+(?:знаю|раскрываю|могу\s+(?:раскрыть|подтвердить)|подтверждаю)|\bнеизвест\w*|\bnot\s+(?:known|confirmed|disclosed|public|available)|\bunknown\b)', re.I)
    def uncertain_value(tail, prefix=''):
        # Uncertainty qualifies THIS slot value, never incidental later text.
        # A concrete name stays a positive disclosure even if a different
        # provider/model is unknown or a parenthetical disclaimer follows.
        tail = re.sub(r'^[\s`*\"\':—–-]+', '', tail)
        tail = re.sub(r'^(?:(?:is|are|это|является|сейчас|currently)\b[\s:—–-]*)+', '', tail, flags=re.I)
        value = re.split(r'[,;.!?()\n]', tail, maxsplit=1)[0].strip()
        unresolved = re.sub(slots, '', value, flags=re.I)
        unresolved = re.sub(r'\b(?:and|or|и|или)\b', '', unresolved, flags=re.I).strip()
        return bool(nonassertion.match(value) or (not unresolved and nonassertion.search(prefix)))
    spans = []
    for part in re.finditer(r'[^.!?;\n]+(?:[.!?;]|(?=\n|$))', prose):
        value = part.group()
        for assertion in claim.finditer(value):
            own_slots = list(re.finditer(slots, value[assertion.start():assertion.end()], re.I))
            target_end = (assertion.start() + own_slots[0].end()) if own_slots else assertion.end()
            if not uncertain_value(value[target_end:], value[:target_end]):
                spans.append((part.start(), part.end()))
                break
    # Actual old answers contain a labelled engine/model/provider block with
    # no subject on each line. Two distinct deployment labels establish this
    # typed presentation; an external-project/documentation introduction does not.
    label = re.compile(r'(?<![\w])(?:\*\*)?(' + slots + r')(?:\*\*)?\s*[:—–]\s*\S', re.I)
    for block in re.finditer(r'(?:[^\n]+(?:\n|$))+', labelled_prose):
        value = block.group()
        found = list(label.finditer(value))
        external = re.search(r'\b(?:external\s+(?:project|example)|your\s+(?:project|example)|сторонн\w*\s+проект\w*|ваш\w*\s+проект\w*|пример\s+конфигурации|документаци\w*)\b', value, re.I)
        # An unqualified singleton carrying a known deployed value is the
        # same typed disclosure as the multi-slot block. External examples and
        # unrelated model labels (e.g. linear regression) remain task content.
        known_slot = any(re.match(r'[\s`*\"\']*(?:Hermes|Linux|dispatcher|custom|self[- ]hosted|кастомн\w*)(?:\b|$)', value[x.end()-1:], re.I) for x in found)
        if (len({x.group(1).casefold() for x in found}) >= 2 or known_slot) and not external:
            for m in found:
                end = next((i for i in range(m.end(), len(value)) if value[i] in ';\n'), len(value))
                following = next((x.start() for x in found if x.start() > m.start()), len(value))
                end = min(end, following)
                if not uncertain_value(value[m.end()-1:end], value[:m.start()]):
                    spans.append((block.start()+m.start(), block.start()+end))
    # Merge overlaps without dropping surrounding conversation or file anchors.
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]: merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else: merged.append((a, b))
    return tuple(merged)


def _self_claim_texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value: yield from _self_claim_texts(item)
    elif isinstance(value, dict):
        # Text carriers only. Tool-call arguments, names, grants and IDs are
        # task evidence and are NOT assistant identity assertions.
        for key in ('content', 'text', 'api_content', 'reasoning', 'reasoning_content',
                    'reasoning_details', 'codex_reasoning_items', 'codex_message_items', 'summary', 'thinking', 'analysis'):
            if key in value: yield from _self_claim_texts(value[key])


def project_file_delivery_frames(text, *, history=False):
    """Separate the exact retired host protocol from assistant text.

    A complete standalone frame is reserved even inside Markdown: formatting
    cannot authenticate model-generated transport evidence. Bare JSON, code
    strings and ordinary prose are not frames. Callers exclude user/tool rows.
    Legacy frames have no reliable provenance, even with a plausible digest or
    DELIVERED value: omit it from assistant speech, never reconstruct a receipt
    or edit the original history. Actual user/tool/MEDIA file references remain;
    receipt-only filenames stay recoverable in the private canonical record.
    """
    import re
    start_frame = re.compile(r'(?m)^[ \t]*(?:>[ \t]*)*(?:[-*+][ \t]+)?(?P<wrap>\*\*|__|`{1,3})?'
        r'\[File delivery observation:')
    decoder = json.JSONDecoder(object_pairs_hook=list)
    spans = []
    for match in start_frame.finditer(text):
        if spans and match.start() < spans[-1][1]:
            continue
        # Decode a bounded complete object, not a brace regex: quoted braces
        # and pretty-printed JSON have exactly the same protocol meaning.
        body = text[match.end():match.end() + 65536]
        try:
            pairs, consumed = decoder.raw_decode(body, len(body) - len(body.lstrip()))
            if (not isinstance(pairs, list) or len(pairs) != 3
                    or {key for key, _ in pairs} != {'path', 'sha256', 'state'}):
                continue
            record = dict(pairs)
            if (not all(isinstance(value, str) for value in record.values())
                    or not record['path']
                    or not re.fullmatch(r'[0-9a-f]{64}', record['sha256'])
                    or record['state'] not in {'UNKNOWN', 'DELIVERED'}):
                continue
        except (ValueError, TypeError):
            continue
        end_frame = re.compile(r'[ \t\r\n]*\]' + re.escape(match.group('wrap') or '')
                               + r'[ \t]*(?P<ending>\r?\n|$)')
        end = end_frame.match(text, match.end() + consumed)
        if end is None:
            continue
        spans.append((match.start(), end.end(), ''))
    for start, end, replacement in reversed(spans):
        text = text[:start] + replacement + text[end:]
    return text


def _public_file_delivery_text(value):
    """Project fresh visible text carriers, never tool arguments or reasoning."""
    if isinstance(value, str):
        public = project_file_delivery_frames(value)
        return ('В этой реплике нет подтверждённого результата доставки.'
                if public != value and not public.strip() else public)
    if isinstance(value, list):
        return [_public_file_delivery_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _public_file_delivery_text(item) if key in {'text', 'content'} else item
                for key, item in value.items()}
    return value


def is_file_delivery_observation(row):
    """Presentation classification only; neither metadata nor prose grants an effect."""
    return (isinstance(row, dict) and row.get('role') == 'assistant'
            and row.get('display_kind') == 'hidden' and not row.get('tool_calls')
            and not row.get('tool_call_id') and isinstance(row.get('display_metadata'), dict)
            and isinstance(row['display_metadata'].get('friday_file_delivery_observation'), dict))


def is_file_delivery_context_row(row):
    """A receipt-only record is not speech, including the retired text protocol.

    Classification suppresses presentation only. It never authenticates a status
    or authorizes transport, and ordinary surrounding prose/calls remain intact.
    """
    import re
    if not isinstance(row, dict) or row.get('role') != 'assistant':
        return False
    if is_file_delivery_observation(row) or row.get('_friday_file_context_only'):
        return True
    # Provider-required whitespace pads are not reasoning payload. Counting a
    # pad as speech prevents receipt removal and makes every send heal it again.
    reasoning = (row.get(key) for key in
        ('reasoning', 'reasoning_content', 'reasoning_details', 'codex_reasoning_items', 'codex_message_items'))
    if row.get('tool_calls') or any(value.strip() if isinstance(value, str) else value for value in reasoning):
        return False
    text = row.get('api_content') or row.get('content')
    if not isinstance(text, str):
        return False
    projected = project_file_delivery_frames(text)
    if projected == text:
        return False
    # An empty Markdown fence was only a decoration of the reserved protocol.
    projected = re.sub(r'(?m)^[ \t]*(?:```|~~~)[a-zA-Z0-9_+-]*[ \t]*$', '', projected)
    return not projected.strip()


def project_legacy_self_claims(rows):
    """Pure, reversible request view AFTER api_content selection.

    The caller must validate managed admission. Original rows, user/tool/system
    IDs/order and calls/results remain untouched. Assistant assertions are
    projected; operational records become empty private placeholders. Existing
    user/tool/MEDIA file anchors remain exact. Receipt-only filenames remain in
    private canonical evidence; they never rewrite protected user/tool rows.
    A still-present sidecar is refused rather than projecting one representation
    while sending a different one. The original transcript is the recovery view.
    """
    import copy
    import re
    result = copy.deepcopy(rows)
    for row in result:
        if not isinstance(row, dict): raise ScopeDenied()
        if 'api_content' in row: raise ScopeDenied()
        if row.get('role') != 'assistant': continue
        if is_file_delivery_context_row(row):
            row['_friday_file_context_only'] = True
            row['content'] = ''
            for key in ('reasoning', 'reasoning_content', 'reasoning_details',
                        'codex_reasoning_items', 'codex_message_items'):
                row.pop(key, None)
            continue
        def project(value):
            if isinstance(value, str):
                value = project_file_delivery_frames(value, history=True)
                spans = self_deployment_claim_spans(value)
                for start, end in reversed(spans):
                    # Keep exact usable file/result references even when a bad
                    # old self-description shared their sentence.
                    anchors = re.findall(r'MEDIA:(?:"[^"\n]+"|\S+)|\[[^\]\n]+\]\([^\)\n]+\)', value[start:end])
                    replacement = LEGACY_SELF_CLAIM_VIEW + ((' ' + ' '.join(anchors)) if anchors else '')
                    value = value[:start] + replacement + value[end:]
                return value
            if isinstance(value, list): return [project(v) for v in value]
            if isinstance(value, dict):
                if value.get('signature') and any(self_deployment_claim_spans(t)
                        or project_file_delivery_frames(t, history=True) != t for t in _self_claim_texts(value)):
                    raise ScopeDenied()  # Cannot forge a new provider signature for edited thinking.
                return {k:project(v) if k in ('text','content','reasoning','reasoning_content','summary','thinking','analysis') else v for k,v in value.items()}
            return value
        for key in ('content','reasoning_content','reasoning_details','codex_reasoning_items','codex_message_items'):
            if key in row: row[key] = project(row[key])
    return result


def public_identity_request_view(agent, rows):
    """Admission-bound shared main/replay/summary request presentation."""
    if not managed_reply_stream(agent): return rows
    _restricted_reply_values(agent)  # Existing retained principal/generation check.
    return project_legacy_self_claims(rows)


def guard_generated_reply(agent, value):
    """Typed values plus bounded unsupported self-deployment assertions.

    Public research/code names remain valid; arbitrary semantic/encoded secrecy is not claimed.
    """
    if not managed_reply_stream(agent):
        return value, False
    if getattr(agent, '_friday_reply_withheld', False):
        return _withheld_reply_copy(agent), True
    try:
        cap, restricted = _restricted_reply_values(agent)
        candidate = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            value = _public_reply_media(cap, value)
            candidate = value
        typed_denied = any(item in candidate for item in restricted)
        self_claim_denied = any(self_deployment_claim_spans(text) for text in _self_claim_texts(value))
        denied = typed_denied or self_claim_denied
    except Exception:
        cap, candidate, denied = None, '', True
        typed_denied = self_claim_denied = False
    if not denied:
        return _public_file_delivery_text(value), False
    agent._friday_reply_withheld = True
    agent._friday_reply_withheld_reason = ('unsupported_self_deployment_claim' if self_claim_denied
        else 'restricted_deployment_value' if typed_denied else 'privacy_boundary_unavailable')
    if cap is not None:
        try: _retain_private_reply(cap, candidate, 'unsupported_self_deployment_claim' if self_claim_denied else 'restricted_deployment_value',
                                   effect_unknown=bool(getattr(agent, '_friday_reply_effect_unknown', False)))
        except Exception:
            import logging
            logging.getLogger('run_agent').warning('private reply withheld; private candidate storage unavailable')
    return _withheld_reply_copy(agent), True


def generated_public_payload(row):
    """Fresh public carriers only; provider scratchpad remains private replay data.

    Codex message items also carry visible commentary/final output. Use the same
    phase projection as native history; never mistake analysis or sealed reasoning
    for public prose. Malformed visible text still receives the existing guard.
    """
    from agent.history_commentary import _phase_message_items
    return {"content": [row.get("content"), *_phase_message_items(row,
                frozenset({"commentary", "final", "final_answer", None}))],
            "api_content": row.get("api_content")}


def generated_public_tool_payload(calls):
    """Scan decoded JSON argument values as well as the exact public call envelope.

    Escaping is transport representation, never permission to publish a private
    location. Invalid arguments retain the existing native parser/dispatch checks.
    """
    arguments = []
    for call in calls:
        try:
            arguments.append(json.loads(call["function"]["arguments"]))
        except (KeyError, TypeError, ValueError):
            continue
    return {"calls": calls, "arguments": arguments}


def ordinary_message_view(message, *, home=None):
    """Public display copy; durable provider fields remain available for model replay.

    Audience selection grants no authority. Conservative managed/failed admission
    also suppresses sidecars on administration and history presentation surfaces.
    """
    ordinary = ordinary_presentation() if home is None else ordinary_presentation(home=home)
    if not ordinary:
        return message
    private = {"api_content", "reasoning", "reasoning_content", "reasoning_details",
               "codex_reasoning_items", "codex_message_items", "display_reasoning"}
    public = {key: value for key, value in message.items() if key not in private}
    if is_file_delivery_context_row(message):
        public['content'] = ''
        public['display_kind'] = 'hidden'
    elif message.get('role') == 'assistant' and 'content' in public:
        public['content'] = _public_file_delivery_text(public['content'])
    if isinstance(public.get('display_metadata'), dict):
        public['display_metadata'] = {key: value for key, value in public['display_metadata'].items()
                                      if key != 'friday_file_delivery_observation'}
    return public


def guard_generated_rows(agent, rows, messages):
    """Only freshly collected assistant rows; restored/history rows are excluded by caller."""
    if not managed_reply_stream(agent):
        return
    from agent.tool_result_classification import tool_effects_unknown, tool_call_identity
    observed = getattr(agent, '_friday_reply_effect_messages', None)
    if observed is None:
        observed = agent._friday_reply_effect_messages = []
    denied_calls = getattr(agent, '_friday_no_dispatch_tool_calls', ())
    for row, message in zip(rows, messages):
        if not any(prior is message for prior in observed):
            observed.append(message)
        # A fresh assistant declaration has not dispatched yet. Tool progress may
        # leave other slots pending; finalization checks every missing result.
        pending = [tool_call_identity(call) for call in (row.get('tool_calls') or ())]
        unknown = tool_effects_unknown(observed,
            no_dispatch_tool_calls=(*denied_calls, *pending),
            pending_calls=row.get('role') == 'assistant')
        agent._friday_reply_effect_unknown = bool(
            getattr(agent, '_friday_reply_effect_unknown', False) or unknown)
        if row.get('role') != 'assistant':
            continue
        if row.get('tool_calls'):
            public_calls = _public_file_call_paths(row['tool_calls'])
            row['tool_calls'] = message['tool_calls'] = public_calls
            _, private_call = guard_generated_reply(agent, generated_public_tool_payload(public_calls))
            if private_call:
                # Native proof for this exact batch, including the finalizer/gateway
                # fallback. Keep the original calls and never trust model claims.
                agent._friday_no_dispatch_tool_calls = list(denied_calls) + pending
                raise ScopeDenied()  # Halt before the public write and before tool dispatch.
        for key in ('content', 'api_content'):
            if isinstance(row.get(key), str):
                public, _ = guard_generated_reply(agent, row[key])
                row[key] = message[key] = public
        payload = generated_public_payload(row)
        _, blocked = guard_generated_reply(agent, payload)
        if blocked:
            row['content'] = message['content'] = _withheld_reply_copy(agent)
            row['api_content'] = message['api_content'] = None
            for key in ('reasoning','reasoning_content','reasoning_details','codex_reasoning_items','codex_message_items'):
                if key in row: row[key] = None
                if key in message: message[key] = None
        else:
            for key in ('content', 'api_content'):
                if key in row:
                    row[key] = message[key] = _public_file_delivery_text(row[key])
            if isinstance(row.get('codex_message_items'), list):
                row['codex_message_items'] = message['codex_message_items'] = [
                    _public_file_delivery_text(item) if isinstance(item, dict)
                    and item.get('type') == 'message' and item.get('role') == 'assistant'
                    and item.get('phase') in {'commentary', 'final', 'final_answer', None} else item
                    for item in row['codex_message_items']]


def ordinary_steer_note(agent, donor):
    if not managed_reply_stream(agent):
        return donor
    # Exact owned prefix only. The marker and all trust/replay rules retain their bytes.
    prefix = ('## Mid-turn user steering\nMid-turn, the user can steer you: Hermes delivers their message as a standalone user message right after '
              'the latest tool results, wrapped exactly as:\n')
    if not donor.startswith(prefix):
        raise ScopeDenied()
    return ('## Mid-turn user steering\nA direct user message can arrive after the latest tool results, wrapped exactly as:\n'
            + donor[len(prefix):])


def ordinary_session_schema(schema):
    if not ordinary_presentation():
        return schema
    import copy
    from tools.session_search_tool import SESSION_SEARCH_SCHEMA
    if not isinstance(schema, dict):
        raise ScopeDenied()
    value = copy.deepcopy(schema)
    if value.get('description') == SESSION_SEARCH_SCHEMA['description']:
        prefix = 'Recall past conversations: search or read old Hermes sessions (FTS5), or '
        value['description'] = 'Recall your past conversations: search, read, or ' + value['description'][len(prefix):]
    profile = value.get('parameters', {}).get('properties', {}).get('profile', {})
    if profile.get('description') == SESSION_SEARCH_SCHEMA['parameters']['properties']['profile']['description']:
        profile['description'] = ('Optional internal follow-up routing anchor. Use only a profile anchor returned by an authorized session result; it grants no additional access.')
    return value



def _public_reply_media(cap, text):
    """Only actual MEDIA protocol fields may project to validated relative file anchors."""
    from gateway.platforms.base import MEDIA_TAG_CLEANUP_RE, _mask_media_scan_text, _normalize_media_tag_path, _extensionless_media_matches
    spans = []
    for match in MEDIA_TAG_CLEANUP_RE.finditer(_mask_media_scan_text(text)):
        path = _normalize_media_tag_path(match.group('path'))
        if not path or not Path(path).is_absolute():
            continue
        try:
            relative = Path(path).relative_to(cap.home / 'workspace')
            workspace_document(str(cap.home / 'workspace' / relative))
        except (ScopeDenied, ValueError, OSError):
            continue
        spans.append((match.start(), match.end(), 'MEDIA:"./' + relative.as_posix() + '"'))
    for match, path, end in _extensionless_media_matches(_mask_media_scan_text(text)):
        start = match.start()
        try:
            relative = Path(path).relative_to(cap.home / 'workspace')
            workspace_document(str(cap.home / 'workspace' / relative))
        except (ScopeDenied, ValueError, OSError):
            continue
        if not any(start < prior_end and end > prior_start for prior_start, prior_end, _ in spans):
            spans.append((start, end, 'MEDIA:"./' + relative.as_posix() + '"'))
    for start, end, public in sorted(spans, reverse=True):
        text = text[:start] + public + text[end:]
    return text


def guard_gateway_reply(source, text):
    if not ordinary_presentation(source):
        return text, False
    class ReplyBoundary: pass
    state = ReplyBoundary()
    try:
        state._friday_user_scope = current(required=True)
        state._friday_delegation = None
    except Exception:
        return PRIVATE_REPLY_FAILURE_COPY, True
    return guard_generated_reply(state, text)



def _public_file_call_paths(calls):
    """Equivalent own-workspace path arguments retain tool names, IDs and execution authority."""
    import copy
    cap = current(required=True)
    value = copy.deepcopy(calls)
    for call in value:
        if not isinstance(call, dict):
            continue
        function = call.get('function', {})
        if function.get('name') not in ('read_file', 'write_file', 'patch', 'search_files'):
            continue
        try:
            args = json.loads(function.get('arguments', '{}'))
            raw = args.get('path')
            if not isinstance(raw, str) or not Path(raw).is_absolute():
                continue
            guard_tool(function['name'], args)
            relative = Path(raw).relative_to(cap.home / 'workspace')
            if not relative.parts or any(part in ('.','..') or part.startswith('.') for part in relative.parts):
                continue
            args['path'] = relative.as_posix()
            function['arguments'] = json.dumps(args, ensure_ascii=False)
        except (ValueError, TypeError, ScopeDenied):
            continue
    return value
