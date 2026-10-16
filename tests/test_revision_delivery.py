import asyncio, hashlib, copy
from pathlib import Path
import pytest
from test_ordinary_document_delivery import own, private
from gateway import run_plugin_delivery as delivery
from hermes_cli.plugins_state import PluginState


def send(own,path):
    return asyncio.run(delivery.deliver_ordinary_document(own.adapter,own.source,path))

def next_request(own,number='304'):
    own.source.message_id=number;own.pin()


def test_later_request_delivers_revised_same_path_and_preserves_receipts(own):
    path=private(own.work/'draft.md',b'first version')
    assert send(own,path).success
    state=PluginState('friday_rework')
    prior={p.name:p.read_bytes() for p in state.data_dir.glob('friday-*.json')}
    assert prior and any(hashlib.sha256(b'first version').hexdigest().encode() in b for b in prior.values())
    private(Path(path),b'revised second version');next_request(own)
    result=send(own,path)
    assert result.success and [x[1] for x in own.sent]==[b'first version',b'revised second version']
    assert [x[3] for x in own.sent]==['303','304']
    assert all((state.data_dir/n).read_bytes()==b for n,b in prior.items())
    assert len(own.history)==4 and 'DELIVERED' in own.history[-1]['content']


def test_changed_bytes_same_ingress_is_not_a_new_delivery(own):
    path=private(own.work/'draft.md',b'first');assert send(own,path).success
    private(Path(path),b'changed');assert not send(own,path).success
    assert len(own.sent)==1


@pytest.mark.parametrize('field,value',[('chat_id','999'),('user_id','999'),('thread_id','9'),('chat_type','group')])
def test_later_revision_cannot_change_original_route(own,field,value):
    path=private(own.work/'draft.md',b'first');assert send(own,path).success
    private(Path(path),b'changed');route=copy.deepcopy(own.source._friday_document_route)
    route['source']['message_id']='304';route['source'][field]=value
    with pytest.raises(ValueError,match='delivery_requires_reconciliation'):
        delivery._begin_ordinary_document(own.cap,'draft.md',b'changed',route,'draft.md')
    assert len(own.sent)==1


def test_committed_unknown_return_failure_never_repeats_new_revision(own,monkeypatch):
    path=private(own.work/'draft.md',b'first');assert send(own,path).success
    original=delivery._ordinary_commit
    def lost_return(*args,**kwargs):
        original(*args,**kwargs);raise RuntimeError('fixture lost commit return')
    monkeypatch.setattr(delivery,'_ordinary_commit',lost_return)
    private(Path(path),b'changed');next_request(own)
    assert not send(own,path).success and len(own.sent)==1
    monkeypatch.setattr(delivery,'_ordinary_commit',original)
    private(Path(path),b'another revision');next_request(own,'305')
    assert not send(own,path).success and len(own.sent)==1


def test_revised_ack_unknown_keeps_old_receipt_and_stops_next_send(own):
    path=private(own.work/'draft.md',b'first');assert send(own,path).success
    state=PluginState('friday_rework');prior={p.name:p.read_bytes() for p in state.data_dir.glob('friday-*.json')}
    async def lost(*args,**kwargs):
        own.sent.append(('unknown',args[1]));raise OSError('fixture missing ACK')
    own.adapter.send_document_bytes=lost
    private(Path(path),b'changed');next_request(own)
    assert not send(own,path).success and len(own.sent)==2
    assert all((state.data_dir/n).read_bytes()==b for n,b in prior.items())
    next_request(own,'305');private(Path(path),b'third')
    assert not send(own,path).success and len(own.sent)==2


def test_a_b_a_replay_is_denied_after_later_delivery(own):
    path=private(own.work/'draft.md',b'first');assert send(own,path).success
    next_request(own);private(Path(path),b'second');assert send(own,path).success
    next_request(own,'303');private(Path(path),b'third attempt at old ingress')
    assert not send(own,path).success and len(own.sent)==2


@pytest.mark.parametrize('candidate_only',[False,True])
def test_old_native_journals_without_ingress_markers_still_deny_replay(own,monkeypatch,candidate_only):
    original=delivery._ordinary_commit
    def legacy_journals(state,value,previous,*,journals):
        import json
        journals=tuple((kind,body) for kind,body in journals
            if not (json.loads(body).get('schema')=='friday.ordinary-document-attempt.v1'
                    and 'route' in json.loads(body)))
        return original(state,value,previous,journals=journals)
    monkeypatch.setattr(delivery,'_ordinary_commit',legacy_journals)
    path=private(own.work/'draft.md',b'first');assert send(own,path).success
    next_request(own);assert send(own,path).success
    monkeypatch.setattr(delivery,'_ordinary_commit',original)
    if candidate_only:
        import json
        state=PluginState('friday_rework')
        for p in state.data_dir.glob('friday-unknown-*.json'):
            row=json.loads(p.read_bytes())
            if row.get('relative_path')=='draft.md' and row.get('route',{}).get('source',{}).get('message_id')=='303':p.unlink()
    next_request(own,'303');private(Path(path),b'modified replay')
    assert not send(own,path).success and len(own.sent)==2


def test_corrupt_immutable_history_refuses_without_send(own):
    path=private(own.work/'draft.md');assert send(own,path).success
    state=PluginState('friday_rework');p=next(state.data_dir.glob('friday-candidate-*.json'))
    p.chmod(0o600);p.write_bytes(b'{broken');p.chmod(0o400)
    next_request(own);assert not send(own,path).success and len(own.sent)==1
