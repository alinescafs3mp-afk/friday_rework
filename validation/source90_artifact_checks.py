"""Portable, observational checks extracted from Source90 installation work.

These functions do not read host files, import a target module, decode a cache,
install software, or grant runtime admission. The caller must independently
authenticate the manifest, file custody and PYC header before using a result.
"""
import hashlib
import marshal
from pathlib import PurePosixPath


def source_compiled_payload_matches(source, filename, payload):
    """Compare an entire PYC body to exact-source compile serializations.

    filename is part of the code object and must be independently authenticated.
    CPython can serialize references differently depending on object ownership;
    an explicit owning container covers the native FLAG_REF form on CPython 3.14.
    This is an equality check, not a parser for untrusted marshal data.
    A false result means these serializations did not prove equality. Nested
    object ownership can change serialization too; false does not prove that
    source or cached code changed. This helper does not provide complete cache
    validation across import contexts.
    """
    if type(source) is not bytes or type(payload) is not bytes:
        raise TypeError('source_and_payload_bytes_required')
    if type(filename) is not str or not filename:
        raise ValueError('authenticated_compile_filename_required')
    code = compile(source, filename, 'exec', dont_inherit=True, optimize=0)
    retained = marshal.dumps(code, marshal.version)
    temporary = marshal.dumps(
        compile(source, filename, 'exec', dont_inherit=True, optimize=0),
        marshal.version,
    )
    holder = [code]
    owned = marshal.dumps(holder[0], marshal.version)
    return payload in (retained, temporary, owned)


def check_source_inventory(files, observed_modes, read_record):
    """Check exact inventory, bytes and preserved mode via a supplied reader.

    read_record(relative_name) returns (bytes, current_permission_mode). It must
    provide its own race, ownership, regular-file and link protections. Git mode
    100644 means non-executable: preserved OS modes 0600 and 0644 are supported.
    """
    def require(ok, reason):
        if not ok:
            raise ValueError(reason)

    require(type(files) is dict and type(observed_modes) is dict and
            set(files) == set(observed_modes), 'exact_mode_inventory_required')
    for relative, row in files.items():
        require(type(relative) is str and relative and '\x00' not in relative and
                PurePosixPath(relative).parts and
                not PurePosixPath(relative).is_absolute() and
                '..' not in PurePosixPath(relative).parts and
                str(PurePosixPath(relative)) == relative,
                'canonical_relative_name_required')
        expected = observed_modes[relative]
        require(type(expected) is int and expected in (0o600, 0o644, 0o755),
                'supported_observed_mode_required')
        require(type(row) is dict and row.get('mode') in ('100644', '100755'),
                'canonical_git_mode_required')
        require(bool(expected & 0o111) == (row['mode'] == '100755'),
                'observed_git_executable_mismatch')
        raw, actual = read_record(relative)
        require(type(raw) is bytes and type(row.get('bytes')) is int and
                len(raw) == row['bytes'] and
                hashlib.sha256(raw).hexdigest() == row.get('sha256'),
                'source_bytes_changed')
        require(type(actual) is int and actual == expected,
                'source_mode_changed')
    return True
