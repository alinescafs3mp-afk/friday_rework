import asyncio,contextlib,subprocess,sys,types
from pathlib import Path
import pytest
from hermes_cli import friday_dashboard_owner as owner,gateway,web_server as web
from gateway import host_rendezvous as hr
from hermes_cli import friday_product_access as access

@pytest.mark.parametrize('fault',['none','missing_owner','no_lock','source','auth','host','port'])
def test_startup_identity_fails_closed(monkeypatch,fault):
 boot={'host':'127.0.0.1','port':9119,'source':{'receipt':'a'},'operator':{'provider':'basic','user_id':'operator','org_id':''}}
 monkeypatch.setattr(access,'operator_allowed',lambda identity:identity==boot['operator'])
 app=types.SimpleNamespace(state=types.SimpleNamespace(friday_dashboard_owner=boot,auth_required=True,bound_host=boot['host']))
 monkeypatch.setattr(owner,'enabled',lambda:True)
 monkeypatch.setattr(hr,'owns_host_lock',lambda role:fault!='no_lock' and role==hr.ROLE_SERVE)
 def expected(**kw):
  assert kw['registered'] is True
  if fault=='auth':raise ValueError('actual authentication validation failed')
  assert kw['auth_required'] is True and kw['host']=='127.0.0.1' and kw['port']==9119
  return boot if fault=='none' else {**boot,'source':{'receipt':'drift'}}
 monkeypatch.setattr(owner,'expected',expected)
 if fault=='missing_owner':app.state.friday_dashboard_owner=None
 if fault=='host':app.state.bound_host='foreign'
 if fault=='port':boot['port']=9220
 if fault=='none':assert owner.startup_identity(app) is boot
 else:
  with pytest.raises((ValueError,AssertionError)):owner.startup_identity(app)

@pytest.mark.parametrize('outcome',['deny','error'])
def test_startup_identity_refuses_current_operator(monkeypatch,outcome):
 boot={'host':'127.0.0.1','port':9119,'operator':{'provider':'basic','user_id':'operator','org_id':''}}
 app=types.SimpleNamespace(state=types.SimpleNamespace(friday_dashboard_owner=boot,auth_required=True,bound_host=boot['host']))
 monkeypatch.setattr(owner,'enabled',lambda:True)
 monkeypatch.setattr(hr,'owns_host_lock',lambda role:role==hr.ROLE_SERVE)
 monkeypatch.setattr(owner,'expected',lambda **kw:boot)
 calls=[]
 def current_policy(identity):
  calls.append(identity)
  if outcome=='error':raise RuntimeError('current policy unavailable')
  return False
 monkeypatch.setattr(access,'operator_allowed',current_policy)
 with pytest.raises(RuntimeError if outcome=='error' else ValueError):owner.startup_identity(app)
 assert calls==[boot['operator']]

def test_legacy_startup_identity(monkeypatch):
 monkeypatch.setattr(owner,'enabled',lambda:False)
 assert owner.startup_identity(types.SimpleNamespace(state=types.SimpleNamespace())) is None

@pytest.mark.parametrize('system',[False,True])
@pytest.mark.parametrize('outcome',['success45','failure','timeout','preamble','refresh'])
def test_systemd_start_single_operation_preserves_failures(monkeypatch,capsys,system,outcome):
 events=[]
 def preamble(*a,**kw):
  events.append('preamble')
  if outcome=='preamble':raise ValueError('preamble refused')
  return system
 def refresh(**kw):
  events.append('refresh')
  if outcome=='refresh':raise ValueError('refresh refused')
 def run(args,**kw):
  events.append('start');assert args==['start','own.service'] and kw=={'system':system,'check':True,'timeout':120}
  if outcome=='failure':raise subprocess.CalledProcessError(1,args)
  if outcome=='timeout':raise subprocess.TimeoutExpired(args,120)
  # Model a notify ready event after45s without any wait/process/service effect.
  assert kw['timeout']>45
 monkeypatch.setattr(gateway,'_systemd_scope_preamble',preamble)
 monkeypatch.setattr(gateway,'refresh_systemd_unit_if_needed',refresh)
 monkeypatch.setattr(gateway,'get_service_name',lambda:'own.service')
 monkeypatch.setattr(gateway,'_run_systemctl',run)
 if outcome=='success45':gateway.systemd_start(system);assert 'service started' in capsys.readouterr().out
 else:
  with pytest.raises((ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired)):gateway.systemd_start(system)
  assert 'service started' not in capsys.readouterr().out
 assert events.count('start')==(0 if outcome in {'preamble','refresh'} else 1)

@pytest.mark.parametrize('administrative',[False,True])
def test_lifespan_keeps_legacy_hosted_rooms_and_cleans_own_services(monkeypatch,administrative):
 events=[]
 async def idle(*a):await asyncio.sleep(3600)
 monkeypatch.setattr(owner,'startup_identity',lambda app:{} if administrative else None)
 monkeypatch.setattr(web,'_warm_gateway_module',lambda:None)
 monkeypatch.setattr(web,'_eager_reconcile_own_session_db',lambda:None)
 monkeypatch.setattr(web,'run_reaper',idle)
 monkeypatch.setattr(web,'_dashboard_selftest_loop',idle)
 async def archive():
  events.append('archive');await asyncio.sleep(3600)
 monkeypatch.setattr(web,'_auto_archive_ticker_loop',archive)
 monkeypatch.setattr(web,'is_desktop_owned_backend',lambda:False)
 monkeypatch.setattr(web,'_terminate_desktop_managed_gateway',lambda:events.append('bad_desktop'))
 import hermes_cli.local_runtime.bootstrap as runtime
 import hermes_cli.free_tier_bootstrap as bootstrap
 monkeypatch.setattr(runtime,'ensure_local_runtime',lambda c:None)
 monkeypatch.setattr(runtime,'shutdown_local_runtime',lambda:events.append('runtime_stop'))
 monkeypatch.setattr(bootstrap,'start_background_bootstrap',lambda:None)
 fake=types.ModuleType('tui_gateway.server');fake.install_tui_message_injector=lambda:events.append('inject');fake.clear_tui_message_injector=lambda:events.append('clear')
 from tui_gateway import methods_groups
 monkeypatch.setitem(sys.modules,'tui_gateway.server',fake)
 import tui_gateway
 monkeypatch.setattr(tui_gateway,'server',fake,raising=False)
 monkeypatch.setattr(methods_groups,'start_hosted_room_service',lambda:events.append('rooms_start'))
 monkeypatch.setattr(methods_groups,'stop_hosted_room_service',lambda **kw:events.append('rooms_stop'))
 async def run():
  async with web._lifespan(web.app):
   assert web.app.state.event_channels=={}
   await asyncio.sleep(0)
 asyncio.run(run())
 assert 'runtime_stop' in events
 assert ('archive' in events)==(not administrative)
 assert ('inject' in events)==(not administrative)
 assert ('clear' in events)==(not administrative)
 assert ('rooms_start' in events)==(not administrative)
 assert ('rooms_stop' in events)==(not administrative)
