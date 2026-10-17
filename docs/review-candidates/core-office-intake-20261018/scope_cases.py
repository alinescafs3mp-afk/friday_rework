"""Ordinary office dispatch and text-write boundaries, using synthetic users.

Injected converters below test the scoped dispatch contract only. They do not
qualify any conversion backend; actual converter tests are kept separately.
RTF boundary inputs are genuine small RTF documents, never renamed text files.
"""
import json
import os

import pytest

from file_native_fixture import env, entered, home, scope
from hermes_cli import friday_workspace_revision as revision
from tools import file_tools as ft, read_extract as extraction
from tools.binary_extensions import BINARY_EXTENSIONS, OPAQUE_DOCUMENT_EXTENSIONS


RTF = br'{\rtf1\ansi Ordinary own document\par Second paragraph\par}'
ADDED_FORMATS = ('odt', 'rtf', 'xlsx', 'ods', 'pptx', 'odp')
EXTRA_OPAQUE = {
    '.pdf', '.dot', '.dotx', '.dotm', '.xlt', '.xltx', '.xltm', '.xla',
    '.xlam', '.xlw', '.xlm', '.potx', '.potm', '.sldx', '.sldm',
    '.odg', '.odf', '.odb', '.odm', '.oth', '.ott', '.ots', '.otp', '.otg',
    '.db-wal', '.sqlite-shm', '.sqlite3-journal',
}
REFUSED = {'success': False, 'error': 'product_user_scope_refused'}


def put(env, name='report.rtf', data=RTF, uid='1'):
    path = home(env, uid) / 'workspace' / name
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def read(name='report.rtf', **kwargs):
    return json.loads(ft.read_file_tool(name, **kwargs))


@pytest.mark.parametrize('format', ADDED_FORMATS)
def test_dispatch_contract_passes_selected_snapshot_bytes_only(env, monkeypatch, format):
    # No fabricated document is passed to a real converter. Both ends of this
    # seam are observed here; container validity belongs to backend tests.
    snapshot = bytes(bytearray(b'\x00immutable scoped byte snapshot\xff'))
    seen = []
    def take_snapshot(path, *, max_bytes):
        assert path == str(home(env) / 'workspace' / ('report.' + format.upper()))
        assert max_bytes == 1000000
        seen.append('snapshot')
        return snapshot, 'report.' + format.upper()
    def convert(data, kind):
        assert type(data) is bytes and data is snapshot and kind == format
        seen.append('convert')
        return 'Visible first line\nVisible second line\n'
    def forbidden_coverage(*args, **kwargs):
        raise AssertionError('extracted text cannot grant binary revision coverage')
    monkeypatch.setattr(scope, 'workspace_document', take_snapshot)
    monkeypatch.setattr(extraction, 'extract_scoped_document_bytes', convert)
    monkeypatch.setattr(revision, 'note_read', forbidden_coverage)
    with entered(env):
        result = read('report.' + format.upper(), offset=2, limit=1)
        assert result['success'] and result['extracted_document']
        assert result['format'] == format and result['content'] == '2: Visible second line'
        assert result['coverage'] == 'text_only; images_and_layout_not_covered'
        assert result['path'] == 'report.' + format.upper()
        assert seen == ['snapshot', 'convert']


def test_all_shared_binary_opaque_and_template_suffixes_refuse_new_and_old_text(env, monkeypatch):
    # Synthetic negative targets intentionally need no valid container: text
    # must be refused before create/revision regardless of their current bytes.
    def no_text_write(*args, **kwargs):
        raise AssertionError('opaque target reached native text-write backend')
    monkeypatch.setattr(revision, 'write', no_text_write)
    suffixes = sorted(BINARY_EXTENSIONS | OPAQUE_DOCUMENT_EXTENSIONS | EXTRA_OPAQUE)
    with entered(env):
        root = home(env) / 'workspace'
        for number, suffix in enumerate(suffixes):
            old = put(env, f'old-{number}' + suffix.upper(), b'\x00RETAINED\xff')
            new = f'new-{number}' + suffix.upper()
            for name in (old.name, new):
                result = json.loads(ft.write_file_tool(name, 'UTF8 must not masquerade'))
                assert result == {'success': False, 'error': 'document_write_unsupported',
                                  'format': suffix[1:]}, name
            assert old.read_bytes() == b'\x00RETAINED\xff'
            assert not (root / new).exists()


@pytest.mark.parametrize('name', ['notes.txt', 'source.py', 'data.json', 'rows.csv',
                                  'rows.tsv', 'markup.xml', 'page.html', 'README'])
def test_legitimate_text_and_code_creation_remains_available(env, name):
    text = 'name,value\nFriday,1\n' if name.endswith('.csv') else 'ordinary text\t1\n'
    with entered(env):
        result = json.loads(ft.write_file_tool(name, text, format='text'))
        assert result['success'] and (home(env) / 'workspace' / name).read_text() == text
        assert read(name)['success']


@pytest.mark.parametrize('kind', ['foreign', 'symlink', 'hardlink', 'parent-symlink',
                                  'permission', 'parent-permission', 'directory',
                                  'oversize', 'traversal', 'revoked'])
def test_genuine_rtf_scope_denials_happen_before_converter(env, monkeypatch, kind):
    seen = []
    monkeypatch.setattr(extraction, 'extract_scoped_document_bytes',
                        lambda *args: seen.append(args) or 'UNREACHABLE')
    with entered(env) as cap:
        path = put(env)
        foreign = put(env, uid='2')
        name = path.name
        if kind == 'foreign':
            name = str(foreign)
        elif kind == 'symlink':
            path.unlink(); path.symlink_to(foreign)
        elif kind == 'hardlink':
            os.link(path, path.with_name('other.rtf'))
        elif kind == 'parent-symlink':
            (path.parent / 'linked').symlink_to(foreign.parent)
            name = 'linked/report.rtf'
        elif kind == 'permission':
            path.chmod(0o644)
        elif kind == 'parent-permission':
            directory = path.parent / 'unprivate'
            directory.mkdir(mode=0o755); directory.chmod(0o755)
            name = 'unprivate/report.rtf'
            (directory / 'report.rtf').write_bytes(RTF)
        elif kind == 'directory':
            path.unlink(); path.mkdir(mode=0o700)
        elif kind == 'oversize':
            path.write_bytes(RTF + b' ' * 1000000)
        elif kind == 'traversal':
            name = '../report.rtf'
        else:
            cap.revoked = True
        assert read(name) == REFUSED and seen == []
        assert foreign.read_bytes() == RTF


@pytest.mark.parametrize('kind', ['revoked', 'generation', 'grant'])
@pytest.mark.parametrize('converter_fails', [False, True])
def test_changed_authority_discards_success_and_failure_output(env, monkeypatch, kind, converter_fails):
    from hermes_cli.friday_product_access import KEY, current_access
    from hermes_cli.plugins_state import PluginState
    with entered(env) as cap:
        path = put(env)
        def convert(data, format):
            assert data == RTF and format == 'rtf'
            if kind == 'revoked':
                cap.revoked = True
            elif kind == 'generation':
                with scope.authority(env.root):
                    access = current_access()
                    access['users'][cap.key]['enabled'] = False
                    PluginState('friday_rework').set(KEY, access)
                    access = current_access()
                    access['users'][cap.key]['enabled'] = True
                    PluginState('friday_rework').set(KEY, access)
            else:
                config = env.root / 'config.yaml'
                value = json.loads(config.read_text())
                bindings = value['plugins']['entries']['friday_rework']['settings']['user_isolation']['bindings']
                bindings[0]['tools'].remove('read_file')
                config.write_text(json.dumps(value))
            if converter_fails:
                raise extraction.ScopedExtractionError('missing_local_converter')
            return 'DISCARDED after authority changed\n'
        monkeypatch.setattr(extraction, 'extract_scoped_document_bytes', convert)
        assert read() == REFUSED and path.read_bytes() == RTF


def test_rtf_snapshot_remains_immutable_when_named_file_replaced(env, monkeypatch):
    with entered(env):
        path = put(env)
        def convert(data, format):
            assert type(data) is bytes and data == RTF and format == 'rtf'
            path.unlink(); path.write_bytes(b'replaced after snapshot'); path.chmod(0o600)
            assert data == RTF
            return 'Text from selected immutable snapshot\n'
        monkeypatch.setattr(extraction, 'extract_scoped_document_bytes', convert)
        assert 'immutable snapshot' in read()['content']
        assert path.read_bytes() == b'replaced after snapshot'


def test_backend_gap_is_typed_and_does_not_fall_back_to_utf8(env, monkeypatch):
    with entered(env):
        path = put(env)
        def unavailable(data, format):
            assert data == RTF and format == 'rtf'
            raise extraction.ScopedExtractionError('missing_local_converter')
        monkeypatch.setattr(extraction, 'extract_scoped_document_bytes', unavailable)
        assert read() == {'success': False, 'error': 'document_extraction_failed',
                          'format': 'rtf', 'reason': 'missing_local_converter'}
        assert path.read_bytes() == RTF


def test_native_delivery_of_extracted_text_grants_no_binary_overwrite(env, monkeypatch):
    from test_read_delivery import actor, dispatch, finalized, transport, TASK
    with entered(env) as cap:
        path = put(env)
        monkeypatch.setattr(extraction, 'extract_scoped_document_bytes',
                            lambda data, format: 'Visible extracted text\n')
        agent = actor()
        messages = finalized(agent, path.name, ident='rtf-read')
        call = agent._tool_result_calls[(TASK, 'rtf-read')]
        assert not getattr(call, '_workspace_read', None)
        transport(agent, messages, monkeypatch)
        assert revision._baseline(cap, TASK, path.name) is None
        _, outcome = dispatch(agent, 'write_file', {'path': path.name, 'content': 'DESTROY'}, 'rtf-write')
        assert json.loads(outcome.result)['error'] == 'document_write_unsupported'
        assert path.read_bytes() == RTF


@pytest.mark.parametrize('name', ['rows.csv', 'rows.tsv'])
def test_native_text_revision_still_requires_delivered_current_read(env, monkeypatch, name):
    from test_read_delivery import actor, create, finalized, transport, write
    with entered(env):
        agent = actor()
        create(agent, name, 'one\ttwo\n')
        assert write(agent, name)['error'] == 'file_revision_requires_current_full_read'
        messages = finalized(agent, name)
        transport(agent, messages, monkeypatch)
        assert write(agent, name, 'one\tTHREE\n')['success']
        assert (home(env) / 'workspace' / name).read_text() == 'one\tTHREE\n'


def test_explicit_docx_remains_create_only_and_generic_patch_ungranted(env):
    with entered(env):
        name = 'new.docx'
        result = json.loads(ft.write_file_tool(name, 'Native DOCX text', format='docx'))
        assert result['success'] and result['create_only']
        path = home(env) / 'workspace' / name
        before = path.read_bytes()
        assert read(name)['success'] and 'Native DOCX text' in read(name)['content']
        assert json.loads(ft.write_file_tool(name, 'Changed', format='docx'))['error'] == 'document_already_exists'
        assert json.loads(ft.write_file_tool(name, 'Changed'))['error'] == 'document_write_unsupported'
        with pytest.raises(scope.ScopeDenied):
            scope.guard_tool('patch', {'path': str(path), 'old_string': 'Native', 'new_string': 'Changed'})
        assert path.read_bytes() == before
