"""Source-only fixtures; no installed credential host or model is started."""
import os
from pathlib import Path
import pytest
os.umask(0o077)
from hermes_cli import env_loader
# These cases build gateway runners with __new__, without an installed marker.
env_loader.load_hermes_dotenv = lambda *args, **kwargs: ()

@pytest.fixture(autouse=True)
def _bounded_multipass_fixture_home(request, monkeypatch, tmp_path):
    if request.node.path.name == "test_bounded_multipass.py":
        if "_hermetic_environment" in request.fixturenames:
            request.getfixturevalue("_hermetic_environment")
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        monkeypatch.setenv("HERMES_HOME", str(home))
