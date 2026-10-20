"""Finite, read-only, stdlib Office semantic predicates. See CONTENT-CONTRACT.md."""
from __future__ import annotations
import hashlib
import io
import json
import posixpath
import re
import stat
import struct
import urllib.parse
import zipfile
import zlib
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

class Unsupported(ValueError):
    """The finite reader cannot substantiate the requested claim."""

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
O = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
V = 'urn:schemas-microsoft-com:vml'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
NS = {'w': W, 's': S, 'a': A, 'p': P, 'r': O}
MAX_DATA = 32 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_TOTAL = 48 * 1024 * 1024
MAX_XML = 8 * 1024 * 1024
MAX_ITEMS = 65536
MAX_STR = 262144
SAFE_ROLES = {
    'officeDocument', 'styles', 'settings', 'webSettings', 'fontTable', 'theme',
    'header', 'footer', 'comments', 'footnotes', 'endnotes', 'numbering', 'image',
    'hyperlink', 'worksheet', 'sharedStrings', 'calcChain', 'chartsheet', 'drawing',
    'chart', 'table', 'slide', 'slideMaster', 'slideLayout', 'notesSlide', 'notesMaster',
    'handoutMaster', 'presProps', 'viewProps', 'tableStyles', 'package', 'themeOverride',
    'printerSettings', 'connections', 'queryTable', 'externalLinkPath',
    'customXml', 'customXmlProps',
}
# These known roles remain explicitly unsupported rather than silently ignored.
UNSAFE_ROLES = {'oleObject', 'control', 'aFChunk', 'attachedTemplate', 'externalLink',
                'externalLinkPath', 'connections', 'queryTable', 'vbaProject'}
META_ROLES = {
    'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties',
    'http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail',
    O + '/extended-properties', O + '/custom-properties',
    'http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects',
    'http://schemas.microsoft.com/office/2011/relationships/chartStyle',
    'http://schemas.microsoft.com/office/2011/relationships/chartColorStyle',
}
MAIN = {
    'docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml', W, 'document'),
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml', S, 'workbook'),
    'pptx': ('application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml', P, 'presentation'),
}
CELL = re.compile(r'([A-Z]{1,3})([1-9][0-9]{0,6})\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')

def _need(ok, why):
    if not ok:
        raise ValueError(why)

def _string(value, where, empty=True):
    _need(type(value) is str and len(value) <= MAX_STR and (empty or bool(value)), where + ': invalid string')
    return value

def _list(value, where, nonempty=False):
    _need(type(value) is list and len(value) <= MAX_ITEMS and (not nonempty or bool(value)), where + ': invalid list')
    return value

def _keys(value, keys, where):
    _need(type(value) is dict and set(value) == set(keys), where + ': invalid keys')

def _index(value, where):
    _need(type(value) is int and 1 <= value <= 65536, where + ': invalid one-based index')
    return value

def _addr(value):
    _string(value, 'cell address', False)
    m = CELL.fullmatch(value)
    _need(m is not None, 'invalid cell address')
    col = 0
    for c in m[1]:
        col = col * 26 + ord(c) - 64
    _need(col <= 16384 and int(m[2]) <= 1048576, 'cell outside worksheet bounds')
    return value

def _number(value):
    _string(value, 'numeric lexical value', False)
    _need(len(value) <= 256 and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?', value) is not None, 'invalid number')
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid number') from exc
    _need(n.is_finite() and abs(n.adjusted()) <= 1024, 'numeric range unsupported')
    if n == 0:
        return '0'
    out = format(n, 'f')
    return out.rstrip('0').rstrip('.') if '.' in out else out

def _xml(raw, name, budget):
    _need(len(raw) <= MAX_XML, 'XML member too large: ' + name)
    # Removing NULs also exposes declarations in UTF16/UTF32; ElementTree never
    # receives a DTD, even in an otherwise unsupported encoding.
    lexical = raw.replace(b'\x00', b'').upper()
    _need(b'<!DOCTYPE' not in lexical and b'<!ENTITY' not in lexical, 'DTD/entity prohibited: ' + name)
    budget['xmlbytes'] += len(raw)
    _need(budget['xmlbytes'] <= 24 * 1024 * 1024, 'aggregate XML byte bound')
    try:
        # iterparse delivers starts while reading bounded chunks, so tree size
        # limits apply before a huge tree has been completely materialized.
        depth = 0
        parser = ET.iterparse(io.BytesIO(raw), events=('start', 'end'))
        for event, e in parser:
            if event == 'start':
                depth += 1
                budget['elements'] += 1
                budget['attributes'] += len(e.attrib)
                _need(depth <= 128 and budget['elements'] <= 250000 and
                      budget['attributes'] <= 500000, 'aggregate XML tree bound')
            else:
                depth -= 1
        root = parser.root
    except (ET.ParseError, ValueError, LookupError) as exc:
        raise ValueError('invalid/bounded XML: ' + name + ': ' + str(exc)) from exc
    stack = [(root, 1)]
    count = 0
    while stack:
        e, depth = stack.pop()
        count += 1
        _need(count <= MAX_ITEMS and depth <= 128, 'XML tree bounds: ' + name)
        _need(len(e.attrib) <= 128, 'XML attribute bounds')
        for text in [e.text, e.tail, *e.attrib.values()]:
            if text is not None:
                _need(len(text) <= MAX_STR, 'XML text bounds')
                budget['characters'] += len(text)
                _need(budget['characters'] <= 16 * 1024 * 1024, 'aggregate XML character bound')
        if e.tag in ('{' + MC + '}AlternateContent', '{' + W + '}altChunk'):
            raise Unsupported('alternate/active content unsupported')
        if e.tag in {'{' + ns + '}' + local for ns, local in (
            (P, 'oleObj'), (W, 'object'), (W, 'control'),
            (S, 'externalLink'), (S, 'oleObject'), (S, 'control'),
        )}:
            raise Unsupported('active/embedded Office object unsupported')
        if e.tag in {'{' + W + '}' + t for t in ('ins', 'del', 'moveFrom', 'moveTo', 'contentPart')}:
            raise Unsupported('tracked/embedded document content unsupported')
        if e.tag in ('{' + A + '}hlinkClick', '{' + A + '}hlinkMouseOver') and e.get('action'):
            raise Unsupported('active drawing hyperlink action unsupported')
        if e.tag == '{' + S + '}f' and e.text:
            # No interpretation or calculation; these formula families can have
            # external/native effects when opened by an Office implementation.
            if re.search(r'(?i)(?:\b(?:WEBSERVICE|RTD|HYPERLINK|CALL|REGISTER|EXEC|RUN|DDE)\s*\(|\|)', e.text):
                raise Unsupported('active/external formula unsupported')
        if e.tag in ('{' + W + '}fldSimple', '{' + W + '}instrText'):
            instruction = e.get('{' + W + '}instr', '') if e.tag.endswith('fldSimple') else e.text or ''
            # Split complex instructions are additionally checked once assembled.
            if re.search(r'(?i)\b(?:DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|LINK|DATABASE|MACROBUTTON|HYPERLINK)\b', instruction):
                raise Unsupported('active/external document field unsupported')
        stack.extend((child, depth + 1) for child in e)
    # Unnormalized headers/footers/comments are still checked for split active
    # field instructions; otherwise moving one dangerous field outside body
    # would bypass the package-wide active-content refusal.
    field = None
    for e in root.iter():
        if e.tag == '{' + W + '}fldChar':
            kind = e.get('{' + W + '}fldCharType')
            if kind == 'begin':
                if field is not None:
                    raise Unsupported('nested complex document field unsupported')
                field = ''
            elif kind == 'end':
                _need(field is not None, 'unbalanced document field')
                _safe_field(field)
                field = None
            elif kind == 'separate':
                _need(field is not None, 'unbalanced document field separator')
            else:
                raise Unsupported('unknown document field character')
        elif e.tag == '{' + W + '}instrText':
            _need(field is not None, 'orphan document field instruction')
            field += e.text or ''
    _need(field is None, 'unclosed document field')
    return root

def _part_name(name):
    _string(name, 'part name', False)
    _need(len(name) <= 512 and not name.startswith('/') and not name.endswith('/') and
          not any(c in name for c in '\\:%?#') and
          all(x not in ('', '.', '..') for x in name.split('/')) and
          all(ord(c) >= 32 and ord(c) != 127 for c in name), 'unsafe package part name')
    return name

class _Package:
    def __init__(self, data, fmt, nested=False, budget=None):
        _need(type(data) is bytes and 0 < len(data) <= MAX_DATA, 'input bytes bounds')
        _need(data.startswith(b'PK\x03\x04'), 'ZIP prefix must be local file header')
        _need(len(data) >= 22 and data[-22:-18] == b'PK\x05\x06', 'ZIP overlay/comment unsupported')
        _, disk, central_disk, disk_entries, entries, central_size, central_offset, comment_size = struct.unpack('<4s4H2LH', data[-22:])
        _need(disk == central_disk == 0 and disk_entries == entries and comment_size == 0,
              'multidisk/comment ZIP unsupported')
        _need(central_offset + central_size == len(data) - 22, 'ZIP central directory layout unsupported')
        self.parts = {}
        self.roots = {}
        self.rels = {}
        self.external = set()
        self.consumed_external = set()
        self.fmt = fmt
        if budget is None:
            budget = dict(elements=0, attributes=0, characters=0, xmlbytes=0, members=0, unpacked=0, packaged=0, compressed=0)
        budget['packaged'] += len(data)
        _need(budget['packaged'] <= 64 * 1024 * 1024, 'aggregate embedded package byte bound')
        try:
            with zipfile.ZipFile(io.BytesIO(data), 'r') as z:
                _need(not z.comment and data[-22:-18] == b'PK\x05\x06', 'ZIP overlay/comment unsupported')
                infos = z.infolist()
                _need(0 < len(infos) <= 1024, 'ZIP member count')
                _need(entries == len(infos), 'ZIP central member count mismatch')
                budget['members'] += len(infos)
                _need(budget['members'] <= 2048, 'aggregate embedded ZIP member bound')
                seen = set()
                total = 0
                for info in infos:
                    name = info.filename
                    _need(name == info.orig_filename and '\x00' not in name, 'NUL ZIP filename')
                    _need(name.casefold() not in seen, 'duplicate/case-colliding ZIP member')
                    seen.add(name.casefold())
                    _need(not info.flag_bits & 1 and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'encrypted/unsupported ZIP compression')
                    mode = stat.S_IFMT(info.external_attr >> 16)
                    _need(mode in (0, stat.S_IFREG, stat.S_IFDIR), 'special/symlink ZIP member')
                    if info.is_dir():
                        _part_name(name[:-1])
                        _need(info.file_size == 0, 'nonempty ZIP directory')
                        continue
                    _part_name(name)
                    _need(0 <= info.file_size <= MAX_MEMBER and info.compress_size >= 0, 'ZIP member size')
                    _need(info.file_size <= max(1, info.compress_size) * 200, 'ZIP compression ratio')
                    budget['compressed'] += info.compress_size
                    _need(budget['compressed'] <= 64 * 1024 * 1024, 'aggregate embedded compressed byte bound')
                    total += info.file_size
                    _need(total <= MAX_TOTAL, 'ZIP total size')
                    budget['unpacked'] += info.file_size
                    _need(budget['unpacked'] <= MAX_TOTAL, 'aggregate embedded ZIP size')
                    with z.open(info) as stream:
                        raw = stream.read(MAX_MEMBER + 1)
                        _need(len(raw) == info.file_size and not stream.read(1), 'ZIP declared size mismatch')
                    self.parts[name] = raw
        except (zipfile.BadZipFile, zlib.error, struct.error, RuntimeError, NotImplementedError, OSError, EOFError) as exc:
            raise ValueError('invalid or unsupported ZIP') from exc
        _need('[Content_Types].xml' in self.parts and '_rels/.rels' in self.parts, 'missing OPC roots')
        for name, raw in self.parts.items():
            low = name.lower()
            if any(x in low for x in ('vbaproject', 'activex', 'oleobject', '/externallinks/', 'customui', 'vbasignature')):
                raise Unsupported('active/external package content')
            if low.endswith(('.xml', '.rels')):
                self.roots[name] = _xml(raw, name, budget)
            elif low.endswith('.xlsx'):
                if nested:
                    raise Unsupported('nested embedded packages beyond one level')
                _Package(raw, 'xlsx', nested=True, budget=budget).view()
            elif low.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.emf', '.wmf')):
                pass  # Never decoded or rendered; only byte hashes may be asserted.
            elif re.fullmatch(r'(?:word|xl|ppt)/printerSettings/printerSettings[0-9]+\.bin', name):
                pass  # Opaque print metadata, checked by exact type+relationship below.
            else:
                raise Unsupported('unsupported binary member: ' + name)
        self._content_types()
        self._relationships()
        linked_types = {
            'worksheet': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml',
            'sharedStrings': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml',
            'slide': 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml',
        }
        for relmap in self.rels.values():
            for rel in relmap.values():
                if rel['role'] in linked_types:
                    _need(not rel['external'] and self.types[rel['target']] == linked_types[rel['role']], 'linked part content type mismatch')
                if rel['role'] == 'package':
                    _need(not rel['external'] and rel['target'].endswith('.xlsx') and
                          self.types[rel['target']] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'only safe embedded XLSX packages supported')
        for name in self.parts:
            if name.endswith('.bin'):
                _need(self.types[name] in {
                    'application/vnd.openxmlformats-officedocument.presentationml.printerSettings',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.printerSettings',
                } and any(r['role'] == 'printerSettings' and r['target'] == name and not r['external']
                          for relmap in self.rels.values() for r in relmap.values()), 'unlinked/invalid printer settings')
        office = [r for r in self.rels.get('', {}).values() if r['role'] == 'officeDocument']
        _need(len(office) == 1 and not office[0]['external'], 'root officeDocument relationship required')
        self.main = office[0]['target']
        expected, ns, local = MAIN[fmt]
        _need(self.types.get(self.main) == expected and self.roots.get(self.main) is not None and
              self.roots[self.main].tag == '{' + ns + '}' + local, 'wrong main Office part/type')

    def _content_types(self):
        root = self.roots['[Content_Types].xml']
        _need(root.tag == '{' + CT + '}Types', 'invalid content-types root')
        defaults, overrides = {}, {}
        for e in root:
            if e.tag == '{' + CT + '}Default':
                _keys(e.attrib, ('Extension', 'ContentType'), 'content-type default')
                key = _string(e.get('Extension'), 'extension', False).lower()
                _need(key not in defaults and re.fullmatch('[a-z0-9]+', key), 'duplicate/invalid default type')
                defaults[key] = e.get('ContentType')
            elif e.tag == '{' + CT + '}Override':
                _keys(e.attrib, ('PartName', 'ContentType'), 'content-type override')
                path = e.get('PartName')
                _need(path.startswith('/'), 'nonabsolute override')
                key = _part_name(path[1:])
                _need(key in self.parts and key not in overrides, 'duplicate/missing override part')
                overrides[key] = e.get('ContentType')
            else:
                raise ValueError('unknown content-type entry')
        self.types = {}
        for name in self.parts:
            if name == '[Content_Types].xml':
                continue
            typ = overrides.get(name, defaults.get(name.rsplit('.', 1)[-1].lower()))
            _string(typ, 'part content type', False)
            low = typ.lower()
            if any(x in low for x in ('macroenabled', 'vbaproject', 'activex', 'oleobject', 'ms-office.vba')):
                raise Unsupported('active content type')
            if name.endswith('.rels'):
                _need(typ == 'application/vnd.openxmlformats-package.relationships+xml', 'wrong relationships type')
            self.types[name] = typ

    def _relationships(self):
        for name, root in self.roots.items():
            if not name.endswith('.rels'):
                continue
            if name == '_rels/.rels':
                source = ''
            else:
                _need('/_rels/' in name, 'orphan relationship part')
                prefix, base = name.rsplit('/_rels/', 1)
                _need('/' not in base and base.endswith('.rels'), 'invalid relationship part')
                source = prefix + '/' + base[:-5]
                _need(source in self.parts, 'relationship source missing')
            _need(root.tag == '{' + R + '}Relationships' and source not in self.rels, 'invalid relationships root')
            relmap = {}
            for e in root:
                _need(e.tag == '{' + R + '}Relationship' and set(e.attrib) in
                      ({'Id', 'Type', 'Target'}, {'Id', 'Type', 'Target', 'TargetMode'}), 'invalid relationship')
                rid = _string(e.get('Id'), 'relationship id', False)
                _need(rid not in relmap, 'duplicate relationship ID')
                typ = _string(e.get('Type'), 'relationship type', False)
                if not (typ.startswith(O + '/') or typ in META_ROLES):
                    raise Unsupported('relationship Type must be official absolute URI')
                role = typ[len(O) + 1:] if typ.startswith(O + '/') else typ
                if role in UNSAFE_ROLES:
                    raise Unsupported('unsafe relationship: ' + role)
                if not (role in SAFE_ROLES or typ in META_ROLES):
                    raise Unsupported('unsupported relationship type: ' + typ)
                mode = e.get('TargetMode', 'Internal')
                _need(mode in ('Internal', 'External'), 'invalid TargetMode')
                target = _string(e.get('Target'), 'relationship target', False)
                if mode == 'External':
                    if role != 'hyperlink':
                        raise Unsupported('external non-hyperlink relationship')
                    parsed = urllib.parse.urlsplit(target)
                    _need(parsed.scheme == 'https' and parsed.netloc and parsed.hostname and
                          parsed.username is None and parsed.password is None and
                          not any(ord(c) <= 32 or ord(c) == 127 or c == '\\' for c in target), 'unsafe external hyperlink')
                    try:
                        parsed.port
                    except ValueError as exc:
                        raise ValueError('invalid hyperlink port') from exc
                    self.external.add((source, rid))
                else:
                    _need(not any(c in target for c in '\\:%?#') and not any(ord(c) < 32 for c in target), 'unsafe relationship path')
                    target = posixpath.normpath(target[1:] if target.startswith('/') else posixpath.join(posixpath.dirname(source), target))
                    _need(target in self.parts and not target.startswith('../'), 'relationship target missing/escaped')
                relmap[rid] = {'role': role, 'target': target, 'external': mode == 'External'}
            self.rels[source] = relmap

    def rel(self, source, rid, role):
        _string(rid, 'referenced relationship id', False)
        item = self.rels.get(source, {}).get(rid)
        _need(item is not None and item['role'] == role, 'missing/wrong linked relationship: ' + role)
        if item['external']:
            self.consumed_external.add((source, rid))
        return item

    def image(self, source, rid):
        rel = self.rel(source, rid, 'image')
        _need(not rel['external'] and self.types[rel['target']].startswith('image/'), 'invalid linked image')
        return hashlib.sha256(self.parts[rel['target']]).hexdigest()

    def view(self):
        if self.fmt == 'docx':
            value = self._docx()
        elif self.fmt == 'xlsx':
            value = self._xlsx()
        else:
            value = self._pptx()
        if self.external != self.consumed_external:
            raise Unsupported('external hyperlink outside supported visible content')
        return {'format': self.fmt, 'main_part': self.main,
                'parts': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(self.parts.items())}, self.fmt: value}

    def _docx(self):
        bodies = self.roots[self.main].findall('w:body', NS)
        _need(len(bodies) == 1, 'exactly one document body required')
        body = bodies[0]
        allowed = {'{' + W + '}' + t for t in ('p', 'tbl', 'sectPr')}
        if any(e.tag not in allowed for e in body):
            raise Unsupported('unsupported body content container')
        paragraphs = [_wtext(e) for e in body.findall('w:p', NS)]
        tables = [_table(e, W) for e in body.findall('w:tbl', NS)]
        links, fields, images = [], [], []
        complex_field = None
        for e in body.iter():
            if e.tag == '{' + W + '}hyperlink':
                rid, anchor = e.get('{' + O + '}id'), e.get('{' + W + '}anchor')
                _need(bool(rid) != bool(anchor), 'ambiguous hyperlink target')
                target = self.rel(self.main, rid, 'hyperlink')['target'] if rid else '#' + anchor
                links.append({'text': _wtext(e), 'target': target})
            elif e.tag == '{' + W + '}fldSimple':
                _need(complex_field is None, 'nested field encoding unsupported')
                fields.append(_safe_field(_string(e.get('{' + W + '}instr'), 'simple field instruction', False)))
            elif e.tag == '{' + W + '}fldChar':
                kind = e.get('{' + W + '}fldCharType')
                if kind == 'begin':
                    if complex_field is not None:
                        raise Unsupported('nested complex field')
                    complex_field = {'text': '', 'separated': False}
                elif kind == 'separate':
                    _need(complex_field is not None and not complex_field['separated'], 'unbalanced field separator')
                    complex_field['separated'] = True
                elif kind == 'end':
                    _need(complex_field is not None and complex_field['text'], 'unbalanced/empty complex field')
                    fields.append(_safe_field(complex_field['text']))
                    complex_field = None
                else:
                    raise Unsupported('unknown field character')
            elif e.tag == '{' + W + '}instrText':
                _need(complex_field is not None and not complex_field['separated'], 'field instruction outside field')
                complex_field['text'] += e.text or ''
            elif e.tag == '{' + A + '}blip':
                rid = e.get('{' + O + '}embed')
                _need(rid is not None and e.get('{' + O + '}link') is None, 'external/missing drawing image')
                images.append(self.image(self.main, rid))
            elif e.tag == '{' + V + '}imagedata':
                images.append(self.image(self.main, e.get('{' + O + '}id')))
        _need(complex_field is None, 'unclosed complex field')
        return {'paragraphs': paragraphs, 'tables': tables, 'hyperlinks': links, 'fields': fields, 'images': images}

    def _xlsx(self):
        root = self.roots[self.main]
        shared = []
        shared_rels = [r for r in self.rels.get(self.main, {}).values() if r['role'] == 'sharedStrings']
        _need(len(shared_rels) <= 1, 'multiple shared strings tables')
        if shared_rels:
            sr = self.roots.get(shared_rels[0]['target'])
            _need(sr is not None and sr.tag == '{' + S + '}sst', 'wrong shared strings part')
            shared = [_stext(e) for e in sr.findall('s:si', NS)]
        sheets, names, targets, ids = [], set(), set(), set()
        containers = root.findall('s:sheets', NS)
        _need(len(containers) == 1 and 0 < len(containers[0]) <= 1024, 'exactly one bounded workbook sheets container required')
        container = containers[0]
        for sh in container:
            _need(sh.tag == '{' + S + '}sheet', 'unknown sheet entry')
            name = _string(sh.get('name'), 'sheet name', False)
            sid = sh.get('sheetId')
            _need(name.casefold() not in names and sid and sid not in ids, 'duplicate sheet name/id')
            names.add(name.casefold()); ids.add(sid)
            rel = self.rel(self.main, sh.get('{' + O + '}id'), 'worksheet')
            part = rel['target']
            _need(part not in targets and not rel['external'], 'duplicate/external worksheet')
            targets.add(part)
            ws = self.roots.get(part)
            _need(ws is not None and ws.tag == '{' + S + '}worksheet', 'wrong linked worksheet')
            _need(len(ws.findall('s:sheetData', NS)) == 1 and len(ws.findall('s:hyperlinks', NS)) <= 1, 'duplicate/missing worksheet data container')
            cells = {}
            rows = set()
            for row in ws.findall('s:sheetData/s:row', NS):
                rn = row.get('r')
                _need(rn is not None and re.fullmatch('[1-9][0-9]{0,6}', rn) and int(rn) <= 1048576 and rn not in rows, 'invalid/duplicate row')
                rows.add(rn)
                for c in row:
                    _need(c.tag == '{' + S + '}c', 'unknown row content')
                    addr = _addr(c.get('r'))
                    _need(CELL.fullmatch(addr)[2] == rn and addr not in cells, 'cell row mismatch/duplicate')
                    cells[addr] = _cell(c, shared)
            hyperlinks = []
            for h in ws.findall('s:hyperlinks/s:hyperlink', NS):
                ref = _cell_range(h.get('ref'))
                rid, location = h.get('{' + O + '}id'), h.get('location')
                _need(bool(rid) != bool(location), 'ambiguous sheet hyperlink')
                target = self.rel(part, rid, 'hyperlink')['target'] if rid else '#' + location
                hyperlinks.append({'ref': ref, 'target': target})
            sheets.append({'name': name, 'part': part, 'cells': cells, 'hyperlinks': hyperlinks})
        return {'sheets': sheets}

    def _pptx(self):
        root = self.roots[self.main]
        containers = root.findall('p:sldIdLst', NS)
        _need(len(containers) == 1 and 0 < len(containers[0]) <= 1024, 'exactly one bounded presentation slide list required')
        container = containers[0]
        slides, targets, ids = [], set(), set()
        for item in container:
            _need(item.tag == '{' + P + '}sldId', 'unknown slide entry')
            sid = item.get('id')
            _need(sid and sid not in ids, 'duplicate/missing slide ID')
            ids.add(sid)
            rel = self.rel(self.main, item.get('{' + O + '}id'), 'slide')
            part = rel['target']
            _need(part not in targets and not rel['external'], 'duplicate/external slide')
            targets.add(part)
            slide = self.roots.get(part)
            _need(slide is not None and slide.tag == '{' + P + '}sld', 'wrong linked slide')
            _need(len(slide.findall('p:cSld', NS)) == 1, 'exactly one slide content container required')
            trees = slide.findall('p:cSld/p:spTree', NS)
            _need(len(trees) == 1, 'exactly one slide shape tree required')
            tree = trees[0]
            texts = [_atext(e) for e in tree.iter('{' + A + '}p')]
            tables = [_table(t, A) for t in tree.iter('{' + A + '}tbl')]
            links, images = [], []
            for e in tree.iter():
                if e.tag in ('{' + A + '}r', '{' + A + '}fld'):
                    hs = e.findall('a:rPr/a:hlinkClick', NS)
                    _need(len(hs) <= 1, 'duplicate text hyperlink')
                    for h in hs:
                        if h.get('action'):
                            raise Unsupported('slide hyperlink actions unsupported')
                        target = self.rel(part, h.get('{' + O + '}id'), 'hyperlink')['target']
                        links.append({'text': ''.join(x.text or '' for x in e.findall('a:t', NS)), 'target': target})
                elif e.tag == '{' + A + '}hlinkMouseOver':
                    raise Unsupported('mouseover hyperlinks unsupported')
                elif e.tag == '{' + A + '}blip':
                    rid = e.get('{' + O + '}embed')
                    _need(rid is not None and e.get('{' + O + '}link') is None, 'external/missing image')
                    images.append(self.image(part, rid))
            slides.append({'part': part, 'text': texts, 'tables': tables, 'hyperlinks': links, 'images': images})
        return {'slides': slides}

def _wtext(element):
    pieces = []
    for e in element.iter():
        if e.tag == '{' + W + '}t':
            pieces.append(e.text or '')
        elif e.tag == '{' + W + '}tab':
            pieces.append('\t')
        elif e.tag in ('{' + W + '}br', '{' + W + '}cr'):
            pieces.append('\n')
        elif e.tag in ('{' + W + '}sym', '{' + W + '}txbxContent'):
            raise Unsupported('symbol/textbox content unsupported')
    return ''.join(pieces)

def _safe_field(instruction):
    if re.search(r'(?i)\b(?:DDEAUTO|DDE|INCLUDETEXT|INCLUDEPICTURE|LINK|DATABASE|MACROBUTTON|HYPERLINK)\b', instruction):
        raise Unsupported('active/external document field unsupported')
    return instruction

def _stext(element):
    if element.find('.//s:rPh', NS) is not None:
        raise Unsupported('phonetic shared strings unsupported')
    return ''.join(e.text or '' for e in element.iter('{' + S + '}t'))

def _atext(element):
    out = []
    for e in element.iter():
        if e.tag == '{' + A + '}t':
            out.append(e.text or '')
        elif e.tag == '{' + A + '}br':
            out.append('\n')
    return ''.join(out)

def _table(table, ns):
    tag = '{' + ns + '}'
    _need(sum(1 for _ in table.iter(tag + ('tbl' if ns == W else 'tbl'))) == 1, 'nested tables unsupported')
    rowtag, celltag = ('tr', 'tc') if ns == W else ('tr', 'tc')
    rows = []
    for row in table.findall(tag + rowtag):
        cells = []
        for cell in row.findall(tag + celltag):
            if ns == W:
                if any(child.tag not in {tag + 'p', tag + 'tcPr'} for child in cell):
                    raise Unsupported('unsupported table cell container')
                cells.append('\n'.join(_wtext(p) for p in cell.findall(tag + 'p')))
            else:
                cells.append('\n'.join(_atext(p) for p in cell.findall('a:txBody/a:p', NS)))
        rows.append(cells)
    return rows

def _cell_range(value):
    _string(value, 'cell range', False)
    pieces = value.split(':')
    _need(1 <= len(pieces) <= 2, 'invalid cell range')
    for address in pieces:
        _addr(address)
    return value

def _cell(c, shared):
    fs, vs, ins = c.findall('s:f', NS), c.findall('s:v', NS), c.findall('s:is', NS)
    _need(len(fs) <= 1 and len(vs) <= 1 and len(ins) <= 1, 'duplicate cell value/formula')
    formula = None
    if fs:
        if fs[0].attrib:
            raise Unsupported('shared/array/data-table formula encoding unsupported')
        formula = _string(fs[0].text, 'formula', False)
        _need(not formula.startswith('='), 'formula must omit leading equals')
        if '[' in formula or ']' in formula:
            raise Unsupported('external/structured formula references unsupported')
    typ = c.get('t', 'n')
    raw = vs[0].text if vs else None
    if typ == 'inlineStr':
        _need(len(ins) == 1 and not vs and formula is None, 'invalid inline string cell')
        value, typ = _stext(ins[0]), 'text'
    else:
        _need(not ins, 'unexpected inline string')
        if typ == 's':
            _need(formula is None and raw is not None and re.fullmatch('[0-9]+', raw) and int(raw) < len(shared), 'invalid shared-string index')
            value, typ = shared[int(raw)], 'text'
        elif typ in ('n', 'str', 'b', 'e', 'd'):
            if raw is None:
                _need(typ in ('n', 'str'), 'missing typed cell value')
                value, typ = None, 'blank'
            elif typ == 'n':
                value, typ = _number(raw), 'number'
            elif typ == 'b':
                _need(raw in ('0', '1'), 'invalid boolean cell')
                value, typ = raw == '1', 'boolean'
            elif typ == 'str':
                value, typ = raw, 'text'
            elif typ == 'e':
                value, typ = raw, 'error'
            else:
                _need(re.fullmatch(r'\d{4}-\d\d-\d\d(?:T\d\d:\d\d:\d\d(?:\.\d+)?Z?)?', raw) is not None, 'invalid ISO cell date')
                value, typ = raw, 'date'
        else:
            raise Unsupported('unsupported cell type: ' + typ)
    return {'type': typ, 'value': value, 'formula': formula}

def inspect(data: bytes, format: str) -> dict:
    _need(type(format) is str and format in MAIN, 'format must be docx|xlsx|pptx')
    try:
        return _Package(data, format).view()
    except (RecursionError, OverflowError, UnicodeError, KeyError, IndexError, TypeError) as exc:
        raise ValueError('malformed/unsupported Office package') from exc

def _selector(view, selector):
    _string(selector, 'preservation selector', False)
    _need(len(selector) <= 1024 and selector.startswith('/') and not any(c in selector for c in '~*'), 'invalid selector')
    bits = selector[1:].split('/')
    _need(all(bits) and bits[0] == view['format'] and len(bits) <= 10, 'selector outside semantic view')
    _need('part' not in bits, 'part metadata is not a semantic preservation selector')
    if bits[0] in ('xlsx', 'pptx'):
        _need(len(bits) >= 2 and bits[1] == ('sheets' if bits[0] == 'xlsx' else 'slides'), 'selector must select sheets/slides content')
    current = view
    for bit in bits:
        if type(current) is dict:
            _need(bit in current, 'selector key missing')
            current = current[bit]
        elif type(current) is list:
            _need(re.fullmatch('0|[1-9][0-9]{0,5}', bit) is not None and int(bit) < len(current), 'selector index missing')
            current = current[int(bit)]
        else:
            raise ValueError('selector traverses scalar')
    return current

def _expected_strings(value, where, hashes=False):
    for item in _list(value, where):
        _string(item, where)
        if hashes:
            _need(SHA.fullmatch(item) is not None, 'invalid image SHA256')

def _expected_tables(value):
    for table in _list(value, 'tables'):
        for row in _list(table, 'table rows', True):
            _expected_strings(_list(row, 'table cells', True), 'table cell')

def _expected_links(value, sheet=False):
    for link in _list(value, 'hyperlinks'):
        _keys(link, ('ref', 'target') if sheet else ('text', 'target'), 'hyperlink')
        if sheet:
            _cell_range(link['ref'])
        else:
            _string(link['text'], 'hyperlink text')
        _string(link['target'], 'hyperlink target', False)

def _expected_cells(value):
    addresses = set()
    for cell in _list(value, 'cells', True):
        _keys(cell, ('address', 'type', 'value', 'formula'), 'expected cell')
        _addr(cell['address'])
        _need(cell['address'] not in addresses, 'duplicate expected cell address')
        addresses.add(cell['address'])
        typ, val, formula = cell['type'], cell['value'], cell['formula']
        _need(type(typ) is str and typ in ('text', 'number', 'boolean', 'error', 'date', 'blank'), 'expected cell type')
        if typ == 'boolean':
            _need(type(val) is bool, 'expected boolean cell value')
        elif typ == 'blank':
            _need(val is None, 'expected blank value')
        else:
            _string(val, 'expected cell value')
            if typ == 'number':
                _need(_number(val) == val, 'expected number must be canonical')
        if formula is not None:
            _string(formula, 'expected formula', False)
            _need(not formula.startswith('='), 'expected formula must omit equals')

def grade_bytes(data: bytes, format: str, requirements: list, before: bytes | None = None) -> list[str]:
    _need(type(format) is str and format in MAIN, 'format must be docx|xlsx|pptx')
    _list(requirements, 'requirements', True)
    _need(len(requirements) <= 256, 'too many requirements')
    # Schema validation completes before parsing bytes, with no task-supplied code.
    seen = set()
    for req in requirements:
        _need(type(req) is dict and type(req.get('op')) is str, 'invalid requirement')
        op = req['op']
        if op == 'xlsx.calculation':
            raise Unsupported('real formula calculation is unsupported')
        if op in {'docx.paragraphs', 'docx.tables', 'docx.hyperlinks', 'docx.fields', 'docx.images', 'xlsx.sheets', 'pptx.slides'}:
            _keys(req, ('op', 'equals'), op)
            if op == 'docx.tables':
                _expected_tables(req['equals'])
            elif op == 'docx.hyperlinks':
                _expected_links(req['equals'])
            elif op == 'pptx.slides':
                for slide in _list(req['equals'], 'slides'):
                    _expected_strings(slide, 'slide text')
            else:
                _expected_strings(req['equals'], op, op.endswith('.images'))
        elif op in {'xlsx.cells', 'xlsx.hyperlinks'}:
            _keys(req, ('op', 'sheet', 'equals'), op)
            _string(req['sheet'], 'sheet', False)
            _expected_cells(req['equals']) if op == 'xlsx.cells' else _expected_links(req['equals'], True)
        elif op in {'pptx.tables', 'pptx.hyperlinks', 'pptx.images'}:
            _keys(req, ('op', 'slide', 'equals'), op)
            _index(req['slide'], 'slide')
            if op == 'pptx.tables':
                _expected_tables(req['equals'])
            elif op == 'pptx.hyperlinks':
                _expected_links(req['equals'])
            else:
                _expected_strings(req['equals'], 'images', True)
        elif op == 'preserve.parts':
            _keys(req, ('op', 'parts'), op)
            for part in _list(req['parts'], 'preserved parts', True):
                _part_name(part)
            _need(len(set(req['parts'])) == len(req['parts']), 'duplicate preserved part')
        elif op == 'preserve.view':
            _keys(req, ('op', 'selectors'), op)
            for selector in _list(req['selectors'], 'selectors', True):
                _string(selector, 'selector', False)
            _need(len(set(req['selectors'])) == len(req['selectors']), 'duplicate selector')
        else:
            raise Unsupported('unsupported predicate: ' + op)
        if not op.startswith('preserve.'):
            _need(op.startswith(format + '.'), 'predicate format mismatch')
        canonical = json.dumps(req, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        _need(canonical not in seen, 'duplicate requirement')
        seen.add(canonical)
    view = inspect(data, format)
    old = inspect(before, format) if before is not None else None
    successful, covered_links = [], set()
    for req in requirements:
        op = req['op']
        if op == 'preserve.parts':
            _need(old is not None, 'preservation requires before bytes')
            for part in req['parts']:
                _need(part in old['parts'] and view['parts'].get(part) == old['parts'][part], 'preserved part changed/missing: ' + part)
        elif op == 'preserve.view':
            _need(old is not None, 'preservation requires before bytes')
            for selector in req['selectors']:
                _need(_selector(view, selector) == _selector(old, selector), 'preserved view changed: ' + selector)
        else:
            key = op.split('.')[1]
            if format == 'docx':
                actual = view['docx'][key]
                if key == 'hyperlinks':
                    covered_links.add(('docx', 0))
            elif format == 'xlsx':
                if key == 'sheets':
                    actual = [s['name'] for s in view['xlsx']['sheets']]
                else:
                    sheets = [s for s in view['xlsx']['sheets'] if s['name'] == req['sheet']]
                    _need(len(sheets) == 1, 'required sheet missing')
                    sheet = sheets[0]
                    if key == 'cells':
                        actual = []
                        for c in req['equals']:
                            addr = c['address']
                            _need(addr in sheet['cells'], 'required cell missing: ' + addr)
                            actual.append({'address': addr, **sheet['cells'][addr]})
                    else:
                        actual = sheet['hyperlinks']
                        covered_links.add(('xlsx', req['sheet']))
            else:
                if key == 'slides':
                    actual = [s['text'] for s in view['pptx']['slides']]
                else:
                    i = req['slide'] - 1
                    _need(i < len(view['pptx']['slides']), 'required slide missing')
                    actual = view['pptx']['slides'][i][key]
                    if key == 'hyperlinks':
                        covered_links.add(('pptx', i))
            _need(actual == req['equals'], 'predicate mismatch: ' + op)
        successful.append(op + ': ' + json.dumps(req, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    if format == 'docx':
        groups = [(('docx', 0), view['docx']['hyperlinks'])]
    elif format == 'xlsx':
        groups = [(('xlsx', s['name']), s['hyperlinks']) for s in view['xlsx']['sheets']]
    else:
        groups = [(('pptx', i), s['hyperlinks']) for i, s in enumerate(view['pptx']['slides'])]
    for ident, links in groups:
        if any(x['target'].startswith('https://') for x in links):
            _need(ident in covered_links, 'external hyperlinks require explicit exact hyperlink predicate')
    return successful
