import json,os,hashlib,builtins
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import pytest
from file_native_fixture import env,entered,home,scope
from hermes_cli import friday_workspace_docx as dx
from tools import file_tools as ft
from test_read_delivery import actor,dispatch,value

def create(path='report.docx',content='Independent 😀 & <text>\n\nশেষ\n'):
 return json.loads(ft._handle_write_file(dict(path=path,content=content,format='docx'),task_id='independent-review'))

def test_nested_parent_relocation_cannot_escape_own_workspace(env,monkeypatch):
 with entered(env):
  root=home(env)/'workspace';foreign=home(env,'2')/'workspace'
  (root/'nested').mkdir(mode=0o700);original=dx.render
  def relocate(text):
   data=original(text)
   (root/'nested').rename(foreign/'moved')
   (root/'nested').mkdir(mode=0o700)
   return data
  monkeypatch.setattr(dx,'render',relocate)
  result=create('nested/report.docx')
  assert not (foreign/'moved/report.docx').exists(),result

def test_raise_after_successful_rename_and_replacement_must_remain_unknown(env,monkeypatch):
 with entered(env):
  original=dx._move
  def moved_then_replaced_then_error(fd,stage,target_fd,leaf):
   original(fd,stage,target_fd,leaf)
   os.unlink(leaf,dir_fd=fd)
   f=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd)
   os.write(f,b'RACER');os.close(f)
   raise OSError('wrapper failure after real publication and replacement')
  monkeypatch.setattr(dx,'_move',moved_then_replaced_then_error)
  result=create()
  assert result.get('effect_disposition')=='unknown',result
  assert (home(env)/'workspace/report.docx').read_bytes()==b'RACER'

def test_independent_scoped_full_handler_import_denial_and_create_only(env,monkeypatch):
 with entered(env):
  original=builtins.__import__;attempts=[]
  def deny(name,*a,**kw):
   if name.split('.')[0] in {'docx','lxml'}:
    attempts.append(name);raise ImportError('independent explicit dependency denial')
   return original(name,*a,**kw)
  monkeypatch.setattr(builtins,'__import__',deny)
  result=create();assert result['success'];assert not attempts
  p=home(env)/'workspace/report.docx';before=p.read_bytes()
  assert create()['error']=='document_already_exists';assert p.read_bytes()==before
  with ZipFile(BytesIO(before)) as z:
   assert z.testzip() is None
   assert b'Independent' in z.read('word/document.xml')
  assert not json.loads(ft.write_file_tool('report.docx','overwrite'))['success']

def test_input_exact_utf8_and_paragraph_bounds(env):
 with entered(env):
  assert create('unicode.docx','ж'*50000)['success']
  assert not create('over.docx','ж'*50001)['success']
  assert create('paras.docx','\n'*1999)['success']
  assert not create('overparas.docx','\n'*2000)['success']

def test_native_unknown_carrier_survives_unexpected_postrename_replacement(env,monkeypatch):
 from test_read_delivery import actor,dispatch,value
 with entered(env):
  original=dx._move;a=actor()
  def moved_replaced_raised(fd,stage,target_fd,leaf):
   original(fd,stage,target_fd,leaf);os.unlink(leaf,dir_fd=fd)
   f=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd)
   os.write(f,b'RACER');os.close(f)
   raise OSError('postpublication wrapper failure')
  monkeypatch.setattr(dx,'_move',moved_replaced_raised)
  _,out=dispatch(a,'write_file',dict(path='report.docx',content='native marker',format='docx'),'independent-native-unknown')
  result=value(out)
  assert getattr(a,'_friday_reply_effect_unknown',False) is True,result
