"""Bounded byte intake regressions, plus opt-in real local converter observations.

FRIDAY_OFFICE_TEST_FIXTURES may select an independently authored synthetic fixture
directory. No package installation, source catalogue, network or CLI conversion is
performed by these tests. Missing real fixture evidence stays an explicit skip.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import zipfile
import zlib

import pytest


def _extractor():
    source = os.environ.get('FRIDAY_OFFICE_TEST_SOURCE')
    if source:
        spec = importlib.util.spec_from_file_location('office_intake_under_test', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    from tools import read_extract
    return read_extract


@pytest.fixture
def extractor():
    return _extractor()


def package(entries, compression=zipfile.ZIP_STORED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=compression) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return output.getvalue()


def rejected(extractor, data, format, code):
    with pytest.raises(extractor.ScopedExtractionError) as caught:
        extractor.extract_scoped_document_bytes(data, format)
    assert caught.value.code == code


@pytest.mark.parametrize('data', [b'x' * 1000001, bytearray(b'{\\rtf1 text}'), 'text'])
def test_snapshot_type_and_size_are_required(extractor, data):
    rejected(extractor, data, 'rtf', 'input_limit')


@pytest.mark.parametrize('format', ['docm', 'zip', 'csv', 'unknown', 'RTF'])
def test_unsupported_format_never_gains_byte_converter_authority(extractor, format):
    rejected(extractor, b'{\\rtf1 text}', format, 'unsupported_format')


@pytest.mark.parametrize('format', ['rtf', 'xlsx', 'pptx', 'odt', 'ods', 'odp', 'pdf'])
def test_plain_text_cannot_masquerade_as_office(extractor, format):
    expected = 'format_mismatch' if format in ('rtf', 'pdf') else 'malformed_or_unsupported'
    rejected(extractor, b'ordinary UTF-8 text', format, expected)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'dir/../escape', 'drive:name', 'dir\\escape'])
def test_zip_path_links_are_rejected_before_conversion(extractor, name):
    rejected(extractor, package([(name, b'payload')]), 'xlsx', 'unsafe_archive_member')


def test_zip_symlink_is_rejected(extractor):
    link = zipfile.ZipInfo('symlink')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    rejected(extractor, package([(link, b'/private/source')]), 'pptx', 'unsafe_archive_member')


def test_duplicate_member_does_not_hide_a_second_payload(extractor):
    with pytest.warns(UserWarning, match='Duplicate name'):
        data = package([('same', b'first'), ('same', b'second')])
    rejected(extractor, data, 'xlsx', 'unsafe_archive_member')


def test_many_tiny_members_are_bounded(extractor):
    data = package([(f'member{i}', b'x') for i in range(257)])
    rejected(extractor, data, 'odt', 'archive_member_limit')


def test_high_ratio_compressed_member_is_bounded(extractor):
    data = package([('large', b'A' * 300000)], zipfile.ZIP_DEFLATED)
    rejected(extractor, data, 'xlsx', 'archive_expansion_limit')


@pytest.mark.parametrize('name', ['payload', 'hidden/'])
def test_false_size_and_prefix_crc_cannot_hide_deflate_expansion(extractor, name):
    payload = b'A' * 1100000
    data = bytearray(package([(name, payload)], zipfile.ZIP_DEFLATED))
    central = data.index(b'PK\x01\x02')
    prefix_crc = zlib.crc32(payload[:10]) & 0xffffffff
    for offset, crc_at, size_at in ((0, 14, 22), (central, 16, 24)):
        struct.pack_into('<I', data, offset + crc_at, prefix_crc)
        struct.pack_into('<I', data, offset + size_at, 10)
    # Demonstrate the adversarial archive: ordinary ZipExtFile returns only
    # the forged size and validates the forged prefix CRC, concealing the rest.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read(name) == payload[:10]
    rejected(extractor, bytes(data), 'xlsx', 'archive_expansion_limit')


def test_wrong_odf_container_identity_is_not_inferred_from_suffix(extractor):
    data = package([('mimetype', b'application/vnd.oasis.opendocument.text'),
                    ('content.xml', b'<document/>')])
    rejected(extractor, data, 'ods', 'format_mismatch')


def test_zip_crc_damage_is_reported(extractor):
    data = package([('content.xml', b'UNIQUE_CRC_PAYLOAD'),
                    ('mimetype', b'application/vnd.oasis.opendocument.text')])
    data = data.replace(b'UNIQUE_CRC_PAYLOAD', b'BROKEN_CRC_PAYLOAD')
    rejected(extractor, data, 'odt', 'malformed_or_unsupported')


@pytest.fixture
def real_fixtures():
    selected = os.environ.get('FRIDAY_OFFICE_TEST_FIXTURES')
    root = Path(selected) if selected else Path(__file__).parent / 'fixtures' / 'core_office'
    assert root.is_dir()
    if not selected and importlib.util.find_spec('anydoc') is None:
        pytest.skip('optional local anydoc converter is absent; no installation attempted')
    return root


@pytest.mark.parametrize(('format', 'literal'), [
    ('rtf', 'Synthetic rich text 175.'),
    ('xlsx', 'Synthetic cell 853'),
    ('pptx', 'Synthetic slide 964'),
    ('odt', 'Synthetic rich text 175.'),
    ('ods', 'Synthetic cell 853'),
    ('odp', 'Synthetic slide 964'),
])
def test_real_authored_bytes_convert_locally(extractor, real_fixtures, format, literal):
    data = (real_fixtures / ('synthetic.' + format)).read_bytes()
    text = extractor.extract_scoped_document_bytes(data, format)
    assert literal in text


def test_real_rtf_rejects_truncation_instead_of_reading_plain_text(extractor, real_fixtures):
    data = (real_fixtures / 'synthetic.rtf').read_bytes()
    # The maintained parser tolerates this truncated header but produces no
    # text; the public API must still refuse it rather than return success.
    rejected(extractor, data[:6], 'rtf', 'no_extractable_text')


def test_local_converter_absence_is_an_honest_gap(extractor, monkeypatch, real_fixtures):
    # Remove only this test's explicit optional vendor path. No dependency is
    # installed or hidden from an actual runtime; this is a dev capability case.
    vendor = os.environ.get('FRIDAY_OFFICE_TEST_VENDOR')
    if not vendor:
        pytest.skip('explicit optional development vendor directory not selected')
    original = list(sys.path)
    monkeypatch.setattr(sys, 'path', [entry for entry in original
                                    if Path(entry or '.').resolve() != Path(vendor).resolve()])
    if importlib.util.find_spec('anydoc') is not None:
        pytest.skip('a separate actual anydoc installation is present')
    rejected(extractor, (real_fixtures / 'synthetic.rtf').read_bytes(),
             'rtf', 'missing_local_converter')


def _worker_double(extractor, tmp_path, source):
    """A declared test double probes containment, never converter capability."""
    root = tmp_path / 'double_library'
    package_dir = root / 'anydoc'
    package_dir.mkdir(parents=True)
    (package_dir / '__init__.py').write_text(source)
    worker = Path(extractor.__file__).with_name('scoped_office_worker.py')
    completed = subprocess.run([sys.executable, '-I', '-B', str(worker), str(root)],
                               input=b'rtf\n{\\rtf1 synthetic}',
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=5, close_fds=True, cwd='/', env={'LANG': 'C.UTF-8'})
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_exact_worker_denies_file_network_and_fork_with_explicit_double(extractor, tmp_path):
    source = '''import errno,json,os,socket
def format_from_bytes(data): return 'rtf'
def to_markdown_bytes(data,format=None,ocr=None):
    assert format=='rtf' and ocr=='reject'
    observed={}
    operations={'file':lambda:open('/synthetic-containment-negative','rb'),
                'network':lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM),
                'process':os.fork}
    for name,operation in operations.items():
        try:operation()
        except OSError as exc:observed[name]=exc.errno
        else:raise AssertionError('containment bypass: '+name)
    assert all(value==errno.EPERM for value in observed.values()),observed
    return json.dumps(observed)
'''
    result = _worker_double(extractor, tmp_path, source)
    assert json.loads(result['text']) == {'file': 1, 'network': 1, 'process': 1}


def test_exact_worker_filters_an_existing_helper_thread_with_explicit_double(extractor, tmp_path):
    source = '''import errno,json,threading
trigger=threading.Event()
observed=[]
def helper():
    trigger.wait()
    try:open('/synthetic-containment-negative','rb')
    except OSError as exc:observed.append(exc.errno)
    else:observed.append('unexpected_open')
thread=threading.Thread(target=helper)
thread.start()
def format_from_bytes(data): return 'rtf'
def to_markdown_bytes(data,format=None,ocr=None):
    trigger.set()
    thread.join(timeout=1)
    assert not thread.is_alive() and observed==[errno.EPERM],observed
    return json.dumps(observed)
'''
    result = _worker_double(extractor, tmp_path, source)
    assert json.loads(result['text']) == [1]


def test_exact_worker_new_thread_inherits_filter_with_explicit_double(extractor, tmp_path):
    source = '''import errno,json,os,resource,socket,threading
def format_from_bytes(data): return 'rtf'
def to_markdown_bytes(data,format=None,ocr=None):
    observed={}
    def helper():
        operations={'file':lambda:open('/synthetic-containment-negative','rb'),
                    'network':lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM),
                    'process':os.fork,
                    'parent_rlimit':lambda:resource.prlimit(os.getppid(),resource.RLIMIT_CPU)}
        for name,operation in operations.items():
            try:operation()
            except OSError as exc:observed[name]=exc.errno
            else:observed[name]='unexpected_success'
        resource.getrlimit(resource.RLIMIT_CPU)
    thread=threading.Thread(target=helper)
    thread.start()
    thread.join(timeout=1)
    assert not thread.is_alive(),observed
    assert observed==dict.fromkeys(('file','network','process','parent_rlimit'),errno.EPERM),observed
    return json.dumps({'thread_started':True,'observed':observed})
'''
    result = _worker_double(extractor, tmp_path, source)
    assert json.loads(result['text']) == {
        'thread_started': True,
        'observed': {'file': 1, 'network': 1, 'process': 1, 'parent_rlimit': 1},
    }


def test_exact_worker_rejects_oversized_output_with_explicit_double(extractor, tmp_path):
    result = _worker_double(extractor, tmp_path,
        "def format_from_bytes(data): return 'rtf'\n"
        "def to_markdown_bytes(data,format=None,ocr=None): return 'x'*1000001\n")
    assert result == {'error': 'extracted_text_limit'}


def test_exact_worker_reports_broken_local_binding_with_explicit_double(extractor, tmp_path):
    result = _worker_double(extractor, tmp_path, 'from ._missing_native_binding import to_markdown_bytes\n')
    assert result == {'error': 'missing_local_converter'}


def test_parent_accepts_bounded_control_text_despite_larger_json_envelope(extractor, tmp_path, monkeypatch):
    root = tmp_path / 'control_text_library'
    package_dir = root / 'anydoc'
    package_dir.mkdir(parents=True)
    (package_dir / '__init__.py').write_text(
        "def format_from_bytes(data): return 'rtf'\n"
        "def to_markdown_bytes(data,format=None,ocr=None): return chr(0)*1000000\n")
    spec = importlib.util.spec_from_loader('anydoc', loader=None,
                                        origin=str(package_dir / '__init__.py'))
    original_find = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec',
                        lambda name, *args: spec if name == 'anydoc' else original_find(name, *args))
    text = extractor.extract_scoped_document_bytes(b'{\\rtf1 synthetic}', 'rtf')
    assert text == '\x00' * 1000000


def test_parent_timeout_kills_and_reaps_actual_synthetic_worker(extractor, tmp_path, monkeypatch):
    selected = tmp_path / 'timeout_helper'
    selected.mkdir()
    (selected / 'scoped_office_worker.py').write_text('while True: pass\n')
    monkeypatch.setattr(extractor, '__file__', str(selected / 'read_extract.py'))
    # Only package discovery is synthetic. Popen, timeout, SIGKILL, communicate
    # and wait are the actual production parent implementation.
    spec = importlib.util.spec_from_loader('anydoc', loader=None,
                                        origin=str(selected / 'anydoc' / '__init__.py'))
    original_find = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec',
                        lambda name, *args: spec if name == 'anydoc' else original_find(name, *args))
    original_spawn = subprocess.Popen
    children = []
    def spawn(*args, **kwargs):
        child = original_spawn(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    rejected(extractor, b'{\\rtf1 synthetic}', 'rtf', 'converter_timeout')
    assert len(children) == 1
    assert children[0].returncode is not None
    assert children[0].wait(timeout=0) == children[0].returncode
