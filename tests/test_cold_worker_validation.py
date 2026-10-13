"""Cold preparation must not require Hermes; native execution still does."""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_cold_worker_validation_keeps_pins_and_native_admission(tmp_path):
    code = r'''
import hashlib, importlib.abc, pathlib, sys
sys.path.insert(0, sys.argv[1])
class NoHermes(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'hermes_cli' or fullname.startswith('hermes_cli.'):
            raise ModuleNotFoundError('Hermes deliberately absent during cold preparation')
sys.meta_path.insert(0, NoHermes())
from scripts.worker_install import settings
from scripts.a0_prepare import service_plan
from plugins.friday_rework.host_runtime import _pin, configured_runtimes, NativeSupervisor, HostUnavailable
assert not any(n.startswith('hermes_cli') for n in sys.modules)
assert not configured_runtimes({'enabled': False})
path = pathlib.Path(sys.argv[2]) / 'input'
path.write_bytes(b'checked input'); path.chmod(0o600)
pin = _pin({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
assert pin.read() == b'checked input'
path.write_bytes(b'changed input')
try:
    pin.read()
except RuntimeError:
    pass
else:
    raise AssertionError('changed input was accepted')
for bad in ({'path': 'relative', 'sha256': 'a'*64},
            {'path': str(path), 'sha256': 'not-a-hash'},
            {'path': str(path), 'sha256': 'a'*64, 'ready': True}):
    try:
        _pin(bad)
    except HostUnavailable:
        pass
    else:
        raise AssertionError('invalid input pin was accepted')
try:
    from plugins.friday_rework.supervision import NativeSupervisor as actual_native
except ModuleNotFoundError:
    try:
        NativeSupervisor()
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError('missing native supervisor was replaced')
else:
    assert type(NativeSupervisor()) is actual_native
'''
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG') if k in os.environ}
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT), str(tmp_path)],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
