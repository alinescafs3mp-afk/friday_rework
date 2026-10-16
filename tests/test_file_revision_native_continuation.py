"""Native persisted follow-up and file custody, with offline transport receipts.

No model or Telegram endpoint is called. The test supplies the model's selected
tool arguments, while native admission, SessionDB, tool middleware, read-delivery
accounting, descriptor revision and delivery journals execute unchanged.

Run with the composed native source and isolate process startup home, runtime,
cache and temporary directories before imports. The native test runner can use
an isolated interpreter through HERMES_PYTHON; no private pytest hook is needed.
"""
import asyncio
import contextvars
import hashlib
import json
import socket
import weakref
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from hermes_cli import friday_user_scope as scope
from hermes_cli.friday_product_access import KEY, principal_id
from hermes_cli.plugins_state import PluginState
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_state import SessionDB
from gateway.config import GatewayConfig, Platform
from gateway.session import SessionSource, SessionStore, AsyncSessionStore
from gateway.session_identity import RoutingIdentity
from gateway.platforms.base import SendResult, BasePlatformAdapter, validate_media_delivery_path
from gateway import run_plugin_delivery as delivery
from test_read_delivery import actor as tool_actor, dispatch, commit, transport, TASK
from test_tool_result_context import Actor
from agent import tool_executor as te
from tools.budget_config import DEFAULT_BUDGET

TEXT = '1. Keep the first point.\n2. Original second point.\n3. Keep the third point.\n'
REVISED = TEXT.replace('Original second point.', 'Revised second point.')
SESSION = 'native-file-continuation'


@pytest.fixture
def account(tmp_path, monkeypatch):
    # Same provision/onboarding/admission sequence as file_native_fixture, using
    # numeric Telegram identities so the real delivery route validator runs too.
    root = tmp_path / 'launch'; root.mkdir(mode=0o700)
    monkeypatch.setattr(Path, 'home', lambda: root)
    monkeypatch.setenv('HERMES_HOME', str(root))
    import hermes_constants as constants
    monkeypatch.setattr(constants, '_PINNED_PROCESS_HERMES_HOME', str(root))
    monkeypatch.setattr(scope, '_CURRENT', contextvars.ContextVar('revision-current', default=None))
    monkeypatch.setattr(scope, '_SOURCE', contextvars.ContextVar('revision-source', default=None))
    monkeypatch.setattr(scope, '_ENGAGED', False)
    def offline(*args, **kwargs):
        raise AssertionError('native file fixture attempted network')
    monkeypatch.setattr(socket.socket, 'connect', offline)
    monkeypatch.setattr(socket.socket, 'connect_ex', offline)
    monkeypatch.setattr(socket, 'create_connection', offline)
    def save(path, value):
        path.write_text(json.dumps(value)); path.chmod(0o600)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    bindings = [dict(platform='telegram', transport_profile='default', account_id='101',
                     user_id=str(i), runtime_profile='revision-user-'+str(i),
                     tools=['read_file', 'write_file']) for i in (1, 2)]
    settings = {'product_access': {'enabled': True, 'accounts': [dict(
        platform='telegram', transport_profile='default', account_id='101',
        runtime_profiles=[b['runtime_profile'] for b in bindings])]},
        'user_isolation': {'enabled': True, 'bindings': bindings}}
    routes = [{'name': 'friday-'+principal_id(*(b[k] for k in
               ('platform', 'transport_profile', 'account_id', 'user_id'))),
               'platform': 'telegram', 'bot_profile': 'default', 'user_id': b['user_id'],
               'profile': b['runtime_profile'], 'enabled': True} for b in bindings]
    save(root/'config.yaml', {'plugins': {'enabled': ['friday_rework'], 'entries': {
        'friday_rework': {'settings': settings}}}, 'gateway': {
        'multiplex_profiles': True, 'profile_routes': routes}})
    users = {principal_id(*(b[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id'))):
             {k: b[k] for k in ('platform', 'transport_profile', 'account_id', 'user_id')} |
             {'enabled': True, 'role': 'user'} for b in bindings}
    with scope.authority(root):
        PluginState('friday_rework').set(KEY, {'schema': KEY, 'users': users})
    homes, sources, adapters = {}, {}, []
    for b in bindings:
        home = scope.provision_new_home(root, b, {'max_iterations': 8})
        homes[b['user_id']] = home
        (home/'SOUL.md').write_text('Synthetic identity. Preserve user file authority.\n')
        (home/'SOUL.md').chmod(0o600)
        (home/'.env').write_text('SYNTHETIC_FIXTURE_KEY=offline-fixture\n')
        (home/'.env').chmod(0o600)
        st = home.stat()
        save(home/scope.ONBOARDING, dict(schema='friday.onboarding.v1',
             binding_sha256=scope._fingerprint(b), config_sha256=digest(home/'config.yaml'),
             soul_sha256=digest(home/'SOUL.md'), required_secrets=['SYNTHETIC_FIXTURE_KEY'],
             directory_identity=[st.st_dev, st.st_ino], template='synthetic', authorization_home=str(root)))
        marker = json.loads((home/scope.MARKER).read_text())
        marker['onboarding_sha256'] = digest(home/scope.ONBOARDING)
        save(home/scope.MARKER, marker)
        # RoutingIdentity retains the same weak reference as a live adapter.
        class Adapter:
            pass
        adapter = Adapter(); adapters.append(adapter)
        source = SessionSource(Platform.TELEGRAM, '202', user_id=b['user_id'],
                               chat_type='dm', profile=b['runtime_profile'], message_id='303')
        source._identity = RoutingIdentity('default', b['runtime_profile'], root, home,
                                           multiplexed=True, transport=weakref.ref(adapter))
        with scope.authority(root):
            scope.admit_source(source)
        sources[b['user_id']] = source
    token = set_hermes_home_override(str(root))
    try:
        yield NS(root=root, homes=homes, sources=sources, adapters=adapters)
    finally:
        reset_hermes_home_override(token)


@contextmanager
def entered(account, user='1'):
    with scope.authority(account.homes[user]), scope.scoped_source(account.sources[user]) as cap:
        yield cap


def open_db(account):
    db = SessionDB(account.homes['1']/'state.db')
    db.create_session(SESSION, 'telegram', user_id='1', profile_name='revision-user-1',
        origin_json=json.dumps({'friday_account_origin': {'schema': 'friday.account_origin.v1',
            'platform': 'telegram', 'transport_profile': 'default', 'account_id': '101'}}))
    return db


def actor(db):
    a = Actor(); a.__dict__.update(tool_actor().__dict__)
    del a._flush_messages_to_session_db
    a.session_id = SESSION; a._session_db = db; a._persist_disabled = False
    a._session_db_created = True; a._last_flushed_db_idx = 0
    return a


def run_tool(a, messages, name, args, ident):
    messages.append({'role': 'assistant', 'content': None, 'tool_calls': [{
        'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]})
    assert a._flush_messages_to_session_db(messages)
    ref, outcome = dispatch(a, name, args, ident)
    commit(a, messages, ref, outcome)
    te._finalize_tool_batch(a, messages, TASK, 1, DEFAULT_BUDGET)
    return json.loads(outcome.result)


def delivery_fixture(account, store, sent=None):
    source = account.sources['1']; adapter = account.adapters[0]
    if sent is None:
        sent = []
    adapter._bot = NS(id=101); adapter.is_connected = True
    runner = NS(config=NS(multiplex_profiles=True), _primary_profile_name='default',
        async_session_store=AsyncSessionStore(store),
        _served_profile_for_home=lambda path: 'revision-user-1' if path == account.homes['1'] else None,
        _resolve_profile_home_for_source=lambda source: account.homes['1'],
        _delivery_adapter_for=lambda source: adapter,
        _owning_profile=lambda item, platform: (item is adapter, 'default'),
        _is_user_authorized_for_source=lambda source, **kwargs: source.user_id == '1')
    adapter.gateway_runner = runner
    async def send(chat, data, *, file_name, reply_to, metadata, caption=None):
        sent.append((chat, data, file_name, reply_to, metadata))
        proof = dict(kind='document', sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
            file_name=file_name, bot_id='101', chat_id=chat, thread_id=None,
            reply_to=reply_to, message_id=str(400+len(sent)))
        return SendResult(success=True, message_id=proof['message_id'], raw_response=proof)
    adapter.send_document_bytes = send
    source._friday_document_session_id = SESSION
    pin(source)
    return adapter, source, sent


def pin(source, message='303'):
    source.message_id = message
    source._friday_document_route = delivery.freeze_route(dict(transport_profile='default',
        runtime_profile='revision-user-1', bot_id='101', source=dict(platform='telegram',
        **{key: getattr(source, key) for key in
           ('chat_id', 'chat_type', 'user_id', 'thread_id', 'message_id')})))


def send_public(adapter, source, artifact):
    public, blocked = scope.guard_gateway_reply(source, 'Ready.\nMEDIA:'+str(artifact))
    assert not blocked and 'MEDIA:"./notes.txt"' in public
    assert str(artifact.parent) not in public
    media, cleaned = BasePlatformAdapter.extract_media(public)
    assert media == [(str(artifact), False)] and cleaned == 'Ready.'
    paths = [validate_media_delivery_path(path) for path, _ in media]
    assert paths == [str(artifact)]
    results = []
    assert asyncio.run(delivery.deliver_ordinary_files(adapter, source, paths,
        record_delivery=results.append))
    assert len(results) == 1
    return results[0]


def test_persisted_same_session_result_selects_read_revision_and_exact_delivery(account, monkeypatch):
    with entered(account):
        db = open_db(account)
        store = SessionStore(account.homes['1']/'sessions', GatewayConfig())
        try:
            a = actor(db); messages = [{'role': 'user', 'content': 'Create a three-point note.'}]
            created = run_tool(a, messages, 'write_file', {'path': 'notes.txt', 'content': TEXT}, 'create')
            assert created['success'] and created['create_only']
            messages.append({'role': 'assistant', 'content': 'Created notes.txt.'})
            assert a._flush_messages_to_session_db(messages)
            first_result = next(row for row in db.get_messages(SESSION) if row.get('tool_call_id') == 'create')
            adapter, source, sent = delivery_fixture(account, store)
            assert send_public(adapter, source, account.homes['1']/'workspace'/'notes.txt').success
        finally:
            store.close_all_db_handles(); db.close()
    # Re-enter and reopen the canonical native database; no file is copied or
    # re-created here. The selected relative path comes only from native replay.
    with entered(account):
        db = SessionDB(account.homes['1']/'state.db')
        store = SessionStore(account.homes['1']/'sessions', GatewayConfig())
        try:
            replay = store.load_transcript(SESSION)
            observation = next(line for row in reversed(replay) if row.get('role') == 'assistant'
                for line in reversed((row.get('content') or '').splitlines())
                if line.startswith('Контекст файла '))
            receipt = db.get_messages(SESSION)[-1]['display_metadata']['friday_file_delivery_observation']
            assert receipt['state'] == 'DELIVERED' and receipt['sha256'] == hashlib.sha256(TEXT.encode()).hexdigest()
            path = json.JSONDecoder().raw_decode(observation.removeprefix('Контекст файла '))[0]
            assert path == receipt['path']
            assert path == 'notes.txt'
            artifact = account.homes['1']/'workspace'/path
            adapter, source, sent = delivery_fixture(account, store, sent)
            messages = replay + [{'role': 'user', 'content': 'Revise point two in the previous file; preserve one and three.'}]
            a = actor(db)
            a._last_flushed_db_idx = len(replay)
            read = run_tool(a, messages, 'read_file', {'path': path}, 'read-prior')
            assert read['content'] == '\n'.join(f'{i}: {line}' for i, line in enumerate(TEXT.splitlines(), 1))
            with monkeypatch.context() as mp:
                transport(a, messages, mp)
            content = '\n'.join(line.partition(': ')[2] for line in read['content'].splitlines())+'\n'
            revised = run_tool(a, messages, 'write_file', {'path': path,
                'content': content.replace('Original second point.', 'Revised second point.')}, 'revise-prior')
            assert revised['success'] and not revised['create_only'] and revised['verified']
            assert artifact.read_bytes() == REVISED.encode()
            archive = artifact.parent/('.friday-before-'+revised['revision_ref'])/'before'
            assert archive.read_bytes() == TEXT.encode()
            pin(source, '304')
            result = send_public(adapter, source, artifact)
            assert result.success and sent[-1][1] == REVISED.encode() and sent[-1][3] == '304'
            assert [row[1] for row in sent] == [TEXT.encode(), REVISED.encode()]
            assert next(row for row in db.get_messages(SESSION) if row.get('tool_call_id') == 'create') == first_result
            replay_after = store.load_transcript(SESSION)
            assert 'Предыдущая отправка подтверждена.' in replay_after[-1]['content']
            receipt_after = db.get_messages(SESSION)[-1]['display_metadata']['friday_file_delivery_observation']
            assert receipt_after['state'] == 'DELIVERED'
            assert receipt_after['sha256'] == hashlib.sha256(REVISED.encode()).hexdigest()
            assert receipt_after['sha256'] not in replay_after[-1]['content']
        finally:
            store.close_all_db_handles(); db.close()


@pytest.mark.parametrize('bad', ['missing', 'foreign', 'traversal', 'symlink', 'hardlink'])
def test_prior_result_path_cannot_escape_or_invent_file(account, bad):
    with entered(account):
        db = open_db(account)
        store = SessionStore(account.homes['1']/'sessions', GatewayConfig())
        try:
            a = actor(db); messages = []
            run_tool(a, messages, 'write_file', {'path': 'notes.txt', 'content': TEXT}, 'create')
            target = account.homes['1']/'workspace'/'notes.txt'
            path = {'missing': 'absent.txt', 'foreign': str(account.homes['2']/'workspace'/'notes.txt'),
                'traversal': '../notes.txt', 'symlink': 'link.txt', 'hardlink': 'hard.txt'}[bad]
            if bad == 'symlink':
                (target.parent/path).symlink_to(target)
            if bad == 'hardlink':
                (target.parent/path).hardlink_to(target)
            if bad == 'foreign':
                row = {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': 'bad-selection', 'type': 'function', 'function': {
                    'name': 'read_file', 'arguments': json.dumps({'path': path})}}]}
                assert not a._flush_messages_to_session_db(messages+[row])
                assert not any(path in row.get('content', '') for row in db.get_messages(SESSION)
                               if isinstance(row.get('content'), str))
                _, outcome = dispatch(a, 'read_file', {'path': path}, 'bad-selection')
                result = json.loads(outcome.result)
            else:
                result = run_tool(a, messages, 'read_file', {'path': path}, 'bad-selection')
            assert result['success'] is False
            adapter, source, sent = delivery_fixture(account, store)
            delivery_path = path if Path(path).is_absolute() else str(target.parent/path)
            assert not asyncio.run(delivery.deliver_ordinary_document(adapter, source, delivery_path)).success
            assert not sent and target.read_bytes() == TEXT.encode()
        finally:
            store.close_all_db_handles(); db.close()


def test_unknown_delivery_survives_database_replay_and_revised_bytes(account, monkeypatch):
    with entered(account):
        db = open_db(account)
        store = SessionStore(account.homes['1']/'sessions', GatewayConfig())
        try:
            run_tool(actor(db), [], 'write_file', {'path': 'notes.txt', 'content': TEXT}, 'create')
            adapter, source, sent = delivery_fixture(account, store)
            async def lost_ack(chat, data, **kwargs):
                sent.append((chat, data)); raise OSError('offline accepted effect, lost ACK')
            adapter.send_document_bytes = lost_ack
            artifact = account.homes['1']/'workspace'/'notes.txt'
            first = asyncio.run(delivery.deliver_ordinary_document(adapter, source, str(artifact)))
            assert not first.success and first.error == 'document_delivery_UNKNOWN'
            replay = store.load_transcript(SESSION)
            assert 'Доставка не подтверждена' in replay[-1]['content'] and 'notes.txt' in replay[-1]['content']
            assert db.get_messages(SESSION)[-1]['display_metadata']['friday_file_delivery_observation']['state'] == 'UNKNOWN'
            a = actor(db); a._last_flushed_db_idx = len(replay)
            messages = replay + [{'role': 'user', 'content': 'Revise the prior file.'}]
            run_tool(a, messages, 'read_file', {'path': 'notes.txt'}, 'read-after-unknown')
            with monkeypatch.context() as mp:
                transport(a, messages, mp)
            changed = run_tool(a, messages, 'write_file', {'path': 'notes.txt', 'content': REVISED}, 'revise-after-unknown')
            assert changed['success']
            pin(source, '304')
            later = asyncio.run(delivery.deliver_ordinary_document(adapter, source, str(artifact)))
            assert not later.success and len(sent) == 1
            assert artifact.read_bytes() == REVISED.encode()
        finally:
            store.close_all_db_handles(); db.close()
