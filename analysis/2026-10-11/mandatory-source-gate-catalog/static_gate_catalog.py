#!/usr/bin/env python3
"""Read source registrations without importing or executing target modules.

Output is static preparation only. Effect signals are lower bounds, not grants.
No actual pytest item count, runtime collection, gate or release acceptance.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
MAX_FILE = 8 * 1024 * 1024


class Refusal(ValueError):
    pass


def need(condition, cause):
    if not condition:
        raise Refusal(cause)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def bytes_at(path):
    """Bounded regular-file read; reject symlinks in every component and drift."""
    path = Path(os.path.abspath(path))
    for parent in reversed((path, *path.parents)):
        need(not parent.is_symlink(), "symlink_input:" + str(parent))
    try:
        before = path.stat()
        need(stat.S_ISREG(before.st_mode), "nonregular_input:" + str(path))
        need(before.st_size <= MAX_FILE, "oversized_input:" + str(path))
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(path, flags | os.O_NOATIME)
        except PermissionError:
            fd = os.open(path, flags)  # readonly; atime explicitly not invariant
        try:
            opened = os.fstat(fd)
            need((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                 "changed_input_identity:" + str(path))
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, min(65536, MAX_FILE + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                need(size <= MAX_FILE, "oversized_input:" + str(path))
                chunks.append(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        need((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
              opened.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size,
              after.st_mtime_ns, after.st_ctime_ns), "changed_during_read:" + str(path))
        final = path.stat()
        need((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
              after.st_ctime_ns) == (final.st_dev, final.st_ino, final.st_size,
              final.st_mtime_ns, final.st_ctime_ns), "changed_path_after_read:" + str(path))
        return b"".join(chunks)
    except FileNotFoundError as error:
        raise Refusal("missing_input:" + str(path)) from error


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted(node.value) + "." + node.attr
    return "<dynamic>"


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def classify(path):
    data = bytes_at(path)
    source = data.decode("utf-8")
    python = str(path).endswith(".py")
    tree = ast.parse(source, filename=str(path)) if python else None
    imports, calls, tests, controls, parametrized = [], [], [], [], []
    allowed = None
    for node in ast.walk(tree) if tree is not None else []:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append({"line": node.lineno, "module": node.module if isinstance(node, ast.ImportFrom)
                            else ",".join(n.name for n in node.names)})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            tests.append({"name": node.name, "line": node.lineno})
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and dotted(decorator.func).endswith("parametrize"):
                    values = literal(decorator.args[1]) if len(decorator.args) > 1 else None
                    parametrized.append({"test": node.name, "line": decorator.lineno,
                                         "literal_cases": len(values) if isinstance(values, (list, tuple)) else None,
                                         "expression": ast.get_source_segment(source, decorator)})
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "ALLOWED" for target in node.targets):
                allowed = literal(node.value)
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            calls.append((node.lineno, name))
            if name in ("test", "check", "case") and node.args:
                controls.append({"line": node.lineno, "name_literal": literal(node.args[0]),
                                 "name_expression": ast.get_source_segment(source, node.args[0])})
    patterns = {
        "process": r"subprocess|Popen|os\.system|posix_spawn|child_process|spawn\(|execFile|multiprocessing",
        "network_or_http": r"socket\.|httpx|requests\.|urllib\.request|fetch\(|https?://|aiohttp",
        "native_source_execution": r"exec\(|compile\(|spec_from_file_location|exec_module|sys\.path|hermes_cli|gateway\.",
        "OS_or_native_service": r"systemctl|systemd|kill\(|killpg|os\.open|fcntl|/proc/|PTY|pty\.|signal\.",
        "model_related_reference": r"model|inference|OpenAI|provider|api_key",
        "fixture_or_mock_reference": r"tmp_path|tempfile|monkeypatch|mock|fixture|synthetic|Dummy|Fake|TestClient",
        "thread_or_async": r"threading|Thread\(|asyncio|create_task|to_thread|run_coroutine_threadsafe",
        "third_party_import": r"pytest|yaml|fastapi|pydantic|httpx|dotenv|prompt_toolkit",
    }
    effects = {name: [{"line": index, "snippet": line[:220]} for index, line in enumerate(source.splitlines(), 1)
                      if re.search(pattern, line)][:24] for name, pattern in patterns.items()}
    effects = {name: evidence for name, evidence in effects.items() if evidence}
    return {"path": str(Path(path).absolute()), "sha256": digest(data), "bytes": len(data),
            "parser": "stdlib_ast_no_target_import" if python else "bounded_text_no_JS_execution",
            "definitions": tests, "definition_count": len(tests), "registrations": controls,
            "parametrizations": parametrized, "accepted_control_filter": allowed,
            "imports": imports, "effect_signals": effects,
            "effect_claim": "STATIC_LOWER_BOUND; mention may be mocked, imports/calls may hide effects",
            "execution_status": "NOT_RUN", "runtime_collection": "NOT_RUN_REQUIRES_EFFECT_ADMISSION",
            "safe_to_import": False, "admission": "NONE_FROM_COLLECTION"}

def collect(root):
    root = Path(root).absolute()
    need(root.is_dir() and not root.is_symlink(), "foreign_test_root")
    paths, pending = [], [root]
    visited_entries, visited_directories = 0, 0
    while pending:
        directory = pending.pop()
        visited_directories += 1
        need(visited_directories <= 256, "collection_directory_bound")
        need(not directory.is_symlink(), "symlink_collection_directory")
        with os.scandir(directory) as entries:
            for entry in entries:
                visited_entries += 1
                need(visited_entries <= 5000, "collection_visited_entry_bound")
                need(not entry.is_symlink(), "symlink_collection_entry")
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    need(visited_directories + len(pending) < 256, "collection_directory_bound")
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False) and path.suffix in (".py", ".js", ".mjs", ".cjs"):
                    need(len(paths) < 500, "collection_file_bound")
                    paths.append(path)
    need(paths, "empty_source_collection")
    paths.sort()
    rows = []
    for path in paths:
        row = classify(path)
        row["path"] = path.relative_to(root).as_posix()
        rows.append(row)
    return {"schema": "friday.static-source-catalog.v1", "scope": "SOURCE_PREPARATION_ONLY",
            "collection": "actual_files_and_AST_definitions_no_target_import",
            "files": rows, "counts": {"files": len(rows),
                "Python_test_definitions": sum(r["definition_count"] for r in rows),
                "literal_parameter_entries": sum(p["literal_cases"] or 0 for r in rows for p in r["parametrizations"]),
                "unresolved_parameterizations": sum(p["literal_cases"] is None for r in rows for p in r["parametrizations"])},
            "actual_runtime_collection": "NOT_RUN", "target_imports": 0,
            "source_gate_executed": False, "runtime_grant": False, "release_accepted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Explicit test source directory; no defaults to private state")
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.root), ensure_ascii=False, sort_keys=True))
    except (Refusal, SyntaxError, UnicodeError, OSError) as error:
        print(json.dumps({"status": "REFUSED", "cause": str(error), "runtime_grant": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
