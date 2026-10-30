"""Source-only actual module/protocol tests; all provider/process seams synthetic."""
import asyncio
import contextlib
import importlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
BASE=Path(os.environ['FRIDAY_WEB_BASE_SOURCE'])
PKG=Path(os.environ['FRIDAY_WEB_CANDIDATE_SOURCE'])
sys.dont_write_bytecode=True
sys.path.insert(0,str(BASE))
for name in ('agent','tools','plugins','plugins.web'):
    package=types.ModuleType(name)
    package.__path__=[str(PKG/Path(*name.split('.'))),str(BASE/Path(*name.split('.')))]
    sys.modules[name]=package

def audit(event,args):
    # asyncio needs its in-process AF_UNIX wakeup socketpair; all socket connects
    # and Internet sockets remain forbidden, including provider/DNS accidents.
    if (event=='socket.__new__' and args[1] != 1) or event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system','os.exec','os.posix_spawn'):
        raise AssertionError('forbidden_effect:'+event)
    if event=='open':
        path,mode,flags=args
        writing=bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if writing and isinstance(path,(str,bytes,os.PathLike)):
            resolved=Path(os.fsdecode(path)).resolve()
            if resolved!=Path(os.devnull) and not resolved.is_relative_to(ROOT):
                raise AssertionError('write_outside_own_output')
sys.addaudithook(audit)

from agent import web_call_context as ctx
from plugins.web import keyless_mcp as keyless
from plugins.web import keyless_mcp_bounded as bounded
from tools import web_process as parent
from tools import web_process_child as child
import requests

SECRET='W03_SYNTHETIC_USER_SECRET_472019'
class Response:
    def __init__(self,status=200,text='source contents'):
        self.status_code=status
        self.headers={'Content-Encoding':'identity'}
        self.body=json.dumps({'jsonrpc':'2.0','id':1,'result':{'content':[{'type':'text','text':text}]}}).encode()
        self.raw=types.SimpleNamespace(_fp=types.SimpleNamespace(fp=types.SimpleNamespace(raw=types.SimpleNamespace(_sock=types.SimpleNamespace(settimeout=lambda s:None)))),read1=self.read)
    def read(self,size):
        value=self.body[:size];self.body=self.body[size:];return value
    def __enter__(self):return self
    def __exit__(self,*a):pass
class Session:
    response=Response
    error=None
    calls=0
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def post(self,*a,**kw):
        Session.calls+=1
        if Session.error is not None:raise Session.error
        return Session.response()

def fake(name,**kw):
    result=types.ModuleType(name);result.__dict__.update(kw);return result

class Diagnostics(unittest.TestCase):
    def setUp(self):
        ctx.begin_child_web_diagnostics();ctx.child_deadline(time.monotonic()+60)
        Session.calls=0;Session.error=None;Session.response=Response
        self.requests=patch.object(requests,'Session',Session);self.requests.start()
    def tearDown(self):self.requests.stop()
    def test_disabled_outside_child_and_reset(self):
        token=ctx._child_diagnostics.set(None)
        try:
            keyless.KeylessMCPError('keyless result refused')
            self.assertEqual(ctx.child_web_diagnostics(),[])
        finally:ctx._child_diagnostics.reset(token)
        keyless.KeylessMCPError('keyless result refused')
        self.assertTrue(ctx.child_web_diagnostics())
        ctx.begin_child_web_diagnostics();self.assertEqual(ctx.child_web_diagnostics(),[])
    def test_exact_fixed_code_only_and_original_exception_args_preserved(self):
        for args in ((),(SECRET,),({'message':SECRET},),('keyless timeout',SECRET)):
            e=keyless.KeylessMCPError(*args);self.assertEqual(e.args,args)
        records=ctx.child_web_diagnostics()
        self.assertNotIn(SECRET,json.dumps(records));self.assertTrue(all('code' not in x for x in records))
        keyless.KeylessMCPError('keyless result refused')
        self.assertEqual(ctx.child_web_diagnostics()[-1]['code'],'keyless result refused')
    def test_context_propagation_to_extract_thread_does_not_reset_deadline(self):
        original=ctx._child_deadline.get()
        async def run():await asyncio.to_thread(keyless.KeylessMCPError,'keyless text bound')
        asyncio.run(run())
        self.assertEqual(ctx._child_deadline.get(),original)
        self.assertEqual(ctx.child_web_diagnostics()[0]['code'],'keyless text bound')
    def test_exception_class_other_never_custom_class_name(self):
        special=type(SECRET,(Exception,),{})
        ctx.record_child_web_diagnostic('keyless_text',exception=special(SECRET),code=SECRET,http_status=SECRET)
        self.assertEqual(ctx.child_web_diagnostics(),[{'phase':'keyless_text','exception':'other'}])
    def test_bounded_deduplicated_metadata(self):
        for status in range(400,420):
            for repeat in range(2):ctx.record_child_web_diagnostic('keyless_response',http_status=status)
        self.assertEqual(len(ctx.child_web_diagnostics()),8)
        self.assertEqual([r['http_status'] for r in ctx.child_web_diagnostics()],list(range(400,408)))
        ctx.validate_child_web_diagnostics(ctx.child_web_diagnostics())
    def test_strict_private_protocol_no_arbitrary_messages(self):
        bad=(None,{},[{}],[{'phase':SECRET}],[{'phase':[]}],[{'phase':'keyless_text','message':SECRET}],
             [{'phase':'keyless_text','exception':SECRET}],[{'phase':'keyless_text','exception':{}}],
             [{'phase':'keyless_text','code':[SECRET]}],[{'phase':'keyless_text','http_status':True}],
             [{'phase':'keyless_text','http_status':999}], [{'phase':'keyless_text'}]*9)
        for value in bad:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(RuntimeError):ctx.validate_child_web_diagnostics(value)
    def test_actual_provider_status_is_private_and_not_source_status(self):
        for status in (404,410,401,403,503):
            with self.subTest(status=status):
                ctx.begin_child_web_diagnostics();Session.response=lambda:Response(status)
                rows=keyless.exa_extract_keyless(['https://fixture.example/page'])
                self.assertIn('keyless provider unavailable',rows[0]['error'])
                records=ctx.child_web_diagnostics()
                self.assertEqual(records[0],{'phase':'keyless_response','http_status':status})
                self.assertEqual(records[1]['code'],'keyless provider unavailable')
                self.assertNotIn('retry_allowed',json.dumps(records))
    def test_actual_transport_exception_retains_class_without_message(self):
        Session.error=requests.exceptions.ReadTimeout(SECRET)
        rows=keyless.exa_extract_keyless(['https://fixture.example/page'])
        records=ctx.child_web_diagnostics()
        self.assertIn({'phase':'keyless_request','exception':'requests.exceptions.ReadTimeout'},records)
        self.assertNotIn(SECRET,json.dumps(records));self.assertNotIn(SECRET,json.dumps(rows))
    def test_actual_text_handler_exception_preserved_without_message(self):
        def broken(text,deadline):raise ValueError(SECRET)
        with self.assertRaisesRegex(keyless.KeylessMCPError,'keyless text bound'):
            bounded.read_response(Response(),time.monotonic()+10,keyless.KeylessMCPError,text_handler=broken)
        self.assertEqual(ctx.child_web_diagnostics()[0],{'phase':'keyless_text','exception':'builtins.ValueError'})
        self.assertNotIn(SECRET,json.dumps(ctx.child_web_diagnostics()))
    def test_remote_tool_error_cannot_enter_diagnostics(self):
        response=Response();response.body=json.dumps({'jsonrpc':'2.0','id':1,'result':{'isError':True,'content':[{'type':'text','text':SECRET}]}}).encode()
        with self.assertRaisesRegex(keyless.KeylessMCPError,'keyless result refused'):
            bounded.read_response(response,time.monotonic()+10,keyless.KeylessMCPError)
        self.assertEqual(ctx.child_web_diagnostics()[0]['code'],'keyless result refused')
        self.assertNotIn(SECRET,json.dumps(ctx.child_web_diagnostics()))
    def test_success_content_unchanged_no_diagnostic(self):
        result=bounded.read_response(Response(text='source '+SECRET),time.monotonic()+10,keyless.KeylessMCPError)
        self.assertEqual(result,'source '+SECRET);self.assertEqual(ctx.child_web_diagnostics(),[])
    def test_url_refusal_and_expired_clock_never_reach_transport(self):
        rows=keyless.exa_extract_keyless(['https://127.0.0.1/private'])
        self.assertIn('keyless IP URL refused',rows[0]['error']);self.assertEqual(Session.calls,0)
        with self.assertRaises(TimeoutError):ctx.child_deadline(time.monotonic()-1)
        with self.assertRaises(TimeoutError):keyless.exa_extract_keyless(['https://fixture.example/page'])
        self.assertEqual(Session.calls,0)

class Protocol(unittest.TestCase):
    def setUp(self):
        self.home=ROOT/'sandbox/home';self.home.mkdir(parents=True,exist_ok=True)
        self.turn=ctx.WebTurn();self.call=ctx.WebCall(self.turn,time.monotonic()+60,'task','session','call')
        self.call.user_authority=None
        self.session=types.SimpleNamespace(id='synthetic-process',web_deadline=self.call.deadline())
        self.spawn_count=0;self.cleanup='QUIESCENT';self.exit_zero=True;self.packet={}
        self.registry=types.SimpleNamespace(spawn_web=self.spawn,web_exchange=lambda *a:json.dumps(self.packet),settle_web=self.settle)
        self.memo=types.SimpleNamespace(export_query=lambda *a:[],import_query=lambda *a:None,flight_lock=lambda *a:__import__('threading').Lock())
        self.users=fake('hermes_cli.friday_user_scope',current=lambda:None,ordinary_presentation=lambda:True,delegation_authority=lambda:None,ScopeDenied=type('ScopeDenied',(Exception,),{}))
        self.modules={'hermes_cli.friday_user_scope':self.users,'hermes_constants':fake('hermes_constants',get_hermes_home=lambda:self.home),
                      'tools.process_registry':fake('tools.process_registry',process_registry=self.registry),
                      'tools.web_result_cache':fake('tools.web_result_cache',search_memo=self.memo),
                      'tools.interrupt':fake('tools.interrupt',is_interrupted=lambda:False),
                      'agent.redact':fake('agent.redact',redact_sensitive_text=lambda text,**kw:text)}
        self.patch=patch.dict(sys.modules,self.modules);self.patch.start()
        self.scope=patch.object(parent,'_scope_payload',lambda home:{});self.scope.start()
    def tearDown(self):self.scope.stop();self.patch.stop()
    def spawn(self,call):self.spawn_count+=1;call.session=self.session;call.registry=self.registry;return self.session
    def settle(self,*args,**kw):return {'status':self.cleanup,'native_child_exit_zero':self.exit_zero}
    def run_parent(self):
        with ctx.bind_web_call(self.call):return parent.run_web('web_extract',{'urls':['https://fixture.example/page']},task_id='task',session_id='session')
    def test_new_private_lane_never_changes_public_failure_or_unblocks_turn(self):
        self.packet={'value':'{"results":[{"error":"unavailable"}]}','search_memo':[],
                     'diagnostics':[{'phase':'keyless_response','http_status':404},{'phase':'keyless_exception','exception':'plugins.web.keyless_mcp.KeylessMCPError','code':'keyless provider unavailable'}]}
        with self.assertLogs(parent.__name__,level='WARNING') as captured:result=json.loads(self.run_parent())
        self.assertFalse(result['retry_allowed']);self.assertEqual(result['cleanup'],'confirmed')
        self.assertEqual(self.turn.failure,result);self.assertNotIn('404',json.dumps(result))
        self.assertTrue(any('Private web child diagnostic' in line and '404' in line for line in captured.output))
        second=ctx.WebCall(self.turn,time.monotonic()+60,'task','session','other-call');second.user_authority=None
        with ctx.bind_web_call(second):again=parent.run_web('web_extract',{'urls':['https://fixture.example/alternate']},task_id='task',session_id='session')
        self.assertEqual(self.spawn_count,1);self.assertFalse(json.loads(again)['retry_allowed'])
    def test_legacy_packets_keep_exact_success_bytes(self):
        expected=' {"results":[{"content":"'+SECRET+'"}]}\n'
        self.packet={'value':expected,'search_memo':[]}
        self.assertEqual(self.run_parent(),expected);self.assertIsNone(self.turn.failure)
    def test_valid_diagnostics_cannot_turn_partial_result_into_failure(self):
        expected='{"results":[{"content":"verified part"},{"error":"unavailable"}]}'
        self.packet={'value':expected,'search_memo':[],'diagnostics':[{'phase':'keyless_response','http_status':503}]}
        self.assertEqual(self.run_parent(),expected);self.assertIsNone(self.turn.failure)
    def test_malformed_private_diagnostics_remain_terminal(self):
        self.packet={'value':'{"results":[{"content":"source"}]}','search_memo':[],
                     'diagnostics':[{'phase':'keyless_response','http_status':404,'message':SECRET}]}
        result=json.loads(self.run_parent())
        self.assertFalse(result['retry_allowed']);self.assertEqual(self.turn.failure,result)
        self.assertNotIn(SECRET,json.dumps(result))
    def test_cleanup_unknown_not_softened_by_status(self):
        self.packet={'value':'{"success":false}','search_memo':[],
                     'diagnostics':[{'phase':'keyless_response','http_status':410}]}
        self.cleanup='STOP_UNCONFIRMED';result=json.loads(self.run_parent())
        self.assertEqual(result['cleanup'],'unconfirmed');self.assertTrue(self.turn.stopped.is_set())
    def test_actual_child_envelope_exports_only_fixed_metadata(self):
        old_deadline=time.monotonic()+60
        data={'tool':'web_extract','args':{'urls':['https://fixture.example/page']},'home':str(self.home),'deadline':old_deadline,
              'options':{},'secrets':{},'authority':None,'session_id':'session','session_key':'session'}
        async def extract(*args,**kw):
            # Same asyncio-to-thread propagation as the native extract dispatcher.
            await asyncio.to_thread(keyless.KeylessMCPError,'keyless result refused')
            return '{"results":[{"error":"unavailable"}]}'
        extra={'pm.environments':fake('pm.environments',activate_dependencies=lambda root:None),
               'agent.secret_scope':fake('agent.secret_scope',set_multiplex_active=lambda *a:None,set_secret_scope=lambda *a,**kw:None),
               'agent.redact':fake('agent.redact',redact_sensitive_text=lambda text,**kw:text,register_vault_redaction_value=lambda *a:None),
               'gateway.session_context':fake('gateway.session_context',set_current_session_id=lambda *a:None),
               'tools.approval_context':fake('tools.approval_context',set_current_session_key=lambda *a:None),
               'tools.web_tools_truncate':fake('tools.web_tools_truncate',_store_full_text=lambda *a:None),
               'tools.web_tools':fake('tools.web_tools',web_extract_tool=extract)}
        self.users.policy=lambda home:None;self.users.guard_tool=lambda *a:None
        self.modules['tools.web_result_cache'].extract_cache_put=lambda *a,**kw:None
        original=keyless._response_text
        output=io.StringIO();input_stream=types.SimpleNamespace(buffer=io.BytesIO((json.dumps(data)+'\n').encode()))
        with patch.dict(sys.modules,extra),patch.dict(os.environ,{'HERMES_HOME':str(self.home)}),patch.object(sys,'stdin',input_stream),patch.object(sys,'stdout',output):
            try:child.main()
            finally:keyless._response_text=original
        wire=json.loads(output.getvalue());self.packet=json.loads(wire['result'])
        self.assertEqual(set(self.packet),{'value','search_memo','diagnostics'})
        self.assertEqual(self.packet['diagnostics'],[{'phase':'keyless_exception','exception':'plugins.web.keyless_mcp.KeylessMCPError','code':'keyless result refused'}])
        self.assertNotIn('diagnostics',self.packet['value']);self.assertEqual(ctx._child_deadline.get(),old_deadline)
        result=json.loads(self.run_parent());self.assertFalse(result['retry_allowed'])

if __name__=='__main__':unittest.main(verbosity=2)
