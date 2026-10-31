"""Finite local XLSX recalculation, preserving the original OOXML package.

Only numeric formulas in a conservative local subset are admitted. LibreOffice
receives a disposable, cache-cleared copy in the existing document sandbox.
Only verified numeric cell caches and ordinary chart reference caches return;
the engine's rewritten workbook is never published. No formula evaluator here.
"""
from io import BytesIO
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET
from xml.parsers import expat
from xml.sax.saxutils import escape
from zipfile import ZipFile, BadZipFile, ZIP_STORED, ZIP_DEFLATED
import zlib

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
P = '{http://schemas.openxmlformats.org/package/2006/relationships}'
C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
MAX_BYTES = 1000000
MAX_EXPANDED = 4000000
TAG = rb'(?:[A-Za-z_][\w.-]*:)?'
FUNCTIONS = frozenset('SUM AVERAGE MIN MAX COUNT COUNTA ABS ROUND ROUNDUP ROUNDDOWN INT MOD SQRT POWER IF AND OR NOT SUMIF COUNTIF'.split())
RELATIONS = frozenset('officeDocument core-properties extended-properties worksheet styles theme sharedStrings table drawing chart'.split())
PATH = re.compile(r'(?:\[Content_Types\]\.xml|_rels/\.rels|docProps/(?:core|app)\.xml|xl/(?:workbook\.xml|styles\.xml|sharedStrings\.xml|_rels/workbook\.xml\.rels|theme/theme[0-9]+\.xml|worksheets/sheet[0-9]+\.xml|worksheets/_rels/sheet[0-9]+\.xml\.rels|tables/table[0-9]+\.xml|drawings/drawing[0-9]+\.xml|drawings/_rels/drawing[0-9]+\.xml\.rels|charts/chart[0-9]+\.xml))\Z')
REF = re.compile(r"(?:'((?:[^']|'')+)'|([^'!\[\]]+))!\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})(?::\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6}))?\Z")


class RecalculationRefused(ValueError):
    """Public finite reason only; never expose XML, paths or engine output."""


def _deny(reason='unsupported_workbook'):
    raise RecalculationRefused(reason)


def _xml(raw, *, engine=False):
    if (b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper() or b'\x00' in raw
            or re.search(br'<\?xml[^>]*encoding\s*=\s*[\'"](?!utf-8[\'"]|UTF-8[\'"])', raw)):
        _deny()
    root = ET.fromstring(raw)
    stack = [(root, 0)]; count = 0
    while stack:
        node, depth = stack.pop(); count += 1
        if count > 50000 or depth > 64: _deny()
        if node.tag.rsplit('}', 1)[-1] in ({'AlternateContent', 'externalReferences',
                'oleObjects', 'controls', 'webPublishItems', 'connections', 'queryTable',
                'pivotTableDefinition', 'calculatedColumnFormula', 'totalsRowFormula'} | (set() if engine else {'extLst'})):
            _deny()
        stack.extend((child, depth+1) for child in node)
    return root


def _numeric(raw):
    if not isinstance(raw, str) or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?', raw): _deny('invalid_formula_result')
    value = Decimal(raw)
    if not value.is_finite() or abs(value) > Decimal('1e100'): _deny('invalid_formula_result')
    return value


TOKEN = re.compile(r"\s*(?:(?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_.]*)!)?\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6}(?::\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6})?)(?![A-Za-z0-9_])|(?P<number>(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op><>|<=|>=|[+*/^%(),=<>-]))")


def _formula(text, names=()):
    """Parse a finite numeric grammar; return references, never their values."""
    if not isinstance(text, str) or not 1 <= len(text) <= 4096: _deny()
    tokens = []; offset = 0
    while offset < len(text.rstrip()):
        match = TOKEN.match(text, offset)
        if not match: _deny()
        tokens.append((match.lastgroup, match.group(match.lastgroup))); offset = match.end()
    if not tokens or len(tokens) > 1024: _deny()
    index = 0; refs = []
    priorities = {'=': 1, '<>': 1, '<': 1, '>': 1, '<=': 1, '>=': 1,
                  '+': 2, '-': 2, '*': 3, '/': 3, '^': 4}
    def expression(minimum=0, depth=0):
        nonlocal index
        if depth > 64 or index >= len(tokens): _deny()
        kind, value = tokens[index]; index += 1
        if value in ('+', '-'):
            expression(5, depth+1)
        elif value == '(':
            expression(0, depth+1)
            if index >= len(tokens) or tokens[index][1] != ')': _deny()
            index += 1
        elif kind == 'number': _numeric(value)
        elif kind == 'ref': refs.append(('ref', value))
        elif kind == 'name':
            if index < len(tokens) and tokens[index][1] == '(':
                if value.upper() not in FUNCTIONS: _deny()
                index += 1; arguments = 0
                while index < len(tokens) and tokens[index][1] != ')':
                    expression(0, depth+1); arguments += 1
                    if index < len(tokens) and tokens[index][1] == ',': index += 1
                    else: break
                if not arguments or index >= len(tokens) or tokens[index][1] != ')': _deny()
                index += 1
            elif value.upper() not in {'TRUE', 'FALSE'}: refs.append(('name', value.upper()))
        else: _deny()
        while index < len(tokens):
            op = tokens[index][1]
            if op == '%': index += 1; continue
            priority = priorities.get(op, -1)
            if priority < minimum: break
            index += 1; expression(priority+1, depth+1)
    expression()
    if index != len(tokens): _deny()
    return refs


def _coord(value):
    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})', value or '')
    if not match: _deny()
    col = 0
    for char in match[1]: col = col*26+ord(char)-64
    if col > 16384 or int(match[2]) > 1048576: _deny()
    return col, int(match[2])


class Book:
    def __init__(self, data, *, engine=False, checkpoint=lambda: None):
        self.checkpoint = checkpoint
        try:
            self._load(data, engine=engine)
        except (BadZipFile, ET.ParseError, ValueError, KeyError, TypeError, OSError,
                RuntimeError, NotImplementedError, zlib.error, InvalidOperation):
            _deny()

    def _load(self, data, *, engine=False):
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES: _deny()
        with ZipFile(BytesIO(data)) as package:
            self.infos = package.infolist(); self.comment = package.comment
            if not 1 <= len(self.infos) <= 128 or sum(i.file_size for i in self.infos) > MAX_EXPANDED: _deny()
            self.parts = {}; self.roots = {}
            for info in self.infos:
                self.checkpoint()
                name = info.filename
                engine_extra = engine and re.fullmatch(r'xl/charts/(?:_rels/chart[0-9]+\.xml\.rels|(?:style|colors)[0-9]+\.xml)', name)
                if (name in self.parts or not (PATH.fullmatch(name) or engine_extra) or info.flag_bits & 1
                        or info.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
                        or stat.S_ISLNK(info.external_attr >> 16)
                        or info.file_size > MAX_EXPANDED or info.file_size > max(4096, info.compress_size*200)):
                    _deny()
                raw = package.read(info)
                if len(raw) != info.file_size: _deny()
                self.parts[name] = raw; self.roots[name] = _xml(raw, engine=engine)
        ct = '{http://schemas.openxmlformats.org/package/2006/content-types}'
        types = self.roots['[Content_Types].xml']
        if types.tag != ct+'Types': _deny()
        overrides = {}
        allowed_types = {'application/xml', 'application/vnd.openxmlformats-package.relationships+xml',
            'application/vnd.openxmlformats-package.core-properties+xml',
            'application/vnd.openxmlformats-officedocument.extended-properties+xml',
            'application/vnd.openxmlformats-officedocument.theme+xml',
            'application/vnd.openxmlformats-officedocument.drawing+xml',
            'application/vnd.openxmlformats-officedocument.drawingml.chart+xml'}
        allowed_types.update('application/vnd.openxmlformats-officedocument.spreadsheetml.'+suffix+'+xml'
            for suffix in ('sheet.main', 'worksheet', 'styles', 'sharedStrings', 'table'))
        if engine: allowed_types.update({'application/vnd.ms-office.chartstyle+xml', 'application/vnd.ms-office.chartcolorstyle+xml'})
        for node in types:
            mime = node.get('ContentType', '')
            if engine and node.tag == ct+'Default' and node.get('Extension') in {'fntdata', 'jpeg', 'png'}:
                continue  # LibreOffice declares these even with no such member.
            if mime not in allowed_types: _deny()
            if node.tag == ct+'Override':
                name = node.get('PartName', '')
                if name in overrides or name.lstrip('/') not in self.parts: _deny()
                overrides[name] = mime
            elif node.tag != ct+'Default' or node.get('Extension') not in {'xml', 'rels'}: _deny()
        if overrides.get('/xl/workbook.xml') != 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml': _deny()
        self.links = {}
        for name, root in self.roots.items():
            if not name.endswith('.rels'): continue
            if root.tag != P+'Relationships': _deny()
            parent = '' if name == '_rels/.rels' else name.rsplit('/_rels/', 1)[0]
            links = {}
            for node in root:
                target = node.get('Target', ''); ident = node.get('Id')
                if (node.tag != P+'Relationship' or not ident or ident in links
                        or node.get('TargetMode') is not None or ':' in target or '\\' in target
                        or node.get('Type', '').rsplit('/', 1)[-1] not in (RELATIONS | ({'chartStyle', 'chartColorStyle'} if engine else set()))): _deny()
                resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(parent, target))
                if resolved not in self.parts or resolved.startswith('../'): _deny()
                links[ident] = (node.get('Type'), resolved)
            self.links[name] = links
        offices = [target for kind, target in self.links['_rels/.rels'].values() if kind == R[1:-1]+'/officeDocument']
        if offices != ['xl/workbook.xml']: _deny()
        workbook = self.roots['xl/workbook.xml']
        if workbook.tag != S+'workbook': _deny()
        protection = workbook.find(S+'workbookProtection')
        if protection is not None and (len(protection) or (protection.text or '').strip()
                or any(key not in {'lockStructure', 'lockWindows', 'lockRevision'} or value not in {'0', 'false'}
                       for key, value in protection.attrib.items())): _deny()
        self.sheets = {}; self.cells = {}; self.formulas = {}
        settings = workbook.find(S+'calcPr')
        if settings is not None and settings.get('iterate', '0') not in ('0', 'false'): _deny()
        if settings is not None and settings.get('fullPrecision', '1') not in ('1', 'true'): _deny()
        definitions = workbook.findall(S+'definedNames/'+S+'definedName')
        self.names = {}; self.name_expressions = {}
        for node in definitions:
            self.checkpoint()
            name = node.get('name', '').upper(); local = node.get('localSheetId')
            if any(node.get(key, '0') not in ('0', 'false') for key in ('function', 'vbProcedure', 'xlm')): _deny()
            if not name or (local, name) in self.names: _deny()
            self.names[local, name] = _formula(node.text)
            self.name_expressions[local, name] = node.text
        for sheet in workbook.findall(S+'sheets/'+S+'sheet'):
            name = sheet.get('name'); link = self.links['xl/_rels/workbook.xml.rels'].get(sheet.get(R+'id'))
            if not name or name in self.sheets or not link or link[0] != R[1:-1]+'/worksheet': _deny()
            part = link[1]; root = self.roots[part]
            if root.tag != S+'worksheet' or root.find(S+'sheetProtection') is not None: _deny()
            self.sheets[name] = part; self.cells[name] = {}; self.formulas[name] = {}
            for cell in root.findall(S+'sheetData/'+S+'row/'+S+'c'):
                if len(self.cells[name]) % 256 == 0: self.checkpoint()
                address = cell.get('r'); _coord(address)
                if address in self.cells[name] or len(self.cells[name]) >= 4096: _deny()
                self.cells[name][address] = cell
                fs = cell.findall(S+'f')
                if fs:
                    allowed = {'aca': 'false'} if engine else {}
                    if len(fs) != 1 or any(allowed.get(k) != v for k, v in fs[0].attrib.items()) or cell.get('t', 'n') not in ('n', 'e'): _deny()
                    _formula(fs[0].text)
                    self.formulas[name][address] = fs[0].text
                elif cell.get('t', 'n') == 'n' and cell.find(S+'v') is not None:
                    _numeric(cell.find(S+'v').text)
        if not self.sheets or sum(map(len, self.formulas.values())) > 4096: _deny()
        # All formula sites outside cells/names are either simple chart ranges or refused.
        for part, root in self.roots.items():
            for node in root.iter():
                if node.tag == C+'f': self.range(node.text)
                elif node.tag.rsplit('}', 1)[-1] in {'formula', 'formula1', 'formula2'}: _formula(node.text)
        self._dependencies()

    def _dependencies(self):
        graph = {}; edges = 0; ordered = list(self.sheets); memo = {}; operations = 0
        def expand(tokens, sheet, seen=()):
            nonlocal operations
            result = set()
            for kind, value in tokens:
                operations += 1
                if operations > 100000: _deny('formula_dependency_limit')
                if operations % 256 == 0: self.checkpoint()
                if kind == 'name':
                    scope = str(ordered.index(sheet)); key = (scope, value)
                    if key not in self.names: key = (None, value)
                    if key not in self.names or key in seen or len(seen) > 32: _deny()
                    identity = key, sheet
                    if identity not in memo: memo[identity] = expand(self.names[key], sheet, seen+(key,))
                    result.update(memo[identity])
                else:
                    qualified = value if '!' in value else "'"+sheet.replace("'", "''")+"'!"+value
                    target, addresses = self.range(qualified.upper() if '!' not in value else qualified, casefold=True)
                    operations += len(addresses)
                    if operations > 100000: _deny('formula_dependency_limit')
                    result.update((target, address) for address in addresses)
                if len(result) > 20000: _deny('formula_dependency_limit')
            return result
        for (scope, _), tokens in self.names.items():
            if scope is not None and (not scope.isdecimal() or int(scope) >= len(ordered)): _deny()
            expand(tokens, ordered[int(scope)] if scope is not None else ordered[0])
        for sheet, formulas in self.formulas.items():
            for address, text in formulas.items():
                refs = expand(_formula(text), sheet); edges += len(refs)
                if edges > 20000: _deny()
                graph[sheet, address] = refs
        active = set(); done = set()
        def visit(node, depth=0):
            if node in done or node not in graph: return
            if node in active or depth > 128: _deny('circular_or_deep_formula')
            active.add(node)
            for child in graph[node]: visit(child, depth+1)
            active.remove(node); done.add(node)
        for node in graph: visit(node)
        self.checkpoint()

    def range(self, text, casefold=False):
        match = REF.fullmatch(text or '') if not casefold else re.fullmatch(REF.pattern, text or '', re.I)
        if not match: _deny('unsupported_chart')
        sheet = (match[1] or match[2]).replace("''", "'")
        if casefold:
            matches = [name for name in self.sheets if name.casefold() == sheet.casefold()]
            if len(matches) != 1: _deny()
            sheet = matches[0]
        if sheet not in self.sheets: _deny('unsupported_chart')
        c1, r1 = _coord(match[3].upper()+match[4]); c2, r2 = _coord((match[5] or match[3]).upper()+(match[6] or match[4]))
        if c1 > c2 or r1 > r2 or (not casefold and c1 != c2 and r1 != r2) or (c2-c1+1)*(r2-r1+1) > 4096: _deny('unsupported_chart')
        def col(n):
            s = ''
            while n: n, rem = divmod(n-1, 26); s = chr(65+rem)+s
            return s
        return sheet, [col(c)+str(r) for r in range(r1, r2+1) for c in range(c1, c2+1)]

    def pack(self, changed):
        output = BytesIO()
        with ZipFile(output, 'w') as package:
            package.comment = self.comment
            for info in self.infos: package.writestr(info, changed.get(info.filename, self.parts[info.filename]))
        data = output.getvalue()
        if len(data) > MAX_BYTES: _deny('output_too_large')
        return data


def _tag_end(raw, offset):
    quote = None
    for index in range(offset, len(raw)):
        char = raw[index]
        if quote:
            if char == quote: quote = None
        elif char in (34, 39): quote = char
        elif char == 62: return index+1
    _deny()


def _patch_cells(raw, values):
    """Use XML parser byte offsets, so comments/foreign tags cannot be cells."""
    parser = expat.ParserCreate(namespace_separator='}')
    stack = []; cells = {}; current = None
    def start(name, attrs):
        nonlocal current
        stack.append(name)
        offset = parser.CurrentByteIndex
        if stack == [S[1:]+'worksheet', S[1:]+'sheetData', S[1:]+'row', S[1:]+'c']:
            address = attrs.get('r')
            if address in values:
                if address in cells: _deny()
                current = {'start': offset, 'open_end': _tag_end(raw, offset), 'v': []}
                cells[address] = current
        elif current is not None and len(stack) == 5 and name == S[1:]+'v':
            current['v'].append([offset, None, raw[offset:_tag_end(raw, offset)].rstrip().endswith(b'/>')])
    def end(name):
        nonlocal current
        if current is not None and len(stack) == 5 and name == S[1:]+'v':
            record = current['v'][-1]
            record[1] = parser.CurrentByteIndex if record[2] else _tag_end(raw, parser.CurrentByteIndex)
        elif current is not None and len(stack) == 4 and name == S[1:]+'c':
            current['close'] = parser.CurrentByteIndex; current = None
        stack.pop()
    parser.StartElementHandler = start; parser.EndElementHandler = end
    parser.Parse(raw, True)
    if set(cells) != set(values): _deny()
    edits = []
    for address, record in cells.items():
        opening = raw[record['start']:record['open_end']]
        prefix = re.match(rb'<((?:[A-Za-z_][\w.-]*:)?)c\b', opening)
        if prefix is None or len(record['v']) > 1: _deny()
        adjusted = re.sub(rb'\s+t\s*=\s*([\'"])[^\'"]*\1', b'', opening)
        if adjusted != opening: edits.append((record['start'], record['open_end'], adjusted))
        replacement = b'<'+prefix[1]+b'v>'+values[address].encode('ascii')+b'</'+prefix[1]+b'v>'
        if record['v']:
            start, end, _ = record['v'][0]; edits.append((start, end, replacement))
        else: edits.append((record['close'], record['close'], replacement))
    output = raw
    for start, end, replacement in sorted(edits, reverse=True): output = output[:start]+replacement+output[end:]
    # Prove only the admitted cache/type changed, including unusual attributes.
    before = _xml(raw); after = _xml(output)
    for root in (before, after):
        for cell in root.findall(S+'sheetData/'+S+'row/'+S+'c'):
            if cell.get('r') in values:
                cell.attrib.pop('t', None)
                for value in cell.findall(S+'v'): cell.remove(value)
    if ET.tostring(before) != ET.tostring(after): _deny('preservation_failed')
    return output


def prepare(book):
    changes = {}
    for name, formulas in book.formulas.items():
        if formulas: changes[book.sheets[name]] = _patch_cells(book.parts[book.sheets[name]], dict.fromkeys(formulas, ''))
    raw = book.parts['xl/workbook.xml']
    prefix = re.match(rb'(?:<\?xml[^>]*>\s*)?<((?:[A-Za-z_][\w.-]*:)?)workbook\b', raw)
    if not prefix: _deny()
    calc = b'<'+prefix[1]+b'calcPr calcId="0" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>'
    pattern = rb'<'+TAG+rb'calcPr\b[^>]*(?:/>|>.*?</'+TAG+rb'calcPr\s*>)'
    if re.search(pattern, raw, re.S): raw = re.sub(pattern, lambda _: calc, raw, flags=re.S)
    else:
        offset = raw.rfind(b'</'); raw = raw[:offset]+calc+raw[offset:]
    changes['xl/workbook.xml'] = raw
    return book.pack(changes)


def _literal(book, cell):
    kind = cell.get('t', 'n')
    if kind == 'n':
        raw = cell.findtext(S+'v')
        return ('empty', None) if raw is None else ('number', _numeric(raw))
    if kind == 'b' and cell.findtext(S+'v') in ('0', '1'): return ('bool', cell.findtext(S+'v'))
    if kind == 'inlineStr': return ('text', _string(cell.find(S+'is')))
    if kind == 's':
        try: return ('text', _string(book.roots['xl/sharedStrings.xml'].findall(S+'si')[int(cell.findtext(S+'v'))]))
        except (KeyError, ValueError, IndexError): _deny()
    _deny()


def _string(node):
    if node is None: _deny()
    return ''.join(child.text or '' for child in node.findall(S+'t')+node.findall(S+'r/'+S+'t'))


def _canonical_reference(value):
    if '!' in value:
        sheet, cells = value.rsplit('!', 1)
        if sheet.startswith("'"): sheet = sheet[1:-1].replace("''", "'")
        sheet = sheet.casefold()
    else: sheet, cells = None, value
    addresses = cells.upper().split(':')
    if len(addresses) == 2 and addresses[0] == addresses[1]: addresses.pop()
    return sheet, tuple(addresses)


def _canonical_formula(value):
    # Token boundaries discard grammar whitespace, never whitespace in labels.
    result = []; offset = 0
    while offset < len(value.rstrip()):
        match = TOKEN.match(value, offset)
        if not match: _deny('engine_result_mismatch')
        kind = match.lastgroup; text = match.group(kind); offset = match.end()
        result.append((kind, _canonical_reference(text) if kind == 'ref'
                       else _numeric(text) if kind == 'number' else text.upper()))
    return tuple(result)


def _patch_chart(raw, caches):
    """Edit actual reference/cache XML spans, preserving opaque outside markup."""
    parser = expat.ParserCreate(namespace_separator='}')
    records = []; active = None; depth = 0
    def start(name, attrs):
        nonlocal depth, active
        depth += 1
        offset = parser.CurrentByteIndex; end = _tag_end(raw, offset)
        if name in (C[1:]+'numRef', C[1:]+'strRef'):
            if active is not None: _deny('unsupported_chart')
            active = {'start': offset, 'open_end': end, 'depth': depth,
                      'kind': name.rsplit('}', 1)[1], 'cache': None}
            records.append(active)
        elif active is not None and depth == active['depth']+1 and name in (C[1:]+'numCache', C[1:]+'strCache'):
            if active['cache'] is not None: _deny('unsupported_chart')
            active['cache'] = {'start': offset, 'open_end': end,
                'empty': raw[offset:end].rstrip().endswith(b'/>'), 'kind': name.rsplit('}', 1)[1]}
    def finish(name):
        nonlocal depth, active
        if active is not None:
            if active['cache'] is not None and depth == active['depth']+1 and name in (C[1:]+'numCache', C[1:]+'strCache'):
                item = active['cache']
                item['end'] = item['open_end'] if item['empty'] else _tag_end(raw, parser.CurrentByteIndex)
            elif depth == active['depth']:
                active['close'] = parser.CurrentByteIndex
                active['end'] = _tag_end(raw, parser.CurrentByteIndex); active = None
        depth -= 1
    parser.StartElementHandler = start; parser.EndElementHandler = finish
    parser.Parse(raw, True)
    if len(records) != len(caches): _deny('unsupported_chart')
    edits = []
    for record, (ref_kind, kind, fmt, points) in zip(records, caches):
        opening = raw[record['start']:record['open_end']]
        match = re.match(rb'<((?:[A-Za-z_][\w.-]*:)?)'+record['kind'].encode()+rb'\b', opening)
        if match is None: _deny('unsupported_chart')
        prefix = match[1].decode()
        if record['kind'] != ref_kind:
            if (record['kind'], ref_kind) != ('numRef', 'strRef'): _deny('unsupported_chart')
            edits.append((record['start'], record['open_end'], opening[:len(match[1])+1]+b'strRef'+opening[len(match[1])+7:]))
            closing = raw[record['close']:record['end']]
            edits.append((record['close'], record['end'], closing[:len(match[1])+2]+b'strRef'+closing[len(match[1])+8:]))
        cache = record['cache']
        if cache is None:
            cache_open = '<'+prefix+kind+'>'
        else:
            cache_open = raw[cache['start']:cache['open_end']].decode()
            cache_prefix = re.match(r'<((?:[A-Za-z_][\w.-]*:)?)'+cache['kind']+r'\b', cache_open)
            if cache_prefix is None: _deny('unsupported_chart')
            prefix = cache_prefix[1]
            offset = len(prefix)+1
            cache_open = cache_open[:offset]+kind+cache_open[offset+len(cache['kind']):]
            if cache['empty']: cache_open = cache_open.rstrip()[:-2]+'>'
        def element(tag, body): return '<'+prefix+tag+'>'+body+'</'+prefix+tag+'>'
        body = element('formatCode', escape(fmt)) if fmt is not None else ''
        body += '<'+prefix+'ptCount val="'+str(len(points))+'"/>'
        body += ''.join('<'+prefix+'pt idx="'+str(i)+'">'+element('v', escape(value))+'</'+prefix+'pt>' for i, value in points)
        replacement = (cache_open+body+'</'+prefix+kind+'>').encode()
        if cache is None: edits.append((record['close'], record['close'], replacement))
        else: edits.append((cache['start'], cache['end'], replacement))
    before = _xml(raw)
    for start, end, replacement in sorted(edits, reverse=True): raw = raw[:start]+replacement+raw[end:]
    after = _xml(raw)
    old_refs = [node for node in before.iter() if node.tag in {C+'numRef', C+'strRef'}]
    new_refs = [node for node in after.iter() if node.tag in {C+'numRef', C+'strRef'}]
    if len(new_refs) != len(caches): _deny('preservation_failed')
    for old, new, (ref_kind, kind, fmt, points) in zip(old_refs, new_refs, caches):
        actual = new.find(C+kind)
        if (new.tag != C+ref_kind or actual is None or actual.findtext(C+'formatCode') != fmt
                or actual.find(C+'ptCount').get('val') != str(len(points))
                or [(node.get('idx'), node.findtext(C+'v')) for node in actual.findall(C+'pt')]
                    != [(str(i), value) for i, value in points]): _deny('preservation_failed')
        for node in (old, new):
            for child in list(node):
                if child.tag in {C+'numCache', C+'strCache'}: node.remove(child)
        new.tag = old.tag
    if ET.tostring(before) != ET.tostring(after): _deny('preservation_failed')
    return raw


def transplant(book, calculated):
    engine = Book(calculated, engine=True, checkpoint=book.checkpoint)
    if list(engine.sheets) != list(book.sheets): _deny('engine_result_mismatch')
    def date_system(item):
        props = item.roots['xl/workbook.xml'].find(S+'workbookPr')
        return props is not None and props.get('date1904', '0') in ('1', 'true')
    if date_system(book) != date_system(engine): _deny('engine_result_mismatch')
    changes = {}; values = {}; count = 0
    canonical_names = lambda item: {key: _canonical_formula(value) for key, value in item.name_expressions.items()}
    if canonical_names(book) != canonical_names(engine): _deny('engine_result_mismatch')
    for name, formulas in book.formulas.items():
        book.checkpoint()
        if set(formulas) != set(engine.formulas[name]): _deny('engine_result_mismatch')
        for address, cell in book.cells[name].items():
            if address in formulas: continue
            expected = _literal(book, cell)
            actual = engine.cells[name].get(address)
            if actual is None:
                if expected != ('empty', None): _deny('engine_result_mismatch')
            elif _literal(engine, actual) != expected: _deny('engine_result_mismatch')
        for address, cell in engine.cells[name].items():
            if address not in book.cells[name] and _literal(engine, cell) != ('empty', None): _deny('engine_result_mismatch')
        current = {}
        for address, formula in formulas.items():
            cell = engine.cells[name][address]; vals = cell.findall(S+'v')
            if _canonical_formula(formula) != _canonical_formula(engine.formulas[name][address]) or cell.get('t', 'n') != 'n' or len(vals) != 1: _deny('engine_result_mismatch')
            _numeric(vals[0].text); current[address] = vals[0].text; count += 1
        values[name] = current
        if current: changes[book.sheets[name]] = _patch_cells(book.parts[book.sheets[name]], current)
    charts = 0; chart_adjustments = 0
    for part, root in book.roots.items():
        book.checkpoint()
        if not part.startswith('xl/charts/'): continue
        raw = book.parts[part]
        caches = []
        parents = {child: parent for parent in root.iter() for child in parent}
        for node in root.iter():
            if node.tag in {C+'multiLvlStrRef', C+'numLit', C+'strLit'}: _deny('unsupported_chart')
            if node.tag not in {C+'numRef', C+'strRef'}: continue
            sheet, addresses = book.range(node.findtext(C+'f'))
            numeric = node.tag == C+'numRef'; kind = 'numCache' if numeric else 'strCache'
            cache = node.find(C+kind)
            if any(child.tag not in {C+'f', C+kind} for child in node) or len(node.findall(C+'f')) != 1 or len(node.findall(C+kind)) > 1: _deny('unsupported_chart')
            if cache is not None:
                if (any(child.tag not in {C+'formatCode', C+'ptCount', C+'pt'} for child in cache)
                        or len(cache.findall(C+'formatCode')) > 1 or len(cache.findall(C+'ptCount')) > 1): _deny('unsupported_chart')
                for child in cache:
                    allowed = {'idx'} if child.tag == C+'pt' else {'val'} if child.tag == C+'ptCount' else set()
                    if set(child.attrib) != allowed: _deny('unsupported_chart')
                    if child.tag == C+'pt':
                        if len(child) != 1 or child[0].tag != C+'v' or child[0].attrib or len(child[0]): _deny('unsupported_chart')
                    elif len(child): _deny('unsupported_chart')
            ref_kind = 'numRef' if numeric else 'strRef'
            cells = [book.cells[sheet].get(address) for address in addresses]
            if any(cell is None for cell in cells): _deny('unsupported_chart')
            if numeric and all(cell.get('t') in {'s', 'inlineStr'} for cell in cells):
                if parents[node].tag != C+'cat' or (cache is not None and len(cache)): _deny('unsupported_chart')
                numeric = False; kind = 'strCache'; ref_kind = 'strRef'; chart_adjustments += 1
            points = []
            for index, address in enumerate(addresses):
                cell = book.cells[sheet].get(address)
                if cell is None: _deny('unsupported_chart')
                if numeric:
                    value = values[sheet].get(address, cell.findtext(S+'v'))
                    if cell.get('t', 'n') not in ('n', 'e'): _deny('unsupported_chart')
                    _numeric(value)
                elif cell.get('t') in {'inlineStr', 's'}: value = _literal(book, cell)[1]
                else: _deny('unsupported_chart')
                points.append((index, value))
            caches.append((ref_kind, kind, cache.findtext(C+'formatCode') if cache is not None else None, points)); charts += 1
        raw = _patch_chart(raw, caches)
        if raw != book.parts[part]: changes[part] = raw
    result = book.pack(changes)
    checked = Book(result, checkpoint=book.checkpoint)
    if checked.formulas != book.formulas: _deny('preservation_failed')
    for name, formulas in book.formulas.items():
        for address in formulas:
            cell = checked.cells[name][address]
            if cell.get('t', 'n') != 'n' or cell.findtext(S+'v') != values[name][address]: _deny('preservation_failed')
    return result, count, charts, chart_adjustments


def _argv(work, toolchain):
    from hermes_cli.friday_workspace_pdf import _argv as pdf_argv
    # Reuse the document namespace/custody unchanged, only its fixed input name.
    return [arg.replace('input.docx', 'input.xlsx') for arg in pdf_argv(work, toolchain)]


def render(cap, book):
    from hermes_cli.friday_workspace_pdf import _toolchain, _run, _private_bytes, ExportRefused
    from hermes_cli.friday_workspace_revision import check
    work = Path(tempfile.mkdtemp(prefix='friday-xlsx-recalculate-'))
    try:
        work.chmod(0o700)
        for name in ('out', 'home', 'tmp'): (work/name).mkdir(mode=0o700)
        (work/'input.xlsx').write_bytes(prepare(book)); (work/'input.xlsx').chmod(0o600)
        (work/'renderer.py').write_bytes(Path(__file__).read_bytes()); (work/'renderer.py').chmod(0o600)
        _run(cap, _argv(work, _toolchain()), work)
        root = output = None
        try:
            root = os.open(work, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            output = os.open('out', os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW, dir_fd=root)
            for descriptor in (root, output):
                info = os.fstat(descriptor)
                if info.st_uid != os.getuid() or info.st_mode & 0o077: _deny('invalid_engine_output')
            data = _private_bytes(output, 'input.xlsx', MAX_BYTES)
        finally:
            if output is not None: os.close(output)
            if root is not None: os.close(root)
        check(cap)
        return transplant(book, data)
    finally:
        try: shutil.rmtree(work)
        except OSError:
            from agent.web_call_context import _current
            call = _current.get()
            if call is not None and hasattr(call, 'agent'): call.agent._friday_reply_effect_unknown = True
            raise ExportRefused('renderer_cleanup_unconfirmed') from None


def create_recalculated(cap, fd, leaf, path, content):
    from hermes_cli.friday_user_scope import ScopeDenied, workspace_document
    from hermes_cli.friday_workspace_revision import check
    from hermes_cli.friday_workspace_docx import _create_bytes, _check_parent
    from hermes_cli.friday_workspace_pdf import ExportRefused
    check(cap); _check_parent(cap, fd, path)
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result: raise ScopeDenied()
                result[key] = value
            return result
        if not isinstance(content, str) or len(content) > 4096: raise ScopeDenied()
        spec = json.loads(content, object_pairs_hook=pairs)
        if not isinstance(spec, dict) or set(spec) != {'source'}: raise ScopeDenied()
        raw = spec['source']
        if not isinstance(raw, str) or not raw or '\x00' in raw: raise ScopeDenied()
        root = cap.home/'workspace'; source = Path(raw)
        if not source.is_absolute(): source = root/source
        relative = source.relative_to(root)
        if (not relative.parts or any(p in ('.', '..') or p.startswith('.') for p in relative.parts)
                or source.suffix.lower() != '.xlsx' or relative.as_posix() == path): raise ScopeDenied()
    except (ValueError, TypeError, KeyError, RecursionError): raise ScopeDenied() from None
    try:
        os.stat(leaf, dir_fd=fd, follow_symlinks=False)
        return json.dumps({'success': False, 'error': 'document_already_exists', 'path': path})
    except FileNotFoundError: pass
    try:
        data, _, identity = workspace_document(str(source), with_identity=True)
        book = Book(data, checkpoint=lambda: check(cap))
        rendered, count, charts, chart_adjustments = render(cap, book)
        def verify():
            check(cap)
            current, _, version = workspace_document(str(source), with_identity=True)
            if current != data or version != identity: raise ScopeDenied()
        result = json.loads(_create_bytes(cap, fd, leaf, path, rendered, output_format='xlsx', verify_source=verify))
        if result.get('success'):
            result.update(source=relative.as_posix(), source_sha256=hashlib.sha256(data).hexdigest(),
                          source_unchanged=True, formula_cache_recomputed=True,
                          recalculated_formula_cells=count, refreshed_chart_references=charts,
                          recalculation_engine='LibreOffice', unrelated_parts_preserved=True,
                          preservation_mode='original_parts_with_cache_updates_and_reported_chart_adjustments',
                          chart_category_references_normalized=chart_adjustments)
        return json.dumps(result)
    except (RecalculationRefused, ExportRefused) as error:
        unknown = str(error) == 'renderer_cleanup_unconfirmed'
        return json.dumps({'success': False, 'error': 'xlsx_recalculation_refused', 'reason': str(error),
                           'effect_disposition': 'unknown' if unknown else 'none'})
    except (TimeoutError, RuntimeError, OSError):
        return json.dumps({'success': False, 'error': 'xlsx_recalculation_stopped', 'effect_disposition': 'none'})


def _render_child():
    import resource
    os.umask(0o077)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    for key, value in ((resource.RLIMIT_AS, 2*1024**3), (resource.RLIMIT_CPU, 35),
                       (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_CORE, 0),
                       (resource.RLIMIT_NOFILE, 128)):
        resource.setrlimit(key, (value, value))
    prefix = '/opt/friday-document-toolchain'; program = prefix+'/root/usr/lib/libreoffice/program'
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/work/home', 'TMPDIR': '/work/tmp',
           'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'SAL_USE_VCLPLUGIN': 'svp',
           'XDG_CACHE_HOME': '/work/home/cache', 'XDG_CONFIG_HOME': '/work/home/config',
           'XDG_RUNTIME_DIR': '/work/tmp',
           'LD_LIBRARY_PATH': program+':'+prefix+'/root/usr/lib/x86_64-linux-gnu'}
    command = [program+'/soffice', '--headless', '--norestore', '--nodefault',
               '--nolockcheck', '--nofirststartwizard',
               '-env:UserInstallation=file:///work/home/profile', '--convert-to',
               'xlsx:Calc MS Excel 2007 XML', '--outdir', '/work/out', '/work/input.xlsx']
    subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=35, check=True)


if __name__ == '__main__':
    if sys.argv[1:] != ['--render']: raise SystemExit(2)
    try: _render_child()
    except BaseException: raise SystemExit(1)
