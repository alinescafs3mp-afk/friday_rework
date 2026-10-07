import json,os
from pathlib import Path
import pytest
from test_admin_foundation import env, session
from test_admin_controls import local_config,body
from test_admin_skill_loader import raw,managed,visible
from test_admin_skill_loader_consumers import plugin_fixture

E=Path(os.environ["FRIDAY_FIXTURE_EVIDENCE"])

def put(env,rel,name,bodytext=None):
 p=env.home/'skills'/rel/'SKILL.md';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(f'---\nname: {name}\ndescription: independent review fixture\n---\n{bodytext or rel}\n')
 support=p.parent/'references/detail.md';support.parent.mkdir(exist_ok=True);support.write_text('SUPPORT:'+rel)
 return p

def reg(name,task='independent',file=None):
 from tools.registry import registry
 args={'name':name}
 if file:args['file_path']=file
 answer=registry.dispatch('skill_view',args,task_id=task)
 return json.loads(answer) if isinstance(answer,str) else answer

def reset():
 from tools.skills_tool import reset_skill_view_dedup
 reset_skill_view_dedup()

def log(name,value):
 with (E/'observations.jsonl').open('a') as f:f.write(json.dumps({'case':name,'observation':value})+'\n')

@pytest.mark.parametrize('layer',['raw','managed'])
@pytest.mark.parametrize('scope',['global','platform'])
@pytest.mark.parametrize('kind',['local','plugin'])
def test_registered_policy_transition_and_linked_guard(env,monkeypatch,layer,scope,kind):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram')
 if kind=='local':put(env,'unique','unique','UNIQUE_ALLOWED');name='unique';linked='references/detail.md'
 else:plugin_fixture(env,monkeypatch);name='fixtureplug:one';linked='references/note.md'
 first=reg(name);warm=reg(name);support=reg(name,file=linked)
 assert first['success'] and first['content'] and warm['dedup'] and support['content']
 deny='\u00a0\t'+name+'\r\n'
 policy={'disabled':[deny]} if scope=='global' else {'platform_disabled':{'telegram':[deny]}}
 (raw(env,policy) if layer=='raw' else managed(env,monkeypatch,policy))
 a=reg(name);b=reg(name,file=linked)
 assert a['success'] is False and b['success'] is False and 'content' not in a and 'content' not in b
 (raw(env,{}) if layer=='raw' else managed(env,monkeypatch,{}))
 assert reg(name)['content'] and reg(name,file=linked)['content']

@pytest.mark.parametrize('layer',['raw','managed'])
@pytest.mark.parametrize('scope',['global','platform'])
def test_denied_qualified_plugin_cannot_hit_allowed_local_cache(env,monkeypatch,layer,scope):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');put(env,'one','one','LOCAL_ONE');plugin_fixture(env,monkeypatch)
 policy={'disabled':[' fixtureplug:one ']} if scope=='global' else {'platform_disabled':{'telegram':[' fixtureplug:one ']}}
 (raw(env,policy) if layer=='raw' else managed(env,monkeypatch,policy))
 from tools.skills_tool import skill_view
 direct=json.loads(skill_view('fixtureplug:one',preprocess=False));assert direct['success'] is False
 assert reg('one')['content'];answer=reg('fixtureplug:one')
 log('qualified-deny-'+layer+'-'+scope,{'direct':direct,'registered':answer})
 assert answer['success'] is False,'Denied qualified plugin received allowed local repeat-view stub'

@pytest.mark.parametrize('layer',['raw','managed'])
def test_newly_enabled_plugin_returns_its_own_useful_content(env,monkeypatch,layer):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');put(env,'one','one','LOCAL_ONE');plugin_fixture(env,monkeypatch)
 setter=lambda value:raw(env,value) if layer=='raw' else managed(env,monkeypatch,value)
 setter({'disabled':[' fixtureplug:one ']});assert reg('fixtureplug:one')['success'] is False
 setter({});assert reg('one')['content']=='---\nname: one\ndescription: independent review fixture\n---\nLOCAL_ONE\n'
 answer=reg('fixtureplug:one');log('enabled-qualified-'+layer,answer)
 assert answer.get('success') and 'PLUGIN_USEFUL:one' in answer.get('content',''),'Newly enabled plugin content hidden by unrelated local cache entry'

@pytest.mark.parametrize('essential',[False,True])
def test_typed_enable_and_duplicate_peer_preservation(env,monkeypatch,essential):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');declared='hermes-agent' if essential else 'shared'
 put(env,'a/one',declared);put(env,'b/two',declared);put(env,'other','other')
 raw(env,{'disabled':[' '+declared+' ',' b/two ',' other ','*','shar*'],'platform_disabled':{'telegram':[' '+declared+' ']}})
 answer=env.admin.write_settings('default',body(env,'skill',name='a/one',enabled=True),session());assert answer['recorded'];assert visible()=={'a/one'}
 assert reg('a/one')['content'];assert reg('b/two')['success'] is False;assert reg('other')['success'] is False
 if essential:
  with pytest.raises(ValueError,match='native_required_skill'):env.admin.write_settings('default',body(env,'skill',name='a/one',enabled=False),session())
 else:
  assert env.admin.write_settings('default',body(env,'skill',name='a/one',enabled=False),session())['recorded'];assert reg('a/one')['success'] is False

@pytest.mark.parametrize('value',['*','fixtureplug:*','one','hermes-agent'])
def test_plugin_literal_names_and_denied_content_not_read(env,monkeypatch,value):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');pm=plugin_fixture(env,monkeypatch)
 raw(env,{'disabled':[value]});assert 'PLUGIN_USEFUL:one' in reg('fixtureplug:one')['content']
 raw(env,{'disabled':[' fixtureplug:one ']})
 from tools import skills_tool_plugin
 original=skills_tool_plugin._read_skill_text;root=pm.find_plugin_skill('fixtureplug:one').parent;reads=[]
 def read(path):
  reads.append(str(path));assert not Path(path).is_relative_to(root);return original(path)
 monkeypatch.setattr(skills_tool_plugin,'_read_skill_text',read)
 assert reg('fixtureplug:one')['success'] is False
 assert reg('fixtureplug:one',file='references/note.md')['success'] is False
 assert 'PLUGIN_USEFUL:two' in reg('fixtureplug:two')['content'];assert all(not Path(p).is_relative_to(root) for p in reads)

@pytest.mark.parametrize('layer',['raw','managed'])
@pytest.mark.parametrize('scope',['global','platform'])
def test_denied_duplicate_cannot_hit_allowed_peer_cache(env,monkeypatch,layer,scope):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');put(env,'allowed/shared','shared','ALLOWED_PEER');put(env,'denied/shared','shared','DENIED_PEER')
 policy={'disabled':[' denied/shared ']} if scope=='global' else {'platform_disabled':{'telegram':[' denied/shared ']}}
 (raw(env,policy) if layer=='raw' else managed(env,monkeypatch,policy))
 from tools.skills_tool import skill_view
 direct=json.loads(skill_view('denied/shared',preprocess=False));assert direct['success'] is False
 assert 'ALLOWED_PEER' in reg('allowed/shared')['content'];answer=reg('denied/shared')
 log('duplicate-deny-'+layer+'-'+scope,{'direct':direct,'registered':answer})
 assert answer['success'] is False,'Denied duplicate received allowed peer repeat-view stub'


def test_two_enabled_duplicates_return_distinct_useful_content(env,monkeypatch):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');put(env,'a/shared','shared','A_USEFUL');put(env,'b/shared','shared','B_USEFUL')
 assert 'A_USEFUL' in reg('a/shared')['content'];answer=reg('b/shared');log('allowed-duplicate-content',answer)
 assert 'B_USEFUL' in answer.get('content',''),'Second enabled duplicate hidden by unrelated peer cache entry'


@pytest.mark.parametrize('first',['local','plugin'])
@pytest.mark.parametrize('linked',[False,True])
def test_distinct_local_and_plugin_copies_in_either_order(env,monkeypatch,first,linked):
 local_config(env);reset();put(env,'one','one','LOCAL_ONE');plugin_fixture(env,monkeypatch)
 names=['one','fixtureplug:one'] if first=='local' else ['fixtureplug:one','one']
 for name in names:
  file=('references/detail.md' if name=='one' else 'references/note.md') if linked else None
  answer=reg(name,file=file)
  wanted=('SUPPORT:one' if linked else 'LOCAL_ONE') if name=='one' else ('PLUGIN_SUPPORT:one' if linked else 'PLUGIN_USEFUL:one')
  assert wanted in answer.get('content','') and not answer.get('dedup')
  repeat=reg(name,file=file);assert repeat['dedup'] and repeat['name']==answer['name']


@pytest.mark.parametrize('first',['a','b'])
@pytest.mark.parametrize('linked',[False,True])
def test_duplicate_copy_order_preserves_content_and_dedup(env,monkeypatch,first,linked):
 local_config(env);reset();put(env,'a/shared','shared','A_USEFUL');put(env,'b/shared','shared','B_USEFUL')
 for copy in [first,'b' if first=='a' else 'a']:
  file='references/detail.md' if linked else None
  answer=reg(copy+'/shared',file=file)
  assert ('SUPPORT:'+copy+'/shared' if linked else copy.upper()+'_USEFUL') in answer.get('content','')
  assert reg(copy+'/shared',file=file)['dedup']


@pytest.mark.parametrize('alias',['unique','one','category/one','category:one'])
@pytest.mark.parametrize('linked',[False,True])
def test_same_resolved_copy_aliases_keep_useful_dedup(env,monkeypatch,alias,linked):
 local_config(env);reset();put(env,'category/one','unique','UNIQUE_USEFUL')
 file='references/detail.md' if linked else None
 assert reg('unique',file=file)['content']
 assert reg(alias,file=file)['dedup']


@pytest.mark.parametrize('layer',['raw','managed'])
@pytest.mark.parametrize('scope',['global','platform'])
def test_warm_support_homonym_never_reads_denied_plugin(env,monkeypatch,layer,scope):
 local_config(env);reset();monkeypatch.setenv('HERMES_PLATFORM','telegram');put(env,'one','one','LOCAL_ONE');pm=plugin_fixture(env,monkeypatch)
 # Match the same file selector that used to be sufficient for a false stub.
 p=env.home/'skills/one/references/note.md';p.write_text('LOCAL_NOTE')
 policy={'disabled':[' fixtureplug:one ']} if scope=='global' else {'platform_disabled':{'telegram':[' fixtureplug:one ']}}
 (raw(env,policy) if layer=='raw' else managed(env,monkeypatch,policy))
 assert reg('one',file='references/note.md')['content']=='LOCAL_NOTE'
 from tools import skills_tool_plugin
 original=skills_tool_plugin._read_skill_text;root=pm.find_plugin_skill('fixtureplug:one').parent;reads=[]
 def read(path):
  reads.append(str(path));assert not Path(path).is_relative_to(root);return original(path)
 monkeypatch.setattr(skills_tool_plugin,'_read_skill_text',read)
 answer=reg('fixtureplug:one',file='references/note.md');assert answer['success'] is False and 'content' not in answer
 assert reg('one',file='references/note.md')['dedup']


def test_plugin_disable_and_reload_reauthorize_warm_copy(env,monkeypatch):
 local_config(env);reset();pm=plugin_fixture(env,monkeypatch)
 assert 'PLUGIN_USEFUL:one' in reg('fixtureplug:one')['content']
 from hermes_cli import plugins
 monkeypatch.setattr(plugins,'_get_disabled_plugins',lambda:{'fixtureplug'})
 assert reg('fixtureplug:one')['success'] is False
 monkeypatch.setattr(plugins,'_get_disabled_plugins',lambda:set())
 old=pm.find_plugin_skill('fixtureplug:one');pm.remove_plugin_skill('fixtureplug:one')
 assert not reg('fixtureplug:one').get('success')
 from hermes_cli.plugins import PluginContext,PluginManifest
 new=env.home/'reloaded/one/SKILL.md';new.parent.mkdir(parents=True);new.write_text('---\nname: shared\ndescription: reload\n---\nRELOADED_USEFUL')
 ctx=PluginContext(PluginManifest(name='fixtureplug',version='2',source='user',description='reload'),pm)
 ctx.register_skill('one',new,description='reload',frontmatter={'name':'shared'})
 answer=reg('fixtureplug:one');assert 'RELOADED_USEFUL' in answer.get('content','') and not answer.get('dedup')
 assert old!=new and reg('fixtureplug:one')['dedup']


def test_new_ambiguity_cannot_reuse_previously_unique_alias(env,monkeypatch):
 local_config(env);reset();put(env,'a/shared','shared','A_USEFUL')
 assert 'A_USEFUL' in reg('shared')['content'];assert reg('shared')['dedup']
 put(env,'b/shared','shared','B_USEFUL')
 answer=reg('shared');assert answer['success'] is False and 'content' not in answer and not answer.get('dedup')
 own=reg('a/shared');assert 'A_USEFUL' in own.get('content','') or own.get('dedup')
 assert 'B_USEFUL' in reg('b/shared')['content']


@pytest.mark.parametrize('kind',['local','plugin'])
def test_cache_reset_and_task_boundaries_keep_real_content(env,monkeypatch,kind):
 local_config(env);reset()
 if kind=='local':put(env,'unique','unique','LOCAL_UNIQUE');name='unique'
 else:plugin_fixture(env,monkeypatch);name='fixtureplug:one'
 first=reg(name,task='one');assert first['content'] and reg(name,task='one')['dedup']
 assert reg(name,task='two')['content']==first['content']
 from tools.skills_tool import reset_skill_view_dedup
 reset_skill_view_dedup('one');assert reg(name,task='one')['content']==first['content']
 assert reg(name,task='two')['dedup']


def test_same_plugin_file_and_task_are_isolated_by_runtime_home(env,monkeypatch):
 from hermes_constants import get_hermes_home,set_hermes_home_override,reset_hermes_home_override
 local_config(env);reset();plugin_fixture(env,monkeypatch)
 assert get_hermes_home()==env.home
 first=reg('fixtureplug:one');assert first['content'] and reg('fixtureplug:one')['dedup']
 second=env.home.parent/'second-runtime';second.mkdir();(second/'config.yaml').write_text('{}')
 with monkeypatch.context() as profile:
  profile.setenv('HERMES_HOME',str(second))
  token=set_hermes_home_override(second)
  try:
   assert get_hermes_home()==second
   answer=reg('fixtureplug:one');log('same-file-task-different-runtime-home',{'home':str(get_hermes_home()),'answer':answer})
   assert answer['content']==first['content'] and not answer.get('dedup')
   assert reg('fixtureplug:one')['dedup']
  finally:reset_hermes_home_override(token)
 assert reg('fixtureplug:one')['dedup']
