"""Workbook facts from real XLSX bytes, separate from model recall compliance."""
import io
import json
from types import SimpleNamespace
import zipfile

import pytest

from tools import read_extract

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'


def workbook_bytes():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('xl/workbook.xml', f'''<workbook xmlns="{S}" xmlns:r="{R}">
          <sheets><sheet name="Orders" sheetId="1" r:id="rId1"/>
          <sheet name="Hidden notes" sheetId="2" state="veryHidden" r:id="rId2"/></sheets>
          <definedNames><definedName name="OrderTotal">Orders!$B$1</definedName>
          <definedName name="LocalTotal" localSheetId="0">Orders!$B$1</definedName></definedNames>
        </workbook>''')
        archive.writestr('xl/_rels/workbook.xml.rels', f'''<Relationships xmlns="{P}">
          <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
          <Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>''')
        archive.writestr('xl/worksheets/sheet1.xml', f'''<worksheet xmlns="{S}"><sheetData>
          <row r="1"><c r="A1" t="inlineStr"><is><t>Item</t></is></c>
          <c r="B1"><f>1+2</f><v/></c></row></sheetData></worksheet>''')
        archive.writestr('xl/worksheets/sheet2.xml', f'''<worksheet xmlns="{S}"><sheetData>
          <row r="1"><c r="A1" t="inlineStr"><is><t>PRIVATE HIDDEN CELL</t></is></c></row>
          </sheetData></worksheet>''')
    return payload.getvalue()


def inventory_entries(text):
    return [json.loads(line) for line in text.splitlines() if line.startswith('{')]


def test_scoped_inventory_records_actual_declarations_and_retains_blank_cache():
    text = read_extract.extract_scoped_document_bytes(workbook_bytes(), 'xlsx')
    assert inventory_entries(text) == [
        {'name': 'Orders', 'state': 'visible'},
        {'name': 'Hidden notes', 'state': 'veryHidden'},
        {'name': 'OrderTotal', 'localSheetId': None},
        {'name': 'LocalTotal', 'localSheetId': '0'},
    ]
    assert 'PRIVATE HIDDEN CELL' not in text
    assert 'Item\t\n' in text  # A formula without a cache is not invented as value 3.
    assert text.extraction_metadata['recalculated'] is False
    assert 'formulas_charts_comments_layout_not_inspected' in text.extraction_metadata['coverage']


def test_generic_projection_and_input_limits_remain_in_effect(tmp_path):
    path = tmp_path / 'book.xlsx'
    path.write_bytes(workbook_bytes())
    text = read_extract.extract_document_text(str(path))
    assert text == '# ── Sheet: Orders ──\nItem\t\n'
    assert not hasattr(text, 'extraction_metadata')
    with pytest.raises(read_extract.ScopedExtractionError, match='input_limit'):
        read_extract.extract_scoped_document_bytes(b'x' * 1000001, 'xlsx')
    with pytest.raises(read_extract.ExtractionError, match='aggregate'):
        read_extract._extract_xlsx(io.BytesIO(workbook_bytes()), max_xml_bytes=1000000,
                                  max_total_xml_bytes=100)


def test_optional_inventory_does_not_reject_an_existing_large_preview():
    payload = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(workbook_bytes())) as source, zipfile.ZipFile(payload, 'w') as out:
        for item in source.infolist():
            if item.filename != 'xl/worksheets/sheet1.xml':
                out.writestr(item, source.read(item))
        out.writestr('xl/sharedStrings.xml', f'<sst xmlns="{S}"><si><t>{"v" * 1998}</t></si></sst>')
        rows = ''.join(f'<row r="{n}"><c r="A{n}" t="s"><v>0</v></c></row>' for n in range(1, 501))
        out.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{S}"><sheetData>{rows}</sheetData></worksheet>')
    data = payload.getvalue()
    expected = read_extract._extract_xlsx(io.BytesIO(data), max_xml_bytes=1000000,
                                         max_total_xml_bytes=1000000)
    assert len(expected.encode()) < 1000000
    actual = read_extract.extract_scoped_document_bytes(data, 'xlsx')
    assert actual == expected
    assert actual.extraction_metadata['workbook_inventory'].startswith('omitted_size_limit;')


def test_scoped_consumer_paginates_inventory_and_keeps_coverage(tmp_path, monkeypatch):
    # Admission is outside this extraction change; retain real descriptor and pagination code.
    from hermes_cli import friday_user_scope as scope
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    work = home / 'workspace'
    work.mkdir(mode=0o700)
    path = work / 'book.xlsx'
    path.write_bytes(workbook_bytes())
    path.chmod(0o600)
    before = path.read_bytes(), path.stat().st_mtime_ns
    cap = SimpleNamespace(home=home, directory_identity=(home.stat().st_dev, home.stat().st_ino))
    cap.check = lambda: cap
    monkeypatch.setattr(scope, 'guard_tool', lambda *_a, **_k: None)
    token = scope._CURRENT.set(cap)
    try:
        first = json.loads(scope.scoped_file('read_file', {'path': 'book.xlsx', 'limit': 2}))
        assert first['success'] is True and first['partial'] is True
        assert first['extraction']['recalculated'] is False
        pages = [first['content']]
        result = first
        while result['partial']:
            result = json.loads(scope.scoped_file('read_file', {
                'path': 'book.xlsx', 'limit': 2, 'offset': result['next_offset'],
                'char_offset': result['next_char_offset']}))
            assert result['coverage'] == first['coverage']
            pages.append(result['content'])
        joined = '\n'.join(pages)
        assert '"name": "OrderTotal"' in joined
        assert '"name": "Hidden notes"' in joined
        assert 'PRIVATE HIDDEN CELL' not in joined
        assert before == (path.read_bytes(), path.stat().st_mtime_ns)
        with pytest.raises(scope.ScopeDenied):
            scope.scoped_file('read_file', {'path': '../book.xlsx'})
    finally:
        scope._CURRENT.reset(token)


def test_scoped_preview_limits_and_hidden_cell_policy_on_every_page(tmp_path, monkeypatch):
    """Coverage must describe retained hidden cells and omitted rows/columns."""
    payload = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(workbook_bytes())) as original, zipfile.ZipFile(payload, 'w') as archive:
        for item in original.infolist():
            if item.filename != 'xl/worksheets/sheet1.xml':
                archive.writestr(item, original.read(item))
        rows = [f'<row r="{n}"><c r="A{n}" t="inlineStr"><is><t>v</t></is></c></row>'
                for n in range(1, 5002)]
        rows[0] = '<row r="1" hidden="1"><c r="A1" t="inlineStr"><is><t>HIDDEN_ROW_VALUE</t></is></c></row>'
        rows[1] = '<row r="2"><c r="B2" t="inlineStr"><is><t>HIDDEN_COLUMN_VALUE</t></is></c></row>'
        rows[2] = '<row r="3"><c r="IW3" t="inlineStr"><is><t>OMITTED_COLUMN</t></is></c></row>'
        rows[5000] = '<row r="5001"><c r="A5001" t="inlineStr"><is><t>OMITTED_ROW</t></is></c></row>'
        archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{S}"><cols><col min="2" max="2" hidden="1"/></cols><sheetData>{"".join(rows)}</sheetData></worksheet>')
    data = payload.getvalue()
    text = read_extract.extract_scoped_document_bytes(data, 'xlsx')
    assert 'HIDDEN_ROW_VALUE' in text and 'HIDDEN_COLUMN_VALUE' in text
    assert 'OMITTED_COLUMN' not in text and 'OMITTED_ROW' not in text
    expected = {'sheets': 'visible_only', 'max_rows_per_sheet': 5000,
                'max_columns': 256, 'hidden_rows_and_columns': 'not_filtered',
                'formula_values': 'saved_cache_only'}
    assert text.extraction_metadata.get('cell_value_preview') == expected
    assert 'visible_sheet_cell_value_preview' in text.extraction_metadata['coverage']
    from hermes_cli import friday_user_scope as scope
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    work = home / 'workspace'
    work.mkdir(mode=0o700)
    path = work / 'book.xlsx'
    path.write_bytes(data)
    path.chmod(0o600)
    before = path.read_bytes(), path.stat().st_mtime_ns
    cap = SimpleNamespace(home=home, directory_identity=(home.stat().st_dev, home.stat().st_ino))
    cap.check = lambda: cap
    monkeypatch.setattr(scope, 'guard_tool', lambda *_a, **_k: None)
    token = scope._CURRENT.set(cap)
    try:
        offsets = [1, len(text.splitlines()) // 2, len(text.splitlines())]
        for offset in offsets:
            result = json.loads(scope.scoped_file('read_file', {'path': 'book.xlsx', 'limit': 1, 'offset': offset}))
            assert result['success'] is True
            assert result['extraction']['cell_value_preview'] == expected
            assert result['coverage'] == text.extraction_metadata['coverage']
        assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    finally:
        scope._CURRENT.reset(token)
