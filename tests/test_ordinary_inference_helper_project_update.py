"""Exact helper-only update with synthetic source/custody; no live acceptance."""
import copy
from pathlib import Path

import pytest

from test_ordinary_dsh_project_update import installed, put, doc, snapshot, repin, f, o, Budget


@pytest.fixture
def helper(installed, monkeypatch):
    s=installed
    old=copy.deepcopy(s['previous'])
    # Restore source files changed by the earlier-transition fixture, without
    # executing that transition or changing its retained input/ancestry.
    for name in set(s['after']) & set(old['project_files']):
        data=s['before_dsh'] if name==o.PROJECT_DSH else b'# previous '+name.encode()+b'\n'
        assert put(s['root']/name,data)['sha256']==old['project_files'][name]
    additions=[o.SPARK_MULTIPASS_MANIFEST,'patches/hermes/spark-primary-multipass.patch']
    additions += ['scripts/dsh_prepare.py','scripts/friday_worker_preparation.py']
    additions += [f'config/source79-retained-{n}.txt' for n in range(5)]
    for name in additions:
        old['project_files'][name]=put(s['root']/name,b'retained source79 fixture\n')['sha256']
    assert len(old['project_files'])==231
    oldref=doc(s['requestpath'].with_name('helper-previous.json'),old)
    source_input=copy.deepcopy(old)
    source_input['project_files'].update({'scripts/dsh_prepare.py':'b'*64,
        'scripts/friday_worker_preparation.py':'c'*64})
    source_ref=doc(s['requestpath'].with_name('helper-source79-input.json'),source_input)
    monkeypatch.setattr(o,'PROJECT_INFERENCE_INPUT_BEFORE',oldref['sha256'])
    monkeypatch.setattr(o,'PROJECT_INFERENCE_PREDECESSOR_INPUT',source_ref['sha256'])
    current=copy.deepcopy(old)
    current['project_files'][o.PROJECT_INFERENCE_HELPER]=put(
        s['root']/o.PROJECT_INFERENCE_HELPER,b'# reviewed helper-only afterimage\n')['sha256']
    monkeypatch.setattr(o,'PROJECT_INFERENCE_HELPER_BEFORE',old['project_files'][o.PROJECT_INFERENCE_HELPER])
    s['layers'].extend([
        {'manifest':'patches/hermes/source78.json','manifest_sha256':'7'*64,'patch_sha256':'8'*64},
        {'manifest':o.SPARK_MULTIPASS_MANIFEST,'manifest_sha256':'9'*64,'patch_sha256':'a'*64}])
    receiptref=doc(s['home']/'hermes-agent.source.json',s['receipt'])
    stamp=f.read_json(s['source']/'install-stamp.json')
    stamp['fridaySource']['layers']=s['layers']
    stampref=doc(s['source']/'install-stamp.json',stamp)
    history=copy.deepcopy(s['history']);prior=s['prior'];generation=s['prevref']
    for number in (32,33):
        following=source_ref if number==33 else doc(s['requestpath'].with_name('helper-intermediate.json'),{'id':32})
        previous_request={'schema':f'friday.ordinary-telegram-source-update.v{number}',
            'home':str(s['home']),'previous_input':generation,'current_input':following,
            'transaction_history':copy.deepcopy(history),'predecessor_update':prior}
        prior=doc(s['requestpath'].with_name(f'helper-predecessor-{number}.json'),previous_request)
        tx=s['home']/'preparation'/('ordinary-source-update-'+generation['sha256'])
        doc(tx/'intent.json',{'schema':'friday.ordinary-telegram-source-update-transaction.v1',
            'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':prior['sha256']})
        doc(tx/'committed.json',{'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
            'previous_input':generation,'current_input':following,
            'source_receipt_sha256':receiptref['sha256'],'gateway_started':False,'workers_enabled':False})
        put(tx/'before/preserved',b'closed historical source, never replayed\n')
        history.update({str(p.relative_to(s['home'])):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
        generation=following
    # Small synthetic inventories retain exact checks against their declared
    # fixture counts; real Source79 counts require separate installed evidence.
    monkeypatch.setattr(o,'PROJECT_INFERENCE_NATIVE_FILES',len(s['receipt']['files']))
    monkeypatch.setattr(o,'PROJECT_INFERENCE_HISTORY_FILES',len(history))
    marker=copy.deepcopy(s['marker'])
    marker.update(input_sha256=oldref['sha256'],source_receipt_sha256=receiptref['sha256'])
    marker['ordinary_gateway']['operator_entry']['input']=oldref
    marker['ordinary_gateway']['source_receipt_sha256']=receiptref['sha256']
    markerref=doc(s['home']/f.MARKER,marker)
    archive=s['home']/o.PROJECT_INFERENCE_RECONCILIATION
    reconciled={
        'intent.json':{'state':'CONSUMED_NO_RETRY','original_attempt':marker['original_attempt']},
        'committed.json':{'state':'ARCHIVED_CLOSED_FAILURE_WORKERS_OFF_NO_CONTINUATION_AUTHORITY',
            'workers_enabled':False,'runtime_acceptance':False},
        'before/FRIDAY-INSTALL.json':dict(marker,input_sha256=source_ref['sha256']),
    }
    monkeypatch.setattr(o,'PROJECT_INFERENCE_RECONCILIATION_PINS',{
        str((archive/name).relative_to(s['home'])):doc(archive/name,value)['sha256']
        for name,value in reconciled.items()})
    request=copy.deepcopy(s['request'])
    request.update(schema=o.PROJECT_INFERENCE_HELPER_SCHEMA,previous_input=oldref,
        current_input=doc(Path(request['current_input']['path']),current),marker=markerref,
        source_receipt=receiptref,stamp=stampref,transaction_history=history,predecessor_update=prior)
    doc(s['requestpath'],request)
    s.update(previous=old,current=current,request=request,marker=marker,history=history,receiptref=receiptref)
    return s


def test_source79_helper_update_publishes_only_marker_and_retains_full_ancestry(helper):
    s=helper;before=snapshot(s['home'])
    result=o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    assert {n for n in before if before[n]!=after[n]}=={f.MARKER}
    marker=f.read_json(s['home']/f.MARKER)
    assert marker['ordinary_gateway']['operator_entry']['input']==s['request']['current_input']
    assert marker['ordinary_gateway']['operator_entry']['script']['sha256']==s['current']['project_files']['scripts/friday_native.py']
    assert marker['original_attempt']==s['marker']['original_attempt']
    assert marker['plugin_files']==s['marker']['plugin_files']
    assert result['native_source_unchanged'] is True and result['ready'] is False
    assert result['gateway_started'] is result['workers_enabled'] is False
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert set(f.read_json(tx/'intent.json')['before'])=={f.MARKER}
    history=dict(s['history'],**{str(p.relative_to(s['home'])):f.digest(p.read_bytes()) for p in tx.rglob('*') if p.is_file()})
    o.update_history(s['home'],history,doc(s['requestpath'],s['request']))
    with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))


@pytest.mark.parametrize('fault',['extra','plugin','before','unchanged','settings','zero',
    'source77','last_layer','native_count','history_count','predecessor','history',
    'reconciled_input','source_input','archive_pin'])
def test_helper_update_refuses_unreviewed_scope_before_publication(helper,monkeypatch,fault):
    s=helper;r=s['request']
    if fault=='extra':s['current']['project_files']['unreviewed.py']=put(s['root']/'unreviewed.py',b'no\n')['sha256']
    elif fault=='plugin':
        name='plugins/friday_rework/unchanged.py'
        s['current']['project_files'][name]=put(s['root']/name,b'unreviewed plugin\n')['sha256']
    elif fault=='before':monkeypatch.setattr(o,'PROJECT_INFERENCE_HELPER_BEFORE','0'*64)
    elif fault=='unchanged':s['current']['project_files'][o.PROJECT_INFERENCE_HELPER]=s['previous']['project_files'][o.PROJECT_INFERENCE_HELPER]
    elif fault=='settings':s['current']['model']='changed'
    elif fault=='zero':
        s['previous']['product']['runtime']={'enabled':0};s['current']['product']['runtime']={'enabled':0}
        r['previous_input']=doc(s['requestpath'].with_name('zero-previous.json'),s['previous'])
    elif fault=='source77':
        s['receipt']['layers'][:]=s['receipt']['layers'][:77];r['source_receipt']=doc(s['home']/'hermes-agent.source.json',s['receipt'])
    elif fault=='last_layer':
        s['receipt']['layers'][-1]['manifest']='unreviewed.json';r['source_receipt']=doc(s['home']/'hermes-agent.source.json',s['receipt'])
    elif fault=='native_count':monkeypatch.setattr(o,'PROJECT_INFERENCE_NATIVE_FILES',999)
    elif fault=='history_count':monkeypatch.setattr(o,'PROJECT_INFERENCE_HISTORY_FILES',999)
    elif fault=='predecessor':
        prior=f.read_json(Path(r['predecessor_update']['path']));prior['schema']='friday.ordinary-telegram-source-update.v32'
        r['predecessor_update']=doc(s['requestpath'].with_name('wrong-predecessor.json'),prior)
    elif fault=='history':
        name=next(n for n in r['transaction_history'] if n.endswith('/before/preserved'))
        put(s['home']/name,b'changed historical source\n')
    elif fault=='reconciled_input':monkeypatch.setattr(o,'PROJECT_INFERENCE_INPUT_BEFORE','0'*64)
    elif fault=='source_input':monkeypatch.setattr(o,'PROJECT_INFERENCE_PREDECESSOR_INPUT','0'*64)
    elif fault=='archive_pin':
        name=next(iter(o.PROJECT_INFERENCE_RECONCILIATION_PINS))
        put(s['home']/name,b'unreviewed reconciliation metadata\n')
    repin(s);before=snapshot(s['home'])
    with pytest.raises(ValueError):o.update(r,s['requestpath'],Budget(180))
    assert snapshot(s['home'])==before


@pytest.mark.parametrize('interrupt',[False,True])
def test_helper_marker_failure_restores_only_owned_marker(helper,monkeypatch,interrupt):
    s=helper;before=snapshot(s['home']);publish=o.publish_update_file;injected=False
    def fail(path,*args,**kwargs):
        nonlocal injected
        result=publish(path,*args,**kwargs)
        if path==s['home']/f.MARKER and not injected:
            injected=True
            if interrupt:raise KeyboardInterrupt('synthetic cancellation')
            raise RuntimeError('synthetic marker failure')
        return result
    monkeypatch.setattr(o,'publish_update_file',fail)
    with pytest.raises(KeyboardInterrupt if interrupt else RuntimeError):o.update(s['request'],s['requestpath'],Budget(180))
    after=snapshot(s['home'])
    assert all(after[n]==row for n,row in before.items())
    tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
    assert (tx/'rolled-back.json').is_file()
