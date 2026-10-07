"""Real native AIAgent/profile/SDK/store/tool loop; all responses synthetic.

This is not a model/provider run or acceptance of autonomous research. Known
web provider registration and API responses are fixture seams, explicitly so.
"""
import json
import os
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest
import requests

from test_web_runtime_runner import M, OriginalTask, FakeBoundary, pin, digest

Q = Path(__file__).resolve().parents[1]
build = runpy.run_path(str(Q/'tools/configure_local_test.py'))['build_config']


@pytest.mark.parametrize('mode',['ordinary','explicit'])
def test_real_native_agent_reaches_web_and_cleanup(tmp_path,monkeypatch,mode):
    from tools import web_tools as wt
    from agent import web_search_registry as registry
    from plugins.web.exa.provider import ExaWebSearchProvider
    from hermes_cli.config import atomic_config_replace
    from hermes_constants import get_hermes_home
    from openai.types.chat import ChatCompletion
    import run_agent
    root=Path(run_agent.__file__).resolve().parent
    home=tmp_path/'profile';home.mkdir(mode=0o700)
    config=build(base_url='http://127.0.0.1:8011/v1',model='offline-native-fixture',key_env='FRIDAY_FIXTURE_KEY',
                 context=40960,max_input=40954,main_output=4096,summary_output=2048,margin=1024,template_overhead=2048,
                 web_profile='exa-keyless')
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    config=M['validation_profile'](config,DEFAULT_CONFIG)
    atomic_config_replace(home/'config.yaml',config)
    (home/'SOUL.md').write_text('FRIDAY_SYNTHETIC_SOUL_NATIVE_DRIVER\n')
    output=tmp_path/'output';output.mkdir(mode=0o700)
    workspace=tmp_path/'workspace';workspace.mkdir(mode=0o700)
    rels=['run_agent.py','agent/agent_init.py','agent/prompt_builder.py','agent/system_prompt.py',
          'agent/secret_scope.py','hermes_cli/runtime_provider.py','tools/web_tools.py','tools/web_result_cache.py',
          'plugins/web/exa/provider.py','plugins/web/keyless_mcp.py','hermes_cli/config_defaults.py']
    plan={'task_id':'offline-native-'+mode,'mode':mode,'source':str(root),'source_files':{r:pin(root/r)['sha256'] for r in rels},
          'profile':pin(home/'config.yaml'),'soul':pin(home/'SOUL.md'),'policy':pin(Q/'config/RESEARCH.md'),
          'driver':pin(Q/'validation/web_runtime.py'),'web_profile_source':pin(Q/'tools/web_profile.py'),
          'inference_endpoint':'http://127.0.0.1:8011/v1','web_profile':'exa-keyless','max_iterations':4,
          'workspace':str(workspace),'output':str(output)}
    task=OriginalTask(plan['task_id'],100.,1000.,90.,'fixture-boot',digest(plan))
    registry.register_provider(ExaWebSearchProvider());monkeypatch.setattr(wt,'_ensure_web_plugins_loaded',lambda:None)
    async def safe(url):return True  # synthetic DNS/public page, not an SSRF acceptance
    monkeypatch.setattr(wt,'async_is_safe_url',safe)
    transport=[]
    def post(url,**kw):
        transport.append((url,kw['json']['params']))
        assert url=='https://mcp.exa.ai/mcp'
        args=kw['json']['params']['arguments']
        if kw['json']['params']['name']=='web_search_exa':
            assert args['numResults']==3
            text='Title: urllib3 official source\nURL: https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html\nHighlights:\nRetry API'
        else:text='# Retry\ntotal, allowed_methods, status_forcelist, respect_retry_after_header: synthetic official-text fixture'
        return SimpleNamespace(status_code=200,headers={'Content-Type':'application/json'},content=json.dumps({'jsonrpc':'2.0','id':1,'result':{'content':[{'type':'text','text':text}]}}).encode())
    monkeypatch.setattr(requests,'post',post)
    responses=[]
    for number,(name,args) in enumerate([('web_search',{'query':'urllib3 Retry API','limit':3}),
                                       ('web_extract',{'urls':['https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html']})]):
        responses.append(ChatCompletion(id='offline'+str(number),created=1,object='chat.completion',model=config['model']['default'],
            choices=[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[
                {'id':'call'+str(number),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
            usage={'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}))
    responses.append(ChatCompletion(id='offline-final',created=1,object='chat.completion',model=config['model']['default'],
        choices=[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps({'total':2,'allowed_methods':['GET'],
        'status_forcelist':[503],'respect_retry_after_header':True,'sources':['https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html']})}}],
        usage={'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}))
    api=[]
    import httpx
    def send(client,request,**kw):
        assert str(request.url)=='http://127.0.0.1:8011/v1/chat/completions'
        body=json.loads(request.content);api.append(body)
        assert responses;value=responses.pop(0).model_dump()
        if body.get('stream'):
            choice=value['choices'][0];delta=choice['message']
            if delta.get('tool_calls'):
                for i,c in enumerate(delta['tool_calls']):c['index']=i
            chunk={'id':value['id'],'created':value['created'],'object':'chat.completion.chunk','model':value['model'],
                   'choices':[{'index':0,'delta':delta,'finish_reason':choice['finish_reason']}], 'usage':value.get('usage')}
            data=('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=data,request=request)
        return httpx.Response(200,json=value,request=request)
    # Genuine SDK serialization/parsing/stream/relay; only HTTP transport fake.
    # Native fresh per-request clients are covered, not just agent.client.
    monkeypatch.setattr(httpx.Client,'send',send)
    class OfflineNative(M['Native']):
        def open(self,*args):
            try: super().open(*args)
            except Exception as exc:
                self.open_failure = type(exc).__name__ + ': ' + str(exc).replace('SYNTHETIC_SCOPED_CREDENTIAL','[REDACTED]')
                raise
            assert 'FRIDAY_SYNTHETIC_SOUL_NATIVE_DRIVER' in self.rendered_prompt
            return self
    obj=OfflineNative();boundary=FakeBoundary()
    try: result=M['execute'](plan,task,boundary,native=obj,mono=lambda:110.,wall=lambda:1010.,boot='fixture-boot')
    except M['Refused']:
        pytest.fail(getattr(obj,'open_failure','native run failed; inspect synthetic observation'))
    assert result['model_completed'] and len(api)==3 and not responses
    assert len(result['tool_source_observations'])==2 and len(transport)==2
    assert result['journey_acceptance']=='NOT_CLAIMED' and boundary.settles==1
    assert all(k['function']['name'] in {'web_search','web_extract'} for request in api for k in request.get('tools',[]))
    from agent.secret_scope import current_secret_scope
    assert current_secret_scope() is None  # restored original scope, no credential retention
