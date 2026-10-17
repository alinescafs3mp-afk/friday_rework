from types import MethodType
from gateway.session_state import SessionState
from gateway.run_shutdown import GatewayShutdownMixin
from gateway.run_agent_cache import GatewayAgentCacheMixin
from gateway.slash_commands_session import GatewaySessionCommandsMixin

def own_runner(runner,source):
 state=SessionState()
 runner._get_executor=lambda:None
 runner._track_deferred_agent_worker=MethodType(GatewayShutdownMixin._track_deferred_agent_worker,runner)
 runner._state=state
 runner._session_state=lambda key:state
 runner._peek_session_state=lambda key:state
 runner._is_session_running=lambda key:state.turn.agent is not None
 runner._claim_active_session_slot=lambda key,src:(None,None)
 runner._persist_active_agents=lambda:None
 runner._session_web_pending=lambda key:False
 runner._restore_pending_one_turn_model_override=lambda key:None
 for name in ['_begin_session_run_generation','_current_session_run_generation','_is_session_run_current','_invalidate_session_run_generation','_release_running_agent_state','_drop_turn_slot','_interrupt_running_turn','_interrupt_and_clear_session']:
  setattr(runner,name,MethodType(getattr(GatewayAgentCacheMixin,name),runner))
 runner._complete_manual_compression=MethodType(GatewaySessionCommandsMixin._complete_manual_compression,runner)
 return runner
