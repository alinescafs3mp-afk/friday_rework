"""Pure regression checks for the portable excerpt; never opens a connection."""
import asyncio
import copy
import json
import time
import uuid
from pathlib import Path
from native_rpc_boundary import exact_confirmation,deadline_control,add_once

EVENT='synthetic-event';NOTICE='synthetic notice'
VALID={'queuedSubmission':{'id':str(uuid.uuid4()),'clientUserMessageId':EVENT,
                          'input':[{'type':'text','text':NOTICE}]}}
rows=[]
def record(name,passed,**evidence):rows.append(dict(name=name,passed=bool(passed),**evidence))
for name,change in [
 ('foreign_client',lambda q:q.update(clientUserMessageId='foreign')),
 ('foreign_notice',lambda q:q['input'][0].update(text='foreign')),
 ('foreign_field',lambda q:q['input'][0].update(unexpected=True)),
 ('foreign_elements',lambda q:q['input'][0].update(text_elements=['foreign'])),
 ('invalid_id',lambda q:q.update(id='not-a-uuid')),
 ('multiple_inputs',lambda q:q['input'].append(dict(q['input'][0]))),
]:
 value=copy.deepcopy(VALID);change(value['queuedSubmission'])
 try:exact_confirmation(value,EVENT,NOTICE)
 except ValueError:record(name,True)
 else:record(name,False)
record('exact_confirmation',exact_confirmation(copy.deepcopy(VALID),EVENT,NOTICE)['clientUserMessageId']==EVENT)
empty=copy.deepcopy(VALID);empty['queuedSubmission']['input'][0]['text_elements']=[]
record('empty_native_text_elements',exact_confirmation(empty,EVENT,NOTICE)==empty['queuedSubmission'])

class Transport:
 def __init__(self):self.aborts=0
 def abort(self):self.aborts+=1
class WS:
 def __init__(self):self.transport=Transport();self.notifications=[]
 async def send(self,value):self.notifications.append(json.loads(value))
class Connection:
 def __init__(self,slow_close):self.ws=WS();self.slow_close=slow_close;self.close_calls=0;self.close_cancelled=0
 async def __aenter__(self):return self.ws
 async def __aexit__(self,*args):
  self.close_calls+=1
  try:
   if self.slow_close:await asyncio.sleep(10)
  except asyncio.CancelledError:self.close_cancelled+=1;raise
class Base:
 def __init__(self,scenario):
  self.home='synthetic-home';self.thread='synthetic-thread';self.endpoint='synthetic-no-socket';self.scenario=scenario;self.sequence=0;self.adds=0
 async def call(self,method,params):
  self.sequence+=1
  if method=='initialize':return {'codexHome':self.home if self.scenario!='wrong-home' else 'foreign'}
  if method=='thread/queue/add':
   self.adds+=1
   if self.scenario=='send-uncertain':await asyncio.sleep(10)
   return copy.deepcopy(VALID)
  raise AssertionError('Unexpected simulated call')
 async def inspect(self):
  if self.scenario=='inspect-timeout':await asyncio.sleep(10)
  return {'status':{'type':'active' if self.scenario=='busy' else 'idle'},'queued_ids':[],'queue_has_more':False,'goal_status':None}

async def case(scenario,duration):
 connection=Connection(scenario in {'confirmed-close-timeout','inspect-timeout','send-uncertain'})
 def connect(*args,**kwargs):return connection
 Factory=deadline_control(Base,connect);control=Factory(scenario);reserved=[];confirmed=[]
 started=time.monotonic();deadline=started+duration;error=None
 try:await add_once(control,EVENT,NOTICE,deadline,reserved.append,lambda response,queued:confirmed.append(queued))
 except BaseException as exc:error=type(exc).__name__
 elapsed=time.monotonic()-started
 expected_add=scenario in {'ok','confirmed-close-timeout','send-uncertain'}
 valid=(control.deadline==deadline and elapsed<=duration+.04 and control.adds==int(expected_add))
 if scenario=='ok':valid=valid and error is None and len(confirmed)==1 and len(reserved)==1
 elif scenario in {'busy','wrong-home','no-mutation-clock'}:valid=valid and error=='RuntimeError' and not reserved and not confirmed
 elif scenario=='confirmed-close-timeout':valid=valid and error=='TimeoutError' and len(confirmed)==1 and len(reserved)==1 and connection.ws.transport.aborts==1
 else:valid=valid and error=='TimeoutError' and not confirmed and connection.ws.transport.aborts==1
 record(scenario,valid,elapsed_seconds=elapsed,absolute_deadline_seconds=duration,queue_calls=control.adds,reserved=len(reserved),confirmed=len(confirmed),owned_client_aborts=connection.ws.transport.aborts)
async def run():
 for scenario,duration in [('ok',20),('wrong-home',.05),('busy',20),('no-mutation-clock',.05),('inspect-timeout',.05),('confirmed-close-timeout',3.05),('send-uncertain',3.05)]:await case(scenario,duration)
asyncio.run(run())
result={'schema':'friday.portable-peer-boundary.controls.v1','pure_only':True,'native_network_queue_model_calls':0,'simulated_calls_are_not_native_evidence':True,'controls':rows,'passed':sum(x['passed'] for x in rows),'failed':sum(not x['passed'] for x in rows),'whole_private_procedure_or_release_acceptance':False}
Path('CONTROLS.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({'passed':result['passed'],'failed':result['failed'],'native_effects':0}))
raise SystemExit(0 if not result['failed'] else 1)
