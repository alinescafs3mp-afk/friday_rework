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


