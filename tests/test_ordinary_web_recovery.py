"""Ordinary web text stays recoverable through private scoped file I/O."""
import json,os,pathlib,types,uuid
from contextlib import contextmanager
from hermes_cli import friday_user_scope as us,friday_product_access as pa
from tools import web_tools_truncate as new
import hermes_constants as hc

def test_ordinary_web_page_is_recoverable_and_isolated(tmp_path,monkeypatch):
    ROOT=tmp_path
    # Restore native policy entrypoints after this isolated two-user fixture.
    monkeypatch.setattr(pa,'settings',pa.settings)
    monkeypatch.setattr(pa,'current_access',pa.current_access)
    checks={}
    def cap_for(label,uid):
     home=ROOT/label;home.mkdir(mode=0o700)
     for n in ('workspace','memories'):(home/n).mkdir(mode=0o700)
     principal=('telegram','transport','fixture-bot',uid)
     binding=dict(zip(('platform','transport_profile','account_id','user_id'),principal))|{'runtime_profile':label,'tools':['web_search','web_extract','read_file','write_file']}
     key=pa.principal_id(*principal)
     marker={'schema':'friday.user-home.v1','principal':key,'profile':label,'binding_sha256':us._fingerprint(binding)}
     (home/us.MARKER).write_text(json.dumps(marker));(home/us.MARKER).chmod(0o600)
     st=home.stat();return us.UserScope(ROOT,home,label,principal,binding,(st.st_dev,st.st_ino),admission_generation=1)
    a=cap_for('user_a','a');b=cap_for('user_b','b');caps=[a,b]
    settings={'user_isolation':{'enabled':True,'bindings':[c.binding for c in caps]},'product_access':{'enabled':True,'accounts':[{'platform':'telegram','transport_profile':'transport','account_id':'fixture-bot','runtime_profiles':['user_a','user_b']}]}}
    access={'schema':'product_access.v1','users':{c.key:{'platform':c.principal[0],'transport_profile':c.principal[1],'account_id':c.principal[2],'user_id':c.principal[3],'enabled':True,'role':'user','generation':1} for c in caps}}
    pa.settings=lambda:settings
    pa.current_access=lambda:access
    from contextlib import contextmanager
    @contextmanager
    def active(cap):
     token=us._CURRENT.set(cap)
     try:
      with us.authority(cap.home):yield
     finally:us._CURRENT.reset(token)
    def denied(fn):
     try:fn()
     except (us.ScopeDenied,OSError):return True
     raise AssertionError('operation unexpectedly permitted')
    def saved_path(out):return next(s.split(': ',1)[1] for s in out.splitlines() if s.startswith(('Full text saved to:','Partial text saved to:')))
    body='\n'.join(f'row {i}: finite synthetic public source text' for i in range(5000))
    with active(a):
     out,truncated=new._truncate_with_footer(body,'https://example.test/doc',20000);p=saved_path(out)
     assert pathlib.Path(p).parent==a.home/'workspace';assert pathlib.Path(p).read_text()==body
     result=json.loads(us.scoped_file('read_file',{'path':p,'offset':2401,'limit':3}));assert result['success'] and 'row 2400:' in result['content'];assert 'complete page' in out
     assert pathlib.Path(p).stat().st_mode & 0o777==0o600
     checks['new_actual_scoped_file_pages_complete_own_user_spill']=True
     out2,_=new._truncate_with_footer(body,'https://example.test/doc',20000);assert saved_path(out2)!=p and pathlib.Path(p).read_text()==body
     checks['repeat_extraction_create_only_unique_private']=True
     huge='я'*600000
     out,_=new._truncate_with_footer(huge,'https://example.test/huge',20000);q=saved_path(out);data=pathlib.Path(q).read_bytes()
     assert len(data)<=1000000 and 'stored copy truncated' in data.decode() and 'incomplete' in out and 'complete page' not in out
     assert json.loads(us.scoped_file('read_file',{'path':q,'offset':1,'limit':2}))['success']
     checks['unicode_byte_bound_and_partial_copy_explicit']=True
     assert denied(lambda:us.scoped_file('read_file',{'path':str(a.home/'cache/web/escape.md')}))
     assert denied(lambda:us.scoped_file('read_file',{'path':str(a.home/'workspace'/'..'/pathlib.Path(p).name)}))
     checks['cache_and_dotdot_refused']=True
     foreign=b.home/'workspace/foreign.txt';foreign.write_text('foreign');foreign.chmod(0o600)
     assert denied(lambda:us.scoped_file('read_file',{'path':str(foreign)}))
     checks['foreign_user_path_refused']=True
     link=a.home/'workspace/link';link.symlink_to(foreign)
     assert denied(lambda:us.scoped_file('read_file',{'path':str(link)}));link.unlink()
     hard=a.home/'workspace/hard';os.link(foreign,hard)
     assert denied(lambda:us.scoped_file('read_file',{'path':str(hard)}));hard.unlink()
     checks['symlink_and_hardlink_refused']=True
     real=a.home/'workspace/nested';real.mkdir(mode=0o700);(real/'value').write_text('hidden');(real/'value').chmod(0o600)
     alias=a.home/'workspace/alias';alias.symlink_to(real,target_is_directory=True)
     assert denied(lambda:us.scoped_file('read_file',{'path':str(alias/'value')}));alias.unlink()
     checks['ancestor_symlink_refused']=True
     # Existing UUID names must not overwrite files, links or hardlinks.
     fixed='0'*32;target=a.home/'workspace'/('web-extract-'+fixed+'.md');target.write_text('KEEP');target.chmod(0o600)
     original_uuid=uuid.uuid4;monkeypatch.setattr(uuid,'uuid4',lambda:types.SimpleNamespace(hex=fixed))
     assert new._store_full_text('https://example.test/collision',body) is None and target.read_text()=='KEEP'
     target.unlink();target.symlink_to(foreign);assert new._store_full_text('https://example.test/collision',body) is None and foreign.read_text()=='foreign';target.unlink()
     os.link(foreign,target);assert new._store_full_text('https://example.test/collision',body) is None and foreign.read_text()=='foreign';target.unlink();uuid.uuid4=original_uuid
     checks['create_only_file_symlink_hardlink_collisions_refused']=True
     # Filesystem attack: replace actual workspace with a symlink; no output outside.
     workspace=a.home/'workspace';moved=a.home/'saved-workspace';workspace.rename(moved);workspace.symlink_to(b.home/'workspace',target_is_directory=True)
     assert new._store_full_text('https://example.test/attack',body) is None
     workspace.unlink();moved.rename(workspace)
     # A failed cap check is sticky. Restore only in fixture for the next distinct control.
     assert a.revoked;a.revoked=False
     checks['workspace_ancestor_replacement_refused_no_foreign_write']=True
     assert list((b.home/'workspace').iterdir())==[foreign]
     # Post-write revocation is exercised by the real scoped_file check, not a stubbed writer.
     real_check=a.check;calls=[0]
     def revoke_during_io():
      calls[0]+=1
      if set(workspace.iterdir()) != before:access['users'][a.key]['enabled']=False
      return real_check()
     a.check=revoke_during_io
     before=set(workspace.iterdir());assert new._store_full_text('https://example.test/revoke',body) is None and a.revoked
     assert len(set(workspace.iterdir())-before)==1, 'revocation must occur after the create, not merely before I/O'
     assert denied(lambda:us.scoped_file('read_file',{'path':p}));a.check=real_check
     checks['revocation_fails_closed_without_global_cache_fallback']=True
     # Restore authoritative synthetic fixture for independent read checks.
     access['users'][a.key]['enabled']=True;a.revoked=False
     too_big=workspace/'too-big';too_big.write_bytes(b'x'*1000001);too_big.chmod(0o600)
     assert denied(lambda:us.scoped_file('read_file',{'path':str(too_big)}))
     public=workspace/'public';public.write_text('public');public.chmod(0o644)
     assert denied(lambda:us.scoped_file('read_file',{'path':str(public)}))
     checks['existing_read_size_and_permissions_limits_preserved']=True
    # Unmanaged legacy repeats same URL in cache with original replacement behavior.
    pa.settings=lambda:{}
    legacy=ROOT/'legacy';legacy.mkdir(mode=0o700)
    with us.authority(legacy):
     x=new._store_full_text('https://example.test/legacy','first');y=new._store_full_text('https://example.test/legacy','second')
     assert x==y and pathlib.Path(y).read_text()=='second' and pathlib.Path(y).parent==hc.get_hermes_dir('cache/web','web_cache')
     checks['legacy_unmanaged_cache_repeat_behavior_preserved']=True
