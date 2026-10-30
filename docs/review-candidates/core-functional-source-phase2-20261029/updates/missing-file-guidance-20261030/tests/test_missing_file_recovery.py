import json
from pathlib import Path
import pytest
from hermes_cli import friday_user_scope as scope

def read(path,**kw):
 from tools.file_tools import read_file_tool
 return json.loads(read_file_tool(path,task_id='retained-original-recovery',**kw))

def test_missing_final_name_guides_scoped_recovery(admitted):
 result=read('Отчёт.docx')
 assert result['success'] is False and result['error']=='file_not_found',result
 assert result['scope']=='own_user_workspace'
 assert 'session_search' in result['hint'] and 'substitute' in result['hint']
 assert 'Отчёт.docx' not in json.dumps(result,ensure_ascii=False)
 assert list((admitted.home/'workspace').iterdir())==[]

def test_nested_missing_final_name_and_no_alias(admitted):
 received=admitted.home/'workspace/received';received.mkdir(mode=0o700)
 (received/'opaque-old.txt').write_text('original');(received/'opaque-old.txt').chmod(0o600)
 assert read('received/Отчёт.docx')['error']=='file_not_found'
 assert read('received/opaque-old.txt')['content']=='1: original'
 assert read('Отчёт.docx')['error']=='file_not_found'
 assert not (admitted.home/'workspace/Отчёт.docx').exists()

@pytest.mark.parametrize('fault',['outside','traversal','hidden','missing_parent','parent_symlink','leaf_symlink','parent_acl','leaf_acl','revoked','replaced_home'])
def test_authority_path_identity_link_denials_stay_generic(admitted,fault):
 root=admitted.home/'workspace';path='Отчёт.docx'
 if fault=='outside':path=str(admitted.root/'absent.docx')
 elif fault=='traversal':path='../absent.docx'
 elif fault=='hidden':path='.private/absent.docx'
 elif fault=='missing_parent':path='absent/Отчёт.docx'
 elif fault=='parent_symlink':
  (root/'link').symlink_to(admitted.root,target_is_directory=True);path='link/Отчёт.docx'
 elif fault=='leaf_symlink':(root/path).symlink_to(root/'absent.docx')
 elif fault=='parent_acl':
  (root/'bad').mkdir(mode=0o755);path='bad/Отчёт.docx'
 elif fault=='leaf_acl':
  (root/path).write_text('private');(root/path).chmod(0o644)
 elif fault=='revoked':admitted.cap.revoked=True
 else:admitted.cap.directory_identity=(0,0)
 result=read(path)
 assert result['success'] is False and result['error']=='Это действие недоступно.',result
 assert 'hint' not in result and 'file_not_found' not in json.dumps(result)

@pytest.mark.parametrize('kwargs',[{'offset':False},{'offset':0},{'limit':2001},{'char_offset':-1}])
def test_invalid_pagination_not_reclassified_as_missing(admitted,kwargs):
 assert read('Отчёт.docx',**kwargs)['error']=='Это действие недоступно.'

def test_existing_text_source_read_is_preserved(admitted):
 original=admitted.home/'workspace/actual-original.txt'
 original.write_text('full original content');original.chmod(0o600)
 before=original.read_bytes()
 result=read('actual-original.txt')
 assert result['success'] is True and result['content']=='1: full original content',result
 assert original.read_bytes()==before

def test_replaced_logical_parent_stays_generic(admitted,monkeypatch):
 root=admitted.home/'workspace';received=root/'received';received.mkdir(mode=0o700)
 original_stat=scope.os.stat;tripped=[]
 def swap(path,*args,**kwargs):
  if path=='missing.docx' and kwargs.get('dir_fd') is not None and not tripped:
   tripped.append(True);received.rename(root/'moved');received.mkdir(mode=0o700)
  return original_stat(path,*args,**kwargs)
 monkeypatch.setattr(scope.os,'stat',swap)
 result=read('received/missing.docx')
 assert tripped and result['error']=='Это действие недоступно.' and 'hint' not in result,result

def test_revocation_during_missing_probe_stays_generic(admitted,monkeypatch):
 original_stat=scope.os.stat
 def revoke(path,*args,**kwargs):
  if path=='missing.docx' and kwargs.get('dir_fd') is not None:admitted.cap.revoked=True
  return original_stat(path,*args,**kwargs)
 monkeypatch.setattr(scope.os,'stat',revoke)
 result=read('missing.docx')
 assert result['error']=='Это действие недоступно.' and 'hint' not in result,result

def test_recovery_guidance_survives_model_dispatcher(admitted):
 import model_tools
 result=json.loads(model_tools.handle_function_call('read_file',{'path':'Отчёт.docx'},
     task_id='retained-original-dispatch',enabled_toolsets=['file']))
 assert result['success'] is False and result['error']=='file_not_found',result
 assert 'session_search' in result['hint']
