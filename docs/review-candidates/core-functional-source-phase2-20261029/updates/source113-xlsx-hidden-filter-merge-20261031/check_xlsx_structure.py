"""Offline B146 controls using exact copied source and an in-memory OOXML fixture.

Optional --input repeats the fixture-dependent controls on a retained workbook.
The checker emits JSON to stdout. It never installs, sends or writes an artifact.
"""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
S = '{' + NS + '}'
PINS = {
    'native/source112/tools/read_extract.py': 'cd7c578834272b9d982213e7d1d99c6373fb1d94733cb02f7af5530cdf2dcb87',
    'native/author-b146/tools/read_extract.py': 'd568b4f41fb301b89a9c41ab5f0c9d77fbe4344a4d77c913aa073b4118236646',
    'native/source113/tools/read_extract.py': '67fe706b5fd0bea92bb112949ee32c8695715bff6dd441512e6674c5998172dc',
    'patches/hermes/xlsx-hidden-filter-merge-structure-after-source112.patch': '9643d26f2a3a211ad6db10dc8e77c29fd6c4183ca8cece203a43aa96b5c84842',
    'patches/hermes/xlsx-hidden-filter-merge-structure-after-source112-manifest.json': '61395aa906712473680dbf5ea4f5dcfa12385603864b781c983e87ff1b7678ac',
    'patches/reviewer-fix.patch': '390fb3aedbfea05b49811964aaa469da51cf20840cf91bd08a86dd8c54e84311',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def synthetic_fixture():
    # Fixed timestamps and literal synthetic values make the bytes reproducible.
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        'xl/workbook.xml': '<workbook xmlns="' + NS + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Synthetic" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': '<worksheet xmlns="' + NS + '"><cols><col min="4" max="4" hidden="1"/></cols><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Synthetic header</t></is></c></row><row r="2" hidden="1"><c r="A2"><v>7</v></c><c r="B2" t="inlineStr"><is><t>Merge anchor</t></is></c></row><row r="3"><c r="A3"><v>11</v></c></row></sheetData><autoFilter ref="A1:D3"><filterColumn colId="0"><filters><filter val="7"/></filters></filterColumn></autoFilter><mergeCells count="1"><mergeCell ref="B2:C2"/></mergeCells></worksheet>',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, content in parts.items():
            archive.writestr(zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)), content)
    return output.getvalue()


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mutate(data, edit):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as archive, zipfile.ZipFile(output, 'w') as target:
        for entry in archive.infolist():
            raw = archive.read(entry.filename)
            if entry.filename == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(raw)
                edit(root)
                raw = ET.tostring(root, encoding='utf-8')
            target.writestr(entry, raw)
    return output.getvalue()


def structure(module, raw):
    text = module.extract_scoped_document_bytes(raw, 'xlsx')
    part = text[text.index('# XLSX structure preview'):]
    rows = [json.loads(line) for line in part.splitlines() if line.startswith('{')]
    return text, rows


def cache_case(data, typ, formula, value, inline=None):
    def edit(root):
        cell = next(c for c in root.iter(S + 'c') if c.get('r') == 'B2')
        cell.clear()
        cell.set('r', 'B2')
        cell.set('t', typ)
        if formula:
            ET.SubElement(cell, S + 'f').text = '1=1'
        if value is not None:
            ET.SubElement(cell, S + 'v').text = value
        if inline is not None:
            ET.SubElement(ET.SubElement(cell, S + 'is'), S + 't').text = inline
    return mutate(data, edit)


def anchor(module, raw):
    merge = next(row for row in structure(module, raw)[1] if row['kind'] == 'merge')
    return merge['anchor'], merge['non_anchor_cells'][0]['inherited_display']


def apply_exact(before, patch):
    lines = patch.decode().splitlines(True)
    assert lines[0].startswith('--- ') and lines[1].startswith('+++ ')
    source = before.decode().splitlines(True)
    output, position, index = [], 0, 2
    while index < len(lines):
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[index])
        assert match, 'unrecognized hunk'
        index += 1
        old_line, old_count, new_line, new_count = int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1)
        assert old_line - 1 >= position
        output.extend(source[position:old_line - 1])
        position = old_line - 1
        assert len(output) == new_line - 1
        used = made = 0
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]
            index += 1
            assert line[0] in ' +-'
            if line[0] in ' -':
                assert source[position] == line[1:], 'hunk preimage mismatch'
                position += 1
                used += 1
            if line[0] in ' +':
                output.append(line[1:])
                made += 1
        assert (used, made) == (old_count, new_count)
    output.extend(source[position:])
    return ''.join(output).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes() if args.input else synthetic_fixture()
    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append({'id': name, 'status': 'PASS', 'detail': detail})
        except Exception as exc:
            results.append({'id': name, 'status': 'FAIL', 'error_class': type(exc).__name__})

    def source_pins():
        for relative, expected in PINS.items():
            assert digest((ROOT / relative).read_bytes()) == expected
        return {'checked': len(PINS)}
    check('exact_source_and_patch_pins', source_pins)
    original = load('author_b146', 'native/author-b146/tools/read_extract.py')
    corrected = load('source113', 'native/source113/tools/read_extract.py')

    def cache_matrix():
        count = 0
        for typ in ('b', 'e', 'n', 's'):
            for formula in (False, True):
                for value in (None, ''):
                    actual, inherited = anchor(corrected, cache_case(raw, typ, formula, value))
                    state = ('formula_cache_missing' if value is None else 'formula_cache_blank') if formula else 'blank'
                    expected = None if formula and value is None else ''
                    assert actual['stored_state'] == state and actual['stored_value'] == expected
                    assert inherited['value'] == expected
                    count += 1
        for typ, value, expected in [('b', '0', 'FALSE'), ('b', '1', 'TRUE'), ('e', '#DIV/0!', '#DIV/0!'), ('n', '0', '0')]:
            actual, inherited = anchor(corrected, cache_case(raw, typ, True, value))
            assert actual['stored_state'] == 'present' and actual['stored_value'] == expected
            assert inherited['value'] == expected
            count += 1
        return {'variants': count}
    check('missing_blank_present_cache_matrix', cache_matrix)

    def original_defect():
        for typ, false_value in [('b', 'FALSE'), ('e', '#ERROR')]:
            for formula in (False, True):
                before, _ = anchor(original, cache_case(raw, typ, formula, None))
                after, _ = anchor(corrected, cache_case(raw, typ, formula, None))
                assert before['stored_state'] == 'present' and before['stored_value'] == false_value
                assert after['stored_state'] != 'present'
        return {'original_fabricated_value_variants': 4, 'same_input_per_comparison': True}
    check('original_defect_preserved_and_corrected', original_defect)

    def inline_zero():
        actual, inherited = anchor(corrected, cache_case(raw, 'inlineStr', False, None, '0'))
        assert actual['stored_state'] == 'present' and actual['stored_value'] == '0'
        assert inherited['value'] == '0'
        return True
    check('inline_numeric_text_preserved', inline_zero)

    def truncation(mode):
        def edit(root):
            if mode == 'merge_cells':
                root.find(S + 'mergeCells/' + S + 'mergeCell').set('ref', 'A1:ZZ10000')
                return
            filt = root.find(S + 'autoFilter')
            for child in list(filt):
                filt.remove(child)
            node = ET.SubElement(filt, S + 'unsupported')
            if mode == 'text':
                node.text = 'x' * 5000
            elif mode == 'children':
                for _ in range(129):
                    ET.SubElement(node, S + 'item')
            elif mode == 'top_children':
                for _ in range(128):
                    ET.SubElement(filt, S + 'item')
            elif mode == 'depth':
                for _ in range(12):
                    node = ET.SubElement(node, S + 'item')
        data = mutate(raw, edit)
        before, _ = structure(original, data)
        after, _ = structure(corrected, data)
        old_meta = before.extraction_metadata['structure_preview']
        meta = after.extraction_metadata['structure_preview']
        assert old_meta['truncated'] is False
        assert meta['truncated'] is True and meta['records_with_truncated_fields'] == 1
        assert meta['evaluated'] is False and len(after.encode()) <= 1000000
        return {'original_truncated': False, 'corrected_truncated': True}
    for mode in ('text', 'children', 'depth', 'top_children', 'merge_cells'):
        check('truthful_truncation_' + mode, lambda mode=mode: truncation(mode))

    def four_methods():
        before = ast.parse((ROOT / 'native/author-b146/tools/read_extract.py').read_bytes())
        after = ast.parse((ROOT / 'native/source113/tools/read_extract.py').read_bytes())
        old_class = next(n for n in before.body if isinstance(n, ast.ClassDef) and n.name == '_XlsxFormulaPreview')
        new_class = next(n for n in after.body if isinstance(n, ast.ClassDef) and n.name == '_XlsxFormulaPreview')
        old_methods = {n.name: ast.dump(n) for n in old_class.body if isinstance(n, ast.FunctionDef)}
        new_methods = {n.name: ast.dump(n) for n in new_class.body if isinstance(n, ast.FunctionDef)}
        assert old_methods.keys() == new_methods.keys()
        changed = sorted(k for k in old_methods if old_methods[k] != new_methods[k])
        assert set(changed) == {'_structure_add', '_inert_filter_node', 'add_structure', 'render_structure'}
        old_class.body = []
        new_class.body = []
        assert ast.dump(before) == ast.dump(after)
        return changed
    check('reviewer_fix_limited_to_four_methods', four_methods)

    def patch_join():
        before = (ROOT / 'native/source112/tools/read_extract.py').read_bytes()
        patch = (ROOT / 'patches/hermes/xlsx-hidden-filter-merge-structure-after-source112.patch').read_bytes()
        after = (ROOT / 'native/source113/tools/read_extract.py').read_bytes()
        def checked_apply(data):
            assert digest(data) == PINS['native/source112/tools/read_extract.py'], 'wrong whole-file preimage'
            return apply_exact(data, patch)
        assert checked_apply(before) == after
        # Alter a line outside the hunks: a textual application alone could
        # succeed, whereas the published whole-file preimage pin rejects it.
        mutant = before.replace(b'_MAX_XLSX_ROWS_PER_SHEET = 5000', b'_MAX_XLSX_ROWS_PER_SHEET = 5001')
        assert mutant != before
        refused = False
        try:
            checked_apply(mutant)
        except AssertionError:
            refused = True
        assert refused
        return {'exact_afterimage': True, 'whole_file_preimage_pin_rejects_mutation': True}
    check('source112_tail_exact_afterimage_and_wrong_preimage', patch_join)

    def reviewer_patch():
        before = (ROOT / 'native/author-b146/tools/read_extract.py').read_bytes()
        patch = (ROOT / 'patches/reviewer-fix.patch').read_bytes()
        assert apply_exact(before, patch) == (ROOT / 'native/source113/tools/read_extract.py').read_bytes()
        return True
    check('author_to_corrected_patch_exact_afterimage', reviewer_patch)

    def manifest_pin():
        manifest = json.loads((ROOT / 'patches/hermes/xlsx-hidden-filter-merge-structure-after-source112-manifest.json').read_bytes())
        row, = manifest['files']
        assert row['path'] == 'tools/read_extract.py'
        assert row['before_sha256'] == PINS['native/source112/tools/read_extract.py']
        assert row['sha256'] == PINS['native/source113/tools/read_extract.py']
        assert row['bytes'] == (ROOT / 'native/source113/tools/read_extract.py').stat().st_size
        assert manifest['patch_sha256'] == PINS['patches/hermes/xlsx-hidden-filter-merge-structure-after-source112.patch']
        assert len(manifest['prerequisites']) == 139
        for name in ('bounded-continuation.patch', 'bounded-local-context.patch', 'web-exact-limit.patch'):
            assert 'patches/hermes/' + name in manifest['prerequisites']
        return {'prefix_patch_pins': 139, 'required_restored_pins': 3, 'full_prefix_not_reexecuted': True}
    check('manifest_leaf_pins_and_restored_prerequisites', manifest_pin)

    def baseline_structure():
        text, rows = structure(corrected, raw)
        kinds = {row['kind'] for row in rows}
        assert {'hidden_row', 'auto_filter', 'merge'} <= kinds
        assert text.extraction_metadata['structure_preview']['evaluated'] is False
        return {'hidden_rows_filters_and_merge_declarations': True, 'filter_visibility_not_evaluated': True}
    check('ordinary_structure_declarations_preserved', baseline_structure)
    report = {
        'schema': 'friday.public.source113-xlsx-offline-controls.v1',
        'source_only': True,
        'fixture': 'supplied-retained-workbook' if args.input else 'synthetic-in-memory-OOXML',
        'fixture_sha256': digest(raw),
        'checks': results,
        'passed': sum(row['status'] == 'PASS' for row in results),
        'failed': sum(row['status'] != 'PASS' for row in results),
        'live_authority_install_runtime_or_semantic_acceptance': False,
        'effects': [],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['failed'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
