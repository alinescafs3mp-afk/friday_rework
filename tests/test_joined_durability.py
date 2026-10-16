import json,os,stat,hashlib
import pytest
from file_native_fixture import env,entered,home
from test_read_delivery import actor,dispatch,commit,transport,TASK
from agent import tool_executor as te
from tools.budget_config import DEFAULT_BUDGET
from types import SimpleNamespace as NS
def own_db(env):return NS(close=lambda:None)
from hermes_cli import friday_workspace_revision as rev
from tools import file_tools as ft
from pathlib import Path
O=Path(__file__).resolve().parents[1]
OBS={}

def tools(a,name,path,content=None):
 args={'path':path}
 if content is not None:args['content']=content
 r,out=dispatch(a,name,args,'durability-'+name)
 if name=='read_file':
  m=[];commit(a,m,r,out);te._finalize_tool_batch(a,m,TASK,1,DEFAULT_BUDGET)
  with pytest.MonkeyPatch.context() as patch:transport(a,m,patch)
 return json.loads(out.result)

@pytest.mark.parametrize('fault',['none','captured-inode-sync','capture-tx-sync','capture-parent-sync','publish-tx-sync','publish-parent-sync','archive-parent-sync','archive-parent-sync-persistent','archive-wrapper-after','restore-wrapper-after','restore-collision','restore-failure','restore-and-blocker-failure'])
def test_durable_order_and_recovery(env,monkeypatch,fault):
 db=own_db(env)
 try:
  with entered(env):
   a=actor();name='durable.txt';root=home(env)/'workspace';p=root/name
   assert tools(a,'write_file',name,'ORIGINAL')['success'];tools(a,'read_file',name)
   old_inode=p.stat().st_ino;parent_inode=root.stat().st_ino;events=[];state={'captured':False,'published':False,'archived':False,'faulted':False,'tx_inode':None};move=rev._move;rename=rev._rename;sync=os.fsync;mkdir=os.mkdir
   def injected_move(sfd,source,tfd,target):
    out=move(sfd,source,tfd,target)
    if source==name:state['captured']=True;state['tx_inode']=os.fstat(tfd).st_ino;events.append('capture')
    if source=='new':state['published']=True;events.append('publish')
    return out
   def injected_rename(fd,source,target):
    restoring=source.startswith('.friday-before-')
    if restoring and fault in ('restore-failure','restore-and-blocker-failure'):raise OSError('injected archive restore failure')
    out=rename(fd,source,target)
    if not restoring:
     state['archived']=True;events.append('archive')
     if fault=='archive-wrapper-after':raise OSError('injected after archive rename')
    elif fault=='restore-wrapper-after':raise OSError('injected after fixed fence restore')
    return out
   def injected_sync(fd):
    st=os.fstat(fd);kind='other'
    if st.st_ino==old_inode:kind='captured-inode-sync'
    elif st.st_ino==state['tx_inode']:kind='publish-tx-sync' if state['published'] else 'capture-tx-sync'
    elif st.st_ino==parent_inode:kind='archive-parent-sync' if state['archived'] else ('publish-parent-sync' if state['published'] else ('capture-parent-sync' if state['captured'] else 'initial-parent-sync'))
    events.append(kind)
    target=fault
    if fault in ('restore-wrapper-after','restore-collision','restore-failure','restore-and-blocker-failure','archive-parent-sync-persistent'):target='archive-parent-sync'
    if kind==target and (not state['faulted'] or fault=='archive-parent-sync-persistent'):
     state['faulted']=True
     if fault=='restore-collision':(root/('.friday-revision-'+hashlib.sha256(name.encode()).hexdigest()[:32])).mkdir(mode=0o700)
     raise OSError('injected '+kind)
    return sync(fd)
   def injected_mkdir(path,*args,**kwargs):
    if fault=='restore-and-blocker-failure' and state['archived'] and str(path).startswith('.friday-revision-'):raise OSError('injected blocker recreation failure')
    return mkdir(path,*args,**kwargs)
   with monkeypatch.context() as m:
    m.setattr(rev,'_move',injected_move);m.setattr(rev,'_rename',injected_rename);m.setattr(os,'fsync',injected_sync);m.setattr(os,'mkdir',injected_mkdir)
    result=tools(a,'write_file',name,'REVISED')
   if fault=='none':
    assert result['success'] and result['verified'] and result['previous_version_preserved']
    assert p.read_text()=='REVISED'
    assert events.index('capture')<events.index('captured-inode-sync')<events.index('capture-tx-sync')<events.index('capture-parent-sync')<events.index('publish')<events.index('publish-tx-sync')<events.index('publish-parent-sync')<events.index('archive')<events.index('archive-parent-sync')
    assert (root/('.friday-before-'+result['revision_ref'])/'before').read_text()=='ORIGINAL'
   elif fault in ('captured-inode-sync','capture-tx-sync','capture-parent-sync'):
    assert not result['success'] and p.read_text()=='ORIGINAL' and result['effect_disposition']=='none'
    assert not list(root.glob('.friday-before-*')) and not list(root.glob('.friday-revision-*'))
   else:
    assert not result['success'] and result['effect_disposition']=='unknown' and p.read_text()=='REVISED'
    tag=hashlib.sha256(name.encode()).hexdigest()[:32]
    refs=[root/('.friday-revision-'+result['recovery_ref']),root/('.friday-before-'+result['recovery_ref'])]
    assert any((r/'before').is_file() and (r/'before').read_text()=='ORIGINAL' for r in refs)
    assert (root/('.friday-revision-'+tag)).is_dir() or fault=='restore-and-blocker-failure'
    # Rereading after an unknown effect must not make an automatic replay legal.
    tools(a,'read_file',name);retry=tools(a,'write_file',name,'NO REPLAY')
    assert retry['error']=='file_revision_reconciliation_required' and p.read_text()=='REVISED'
   OBS[fault]={'result':result,'events':events,'current_exact':p.read_text(),'fixed_fence_exists':any(root.glob('.friday-revision-*')),'old_exact':any(x.read_text()=='ORIGINAL' for x in root.glob('.friday-*/before'))}
 finally:db.close()


