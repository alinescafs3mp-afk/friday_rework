import asyncio
import contextlib
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

from hermes_cli import friday_user_scope as scopes
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from gateway import run_plugin_delivery as delivery
from gateway.config import Platform
from gateway.platforms.base import SendResult, BasePlatformAdapter, validate_media_delivery_path
from gateway.session import SessionSource
from gateway.session_identity import RoutingIdentity


@pytest.fixture
def own(tmp_path, monkeypatch):
    home = tmp_path / 'alice'; home.mkdir(mode=0o700)
    work = home / 'workspace'; work.mkdir(mode=0o700)
    st = home.stat()
    cap = scopes.UserScope(tmp_path, home, 'alice', ('telegram', 'transport', '101', '202'), {}, (st.st_dev,st.st_ino), 1)
    monkeypatch.setattr(cap, 'check', lambda: cap)
    source = SessionSource(platform=Platform.TELEGRAM, chat_id='202', chat_type='dm', user_id='202',
                           profile='alice', message_id='303', thread_id=None)
    source._friday_user_scope = cap
    source._friday_document_session_id = 'session-alice'
    source._identity = RoutingIdentity('transport', 'alice', tmp_path, home)
    def pin():
        source._friday_document_route = delivery.freeze_route({'transport_profile':'transport','runtime_profile':'alice',
            'bot_id':'101','source':{'platform':'telegram', **{k:getattr(source,k) for k in
                ('chat_id','chat_type','user_id','thread_id','message_id')}}})
    pin()
    sent = []
    history=[]
    async def append(session_id,message):
        assert session_id=='session-alice'; history.append(message)
    adapter = SimpleNamespace(_bot=SimpleNamespace(id=101), gateway_runner=SimpleNamespace(
        async_session_store=SimpleNamespace(append_to_transcript=append)), is_connected=True)
    async def send_bytes(chat, data, *, file_name, reply_to, metadata, caption=None):
        sent.append((chat, data, file_name, reply_to, metadata))
        proof = dict(kind='document', sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                     file_name=file_name, bot_id='101', chat_id=chat, thread_id=None, reply_to=reply_to, message_id='404')
        return SendResult(success=True, message_id='404', raw_response=proof)
    adapter.send_document_bytes = send_bytes
    monkeypatch.setattr(delivery, 'resolve_document_route', lambda runner, context, route: (source, adapter))
    token = set_hermes_home_override(str(home))
    ct = scopes._CURRENT.set(cap); stoken = scopes._SOURCE.set(source)
    try:
        yield SimpleNamespace(home=home, work=work, cap=cap, source=source, adapter=adapter, sent=sent, history=history, pin=pin)
    finally:
        scopes._SOURCE.reset(stoken); scopes._CURRENT.reset(ct); reset_hermes_home_override(token)


def private(path, data=b'1. first\n2. second\n3. third\n'):
    path.write_bytes(data); path.chmod(0o600); return str(path)


def test_descriptor_scope_own_and_cross_user_symlink_escape(own, tmp_path):
    path=private(own.work/'draft.md')
    assert scopes.workspace_document(path)[0].startswith(b'1. first')
    assert validate_media_delivery_path(path)==path
    foreign=private(tmp_path/'foreign.md')
    assert validate_media_delivery_path(foreign) is None
    for bad in (foreign, str(own.work/'../foreign.md'), str(own.work/'link.md')):
        if bad.endswith('link.md'): (own.work/'link.md').symlink_to(path)
        with pytest.raises(scopes.ScopeDenied): scopes.workspace_document(bad)
    (own.work/'hard.md').hardlink_to(path)
    with pytest.raises(scopes.ScopeDenied): scopes.workspace_document(str(own.work/'hard.md'))


def test_descriptor_rejects_midread_mutation(own, monkeypatch):
    path=private(own.work/'draft.md', b'a'*65537)
    original=os.read; altered=False
    def mutate(fd, size):
        nonlocal altered
        data=original(fd,size)
        if not altered:
            altered=True
            with open(path,'ab') as stream: stream.write(b'x')
        return data
    monkeypatch.setattr(scopes.os,'read',mutate)
    with pytest.raises(scopes.ScopeDenied): scopes.workspace_document(path)


def test_create_revision_read_send_then_restart_dedup(own, monkeypatch):
    # Actual scoped create-only read/write entrypoints, no shell or worker.
    monkeypatch.setattr(scopes, 'guard_tool', lambda *args, **kw: None)
    monkeypatch.setattr('hermes_cli.friday_credential_admission.ordinary_readonly_file', lambda *a: None)
    original='1. first\n2. second\n3. third\n'
    scopes.scoped_file('write_file', {'path':'draft.md','content':original})
    read=json.loads(scopes.scoped_file('read_file', {'path':'draft.md'}))
    assert '2: 2. second' in read['content']
    result=asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,str(own.work/'draft.md')))
    assert result.success and own.sent[0][1]==original.encode()
    # A later request restores prior content/path from the persisted transcript;
    # revisions stay explicit new paths and preserve first/third lines.
    transcript=json.dumps({'path':str(own.work/'draft.md'),'content':original})
    retained=json.loads(transcript)
    revised=retained['content'].replace('2. second','2. revised')
    scopes.scoped_file('write_file', {'path':'draft-v2.md','content':revised})
    own.source.message_id='304'; own.pin()
    result=asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,str(own.work/'draft-v2.md')))
    assert result.success and own.sent[-1][1]==revised.encode() and own.sent[-1][3]=='304'
    # New PluginState object reads disk; a repeated artifact never sends again.
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,str(own.work/'draft-v2.md'))).success
    assert len(own.sent)==2
    own.source.message_id='306'; own.pin()
    assert asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,str(own.work/'draft-v2.md'))).success
    assert len(own.sent)==3 and 'DELIVERED' in own.history[-1]['content']
    with pytest.raises(scopes.ScopeDenied):
        scopes.scoped_file('write_file', {'path':'draft-v2.md','content':'overwrite'})


def test_unknown_no_duplicate_after_reentry_or_mutation(own):
    path=private(own.work/'draft.md')
    async def lost_ack(*a, **k):
        own.sent.append(('accepted-no-ack',a[1])); raise OSError('lost acknowledgement')
    own.adapter.send_document_bytes=lost_ack
    result=asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path))
    assert not result.success and result.error=='document_delivery_UNKNOWN'
    private(Path(path),b'mutated')
    own.source.message_id='305'; own.pin()
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success
    assert len(own.sent)==1


def test_unknown_survives_missing_current_record(own):
    path=private(own.work/'draft.md')
    async def lost(*a, **k): raise OSError('unknown')
    own.adapter.send_document_bytes=lost
    asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path))
    from hermes_cli.plugins_state import PluginState
    state=PluginState('friday_rework'); state.set(delivery._ORDINARY_DOCUMENTS,None)
    # Immutable native UNKNOWN history still blocks a send after state rollback.
    own.adapter.send_document_bytes=lambda *a, **k: pytest.fail('must not resend')
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success


def test_wrong_source_bot_or_path_has_no_effect(own, tmp_path):
    path=private(own.work/'draft.md')
    own.adapter._bot.id=999
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success
    own.adapter._bot.id=101
    other=SessionSource(platform=Platform.TELEGRAM,chat_id='909',chat_type='dm',user_id='909',message_id='3')
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,other,path)).success
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,private(tmp_path/'foreign.md'))).success
    assert not own.sent


def test_legacy_dispatch_continues_original_path(monkeypatch):
    monkeypatch.setattr(scopes, 'ordinary_file_source', lambda: None)
    assert asyncio.run(delivery.deliver_ordinary_files(SimpleNamespace(),SimpleNamespace(),['legacy'])) is False


def test_shared_dispatch_deduplicates_paths(own):
    path=private(own.work/'draft.md')
    results=[]
    assert asyncio.run(delivery.deliver_ordinary_files(own.adapter,own.source,[path,path],record_delivery=results.append))
    assert len(own.sent)==len(results)==1 and results[0].success


def test_original_route_cannot_be_retargeted(own):
    path=private(own.work/'draft.md')
    own.source.chat_id='999'
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success
    assert not own.sent


def test_shared_streaming_and_nonstreaming_media_dispatch(own):
    from gateway.run_notifications import GatewayNotificationsMixin
    own.adapter._media_delivery_scope=lambda source: contextlib.nullcontext()
    own.adapter.extract_media=BasePlatformAdapter.extract_media
    own.adapter.extract_images=BasePlatformAdapter.extract_images
    first=private(own.work/'nonstream.md')
    results=[]
    event=SimpleNamespace(source=own.source)
    asyncio.run(BasePlatformAdapter._deliver_media_attachments(own.adapter,event,[(first,False)],[],
        force_document_attachments=False,human_delay=0,metadata={},record_delivery=results.append))
    second=private(own.work/'stream.md',b'2. streaming')
    runner=SimpleNamespace(_thread_metadata_for_source=lambda *a: {}, _reply_anchor_for_event=lambda *a:'303')
    asyncio.run(GatewayNotificationsMixin._deliver_media_from_response(runner,'MEDIA:'+second,event,own.adapter))
    assert [x[1] for x in own.sent]==[Path(first).read_bytes(),b'2. streaming']
    assert results[0].success


def test_uncertainty_enters_normal_transcript_and_notice(own):
    path=private(own.work/'unknown.md')
    notices=[]
    async def warning(chat,text,metadata=None): notices.append((chat,text))
    async def lost(*a,**k): raise OSError('lost ack')
    own.adapter.send_document_bytes=lost; own.adapter.emit_warning=warning
    asyncio.run(delivery.deliver_ordinary_files(own.adapter,own.source,[path]))
    assert len(notices)==1 and 'UNKNOWN' in notices[0][1]
    assert 'UNKNOWN' in own.history[-1]['content'] and 'unknown.md' in own.history[-1]['content']


def test_managed_home_inode_swap_is_refused(own):
    path=private(own.work/'draft.md')
    original=own.cap.directory_identity; own.cap.directory_identity=(original[0],original[1]+1)
    with pytest.raises(scopes.ScopeDenied): scopes.workspace_document(path)


def test_unmanaged_media_keeps_authority_after_other_profile_engaged(monkeypatch):
    monkeypatch.setattr(scopes, '_ENGAGED', True)
    monkeypatch.setattr(scopes, 'policy', lambda home: None)
    token=scopes._CURRENT.set(None)
    try:
        assert scopes.ordinary_file_scope() is None
        assert scopes.ordinary_file_source() is None
    finally: scopes._CURRENT.reset(token)


def test_missing_scope_managed_profile_refuses_delivery(monkeypatch):
    monkeypatch.setattr(scopes, 'policy', lambda home: {'enabled':True})
    token=scopes._CURRENT.set(None)
    try:
        with pytest.raises(scopes.ScopeDenied): scopes.ordinary_file_source()
    finally: scopes._CURRENT.reset(token)


def test_native_document_bytes_never_retries_missing_topic(own):
    from plugins.platforms.telegram.telegram_document_bytes import send_document_bytes
    calls=[]
    async def missing_topic(**kwargs):
        calls.append(kwargs); raise OSError('topic does not exist')
    own.adapter._bot.send_document=missing_topic
    own.adapter._media_send_kwargs=lambda chat,reply,metadata: (None,{'chat_id':chat,
        'message_thread_id':17,'reply_to_message_id':reply})
    own.adapter._caption_1024=lambda caption: caption
    result=asyncio.run(send_document_bytes(own.adapter,'202',b'exact immutable bytes',
        file_name='draft.md',reply_to='303',caption=None,metadata={'thread_id':'17'}))
    assert not result.success and len(calls)==1
    assert calls[0]['message_thread_id']==17 and calls[0]['reply_to_message_id']=='303'


def test_adapter_send_document_checks_target_and_shared_route(own):
    from plugins.platforms.telegram.adapter import TelegramAdapter
    own.adapter._metadata_thread_id=lambda metadata: None
    path=private(own.work/'direct.md')
    assert not asyncio.run(TelegramAdapter.send_document(own.adapter,'999',path)).success
    assert not asyncio.run(TelegramAdapter.send_document(own.adapter,'202',path,reply_to='999')).success
    assert not own.sent
    assert asyncio.run(TelegramAdapter.send_document(own.adapter,'202',path)).success
    assert len(own.sent)==1


def test_immutable_snapshot_is_the_sent_payload(own):
    path=private(own.work/'snapshot.md',b'checked original')
    sender=own.adapter.send_document_bytes
    async def replace_during_send(chat,data,**kwargs):
        private(Path(path),b'changed pathname')
        return await sender(chat,data,**kwargs)
    own.adapter.send_document_bytes=replace_during_send
    assert asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success
    assert own.sent[0][1]==b'checked original'
    own.source.message_id='310'; own.pin()
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success
    assert len(own.sent)==1


def test_reservation_failure_prevents_any_send(own,monkeypatch):
    from hermes_cli.plugins_state import PluginState
    def broken(*a,**k): raise OSError('reserve failed')
    monkeypatch.setattr(PluginState,'set_commit',broken)
    path=private(own.work/'never.md')
    assert not asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path)).success
    assert not own.sent


def test_unmanaged_cache_allowlist_retains_native_compatibility(own,tmp_path,monkeypatch):
    import gateway.platforms.base as base
    monkeypatch.setattr(scopes,'policy',lambda home:None)
    monkeypatch.setattr(base,'_media_delivery_allowed_roots',lambda:[tmp_path])
    token=scopes._CURRENT.set(None)
    try:
        sibling=private(tmp_path/'sibling-profile.md')
        assert base.validate_media_delivery_path(sibling)==sibling
    finally: scopes._CURRENT.reset(token)
