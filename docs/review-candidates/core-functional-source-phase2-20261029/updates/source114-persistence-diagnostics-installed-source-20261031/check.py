#!/usr/bin/env python3
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def no_effects(event, args):
    if event.startswith(("socket.", "subprocess.")) or event in {
        "os.system",
        "os.exec",
        "os.spawn",
        "os.remove",
        "os.rename",
        "os.mkdir",
        "os.rmdir",
        "os.chmod",
        "os.chown",
        "os.symlink",
        "os.link",
        "os.truncate",
    }:
        raise AssertionError("unexpected external effect: " + event)
    if event == "open":
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(char in mode for char in "wax+")) or (
            isinstance(flags, int)
            and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        ):
            raise AssertionError("unexpected file write")


sys.addaudithook(no_effects)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shipped(relative):
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink(), relative
    assert ROOT in path.resolve().parents, relative
    return path


manifest = json.loads(shipped("MANIFEST.json").read_text(encoding="utf-8"))
for row in manifest["files"]:
    path = shipped(row["path"])
    assert path.stat().st_size == row["bytes"], row["path"]
    assert sha(path) == row["sha256"], row["path"]

pins = json.loads(shipped("SOURCE-HASHES.json").read_text(encoding="utf-8"))
for relative, row in pins["final"].items():
    final_path = shipped(row["path"])
    basis_path = shipped(pins["basis"][relative]["path"])
    assert sha(final_path) == row["sha256"], relative
    assert sha(basis_path) == pins["basis"][relative]["sha256"], relative
    before = basis_path.read_text(encoding="utf-8").splitlines(keepends=True)
    after = final_path.read_text(encoding="utf-8").splitlines(keepends=True)
    expected = "".join(
        difflib.unified_diff(before, after, fromfile="a/" + relative, tofile="b/" + relative)
    )
    actual = shipped(row["patch"]).read_text(encoding="utf-8")
    assert actual == expected, row["patch"]

stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
report = {
    "schema": "friday.source114-persistence-public-portable-controls.v1",
    "success": result.wasSuccessful(),
    "tests": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "actual_source_functions": True,
    "source_and_basis_hash_checks": 6,
    "exact_patch_transitions": 3,
    "manifest_payload_hashes": True,
    "source_only": True,
    "external_effects": 0,
    "runtime_or_user_semantic_acceptance": False,
    "scope": "shipped exact bytes and synthetic in-memory dependencies; no product, model, DB, network, Office or service calls",
}
print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
sys.exit(not result.wasSuccessful())
