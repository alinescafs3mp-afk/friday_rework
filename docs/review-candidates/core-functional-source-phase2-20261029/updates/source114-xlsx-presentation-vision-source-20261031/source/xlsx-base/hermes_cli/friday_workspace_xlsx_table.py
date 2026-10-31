"""Bounded explicit XLSX creation and exact-text left join; no formula engine.

Creates a derived plain table, never claims to preserve source formatting or
package parts. Existing source snapshot/custody and atomic publication apply.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from hermes_cli.friday_user_scope import ScopeDenied, workspace_document
from hermes_cli.friday_workspace_revision import check
from hermes_cli.friday_workspace_docx import _create_bytes
from hermes_cli.friday_workspace_xlsx_recalculate import Book, S, R, P, RecalculationRefused

GUIDANCE = 'XLSX creation: format=xlsx_create, NEW .xlsx path, content JSON {"sheets":[{"name":"Data","rows":[["id","amount","date","note"],["0001",{"type":"decimal","value":"1200.50"},{"type":"date","value":"2026-04-05"},"=1+1"]]}]}. Strings (including =,+,-,@ prefixes and long IDs) are literal text; no prefix inference. Explicit native formulas use {"type":"formula","value":"C2*D2"} (two-cell multiplication) or {"type":"formula","value":"SUM(Orders!G2:G5)"}; references must be numeric, in bounds and acyclic. A sheet may add "table":{"name":"OrdersTable","ref":"A1:G5"}; top-level "names":{"OrderSourceRows":"Orders!$A$2:$G$5"} declares native names. Formulas are not evaluated here; recalculate the returned copy separately. null or {"type":"blank"} is blank, distinct from numeric 0. Optional explicit {"type":"string","value":"0001"}; plain numbers/booleans accepted. Decimal value is a dot-decimal string, at most 15 significant digits/12 places; dates are ISO YYYY-MM-DD (1900-03-01 onward), real Excel dates displayed dd.mm.yyyy. At most 8 uniquely named sheets, 512 rows/sheet, 64 columns, 4096 cells total, 100000 UTF-8 content bytes; rows must be rectangular. XLSX join: format=xlsx_join, NEW .xlsx path, content JSON {"source":"input.xlsx","left_sheet":"Orders","right_sheet":"Codes","key":"order_id","sheet":"Joined"}. Exact-text LEFT join of two different sheets in one own-workspace workbook: preserve left order and every left row, append right non-key columns, unmatched right cells blank. Both sides require unique nonempty text keys and unique text headers; overlapping non-key names refuse. No case/Unicode/space folding or numeric-key coercion. Produces a new plain table, not a formatting-preserving copy; literal scalar source cells only, selected formulas/merged cells/tables and unsupported numeric formats refuse. Source remains unchanged. '

MAX_CONTENT = 100000
MAX_ROWS = 512
MAX_COLS = 64
MAX_CELLS = 4096
MAX_SHEETS = 8
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
DECIMAL = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?\Z')


class TableRefused(ValueError):
    """Fixed public reason; never caller content, XML or filesystem details."""


def deny(reason='xlsx_table_invalid_spec'):
    raise TableRefused(reason)


def text(value):
    if not isinstance(value, str) or len(value) > 32767 or any(not (
            ord(c) in (9, 10, 13) or 0x20 <= ord(c) <= 0xD7FF
            or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
            for c in value):
        deny('xlsx_table_invalid_text')
    if len(value.encode('utf-16-le'))//2 > 32767: deny('xlsx_table_invalid_text')
    return value


def sheet_name(value):
    text(value)
    if (not 1 <= len(value.encode('utf-16-le'))//2 <= 31 or not value.strip()
            or any(ord(char) < 32 for char in value) or re.search(r'[\[\]:*?/\\]', value)
            or value.startswith("'") or value.endswith("'")):
        deny('xlsx_table_sheet_name')
    return value


def parse(content):
    if not isinstance(content, str) or len(content) > MAX_CONTENT:
        deny('xlsx_table_content_limit')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: deny()
            result[key] = value
        return result
    try:
        if len(content.encode('utf-8')) > MAX_CONTENT:
            deny('xlsx_table_content_limit')
        return json.loads(content, object_pairs_hook=pairs, parse_constant=lambda _: deny())
    except (ValueError, RecursionError, UnicodeError):
        deny()


def number(raw):
    if not isinstance(raw, str) or len(raw) > 64 or not DECIMAL.fullmatch(raw):
        deny('xlsx_table_decimal')
    value = Decimal(raw)
    # Excel has 15 significant decimal digits. Identifiers belong in strings.
    if not value.is_finite() or len(value.as_tuple().digits) > 15 or abs(value) > Decimal('1e15'):
        deny('xlsx_table_number_precision')
    scale = len(raw.partition('.')[2])
    return ('number', raw, '0.'+'0'*scale if scale else 'General')


def scalar(value):
    if value is None: return ('blank', None, 'General')
    if isinstance(value, str): return ('string', text(value), 'General')
    if type(value) is bool: return ('boolean', '1' if value else '0', 'General')
    if type(value) in (int, float):
        return number(format(Decimal(str(value)), 'f'))
    if not isinstance(value, dict): deny()
    kind = value.get('type')
    if kind == 'blank' and set(value) == {'type'}: return ('blank', None, 'General')
    if set(value) != {'type', 'value'}: deny()
    if kind == 'string': return ('string', text(value['value']), 'General')
    if kind == 'decimal': return number(value['value'])
    if kind == 'formula':
        raw = value['value']
        if not isinstance(raw, str) or not 1 <= len(raw) <= 512: deny('xlsx_formula_invalid')
        if raw.startswith('='): raw = raw[1:]
        if not raw: deny('xlsx_formula_invalid')
        return ('formula', raw, 'General')
    if kind == 'date':
        raw = value['value']
        if not isinstance(raw, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw): deny('xlsx_table_date')
        try: actual = date.fromisoformat(raw)
        except ValueError: deny('xlsx_table_date')
        if not date(1900, 3, 1) <= actual <= date(9999, 12, 31): deny('xlsx_table_date')
        return ('date', str((actual-date(1899, 12, 30)).days), 'dd.mm.yyyy')
    deny()


def colname(n):
    result = ''
    while n:
        n, rem = divmod(n-1, 26); result = chr(65+rem)+result
    return result


CELL_REF = r'\$?[A-Za-z]{1,3}\$?[1-9][0-9]*'
SHEET_REF = r"(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_.]*)!"
REF = r'(?:' + SHEET_REF + r')?' + CELL_REF
REFERENCE = re.compile(r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_.]*)!)?(?P<col>\$?[A-Za-z]{1,3})(?P<row>\$?[1-9][0-9]*)\Z")
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,127}\Z')


def native_name(value):
    if (not isinstance(value, str) or not NAME.fullmatch(value)
            or re.fullmatch(CELL_REF, value, re.I)
            or value.upper() in {'R', 'C'}
            or re.fullmatch(r'R[1-9][0-9]*C[1-9][0-9]*', value, re.I)):
        deny('xlsx_table_native_name')
    return value


def quote_sheet(name):
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', name) and not re.fullmatch(CELL_REF, name, re.I): return name
    return "'" + name.replace("'", "''") + "'"


def reference(raw, default, sheets):
    match = REFERENCE.fullmatch(raw)
    if not match: deny('xlsx_formula_reference')
    token = match.group('sheet')
    requested = default
    if token: requested = token[1:-1].replace("''", "'") if token.startswith("'") else token
    actual = next((name for name in sheets if name.casefold() == requested.casefold()), None)
    if actual is None: deny('xlsx_formula_reference')
    letters = match.group('col'); raw_row = match.group('row')
    col = 0
    for char in letters.lstrip('$').upper(): col = col * 26 + ord(char) - 64
    row = int(raw_row.lstrip('$'))
    if not 1 <= row <= sheets[actual][0] or not 1 <= col <= sheets[actual][1]: deny('xlsx_formula_reference')
    return actual, row, col, letters.upper() + raw_row, bool(token)


def rendered_ref(ref, with_sheet=False):
    return (quote_sheet(ref[0]) + '!' if with_sheet else '') + ref[3]


def normalize_document(sheets, tables, names):
    if not 1 <= len(sheets) <= MAX_SHEETS: deny('xlsx_table_limit')
    sheets = [(sheet_name(name), rows) for name, rows in sheets]
    names_by_fold = {name.casefold(): name for name, _ in sheets}
    if len(names_by_fold) != len(sheets): deny('xlsx_table_sheet_name')
    dimensions = {}; cells = {}; count = 0
    for name, rows in sheets:
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS: deny('xlsx_table_limit')
        width = len(rows[0])
        if not 1 <= width <= MAX_COLS or any(not isinstance(row, list) or len(row) != width for row in rows): deny('xlsx_table_rectangular_rows')
        count += len(rows) * width
        if count > MAX_CELLS: deny('xlsx_table_limit')
        dimensions[name] = (len(rows), width)
        for row_index, values in enumerate(rows, 1):
            for column, item in enumerate(values, 1):
                if not isinstance(item, tuple) or len(item) != 3: deny()
                cells[name.casefold(), row_index, column] = item
    dependencies = {}; normalized = []; reference_count = 0
    for name, rows in sheets:
        output_rows = []
        for row_index, values in enumerate(rows, 1):
            output = []
            for column, item in enumerate(values, 1):
                kind, value, fmt = item
                if kind != 'formula': output.append(item); continue
                multiply = re.fullmatch('(' + REF + r')\*(' + REF + ')', value)
                total = re.fullmatch(r'SUM\((' + REF + '):(' + REF + r')\)', value, re.I)
                if not multiply and not total: deny('xlsx_formula_unsupported')
                parts = multiply.groups() if multiply else total.groups()
                refs = [reference(parts[0], name, dimensions)]
                refs.append(reference(parts[1], refs[0][0] if total else name, dimensions))
                if total and (refs[0][0] != refs[1][0] or refs[0][1] > refs[1][1] or refs[0][2] > refs[1][2]): deny('xlsx_formula_reference')
                targets = refs if multiply else [(refs[0][0], row, col) for row in range(min(refs[0][1], refs[1][1]), max(refs[0][1], refs[1][1]) + 1) for col in range(min(refs[0][2], refs[1][2]), max(refs[0][2], refs[1][2]) + 1)]
                reference_count += len(targets)
                if reference_count > 20000: deny('xlsx_formula_dependency_limit')
                source = (name.casefold(), row_index, column); dependencies[source] = set()
                for target in targets:
                    target_sheet, row, col = target[:3]
                    target_cell = cells[target_sheet.casefold(), row, col]
                    if target_cell[0] not in ('number', 'formula'): deny('xlsx_formula_reference')
                    if target_cell[0] == 'formula': dependencies[source].add((target_sheet.casefold(), row, col))
                if multiply: value = rendered_ref(refs[0], refs[0][4]) + '*' + rendered_ref(refs[1], refs[1][4])
                else: value = 'SUM(' + rendered_ref(refs[0], refs[0][4] or refs[1][4]) + ':' + rendered_ref(refs[1]) + ')'
                output.append(('formula', value, 'General'))
            output_rows.append(output)
        normalized.append((name, output_rows))
    state = {}
    for start in dependencies:
        stack = [(start, False)]
        while stack:
            node, finished = stack.pop()
            if finished: state[node] = 2; continue
            if state.get(node) == 1: deny('xlsx_formula_cycle')
            if state.get(node) == 2: continue
            state[node] = 1; stack.append((node, True))
            for target in dependencies.get(node, ()):
                if state.get(target) == 1: deny('xlsx_formula_cycle')
                if state.get(target) != 2: stack.append((target, False))
    if not isinstance(tables, dict) or not isinstance(names, dict) or len(tables) > MAX_SHEETS or len(names) > 16: deny('xlsx_table_limit')
    native_names = {}; normalized_tables = {}
    for requested, table in tables.items():
        actual = names_by_fold.get(requested.casefold())
        if actual is None or not isinstance(table, dict) or set(table) != {'name', 'ref'}: deny('xlsx_table_invalid_table')
        table_name = native_name(table['name'])
        if table_name.casefold() in native_names: deny('xlsx_table_native_name')
        native_names[table_name.casefold()] = table_name
        if not isinstance(table['ref'], str): deny('xlsx_table_invalid_table')
        match = re.fullmatch('(' + CELL_REF + '):(' + CELL_REF + ')', table['ref'])
        if not match: deny('xlsx_table_invalid_table')
        refs = [reference(part, actual, dimensions) for part in match.groups()]
        if (any(ref[0] != actual or ref[4] for ref in refs)
                or refs[0][1] > refs[1][1] or refs[0][2] > refs[1][2]): deny('xlsx_table_invalid_table')
        first_row, last_row = sorted((refs[0][1], refs[1][1])); first_col, last_col = sorted((refs[0][2], refs[1][2]))
        if last_row - first_row < 1: deny('xlsx_table_invalid_table')
        headers = [cells[actual.casefold(), first_row, col] for col in range(first_col, last_col + 1)]
        labels = [item[1] for item in headers]
        if any(item[0] != 'string' or not item[1] for item in headers) or len({label.casefold() for label in labels if isinstance(label, str)}) != len(labels): deny('xlsx_table_invalid_table')
        normalized_tables[actual] = {'name':table_name, 'ref':refs[0][3].replace('$', '') + ':' + refs[1][3].replace('$', ''), 'columns':labels, 'id':len(normalized_tables) + 1}
    normalized_names = {}
    for name, target in names.items():
        native = native_name(name)
        if native.casefold() in native_names: deny('xlsx_table_native_name')
        native_names[native.casefold()] = native
        if not isinstance(target, str): deny('xlsx_table_invalid_name')
        match = re.fullmatch('(' + REF + '):(' + REF + ')', target)
        if not match: deny('xlsx_table_invalid_name')
        refs = [reference(match.group(1), sheets[0][0], dimensions)]
        refs.append(reference(match.group(2), refs[0][0], dimensions))
        if (refs[0][0] != refs[1][0] or not (refs[0][4] or refs[1][4])
                or refs[0][1] > refs[1][1] or refs[0][2] > refs[1][2]): deny('xlsx_table_invalid_name')
        normalized_names[native] = quote_sheet(refs[0][0]) + '!' + refs[0][3] + ':' + refs[1][3]
    return normalized, normalized_tables, normalized_names


def render_document(sheets, checkpoint=lambda: None, *, tables=None, names=None):
    sheets, tables, names = normalize_document(sheets, {} if tables is None else tables, {} if names is None else names)
    formats = ['General']; parts = {}; ct = '{http://schemas.openxmlformats.org/package/2006/content-types}'
    types = ET.Element(ct+'Types')
    ET.SubElement(types, ct+'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(types, ct+'Default', Extension='xml', ContentType='application/xml')
    for name, suffix in [('workbook.xml', 'sheet.main'), ('styles.xml', 'styles')]:
        ET.SubElement(types, ct+'Override', PartName='/xl/'+name, ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.'+suffix+'+xml')
    package_rels = ET.Element(P+'Relationships')
    ET.SubElement(package_rels, P+'Relationship', Id='rId1', Type=R[1:-1]+'/officeDocument', Target='xl/workbook.xml')
    workbook = ET.Element(S+'workbook'); native_sheets = ET.SubElement(workbook, S+'sheets')
    rels = ET.Element(P+'Relationships'); has_formulas = False
    for index, (name, rows) in enumerate(sheets, 1):
        checkpoint()
        ET.SubElement(native_sheets, S+'sheet', name=name, sheetId=str(index), attrib={R+'id':'rId'+str(index)})
        ET.SubElement(rels, P+'Relationship', Id='rId'+str(index), Type=R[1:-1]+'/worksheet', Target='worksheets/sheet'+str(index)+'.xml')
        ET.SubElement(types, ct+'Override', PartName='/xl/worksheets/sheet'+str(index)+'.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
        root = ET.Element(S+'worksheet'); data = ET.SubElement(root, S+'sheetData')
        for row_index, values in enumerate(rows, 1):
            checkpoint(); row = ET.SubElement(data, S+'row', r=str(row_index))
            for column, (kind, value, fmt) in enumerate(values, 1):
                cell = ET.SubElement(row, S+'c', r=colname(column)+str(row_index))
                if kind == 'blank': continue
                if kind == 'string':
                    cell.set('t', 'inlineStr'); inline = ET.SubElement(cell, S+'is')
                    ET.SubElement(inline, S+'t', attrib={XML_SPACE:'preserve'}).text = text(value)
                elif kind == 'formula':
                    has_formulas = True; ET.SubElement(cell, S+'f').text = value
                else:
                    cell.set('t', 'b' if kind == 'boolean' else 'n')
                    if fmt not in formats: formats.append(fmt)
                    if len(formats) > 32: deny('xlsx_table_style_limit')
                    if fmt != 'General': cell.set('s', str(formats.index(fmt)))
                    ET.SubElement(cell, S+'v').text = value
        parts['xl/worksheets/sheet'+str(index)+'.xml'] = root
        table = tables.get(name)
        if table:
            table_id = table['id']; table_parts = ET.SubElement(root, S+'tableParts', count='1')
            ET.SubElement(table_parts, S+'tablePart', attrib={R+'id':'rId1'})
            sheet_rels = ET.Element(P+'Relationships')
            ET.SubElement(sheet_rels, P+'Relationship', Id='rId1', Type=R[1:-1]+'/table', Target='../tables/table'+str(table_id)+'.xml')
            parts['xl/worksheets/_rels/sheet'+str(index)+'.xml.rels'] = sheet_rels
            native_table = ET.Element(S+'table', id=str(table_id), name=table['name'], displayName=table['name'], ref=table['ref'], totalsRowShown='0')
            ET.SubElement(native_table, S+'autoFilter', ref=table['ref'])
            columns = ET.SubElement(native_table, S+'tableColumns', count=str(len(table['columns'])))
            for column, label in enumerate(table['columns'], 1): ET.SubElement(columns, S+'tableColumn', id=str(column), name=label)
            ET.SubElement(native_table, S+'tableStyleInfo', name='TableStyleMedium2', showFirstColumn='0', showLastColumn='0', showRowStripes='1', showColumnStripes='0')
            parts['xl/tables/table'+str(table_id)+'.xml'] = native_table
            ET.SubElement(types, ct+'Override', PartName='/xl/tables/table'+str(table_id)+'.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml')
    if names:
        defined = ET.SubElement(workbook, S+'definedNames')
        for name, target in names.items(): ET.SubElement(defined, S+'definedName', name=name).text = target
    if has_formulas: ET.SubElement(workbook, S+'calcPr', calcId='191029', calcMode='auto', fullCalcOnLoad='1', forceFullCalc='1')
    ET.SubElement(rels, P+'Relationship', Id='styles', Type=R[1:-1]+'/styles', Target='styles.xml')
    styles = ET.Element(S+'styleSheet'); numfmts = ET.SubElement(styles, S+'numFmts', count=str(len(formats)-1))
    for index, fmt in enumerate(formats[1:], 164): ET.SubElement(numfmts, S+'numFmt', numFmtId=str(index), formatCode=fmt)
    fonts = ET.SubElement(styles, S+'fonts', count='1'); ET.SubElement(fonts, S+'font')
    fills = ET.SubElement(styles, S+'fills', count='2')
    for pattern in ('none', 'gray125'): ET.SubElement(ET.SubElement(fills, S+'fill'), S+'patternFill', patternType=pattern)
    borders = ET.SubElement(styles, S+'borders', count='1'); ET.SubElement(borders, S+'border')
    base = ET.SubElement(styles, S+'cellStyleXfs', count='1'); ET.SubElement(base, S+'xf', numFmtId='0', fontId='0', fillId='0', borderId='0')
    xfs = ET.SubElement(styles, S+'cellXfs', count=str(len(formats)))
    for index, fmt in enumerate(formats): ET.SubElement(xfs, S+'xf', numFmtId=str(index+163 if index else 0), fontId='0', fillId='0', borderId='0', xfId='0')
    named = ET.SubElement(styles, S+'cellStyles', count='1'); ET.SubElement(named, S+'cellStyle', name='Normal', xfId='0', builtinId='0')
    parts.update({'[Content_Types].xml':types, '_rels/.rels':package_rels, 'xl/workbook.xml':workbook, 'xl/_rels/workbook.xml.rels':rels, 'xl/styles.xml':styles})
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as package:
        for name, root in parts.items(): package.writestr(name, ET.tostring(root, encoding='utf-8', xml_declaration=True))
    result = output.getvalue()
    if len(result) > 1000000: deny('xlsx_table_output_limit')
    # Admit our output through the existing guarded consumer before publication.
    # This parses package/reference/dependency structure only; it never runs LO.
    try: Book(result, checkpoint=checkpoint)
    except RecalculationRefused: deny('xlsx_formula_consumer_unsupported')
    return result


def create_document(spec):
    if not isinstance(spec, dict) or not set(spec) <= {'sheets', 'names'} or 'sheets' not in spec or not isinstance(spec['sheets'], list): deny()
    sheets = []; tables = {}; names = spec.get('names', {})
    if not isinstance(names, dict): deny('xlsx_table_invalid_name')
    if not 1 <= len(spec['sheets']) <= MAX_SHEETS: deny('xlsx_table_limit')
    count = 0
    for sheet in spec['sheets']:
        if not isinstance(sheet, dict) or not set(sheet) <= {'name', 'rows', 'table'} or not {'name', 'rows'} <= set(sheet): deny()
        rows = sheet['rows']
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS: deny('xlsx_table_limit')
        normalized = []
        for row in rows:
            if not isinstance(row, list) or not 1 <= len(row) <= MAX_COLS: deny('xlsx_table_limit')
            count += len(row)
            if count > MAX_CELLS: deny('xlsx_table_limit')
            normalized.append([scalar(cell) for cell in row])
        name = sheet_name(sheet['name']); sheets.append((name, normalized))
        if 'table' in sheet: tables[name] = sheet['table']
    return sheets, tables, names


def render(sheets, checkpoint=lambda: None):
    """Render validated scalar tuples, preserving literal text without apostrophes."""
    if any(item[0] == 'formula' for _, rows in sheets for values in rows for item in values):
        return render_document(sheets, checkpoint)
    if not 1 <= len(sheets) <= MAX_SHEETS: deny('xlsx_table_limit')
    if len({name.casefold() for name, _ in sheets}) != len(sheets): deny('xlsx_table_sheet_name')
    count = 0; formats = ['General']; parts = {}
    ns = S[1:-1]; ct = '{http://schemas.openxmlformats.org/package/2006/content-types}'
    types = ET.Element(ct+'Types')
    ET.SubElement(types, ct+'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(types, ct+'Default', Extension='xml', ContentType='application/xml')
    for name, suffix in [('workbook.xml', 'sheet.main'), ('styles.xml', 'styles')]:
        ET.SubElement(types, ct+'Override', PartName='/xl/'+name, ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.'+suffix+'+xml')
    package_rels = ET.Element(P+'Relationships')
    ET.SubElement(package_rels, P+'Relationship', Id='rId1', Type=R[1:-1]+'/officeDocument', Target='xl/workbook.xml')
    workbook = ET.Element(S+'workbook'); native_sheets = ET.SubElement(workbook, S+'sheets')
    rels = ET.Element(P+'Relationships')
    for index, (name, rows) in enumerate(sheets, 1):
        checkpoint(); sheet_name(name)
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS: deny('xlsx_table_limit')
        width = len(rows[0])
        if not 1 <= width <= MAX_COLS or any(len(row) != width for row in rows): deny('xlsx_table_rectangular_rows')
        count += len(rows)*width
        if count > MAX_CELLS: deny('xlsx_table_limit')
        ET.SubElement(native_sheets, S+'sheet', name=name, sheetId=str(index), attrib={R+'id':'rId'+str(index)})
        ET.SubElement(rels, P+'Relationship', Id='rId'+str(index), Type=R[1:-1]+'/worksheet', Target='worksheets/sheet'+str(index)+'.xml')
        ET.SubElement(types, ct+'Override', PartName='/xl/worksheets/sheet'+str(index)+'.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
        root = ET.Element(S+'worksheet'); data = ET.SubElement(root, S+'sheetData')
        for row_index, values in enumerate(rows, 1):
            checkpoint(); row = ET.SubElement(data, S+'row', r=str(row_index))
            for column, (kind, value, fmt) in enumerate(values, 1):
                cell = ET.SubElement(row, S+'c', r=colname(column)+str(row_index))
                if kind == 'blank': continue
                if kind == 'string':
                    cell.set('t', 'inlineStr'); inline = ET.SubElement(cell, S+'is')
                    ET.SubElement(inline, S+'t', attrib={XML_SPACE:'preserve'}).text = text(value)
                else:
                    cell.set('t', 'b' if kind == 'boolean' else 'n')
                    if fmt not in formats: formats.append(fmt)
                    if len(formats) > 32: deny('xlsx_table_style_limit')
                    if fmt != 'General': cell.set('s', str(formats.index(fmt)))
                    ET.SubElement(cell, S+'v').text = value
        parts['xl/worksheets/sheet'+str(index)+'.xml'] = root
    ET.SubElement(rels, P+'Relationship', Id='styles', Type=R[1:-1]+'/styles', Target='styles.xml')
    styles = ET.Element(S+'styleSheet'); numfmts = ET.SubElement(styles, S+'numFmts', count=str(len(formats)-1))
    for index, fmt in enumerate(formats[1:], 164): ET.SubElement(numfmts, S+'numFmt', numFmtId=str(index), formatCode=fmt)
    fonts = ET.SubElement(styles, S+'fonts', count='1'); ET.SubElement(fonts, S+'font')
    fills = ET.SubElement(styles, S+'fills', count='2')
    for pattern in ('none', 'gray125'): ET.SubElement(ET.SubElement(fills, S+'fill'), S+'patternFill', patternType=pattern)
    borders = ET.SubElement(styles, S+'borders', count='1'); ET.SubElement(borders, S+'border')
    base = ET.SubElement(styles, S+'cellStyleXfs', count='1'); ET.SubElement(base, S+'xf', numFmtId='0', fontId='0', fillId='0', borderId='0')
    xfs = ET.SubElement(styles, S+'cellXfs', count=str(len(formats)))
    for index, fmt in enumerate(formats):
        ET.SubElement(xfs, S+'xf', numFmtId=str(index+163 if index else 0), fontId='0', fillId='0', borderId='0', xfId='0')
    named = ET.SubElement(styles, S+'cellStyles', count='1'); ET.SubElement(named, S+'cellStyle', name='Normal', xfId='0', builtinId='0')
    parts.update({'[Content_Types].xml':types, '_rels/.rels':package_rels, 'xl/workbook.xml':workbook, 'xl/_rels/workbook.xml.rels':rels, 'xl/styles.xml':styles})
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as package:
        for name, root in parts.items():
            package.writestr(name, ET.tostring(root, encoding='utf-8', xml_declaration=True))
    result = output.getvalue()
    if len(result) > 1000000: deny('xlsx_table_output_limit')
    return result


def create_spec(spec):
    if not isinstance(spec, dict) or set(spec) != {'sheets'} or not isinstance(spec['sheets'], list): deny()
    sheets = []
    if not 1 <= len(spec['sheets']) <= MAX_SHEETS: deny('xlsx_table_limit')
    count = 0
    for sheet in spec['sheets']:
        if not isinstance(sheet, dict) or set(sheet) != {'name', 'rows'}: deny()
        rows = sheet['rows']
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS: deny('xlsx_table_limit')
        normalized = []
        for row in rows:
            if not isinstance(row, list) or not 1 <= len(row) <= MAX_COLS: deny('xlsx_table_limit')
            count += len(row)
            if count > MAX_CELLS: deny('xlsx_table_limit')
            normalized.append([scalar(cell) for cell in row])
        sheets.append((sheet_name(sheet['name']), normalized))
    return sheets


def string_text(item):
    # Same visible-base-text semantics as the installed read_extract consumer:
    # rich runs concatenate; phonetic annotations are metadata, not key text.
    return ''.join((child.text or '') if child.tag == S+'t' else child.findtext(S+'t') or ''
                   for child in item if child.tag in {S+'t', S+'r'})


def source_table(book, name):
    if name not in book.sheets: deny('xlsx_join_sheet_missing')
    root = book.roots[book.sheets[name]]
    if root.find(S+'mergeCells') is not None or root.find(S+'tableParts') is not None: deny('xlsx_join_structure_unsupported')
    native_rows = root.findall(S+'sheetData/'+S+'row')
    if not 1 <= len(native_rows) <= MAX_ROWS: deny('xlsx_table_limit')
    shared = []
    if 'xl/sharedStrings.xml' in book.roots:
        shared = [string_text(item) for item in book.roots['xl/sharedStrings.xml'].findall(S+'si')]
    styles = book.roots.get('xl/styles.xml'); formats = {0:'General', 1:'0', 2:'0.00', 14:'mm-dd-yy'}
    xfs = []
    if styles is not None:
        for fmt in styles.findall(S+'numFmts/'+S+'numFmt'):
            ident = int(fmt.get('numFmtId', '-1'))
            if ident < 164 or ident in formats: deny('xlsx_join_styles_unsupported')
            formats[ident] = fmt.get('formatCode')
        xfs = styles.findall(S+'cellXfs/'+S+'xf')
    def value(cell):
        if cell.find(S+'f') is not None: deny('xlsx_join_formula_unsupported')
        kind = cell.get('t', 'n'); values = cell.findall(S+'v'); inline = cell.findall(S+'is')
        if len(values) > 1 or len(inline) > 1: deny('xlsx_join_cell_unsupported')
        raw = values[0].text if values else None
        if kind == 'inlineStr':
            if values or len(inline) != 1: deny('xlsx_join_cell_unsupported')
            return scalar(string_text(inline[0]))
        if kind == 's':
            if inline or raw is None or not raw.isascii() or not raw.isdigit() or not 0 <= int(raw) < len(shared): deny('xlsx_join_cell_unsupported')
            return scalar(shared[int(raw)])
        if inline: deny('xlsx_join_cell_unsupported')
        if raw is None: return scalar(None)
        if kind == 'str': return scalar(raw)
        if kind == 'b' and raw in ('0', '1'): return scalar(raw == '1')
        if kind == 'd': return scalar({'type':'date', 'value':raw})
        if kind != 'n': deny('xlsx_join_cell_unsupported')
        result = number(format(Decimal(raw), 'f'))
        style = cell.get('s', '0')
        if not style.isascii() or not style.isdigit() or (xfs and int(style) >= len(xfs)) or (not xfs and style != '0'): deny('xlsx_join_styles_unsupported')
        fmt = formats.get(int(xfs[int(style)].get('numFmtId', '0'))) if xfs else 'General'
        if fmt in ('dd.mm.yyyy', 'mm-dd-yy', 'yyyy-mm-dd'):
            days = Decimal(raw)
            props = book.roots['xl/workbook.xml'].find(S+'workbookPr')
            if props is not None and props.get('date1904', '0') not in ('0', 'false'): deny('xlsx_join_date_epoch_unsupported')
            if days != days.to_integral_value(): deny('xlsx_join_date_unsupported')
            try: actual = date(1899, 12, 30)+timedelta(days=int(days))
            except (OverflowError, ValueError): deny('xlsx_join_date_unsupported')
            return scalar({'type':'date', 'value':actual.isoformat()})
        if fmt == 'General': return result
        if fmt == '0' or (isinstance(fmt, str) and re.fullmatch(r'0\.0{1,12}', fmt)):
            return (result[0], result[1], fmt)
        deny('xlsx_join_styles_unsupported')
    rows = []; width = 0
    for index, row in enumerate(native_rows, 1):
        if row.get('r') != str(index): deny('xlsx_join_sparse_rows_unsupported')
        cells = list(row)
        if index == 1: width = len(cells)
        if not 1 <= width <= MAX_COLS: deny('xlsx_table_limit')
        decoded = [scalar(None) for _ in range(width)]; seen = set()
        for cell in cells:
            if cell.tag != S+'c': deny('xlsx_join_cell_unsupported')
            match = re.fullmatch(r'([A-Z]{1,3})'+str(index), cell.get('r', ''))
            if not match: deny('xlsx_join_cell_unsupported')
            col = 0
            for char in match[1]: col = col*26+ord(char)-64
            if not 1 <= col <= width or col in seen: deny('xlsx_join_cell_unsupported')
            seen.add(col); decoded[col-1] = value(cell)
        rows.append(decoded)
    return rows


def render_join(data, spec, checkpoint=lambda: None):
    if not isinstance(spec, dict) or set(spec) != {'source', 'left_sheet', 'right_sheet', 'key', 'sheet'}: deny()
    if spec['left_sheet'] == spec['right_sheet']: deny('xlsx_join_distinct_sheets_required')
    for key in ('left_sheet', 'right_sheet', 'sheet'): sheet_name(spec[key])
    key = text(spec['key'])
    if not key: deny()
    book = Book(data, checkpoint=checkpoint)
    if (spec['left_sheet'] in book.sheets and spec['right_sheet'] in book.sheets
            and book.sheets[spec['left_sheet']] == book.sheets[spec['right_sheet']]):
        deny('xlsx_join_distinct_sheets_required')
    left = source_table(book, spec['left_sheet']); right = source_table(book, spec['right_sheet'])
    def headers(rows):
        values = rows[0]
        if any(k != 'string' or not v for k, v, _ in values): deny('xlsx_join_headers')
        names = [v for _, v, _ in values]
        if len(set(names)) != len(names) or key not in names: deny('xlsx_join_headers')
        return names
    lh = headers(left); rh = headers(right); li = lh.index(key); ri = rh.index(key)
    extra = [index for index in range(len(rh)) if index != ri]
    if set(lh) & {rh[index] for index in extra}: deny('xlsx_join_column_conflict')
    def index_rows(rows, column):
        found = {}
        for row in rows[1:]:
            kind, value, _ = row[column]
            if kind != 'string' or not value: deny('xlsx_join_text_key_required')
            if value in found: deny('xlsx_join_duplicate_key')
            found[value] = row
        return found
    index_rows(left, li); lookup = index_rows(right, ri)
    rows = [left[0]+[right[0][i] for i in extra]]; matched = 0
    for row in left[1:]:
        checkpoint(); other = lookup.get(row[li][1]); matched += other is not None
        rows.append(row+[other[i] if other is not None else scalar(None) for i in extra])
    return render([(spec['sheet'], rows)], checkpoint), {'join':'exact_text_left', 'rows':len(rows)-1, 'matched_rows':matched, 'unmatched_rows':len(rows)-1-matched, 'source_formatting_preserved':False}


def create_table(cap, fd, leaf, path, content, *, join=False):
    check(cap)
    try:
        spec = parse(content); verify = None; facts = {}
        if join:
            if not isinstance(spec, dict) or set(spec) != {'source', 'left_sheet', 'right_sheet', 'key', 'sheet'}: deny()
            raw = spec['source']
            if not isinstance(raw, str) or '\x00' in raw: deny()
            root = cap.home/'workspace'; source = Path(raw)
            if not source.is_absolute(): source = root/source
            relative = source.relative_to(root)
            if not relative.parts or any(p in ('.', '..') or p.startswith('.') for p in relative.parts) or source.suffix.lower() != '.xlsx' or relative.as_posix() == path: deny('xlsx_join_invalid_source')
            data, _, identity = workspace_document(str(source), with_identity=True)
            rendered, facts = render_join(data, spec, checkpoint=lambda: check(cap))
            def verify():
                check(cap); current, _, version = workspace_document(str(source), with_identity=True)
                if current != data or version != identity: raise ScopeDenied()
            facts['source'] = relative.as_posix()
        else:
            sheets, tables, names = create_document(spec)
            rendered = render_document(sheets, checkpoint=lambda: check(cap), tables=tables, names=names)
            facts = {'native_tables':sorted(table['name'] for table in tables.values()) if tables else [],
                     'defined_names':sorted(names) if isinstance(names, dict) else []}
        result = json.loads(_create_bytes(cap, fd, leaf, path, rendered, output_format='xlsx_join' if join else 'xlsx_create', verify_source=verify))
        if result.get('success'): result.update(facts, formulas_created=any(kind == 'formula' for _, rows in sheets for values in rows for kind, _, _ in values) if not join else False)
        return json.dumps(result)
    except TableRefused as error:
        return json.dumps({'success':False, 'error':str(error), 'effect_disposition':'none'})
    except RecalculationRefused:
        return json.dumps({'success':False, 'error':'xlsx_join_source_unsupported', 'effect_disposition':'none'})
    except (ValueError, TypeError, KeyError, RecursionError, InvalidOperation, OverflowError):
        return json.dumps({'success':False, 'error':'xlsx_table_invalid_spec', 'effect_disposition':'none'})
