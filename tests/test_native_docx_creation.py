import hashlib,json,os,time
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pytest
from file_native_fixture import env,entered,home,scope
from hermes_cli import friday_workspace_docx as dx
from tools import file_tools as ft
from tools.read_extract import extract_scoped_document_bytes
from agent import web_call_context as wc
from test_read_delivery import actor,dispatch,value,finalized,transport,write

TEXT='Заметки Friday 😀\n  Первый пункт & <текст>\n\nВторой пункт\n'
def create(path='report.docx',content=TEXT,**kw):
 return json.loads(ft._handle_write_file(dict(path=path,content=content,format='docx',**kw),task_id='docx-test'))

def test_real_native_create_extract_media_revision(env,tmp_path):
 with entered(env):
  a=actor();_,out=dispatch(a,'write_file',dict(path='report.docx',content=TEXT,format='docx'),'docx-create')
  r=value(out);assert r['success'] and r['create_only'] and r['verified']
  p=home(env)/'workspace/report.docx';data=p.read_bytes()
  assert data[:2]==b'PK' and hashlib.sha256(data).hexdigest()==r['sha256']
  assert not (p.stat().st_mode&0o077)
  text=extract_scoped_document_bytes(data,'docx');assert 'Первый пункт & <текст>' in text
  _,read=dispatch(a,'read_file',dict(path='report.docx'),'docx-read')
  assert value(read)['extracted_document'] and 'Второй пункт' in value(read)['content']
  snap,path=scope.workspace_document(str(p));assert snap==data and path=='report.docx'
  assert create()['error']=='document_already_exists'
  assert json.loads(ft.write_file_tool('report.docx','BAD'))['error']=='document_write_unsupported'
  assert 'error' in json.loads(ft.patch_tool(path=str(p),old_string='пункт',new_string='BAD'))
  revised=text.replace('Второй пункт','Изменённый пункт')
  assert create('report-v2.docx',revised)['success'] and p.read_bytes()==data
  assert 'Изменённый пункт' in extract_scoped_document_bytes((p.parent/'report-v2.docx').read_bytes(),'docx')
  # Own immutable snapshot survives subsequent path replacement.
  p.unlink();p.write_bytes(b'REPLACED');p.chmod(0o600);assert snap==data
  (tmp_path/'reader.docx').write_bytes(data)
  (tmp_path/'reader-expected.json').write_text(json.dumps(TEXT,ensure_ascii=False))

@pytest.mark.parametrize('path',['../escape.docx','.hidden.docx','a/.hidden.docx','wrong.txt','report.pdf','/tmp/foreign.docx'])
def test_path_suffix_controls(env,path):
 with entered(env):assert create(path)['success'] is False

@pytest.mark.parametrize('kind',['symlink','directory','existing-docx','existing-pdf','foreign','parent-symlink'])
def test_old_or_foreign_paths_untouched(env,kind):
 with entered(env):
  root=home(env)/'workspace';old=root/'old.docx';old.write_bytes(b'OLD');old.chmod(0o600)
  leaf=root/'target.docx';path='target.docx'
  if kind=='symlink':leaf.symlink_to(old)
  elif kind=='directory':leaf.mkdir(mode=0o700)
  elif kind=='existing-docx':leaf.write_bytes(b'BINARY');leaf.chmod(0o600)
  elif kind=='existing-pdf':path='old.pdf';(root/path).write_bytes(b'PDF')
  elif kind=='foreign':path=str(home(env,'2')/'workspace/new.docx')
  else:(root/'link').symlink_to(home(env,'2')/'workspace');path='link/new.docx'
  before=old.read_bytes();r=create(path);assert not r['success'];assert old.read_bytes()==before
  if kind=='existing-docx':assert leaf.read_bytes()==b'BINARY'
  assert not (home(env,'2')/'workspace/new.docx').exists()

@pytest.mark.parametrize('content',['\x00','\x01','\ud800','\ufffe','x'*100001,'ж'*50001,'\n'*2000])
def test_input_limits_xml_unicode(env,content):
 with entered(env):
  assert not create(content=content)['success']
  assert not list((home(env)/'workspace').iterdir())

def test_output_bound(env,monkeypatch):
 with entered(env):
  monkeypatch.setattr(dx,'MAX_OUTPUT',10)
  assert not create()['success'];assert not list((home(env)/'workspace').iterdir())

def test_revoke_during_render(env,monkeypatch):
 with entered(env) as cap:
  original=dx.render
  def revoke(text):data=original(text);cap.revoked=True;return data
  monkeypatch.setattr(dx,'render',revoke)
  assert not create()['success'];assert not list((home(env)/'workspace').iterdir())

def test_cancel_during_render(env,monkeypatch):
 with entered(env):
  call=wc.WebCall(wc.WebTurn(),time.monotonic()+30,'docx-test','s','c');original=dx.render
  def stop(text):data=original(text);call.stopped.set();return data
  monkeypatch.setattr(dx,'render',stop)
  with wc.bind_web_call(call):
   with pytest.raises(RuntimeError,match='web_call_stopped'):create()
  assert not list((home(env)/'workspace').iterdir())

def test_collision_at_publication_preserves_racer(env,monkeypatch):
 with entered(env):
  original=dx._move
  def race(fd,stage,target_fd,leaf):
   n=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd);os.write(n,b'RACER');os.close(n)
   return original(fd,stage,target_fd,leaf)
  monkeypatch.setattr(dx,'_move',race)
  r=create();assert not r['success'] and r['effect_disposition']=='none'
  root=home(env)/'workspace';assert (root/'report.docx').read_bytes()==b'RACER';assert len(list(root.iterdir()))==1

def test_publication_failure_cleans_private_stage(env,monkeypatch):
 with entered(env):
  def fail(*args):raise OSError('synthetic')
  monkeypatch.setattr(dx,'_move',fail)
  r=create();assert r['effect_disposition']=='none';assert not list((home(env)/'workspace').iterdir())

def test_post_publish_cancellation_retains_complete_uncertain(env,monkeypatch):
 with entered(env):
  original=dx._move;call=wc.WebCall(wc.WebTurn(),time.monotonic()+30,'docx-test','s','c')
  def stopped(*args):original(*args);call.stopped.set()
  monkeypatch.setattr(dx,'_move',stopped)
  with wc.bind_web_call(call):r=create()
  assert not r['success'] and r['effect_disposition']=='unknown'
  root=home(env)/'workspace';p=root/'report.docx';assert p.read_bytes()[:2]==b'PK';assert len(list(root.iterdir()))==1
  assert 'Первый пункт' in extract_scoped_document_bytes(p.read_bytes(),'docx')

def test_raise_after_rename_reports_unknown(env,monkeypatch):
 with entered(env):
  original=dx._move
  def fail(*args):original(*args);raise OSError('after effect')
  monkeypatch.setattr(dx,'_move',fail)
  assert create()['effect_disposition']=='unknown'
  assert (home(env)/'workspace/report.docx').read_bytes()[:2]==b'PK'

def test_plain_text_CAS_still_requires_wire_read(env,monkeypatch):
 with entered(env):
  a=actor();_,out=dispatch(a,'write_file',dict(path='notes.txt',content='one\ntwo\n'),'text-create');assert value(out)['success']
  assert write(a,'notes.txt')['error']=='file_revision_requires_current_full_read'
  messages=finalized(a,'notes.txt');transport(a,messages,monkeypatch)
  assert write(a,'notes.txt','one\nTWO\n')['success']
  assert (home(env)/'workspace/notes.txt').read_text()=='one\nTWO\n'

def test_unscoped_explicit_docx_never_silently_text(monkeypatch,tmp_path):
 monkeypatch.setattr(scope,'scoped_file',lambda *a,**k:None)
 p=tmp_path/'file.docx'
 assert json.loads(ft.write_file_tool(str(p),'DATA',format='docx'))['error']=='document_creation_requires_user_scope'
 assert not p.exists()


def test_runtime_docx_lxml_imports_denied(env,monkeypatch):
 import builtins
 original=builtins.__import__;attempts=[]
 def denied_import(name,*args,**kwargs):
  if name.split('.')[0] in {'docx','lxml'}:
   attempts.append(name);raise ImportError('runtime document dependency denied')
  return original(name,*args,**kwargs)
 with entered(env):
  monkeypatch.setattr(builtins,'__import__',denied_import)
  assert create()['success']
  assert attempts==[]


def test_generation_advance_during_render_is_real_revocation(env,monkeypatch):
 from hermes_cli.friday_product_access import KEY,current_access
 from hermes_cli.plugins_state import PluginState
 with entered(env) as cap:
  original=dx.render
  def advance(text):
   data=original(text)
   with scope.authority(env.root):
    access=current_access();access['users'][cap.key]['enabled']=False
    PluginState('friday_rework').set(KEY,access)
   return data
  monkeypatch.setattr(dx,'render',advance)
  assert not create()['success'];assert cap.revoked
  assert not list((home(env)/'workspace').iterdir())


def test_original_deadline_expires_during_render(env,monkeypatch):
 with entered(env):
  call=wc.WebCall(wc.WebTurn(),time.monotonic()+30,'docx-test','s','c');original=dx.render
  def expire(text):data=original(text);call.base_deadline=time.monotonic()-1;return data
  monkeypatch.setattr(dx,'render',expire)
  with wc.bind_web_call(call):
   assert not create()['success']  # Native scoped_file maps OSError/TimeoutError to scope refusal.
  assert not list((home(env)/'workspace').iterdir())


def test_stage_fsync_failure_cleans_up(env,monkeypatch):
 with entered(env):
  original=dx.os.fsync;calls=[]
  def fail_once(fd):
   calls.append(fd)
   if len(calls)==1:raise OSError('stage sync failed')
   return original(fd)
  monkeypatch.setattr(dx.os,'fsync',fail_once)
  assert create()['effect_disposition']=='none'
  assert not list((home(env)/'workspace').iterdir())


def test_post_publication_hash_mismatch_preserves_complete_file_unknown(env,monkeypatch):
 with entered(env):
  original=dx._snapshot;calls=[]
  def wrong(*args):
   data,version=original(*args);calls.append(1)
   return (b'WRONG' if len(calls)==2 else data),version
  monkeypatch.setattr(dx,'_snapshot',wrong)
  assert create()['effect_disposition']=='unknown'
  assert 'Второй пункт' in extract_scoped_document_bytes((home(env)/'workspace/report.docx').read_bytes(),'docx')


def test_postpublication_replaced_name_never_deleted(env,monkeypatch):
 with entered(env):
  original=dx._move
  def replace(*args):
   original(*args);fd,stage,target_fd,leaf=args
   os.unlink(leaf,dir_fd=fd)
   f=os.open(leaf,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=fd);os.write(f,b'RACER');os.close(f)
  monkeypatch.setattr(dx,'_move',replace)
  assert create()['effect_disposition']=='unknown'
  assert (home(env)/'workspace/report.docx').read_bytes()==b'RACER'


def test_plain_template_metadata_relations_and_determinism():
 data=dx.render(TEXT);assert data==dx.render(TEXT)
 with ZipFile(BytesIO(data)) as package:
  for name in package.namelist():
   if name.endswith('.rels'):
    assert not any(r.get('TargetMode')=='External' for r in ET.fromstring(package.read(name)))
  core=ET.fromstring(package.read('docProps/core.xml'))
  assert all(n.text=='Friday' for n in core if n.tag.endswith('creator') or n.tag.endswith('lastModifiedBy'))
  doc=ET.fromstring(package.read('word/document.xml'))
  assert not any(k.endswith('Ignorable') for k in doc.attrib)
  assert b'/home/' not in b''.join(package.read(n) for n in package.namelist() if n.endswith('.xml'))


def test_native_postpublication_unknown_sets_existing_reply_carrier(env,monkeypatch):
 with entered(env):
  original=dx._move;a=actor()
  def stopped(*args):
   original(*args);wc.current_web_call().stopped.set()
  monkeypatch.setattr(dx,'_move',stopped)
  _,out=dispatch(a,'write_file',dict(path='report.docx',content=TEXT,format='docx'),'native-unknown')
  assert value(out)['effect_disposition']=='unknown'
  assert a._friday_reply_effect_unknown is True
  assert extract_scoped_document_bytes((home(env)/'workspace/report.docx').read_bytes(),'docx')
