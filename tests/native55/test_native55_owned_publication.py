import os,stat,sys
from pathlib import Path
import pytest
P=Path(os.environ['FRIDAY_PROJECT_SOURCE']).resolve();sys.path.insert(0,str(P))
from scripts import friday_ordinary_install as o
from scripts.dsh_prepare import StopUnconfirmed

@pytest.mark.parametrize('mask',[0o077,0o002])
def test_new_file_exclusive_mode_and_owned_remove(tmp_path,mask):
 tmp_path.chmod(0o700);target=tmp_path/'added.py';owned={};old=os.umask(mask)
 try:o.publish_update_file(target,b'after\n',0o644,None,owned,'added.py')
 finally:os.umask(old)
 assert target.read_bytes()==b'after\n' and stat.S_IMODE(target.stat().st_mode)==0o644
 o.restore_update_files(tmp_path,{'added.py':None},owned);assert not target.exists()

@pytest.mark.parametrize('fault',['inode','mode','bytes'])
def test_same_created_target_unknown_refuses_removal(tmp_path,fault):
 tmp_path.chmod(0o700);target=tmp_path/'added.py';owned={};o.publish_update_file(target,b'after\n',0o644,None,owned,'added.py')
 if fault=='inode':p=tmp_path/'foreign';p.write_bytes(b'after\n');p.chmod(0o644);os.replace(p,target)
 elif fault=='mode':target.chmod(0o600)
 else:target.write_bytes(b'foreign\n')
 state=o.update_file_state(target)
 with pytest.raises(ValueError,match='ownership_changed'):o.restore_update_files(tmp_path,{'added.py':None},owned)
 assert o.update_file_state(target)==state

def test_foreign_staging_never_deleted(tmp_path):
 tmp_path.chmod(0o700);target=tmp_path/'added.py';staged=tmp_path/'added.py.ordinary-staged';staged.write_bytes(b'foreign');staged.chmod(0o600);state=o.update_file_state(staged)
 with pytest.raises(StopUnconfirmed):o.publish_update_file(target,b'after\n',0o644,None,{},'added.py')
 assert o.update_file_state(staged)==state and not target.exists()

def test_staging_replacement_before_publication_never_deleted(tmp_path,monkeypatch):
 tmp_path.chmod(0o700);target=tmp_path/'added.py';staged=tmp_path/'added.py.ordinary-staged';original=o.same_update_file;foreign=None
 def check(path,state):
  nonlocal foreign
  if path==staged and foreign is None:
   replacement=tmp_path/'foreign';replacement.write_bytes(b'after\n');replacement.chmod(0o644);os.replace(replacement,staged);foreign=o.update_file_state(staged)
  return original(path,state)
 monkeypatch.setattr(o,'same_update_file',check)
 with pytest.raises(StopUnconfirmed):o.publish_update_file(target,b'after\n',0o644,None,{},'added.py')
 assert foreign and o.update_file_state(staged)==foreign and not target.exists()

def test_post_restore_same_bytes_foreign_inode_rejected(tmp_path,monkeypatch):
 tmp_path.chmod(0o700);target=tmp_path/'old.py';target.write_bytes(b'before\n');target.chmod(0o600);before=o.update_file_state(target);owned={};o.publish_update_file(target,b'after\n',0o600,before,owned,'old.py');publish=o.publish_update_file
 def changed(*args):
  result=publish(*args);foreign=tmp_path/'foreign';foreign.write_bytes(b'before\n');foreign.chmod(0o600);os.replace(foreign,target);return result
 monkeypatch.setattr(o,'publish_update_file',changed)
 with pytest.raises(ValueError,match='restore_failed'):o.restore_update_files(tmp_path,{'old.py':before},owned)
