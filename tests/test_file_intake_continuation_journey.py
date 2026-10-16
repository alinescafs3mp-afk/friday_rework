"""One offline native journey: SDK attachment to persisted revision and bytes.

The caller/model choices and transport ACK are supplied fixtures. Native ingress
proof, confined reads/writes, SQLite replay, MEDIA resolution and journals run.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from types import MethodType, SimpleNamespace

from telegram import Bot, Chat, Document, Message, User

from test_file_revision_native_continuation import (
    account, entered, open_db, actor, run_tool, delivery_fixture, pin,
    SessionDB, SessionStore, GatewayConfig, SESSION, TEXT, REVISED, transport,
)
from gateway import run_inbound_media, run_plugin_delivery as delivery
from gateway.platforms.base import BasePlatformAdapter
from plugins.platforms.telegram import telegram_ingress
from plugins.platforms.telegram.telegram_file_boundary import stamp_media


def test_uploaded_txt_reopens_revises_and_delivers_without_restaging(account, monkeypatch):
    cache = account.root/'cache'/'documents'
    cache.mkdir(parents=True, mode=0o700)
    cache.parent.chmod(0o700)
    original = cache/'uploaded.txt'
    original.write_bytes(TEXT.encode()); original.chmod(0o600)
    source = account.sources['1']; adapter = account.adapters[0]
    bot = Bot('101:offline-only'); bot._bot_user = User(101, 'Offline', is_bot=True)
    adapter._bot = bot
    adapter.message_provenance = MethodType(telegram_ingress.message_provenance, adapter)
    adapter._effective_message_thread_id = lambda message: str(message.message_thread_id or '')
    sdk = Message(303, datetime(2026, 1, 1, tzinfo=timezone.utc), Chat(202, 'private'),
        from_user=User(1, 'Own', is_bot=False), document=Document(
            'actual-sdk-file', 'actual-sdk-unique', file_name=original.name, file_size=original.stat().st_size))
    sdk.set_bot(bot)
    event = SimpleNamespace(source=source, raw_message=sdk, message_id='303',
        internal=False, _ingress_merged=False, _ingress_update_id=42, platform_update_id=42,
        reply_to_message_id=None, media_urls=[str(original)], media_types=['text/plain'],
        text=f'Read and return this uploaded note: {original}', _telegram_media_receipts={})
    stamp_media(event, sdk, str(original), original.read_bytes())
    with entered(account):
        run_inbound_media.rehome_inbound_media(event)
        received = Path(event.media_urls[0])
        assert received.read_bytes() == TEXT.encode()
        assert received.parent == account.homes['1']/'workspace'/'received'
        db = open_db(account)
        store = SessionStore(account.homes['1']/'sessions', GatewayConfig())
        try:
            messages = [{'role': 'user', 'content': event.text}]
            read = run_tool(actor(db), messages, 'read_file', {'path': str(received)}, 'uploaded-read')
            assert read['success'] and 'Original second point.' in read['content']
            sender, bound, sent = delivery_fixture(account, store)
            # Exercise the actual projected MEDIA resolver and managed dispatcher.
            relative = received.relative_to(account.homes['1']/'workspace').as_posix()
            files, _ = BasePlatformAdapter.extract_media(f'MEDIA:"./{relative}"')
            files = BasePlatformAdapter.filter_media_delivery_paths(files)
            observed = []
            assert asyncio.run(delivery.deliver_ordinary_files(sender, bound,
                [path for path, _ in files], record_delivery=observed.append))
            assert observed[0].success and sent[-1][1] == TEXT.encode()
        finally:
            store.close_all_db_handles(); db.close()
    # Original download disappears; only persisted workspace content/history remain.
    original.unlink()
    with entered(account):
        db = SessionDB(account.homes['1']/'state.db')
        store = SessionStore(account.homes['1']/'sessions', GatewayConfig())
        try:
            replay = store.load_transcript(SESSION)
            observation = next(row for row in reversed(replay)
                if row.get('content', '').startswith('[File delivery observation: '))
            # Native replay coalesces adjacent assistant observations. Select
            # the final exact JSON record, rather than assuming one per row.
            prior = json.JSONDecoder().raw_decode(
                observation['content'].rsplit('observation: ', 1)[1])[0]
            assert prior['state'] == 'DELIVERED'
            messages = replay + [{'role': 'user', 'content': 'Revise point two in that file.'}]
            a = actor(db); a._last_flushed_db_idx = len(replay)
            read = run_tool(a, messages, 'read_file', {'path': prior['path']}, 'reopened-upload-read')
            assert read['success']
            with monkeypatch.context() as mp:
                transport(a, messages, mp)
            revised = run_tool(a, messages, 'write_file', {
                'path': prior['path'], 'content': REVISED}, 'reopened-upload-revision')
            assert revised['success'] and revised['verified']
            assert received.read_bytes() == REVISED.encode()
            assert (received.parent/('.friday-before-'+revised['revision_ref'])/'before').read_bytes() == TEXT.encode()
            sender, bound, sent = delivery_fixture(account, store); pin(bound, '304')
            result = asyncio.run(delivery.deliver_ordinary_document(sender, bound, str(received)))
            assert result.success and sent[-1][1] == REVISED.encode()
            assert 'DELIVERED' in store.load_transcript(SESSION)[-1]['content']
        finally:
            store.close_all_db_handles(); db.close()
