"""Offline native ingress + descriptor intake + ordinary own-workspace read.

Only fresh tmp_path bytes are touched. Admission/config/database are not run:
the retained capability is the already-admitted input to this source seam.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
import weakref
from datetime import datetime, timezone

import pytest

import hermes_cli
NATIVE = Path(hermes_cli.__file__).resolve().parents[1]
FIXTURE = NATIVE


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


from hermes_cli import friday_user_scope as users
from gateway.session_identity import RoutingIdentity
import hermes_constants

intake = load('candidate_attachment_intake', NATIVE / 'gateway/run_inbound_media.py')
ingress = load('native_telegram_ingress_for_intake', FIXTURE / 'plugins/platforms/telegram/telegram_ingress.py')


class Adapter:
    def __init__(self, bot):
        self._bot = bot

    def message_provenance(self, event):
        return ingress.message_provenance(self, event)

    def _effective_message_thread_id(self, message):
        return getattr(message, 'topic', None) or str(message.message_thread_id or '')


@pytest.fixture
def case(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError('attachment source test attempted network')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket.socket, 'connect_ex', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    launch = tmp_path / 'launch'
    cache = launch / 'cache' / 'documents'
    cache.mkdir(parents=True, mode=0o700)
    cache.parent.chmod(0o700)
    home = tmp_path / 'own'
    home.mkdir(mode=0o700)
    (home / 'workspace').mkdir(mode=0o700)
    binding = {'tools': ['read_file', 'write_file']}
    st = home.stat()
    cap = users.UserScope(launch, home, 'own', ('telegram', 'transport', '123', '11'),
                          binding, (st.st_dev, st.st_ino), 1)
    monkeypatch.setattr(cap, 'check', lambda: cap)
    monkeypatch.setattr(users, 'check_database', lambda cap: None)
    # Isolate unrelated credential admission; run the real scoped_file and
    # guard_tool paths against the actual current UserScope and binding.
    credentials = ModuleType('hermes_cli.friday_credential_admission')
    credentials.CredentialDenied = type('CredentialDenied', (ValueError,), {})
    for name in ('ordinary_readonly_file', 'session_artifact_file', 'ordinary_readonly_tool', 'session_artifact_tool'):
        setattr(credentials, name, lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, credentials.__name__, credentials)
    monkeypatch.setattr(hermes_constants, 'get_routing_process_hermes_home', lambda: launch)
    token = users._CURRENT.set(cap)
    try:
        yield SimpleNamespace(launch=launch, cache=cache, cap=cap, home=home, monkeypatch=monkeypatch)
    finally:
        users._CURRENT.reset(token)


def event_for(case, data=b'hello attachment\nsecond line\n', *, filename='report.txt', user='11'):
    path = case.cache / filename
    path.write_bytes(data)
    path.chmod(0o600)
    bot = SimpleNamespace(id=123)
    adapter = Adapter(bot)
    file = SimpleNamespace(file_id='native-file-id', file_unique_id='native-unique-id', file_size=len(data))
    message = SimpleNamespace(get_bot=lambda: bot, chat=SimpleNamespace(id=11, type='private'),
                              from_user=SimpleNamespace(id=int(user)), message_id=77, topic='8',
                              document=file, photo=[], reply_to_message=None)
    source = SimpleNamespace(platform=SimpleNamespace(value='telegram'), user_id=user, chat_id='11',
                             chat_type='dm', thread_id='8', message_id='77', profile='own',
                             _friday_user_scope=case.cap)
    source._identity = RoutingIdentity('transport', 'own', case.launch, case.home,
                                       transport=weakref.ref(adapter))
    origin = {'bot_id': '123', 'chat_id': '11', 'message_id': '77',
              'file_id': file.file_id, 'file_unique_id': file.file_unique_id, 'declared_bytes': len(data)}
    content = {'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    event = SimpleNamespace(text=f'read {path}', media_urls=[str(path)], media_types=['text/plain'],
                            source=source, raw_message=message, message_id='77', internal=False,
                            _ingress_merged=False, _ingress_update_id=42, platform_update_id=42,
                            reply_to_message_id=None, _telegram_media_receipts={str(path): {'origin': origin, 'content': content}})
    # The real identity uses a weak reference, as production does.
    event._test_adapter_lifetime = adapter
    return event, path


def test_received_file_is_readable_now_and_with_later_scope_from_history(case):
    event, source = event_for(case)
    original_proof = ingress.message_provenance(event._test_adapter_lifetime, event)
    assert original_proof['media'][0]['content']['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    intake.rehome_inbound_media(event)
    received = Path(event.media_urls[0])
    assert received.parent == case.home / 'workspace' / 'received'
    assert received.name.endswith('_report.txt')
    assert received.read_bytes() == source.read_bytes()
    assert received.stat().st_mode & 0o777 == 0o600 and received.stat().st_nlink == 1
    assert received.parent.stat().st_mode & 0o777 == 0o700
    assert str(source) not in event.text and str(received) in event.text
    result = json.loads(users.scoped_file('read_file', {'path': str(received)}))
    assert result['scope'] == 'own_user_workspace' and 'hello attachment' in result['content']
    intake.rehome_inbound_media(event)
    assert event.media_urls == [str(received)]
    assert len(list(received.parent.iterdir())) == 1
    # Simulate a later turn/restart with only the path retained in history.
    history = json.loads(json.dumps({'text': event.text, 'path': str(received)}))
    fresh = users.UserScope(case.launch, case.home, 'own', case.cap.principal,
                            case.cap.binding, case.cap.directory_identity, 1)
    case.monkeypatch.setattr(fresh, 'check', lambda: fresh)
    token = users._CURRENT.set(fresh)
    del event
    try:
        later = json.loads(users.scoped_file('read_file', {'path': history['path'], 'offset': 2, 'limit': 1}))
        assert later['content'] == '2: second line'
    finally:
        users._CURRENT.reset(token)


def test_real_sdk_message_and_native_download_receipt_enter_ordinary_read(case):
    from telegram import Bot, Chat, Document, Message, User
    from plugins.platforms.telegram.telegram_file_boundary import stamp_media
    event, path = event_for(case)
    bot = Bot('123:offline-only')
    # Native SDK identity already returned by admission; no initialize/API call.
    bot._bot_user = User(123, 'Offline', is_bot=True)
    message = Message(77, datetime(2026, 1, 1, tzinfo=timezone.utc), Chat(11, 'private'),
                      from_user=User(11, 'Own', is_bot=False),
                      document=Document('sdk-file-id', 'sdk-unique-id', file_name='report.txt',
                                        file_size=path.stat().st_size), message_thread_id=8)
    message.set_bot(bot)
    adapter = Adapter(bot)
    event._test_adapter_lifetime = adapter
    event.source._identity = RoutingIdentity('transport', 'own', case.launch, case.home,
                                               transport=weakref.ref(adapter))
    event.raw_message = message
    event._telegram_media_receipts.clear()
    stamp_media(event, message, str(path), path.read_bytes())
    intake.rehome_inbound_media(event)
    result = json.loads(users.scoped_file('read_file', {'path': event.media_urls[0]}))
    assert result['scope'] == 'own_user_workspace' and 'hello attachment' in result['content']


def test_cache_mutation_during_descriptor_read_is_refused(case, monkeypatch):
    event, path = event_for(case, b'a' * 65537)
    read = os.read
    changed = False
    def mutate(fd, size):
        nonlocal changed
        data = read(fd, size)
        if not changed:
            changed = True
            with path.open('ab') as stream:
                stream.write(b'x')
        return data
    monkeypatch.setattr(intake.os, 'read', mutate)
    with pytest.raises(users.ScopeDenied):
        intake.rehome_inbound_media(event)
    assert not list((case.home / 'workspace').iterdir())


@pytest.mark.parametrize('change', ['user', 'bot', 'chat', 'thread', 'origin', 'missing_receipt', 'missing_native',
                                   'mutated', 'wrong_size', 'oversized', 'merged'])
def test_unproved_or_changed_attachment_cannot_enter_workspace(case, change):
    event, source = event_for(case)
    receipt = event._telegram_media_receipts[str(source)]
    if change == 'user':
        event.source.user_id = '22'
        event.raw_message.from_user.id = 22
    elif change == 'bot':
        event._test_adapter_lifetime._bot.id = 999
    elif change == 'chat':
        event.source.chat_id = '22'
        event.raw_message.chat.id = 22
    elif change == 'thread':
        event.source.thread_id = '9'
    elif change == 'origin':
        receipt['origin']['message_id'] = '78'
    elif change == 'missing_receipt':
        event._telegram_media_receipts.clear()
    elif change == 'missing_native':
        event.raw_message = None
    elif change == 'mutated':
        source.write_bytes(b'X' * source.stat().st_size)
    elif change == 'wrong_size':
        receipt['content']['size_bytes'] += 1
    elif change == 'oversized':
        receipt['content']['size_bytes'] = 1_000_001
        receipt['origin']['declared_bytes'] = 1_000_001
        event.raw_message.document.file_size = 1_000_001
    elif change == 'merged':
        event._ingress_merged = True
    with pytest.raises(users.ScopeDenied):
        intake.rehome_inbound_media(event)
    assert not list((case.home / 'workspace').iterdir())
    assert event.media_urls == [str(source)]


@pytest.mark.parametrize('change', ['symlink', 'hardlink', 'parent_symlink', 'escaped', 'foreign_cache',
                                   'public_source', 'received_symlink'])
def test_path_and_descriptor_attacks_are_refused(case, change):
    event, source = event_for(case)
    original = source
    if change == 'symlink':
        actual = source.with_name('actual.txt')
        source.rename(actual)
        source.symlink_to(actual)
    elif change == 'hardlink':
        os.link(source, source.with_name('second-link.txt'))
    elif change == 'parent_symlink':
        actual = case.cache.with_name('actual-documents')
        case.cache.rename(actual)
        case.cache.symlink_to(actual, target_is_directory=True)
    elif change in {'escaped', 'foreign_cache'}:
        foreign = case.home.parent / 'foreign' / 'cache'
        foreign.mkdir(parents=True, mode=0o700)
        target = foreign / 'report.txt'
        target.write_bytes(source.read_bytes())
        target.chmod(0o600)
        source = Path(str(case.cache / '..' / '..' / '..' / 'foreign' / 'cache' / 'report.txt')) if change == 'escaped' else target
        event.media_urls = [str(source)]
        event._telegram_media_receipts[str(source)] = event._telegram_media_receipts.pop(str(original))
    elif change == 'public_source':
        source.chmod(0o644)
    elif change == 'received_symlink':
        foreign = case.home.parent / 'foreign'
        foreign.mkdir(mode=0o700)
        (case.home / 'workspace' / 'received').symlink_to(foreign, target_is_directory=True)
    with pytest.raises(users.ScopeDenied):
        intake.rehome_inbound_media(event)
    if change == 'received_symlink':
        assert not list(foreign.iterdir())
    else:
        assert not list((case.home / 'workspace').iterdir())


def test_other_user_cannot_read_received_path_or_cache(case):
    event, cached = event_for(case)
    intake.rehome_inbound_media(event)
    received = event.media_urls[0]
    other_home = case.home.parent / 'other'
    other_home.mkdir(mode=0o700)
    (other_home / 'workspace').mkdir(mode=0o700)
    other = users.UserScope(case.launch, other_home, 'other', ('telegram', 'transport', '123', '22'),
                            case.cap.binding, (other_home.stat().st_dev, other_home.stat().st_ino), 1)
    case.monkeypatch.setattr(other, 'check', lambda: other)
    token = users._CURRENT.set(other)
    try:
        for path in (received, str(cached)):
            with pytest.raises(users.ScopeDenied):
                users.scoped_file('read_file', {'path': path})
    finally:
        users._CURRENT.reset(token)


def test_existing_name_is_verified_and_never_overwritten(case):
    event, source = event_for(case)
    intake.rehome_inbound_media(event)
    received = Path(event.media_urls[0])
    received.write_bytes(b'changed by user')
    again, _ = event_for(case)
    with pytest.raises(users.ScopeDenied):
        intake.rehome_inbound_media(again)
    assert received.read_bytes() == b'changed by user'
    assert not list(received.parent.glob('incoming_*'))


def test_native_cache_prefix_and_unsafe_display_characters_have_safe_stable_name(case):
    event, path = event_for(case, filename='doc_1234567890ab_report [v1].txt')
    intake.rehome_inbound_media(event)
    received = Path(event.media_urls[0])
    assert received.name.endswith('_report__v1_.txt')
    assert all(c.isascii() and (c.isalnum() or c in '._-') for c in received.name)
    intake.rehome_inbound_media(event)
    assert event.media_urls == [str(received)]


def test_unmanaged_legacy_rehome_keeps_original_move(case):
    event, source = event_for(case)
    case.monkeypatch.setattr(users, 'ordinary_file_scope', lambda: None)
    case.monkeypatch.setattr(hermes_constants, 'get_hermes_home', lambda: case.home)
    visible = ModuleType('tools.credential_files')
    visible.to_agent_visible_cache_path = lambda value: value
    case.monkeypatch.setitem(sys.modules, visible.__name__, visible)
    intake.rehome_inbound_media(event)
    destination = case.home / 'cache' / 'documents' / source.name
    assert event.media_urls == [str(destination)] and destination.is_file() and not source.exists()
    assert not (case.home / 'workspace' / 'received').exists()


def test_native_original_delivery_route_binds_before_rehome(case):
    from gateway.run_plugin_delivery import bind_ordinary_document_source
    event, _ = event_for(case)
    from gateway.config import Platform
    event.source.platform=Platform.TELEGRAM
    bind_ordinary_document_source(event,event.source)
    route=event.source._friday_document_route
    assert route['bot_id']=='123' and route['runtime_profile']=='own'
    assert route['source']['chat_id']==event.source.chat_id
    assert route['source']['message_id']==event.source.message_id
    assert route['source']['thread_id']==event.source.thread_id
    intake.rehome_inbound_media(event)
    # The producer still proves a managed immutable original destination after
    # this event's verified bytes have moved into its ordinary workspace.
    bind_ordinary_document_source(event,event.source)
    assert event.source._friday_document_route==route


def test_intake_pins_admitted_home_inode_before_publication(case):
    event,_=event_for(case)
    before=case.cap.directory_identity
    case.cap.directory_identity=(before[0],before[1]+1)
    with pytest.raises(users.ScopeDenied): intake.rehome_inbound_media(event)
    assert not (case.home/'workspace/received').exists()
