"""Exercise the ordinary store contract recommended for explicit scoped requests.

This proves deterministic storage behavior only, never a model's choice to call it.
"""
import json

import pytest

from tools.memory_tool import MemoryStore, memory_tool


@pytest.fixture
def scoped_store(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path)
    original = "Preferred document format: DOCX."
    (tmp_path / "USER.md").write_text(original, encoding="utf-8")
    store = MemoryStore()
    store.load_from_disk()
    return store, tmp_path / "USER.md", original


def test_scoped_correction_preserves_unrelated_preference(scoped_store):
    store, path, original = scoped_store
    scoped_odt = "This conversation test profile: preferred document format ODT."
    added = json.loads(memory_tool(action="add", target="user", content=scoped_odt, store=store))
    assert added["success"] is True and added["done"] is True
    scoped_docx = "This conversation test profile: preferred document format DOCX."
    replaced = json.loads(memory_tool(action="replace", target="user", old_text=scoped_odt,
                                      content=scoped_docx, store=store))
    assert replaced["success"] is True and replaced["done"] is True
    assert path.read_text(encoding="utf-8").split("\n§\n") == [original, scoped_docx]
    assert replaced["replaced_entry"] == scoped_odt
    # The cached prompt remains a snapshot; it cannot testify to the new write.
    assert scoped_docx not in store.format_for_system_prompt("user")


def test_existing_entry_result_reads_current_disk_not_cached_prompt(scoped_store):
    store, path, original = scoped_store
    scoped_odt = "This conversation test profile: preferred document format ODT."
    path.write_text(original + "\n§\n" + scoped_odt, encoding="utf-8")
    before = path.stat()
    result = json.loads(memory_tool(action="add", target="user", content=scoped_odt, store=store))
    assert result["success"] is True and result["done"] is True
    assert "already exists" in result["message"]
    assert path.read_text(encoding="utf-8").split("\n§\n") == [original, scoped_odt]
    assert (path.stat().st_ino, path.stat().st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert scoped_odt not in store.format_for_system_prompt("user")
