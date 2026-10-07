"""Bounded consumer controls; SDK integration is in test_web_stream_native."""
import json
import threading
import time
from types import SimpleNamespace

import pytest
from test_web_runtime_runner import M


def consumer(secrets=('SYNTHETIC_SCOPED_CREDENTIAL',)):
    n=M['Native']();n.secrets=secrets;n.stream_redactor=M['_SecretPrefixRedactor'](secrets)
    n.stream_lock=threading.RLock();n.stream_deadline=time.monotonic()+30
    n.stream_text='';n.stream_input=n.stream_callbacks=n.stream_publications=0
    n.stream_published_input=0;n.stream_published_at=0.;n.interrupts=[];n.saved=[]
    n.agent=SimpleNamespace(interrupt=n.interrupts.append,_session_messages=[])
    n.observe(n.saved.append)
    return n


@pytest.mark.parametrize('escaped',[False,True])
def test_every_chunk_boundary_full_and_partial_prefixes(escaped):
    secret='SYNTHETIC_QUOTE"SLASH\\UNICODEя' if escaped else 'SYNTHETIC_SCOPED_CREDENTIAL'
    for form in M['_secret_forms']((secret,)):
        for cut in range(1,len(form)):
            n=consumer((secret,));n._stream_delta('useful visible text; '+form[:cut])
            first=n.partial()['partial_response']
            assert first=='useful visible text; [REDACTED_PARTIAL]'
            n._stream_delta(form[cut:]+'; continued')
            assert n.partial()['partial_response']=='useful visible text; [REDACTED]; continued'
            assert all(form not in json.dumps(x) for x in n.saved)


def test_prefix_is_not_released_on_retry_mismatch_or_native_buffer_reset():
    n=consumer();n._stream_delta('before; SYNTHETIC_SCOPED_')
    n.agent._current_streamed_assistant_text=''
    n._stream_delta('after retry')
    assert n.partial()['partial_response']=='before; [REDACTED_PARTIAL]after retry'
    assert n.saved[0]['partial_response']=='before; [REDACTED_PARTIAL]'


@pytest.mark.parametrize('where',['callbacks','input','retained','writes','deadline','persistence'])
def test_callback_caps_or_failed_sink_interrupt_once_and_never_resume(where):
    n=consumer();n._stream_delta('retained useful text')
    text='next'
    if where=='callbacks':n.stream_callbacks=4096
    elif where=='input':n.stream_input=65536
    elif where=='retained':n.stream_text='a'*16384
    elif where=='writes':n.stream_publications=256;n.stream_published_at=0
    elif where=='deadline':n.stream_deadline=0
    else:
        n.stream_published_at=0
        n.observe(lambda x:(_ for _ in ()).throw(OSError('synthetic sink failure')))
    with pytest.raises((M['Refused'],OSError)):n._stream_delta(text)
    assert n.observation_failed and n.interrupts==['observation_persistence_failed']
    before=(n.stream_input,n.stream_callbacks,len(n.saved))
    with pytest.raises(M['Refused']):n._stream_delta('ignored')
    assert before==(n.stream_input,n.stream_callbacks,len(n.saved))
    assert len(n.interrupts)==1


def test_many_small_callbacks_coalesce_and_preserve_bounded_snapshot():
    n=consumer()
    for _ in range(1024):n._stream_delta('a')
    assert n.partial()['partial_response']=='a'*1024
    assert 1<=len(n.saved)<=8
    assert n.stream_callbacks==1024 and n.stream_input==1024


def test_prefix_scrub_before_truncation_and_secret_trie_bound():
    value={'final_response':'a'*16375+'SYNTHETIC_SCOPED_CREDENTIAL'}
    public=M['_bounded_public'](value,('SYNTHETIC_SCOPED_CREDENTIAL',))
    assert public['observation_truncated'] and 'SYNTHETIC' not in public['final_response']
    with pytest.raises(M['Refused'],match='redaction_limit'):
        consumer(('x'*8193,))


def test_hard_publication_byte_cap_refuses_before_creating_file(tmp_path):
    path=tmp_path/'observation.json'
    with pytest.raises(M['Refused'],match='observation_file_limit'):
        M['_publish'](path,{'final_response':'я'*(1024*1024)},replace=True)
    assert not list(tmp_path.iterdir())


def test_observation_schema_survives_secret_prefix_matching_field_names():
    result=M['_observation']({'final_response':'safe response','messages':[]},('friday-private-token',))
    assert set(('final_response','partial_response','tool_calls','tool_source_observations'))<=set(result)
