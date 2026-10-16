"""Source-only SDK receipt → native intake → confined ordinary read contracts.

Synthetic admitted users and local files only. No Telegram/model/live acceptance.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import weakref

import pytest

from document_fixtures import docx, pdf, scanned_pdf
from test_ordinary_attachment_intake import Adapter, case, event_for, intake, users
from gateway.session_identity import RoutingIdentity
from tools import file_tools


def sdk_event(case, name, data):
    from telegram import Bot, Chat, Document, Message, User
    from plugins.platforms.telegram.telegram_file_boundary import stamp_media

    event, original = event_for(case, data, filename=name)
    bot = Bot('123:offline-only')
    bot._bot_user = User(123, 'Offline', is_bot=True)
    message = Message(
        77, datetime(2026, 1, 1, tzinfo=timezone.utc), Chat(11, 'private'),
        from_user=User(11, 'Own', is_bot=False),
        document=Document('sdk-file-id', 'sdk-unique-id', file_name=name,
                          file_size=len(data)), message_thread_id=8)
    message.set_bot(bot)
    adapter = Adapter(bot)
    event._test_adapter_lifetime = adapter
    event.source._identity = RoutingIdentity(
        'transport', 'own', case.launch, case.home, transport=weakref.ref(adapter))
    event.raw_message = message
    event._telegram_media_receipts.clear()
    stamp_media(event, message, str(original), data)
    return event, original


@pytest.mark.parametrize('name,data,expected,format', [
    pytest.param('report.txt', 'Отчёт é 漢字 🙂\r\nВторая строка\n'.encode(),
                 'Отчёт é 漢字 🙂', None, id='utf8-txt'),
    pytest.param('report.docx', docx(), 'Own uploaded report', 'docx', id='docx'),
    pytest.param('report.pdf', pdf(), 'Own uploaded PDF report', 'pdf', id='pdf'),
])
def test_native_sdk_intake_read_and_later_scope(case, name, data, expected, format):
    event, original = sdk_event(case, name, data)
    intake.rehome_inbound_media(event)
    received = Path(event.media_urls[0])
    assert received.parent == case.home / 'workspace' / 'received'
    assert received.read_bytes() == original.read_bytes() == data
    assert str(received) in event.text and str(original) not in event.text
    result = json.loads(file_tools.read_file_tool(str(received)))
    assert result['success'] and expected in result['content']
    assert result['scope'] == 'own_user_workspace'
    if format:
        assert result['extracted_document'] and result['format'] == format
        assert result['coverage'] == 'text_only; images_and_layout_not_covered'
    history_path = json.loads(json.dumps({'path': str(received)}))['path']
    fresh = users.UserScope(case.launch, case.home, 'own', case.cap.principal,
                            case.cap.binding, case.cap.directory_identity, 1)
    case.monkeypatch.setattr(fresh, 'check', lambda: fresh)
    token = users._CURRENT.set(fresh)
    del event
    try:
        assert json.loads(file_tools.read_file_tool(history_path)) == result
    finally:
        users._CURRENT.reset(token)


@pytest.mark.parametrize('name,data,reason', [
    pytest.param('bad.txt', b'\xff\xfe\x00\xff', None, id='invalid-utf8'),
    pytest.param('bad.docx', b'not-a-zip', 'malformed_or_required_part_limit', id='bad-docx'),
    pytest.param('bad.pdf', b'not-a-pdf', 'malformed_or_unsupported', id='bad-pdf'),
    pytest.param('scanned.pdf', scanned_pdf(), 'needs_ocr', id='scanned-pdf'),
])
def test_intake_preserves_unsupported_bytes_and_read_refuses_honestly(case, name, data, reason):
    event, original = sdk_event(case, name, data)
    intake.rehome_inbound_media(event)
    received = Path(event.media_urls[0])
    assert received.read_bytes() == original.read_bytes() == data
    result = json.loads(file_tools.read_file_tool(str(received)))
    assert result['success'] is False
    if reason:
        assert result['error'] == 'document_extraction_failed'
        assert result['reason'] == reason
    else:
        assert result['error'] == 'product_user_scope_refused'
    assert received.read_bytes() == data


@pytest.mark.parametrize('change', ['missing', 'foreign', 'symlink', 'traversal'])
def test_read_controls_after_real_native_intake(case, change):
    event, _ = sdk_event(case, 'report.docx', docx())
    intake.rehome_inbound_media(event)
    received = Path(event.media_urls[0])
    path = str(received)
    if change == 'missing':
        received.unlink()
    elif change == 'symlink':
        original = received.with_suffix('.original')
        received.rename(original)
        received.symlink_to(original)
    elif change == 'traversal':
        path = str(received.parent / '..' / 'received' / received.name)
    elif change == 'foreign':
        other_home = case.home.parent / 'other'
        other_home.mkdir(mode=0o700)
        (other_home / 'workspace').mkdir(mode=0o700)
        st = other_home.stat()
        cap = users.UserScope(case.launch, other_home, 'other',
                               ('telegram', 'transport', '123', '22'),
                               case.cap.binding, (st.st_dev, st.st_ino), 1)
        case.monkeypatch.setattr(cap, 'check', lambda: cap)
        case.monkeypatch.setattr(users, 'current', lambda required=False: cap)
    assert json.loads(file_tools.read_file_tool(path)) == {
        'success': False, 'error': 'product_user_scope_refused'}


def test_receipt_without_existing_native_download_cannot_publish(case):
    event, original = sdk_event(case, 'report.pdf', pdf())
    original.unlink()
    with pytest.raises(users.ScopeDenied):
        intake.rehome_inbound_media(event)
    assert event.media_urls == [str(original)]
    assert not (case.home / 'workspace' / 'received').exists()
