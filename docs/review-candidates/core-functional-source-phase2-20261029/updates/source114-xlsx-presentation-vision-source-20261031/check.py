#!/usr/bin/env python3
"""Portable standard-library controls on shipped bytes; prints JSON, writes nothing."""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import types
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
def no_effects(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in {
        'os.system','os.exec','os.spawn','os.remove','os.rename','os.mkdir',
        'os.rmdir','os.chmod','os.chown','os.symlink','os.link','os.truncate'}:
        raise AssertionError('unexpected external effect: '+event)
    if event == 'open':
        mode, flags = args[1:3]
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)):
            raise AssertionError('unexpected file write')
sys.addaudithook(no_effects)
checks = []
def check(name, truth):
    assert truth, name
    checks.append(name)
def sha(data): return hashlib.sha256(data).hexdigest()
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
def parts(data):
    with ZipFile(BytesIO(data)) as z: return {n:z.read(n) for n in z.namelist()}

manifest = json.loads((ROOT/'MANIFEST.json').read_text())
for row in manifest['files']:
    path = ROOT/row['path']
    assert path.is_file() and not path.is_symlink()
    assert sha(path.read_bytes()) == row['sha256'], row['path']
check('all manifest payload hashes match', True)
projections = json.loads((ROOT/'EXPORT-PROJECTIONS.json').read_text())
for projection in projections['excerpts']:
    projection_text = (ROOT/projection['file']).read_text()
    projection_lines = projection_text.splitlines(True)
    tree = ast.parse(projection_text)
    nodes = {n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    for pin in projection['definitions']:
        node = nodes[pin['name']]
        assert sha(ast.dump(node,include_attributes=False).encode()) == pin['AST_sha256']
        exact_slice = ''.join(projection_lines[node.lineno-1:node.end_lineno]).encode()
        assert sha(exact_slice) == pin['exact_slice_sha256']
check('all exact definition projections match saved slice and AST pins', True)

def apply_exact_first_file(base_text, patch_text):
    original = base_text.splitlines(True); patch = patch_text.splitlines(True)
    assert patch[:2] == ['--- a/hermes_cli/friday_workspace_xlsx_table.py\n','+++ b/hermes_cli/friday_workspace_xlsx_table.py\n']
    out = []; pos = 0; i = 2
    while i < len(patch) and not patch[i].startswith('--- '):
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n',patch[i])
        assert match
        start = int(match.group(1))-1
        assert start >= pos
        out.extend(original[pos:start]); pos = start; i += 1
        old_count = new_count = 0
        while i < len(patch) and not patch[i].startswith(('@@ ','--- ')):
            line = patch[i]; assert line[0] in ' +-'
            if line[0] in ' -':
                assert original[pos] == line[1:]; pos += 1; old_count += 1
            if line[0] in ' +': out.append(line[1:]); new_count += 1
            i += 1
        assert old_count == int(match.group(2) or '1') and new_count == int(match.group(4) or '1')
    return ''.join(out+original[pos:])
patch = (ROOT/'patches/xlsx-presentation.patch').read_text()
base_path = ROOT/'source/xlsx-base/hermes_cli/friday_workspace_xlsx_table.py'
candidate_path = ROOT/'source/xlsx-candidate/hermes_cli/friday_workspace_xlsx_table.py'
check('exact zero-fuzz XLSX leaf patch transition',apply_exact_first_file(base_path.read_text(),patch) == candidate_path.read_text())
for product_file in ['tools/file_tools.py','hermes_cli/friday_prompt_scope.py','hermes_cli/friday_user_scope.py']:
    segment = patch.split('--- a/'+product_file+'\n',1)[1].split('\n--- a/',1)[0]
    added = '\n'.join(line[1:] for line in segment.splitlines() if line.startswith('+') and not line.startswith('+++'))
    check('exact changed guidance hunk exposes options '+product_file,all(token in added for token in ['freeze','print_area','number_format','0.00']))

# Inert dependency seams: no workspace authority, publication or renderer may run.
hermes = types.ModuleType('hermes_cli'); hermes.__path__ = []
sys.modules['hermes_cli'] = hermes
scope = types.ModuleType('hermes_cli.friday_user_scope')
scope.ScopeDenied = type('ScopeDenied',(ValueError,),{})
def unreachable(*a,**kw): raise AssertionError('unexpected publication or external dependency')
scope.workspace_document = unreachable
sys.modules[scope.__name__] = scope
revision = types.ModuleType('hermes_cli.friday_workspace_revision'); revision.check = unreachable
sys.modules[revision.__name__] = revision
docx = types.ModuleType('hermes_cli.friday_workspace_docx'); docx._create_bytes = unreachable
sys.modules[docx.__name__] = docx
source = ROOT/'source/xlsx-candidate/hermes_cli'
recalc = load('hermes_cli.friday_workspace_xlsx_recalculate',source/'friday_workspace_xlsx_recalculate.py')
table = load('hermes_cli.friday_workspace_xlsx_table',source/'friday_workspace_xlsx_table.py')
base = load('hermes_cli.original_table',ROOT/'source/xlsx-base/hermes_cli/friday_workspace_xlsx_table.py')
def render(spec, module=table):
    sheets,tables,names = module.create_document(copy.deepcopy(spec))
    return module.render_document(sheets,tables=tables,names=names)
def refuse(spec):
    try: render(spec)
    except table.TableRefused: return True
    return False
fixture = json.loads((ROOT/'fixtures/synthetic-spec.json').read_text())
created = render(fixture); original_parts = parts(created); book = recalc.Book(created)
S = recalc.S
root = book.roots['xl/worksheets/sheet1.xml']
pane = root.find(S+'sheetViews/'+S+'sheetView/'+S+'pane')
check('genuine row-one frozen pane',pane.attrib == {'ySplit':'1','topLeftCell':'A2','activePane':'bottomLeft','state':'frozen'})
check('pane before selection', [n.tag for n in root.find(S+'sheetViews/'+S+'sheetView')] == [S+'pane',S+'selection'])
defined = book.roots['xl/workbook.xml'].findall(S+'definedNames/'+S+'definedName')
prints = [(n.get('localSheetId'),n.text) for n in defined if n.get('name') == '_xlnm.Print_Area']
check('genuine per-sheet local print rectangles',prints == [('0','Items!$A$1:$D$3'),('1','Summary!$A$1:$B$2')])
check('native user name and table retained',any(n.get('name') == 'ItemRows' for n in defined) and book.roots['xl/tables/table1.xml'].get('ref') == 'A1:D3')
check('leading zero ID remains inline text',book.cells['Items']['A2'].findtext(S+'is/'+S+'t') == '0007')
check('numeric display does not round stored value',book.cells['Items']['C2'].findtext(S+'v') == '3.125')
styles = book.roots['xl/styles.xml']
formats = {n.get('numFmtId'):n.get('formatCode') for n in styles.findall(S+'numFmts/'+S+'numFmt')}
xfs = styles.findall(S+'cellXfs/'+S+'xf')
def fmt(cell): return formats.get(xfs[int(cell.get('s','0'))].get('numFmtId'),'General')
check('decimal and formula money styles are numeric 0.00',fmt(book.cells['Items']['C2']) == fmt(book.cells['Items']['D2']) == '0.00')
check('native formulas have no fabricated cached values',sum(map(len,book.formulas.values())) == 3 and all(book.cells[s][c].find(S+'v') is None for s,cells in book.formulas.items() for c in cells))
plain = copy.deepcopy(fixture)
for sheet in plain['sheets']:
    sheet.pop('freeze',None); sheet.pop('print_area',None)
    for row in sheet['rows']:
        for cell in row:
            if isinstance(cell,dict): cell.pop('number_format',None)
check('default package parts remain byte-identical to base',parts(render(plain)) == parts(render(plain,base)))
for value in ['B2','A1','A99','A2:B3','Other!A2']:
    bad = copy.deepcopy(fixture); bad['sheets'][0]['freeze'] = value
    check('reject freeze '+value,refuse(bad))
for value in ['A1:E3','A3:A1','Other!A1:D3','A1:D3,A1:B2']:
    bad = copy.deepcopy(fixture); bad['sheets'][0]['print_area'] = value
    check('reject print rectangle '+value,refuse(bad))
for value in ['0.000',0.00,'@']:
    bad = copy.deepcopy(fixture); bad['sheets'][0]['rows'][1][3]['number_format'] = value
    check('reject unsupported format '+repr(value),refuse(bad))
for formula in ['D2','HYPERLINK("x")','SUM(Other!A1:A2)']:
    bad = copy.deepcopy(fixture); bad['sheets'][0]['rows'][1][3]['value'] = formula
    check('formula safety '+formula,refuse(bad))

# Deliberately fabricated cache fixture, never an Office or model result.
prepared = recalc.prepare(book); engine = recalc.Book(prepared,engine=True)
values = {'Items':{'D2':'6.25','D3':'13.5'},'Summary':{'B2':'19.75'}}
changes = {book.sheets[s]:recalc._patch_cells(engine.parts[engine.sheets[s]],v) for s,v in values.items()}
fake = engine.pack(changes)
transplanted,count,charts,adjustments = recalc.transplant(book,fake)
after_parts = parts(transplanted); after_book = recalc.Book(transplanted)
check('synthetic cache-only transplant returns three caches',(count,charts,adjustments) == (3,0,0))
check('cache transplant preserves formulas',after_book.formulas == book.formulas)
changed = {book.sheets[s] for s in values}
check('cache transplant preserves all other package bytes',all(original_parts[n] == after_parts[n] for n in original_parts.keys()-changed))
check('cache transplant preserves native pane bytes',ET.tostring(root.find(S+'sheetViews')) == ET.tostring(after_book.roots['xl/worksheets/sheet1.xml'].find(S+'sheetViews')))

# Exact central admission definitions; configuration, scoped key and resolver are
# synthetic in-memory dependencies. No real config or credential reader executes.
managed = [True]
admission = types.ModuleType('hermes_cli.friday_credential_admission')
exec(compile((ROOT/'excerpts/admission.py').read_text(),'<shipped-admission-excerpt>','exec'),admission.__dict__)
route = ('custom:offline-route','offline-model','synthetic-endpoint-token','OFFLINE_KEY')
fake_key = 'synthetic-in-memory-value'
home = Path('/synthetic-home')
admission.managed = lambda:managed[0]
admission.configuration = lambda h:{}
admission.profile_policy = lambda h,c:None
admission.local_route = lambda c:route
admission._compression_route = lambda c,m:None
admission.owned_values = lambda h:{route[3]:fake_key}
admission.keyless = lambda c:True
admission.own_pool = lambda p:[]
admission.os = types.SimpleNamespace(environ={})
hermes.friday_credential_admission = admission
sys.modules[admission.__name__] = admission
constants = types.ModuleType('hermes_constants'); constants.get_hermes_home = lambda:home
sys.modules[constants.__name__] = constants
sys.modules['agent'] = types.ModuleType('agent')
secret = types.ModuleType('agent.secret_scope')
secret.current_secret_scope = lambda:{route[3]:fake_key}
secret.current_secret_scope_home = lambda:str(home)
sys.modules[secret.__name__] = secret
runtime = types.ModuleType('hermes_cli.runtime_provider')
def resolve_runtime_provider(**kwargs):
    assert kwargs == {'requested':route[0],'target_model':route[1]}
    return {'api_key':fake_key,'api_mode':'chat_completions'}
runtime.resolve_runtime_provider = resolve_runtime_provider
sys.modules[runtime.__name__] = runtime
class BoundaryReached(Exception): pass
def boundary(): raise BoundaryReached()
def aux(name):
    ns = {'_provider_alias_table':lambda:{'codex':'openai-codex','ollama':'custom','vllm':'custom','llamacpp':'custom','llama.cpp':'custom','llama-cpp':'custom'},'_read_main_provider':lambda:'custom',
        '_normalize_main_runtime':lambda r:r or {},'_validate_proxy_env_urls':boundary,'_VISION_AUTO_PROVIDER_ORDER':('openrouter','nous','deepinfra')}
    exec(compile((ROOT/'excerpts'/name).read_text(),'<shipped-vision-excerpt>','exec'),ns)
    return ns
before = aux('vision-before.py'); after = aux('vision-after.py')
def raises(fn,cls,code=None):
    try: fn()
    except Exception as e: return type(e) is cls and (code is None or e.args == ('friday_credential_'+code,))
    return False
check('original exact caller reproduces managed registered-name denial',raises(lambda:before['resolve_vision_provider_client'](),admission.CredentialDenied,'route_override_refused'))
check('candidate reaches actual central admission then pre-SDK boundary',raises(lambda:after['resolve_vision_provider_client'](),BoundaryReached))
for label,kwargs,code in [
    ('provider',{'provider':'custom:foreign'},'route_override_refused'),
    ('stripped provider',{'provider':'offline-route'},'route_override_refused'),
    ('model',{'model':'foreign-model'},'route_override_refused'),
    ('base',{'base_url':'foreign-endpoint-token'},'route_override_refused'),
    ('key',{'api_key':'foreign-key'},'explicit_foreign_key_refused')]:
    check('managed foreign '+label+' rejected',raises(lambda k=kwargs:after['resolve_vision_provider_client'](**k),admission.CredentialDenied,code))
check('central transport guard unchanged',raises(lambda:admission.client_inputs(route[0],route[1],route[2],None,'anthropic_messages'),admission.CredentialDenied,'client_transport_override_refused'))
for label,overrides in [('provider',('custom:foreign',route[1],route[2],None,None)),('model',(route[0],'foreign-model',route[2],None,None)),('base',(route[0],route[1],'foreign-endpoint-token',None,None))]:
    central = aux('vision-after.py'); central['_resolve_task_provider_model'] = lambda *a,v=overrides:v
    check('patched edge independently retains central '+label+' guard',raises(lambda n=central:n['resolve_vision_provider_client'](),admission.CredentialDenied,'route_override_refused'))
managed[0] = False
for provider in ['custom:example','custom:ollama','custom:kimi','codex','ollama','llama.cpp','vllm','openrouter','auto',None]:
    results = []
    for name in ['vision-before.py','vision-after.py']:
        ns = aux(name)
        ns['_resolve_task_provider_model'] = lambda *a,p=provider:(p,'offline-model','synthetic-endpoint-token',None,None)
        ns['resolve_provider_client'] = lambda p,**kw:({'provider':p},kw['model'])
        results.append(ns['resolve_vision_provider_client']())
    check('non-managed donor argument behavior unchanged '+repr(provider),results[0] == results[1])
old = (ROOT/'excerpts/vision-before.py').read_text(); new = (ROOT/'excerpts/vision-after.py').read_text()
addition = ''.join(line[1:] for line in (ROOT/'patches/managed-vision-caller.patch').read_text().splitlines(True) if line.startswith('+') and not line.startswith('+++'))
anchor = '        client, final_model = resolve_provider_client(\n'
check('exact vision patch addition reconstructs shipped function projection',old.replace(anchor,addition+anchor,1) == new)
print(json.dumps({'schema':'friday.source-next.portable-controls.v1','passed':len(checks),'failed':0,'checks':checks,'scope':'shipped exact snapshots and explicitly declared definition projections, synthetic in-memory inputs','external_effects':0,'Office_recalculation':False,'runtime_or_semantic_acceptance':False},sort_keys=True,indent=2))
