"""Isolated synthetic source checks; no admitted profile, service or network."""
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
import time
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source'))
from hermes_cli import friday_workspace_docx as docx
from hermes_cli import friday_user_scope as scope
from hermes_cli import friday_prompt_scope as prompt
from agent.web_call_context import _current

W=docx._W
observations=[]
def check(name,condition):
    observations.append({'name':name,'passed':bool(condition)})
    assert condition,name
def denied(name,fn):
    try: fn()
    except scope.ScopeDenied: check(name,True)
    else: check(name,False)
def read_document(data):
    with ZipFile(BytesIO(data)) as archive:
        check('zip_crc_valid',archive.testzip() is None)
        return ET.fromstring(archive.read('word/document.xml'))
def text(node): return ''.join(n.text or '' for n in node.iter(W+'t'))

rows=[['Статья','Сумма'],['Материалы','1200'],['Работа','800'],['Итого','2000']]
blocks=[{'type':'title','text':'Проверка документа'},
        {'type':'heading','level':1,'text':'Цель'},
        {'type':'paragraph','text':'Проверить создание документа'},
        {'type':'heading','level':1,'text':'Данные'},
        {'type':'table','rows':rows},
        {'type':'heading','level':1,'text':'Решение'},
        {'type':'paragraph','text':'Документ подготовлен'}]
content=json.dumps({'blocks':blocks},ensure_ascii=False)
data=docx.render(content,structured=True)
body=read_document(data).find(W+'body')
check('body_order_exact',[n.tag for n in body]==[W+'p',W+'p',W+'p',W+'p',W+'tbl',W+'p',W+'p',W+'sectPr'])
paragraphs=body.findall(W+'p')
check('exact_title_and_paragraph_text',[text(n) for n in paragraphs]==['Проверка документа','Цель','Проверить создание документа','Данные','Решение','Документ подготовлен'])
check('real_title_style',paragraphs[0].find(W+'pPr/'+W+'pStyle').get(W+'val')=='Title')
headings=[p for p in paragraphs if p.find(W+'pPr/'+W+'outlineLvl') is not None]
check('three_real_outline_headings',[text(n) for n in headings]==['Цель','Данные','Решение'] and all(n.find(W+'pPr/'+W+'outlineLvl').get(W+'val')=='0' for n in headings))
tables=body.findall(W+'tbl')
check('one_real_4_by_2_table',len(tables)==1 and [[text(cell) for cell in row.findall(W+'tc')] for row in tables[0].findall(W+'tr')]==rows)
check('table_grid_has_two_columns',len(tables[0].findall(W+'tblGrid/'+W+'gridCol'))==2)
with ZipFile(BytesIO(data)) as out, ZipFile(BytesIO(__import__('base64').b64decode((ROOT/'source/hermes_cli/friday_plain_docx_template.b64').read_bytes()))) as template:
    check('other_package_parts_unchanged',out.namelist()==template.namelist() and all(out.read(name)==template.read(name) for name in out.namelist() if name!='word/document.xml'))

plain='# Проверка документа\n## Цель\nСтатья\tСумма\n{"blocks":[]}'
plain_body=read_document(docx.render(plain)).find(W+'body')
check('plain_markdown_tabs_json_remain_literal',[text(p) for p in plain_body.findall(W+'p')]==plain.split('\n') and not plain_body.findall(W+'tbl') and all(p.find(W+'pPr') is None for p in plain_body.findall(W+'p')))
check('plain_newline_normalization',[text(p) for p in read_document(docx.render('a\r\nb\rc')).findall(W+'body/'+W+'p')]==['a','b','c'])
original_spec=importlib.util.spec_from_file_location('original_docx',ROOT/'original/hermes_cli/friday_workspace_docx.py')
original_docx=importlib.util.module_from_spec(original_spec)
original_spec.loader.exec_module(original_docx)
check('legacy_plain_docx_bytes_equal_beforeimage',all(docx.render(value)==original_docx.render(value) for value in [plain,'','a\r\nb\rc','<tag>& \ttext','я'*50000]))
with ZipFile(BytesIO(data)) as archive:
    styles=ET.fromstring(archive.read('word/styles.xml'))
    ids={style.get(W+'styleId') for style in styles.findall(W+'style')}
    check('referenced_styles_exist_in_checked_template',{'Title','Heading1','Heading9','TableGrid'}<=ids)
for name,value in [
    ('malformed_json','{'),('plain_text_not_inferred',plain),
    ('duplicate_json_keys','{"blocks":[],"blocks":[]}'),
    ('unknown_root_key','{"blocks":[],"url":"https://example.invalid"}'),
    ('empty_blocks','{"blocks":[]}'),
    ('unknown_block_type',json.dumps({'blocks':[{'type':'xml','text':'<w:p/>'}]})),
    ('extra_block_key',json.dumps({'blocks':[{'type':'paragraph','text':'x','source':'secret'}]})),
    ('bad_heading_level',json.dumps({'blocks':[{'type':'heading','level':True,'text':'x'}]})),
    ('heading_zero',json.dumps({'blocks':[{'type':'heading','level':0,'text':'x'}]})),
    ('heading_ten',json.dumps({'blocks':[{'type':'heading','level':10,'text':'x'}]})),
    ('ragged_table',json.dumps({'blocks':[{'type':'table','rows':[['x','y'],['z']]}]})),
    ('numeric_cell',json.dumps({'blocks':[{'type':'table','rows':[['x',800]]}]})),
    ('empty_table',json.dumps({'blocks':[{'type':'table','rows':[]}]})),
    ('too_many_columns',json.dumps({'blocks':[{'type':'table','rows':[['']*33]}]})),
    ('too_many_cell_paragraphs',json.dumps({'blocks':[{'type':'table','rows':[['']*32]*63}]})),
    ('too_many_blocks',json.dumps({'blocks':[{'type':'paragraph','text':''}]*2001})),
    ('decoded_xml_control','{"blocks":[{"type":"paragraph","text":"\\u0000"}]}'),
    ('decoded_unpaired_surrogate','{"blocks":[{"type":"paragraph","text":"\\ud800"}]}'),
    ('json_too_deep','['*1100+']'*1100),
    ('raw_oversize','x'*100001),
    ('utf8_oversize','я'*50001),
]: denied(name,lambda value=value:docx.render(value,structured=True))
denied('plain_paragraph_limit',lambda:docx.render('\n'*2000))
denied('plain_control_refused',lambda:docx.render('\x00'))
special=docx.render(json.dumps({'blocks':[{'type':'paragraph','text':'<tag>&\nnext\tcell'},{'type':'heading','level':9,'text':'Deep'}]}),structured=True)
special_body=read_document(special).find(W+'body')
check('xml_is_text_not_injection',text(special_body[0])=='<tag>&nextcell' and len(special_body[0].findall('.//'+W+'br'))==1 and len(special_body[0].findall('.//'+W+'tab'))==1)
check('heading_nine_outline_eight',special_body[1].find(W+'pPr/'+W+'outlineLvl').get(W+'val')=='8')

fixture=ROOT/'fixture-home'
fixture.mkdir(mode=0o700)
(fixture/'workspace').mkdir(mode=0o700)
class Capability:
    home=fixture
    directory_identity=(fixture.stat().st_dev,fixture.stat().st_ino)
    valid=True
    def check(self):
        if not self.valid: raise scope.ScopeDenied()
        return self
cap=Capability()
fd=scope._workspace_directory(cap)
try:
    result=json.loads(docx.create(cap,fd,'report.docx','report.docx',content,structured=True))
    check('real_create_verified',result.get('success') and result.get('verified') and result.get('create_only') and result.get('format')=='docx')
    created=(fixture/'workspace/report.docx').read_bytes()
    check('created_bytes_match_render',created==data and hashlib.sha256(created).hexdigest()==result['sha256'])
    again=json.loads(docx.create(cap,fd,'report.docx','report.docx','do not overwrite'))
    check('existing_document_refused_intact',again.get('error')=='document_already_exists' and (fixture/'workspace/report.docx').read_bytes()==created)
    (fixture/'workspace/link.docx').symlink_to('report.docx')
    link=json.loads(docx.create(cap,fd,'link.docx','link.docx',content,structured=True))
    check('existing_symlink_refused_intact',link.get('error')=='document_already_exists' and (fixture/'workspace/link.docx').is_symlink())
    denied('traversal_refused',lambda:docx.create(cap,fd,'escape.docx','../escape.docx',content,structured=True))
    cap.valid=False
    denied('revoked_capability_refused',lambda:docx.create(cap,fd,'revoked.docx','revoked.docx',content,structured=True))
    cap.valid=True
    check('no_stage_residue',not any(p.name.startswith('.friday-') for p in (fixture/'workspace').iterdir()))
    # Exercise native NOREPLACE publication against a race, without replacing it.
    native_move=docx._move
    def race(*args):
        (fixture/'workspace/race.docx').write_bytes(b'concurrent owner')
        os.chmod(fixture/'workspace/race.docx',0o600)
        return native_move(*args)
    docx._move=race
    raced=json.loads(docx.create(cap,fd,'race.docx','race.docx',content,structured=True))
    docx._move=native_move
    check('noreplace_race_preserves_other_writer',not raced['success'] and raced['effect_disposition']=='none' and (fixture/'workspace/race.docx').read_bytes()==b'concurrent owner')
    check('race_no_stage_residue',not any(p.name.startswith('.friday-') for p in (fixture/'workspace').iterdir()))
finally:
    os.close(fd)
    shutil.rmtree(fixture)

schema_tree=ast.parse((ROOT/'source/tools/file_tools.py').read_text())
schema=next(ast.literal_eval(n.value) for n in schema_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='WRITE_FILE_SCHEMA' for t in n.targets))
check('schema_exposes_explicit_mode','docx_structured' in schema['parameters']['properties']['format']['enum'])
token=scope._CURRENT.set(cap)
try:
    adapted=prompt.ordinary_file_schema({'function':schema})
finally: scope._CURRENT.reset(token)
check('actual_ordinary_schema_teaches_blocks','format=docx_structured' in adapted['function']['description'] and '"type":"table"' in adapted['function']['description'])
check('all_local_imports_own_source',all(not getattr(module,'__file__','') or str(ROOT/'source') in module.__file__ for name,module in sys.modules.items() if name.startswith(('hermes_cli','tools.','agent.'))))
report={'assignment':'FRW-R116-DOCX-STRUCTURED-CREATION-SOURCE-FIX','observations':observations,'passed':all(r['passed'] for r in observations),'native_pm_processes_this_run':1,'live_or_network_calls':0,'fixture_home_removed':not fixture.exists(),'generated_docx_sha256':hashlib.sha256(data).hexdigest(),'generated_docx_bytes':len(data),'limitations':['isolated direct renderer/create tests with synthetic capability; no admitted native profile or model inference','schema inspected and ordinary schema adaptation executed; full write_file tool dispatch not executed','source-only; no installation, runtime or deployed semantic acceptance']}
(ROOT/'TEST-RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'checks':len(observations),'fixture_removed':report['fixture_home_removed'],'docx_sha256':report['generated_docx_sha256']}))
