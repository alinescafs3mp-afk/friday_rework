import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from caption_fixture import own, private
from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult, ProcessingOutcome, EphemeralReply
from gateway.platforms.event import MessageEvent
from gateway.run_turn_status import TelegramTurnStatus
from gateway import run_plugin_delivery as delivery
from plugins.platforms.telegram.telegram_document_bytes import send_document_bytes
from hermes_cli import friday_user_scope as scopes
from hermes_cli.plugins_state import PluginState


class Adapter(BasePlatformAdapter):
    def __init__(self, own):
        super().__init__(PlatformConfig(enabled=True), Platform.TELEGRAM)
        self.gateway_runner=own.adapter.gateway_runner
        self._bot=SimpleNamespace(id=101,send_document=self.bot_document)
        self._running=True
        self.document_calls=[];self.text_calls=[];self.edits=[];self.deleted=[]
        self.document_fault=None
        self.emit_warning=AsyncMock()
        self._start_typing_refresh=MagicMock(return_value=None)
        self._stop_typing_refresh=AsyncMock()
        self._run_processing_hook=AsyncMock()
        self._flush_text_debounce_now=AsyncMock()
        self._finish_session_task=MagicMock()
        self._release_turn_marker=AsyncMock()
        self._record_delivery_obligation=AsyncMock(return_value=None)
        self._notify_turn_error=AsyncMock(return_value=None)
        self._get_human_delay=lambda:0
        self._media_delivery_scope=lambda source:nullcontext()
        self._should_auto_tts_for_chat=lambda chat:False
        self._bounded_history_media_paths_for_session=AsyncMock(return_value=set())
        self.receipts=[]
    async def connect(self,**kw):return True
    async def disconnect(self):pass
    async def get_chat_info(self,chat_id):return {}
    async def send(self,chat_id,content,reply_to=None,metadata=None):
        self.text_calls.append((chat_id,content,reply_to,metadata))
        return SendResult(success=True,message_id='405')
    async def bot_document(self,**kwargs):
        payload=kwargs['document'].read()
        self.document_calls.append({**kwargs,'document':payload})
        if self.document_fault:raise self.document_fault
        return SimpleNamespace(document=SimpleNamespace(file_id='native-file',file_size=len(payload)),
            message_id=404,chat=SimpleNamespace(id=202),message_thread_id=kwargs.get('message_thread_id'))
    async def send_document_bytes(self,chat_id,data,**kwargs):
        return await send_document_bytes(self,chat_id,data,**kwargs)
    def _media_send_kwargs(self,chat,reply,metadata):
        result={'chat_id':int(chat),'reply_to_message_id':int(reply)}
        if (metadata or {}).get('thread_id') is not None: result['message_thread_id']=int(metadata['thread_id'])
        return int(reply),result
    def _metadata_thread_id(self,metadata):return (metadata or {}).get('thread_id')
    def _caption_1024(self,caption):return caption[:1024] if caption else None
    def _send_flood_cooldown_remaining(self,chat):return 0
    def _chat_outbound_slot_remaining(self,chat):return 0
    async def delete_message(self,chat,message):self.deleted.append(message);return True
    async def edit_message(self,chat,message,text,**kw):
        self.edits.append(text);return SendResult(success=True,message_id=message)


@pytest.fixture
def adapter(own,monkeypatch):
    a=Adapter(own)
    monkeypatch.setattr(delivery,'resolve_document_route',lambda runner,context,route:(own.source,a))
    monkeypatch.setattr('gateway.platforms.base.diagnostic_wake_muted',lambda event:False)
    # Native guard still executes. Its private-value catalog is empty in this isolated identity.
    return a


def background(own,adapter,text):
    async def run():
        async def handler(event):return text
        adapter._message_handler=handler
        event=MessageEvent(text='request',source=own.source,message_id=own.source.message_id)
        ctx=SimpleNamespace(source=own.source,agent_holder=[None])
        status=TelegramTurnStatus(SimpleNamespace(),ctx,adapter,{})
        status.task=None;status.message_id='progress';status.phase='delivery';status.awaiting_delivery=True
        adapter.register_post_delivery_callback('fixture',status.after_delivery)
        async def receipt(*,delivery_receipt):adapter.receipts.append(delivery_receipt)
        adapter.register_post_delivery_callback('fixture',receipt)
        await adapter._process_message_background(event,'fixture')
        assert not adapter._post_delivery_callbacks
        assert status.ended and not status.awaiting_delivery
        assert adapter._notify_turn_error.await_count == 0
        return status
    return asyncio.run(run())


def answer(path,text='Готово. В документе — полный ответ.'):
    return text+'\nMEDIA:'+path


def test_single_document_answer_is_complete_caption_with_one_reply(own,adapter):
    path=private(own.work/'answer.txt',b'exact bytes')
    background(own,adapter,answer(path))
    assert not adapter.text_calls
    assert len(adapter.document_calls)==1
    call=adapter.document_calls[0]
    assert call['caption']=='Готово. В документе — полный ответ.'
    assert call['reply_to_message_id']==303 and call['document']==b'exact bytes'
    assert adapter.receipts==['confirmed'] and adapter.deleted==['progress']
    assert adapter._run_processing_hook.call_args.args[-1] is ProcessingOutcome.SUCCESS
    assert adapter._record_delivery_obligation.await_count==0
    observed=[x['display_metadata']['friday_file_delivery_observation']['state'] for x in own.history]
    assert observed==['UNKNOWN','DELIVERED']
    state=PluginState('friday_rework').get(delivery._ORDINARY_DOCUMENTS)
    row=next(iter(state['files'].values()))
    assert row['state']=='DELIVERED' and row['receipt']['reply_to']=='303'


@pytest.mark.parametrize('text',['x'*1025,'😀'*513],ids=['ascii-overflow','astral-overflow'])
def test_long_caption_preserves_complete_text_fallback(own,adapter,text):
    path=private(own.work/'long.txt')
    background(own,adapter,answer(path,text))
    assert len(adapter.text_calls)==len(adapter.document_calls)==1
    assert adapter.text_calls[0][1]==text and adapter.document_calls[0]['caption'] is None
    assert adapter.receipts==['confirmed']


@pytest.mark.parametrize('text',['x'*1024,'😀'*512],ids=['ascii-limit','astral-limit'])
def test_caption_exact_limit_keeps_every_character(own,adapter,text):
    path=private(own.work/'boundary.txt')
    background(own,adapter,answer(path,text))
    assert not adapter.text_calls and adapter.document_calls[0]['caption']==text


def test_multiple_files_keep_original_full_text_and_both_documents(own,adapter):
    first=private(own.work/'one.txt');second=private(own.work/'two.txt')
    background(own,adapter,answer(first,'Two files')+'\nMEDIA:'+second)
    assert [c[1] for c in adapter.text_calls]==['Two files']
    assert len(adapter.document_calls)==2 and all(c['caption'] is None for c in adapter.document_calls)
    assert adapter.receipts==['confirmed']


def test_repeated_media_tag_is_one_document_caption(own,adapter):
    path=private(own.work/'same.txt')
    background(own,adapter,answer(path)+'\nMEDIA:'+path)
    assert not adapter.text_calls and len(adapter.document_calls)==1


def test_lost_ack_is_unknown_no_text_fallback_and_no_second_send(own,adapter):
    path=private(own.work/'unknown.txt')
    adapter.document_fault=TimeoutError('synthetic lost ACK')
    status=background(own,adapter,answer(path))
    assert status.phase=='unknown' and not adapter.deleted
    assert adapter.receipts==['unknown'] and not adapter.text_calls
    assert len(adapter.document_calls)==1
    assert adapter._run_processing_hook.call_args.args[-1] is ProcessingOutcome.FAILURE
    private(Path(path),b'revised after unknown');own.source.message_id='304';own.pin()
    background(own,adapter,answer(path))
    assert len(adapter.document_calls)==1 and not adapter.text_calls
    state=PluginState('friday_rework').get(delivery._ORDINARY_DOCUMENTS)
    assert next(iter(state['files'].values()))['state']=='UNKNOWN'


@pytest.mark.parametrize('fault',['privacy','authorization','source','commit'])
def test_preflight_failure_does_not_send_answer_or_document(own,adapter,monkeypatch,fault):
    path=private(own.work/'rejected.txt')
    if fault=='privacy':
        monkeypatch.setattr(scopes,'guard_gateway_reply',lambda source,text:('private refusal',True))
    elif fault=='authorization':
        def denied(*a,**kw):raise RuntimeError('route no longer authorized')
        monkeypatch.setattr(delivery,'resolve_document_route',denied)
    elif fault=='source':
        adapter._bot.id=999
    else:
        def denied(*a,**kw):raise OSError('reservation unavailable')
        monkeypatch.setattr(PluginState,'set_commit',denied)
    status=background(own,adapter,answer(path,'must never be sent'))
    assert not adapter.text_calls and not adapter.document_calls and not adapter.deleted
    assert adapter.receipts==['unknown']
    assert adapter.emit_warning.await_count==0
    assert adapter._run_processing_hook.call_args.args[-1] is ProcessingOutcome.FAILURE


def test_later_revision_preserves_prior_receipt_and_rejects_replayed_ingress(own,adapter):
    path=private(own.work/'revision.txt',b'first')
    background(own,adapter,answer(path,'First answer'))
    state=PluginState('friday_rework')
    prior={p.name:p.read_bytes() for p in state.data_dir.glob('friday-*.json')}
    own.source.message_id='304';own.pin();private(Path(path),b'second')
    background(own,adapter,answer(path,'Second answer'))
    assert [c['caption'] for c in adapter.document_calls]==['First answer','Second answer']
    assert [c['reply_to_message_id'] for c in adapter.document_calls]==[303,304]
    assert all((state.data_dir/name).read_bytes()==body for name,body in prior.items())
    own.source.message_id='303';own.pin();private(Path(path),b'replay')
    background(own,adapter,answer(path,'must not resend'))
    assert len(adapter.document_calls)==2 and not adapter.text_calls
    assert adapter.receipts==['confirmed','confirmed','unknown']


def test_dispatch_unmanaged_remains_original_path(monkeypatch):
    monkeypatch.setattr(scopes,'ordinary_file_source',lambda:None)
    assert asyncio.run(delivery.deliver_ordinary_files(SimpleNamespace(),SimpleNamespace(),['legacy'],caption='answer')) is False


def test_empty_media_stays_text_only(own,adapter):
    background(own,adapter,'Plain answer')
    assert [c[1] for c in adapter.text_calls]==['Plain answer'] and not adapter.document_calls


def test_real_privacy_guard_rejects_private_host_path_before_reservation(own,adapter):
    path=private(own.work/'private-caption.txt')
    text='Host private path: '+str(own.home/'private.key')
    guarded,blocked=scopes.guard_gateway_reply(own.source,text)
    assert blocked and guarded!=text
    background(own,adapter,answer(path,text))
    assert not adapter.document_calls and not adapter.text_calls
    assert adapter.emit_warning.await_count==0
    assert PluginState('friday_rework').get(delivery._ORDINARY_DOCUMENTS) is None


def test_cancellation_keeps_unknown_and_never_retries(own,adapter):
    path=private(own.work/'cancelled.txt')
    adapter.document_fault=asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):background(own,adapter,answer(path))
    assert len(adapter.document_calls)==1 and not adapter.text_calls
    assert adapter.receipts==['unknown'] and not adapter.deleted
    assert not adapter._post_delivery_callbacks
    state=PluginState('friday_rework').get(delivery._ORDINARY_DOCUMENTS)
    assert next(iter(state['files'].values()))['state']=='UNKNOWN'
    adapter.document_fault=None
    background(own,adapter,answer(path))
    assert len(adapter.document_calls)==1 and not adapter.text_calls


def test_streamed_body_keeps_media_dispatch_without_caption(own,adapter):
    from gateway.run_notifications import GatewayNotificationsMixin
    path=private(own.work/'streamed.txt')
    runner=SimpleNamespace(_thread_metadata_for_source=lambda *a: {},_reply_anchor_for_event=lambda *a:'303')
    asyncio.run(GatewayNotificationsMixin._deliver_media_from_response(
        runner,answer(path,'Already streamed'),SimpleNamespace(source=own.source),adapter))
    assert len(adapter.document_calls)==1 and adapter.document_calls[0]['caption'] is None
    assert not adapter.text_calls


def test_single_bare_file_uses_same_native_caption_path(own,adapter):
    path=private(own.work/'bare.txt')
    background(own,adapter,'Here is the file.\n'+path)
    assert not adapter.text_calls and len(adapter.document_calls)==1
    assert adapter.document_calls[0]['caption']=='Here is the file.'


@pytest.mark.parametrize('lost_ack',[False,True],ids=['confirmed-clock','unknown-clock'])
def test_caption_reply_clock_requires_actual_delivery(own,adapter,monkeypatch,lost_ack):
    from hermes_cli.observability import shared_metrics_gateway as metrics
    monkeypatch.setattr(metrics,'_submit',lambda *args,**kwargs:None)
    metrics.start_reply_clock(own.source)
    key=('telegram','202')
    assert key in metrics._reply_clocks
    path=private(own.work/'timed.txt')
    if lost_ack:adapter.document_fault=TimeoutError('lost ACK')
    background(own,adapter,answer(path))
    assert (key in metrics._reply_clocks) is lost_ack
    metrics._reply_clocks.pop(key,None);metrics._chat_homes.pop(key,None)
