"""Portable offline formula-reader controls using synthetic XLSX ZIP fixtures.

Run against the patched Hermes source root on PYTHONPATH. These tests do not
exercise admission, installed runtime, models, Telegram, or user acceptance.
No real workbooks or private source paths are needed.
"""
import io
import json
import socket
import unittest
from unittest import mock
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from tools import read_extract as rex

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def worksheet(rows):
    return f'<worksheet xmlns="{NS}"><sheetData>{rows}</sheetData></worksheet>'

def package(sheets, *, shared=None, extra=None, compression=zipfile.ZIP_DEFLATED, workbook_extra=''):
    # Tuple: name, state, part-or-URL, XML-or-None, target-mode-or-None.
    entries = []
    rels = []
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=compression) as archive:
        for index, (name, state, part, xml, mode) in enumerate(sheets, 1):
            entries.append(f'<sheet name={quoteattr(name)} state={quoteattr(state)} sheetId="{index}" r:id="r{index}"/>')
            rels.append(f'<Relationship Id="r{index}" Target={quoteattr(part)} Type="x"'
                        + (f' TargetMode={quoteattr(mode)}' if mode else '') + '/>')
            if xml is not None:
                archive.writestr('xl/' + part, xml)
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>{"".join(entries)}</sheets>{workbook_extra}</workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{PKG}">{"".join(rels)}</Relationships>')
        if shared is not None:
            archive.writestr('xl/sharedStrings.xml', shared)
        for name, value in (extra or {}).items():
            archive.writestr(name, value)
    return output.getvalue()

def book(rows, **kw):
    return package([('Data', 'visible', 'worksheets/sheet1.xml', worksheet(rows), None)], **kw)

def records(text):
    return [json.loads(line) for line in text.splitlines() if line.startswith('{"sheet":')]

def metadata(text):
    return text.extraction_metadata['formula_source_preview']

def scoped(data):
    return rex.extract_scoped_document_bytes(data, 'xlsx')


class FormulaControls(unittest.TestCase):
    def test_missing_blank_zero_cache_states_and_types(self):
            data = book('<row r="1"><c r="A1" t="b"><f>FALSE()</f></c>'
                        '<c r="B1" t="e"><f>1/0</f><v/></c>'
                        '<c r="C1"><f>0</f><v>0</v></c>'
                        '<c r="D1" t="b"><f>FALSE()</f><v>0</v></c>'
                        '<c r="E1" t="str"><f>"x"</f><v>x</v></c></row>')
            result = scoped(data)
            found = records(result)
            self.assertEqual([r['saved_cache']['state'] for r in found], ['missing','blank','present','present','present'])
            self.assertEqual([r['saved_cache']['raw_value'] for r in found], [None,'','0','0','x'])
            self.assertEqual([r['saved_cache']['cell_type'] for r in found], ['b','e','n','b','str'])
            self.assertIn('\n\t\t0\tFALSE\tx\n', result)
            self.assertNotIn('#ERROR', result)
            self.assertIn('FALSE\t#ERROR\t0\tFALSE\tx', rex._extract_xlsx(io.BytesIO(data)))

    def test_shared_and_array_are_exact_declarations_without_reconstruction(self):
            data = book('<row><c r="A1"><f t="shared" si="7" ref="A1:A2">B1+1</f><v>2</v></c>'
                        '<c r="B1"><f t="array" ref="B1:B2" aca="1">SUM(C1:C2)</f></c></row>'
                        '<row><c r="A2"><f t="shared" si="7"/><v>3</v></c></row>')
            found = records(scoped(data))
            self.assertEqual(found[0]['formula_attributes'], {'t':'shared','si':'7','ref':'A1:A2'})
            self.assertEqual(found[1]['formula_attributes'], {'t':'array','ref':'B1:B2','aca':'1'})
            self.assertEqual(found[2]['formula'], '')
            self.assertEqual(found[2]['formula_attributes'], {'t':'shared','si':'7'})
            self.assertNotIn('B2+1', json.dumps(found))

    def test_hidden_external_missing_and_malformed_sheet_coverage(self):
            xml = worksheet('<row><c r="A1"><f>VISIBLE()</f><v>1</v></c></row>')
            data = package([('Visible','visible','worksheets/one.xml',xml,None),
                            ('Hidden','hidden','worksheets/two.xml',xml.replace('VISIBLE','HIDDEN'),None),
                            ('VeryHidden','veryHidden','worksheets/three.xml',xml,None),
                            ('Missing','visible','worksheets/absent.xml',None,None),
                            ('External','visible','worksheets/external.xml',xml,'External'),
                            ('Malformed','visible','worksheets/bad.xml','<bad',None)])
            result = scoped(data)
            self.assertEqual(len(records(result)), 1)
            self.assertEqual(records(result)[0]['sheet'], 'Visible')
            self.assertEqual(metadata(result)['sheets'], dict(parsed=1, skipped_hidden=2,
                             skipped_missing_or_external=2, skipped_malformed=1))
            self.assertIn('"name": "VeryHidden"', result)
            self.assertNotIn('HIDDEN()', result)

    def test_row_column_limits_and_hidden_rows_columns_not_filtered(self):
            rows = '<row r="1" hidden="1"><c r="IV1"><f>IN_PREVIEW()</f></c><c r="IW1"><f>OUT_COLUMN()</f></c></row>'
            rows += ''.join(f'<row r="{i}"/>' for i in range(2, 5001))
            rows += '<row r="5001"><c r="A5001"><f>OUT_ROW()</f></c></row>'
            result = scoped(book(rows))
            self.assertEqual([r['cell'] for r in records(result)], ['IV1'])
            self.assertEqual(metadata(result)['rows_omitted_by_preview_limit'], 1)
            self.assertEqual(metadata(result)['cells_omitted_by_column_limit'], 1)
            self.assertNotIn('OUT_COLUMN', result)
            self.assertNotIn('OUT_ROW', result)

    def test_missing_cell_reference_not_invented(self):
            result = scoped(book('<row><c><f>1+1</f><v>2</v></c></row>'))
            self.assertIsNone(records(result)[0]['cell'])

    def test_long_formula_and_cache_are_explicitly_truncated(self):
            source = 'X' * 4500
            cache = 'Y' * 4500
            result = scoped(book(f'<row><c r="A1" t="str"><f>{source}</f><v>{cache}</v></c></row>'))
            record = records(result)[0]
            self.assertEqual(len(record['formula']), 4096)
            self.assertEqual(len(record['saved_cache']['raw_value']), 4096)
            self.assertEqual(record['truncated_fields'], ['formula', 'saved_cache.raw_value'])
            self.assertTrue(metadata(result)['truncated'])
            self.assertEqual(metadata(result)['records_with_truncated_fields'], 1)

    def test_formula_count_limit_and_metadata(self):
            result = scoped(book(''.join(f'<row><c r="A{i}"><f>{i}+1</f></c></row>' for i in range(1, 601))))
            self.assertEqual(len(records(result)), 512)
            self.assertEqual(metadata(result)['observed_formula_cells'], 600)
            self.assertEqual(metadata(result)['omitted_records'], 88)
            self.assertTrue(metadata(result)['truncated'])

    def test_formula_byte_limit_and_oversize_attributes(self):
            result = scoped(book(''.join(f'<row><c r="A{i}"><f>{"X"*500}</f></c></row>' for i in range(1, 601))))
            preview = result[result.index('\n# XLSX formula source preview'):]
            self.assertLessEqual(len(preview.encode()), 128000)
            self.assertGreater(metadata(result)['omitted_records'], 0)
            self.assertEqual(metadata(result)['observed_formula_cells'], 600)
            self.assertEqual(len(records(result)), metadata(result)['included_records'])
            oversized = scoped(book(f'<row><c r="A1"><f t="{"z"*40000}">1</f></c></row>'))
            self.assertEqual(records(oversized), [])
            self.assertEqual(metadata(oversized)['omitted_records'], 1)
            self.assertTrue(metadata(oversized)['truncated'])

    def test_output_budget_retains_readable_preview_and_truthful_omission(self):
            found_omission = False
            for n in (998600, 998800, 999000):
                data = book(f'<row><c r="A1" t="inlineStr"><is><t>{"x"*n}</t></is></c>'
                            '<c r="B1"><f>1+1</f></c></row>')
                result = scoped(data)
                self.assertLessEqual(len(result.encode()), 1000000)
                if metadata(result)['omitted_records']:
                    self.assertTrue(metadata(result)['truncated'])
                    self.assertIn('x'*100, result)
                    found_omission = True
                    break
            self.assertTrue(found_omission)

    def test_inventory_omission_remains_truthful_and_record_identity_not_truncated(self):
            data = package([('N'*300000,'visible','worksheets/one.xml',
                            worksheet('<row><c r="A1" t="inlineStr"><is><t>'+'x'*500000+
                                      '</t></is></c><c r="B1"><f>1+1</f></c></row>'),None)])
            result = scoped(data)
            self.assertLessEqual(len(result.encode()),1000000)
            self.assertIn('omitted_size_limit',result.extraction_metadata['workbook_inventory'])
            self.assertNotIn('# XLSX workbook inventory',result)
            self.assertEqual(metadata(result)['observed_formula_cells'],1)
            self.assertEqual(metadata(result)['omitted_records'],1)
            self.assertTrue(metadata(result)['truncated'])
            self.assertEqual(records(result),[])

    def test_unicode_json_expansion_respects_record_and_output_limits(self):
            result = scoped(book('<row><c r="A1"><f>'+'🙂'*4500+'</f></c></row>'))
            self.assertEqual(records(result),[])
            self.assertEqual(metadata(result)['omitted_records'],1)
            self.assertTrue(metadata(result)['truncated'])
            self.assertLessEqual(len(result.encode()),1000000)

    def test_formula_is_inert_json_even_for_external_references_and_controls(self):
            source = 'WEBSERVICE("https://example.invalid/formula-probe")\n+\t[other.xlsx]Sheet1!A1'
            data = book(f'<row><c r="A1"><f>{escape(source)}</f></c></row>',
                        extra={'_rels/.rels':'<Relationships/>','xl/externalLinks/externalLink1.xml':'<never-read/>'})
            with mock.patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')), \
                 mock.patch.object(rex.subprocess, 'run', side_effect=AssertionError('process forbidden')), \
                 mock.patch.object(rex.subprocess, 'Popen', side_effect=AssertionError('process forbidden')), \
                 mock.patch.object(rex.importlib, 'import_module', side_effect=AssertionError('dynamic import forbidden')):
                result = scoped(data)
            self.assertEqual(records(result)[0]['formula'], source)
            formula_line = next(line for line in result.splitlines() if line.startswith('{"sheet":'))
            self.assertIn('\\n+\\t', formula_line)
            self.assertFalse(metadata(result)['evaluated'])

    def test_external_xml_entity_not_resolved(self):
            xml = f'<!DOCTYPE worksheet [<!ENTITY x SYSTEM "file:///never-readable">]><worksheet xmlns="{NS}"><sheetData><row><c><f>&x;</f></c></row></sheetData></worksheet>'
            with self.assertRaises(rex.ScopedExtractionError):
                scoped(package([('Data','visible','worksheets/one.xml',xml,None)]))

    def test_input_per_part_and_aggregate_limits(self):
            for raw in (b'x'*1000001, b'not-a-zip', book('x'*1000001),
                        package([('One','visible','worksheets/one.xml',worksheet(' '*600000),None),
                                 ('Two','visible','worksheets/two.xml',worksheet(' '*600000),None)])):
                with self.subTest(bytes=len(raw)), self.assertRaises(rex.ScopedExtractionError):
                    scoped(raw)

    def test_duplicate_sheet_references_charged_and_unsupported_compression_refused(self):
            big = worksheet(' '*400000)
            data = package([('One','visible','worksheets/one.xml',big,None),
                            ('Two','visible','worksheets/one.xml',None,None),
                            ('Three','visible','worksheets/one.xml',None,None)])
            with self.assertRaises(rex.ScopedExtractionError):
                scoped(data)
            with self.assertRaises(rex.ScopedExtractionError):
                scoped(book('<row><c r="A1"><f>1</f></c></row>', compression=zipfile.ZIP_BZIP2))

    def test_generic_does_not_collect_formulas_and_keeps_saved_projection(self):
            shared = f'<sst xmlns="{NS}"><si><t>Name</t></si><si><r><t>Alice</t></r><rPh><t>PHONETIC</t></rPh></si></sst>'
            data = book('<row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
                        '<c r="C1"><f>3+4</f><v>7</v></c></row>', shared=shared)
            with mock.patch.object(rex, '_XlsxFormulaPreview', side_effect=AssertionError('generic collector forbidden')):
                generic = rex._extract_xlsx(io.BytesIO(data))
            self.assertIn('Name\tAlice\t7', generic)
            self.assertNotIn('PHONETIC', generic)
            self.assertNotIn('3+4', generic)
            self.assertNotIn('formula_source_preview', generic)

    def test_formula_entities_whitespace_cache_and_empty_declaration(self):
            source = 'IF(A1>0,B1<2,"a&b")'
            raw = book('<row><c r="A1" t="str"><f>' + escape(source) + '</f><v> </v></c>'
                       '<c r="B1"><f t="shared" si="4"/></c><c r="C1" t="str"><v>not-a-formula</v></c></row>')
            found = records(scoped(raw))
            self.assertEqual(found[0]['formula'], source)
            self.assertEqual(found[0]['saved_cache'], {'state': 'present', 'cell_type': 'str', 'raw_value': ' '})
            self.assertEqual(found[1]['formula'], '')
            self.assertEqual(found[1]['saved_cache']['state'], 'missing')
            self.assertEqual(len(found), 2)

    def test_tiny_budget_and_oversize_record_metadata_are_consistent(self):
            collector = rex._XlsxFormulaPreview()
            root = ET.fromstring(worksheet('<row><c r="A1"><f t="' + 'x' * 40000 + '">1+1</f></c>'
                                           '<c r="B1"><f>2+2</f></c></row>').encode())
            cells = list(root.iter('{%s}c' % NS))
            collector.add('Data', cells[0], '{%s}' % NS)
            collector.add('Data', cells[1], '{%s}' % NS)
            text, meta = collector.render(128000)
            self.assertEqual([json.loads(line)['cell'] for line in text.splitlines() if line.startswith('{"sheet":')], ['B1'])
            self.assertEqual((meta['observed_formula_cells'], meta['included_records'], meta['omitted_records']), (2, 1, 1))
            self.assertTrue(meta['truncated'])
            tiny = rex._XlsxFormulaPreview()
            tiny.add('Data', cells[1], '{%s}' % NS)
            omitted, tiny_meta = tiny.render(0)
            self.assertEqual(omitted, '')
            self.assertEqual(tiny_meta['location'], 'omitted_size_limit')
            self.assertEqual((tiny_meta['included_records'], tiny_meta['omitted_records']), (0, 1))
            self.assertTrue(tiny_meta['truncated'])

    def test_no_formula_plane_or_recalculation_for_plain_cells(self):
            result = scoped(book('<row><c r="A1"><v>0</v></c><c r="B1" t="b"><v>0</v></c></row>'))
            self.assertEqual(records(result), [])
            self.assertEqual(metadata(result)['observed_formula_cells'], 0)
            self.assertFalse(metadata(result)['truncated'])
            self.assertFalse(result.extraction_metadata['recalculated'])
            self.assertNotIn('# XLSX formula source preview', rex._extract_xlsx(__import__('io').BytesIO(book('<row><c r="A1"><f>1+1</f></c></row>'))))

    def test_synthetic_case_preserves_formula_spelling_coordinates_and_blank_cache(self):
        data = package([
            ('Inputs', 'visible', 'worksheets/one.xml', worksheet(
                '<row><c r="A1"><f>2*3</f><v/></c></row>'), None),
            ('Totals', 'visible', 'worksheets/two.xml', worksheet(
                '<row><c r="B2"><f>SUM(Inputs!A1:A1)</f><v/></c></row>'), None),
        ])
        result = scoped(data)
        self.assertEqual([(r['sheet'], r['cell'], r['formula']) for r in records(result)],
                         [('Inputs', 'A1', '2*3'), ('Totals', 'B2', 'SUM(Inputs!A1:A1)')])
        self.assertTrue(all(r['saved_cache'] == {
            'state': 'blank', 'cell_type': 'n', 'raw_value': ''} for r in records(result)))
        self.assertFalse(metadata(result)['truncated'])
        self.assertFalse(result.extraction_metadata['recalculated'])

    def test_synthetic_worksheets_are_parsed_once_each(self):
        data = package([
            ('One', 'visible', 'worksheets/one.xml', worksheet(
                '<row><c r="A1"><f>1+1</f><v>2</v></c></row>'), None),
            ('Two', 'visible', 'worksheets/two.xml', worksheet(
                '<row><c r="B1"><f>2+2</f><v>4</v></c></row>'), None),
        ])
        seen = []
        parse = ET.fromstring
        def tracked(raw, *args, **kwargs):
            if b'<worksheet' in raw:
                seen.append(raw)
            return parse(raw, *args, **kwargs)
        with mock.patch.object(rex.ET, 'fromstring', side_effect=tracked):
            self.assertEqual(len(records(scoped(data))), 2)
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(set(seen)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
