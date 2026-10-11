"""Actual candidate code on private physical fixtures; NO native connector/API.

Protocol doubles establish only finite offline Source behavior, never delivery.
"""
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('candidate_result_rpc', HERE/'result_rpc.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
class SubmachineCustody:
    active=True
    operation_end=time.monotonic()+18
    cleanup=2
    def tighten(self,end):self.operation_end=end
    def commit(self,receipt):pass
async def wrapped_submachine(path,sha):
    return await M.deliver_in_worker(path,sha,SubmachineCustody())
M.deliver=wrapped_submachine
# These legacy controls run UNDER the actual whole supervisor in controls.py.
# This injected custody only adapts the previous API, not live acceptance.
OUT = HERE.parent/os.environ.get('C26_COMPAT_OUT', 'execution-compat81'); OUT.mkdir(mode=0o700)
FIX = OUT/'fixtures'; FIX.mkdir(mode=0o700)
rows = []


def file(name, data):
    p = FIX/name
    if isinstance(data, dict): data = M.encode(data)
    fd = os.open(p, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o400)
    with os.fdopen(fd, 'wb') as f: f.write(data)
    return {'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def control(name, run, expected='OK', fixture=None):
    try:
        value = run(); observed = 'OK'
    except Exception as exc:
        value = {'class': type(exc).__name__, 'message': str(exc)[:150]}; observed = 'REFUSED'
    passed = observed == expected
    rows.append({'id': name, 'expected': expected, 'observed': observed, 'PASS': passed,
                 'value': value, 'physical_fixture': fixture})


sender = json.loads((HERE.parent/'INTAKE.json').read_bytes())
bindings = {}
deps=OUT/'deps';deps.mkdir(mode=0o700)
for slot in ('sol','astra'):
    home=str(deps/(slot+'-home'))
    b={'thread_id':slot+'-offline-thread','account_home':home,'generation':slot+'-offline-generation','backend_endpoint':'unix://'+home+'/app-server-control/app-server-control.sock','role':'Sol' if slot=='sol' else 'Astra','pid':os.getpid(),'backend_pid':os.getpid()}
    bindings[slot]=b
    p=deps/(slot+'.json');p.write_text(json.dumps(b));p.chmod(0o600)
M.DEPENDENCIES={k:deps/(k+'.py') for k in M.DEPENDENCIES}
M.DEPENDENCIES['sender']=deps/'sol.json';M.DEPENDENCIES['recipient']=deps/'astra.json'
for k,p in M.DEPENDENCIES.items():
    if k not in ('sender','recipient'):p.write_text('# inert offline dependency pin\n');p.chmod(0o600)
os.environ['CODEX_THREAD_ID']='sol-offline-thread'  # Owned synthetic worker fixture only.
expected = {slot: {'thread': b['thread_id'], 'home': b['account_home'], 'generation': b['generation'],
                   'endpoint': b['backend_endpoint'].removeprefix('unix://')} for slot,b in bindings.items()}
controls = {slot: SimpleNamespace(thread=e['thread'], home=e['home'], endpoint=Path(e['endpoint'])) for slot,e in expected.items()}

result = file('result.json', {'state':'OFFLINE_SOURCE_FIXTURE_ONLY'})
manifest = file('manifest.json', {'payloads':[]})
body = M.encode({'status':'SOURCE_ONLY_NOT_DELIVERED', 'result':result, 'manifest':manifest})
body_pin = file('notice.json',body)
grant = {'event':'SOL-C24-OFFLINE-R1', 'assignment':'C24-OFFLINE', 'generation':'1',
         'expected':expected, 'notice':body_pin, 'artifacts':{'result':result,'manifest':manifest}}
text = M.notice(grant, body, expected)
control('notice_exact_positive', lambda: len(text.encode()))
control('route_exact_positive', lambda: M.route(bindings['sol'],bindings['astra'],expected,controls,expected['sol']['thread']))

for slot,field,key in [('sol','home','account_home'),('astra','home','account_home'),
                       ('sol','epoch','generation'),('astra','epoch','generation'),
                       ('sol','thread','thread_id'),('astra','thread','thread_id'),
                       ('sol','endpoint','backend_endpoint'),('astra','endpoint','backend_endpoint'),
                       ('sol','role','role'),('astra','role','role')]:
    changed = copy.deepcopy(bindings); changed[slot][key]='foreign'
    pin = file('wrong-'+slot+'-'+field+'.json',changed[slot])
    control('route_wrong_'+slot+'_'+field,
            lambda changed=changed: M.route(changed['sol'],changed['astra'],expected,controls,expected['sol']['thread']), 'REFUSED', pin)
foreign_control = copy.copy(controls); foreign_control['astra']=SimpleNamespace(**{**vars(controls['astra']),'thread':'foreign'})
control('constructor_wrong_route', lambda: M.route(bindings['sol'],bindings['astra'],expected,foreign_control,expected['sol']['thread']), 'REFUSED')
control('caller_wrong_root', lambda: M.route(bindings['sol'],bindings['astra'],expected,controls,'foreign'), 'REFUSED')

for name, raw in [('body_extra_field',M.encode({'status':'SOURCE','result':result,'manifest':manifest,'extra':False})),
                  ('body_foreign_artifact',M.encode({'status':'SOURCE','result':manifest,'manifest':manifest})),
                  ('body_invalid_json',b'{'), ('body_duplicate_field',b'{"status":"one","status":"two"}'),
                  ('body_oversize',b' ' * 2001)]:
    pin=file(name+'.json',raw)
    changed_grant={**grant,'notice':pin}
    control(name,lambda raw=raw,changed_grant=changed_grant:M.notice(changed_grant,raw,expected),'REFUSED',pin)
wrong_pin=copy.deepcopy(result);wrong_pin['sha256']='0'*64
control('wrong_hash',lambda:M.pinned(wrong_pin),'REFUSED',file('wrong-hash.json',wrong_pin))
wrong_pin=copy.deepcopy(result);wrong_pin['bytes']+=1
control('wrong_bytes',lambda:M.pinned(wrong_pin),'REFUSED',file('wrong-bytes.json',wrong_pin))
wrong_pin=copy.deepcopy(result);wrong_pin['bytes']=True
control('bool_pin_bytes',lambda:M.pinned(wrong_pin),'REFUSED',file('bool-bytes.json',wrong_pin))
link=FIX/'symlink.json';link.symlink_to(Path(result['path']))
control('symlink_pin',lambda:M.pinned({**result,'path':str(link)}),'REFUSED',{'path':str(link),'type':'symlink_own_fixture_not_followed_by_checker'})
hard=FIX/'hardlink.json';os.link(result['path'],hard)
control('hardlink_pin',lambda:M.pinned(result),'REFUSED',{'path':str(hard),'type':'owned_hardlink'})
hard.unlink()
unsafe=file('unsafe-mode.json',b'{}');os.chmod(unsafe['path'],0o644)
control('foreign_read_mode',lambda:M.pinned(unsafe),'REFUSED',unsafe)
os.chmod(unsafe['path'],0o400)
fifo=FIX/'fifo-pin';os.mkfifo(fifo,0o600)
control('fifo_pin_refused_before_open',lambda:M.pinned({**result,'path':str(fifo)}),'REFUSED',{'path':str(fifo),'type':'owned_FIFO'})
fifo.unlink()
for name,path in [('protocol_ref_space',str(FIX/'notice with space.json')),
                  ('protocol_ref_newline',str(FIX/'notice\nsecond-peer.json'))]:
    altered={**grant,'notice':{**body_pin,'path':path}}
    control(name,lambda altered=altered:M.notice(altered,body,expected),'REFUSED',file(name+'.json',altered))

clock={'original_start_unix':1000,'original_start_monotonic':50,'original_seconds':1200,
       'cleanup_seconds':120,'useful_deadline_unix':2080,'final_deadline_unix':2200}
control('original_clock_positive',lambda:M.deadline(clock,1010,60))
for name, changes, unix,mono in [('clock_future',{},999,49),('clock_expired',{},2081,1131),
                               ('clock_divergence',{},1010,65),('clock_bool',{'original_seconds':True},1010,60),
                               ('clock_extended',{'useful_deadline_unix':2090},1010,60),
                               ('clock_cleanup_reduced_without_bound',{'cleanup_seconds':119},1010,60),
                               ('clock_nonfinite',{'original_start_unix':float('nan')},1010,60)]:
    fixture={**clock,**changes}
    pin=file(name+'.json',json.dumps(fixture).encode())
    control(name,lambda fixture=fixture,unix=unix,mono=mono:M.deadline(fixture,unix,mono),'REFUSED',pin)


class Base:
    def __init__(self,slot):
        self.sequence=0;self.home=expected[slot]['home'];self.thread=expected[slot]['thread'];self.endpoint=expected[slot]['endpoint']


class Socket:
    def __init__(self,kind): self.kind=kind;self.sent=[];self.transport=SimpleNamespace(abort=lambda:None)
    async def send(self,raw): self.sent.append(json.loads(raw))
    async def recv(self):
        request=self.sent[-1];method=request['method'];rid=request['id']
        if self.kind=='hang_rpc' and method=='thread/queue/add':await asyncio.Future()
        if method=='initialize':
            response={'codexHome': expected['astra']['home'] if self.kind!='initialize_wrong_home' else 'foreign'}
        else:
            q={'id':str(uuid.uuid4()),'clientUserMessageId':grant['event'],
               'input':[{'type':'text','text':text,'text_elements':[]}]}
            if self.kind=='wrong_client':q['clientUserMessageId']='foreign'
            if self.kind=='missing_queueid':del q['id']
            if self.kind=='invalid_queueid':q['id']='notuuid'
            if self.kind=='null_queueid':q['id']=str(uuid.UUID(int=0))
            if self.kind=='wrong_text':q['input'][0]['text']+='foreign'
            if self.kind=='wrong_elements':q['input'][0]['text_elements']=[{}]
            if self.kind=='extra_input':q['input'].append({'type':'text','text':text})
            if self.kind=='extra_input_field':q['input'][0]['extra']=True
            response={'queuedSubmission':q}
            if self.kind=='extra_response_field':response['extra']=False
        value={'id':rid,'result':response}
        if self.kind=='wrong_response_id' and method=='thread/queue/add':value['id']=rid+1
        if self.kind=='bool_response_id':value['id']=True
        if self.kind=='rpc_explicit_error' and method=='thread/queue/add':value={'id':rid,'error':{'code':-1}}
        if self.kind=='rpc_missing_result' and method=='thread/queue/add':value={'id':rid}
        if self.kind=='rpc_both_result_error' and method=='thread/queue/add':value['error']={}
        if self.kind=='notifications_only':return '{"method":"bounded/notification","params":{}}'
        if self.kind=='invalid_notification':return '{"result":{}}'
        if self.kind=='duplicate_rpc_field':return '{"id":1,"id":1,"result":{}}'
        return json.dumps(value)


class Connection:
    def __init__(self,socket,kind,receipt):self.socket=socket;self.kind=kind;self.receipt=receipt;self.close_state=None
    async def __aenter__(self):
        if self.kind=='open_failure':raise ConnectionError('offline injected')
        if self.kind=='hang_open':await asyncio.Future()
        return self.socket
    async def __aexit__(self,*_):
        self.close_state=json.loads(self.receipt.read_bytes())['state']
        if self.kind=='close_failure':raise ConnectionError('offline close injected')
        if self.kind=='hang_close':await asyncio.Future()


def scenario(kind, desired='UNKNOWN', duplicate=False, collision=False):
    directory=OUT/kind;directory.mkdir(mode=0o700)
    audit=directory/'audit';audit.mkdir(mode=0o700)
    receipt=directory/'receipt.json';socket=Socket(kind);connection=Connection(socket,kind,receipt)
    connector=lambda *a,**k:connection
    c=M.bounded_control(Base,connector)('astra');calls=[];checks=[]
    def lifecycle(action,slot):
        calls.append([action,slot])
        if kind=='lifecycle_'+action+'_'+slot:raise M.Refusal('offline lifecycle injected')
    def recheck():
        checks.append(True)
        if kind=='recheck_before_open' or (kind=='recheck_after_open' and len(checks)==2):raise M.Refusal('offline pin drift')
    saved=M.replace_receipt
    if kind=='receipt_commit_failure':
        def fail(*_):raise OSError('offline persistence injected')
        M.replace_receipt=fail
    try:
        value=asyncio.run(M.send_prepared(c,grant,text,time.monotonic()+3.15,receipt,audit,lifecycle,recheck))
    finally:M.replace_receipt=saved
    adds=[x for x in socket.sent if x['method']=='thread/queue/add']
    assert value['state']==desired,(kind,value)
    assert len(adds)<=1 and all(x['method'] in ('initialize','initialized','thread/queue/add') for x in socket.sent)
    assert value['peer_receipt']=='unconfirmed'
    if desired=='ENQUEUED':
        assert connection.close_state=='ENQUEUED'
        assert (audit/'RPC-ADD-CONFIRMED.json').is_file()
    if duplicate:
        value2=asyncio.run(M.send_prepared(c,grant,text,time.monotonic()+0.08,receipt,audit,lifecycle,recheck))
        assert value2['duplicate_suppressed'] is True and value2['queue_calls']==0
        assert len([x for x in socket.sent if x['method']=='thread/queue/add'])==len(adds)
    if collision:
        altered={**grant,'notice':{**body_pin,'sha256':'0'*64}}
        try:asyncio.run(M.send_prepared(c,altered,text,time.monotonic()+0.08,receipt,audit,lifecycle,recheck))
        except M.Refusal:pass
        else:raise AssertionError('collision admitted')
    return {'state':value['state'],'close':value['close'],'queue_add_count':len(adds),
            'close_observed_receipt_state':connection.close_state,'lifecycle_order':calls,
            'no_live_connector_or_API':True,'duplicate':duplicate,'collision_refused':collision}


for kind in ('success','close_failure','hang_close'):
    control('rpc_'+kind,lambda kind=kind:scenario(kind,'ENQUEUED',duplicate=True,collision=True))
for kind in ('open_failure','hang_open','initialize_wrong_home','wrong_response_id','bool_response_id',
             'wrong_client','missing_queueid','invalid_queueid','null_queueid','wrong_text','wrong_elements',
             'extra_input','extra_input_field','extra_response_field','rpc_explicit_error','rpc_missing_result',
             'rpc_both_result_error','notifications_only','invalid_notification','duplicate_rpc_field',
             'hang_rpc','receipt_commit_failure','recheck_before_open','recheck_after_open',
             'lifecycle_check_sol','lifecycle_check_astra','lifecycle_register_sol','lifecycle_register_astra'):
    control('rpc_'+kind,lambda kind=kind:scenario(kind,duplicate=True,collision=True))

unreviewed=file('unreviewed-grant.json',{'decision':'NO_LIVE_AUTHORITY','mode':'LIVE'})
control('unreviewed_live_entry_refused',lambda:asyncio.run(M.deliver(unreviewed['path'],unreviewed['sha256'])),'REFUSED',unreviewed)
control('receipt_over_bound',lambda:M.write_once(OUT/'oversized-receipt.json',{'x':'x'*65536}),'REFUSED')


def full_entry(kind):
    """Replace only connectors/lifecycle and existing-namespace root IN THIS process.

    Exact real dependency/Source/clock pins are still read. All writes remain OUT.
    No actual NativeControl constructor or native API is called by this fixture.
    """
    directory=OUT/('entry-'+kind);directory.mkdir(mode=0o700)
    receipts=directory/'sol-link-native-receipts';receipts.mkdir(mode=0o700)
    audit=directory/'audit';audit.mkdir(mode=0o700)
    src=HERE/'result_rpc.py';src_raw=src.read_bytes()
    src_pin={'path':str(src),'bytes':len(src_raw),'sha256':hashlib.sha256(src_raw).hexdigest()}
    review=file('entry-'+kind+'-review.json',{'decision':'ACCEPT_ONE_NATIVE_RPC_RESULT_SOURCE',
                'source_sha256':src_pin['sha256'],'domain':'INJECTED_OFFLINE_FIXTURE_NOT_INDEPENDENT_ACCEPTANCE'})
    deps={k:{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
          for k,p in M.DEPENDENCIES.items()}
    original_clock=HERE.parent/'TRANSPORT-FIXTURE-CLOCK.json';cr=original_clock.read_bytes()
    births={str(b[key]):Path('/proc/'+str(b[key])+'/stat').read_text().rsplit(')',1)[1].split()[19]
            for b in bindings.values() for key in ('pid','backend_pid')}
    whole={**grant,'decision':'APPROVE_ONE_NATIVE_RPC_RESULT','mode':'LIVE','source':src_pin,
           'independent_review':review,'dependencies':deps,
           'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
           'clock':{'path':str(original_clock),'bytes':len(cr),'sha256':hashlib.sha256(cr).hexdigest()},
           'writer_births':births,'audit_dir':str(audit)}
    if kind=='wrong_boot':whole['boot_id']='foreign'
    if kind=='wrong_review_source':
        whole['independent_review']=file('entry-wrong-review.json',{'decision':'ACCEPT_ONE_NATIVE_RPC_RESULT_SOURCE','source_sha256':'0'*64})
    if kind=='wrong_dependency':whole['dependencies']['control']['sha256']='0'*64
    if kind=='missing_dependency':del whole['dependencies']['native_endpoint']
    if kind=='wrong_writer_birth':whole['writer_births'][next(iter(births))]='0'
    if kind=='missing_writer_birth':whole['writer_births'].pop(next(iter(births)))
    if kind=='wrong_notice_hash':whole['notice']={**whole['notice'],'sha256':'0'*64}
    if kind=='wrong_artifact_hash':whole['artifacts']={**whole['artifacts'],'result':{**result,'sha256':'0'*64}}
    gp=file('entry-'+kind+'-grant.json',whole)
    receipt=receipts/(grant['event']+'.json');socket=Socket('success');connection=Connection(socket,'success',receipt)
    calls=[]
    def lifecycle(args):calls.append([args.profile,args.action,args.kind,args.event]);return 0
    def loader(path):
        if path==str(M.DEPENDENCIES['control']):return {'NativeControl':Base,'unix_connect':lambda *a,**kw:connection}
        if path==str(M.DEPENDENCIES['lifecycle']):return {'command_peer_check':lifecycle,'command_peer_register':lifecycle}
        raise AssertionError('unapproved loader invoked')
    old_R=M.R;old_loader=M.DEPENDENCY_LOADER
    M.R=directory;M.DEPENDENCY_LOADER=loader
    try:value=asyncio.run(M.deliver(gp['path'],gp['sha256']))
    finally:M.R=old_R;M.DEPENDENCY_LOADER=old_loader
    assert value['state']=='ENQUEUED' and connection.close_state=='ENQUEUED'
    assert len([r for r in socket.sent if r['method']=='thread/queue/add'])==1
    assert len(calls)==4
    return {'state':'OFFLINE_ONE_FAKE_QUEUE_ADD_CONFIRMED','actual_native_calls':0,
            'all_writes_under_owned_fixture':str(directory),'grant':gp}


control('full_grant_entry_positive',lambda:full_entry('positive'))
for kind in ('wrong_boot','wrong_review_source','wrong_dependency','missing_dependency','wrong_writer_birth',
             'missing_writer_birth','wrong_notice_hash','wrong_artifact_hash'):
    control('full_grant_entry_'+kind,lambda kind=kind:full_entry(kind),'REFUSED')

for name,kind in [('AS',M.resource.RLIMIT_AS),('CPU',M.resource.RLIMIT_CPU),('FSIZE',M.resource.RLIMIT_FSIZE)]:
    saved=M.resource.getrlimit
    def bad_limit(k,kind=kind,saved=saved):return (-1,-1) if k==kind else saved(k)
    M.resource.getrlimit=bad_limit
    try:control('entry_unbounded_'+name,lambda:asyncio.run(M.deliver(unreviewed['path'],unreviewed['sha256'])),'REFUSED')
    finally:M.resource.getrlimit=saved

report={'domain':'OFFLINE_SOURCE_AND_FAULT_INJECTION_ONLY_NOT_NATIVE_DELIVERY',
        'source':{'path':str(HERE/'result_rpc.py'),'sha256':hashlib.sha256((HERE/'result_rpc.py').read_bytes()).hexdigest()},
        'controls':rows,'raw':len(rows),'unique':len({r['id'] for r in rows}),
        'PASS':sum(r['PASS'] for r in rows),'FAIL':sum(not r['PASS'] for r in rows),
        'native_RPC':0,'native_CLI':0,'model_calls':0,'independent_acceptance':'PENDING'}
M.write_once(OUT/'CONTROLS.json',report)
print(json.dumps({k:report[k] for k in ('domain','raw','unique','PASS','FAIL','native_RPC','native_CLI')}))
if report['FAIL']:raise SystemExit(1)
