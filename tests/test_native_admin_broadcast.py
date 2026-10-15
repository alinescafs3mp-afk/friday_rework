import builtins,sys,types
import pytest
from hermes_cli import free_tier_bootstrap as bootstrap

@pytest.mark.parametrize("partial",[False,True])
def test_no_initialized_consumer_never_imports_stdio(monkeypatch,partial):
    if partial:monkeypatch.setitem(sys.modules,"tui_gateway.server",types.ModuleType("tui_gateway.server"))
    else:monkeypatch.delitem(sys.modules,"tui_gateway.server",raising=False)
    original=builtins.__import__
    def forbidden(name,*args,**kwargs):
        if name=="tui_gateway.server":raise AssertionError("announcement attempted stdio import")
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,"__import__",forbidden)
    bootstrap._broadcast(bootstrap.SetupRecord(False,"",False,False,False))
    assert ("tui_gateway.server" in sys.modules)==partial


def test_existing_authorized_consumer_receives_exact_native_event(monkeypatch):
    events=[]
    server=types.ModuleType("tui_gateway.server")
    server._broadcast_global_event=lambda event,payload:events.append((event,payload))
    monkeypatch.setitem(sys.modules,"tui_gateway.server",server)
    record=bootstrap.SetupRecord(True,"OWN",False,False,True)
    bootstrap._broadcast(record)
    assert events==[(bootstrap.SETUP_READY_EVENT,record.as_payload())]


def test_broken_existing_consumer_does_not_break_bootstrap(monkeypatch):
    server=types.ModuleType("tui_gateway.server")
    def fail(*args):raise RuntimeError("OWN broken transport")
    server._broadcast_global_event=fail
    monkeypatch.setitem(sys.modules,"tui_gateway.server",server)
    bootstrap._broadcast(bootstrap.SetupRecord(False,"",False,False,False))
