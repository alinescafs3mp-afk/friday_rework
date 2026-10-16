"""Scoped native DOCX/PDF extraction; run with native sources on PYTHONPATH."""
import io,json,zipfile,os,subprocess,importlib
from pathlib import Path
from unittest.mock import patch
import pytest
from file_native_fixture import env,entered,home,scope
from document_fixtures import docx,pdf
from tools import file_tools as ft,read_extract as re
from hermes_cli import friday_workspace_revision as rev


def put(env,name,data):
 p=home(env)/'workspace'/name;p.write_bytes(data);p.chmod(0o600);return p

def read(name,**kw):return json.loads(ft.read_file_tool(name,**kw))

def make_docx(text):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>')
 return b.getvalue()

@pytest.mark.parametrize('name,fixture,expected',[('report.docx',docx,'Own uploaded report'),('report.pdf',pdf,'Own uploaded PDF report')])
def test_real_native_own_document_no_install_hosted_temp_or_subprocess(env,monkeypatch,name,fixture,expected):
 import anydoc
 with entered(env):
  data=fixture();p=put(env,name,data)
  with patch.object(re,'_anydoc',side_effect=AssertionError('pm loader forbidden')),patch.object(re,'_temp_copy',side_effect=AssertionError('temp forbidden')),patch.object(subprocess,'run',side_effect=AssertionError('subprocess forbidden')),patch.object(anydoc,'_parse_hosted',side_effect=AssertionError('hosted forbidden')),patch.object(rev,'note_read',side_effect=AssertionError('binary coverage forbidden')):
   r=read(name);assert r['success'] and expected in r['content']
   assert r['extracted_document'] and r['format']==Path(name).suffix[1:]
   assert r['coverage']=='text_only; images_and_layout_not_covered'
   assert str(home(env)) not in json.dumps(r)
   assert read(str(p))==r
  assert p.read_bytes()==data

@pytest.mark.parametrize('name,fixture',[('report.docx',docx),('report.pdf',pdf)])
def test_document_paginated(env,name,fixture):
 with entered(env):
  put(env,name,fixture());r=read(name,limit=1)
  assert r['success'] and r['content'].startswith('1: ')
  assert read(name,offset=999)['content']==''

def test_low_serialized_budget_and_char_continuation(env,monkeypatch):
 from agent import bounded_context as bc
 text='é漢字🙂'*300
 with entered(env):
  put(env,'long.docx',make_docx(text));monkeypatch.setattr(bc,'bounded_tool_result_budget',lambda:500)
  n=1;c=0;out='';calls=0
  while True:
   raw=ft.read_file_tool('long.docx',offset=n,char_offset=c)
   assert bc.serialized_bytes(raw)<=500
   r=json.loads(raw);assert r['success'];out+=r['content'].partition(': ')[2];calls+=1
   if not r['partial']:break
   assert (r['next_offset'],r['next_char_offset'])!=(n,c)
   n,c=r['next_offset'],r['next_char_offset'];assert calls<100
  assert out==text

@pytest.mark.parametrize('kind',['foreign','symlink','hardlink','revoked','oversize','traversal','private'])
def test_document_boundary_denials(env,kind):
 with entered(env) as cap:
  p=put(env,'report.docx',docx());name='report.docx'
  if kind=='foreign':name=str(home(env,'2')/'workspace/report.docx')
  elif kind=='symlink':p.unlink();p.symlink_to(home(env,'2')/'workspace/report.docx')
  elif kind=='hardlink':os.link(p,p.with_name('second.docx'))
  elif kind=='revoked':cap.revoked=True
  elif kind=='oversize':p.write_bytes(b'x'*1000001)
  elif kind=='traversal':name='../report.docx'
  elif kind=='private':name=str(home(env)/'config.yaml')
  assert read(name)=={'success':False,'error':'product_user_scope_refused'}

def test_revocation_during_parse_discards_output(env,monkeypatch):
 original=re.extract_scoped_document_bytes
 with entered(env) as cap:
  put(env,'report.docx',docx())
  def convert(*args):
   text=original(*args);cap.revoked=True;return text
  monkeypatch.setattr(re,'extract_scoped_document_bytes',convert)
  assert read('report.docx')=={'success':False,'error':'product_user_scope_refused'}

@pytest.mark.parametrize('name,data,reason',[('bad.docx',b'bad','malformed_or_required_part_limit'),('bad.pdf',b'bad','malformed_or_unsupported'),('expand.docx',make_docx('A'*2000000),'malformed_or_required_part_limit'),('xml.docx',make_docx('<bad>'),'malformed_or_required_part_limit')])
def test_malformed_expansion_typed(env,name,data,reason):
 with entered(env):
  put(env,name,data);r=read(name)
  assert r=={'success':False,'error':'document_extraction_failed','format':Path(name).suffix[1:],'reason':reason}


def test_required_xml_only_no_unrelated_zip_expansion(env):
 b=io.BytesIO(docx())
 with zipfile.ZipFile(b,'a',zipfile.ZIP_DEFLATED) as z:z.writestr('unused.bin',b'Z'*2000000)
 with entered(env):
  put(env,'report.docx',b.getvalue());assert read('report.docx')['success']

def test_missing_pdf_dependency_is_typed_without_install(env,monkeypatch):
 original=importlib.import_module
 def load(name,*a,**kw):
  if name=='anydoc':raise ModuleNotFoundError('synthetic absence')
  return original(name,*a,**kw)
 with entered(env):
  put(env,'report.pdf',pdf());monkeypatch.setattr(re.importlib,'import_module',load)
  assert read('report.pdf')['reason']=='missing_local_converter'


def test_real_blank_pdf_honest_no_text_or_needs_ocr(env):
 data=pdf().replace(b'(Own uploaded PDF report)',b'(                       )')
 # Same stream length and offsets preserve the real PDF container.
 with entered(env):
  put(env,'blank.pdf',data);r=read('blank.pdf')
  assert not r['success'] and r['error']=='document_extraction_failed'
  assert r['reason'] in ('needs_ocr','no_extractable_text')

@pytest.mark.parametrize('name,data',[('report.docx',docx()),('report.pdf',pdf()),('utf.docx',b'UTF8 fake office'),('utf.pdf',b'%PDF-1.4 fake UTF8')])
def test_binary_format_never_written_or_created(env,name,data):
 with entered(env):
  p=put(env,name,data);read(name)
  result=json.loads(ft.write_file_tool(name,'DESTROY'))
  assert result['error']=='document_write_unsupported' and p.read_bytes()==data
  new='new'+Path(name).suffix
  assert json.loads(ft.write_file_tool(new,'FAKE'))['error']=='document_write_unsupported'
  assert not p.with_name(new).exists()


def test_actual_native_call_cannot_stage_binary_read_authority(env):
 from test_read_delivery import actor,dispatch,commit,transport,TASK
 from agent import tool_executor as te
 from tools.budget_config import DEFAULT_BUDGET
 with entered(env):
  data=docx();p=put(env,'report.docx',data);a=actor();ref,out=dispatch(a,'read_file',{'path':'report.docx'},'read-doc')
  assert json.loads(out.result)['success'];call=a._tool_result_calls[(TASK,'read-doc')]
  assert not getattr(call,'_workspace_read',None)
  m=[];commit(a,m,ref,out);te._finalize_tool_batch(a,m,TASK,1,DEFAULT_BUDGET)
  with pytest.MonkeyPatch.context() as mp:transport(a,m,mp)
  assert rev._baseline(scope.current(),TASK,'report.docx') is None
  assert p.read_bytes()==data

def test_real_image_only_pdf_reports_needs_ocr_without_hosted(env):
 import anydoc
 from document_fixtures import scanned_pdf
 with entered(env):
  put(env,'scanned.pdf',scanned_pdf())
  with patch.object(anydoc,'_parse_hosted',side_effect=AssertionError('hosted forbidden')),patch.object(subprocess,'run',side_effect=AssertionError('subprocess forbidden')):
   result=read('scanned.pdf')
  assert result=={'success':False,'error':'document_extraction_failed','format':'pdf','reason':'needs_ocr'}

@pytest.mark.parametrize('kind',['missing','compression','permission'])
def test_more_required_part_and_owner_boundaries(env,kind):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_BZIP2 if kind=='compression' else zipfile.ZIP_DEFLATED) as z:
  z.writestr('wrong.xml' if kind=='missing' else 'word/document.xml',b'<w:document/>')
 with entered(env):
  p=put(env,'report.docx',b.getvalue())
  if kind=='permission':p.chmod(0o644)
  result=read('report.docx')
  assert not result['success']
  assert result['error']==('product_user_scope_refused' if kind=='permission' else 'document_extraction_failed')


def test_snapshot_is_exact_immutable_bytes_and_no_path_reopen_in_converter(env,monkeypatch):
 original=re.extract_scoped_document_bytes
 with entered(env):
  data=docx();p=put(env,'report.docx',data)
  def convert(snapshot,format):
   assert type(snapshot) is bytes and snapshot==data
   # Conversion consumes the obtained snapshot, never the named file again.
   p.write_bytes(b'changed after snapshot')
   return original(snapshot,format)
  monkeypatch.setattr(re,'extract_scoped_document_bytes',convert)
  assert 'Own uploaded report' in read('report.docx')['content']


def test_document_no_budget_uses_existing_renderer_continuation(env):
 text='A'*110000
 with entered(env):
  put(env,'large.docx',make_docx(text));first=read('large.docx')
  assert first['success'] and first['partial'] and first['next_char_offset']>0
  second=read('large.docx',offset=first['next_offset'],char_offset=first['next_char_offset'])
  assert not second['partial']
  assert first['content'].partition(': ')[2]+second['content'].partition(': ')[2]==text

@pytest.mark.parametrize('repetitions,allowed',[(20,True),(30,False)])
def test_docx_xml_entities_and_utf8_output_bound(env,repetitions,allowed):
 entity='é'*20000
 xml='<!DOCTYPE document [<!ENTITY big "'+entity+'">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+'&big;'*repetitions+'</w:t></w:r></w:p></w:body></w:document>'
 assert len(xml.encode())<1000000
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('word/document.xml',xml)
 with entered(env):
  put(env,'entities.docx',b.getvalue());r=read('entities.docx')
  assert r['success'] is allowed
  if allowed:
   assert r['partial'] and 'é' in r['content']
   assert re.extract_scoped_document_bytes(b.getvalue(),'docx')==entity*repetitions+'\n'
  else:assert r['reason']=='extracted_text_limit'


def test_corrupt_deflate_required_part_still_typed_format_failure(env):
 import struct
 data=bytearray(docx())
 start=30+struct.unpack_from('<H',data,26)[0]+struct.unpack_from('<H',data,28)[0]
 data[start:start+8]=b'\xff'*8
 with entered(env):
  p=put(env,'corrupt.docx',bytes(data));r=read('corrupt.docx')
  assert r=={'success':False,'error':'document_extraction_failed','format':'docx','reason':'malformed_or_required_part_limit'}
  assert p.read_bytes()==bytes(data)
