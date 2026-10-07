"""Actual native ASGI/auth/PTY route; synthetic bridge intercepts all process effects."""
import asyncio,copy,sys,json
from types import ModuleType
from pathlib import Path
import pytest
from test_admin_foundation import env

def test_retained_pty_must_refuse_next_input_when_product_admin_activates(env):
 from hermes_cli import web_server_chat as chat
 from hermes_cli.web_routers import chat_ws
 from hermes_cli.dashboard_auth.ws_tickets import mint_ticket
 from hermes_cli.friday_product_access import ProductDashboardBoundary,product_websocket_allowed
 original=copy.deepcopy(env.cfg['plugins']['entries']['friday_rework']['settings']['admin'])
 env.cfg['plugins']['entries']['friday_rework']['settings'].pop('admin');env.save()
 assert product_websocket_allowed()
 previous=sys.stdout
 try:
  from hermes_cli import web_server as web
 finally:sys.stdout=previous
 app=web.app;app.state.auth_required=True;app.state.bound_host='127.0.0.1'
 assert any(m.cls is ProductDashboardBoundary for m in app.user_middleware)
 observed={'writes':[],'closed':False,'spawn_intercepted':False,'sent':[],'receives':0}
 class Bridge:
  @classmethod
  def spawn(cls,*args,**kwargs):observed['spawn_intercepted']=True;return cls()
  def read(self,*args):return None
  async def write(self,raw):observed['writes'].append(raw.decode());return True
  def close(self):observed['closed']=True
  def resize(self,**kwargs):raise AssertionError('not requested')
 async def resolve(**kwargs):return ['SYNTHETIC-NOT-EXECUTED'],str(env.home),{}
 env.monkeypatch.setattr(chat,'PtyBridge',Bridge);env.monkeypatch.setattr(chat,'_PTY_BRIDGE_AVAILABLE',True);env.monkeypatch.setattr(chat,'_resolve_chat_argv_async',resolve)
 async def receive():
  observed['receives']+=1
  if observed['receives']==1:return {'type':'websocket.connect'}
  if observed['receives']==2:
   assert any(m['type']=='websocket.accept' for m in observed['sent'])
   env.cfg['plugins']['entries']['friday_rework']['settings']['admin']=original;env.save()
   assert not product_websocket_allowed()
   return {'type':'websocket.receive','bytes':b'POST_POLICY_INPUT'}
  return {'type':'websocket.disconnect','code':1000}
 async def send(message):observed['sent'].append(message)
 ticket=mint_ticket(user_id='owner',provider='basic',extra={'org_id':''})
 scope=dict(type='websocket',asgi={'version':'3.0'},path='/api/pty',root_path='',query_string=('ticket='+ticket).encode(),headers=[(b'host',b'127.0.0.1'),(b'origin',b'http://127.0.0.1')],scheme='ws',server=('127.0.0.1',80),client=('127.0.0.1',1))
 asyncio.run(app(scope,receive,send))
 observed['new_connection']=[]
 async def forbidden_receive():raise AssertionError('New product WS must not receive')
 async def new_send(message):observed['new_connection'].append(message)
 asyncio.run(app(scope,forbidden_receive,new_send))
 assert observed['new_connection']==[{'type':'websocket.close','code':1008,'reason':'product_websocket_surface_unaudited'}]
 (env.home / 'retained-pty-observation.json').write_text(json.dumps(observed,indent=2)+'\n')
 assert observed['closed']
 assert observed['writes']==[], 'Native PTY forwarded a new command after product admin policy was enabled'


@pytest.mark.parametrize("path", ["/api/pty", "/api/console", "/api/ws", "/api/events", "/api/display/ws", "/api/audio/speak-stream"])
@pytest.mark.parametrize("direction", ["receive", "send"])
def test_retained_frames_recheck_current_policy_and_unwind(env, path, direction):
 from hermes_cli.friday_product_access import ProductDashboardBoundary
 original=copy.deepcopy(env.cfg['plugins']['entries']['friday_rework']['settings']['admin'])
 env.cfg['plugins']['entries']['friday_rework']['settings'].pop('admin');env.save()
 sent=[];dispatched=[];cleaned=[]
 def activate():
  env.cfg['plugins']['entries']['friday_rework']['settings']['admin']=original;env.save()
 async def receive():
  activate()
  return {'type':'websocket.receive','text':'MUST_NOT_DISPATCH'}
 async def send(message):sent.append(message)
 async def native(scope,recv,emit):
  try:
   await emit({'type':'websocket.accept'})
   if direction=='receive':
    frame=await recv()
    if frame['type']=='websocket.receive':dispatched.append(frame)
   else:
    activate()
    await emit({'type':'websocket.send','text':'MUST_NOT_LEAK'})
  finally:cleaned.append(True)
 asyncio.run(ProductDashboardBoundary(native)({'type':'websocket','path':path},receive,send))
 assert sent==[{'type':'websocket.accept'},{'type':'websocket.close','code':1008,'reason':'product_websocket_surface_unaudited'}]
 assert dispatched==[] and cleaned==[True]


def test_retained_revocation_cannot_reopen_during_pending_receive(env):
 from hermes_cli.friday_product_access import ProductDashboardBoundary
 from starlette.websockets import WebSocketDisconnect
 original=copy.deepcopy(env.cfg['plugins']['entries']['friday_rework']['settings']['admin'])
 settings=env.cfg['plugins']['entries']['friday_rework']['settings']
 settings.pop('admin');env.save()
 sent=[];frames=[];shared={}
 async def receive():
  settings['admin']=original;env.save()
  with pytest.raises(WebSocketDisconnect):
   await shared['send']({'type':'websocket.send','text':'REVOKED_OUTPUT'})
  settings.pop('admin');env.save()
  return {'type':'websocket.receive','text':'MUST_NOT_REVIVE'}
 async def send(message):sent.append(message)
 async def native(scope,recv,emit):
  shared['send']=emit
  await emit({'type':'websocket.accept'})
  frames.append(await recv())
  await emit({'type':'websocket.close','code':1000})
 asyncio.run(ProductDashboardBoundary(native)({'type':'websocket','path':'/api/pty'},receive,send))
 assert frames==[{'type':'websocket.disconnect','code':1008}]
 assert sent==[{'type':'websocket.accept'},{'type':'websocket.close','code':1008,'reason':'product_websocket_surface_unaudited'}]
