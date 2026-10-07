"""Bounded consumer controls; SDK integration is in test_web_stream_native."""
import json
import random
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
            threshold=M['_secret_form_prefixes']((secret,))[form]
            assert first=='useful visible text; '+('[REDACTED_PARTIAL]' if cut>=threshold else form[:cut])
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


REALISTIC_SECRETS = ('sk-synthetic_credential_only_1234567890',
                     'a1234567-89ab-4cde-8012-3456789abcde',
                     'local-synthetic_credential_only', 'friday-synthetic_credential_only')


@pytest.mark.parametrize('secret', REALISTIC_SECRETS)
def test_ordinary_evidence_nested_schema_and_every_split_remain_exact(secret):
    url='https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html'
    text='Sources: respect_retry_after_header supports status retries. '+url
    value={'final_response':json.dumps({'sources':[url]}), 'tool_calls':[[
        {'id':'source1','type':'function','function':{'name':'web_search',
         'arguments':json.dumps({'query':'urllib3 Retry status'})}}]],
        'tool_source_observations':[{'role':'tool','tool_call_id':'source1',
                                     'name':'web_extract','content':text}]}
    assert M['_bounded_public'](value,(secret,))==dict(value,observation_truncated=False)
    for ordinary in (text,'status','local','friday','s', 'a', 'l', 'f'):
        assert M['_redact'](ordinary,(secret,))==ordinary
        for cut in range(len(ordinary)+1):
            n=consumer((secret,));n._stream_delta(ordinary[:cut]);n._stream_delta(ordinary[cut:])
            assert n.partial()['partial_response']==ordinary


@pytest.mark.parametrize('secret', REALISTIC_SECRETS + ('sk-"\\я_sensitive_secret',))
def test_meaningful_partial_full_escaped_and_cutoff_controls(secret):
    for form,threshold in M['_secret_form_prefixes']((secret,)).items():
        for cut in range(1,len(form)):
            n=consumer((secret,));n._stream_delta(form[:cut])
            expected='[REDACTED_PARTIAL]' if cut>=threshold else form[:cut]
            assert n.partial()['partial_response']==expected
            n._stream_delta(form[cut:])
            assert n.partial()['partial_response']=='[REDACTED]'
            if cut>=threshold:
                assert M['_redact'](form[:cut]+'! mismatch',(secret,))=='[REDACTED_PARTIAL]! mismatch'
        # Artificial cuts must conceal even one matching character, without
        # changing the 16 Ki scan budget or claiming a complete observation.
        for visible in range(1,threshold+1):
            value=M['_bounded_public']({'final_response':'Z'*(16384-visible)+form},(secret,))
            assert value['observation_truncated']
            assert form[:visible] not in value['final_response'].lstrip('Z')
        value=M['_bounded_public']({'data':{form:'before '+form+' after'}},(secret,))
        assert value['data']=={'[REDACTED]':'before [REDACTED] after'}


def test_overlapping_short_matches_and_short_full_credentials():
    secret='aaaab_secret_credential'
    for prefix in ('a','aa','aaa','aaaa','aaaaa'):
        assert M['_redact'](prefix+secret,(secret,))==prefix+'[REDACTED]'
    assert M['_redact']('before xy after',('xy',))=='before [REDACTED] after'
    n=consumer(('sk-"\\я_sensitive_secret',))
    n._stream_delta('sk-"\\я_sensitive')
    assert n.stream_redactor.pending==[]
    assert n.partial()['partial_response']=='[REDACTED_PARTIAL]'


def test_redacted_keys_preserve_values_and_key_cutoff_is_explicit():
    secrets=('sk-first_synthetic_credential','sk-second_synthetic_credential')
    value=M['_bounded_public']({secrets[0]:'first evidence',secrets[1]:'second evidence'},secrets)
    assert list(value.values())==['first evidence','second evidence',False]
    assert not any(secret in json.dumps(value) for secret in secrets)
    value=M['_bounded_public']({'nested':{'Z'*255+secrets[0]:'retained'}},secrets)
    assert value['observation_truncated'] and list(value['nested'].values())==['retained']


def interval_oracle(text, secrets, *, truncated=False):
    """Exhaustive span oracle: no trie, streaming state or production helper."""
    forms = {}
    for secret in secrets:
        pairs = {(secret, secret[:8])}
        for _ in range(3):
            pairs |= {(json.dumps(v, ensure_ascii=a)[1:-1],
                       json.dumps(p, ensure_ascii=a)[1:-1])
                      for v, p in tuple(pairs) for a in (False, True)}
        for form, prefix in pairs:
            forms[form] = min(forms.get(form, len(prefix)), len(prefix))
    covered, full_ends = set(), set()
    for start in range(len(text)):
        for form, threshold in forms.items():
            length = 0
            while length < min(len(form), len(text)-start) and text[start+length] == form[length]:
                length += 1
            full = length == len(form)
            if full or length >= threshold or (truncated and length and start+length == len(text)):
                covered.update(range(start, start+length))
                if full:
                    full_ends.add(start+length-1)
    result = []
    index = 0
    while index < len(text):
        if index not in covered:
            result.append(text[index]); index += 1
        else:
            end = index
            while end < len(text) and end in covered:
                end += 1
            result.append('[REDACTED]' if full_ends.intersection(range(index, end)) else '[REDACTED_PARTIAL]')
            index = end
    return ''.join(result)


OVERLAPS = [
    (('local-local-SYNTHETIC_CREDENTIAL_123456789',), 'local-local-local-SYNTHETIC_CREDENTIAL_123456789'),
    (('sk-sk-sk-SYNTHETIC_CREDENTIAL_123456789',), 'sk-sk-sk-sk-SYNTHETIC_CREDENTIAL_123456789'),
    (('abcdefghX','hIJKLMNOPQRSTUVWXYZ'), 'abcdefghIJKLMNOPQRSTUVWXYZ'),
    (('abcdefgh','fghijklmnopqrstuvwxyz'), 'abcdefghijklmnopqrstuvwxyz'),
    (('aaaab-synthetic-credential','aaab-synthetic-second'), 'aaaab-synthetic-second'),
    (('ABCDEFGH-long-secret','secret-secondary-credential'), 'ABCDEFGH-long-secret-secondary-credential'),
    (('abcdefghX','hijklmnopY'), 'abcdefghijklmnop! ordinary'),
    (('aaaab_secret_credential',), 'aaaaaaaab_secret_credential'),
    (('xyxy',), 'xyxyxy'),
    (('ab','bc','cd'), 'abcd'),
    (('"\\я"\\я_SYNTHETIC_CREDENTIAL',), '"\\я"\\я"\\я_SYNTHETIC_CREDENTIAL'),
]


@pytest.mark.parametrize('secrets,text', OVERLAPS)
@pytest.mark.parametrize('escaping', [None, False, True])
def test_overlapping_union_every_boundary_snapshot_reset_and_cut(secrets, text, escaping):
    if escaping is not None:
        for _ in range(3):
            text = json.dumps(text, ensure_ascii=escaping)[1:-1]
    expected = interval_oracle(text, secrets)
    assert M['_redact'](text, secrets) == expected
    for cut in range(len(text)+1):
        n = consumer(secrets)
        n._stream_delta('Evidence: '+text[:cut])
        before = n.partial()['partial_response']
        assert before == 'Evidence: '+interval_oracle(text[:cut], secrets)
        assert n.partial()['partial_response'] == before  # snapshot must not consume state
        n.agent._current_streamed_assistant_text = ''
        n._stream_delta(text[cut:]+'; usable URL https://example.org/source')
        assert n.partial()['partial_response'] == interval_oracle('Evidence: '+text+'; usable URL https://example.org/source', secrets)
        assert M['_redact'](text[:cut], secrets, truncated=True) == interval_oracle(text[:cut], secrets, truncated=True)
    n = consumer(secrets)
    for char in text:
        n._stream_delta(char)
    assert n.partial()['partial_response'] == expected
    public = M['_bounded_public']({'final_response':text, 'tool_source_observations':[
        {'role':'tool','tool_call_id':'c1','name':'web_extract','content':text}]}, secrets)
    assert public['final_response'] == expected
    assert public['tool_source_observations'][0]['content'] == expected
    assert not public['observation_truncated']


def test_union_independent_generated_intervals_and_pending_bound():
    rng = random.Random(36180)
    for _ in range(250):
        keys = tuple(''.join(rng.choices('abcd', k=rng.randrange(1, 22))) for _ in range(3))
        text = '~'.join(''.join(rng.choices('abcd', k=6))+rng.choice(keys)[:rng.randrange(1, 24)] for _ in range(4))
        expected = interval_oracle(text, keys)
        assert M['_redact'](text, keys) == expected
        n = consumer(keys)
        for start in range(0, len(text), 3):
            n._stream_delta(text[start:start+3])
        assert n.partial()['partial_response'] == expected
    redactor = M['_SecretPrefixRedactor'](('a'*8191+'b',))
    for _ in range(64):
        assert redactor.feed('a'*1024) == ''
        assert redactor.pending == []
    assert redactor.tail() == '[REDACTED_PARTIAL]'
    assert redactor.feed('b! usable')+redactor.tail() == '[REDACTED]! usable'
    assert len(redactor.edges) == 8193


def test_artificial_cut_conceals_overlapping_union_without_incidental_corruption():
    key = 'local-local-SYNTHETIC_CREDENTIAL_123456789'
    text = 'local-'+key
    for visible in range(1, len(text)):
        public = M['_bounded_public']({'final_response':'Z'*(16384-visible)+text}, (key,))
        assert public['observation_truncated']
        expected = interval_oracle(text[:visible], (key,), truncated=True)
        assert public['final_response'].lstrip('Z') == (expected[:visible]+'[TRUNCATED]' if len(expected)>visible else expected)
