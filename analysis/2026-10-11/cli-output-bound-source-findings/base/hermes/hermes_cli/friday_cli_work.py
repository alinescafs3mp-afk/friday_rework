"""Original authenticated classic CLI producers; no new scheduler or session store.

Local work is finite foreground only. The native async bridge drives the owned
PluginContext task ledger until settlement. Stdio/TUI and file-input ingress
are unsupported here and refuse before a work claim. Serialized facts never
reconstruct an admission capability or an output route.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import base64
import copy
import hashlib
import json
from pathlib import Path
import sqlite3

from hermes_cli import friday_user_scope as users
from hermes_cli.friday_cli_principal import current_cli

_TURN = ContextVar('friday_original_cli_turn', default=None)
_TOOL = ContextVar('friday_original_cli_tool', default=None)
_CONTROL = ContextVar('friday_original_cli_control', default=None)
CALL_FIELDS = ('task_id', 'session_id', 'turn_id', 'api_request_id', 'tool_call_id')
OWNER_FIELDS = {'schema', 'platform', 'session_id', 'profile', 'transport_profile',
                'account_id', 'user_id', 'os_uid', 'authority', 'home', 'ingress_message_id'}
INGRESS_FIELDS = {'schema', 'platform', 'session_id', 'runtime_profile',
                  'transport_profile', 'account_id', 'user_id', 'authority',
                  'runtime_home', 'input', 'route'}
ROUTE_FIELDS = {'schema', 'platform', 'session_id', 'runtime_profile',
                'transport_profile', 'account_id', 'user_id', 'authority', 'runtime_home', 'output'}


def is_cli():
    cap = users.current()
    return cap is not None and cap.principal[0] == 'cli'


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')


def validate_route(value):
    if (not isinstance(value, dict) or set(value) != ROUTE_FIELDS
            or value['schema'] != 'friday.cli-output-route.v1' or value['platform'] != 'cli'
            or value['output'] != 'original-classic-cli-stream'):
        raise users.ScopeDenied()
    for k in ('session_id','runtime_profile','transport_profile','account_id','user_id','runtime_home'):
        if not isinstance(value[k],str) or not value[k] or '\x00' in value[k] or len(value[k].encode()) > 2048:
            raise users.ScopeDenied()
    a=value['authority']
    if (not isinstance(a,dict) or set(a) != {'schema','uid','principal_id','generation','admission_sha256'}
            or a['schema'] != 'friday.cli-os-authority.v1' or type(a['uid']) is not int or a['uid'] < 0
            or type(a['generation']) is not int or a['generation'] < 1
            or not isinstance(a['principal_id'],str) or not a['principal_id']
            or not isinstance(a['admission_sha256'],str) or len(a['admission_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in a['admission_sha256'])):
        raise users.ScopeDenied()
    return copy.deepcopy(value)


def validate_ingress(value):
    if (not isinstance(value,dict) or set(value) != INGRESS_FIELDS
            or value['schema'] != 'friday.cli-ingress.v1' or value['platform'] != 'cli'):
        raise users.ScopeDenied()
    route=validate_route(value['route'])
    expected={k:value[k] for k in ('platform','session_id','runtime_profile','transport_profile','account_id','user_id','authority','runtime_home')}
    if any(route[k] != v for k,v in expected.items()): raise users.ScopeDenied()
    content=value['input']
    if (not isinstance(content,dict) or set(content) != {'native_message_id','sha256','size_bytes','attachments'}
            or type(content['native_message_id']) is not int or content['native_message_id'] < 1
            or type(content['size_bytes']) is not int or not 0 < content['size_bytes'] <= 65536
            or not isinstance(content['sha256'],str) or len(content['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in content['sha256'])
            or content['attachments'] != []):
        raise users.ScopeDenied()
    if len(_canonical(value)) > 65536: raise users.ScopeDenied()
    return copy.deepcopy(value)


def owner_from_receipt(value):
    value=validate_ingress(value)
    return {'schema':'friday.cli-owner.v1','platform':'cli','session_id':value['session_id'],
            'profile':value['runtime_profile'],'transport_profile':value['transport_profile'],
            'account_id':value['account_id'],'user_id':value['user_id'],
            'os_uid':value['authority']['uid'],'authority':copy.deepcopy(value['authority']),
            'home':value['runtime_home'],'ingress_message_id':value['input']['native_message_id']}


def validate_owner(value):
    if (not isinstance(value,dict) or set(value) != OWNER_FIELDS
            or value.get('schema') != 'friday.cli-owner.v1' or value.get('platform') != 'cli'
            or type(value['ingress_message_id']) is not int or value['ingress_message_id'] < 1
            or type(value['os_uid']) is not int or value['os_uid'] < 0):
        raise users.ScopeDenied()
    route={'schema':'friday.cli-output-route.v1','output':'original-classic-cli-stream',
           'platform':'cli','session_id':value['session_id'],'runtime_profile':value['profile'],
           'transport_profile':value['transport_profile'],'account_id':value['account_id'],
           'user_id':value['user_id'],'authority':value['authority'],'runtime_home':value['home']}
    validate_route(route)
    if value['os_uid'] != value['authority']['uid']: raise users.ScopeDenied()
    return copy.deepcopy(value)


def _session_query(cap,session_id,query,args=(),*,allow_new=False):
    path=cap.home/'state.db'; before=users._private(path)
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
    try:
        connection.execute('PRAGMA query_only=ON')
        row=connection.execute('SELECT source,user_id,profile_name,origin_json FROM sessions WHERE id=?',(session_id,)).fetchone()
        expected={'schema':'friday.account_origin.v1','platform':'cli',
                  'transport_profile':cap.principal[1],'account_id':cap.principal[2]}
        if row is None:
            # Native Hermes creates a first session only after building the
            # system prompt. Before that original producer starts, capture an
            # empty transcript boundary without inventing/adopting a session.
            if not allow_new or connection.execute('SELECT COUNT(*) FROM messages WHERE session_id=?',(session_id,)).fetchone()[0]:
                raise users.ScopeDenied()
        elif (row[:3] != ('cli',cap.principal[3],cap.profile)
                or json.loads(row[3] or '{}').get('friday_account_origin') != expected
                or json.loads(row[3] or '{}').get('friday_cli_authority') != cap.session_authority):
            raise users.ScopeDenied()
        result=connection.execute(query,args).fetchall()
        after=users._private(path)
        if (before.st_dev,before.st_ino) != (after.st_dev,after.st_ino): raise users.ScopeDenied()
        cap.check()
        return result
    except (sqlite3.Error,ValueError,TypeError):
        raise users.ScopeDenied() from None
    finally:
        connection.close()


def _check_lease(lease):
    from hermes_constants import get_hermes_home
    cap=current_cli(required=True)
    if (not isinstance(lease,dict) or not lease.get('active') or lease['cap'] is not cap
            or get_hermes_home() != cap.home or lease['home'] != cap.home):
        raise users.ScopeDenied()
    cli,agent=lease['cli'],lease['agent']
    if (getattr(cli,'_friday_cli_scope',None) is not cap or cli.agent is not agent
            or cli.session_id != lease['session_id'] or agent.session_id != lease['session_id']
            or getattr(agent,'platform',None) != 'cli' or getattr(agent,'_user_id',None) != cap.principal[3]
            or getattr(agent,'_session_db',None) is not lease['database']
            or Path(lease['database'].db_path) != cap.home/'state.db'
            or getattr(cli,'console',None) is not lease['console']
            or getattr(lease['console'],'file',None) is not lease['stream']):
        raise users.ScopeDenied()
    info=users._private(cap.home/'state.db')
    if (info.st_dev,info.st_ino) != lease['database_identity']: raise users.ScopeDenied()
    users.check_agent(agent)
    return cap


@contextmanager
def cli_turn(cli,message,*,received=None):
    if not is_cli():
        yield
        return
    cap=current_cli(required=True)
    if (not isinstance(received, CLIReceivedInput) or received.cap is not cap
            or received.cli is not cli or received.home != cap.home
            or received.session_id != cli.session_id or received.message != message
            or _TURN.get() is not None or type(message) is not str
            or not message.strip() or len(message.encode()) > 65536):
        raise users.ScopeDenied()  # no trusted file receive contract on this path
    agent=cli.agent; db=getattr(agent,'_session_db',None)
    from hermes_state import SessionDB
    if not isinstance(db,SessionDB) or Path(db.db_path) != cap.home/'state.db': raise users.ScopeDenied()
    console=getattr(cli,'console',None);stream=getattr(console,'file',None)
    if not callable(getattr(stream,'write',None)) or not callable(getattr(stream,'flush',None)):
        raise users.ScopeDenied()
    lease={'active':True,'cap':cap,'home':cap.home,'cli':cli,'agent':agent,'session_id':cli.session_id,
           'database':db,'console':console,'stream':stream,'message':message,'receipt':None}
    info=users._private(cap.home/'state.db');lease['database_identity']=(info.st_dev,info.st_ino)
    _check_lease(lease)
    rows=_session_query(cap,cli.session_id,'SELECT COALESCE(MAX(id),0) FROM messages WHERE session_id=?',(cli.session_id,),
                        allow_new=getattr(agent,'_session_db_created',True) is False)
    lease['before_message_id']=rows[0][0]
    token=_TURN.set(lease)
    try: yield
    finally:
        lease['active']=False
        _TURN.reset(token)


def current_turn():
    lease=_TURN.get();_check_lease(lease)
    return lease


def route_for(lease):
    cap=_check_lease(lease)
    return {'schema':'friday.cli-output-route.v1','platform':'cli','session_id':lease['session_id'],
            'runtime_profile':cap.profile,'transport_profile':cap.principal[1],
            'account_id':cap.principal[2],'user_id':cap.principal[3],
            'authority':cap.session_authority,'runtime_home':str(cap.home),
            'output':'original-classic-cli-stream'}


def ingress_for(lease):
    cap=_check_lease(lease)
    prior=lease['receipt']
    if prior is None:
        rows=_session_query(cap,lease['session_id'],
             "SELECT id,content FROM messages WHERE session_id=? AND role='user' AND id>? ORDER BY id LIMIT 2",
             (lease['session_id'],lease['before_message_id']))
        if len(rows)!=1 or rows[0][1] != lease['message']: raise users.ScopeDenied()
        raw=lease['message'].encode('utf-8')
        route=route_for(lease)
        prior={'schema':'friday.cli-ingress.v1',**{k:route[k] for k in ('platform','session_id','runtime_profile','transport_profile','account_id','user_id','authority','runtime_home')},
               'input':{'native_message_id':rows[0][0],'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'attachments':[]},'route':route}
        lease['receipt']=validate_ingress(prior)
    check_owner(owner_from_receipt(prior),prior)
    return copy.deepcopy(prior)


def check_owner(owner,ingress):
    cap=current_cli(required=True);lease=current_turn();value=validate_ingress(ingress)
    if validate_owner(owner) != owner_from_receipt(value) or value['route'] != route_for(lease): raise users.ScopeDenied()
    content=value['input']
    rows=_session_query(cap,value['session_id'],
          "SELECT role,content FROM messages WHERE id=? AND session_id=?",
          (content['native_message_id'],value['session_id']))
    if len(rows)!=1 or rows[0][0]!='user' or not isinstance(rows[0][1],str): raise users.ScopeDenied()
    raw=rows[0][1].encode('utf-8')
    if len(raw)!=content['size_bytes'] or hashlib.sha256(raw).hexdigest()!=content['sha256']: raise users.ScopeDenied()


@contextmanager
def native_cli_call(agent,task_id,tool_call_id,tool_name):
    if tool_name not in {'friday_work','friday_result'} or not is_cli():
        yield
        return
    outer=_TOOL.get()
    token=_TOOL.set(None)
    lease=None
    try:
        if outer is not None: raise users.ScopeDenied()
        turn=current_turn()
        if agent is not turn['agent'] or task_id != turn['session_id'] or not isinstance(tool_call_id,str) or not tool_call_id:
            raise users.ScopeDenied()
        ids={'task_id':task_id,'session_id':agent.session_id,'turn_id':getattr(agent,'_current_turn_id',None),
             'api_request_id':getattr(agent,'_current_api_request_id',None),'tool_call_id':tool_call_id}
        if any(not isinstance(v,str) or not v or '\x00' in v or len(v.encode())>512 for v in ids.values()): raise users.ScopeDenied()
        lease={'active':True,'turn':turn,'ids':ids};_TOOL.set(lease)
        yield
    finally:
        if lease is not None: lease['active']=False
        _TOOL.reset(token)


def admitted_call(context):
    lease=_TOOL.get();turn=current_turn()
    if (not isinstance(lease,dict) or not lease.get('active') or lease['turn'] is not turn
            or any(context.get(k) != lease['ids'][k] for k in CALL_FIELDS)
            or turn['agent']._current_turn_id != lease['ids']['turn_id']
            or turn['agent']._current_api_request_id != lease['ids']['api_request_id']):
        raise users.ScopeDenied()
    return ingress_for(turn),copy.deepcopy(lease['ids'])


def check_store(cap,state):
    if cap is None:
        if is_cli(): raise users.ScopeDenied()
        return
    if current_cli(required=True) is not cap or Path(state.data_dir) != cap.home/'plugin-data'/state._data_namespace or state._plugin_id != 'friday_rework':
        raise users.ScopeDenied()


def _require_context(context,route):
    turn=current_turn();cap=_check_lease(turn);manager=context._manager
    loaded=manager._plugins.get(context.plugin_id)
    if (context.plugin_id != 'friday_rework' or context._load_abandoned or getattr(manager,'_gateway_unloading',False)
            or loaded is None or not loaded.enabled or loaded.manifest is not context.manifest
            or Path(manager.home_path) != cap.home or manager._cli_ref is not turn['cli']
            or validate_route(route) != route_for(turn)):
        raise users.ScopeDenied()
    check_store(cap,context.state)
    return turn


def require_cli_foreground(context,route):
    import asyncio
    _require_context(context,route)
    if context.get_config('local_work') != {'enabled':True}: raise users.ScopeDenied()
    try: asyncio.get_running_loop()
    except RuntimeError: return
    raise users.ScopeDenied()  # refuse async/stdio paths and bridge's temporary-loop branch


def run_cli_foreground(context,coro,*,route,name=None):
    import asyncio
    from hermes_cli.plugins_gateway_work import _close_unstarted
    try: require_cli_foreground(context,route)
    except BaseException:
        _close_unstarted(coro)
        raise
    async def run():
        try:
            # Native unload/discovery uses this same lock. Registration happens
            # before yielding; unload can then cancel the exact native ledger task.
            with context._manager._discovery_lock:
                _require_context(context,route)
                if context.get_config('local_work') != {'enabled':True}: raise users.ScopeDenied()
                task=context.spawn_task(coro,name=name)
            result=await task
            _require_context(context,route)
            return result
        finally:
            _close_unstarted(coro)
    from model_tools import _run_async
    try:
        return _run_async(run())
    finally:
        _close_unstarted(coro)


def should_stop():
    turn=current_turn();agent=turn['agent'];hard=getattr(agent,'_hard_interrupt_requested',None)
    return bool(getattr(agent,'_interrupt_requested',False) or (hard is not None and hard.is_set()))


async def deliver_cli_document(context,*,route,data,file_name,caption=None,timeout=30):
    # Output is an exact, bounded ASCII JSON/base64 envelope on the retained
    # original native classic UI stream. A completed flush is output acceptance,
    # not a claim that a human has read it. No attachment/download API is invented.
    entered=False
    try:
        turn=_require_context(context,route)
        if (context.get_config('results') != {'enabled':True} or type(data) is not bytes or len(data)>256*1024
                or not isinstance(file_name,str) or not file_name or len(file_name.encode())>255
                or any(ord(c)<32 or c in '/\\' for c in file_name)):
            return {'state':'FAILED','error':'cli_document_preflight_rejected'}
        body={'schema':'friday.cli-document-output.v1','route':validate_route(route),
              'file_name':file_name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
              'encoding':'base64','data':base64.b64encode(data).decode('ascii'),'caption':caption}
        encoded=json.dumps(body,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n'
        _require_context(context,route)
        entered=True
        count=turn['stream'].write(encoded)
        turn['stream'].flush()
        _require_context(context,route)
        if count != len(encoded): return {'state':'UNKNOWN'}
        return {'state':'DELIVERED','kind':'local-output','route':validate_route(route),
                'file_name':file_name,'bytes':len(data),'sha256':body['sha256'],
                'native_output':'write-and-flush','human_read':'UNCONFIRMED'}
    except Exception:
        return {'state':'UNKNOWN'} if entered else {'state':'FAILED','error':'cli_document_preflight_rejected'}


PRINCIPAL_FIELDS = {'platform','session_id','profile','transport_profile','account_id',
                    'user_id','os_uid','authority','home'}


def principal_from_route(route):
    value=validate_route(route)
    return {'platform':'cli','session_id':value['session_id'],'profile':value['runtime_profile'],
            'transport_profile':value['transport_profile'],'account_id':value['account_id'],
            'user_id':value['user_id'],'os_uid':value['authority']['uid'],
            'authority':value['authority'],'home':value['runtime_home']}


def validate_principal(value):
    if not isinstance(value,dict) or set(value) != PRINCIPAL_FIELDS or value['platform']!='cli': raise users.ScopeDenied()
    route={'schema':'friday.cli-output-route.v1','output':'original-classic-cli-stream',
           'platform':'cli','session_id':value['session_id'],'runtime_profile':value['profile'],
           'transport_profile':value['transport_profile'],'account_id':value['account_id'],
           'user_id':value['user_id'],'authority':value['authority'],'runtime_home':value['home']}
    if principal_from_route(route) != value: raise users.ScopeDenied()
    return copy.deepcopy(value)


def require_local_command(cli,name):
    if not is_cli(): return
    from hermes_cli.plugins import _ensure_plugins_discovered
    cap=current_cli(required=True);manager=_ensure_plugins_discovered()
    entry=manager._plugin_commands.get(name)
    loaded=manager._plugins.get('friday_rework')
    if (name not in {'friday-stop','friday-pause','friday-status'}
            or Path(manager.home_path)!=cap.home or manager._cli_ref is not cli
            or getattr(cli,'_friday_cli_scope',None) is not cap
            or loaded is None or not loaded.enabled or entry is None
            or entry.get('plugin_key')!='friday_rework' or entry.get('gateway_control') is not False):
        raise users.ScopeDenied()


@contextmanager
def cli_command(cli,name):
    if not is_cli():
        yield
        return
    require_local_command(cli,name)
    cap=current_cli(required=True);agent=cli.agent;db=getattr(agent,'_session_db',None)
    from hermes_state import SessionDB
    if not isinstance(db,SessionDB) or Path(db.db_path)!=cap.home/'state.db': raise users.ScopeDenied()
    console=cli.console;stream=console.file
    lease={'active':True,'cap':cap,'home':cap.home,'cli':cli,'agent':agent,
           'session_id':cli.session_id,'database':db,'console':console,'stream':stream}
    info=users._private(cap.home/'state.db');lease['database_identity']=(info.st_dev,info.st_ino)
    _check_lease(lease)
    _session_query(cap,cli.session_id,'SELECT id FROM sessions WHERE id=?',(cli.session_id,))
    if _TURN.get() is not None or _CONTROL.get() is not None: raise users.ScopeDenied()
    control={'active':True,'turn':lease,'receipt':{'schema':'friday.cli-control.v1','command':name,'route':route_for(lease)}}
    tt=_TURN.set(lease);ct=_CONTROL.set(control)
    try: yield
    finally:
        control['active']=False;lease['active']=False
        _CONTROL.reset(ct);_TURN.reset(tt)


def get_cli_control(context):
    lease=_CONTROL.get()
    if lease is None or not lease['active']: return None
    _require_context(context,lease['receipt']['route'])
    if _TURN.get() is not lease['turn']: return None
    return copy.deepcopy(lease['receipt'])


def retain_local_owner(context,ingress):
    turn=_require_context(context,ingress['route'])
    check_owner(owner_from_receipt(ingress),ingress)
    return {'cap':turn['cap'],'cli':turn['cli'],'agent':turn['agent'],
            'database':turn['database'],'database_identity':turn['database_identity'],'console':turn['console'],'stream':turn['stream'],
            'context':context,'manager':context._manager,'manifest':context.manifest,'state':context.state,
            'route':copy.deepcopy(ingress['route'])}


def check_local_job(host,row):
    if row['owner'].get('platform') != 'cli': return
    original=host._local_owners.get(row['existing_task_id'])
    if original is None: raise users.ScopeDenied()  # cannot remint from a durable record on restart
    turn=current_turn();ingress=row['host']['binding']['ingress']
    if (host.ctx is not original['context'] or host.ctx._manager is not original['manager']
            or host.ctx.manifest is not original['manifest'] or host.ctx.state is not original['state']
            or any(turn[k] is not original[k] for k in ('cap','cli','agent','database','console','stream'))
            or turn['database_identity'] != original['database_identity']
            or ingress['route'] != original['route']):
        raise users.ScopeDenied()
    _require_context(host.ctx,original['route'])
    check_owner(row['owner'],ingress)


@dataclass(frozen=True)
class CLIReceivedInput:
    cap: object
    cli: object
    home: Path
    session_id: str
    message: str


def capture_cli_receive(cli,message,images=None):
    """Original native chat entry, before reference/image transformations.

    The opaque original capability is never part of a tool payload or persisted
    receipt. Unsupported receive types/attachments/reference expansion refuse;
    later admission also needs the original message in the real native DB.
    """
    if not is_cli(): return None
    cap=current_cli(required=True)
    if (getattr(cli,'_friday_cli_scope',None) is not cap or images not in (None,[])
            or type(message) is not str or not message.strip() or len(message.encode())>65536
            or not isinstance(cli.session_id,str) or not cli.session_id):
        raise users.ScopeDenied()
    from agent.context_references import parse_context_references
    if parse_context_references(message): raise users.ScopeDenied()
    return CLIReceivedInput(cap,cli,cap.home,cli.session_id,message)
