"""Source-only transaction controls. Every home and process effect is synthetic."""
import copy,json,os,stat
from pathlib import Path
import pytest
from test_ordinary_dsh_project_update import installed,doc,put,snapshot
from scripts import friday_install as f
from scripts import friday_ordinary_install as o
from scripts.install_containment import Budget
BASE=Path(o.__file__).resolve().parents[1]

@pytest.fixture
def dashboard(installed,monkeypatch):
 s=installed;home=s['home'];root=s['root'];source=s['source']
 previous=copy.deepcopy(s['current']);old=previous['project_files']
 before={n:('# synthetic reviewed prior dashboard '+n+'\n').encode() for n in o.PROJECT_DASHBOARD_BEFORE}
 monkeypatch.setattr(o,'PROJECT_DASHBOARD_BEFORE',{n:f.digest(v) for n,v in before.items()})
 for n,data in before.items():old[n]=put(root/n,data)['sha256'];put(home/n,data)
 helper='scripts/friday_ordinary_install.py';old[helper]=put(root/helper,b'# synthetic previous updater\n')['sha256']
 for i in range(253-len(old)):
  n=f'config/source90-preserved-{i}';old[n]=put(root/n,b'unchanged Source90\n')['sha256']
 previous['product'].update(inference={'key_env':'FRIDAY_LLM_API_KEY'},compression_inference={'key_env':'FRIDAY_COMPRESSION_API_KEY'},compression_multipass={'enabled':True})
 for n in old:
  if n.startswith('plugins/'):put(home/n,(root/n).read_bytes())
 oldref=doc(s['requestpath'].with_name('source90-input.json'),previous)
 monkeypatch.setattr(o,'PROJECT_DASHBOARD_PROJECT_SHA256',f.digest(o.encoded(old)))
 s['receipt']['layers'][:]=s['receipt']['layers'][:76]+[{'manifest':f'fixture-prior-{i}'} for i in range(13)]+[{'manifest':'patches/hermes/ordinary-coherent-memory-skills-source90-manifest.json'}]
 receiptref=doc(home/'hermes-agent.source.json',s['receipt']);monkeypatch.setattr(o,'PROJECT_DASHBOARD_RECEIPT_SHA256',receiptref['sha256']);monkeypatch.setattr(o,'PROJECT_DASHBOARD_NATIVE_FILES',len(s['receipt']['files']))
 source_request={'schema':'friday.ordinary-telegram-source-update.v44','home':str(home),'previous_input':s['request']['previous_input'],'current_input':oldref,'transaction_history':copy.deepcopy(s['request']['transaction_history']),'predecessor_update':s['request']['predecessor_update']}
 source_ref=doc(s['requestpath'].with_name('source90-request.json'),source_request)
 tx=home/'preparation'/('ordinary-source-update-'+source_request['previous_input']['sha256'])
 doc(tx/'intent.json',{'schema':'friday.ordinary-telegram-source-update-transaction.v1','state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':source_ref['sha256']})
 doc(tx/'committed.json',{'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED','previous_input':source_request['previous_input'],'current_input':oldref,'source_receipt_sha256':receiptref['sha256'],'gateway_started':False,'workers_enabled':False})
 put(tx/'before/preserved',b'original closed clock and Source90 proof\n')
 marker=copy.deepcopy(s['marker']);marker.update(input_sha256=oldref['sha256'],source_receipt_sha256=receiptref['sha256'],plugin_files={n:h for n,h in old.items() if n.startswith('plugins/')})
 marker['ordinary_gateway']['operator_entry']['input']=oldref;marker['ordinary_gateway']['source_receipt_sha256']=receiptref['sha256']
 before_marker=doc(home/f.MARKER,marker)
 latest=copy.deepcopy(previous);latest['product']['compression_inference']['exact_renderer']={'binding':{'path':str(root/'binding.json'),'sha256':'a'*64},'deployment':{'path':str(root/'deployment.json'),'sha256':'b'*64}}
 latestref=doc(s['requestpath'].with_name('latest-renderer-input.json'),latest)
 monkeypatch.setattr(o,'inference_renderer_references',lambda product:())
 before_names={f.MARKER,'config.yaml','profiles/dest_telegram/config.yaml','profiles/dest_telegram/.friday-onboarding.json','profiles/dest_telegram/.friday-user-scope.json'}
 for n in before_names-{'config.yaml',f.MARKER}:put(home/n,b'private retained fixture\n')
 before={n:{'path':str(home/n),'sha256':f.digest((home/n).read_bytes())} for n in before_names}
 renderer_retained={'FRIDAY-PROFILE.json':s['request']['profile'],'hermes-agent.source.json':receiptref,'hermes-agent/install-stamp.json':s['request']['stamp'],'hermes-agent/.hermes/bin/hermes':s['request']['launcher']}
 renderer={'schema':o.REBIND_RENDERER_SCHEMA,'home':str(home),'profile':'dest_telegram','seconds':180,'previous_input':oldref,'current_input':latestref,'before':before,'retained':renderer_retained,'native_unit':s['request']['native_unit']}
 rendererref=doc(s['requestpath'].with_name('renderer-request.json'),renderer)
 rtx=home/'preparation'/('ordinary-inference-rebind-'+oldref['sha256'])
 for n in before_names:put(rtx/'before'/n,(home/n).read_bytes())
 marker['input_sha256']=latestref['sha256'];marker['ordinary_gateway']['operator_entry']['input']=latestref
 markerref=doc(home/f.MARKER,marker)
 after={n:put(rtx/'stage'/n,(home/n).read_bytes())['sha256'] for n in before_names}
 put(rtx/'stage/FRIDAY-PROFILE.json',(home/'FRIDAY-PROFILE.json').read_bytes())
 put(rtx/'stage/config.yaml.lock',b'');put(rtx/'stage/profiles/dest_telegram/config.yaml.lock',b'')
 intent={'schema':o.REBIND_RENDERER_SCHEMA,'state':'CONSUMED_NO_RETRY','request_sha256':rendererref['sha256'],'seconds':180,'previous_input':oldref,'current_input':latestref,'before':{n:{'sha256':ref['sha256'],'mode':0o600} for n,ref in before.items()},'consumers_started':False,'workers_enabled':False,'database_changed':False}
 doc(rtx/'intent.json',intent);doc(rtx/'committed.json',{'state':'EXACT_COMPRESSOR_RENDERER_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED','ready':False,'workers_enabled':False,'consumers_started':False,'database_changed':False,'after':after})
 state='installs/'+f.digest(str(source).encode())[:16];environment=home/state/'environments/generation-fixture'
 facts={'schema':1,'packages':{'venv':{'environment':str(environment),'extras':[],
  'resolved_lock':str(home/state/'resolved.lock'),'source_identity':'synthetic-Source90',
  'source_parent':str(source.parent),'stamp':'synthetic-retained-generation'}}}
 factsref=doc(home/state/'facts.json',facts)
 pyvenvref=put(environment/'pyvenv.cfg',b'fixture interpreter never executed\n')
 retained={**renderer_retained,**{n:{'path':str(home/n),'sha256':h} for n,h in after.items() if n!=f.MARKER},state+'/facts.json':factsref,str(environment.relative_to(home))+'/pyvenv.cfg':pyvenvref}
 # Retain representative current private DB/WAL/session/artifacts without opening DBs.
 for n in ('data/retained.db-wal','profiles/dest_telegram/sessions/latest.json','profiles/dest_telegram/artifacts/latest.txt'):
  retained[n]=put(home/n,b'current fixture retained data\n')
 history={n:f.digest(data) for n,(data,mode) in snapshot(home).items() if n.startswith('preparation/')}
 current=copy.deepcopy(latest)
 for n in o.PROJECT_DASHBOARD_AFTER:current['project_files'][n]=put(root/n,(BASE/n).read_bytes())['sha256']
 current['project_files'][helper]=put(root/helper,Path(o.__file__).read_bytes())['sha256']
 request=copy.deepcopy(s['request']);request.update(schema=o.PROJECT_DASHBOARD_SCHEMA,previous_input=latestref,current_input=doc(s['requestpath'].with_name('dashboard-current.json'),current),marker=markerref,source_receipt=receiptref,predecessor_update=source_ref,transaction_history=history,rebind_updates=[rendererref],retained=retained)
 doc(s['requestpath'],request)
 @o.contextlib.contextmanager
 def locked(*a):
  yield lambda:s['events'].append('pm-proof')
 monkeypatch.setattr(o,'retained_pm_lock',locked)
 s.update(previous=latest,current=current,request=request,marker=marker,receiptref=receiptref,rtx=rtx,state=state,renderer=renderer,source_request=source_request,source_ref=source_ref,environment=environment)
 return s

def repin(s):
 s['request']['current_input']=doc(Path(s['request']['current_input']['path']),s['current']);doc(s['requestpath'],s['request'])

def test_exact_two_plugins_marker_and_retained_custody(dashboard):
 s=dashboard;before=snapshot(s['home']);states={n:o.update_file_state(s['home']/n) for n in before}
 result=o.update(s['request'],s['requestpath'],Budget(180));after=snapshot(s['home']);changed={n for n in before if before[n]!=after[n]}
 assert changed==set(o.PROJECT_DASHBOARD_AFTER)|{f.MARKER}
 assert all(o.update_file_state(s['home']/n)==state for n,state in states.items() if n not in changed)
 assert all(after[n][0]==(BASE/n).read_bytes() for n in o.PROJECT_DASHBOARD_AFTER)
 expected=copy.deepcopy(s['marker']);expected['input_sha256']=s['request']['current_input']['sha256'];expected['plugin_files'].update(o.PROJECT_DASHBOARD_AFTER);expected['ordinary_gateway']['operator_entry']['input']=s['request']['current_input']
 expected['ordinary_gateway']['operator_entry']['script']['sha256']=s['current']['project_files']['scripts/friday_native.py']
 assert f.read_json(s['home']/f.MARKER)==expected
 assert not (s['home']/'scripts').exists();assert 'pm-proof' in s['events'];assert result['ready'] is result['gateway_started'] is result['workers_enabled'] is False
 with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))

@pytest.mark.parametrize('fault',['extra','missing','third_plugin','wrong_typed','helper_wrong','helper_unchanged','oldmap','model','budget','runtimezero','newkey','source77','last_layer','nativecount','receipt','stamp','nativebytes','historymissing','historybytes','renderer_missing','renderer_order','renderer_commit','renderer_stage','renderer_before','predecessor','facts','selectedgeneration','omitfacts','omitgeneration','omit_user_scope','unit','profile','credentials'])
def test_refuses_drift_without_publication(dashboard,monkeypatch,fault):
 s=dashboard;r=s['request'];cur=s['current'];h=s['home'];helper='scripts/friday_ordinary_install.py'
 if fault=='extra':cur['project_files']['extra.py']=put(s['root']/'extra.py',b'extra')['sha256']
 elif fault=='missing':cur['project_files'].pop(next(n for n in cur['project_files'] if n.startswith('config/unchanged')))
 elif fault in ('third_plugin','wrong_typed'):
  n='plugins/friday_rework/unchanged.py' if fault=='third_plugin' else 'plugins/friday_rework/admin_settings.py';cur['project_files'][n]=put(s['root']/n,b'unreviewed')['sha256']
 elif fault=='helper_wrong':cur['project_files'][helper]=put(s['root']/helper,b'unreviewed helper')['sha256']
 elif fault=='helper_unchanged':cur['project_files'][helper]=s['previous']['project_files'][helper]
 elif fault=='oldmap':
  old=copy.deepcopy(s['previous']);old['project_files'][next(n for n in old['project_files'] if n.startswith('config/unchanged'))]='0'*64;r['previous_input']=doc(Path(r['previous_input']['path']),old)
 elif fault=='model':cur['model']='changed'
 elif fault=='budget':cur['seconds']=999
 elif fault=='runtimezero':
  cur['product']['runtime']['enabled']=0
 elif fault=='newkey':r['unknown']=True
 elif fault=='source77':s['receipt']['layers'][:]=s['receipt']['layers'][:77];r['source_receipt']=doc(h/'hermes-agent.source.json',s['receipt'])
 elif fault=='last_layer':s['receipt']['layers'][-1]['manifest']='wrong';r['source_receipt']=doc(h/'hermes-agent.source.json',s['receipt'])
 elif fault=='nativecount':monkeypatch.setattr(o,'PROJECT_DASHBOARD_NATIVE_FILES',999)
 elif fault=='receipt':put(h/'hermes-agent.source.json',b'changed')
 elif fault=='stamp':put(s['source']/'install-stamp.json',b'changed')
 elif fault=='nativebytes':put(s['source']/'retained.txt',b'changed')
 elif fault=='historymissing':r['transaction_history'].pop(next(iter(r['transaction_history'])))
 elif fault=='historybytes':put(h/next(n for n in r['transaction_history'] if n.endswith('/before/preserved')),b'changed')
 elif fault=='renderer_missing':r['rebind_updates']=[]
 elif fault=='renderer_order':r['rebind_updates']*=2
 elif fault in ('renderer_commit','renderer_stage','renderer_before'):
  n={'renderer_commit':'committed.json','renderer_stage':'stage/config.yaml','renderer_before':'before/config.yaml'}[fault];put(s['rtx']/n,b'changed')
 elif fault=='predecessor':
  d=copy.deepcopy(s['source_request']);d['schema']='friday.ordinary-telegram-source-update.v43';r['predecessor_update']=doc(Path(r['predecessor_update']['path']),d)
 elif fault=='facts':put(h/s['state']/'facts.json',b'changed')
 elif fault=='selectedgeneration':
  facts=f.read_json(h/s['state']/'facts.json');facts['packages']['venv']['environment']=str(h/s['state']/'environments/foreign');r['retained'][s['state']+'/facts.json']=doc(h/s['state']/'facts.json',facts)
 elif fault=='omitfacts':r['retained'].pop(s['state']+'/facts.json')
 elif fault=='omitgeneration':r['retained'].pop(str(s['environment'].relative_to(h))+'/pyvenv.cfg')
 elif fault=='omit_user_scope':r['retained'].pop('profiles/dest_telegram/.friday-user-scope.json')
 elif fault=='unit':put(Path(r['native_unit']['path']),b'changed')
 elif fault=='profile':put(h/'FRIDAY-PROFILE.json',b'changed')
 elif fault=='credentials':put(h/'.env',b'changed')
 repin(s);before=snapshot(h)
 with pytest.raises((ValueError,KeyError,AssertionError)):o.update(r,s['requestpath'],Budget(180))
 assert snapshot(h)==before


@pytest.mark.parametrize('fault',['root_malformed','schema','schema_boolean','top_level_only',
 'packages_missing','packages_malformed','venv_missing','venv_malformed',
 'environment_missing','environment_type','foreign_install','foreign_generation'])
def test_native_pm_facts_selection_refuses_malformed_missing_or_foreign(dashboard,fault):
 s=dashboard;home=s['home'];r=s['request'];name=s['state']+'/facts.json'
 facts=f.read_json(home/name)
 if fault=='root_malformed':facts=[]
 elif fault=='schema':facts['schema']=2
 elif fault=='schema_boolean':facts['schema']=True
 elif fault=='top_level_only':facts={'schema':1,'packages':{},'environment':str(s['environment'])}
 elif fault=='packages_missing':facts.pop('packages')
 elif fault=='packages_malformed':facts['packages']=[]
 elif fault=='venv_missing':facts['packages'].pop('venv')
 elif fault=='venv_malformed':facts['packages']['venv']=[]
 elif fault=='environment_missing':facts['packages']['venv'].pop('environment')
 elif fault=='environment_type':facts['packages']['venv']['environment']=None
 else:
  # A different extant generation is not authority to switch environments:
  # an outside-install generation stays refused even with an exact retained pin.
  selected=(home/'installs/foreign-install/environments/generation/venv' if fault=='foreign_install'
   else home/s['state']/'environments/foreign-generation/venv')
  config=put(selected/'pyvenv.cfg',b'synthetic unselected interpreter never executed\n')
  facts['packages']['venv']['environment']=str(selected)
  if fault=='foreign_install':r['retained'][str(selected.relative_to(home))+'/pyvenv.cfg']=config
 r['retained'][name]=doc(home/name,facts)
 repin(s);before=snapshot(home)
 reason=('latest_retained_scope_changed' if fault in ('foreign_install','foreign_generation')
  else 'native_pm_environment_required')
 with pytest.raises(ValueError,match=reason):o.update(r,s['requestpath'],Budget(180))
 assert snapshot(home)==before
 tx=home/'preparation'/('ordinary-source-update-'+r['previous_input']['sha256'])
 assert not(tx/'intent.json').exists()

@pytest.mark.parametrize('publication',[1,2,3,4])
def test_injected_failure_owned_rollback_and_once_intent(dashboard,monkeypatch,publication):
 s=dashboard;before=snapshot(s['home']);publish=o.publish_update_file;count=0
 def fail(*a,**kw):
  nonlocal count
  count+=1
  if publication<=3 and count==publication:raise RuntimeError('injected failure')
  return publish(*a,**kw)
 monkeypatch.setattr(o,'publish_update_file',fail)
 if publication==4:
  original=o.checked_plugin_inventory;injected=False
  def after(home,expected):
   nonlocal injected
   if not injected and f.read_json(home/f.MARKER)['input_sha256']==s['request']['current_input']['sha256']:
    injected=True;raise RuntimeError('injected failure')
   return original(home,expected)
  monkeypatch.setattr(o,'checked_plugin_inventory',after)
 with pytest.raises(RuntimeError,match='injected failure'):o.update(s['request'],s['requestpath'],Budget(180))
 assert all(snapshot(s['home'])[n]==row for n,row in before.items())
 tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256']);assert (tx/'rolled-back.json').exists();assert not(tx/'committed.json').exists()
 with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))

def test_late_cas_preserves_foreign_inode_and_consumes_intent(dashboard,monkeypatch):
 from scripts.dsh_prepare import StopUnconfirmed
 s=dashboard;publish=o.publish_update_file;target=s['home']/sorted(o.PROJECT_DASHBOARD_AFTER)[0];foreign={}
 def race(path,*a,**kw):
  result=publish(path,*a,**kw)
  if path==target and not foreign:
   other=path.with_name('foreign');put(other,path.read_bytes());os.replace(other,path);foreign['state']=o.update_file_state(path);raise RuntimeError('late foreign inode')
  return result
 monkeypatch.setattr(o,'publish_update_file',race)
 with pytest.raises(StopUnconfirmed):o.update(s['request'],s['requestpath'],Budget(180))
 assert o.update_file_state(target)==foreign['state']
 tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256']);assert(tx/'intent.json').exists();assert not(tx/'committed.json').exists();assert not(tx/'rolled-back.json').exists()
 with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))

def test_reviewed_source90_production_anchors():
 # Static public anchors constrain the source path; synthetic fixtures above
 # do not substitute for real receipts or current runtime admission.
 assert o.PROJECT_DASHBOARD_PROJECT_SHA256=='c47a8cad7932e557c06aaaac85d571c514e474b001e774e83e8b2619a107d58f'
 assert o.PROJECT_DASHBOARD_RECEIPT_SHA256=='d722d6bc33d045a8d0d6571e89c0cb9ea58bbb5f8230dff4b3b85b7c91ca39ab'
 assert o.PROJECT_DASHBOARD_NATIVE_FILES==17710
 assert len(o.PROJECT_DASHBOARD_BEFORE)==len(o.PROJECT_DASHBOARD_AFTER)==2
 for n,h in o.PROJECT_DASHBOARD_AFTER.items():assert f.digest((BASE/n).read_bytes())==h

@pytest.mark.parametrize('kind',['source','renderer'])
def test_unknown_partial_current_history_stops_before_publication(dashboard,kind):
 s=dashboard;name='ordinary-source-update-' if kind=='source' else 'ordinary-inference-rebind-'
 put(s['home']/'preparation'/(name+'f'*64)/'intent.json',b'unknown consumed partial transaction\n')
 before=snapshot(s['home'])
 with pytest.raises(ValueError,match='unaccounted_current_history'):o.update(s['request'],s['requestpath'],Budget(180))
 assert snapshot(s['home'])==before

def test_pm_generation_late_drift_remains_owned_by_foreign_writer(dashboard,monkeypatch):
 from scripts.dsh_prepare import StopUnconfirmed
 s=dashboard;publish=o.publish_update_file;foreign={};facts=s['home']/s['state']/'facts.json'
 def change(path,*args,**kw):
  out=publish(path,*args,**kw)
  if not foreign:
   put(facts,b'foreign PM selection\n');foreign['state']=o.update_file_state(facts)
  return out
 monkeypatch.setattr(o,'publish_update_file',change)
 with pytest.raises(StopUnconfirmed):o.update(s['request'],s['requestpath'],Budget(180))
 assert o.update_file_state(facts)==foreign['state']
 tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
 assert(tx/'intent.json').exists();assert not(tx/'committed.json').exists();assert not(tx/'rolled-back.json').exists()

def test_custody_cleanup_failure_keeps_committed_intent_and_stops(dashboard,monkeypatch):
 from scripts.dsh_prepare import StopUnconfirmed
 s=dashboard
 @o.contextlib.contextmanager
 def cleanup(*args):
  yield lambda:None
  raise StopUnconfirmed('synthetic PM cleanup failure')
 monkeypatch.setattr(o,'retained_pm_lock',cleanup)
 with pytest.raises(StopUnconfirmed,match='cleanup failure'):o.update(s['request'],s['requestpath'],Budget(180))
 tx=s['home']/'preparation'/('ordinary-source-update-'+s['request']['previous_input']['sha256'])
 assert(tx/'intent.json').exists() and(tx/'committed.json').exists();assert not(tx/'rolled-back.json').exists()
 assert f.read_json(tx/'committed.json')['state']=='SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
 with pytest.raises(ValueError):o.update(s['request'],s['requestpath'],Budget(180))
