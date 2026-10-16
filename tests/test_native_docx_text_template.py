from io import BytesIO
from pathlib import Path
import pytest
from hermes_cli import friday_workspace_docx as dx
from hermes_cli.friday_user_scope import ScopeDenied

@pytest.mark.parametrize("payload",[b"a",b"!"*48760+b"\n",b"A"*48760+b"\n"])
def test_text_template_invalid_length_encoding_or_hash_refuses(monkeypatch,payload):
 original=Path.open
 def replacement(path,*args,**kwargs):
  if path.name=="friday_plain_docx_template.b64":return BytesIO(payload)
  return original(path,*args,**kwargs)
 monkeypatch.setattr(Path,"open",replacement)
 with pytest.raises(ScopeDenied):dx.render("Valid text")
