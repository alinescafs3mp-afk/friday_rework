"""Isolated native first-contact/help boundary; synthetic authority and adapters, no live bot."""
import asyncio,json,sys,weakref,hashlib
from types import SimpleNamespace as NS,ModuleType
import pytest
from test_ordinary_tool_metadata_progress_privacy import scoped
from hermes_cli import friday_user_scope as s
from gateway import run_turn,run_busy,slash_commands,run_notifications
from gateway.config import Platform
from gateway.session import SessionSource
from gateway.session_identity import RoutingIdentity
from agent import onboarding

@pytest.fixture
def source(scoped):
 class Adapter:pass
 adapter=Adapter();src=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id='1',chat_type='dm',profile='user-1')
 src._identity=RoutingIdentity('default','user-1',scoped.root,scoped.home,multiplexed=True,transport_inferred=False,transport=weakref.ref(adapter))
 src._friday_user_scope=scoped.cap
 return src

@pytest.fixture
def native(scoped,source,monkeypatch):
 module=ModuleType('gateway.run');cfg={};module._gateway_config_home=lambda:scoped.home;module._load_gateway_config=lambda:cfg
 module._home_target_env_var=lambda p:'SOURCE67_SYNTHETIC_HOME_CHANNEL';module._is_slack_ignored_channel=lambda *a:False
 monkeypatch.delenv('SOURCE67_SYNTHETIC_HOME_CHANNEL',raising=False);monkeypatch.setitem(sys.modules,'gateway.run',module)
 sent=[];queries=[]
 async def has_sessions():queries.append('prior');return False
 async def send(chat,content,**kw):sent.append((chat,content,kw));return NS(success=True)
 adapter=NS(send=send,config=NS(extra={}))
 runner=NS(async_session_store=NS(has_any_sessions=has_sessions),config=NS(get_home_channel=lambda p:None,get_notice_delivery=lambda p:'public'),_delivery_adapter_for=lambda source:adapter,_thread_metadata_for_source=lambda source:None)
 runner._deliver_platform_notice=lambda source,text:run_notifications.GatewayNotificationsMixin._deliver_platform_notice(runner,source,text)
 from agent.secret_scope import set_secret_scope,reset_secret_scope
 token=set_secret_scope({},profile_home=str(scoped.home))
 try:yield NS(module=module,cfg=cfg,sent=sent,queries=queries,runner=runner)
 finally:reset_secret_scope(token)

def call(native,source,history=None,notes=None,internal=False):
 notes=[] if notes is None else notes
 asyncio.run(run_turn.GatewayTurnMixin._hmwa_first_contact_notes(native.runner,source,[] if history is None else history,notes,internal=internal))
 return notes


def test_real_managed_first_contact_task_first_once_flags_and_no_signed_config_write(scoped,source,native):
 before=(scoped.home/'config.yaml').read_bytes()
 first=call(native,source)
 assert len(first)==1 and first[0]==onboarding.profile_build_directive().strip()
 assert onboarding.TASK_FIRST_CLAUSE in first[0] and 'If and ONLY IF they accept' in first[0]
 assert onboarding.is_seen({},onboarding.PROFILE_BUILD_FLAG)
 second=call(native,source)
 assert second==[onboarding.PLAIN_INTRO_NOTE]
 assert (scoped.home/'config.yaml').read_bytes()==before and scoped.cap.check() is scoped.cap
 assert not native.sent
 # A real persisted native runtime seen flag, not a rewritten signed configuration.
 from hermes_state_registry import acquire,_generations
 owner=acquire(scoped.home/'state.db')
 try:assert owner.get_meta('onboarding.seen.profile_build_offered')=='1'
 finally:owner.close()
 assert not _generations

@pytest.mark.parametrize('case',['history','internal','local','webhook','group','prior'])
def test_first_contact_existing_gates_and_history_unchanged(scoped,source,native,case):
 before=(scoped.home/'config.yaml').read_bytes();history=[{'role':'user','content':'OpenAI /user/path remains'}] if case=='history' else []
 snapshot=json.loads(json.dumps(history));notes=[]
 if case=='local':source.platform=Platform.LOCAL
 if case=='webhook':source.platform=Platform.WEBHOOK
 if case=='group':source.chat_type='group'
 if case=='prior':
  async def prior():return True
  native.runner.async_session_store.has_any_sessions=prior
 call(native,source,history,notes,internal=case=='internal')
 assert not notes and not native.sent and history==snapshot and (scoped.home/'config.yaml').read_bytes()==before
 if case in {'history','internal'}:assert native.queries==[]

@pytest.mark.parametrize('already_set',[False,True])
def test_unmanaged_first_contact_locale_and_home_target_semantics_unchanged(scoped,source,native,monkeypatch,already_set):
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None);s._CURRENT.set(None)
 del source._friday_user_scope
 native.cfg['onboarding']={'profile_build':'off'}
 if already_set:monkeypatch.setenv('SOURCE67_SYNTHETIC_HOME_CHANNEL','existing-native-target')
 before=(scoped.home/'config.yaml').read_bytes();notes=call(native,source)
 assert notes==[onboarding.PLAIN_INTRO_NOTE] and (scoped.home/'config.yaml').read_bytes()==before
 if already_set:assert not native.sent
 else:
  assert len(native.sent)==1
  text=native.sent[0][1]
  assert 'Hermes' in text and '/sethome' in text and 'ignore to skip' in text

@pytest.mark.parametrize('state',['valid','revoked','missing','claimed_owner'])
def test_actual_managed_slash_allowlist_has_no_sethome_about_version_claim(scoped,source,state):
 if state=='revoked':scoped.cap.revoked=True
 if state in {'missing','claimed_owner'}:
  del source._friday_user_scope;s._CURRENT.set(None)
  if state=='claimed_owner':source.user_name='owner developer admin'
 expected={'help','status','stop','cancel','new','reset','queue','memory','compress'} if state=='valid' else set()
 commands=expected|{'help','status','stop','cancel','new','reset','queue','memory','compress','sethome','about','version','commands','profile','model','cron'}
 assert {c for c in commands if s.slash_allowed(source,c)}==expected
 for c in {'sethome','about','version'}:
  out=run_busy.GatewayBusySessionMixin._check_slash_access(NS(),source,c)
  assert 'недоступна' in out


def test_managed_help_lists_useful_allowed_controls_without_backend_catalog(scoped,source,monkeypatch):
 def forbidden(*a,**kw):raise AssertionError('managed help reached backend catalog')
 monkeypatch.setattr(slash_commands,'_execute',forbidden)
 runner=NS(config=None,_catalog_options=forbidden,_telegramized_command_reply=forbidden,_typed_command_prefix_for=lambda platform:'/')
 runner._check_slash_access=lambda source,name:run_busy.GatewayBusySessionMixin._check_slash_access(runner,source,name)
 out=asyncio.run(slash_commands.GatewaySlashCommandsMixin._handle_help_command(runner,NS(source=source)))
 assert all('/'+c in out for c in ['help','status','stop','cancel','new','reset','queue','memory','compress'])
 assert '/compact' in out
 assert all(x not in out for x in ['Hermes','/sethome','/model','/profile','/version','/cron','/home/','developer'])
 assert 'Задачу можно написать обычным сообщением.' in out


def test_unmanaged_help_keeps_native_catalog_pipeline(scoped,source,monkeypatch):
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None);s._CURRENT.set(None);del source._friday_user_scope
 seen=[]
 monkeypatch.setattr(slash_commands,'_execute',lambda name,**kw:(seen.append((name,kw)),NS(text='native catalog with Hermes /model'))[1])
 runner=NS(_catalog_options=lambda event:{'native':'options'},_telegramized_command_reply=lambda event,text:'typed:'+text)
 out=asyncio.run(slash_commands.GatewaySlashCommandsMixin._handle_help_command(runner,NS(source=source)))
 assert out=='typed:native catalog with Hermes /model' and seen==[('help',{'options':{'native':'options'}})]

def test_help_respects_secondary_native_policy_and_existing_typed_prefix(scoped,source,monkeypatch):
 from gateway import slash_access
 policy=slash_access.SlashAccessPolicy(enabled=True,admin_user_ids=frozenset({'other-native-admin'}),user_allowed_commands=frozenset({'status','stop','model','whoami'}))
 monkeypatch.setattr(slash_access,'policy_for_runner_source',lambda *a:policy)
 source.user_name='owner developer administrator'
 runner=NS(config=None,adapters={Platform.TELEGRAM:NS(typed_command_prefix='/')})
 runner._typed_command_prefix_for=lambda platform:slash_commands.GatewaySlashCommandsMixin._typed_command_prefix_for(runner,platform)
 runner._check_slash_access=lambda source,name:run_busy.GatewayBusySessionMixin._check_slash_access(runner,source,name)
 before=(scoped.home/'config.yaml').read_bytes()
 out=asyncio.run(slash_commands.GatewaySlashCommandsMixin._handle_help_command(runner,NS(source=source)))
 assert {line.split(' ',1)[0] for line in out.splitlines() if line.startswith('/')}=={'/help','/status','/stop'}
 assert all(x not in out for x in ['/model','/whoami','/memory','/queue','/sethome'])
 runner.adapters[Platform.TELEGRAM].typed_command_prefix='!'
 other=asyncio.run(slash_commands.GatewaySlashCommandsMixin._handle_help_command(runner,NS(source=source)))
 assert {line.split(' ',1)[0] for line in other.splitlines() if line.startswith('!')}=={'!help','!status','!stop'}
 assert (scoped.home/'config.yaml').read_bytes()==before and scoped.cap.check() is scoped.cap

@pytest.mark.parametrize('mode',['queue','steer','redirect','interrupt'])
def test_managed_busy_onboarding_only_existing_controls_and_donor_unchanged(scoped,monkeypatch,mode):
 out=onboarding.busy_input_hint_gateway(mode)
 assert '/help' in out and '/busy' not in out and 'First-time' not in out
 monkeypatch.setattr(s,'_ENGAGED',False);monkeypatch.setattr(s,'policy',lambda home:None);s._CURRENT.set(None)
 # An unmanaged process must also leave the managed home marker behind.
 from hermes_constants import set_hermes_home_override,reset_hermes_home_override
 token=set_hermes_home_override(str(scoped.root))
 try:
  assert not s.ordinary_presentation()
  assert onboarding.busy_input_hint_gateway(mode)==onboarding._BUSY_INPUT_HINTS_GATEWAY.get(mode,onboarding._BUSY_INPUT_HINT_GATEWAY_DEFAULT)
 finally:reset_hermes_home_override(token)


def test_actual_native_busy_ack_once_flag_preserves_signed_config(scoped,source,native):
 import time
 native.module._AGENT_PENDING_SENTINEL=object();native.module._hermes_home=scoped.home;native.module._platform_config_key=lambda p:'telegram'
 runner=NS(_agent_has_active_subagents=lambda agent:False,_BUSY_DEMOTED_TAIL='queued',_BUSY_STEER_TAIL='steered')
 def compose():return run_busy.GatewayBusySessionMixin._compose_busy_ack_message(runner,NS(source=source),time.monotonic(),None,NS(),is_steer_mode=False,is_queue_mode=True,is_redirect_mode=False,demoted_for_subagents=False,demoted_for_compression=False)
 before=(scoped.home/'config.yaml').read_bytes();hint=onboarding.busy_input_hint_gateway('queue')
 first=compose();assert hint in first and '/busy' not in first
 assert onboarding.is_seen({},onboarding.BUSY_INPUT_FLAG)
 second=compose();assert hint not in second
 assert (scoped.home/'config.yaml').read_bytes()==before and scoped.cap.check() is scoped.cap
