"""Installer compatibility exports for the shared native process boundary."""

from scripts.friday_install import _source_runtime_module

_containment = _source_runtime_module('runtime_containment')
Budget, checked_binary, argv, namespace_exit, Containment = (
    getattr(_containment, name) for name in
    ('Budget', 'checked_binary', 'argv', 'namespace_exit', 'Containment'))
