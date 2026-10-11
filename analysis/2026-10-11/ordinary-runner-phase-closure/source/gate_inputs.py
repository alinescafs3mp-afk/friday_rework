#!/usr/bin/env python3
"""Exact source catalog/binding and known-checker relocation. No runtime grant.

Targets are parsed, never imported, while collecting. A binding only establishes
byte/receipt consistency. Observations and author controls need independent review.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "friday.final-source-binding.v1"
INPUT_SCHEMA = "friday.coherent-gate-input-preparation.v1"
INPUT_SHA = "04b0d223a56559e6520bfc18e32ce17807eca88849ce16ab446aa5d3053fec42"
BASE_SHA = "874abefca71903da21e9978462594d0d6da73fe7fa60322e29fb3f9e9fa6eced"
DELTA_SHA = "39b992393f03c21976ff86fef444adc320604b1646b5118ee23018ebb050cf6d"
PREDICATES_SHA = "e5342817a23fbe7ddfa292b1f36735b6df121078db0fbe4543bab4c67dafa52f"
MAX_FILE = 8 * 1024 * 1024
MAX_FILES = 20000
SHA = re.compile(r"^[0-9a-f]{64}$")
CHECKERS = {"onboard": "checks/onboard/check_selected_source.py",
            "cli": "checks/cli/check_cli_composed.py",
            "catalog": "checks/catalog/check_consumers.py"}
STOPS = {"G7": "NO_REPLAY", "G8": "PREPARED_NOT_EXECUTED",
         "kernel120": "NOT_GRANTED", "normal3600": "UNSTARTED",
         "oldFriday": "OFF", "Pandora": "OFF"}


class Refusal(ValueError):
    pass


def need(condition, cause):
    if not condition:
        raise Refusal(cause)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate_json_key:" + key)
        result[key] = value
    return result


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


def document(path):
    try:
        return json.loads(bytes_at(path), object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(Refusal("nonfinite_json")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Refusal("malformed_json:" + str(path)) from error


def ref(path):
    data = bytes_at(path)
    return {"path": str(Path(path).absolute()), "sha256": digest(data), "bytes": len(data)}


def check_ref(value, label="receipt"):
    need(isinstance(value, dict) and set(value) == {"path", "sha256", "bytes"},
         "invalid_ref_schema:" + label)
    need(isinstance(value["path"], str) and Path(value["path"]).is_absolute(), "invalid_ref_path:" + label)
    need(isinstance(value["sha256"], str) and SHA.fullmatch(value["sha256"]), "invalid_ref_sha:" + label)
    need(type(value["bytes"]) is int and 0 <= value["bytes"] <= MAX_FILE, "invalid_ref_size:" + label)
    data = bytes_at(value["path"])
    need(len(data) == value["bytes"] and digest(data) == value["sha256"], "changed_ref:" + label)
    # Parse exactly the verified buffer; do not reopen a changed JSON/source.
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(Refusal("nonfinite_json"))) if str(value["path"]).endswith(".json") else data


def input_document(path):
    need(digest(bytes_at(path)) == INPUT_SHA, "stale_preparation_inputs")
    value = document(path)
    need(value["schema"] == INPUT_SCHEMA, "preparation_schema")
    for name in ("parent_clock", "API_project_manifest", "native_inventory",
                 "composition_integrity_receipt", "API_source_acceptance",
                 "API_source_result", "accepted_exact108_dependency_receipt"):
        check_ref(value[name], name)
    need(value["native_files"] == 17649 and value["native_layers"] == 30, "native_topology_changed")
    for key, state in STOPS.items():
        need(value[key] == state, "retained_stop_changed:" + key)
    return value


def inventory(root, expected, require_frozen=False):
    need(isinstance(expected, dict) and 0 < len(expected) <= MAX_FILES, "inventory_schema")
    root = Path(root).absolute()
    need(root.is_dir() and not root.is_symlink(), "missing_or_foreign_source_root")
    if require_frozen:
        need(stat.S_IMODE(root.stat().st_mode) == 0o500, "final_source_directory_not_frozen")
    actual = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        need(not any((Path(directory) / d).is_symlink() for d in dirs), "source_symlink_directory")
        if require_frozen:
            need(stat.S_IMODE(Path(directory).stat().st_mode) == 0o500, "final_source_directory_not_frozen")
        for name in sorted(files):
            path = Path(directory) / name
            if require_frozen:
                need(stat.S_IMODE(path.stat().st_mode) == 0o400, "final_source_file_not_frozen")
            relative = path.relative_to(root).as_posix()
            actual[relative] = digest(bytes_at(path))
            need(len(actual) <= MAX_FILES, "inventory_file_limit")
    need(set(actual) == set(expected), "source_membership_changed")
    for name, value in expected.items():
        need(not Path(name).is_absolute() and ".." not in Path(name).parts, "escaping_inventory_path")
        wanted = value["sha256"] if isinstance(value, dict) else value
        need(isinstance(wanted, str) and SHA.fullmatch(wanted), "inventory_digest_schema")
        need(actual[name] == wanted, "source_bytes_changed:" + name)
    return actual


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


def definitions(inputs):
    base_path = Path(inputs["acceptance_plan"]).parent / "acceptance_matrix.json"
    product = Path(inputs["repo_test_root"]).parent
    delta_path = product / "validation/acceptance-web-admin.json"
    need(digest(bytes_at(base_path)) == BASE_SHA, "base_acceptance_changed")
    need(digest(bytes_at(delta_path)) == DELTA_SHA, "owner_acceptance_changed")
    pred = Path(inputs["master_directive"]).parent / "tools/validate_run_record.py"
    need(digest(bytes_at(pred)) == PREDICATES_SHA, "audited_predicates_changed")
    base, delta = document(base_path), document(delta_path)
    checks = {row["id"]: copy.deepcopy(row) for row in base["checks"]}
    need(set(checks) == {f"AC{i:03}" for i in range(1, 53)}, "base_acceptance_truncated")
    for override in delta["overrides"]:
        checks[override["id"]].update(override)
    for row in delta["checks"]:
        need(row["id"] not in checks, "duplicate_acceptance_check")
        checks[row["id"]] = copy.deepcopy(row)
    need(set(checks) == {f"AC{i:03}" for i in range(1, 59)}, "owner_acceptance_truncated")
    need(delta["worker_parameters"] == {"AC055": ["Harness", "A0"]}, "worker_parameters_weakened")
    for name in ["AC043", *(f"AC{i:03}" for i in range(53, 59))]:
        need(checks[name]["gate"] == "USEFUL" and checks[name]["critical"] is True, "mandatory_scope_weakened")
    rows = []
    for name, row in sorted(checks.items()):
        for worker in (["Harness", "A0"] if name == "AC055" else [None]):
            rows.append({"check_id": name, "worker": worker, "definition": row,
                         "status": "NOT_RUN", "cause": "NO_ACTUAL_FINAL_CANDIDATE_RUNTIME_EVIDENCE"})
    counts = {"FOUNDATION": 9, "USEFUL": 47, "DAILY": 56}
    need(sum(r["definition"]["gate"] in ("FOUNDATION", "USEFUL") for r in rows) == 47, "useful_count_changed")
    need(sum(r["definition"]["gate"] != "OPTIONAL" for r in rows) == 56, "daily_count_changed")
    return {"base": ref(base_path), "owner_delta": ref(delta_path), "audited_predicates": ref(pred),
            "record_validator": ref(product / "validation/validate_release_record.py"),
            "rows": rows, "cumulative_records": counts, "useful_unique_checks": 46,
            "seven_installed_journeys": {"required_count": 7, "status": "NOT_RUN",
                 "definition_binding": None, "cause": "REQUIRES_EXACT_AUTHORITY_JOURNEY_PLAN_AND_NORMAL_INSTALLED_EXECUTION"},
            "four_web_contexts": ["Hermes_autonomous", "Hermes_explicit_research", "Harness_mid_task", "A0_mid_task"],
            "record_checker_is_not_runtime_attestation": True}


def collect(inputs):
    root = Path(inputs["repo_test_root"])
    paths = sorted(p for p in root.iterdir() if p.is_file() and p.suffix in (".py", ".mjs", ".cjs"))
    need(0 < len(paths) <= 500, "test_file_collection_bounds")
    files = [classify(path) for path in paths]
    checker_files = [classify(Path(inputs["native_fixture_root"]) / name) for name in CHECKERS.values()]
    return {"schema": "friday.static-final-gate-catalog.v1", "main": inputs["main"],
            "collection": "actual_files_and_AST_definitions_no_import", "repo_files": files,
            "composition_checkers": checker_files, "acceptance": definitions(inputs),
            "summary": {"repo_files": len(files), "Python_test_definitions": sum(x["definition_count"] for x in files),
                        "literal_parametrize_cases": sum(x["literal_cases"] or 0 for f in files for x in f["parametrizations"]),
                        "unresolved_parametrizations": sum(x["literal_cases"] is None for f in files for x in f["parametrizations"]),
                        "accepted_composition_filter_controls": sum(len(x["accepted_control_filter"] or []) for x in checker_files)},
            "no_tests_executed": True, "native_imports": 0, "network_calls": 0,
            "runtime_grant": False, "all_controls_and_thresholds_retained_in_definition_bytes": True}


def coverage_preflight(catalog, evidence):
    """No omission/skip can turn the whole mandatory source slice green.

    This verifies declared coverage only; runtime collection and each observation
    must additionally receive independent review on the actual bound candidate.
    """
    need(isinstance(evidence, dict) and evidence.get("schema") == "friday.whole-source-coverage.v1", "coverage_schema")
    need(evidence.get("catalog_sha256") == digest(canonical(catalog)), "stale_coverage_catalog")
    need(evidence.get("independent_acceptance") is True and not evidence.get("AUTHOR_FIXTURE_ONLY"), "coverage_unaccepted")
    need(evidence.get("runtime_grant") is False, "coverage_cannot_mint_runtime_grant")
    rows = evidence.get("files")
    need(isinstance(rows, list), "coverage_file_schema")
    wanted = {row["path"]: row for row in catalog["repo_files"] + catalog["composition_checkers"]}
    need(len(rows) == len(wanted) and {row.get("path") for row in rows} == set(wanted), "mandatory_source_files_omitted_or_foreign")
    for row in rows:
        original = wanted[row["path"]]
        need(row.get("sha256") == original["sha256"], "stale_coverage_source")
        need(row.get("status") == "PASS" and row.get("skipped") == 0, "mandatory_source_scenario_not_run")
        need(row.get("definitions") == original["definitions"], "mandatory_test_definitions_omitted")
        need(row.get("registrations") == original["registrations"], "mandatory_checker_registrations_omitted")
        need(row.get("parametrizations") == original["parametrizations"], "mandatory_parametrization_changed")
        need(row.get("all_dynamic_registration_cases_executed") is True, "dynamic_registration_unresolved")
        need(isinstance(row.get("actual_collection"), dict), "actual_collection_receipt_missing")
        check_ref(row["actual_collection"], "independently_reviewed_actual_collection")
        need(isinstance(row.get("observations"), list) and row["observations"], "actual_source_observations_missing")
        for item in row["observations"]:
            check_ref(item, "source_observation")
    return {"status": "DECLARED_WHOLE_SOURCE_COVERAGE_COMPLETE_REVIEW_REQUIRED", "files": len(rows),
            "runtime_grant": False, "release_accepted": False,
            "seven_live_journeys": "NOT_RUN_SEPARATE_INSTALLED_EVIDENCE_REQUIRED"}


def source_preflight(inputs, binding, trusted_acceptance):
    """Exact binding against a separately supplied root-received trust anchor."""
    need(isinstance(binding, dict) and binding.get("schema") == SCHEMA, "binding_schema")
    fields = {"schema", "main", "preparation_inputs_sha256", "project_root", "project_manifest",
              "native_root", "native_inventory", "native_layers", "API_sha256", "CLI_source_manifest",
              "owner_output_acceptance", "candidate_source_acceptance", "binding_sha256", "retained_stops"}
    need(set(binding) == fields, "binding_fields")
    need(binding["main"] == inputs["main"], "stale_main")
    need(binding["preparation_inputs_sha256"] == INPUT_SHA, "stale_inputs_binding")
    need(binding["retained_stops"] == STOPS, "stop_policy_changed")
    unsigned = {k: v for k, v in binding.items() if k != "binding_sha256"}
    need(binding["binding_sha256"] == digest(canonical(unsigned)), "binding_digest_mismatch")
    need(binding["native_layers"] == 30, "native_topology_changed")
    native = check_ref(binding["native_inventory"], "native_inventory")
    base_native = check_ref(inputs["native_inventory"], "accepted_native_base_inventory")
    need(len(base_native["files"]) == 17649, "native_base_file_count")
    project = check_ref(binding["project_manifest"], "final_project_manifest")
    inventory(binding["project_root"], project, require_frozen=True)
    original = check_ref(inputs["API_project_manifest"], "accepted_API_project_manifest")
    api_name = "plugins/friday_rework/dashboard/api.py"
    need(binding["API_sha256"] == original[api_name] == project.get(api_name), "stale_API")
    cli = check_ref(binding["CLI_source_manifest"], "CLI_source_manifest")
    need(isinstance(cli, dict) and cli.get("schema") == "friday.owner-output-final-source.v1", "CLI_manifest_schema")
    need(cli.get("assignment") == "FRW-ORDINARY-CLI-OWNER-OUTPUT-PATH-SOL" and cli.get("generation") == 1,
         "foreign_CLI_assignment")
    need(cli.get("status") == "INDEPENDENT_SOURCE_ACCEPTED" and cli.get("whole_owner_output_path") is True,
         "unaccepted_owner_output")
    need(isinstance(cli.get("project_changes"), dict) and isinstance(cli.get("native_changes"), dict), "CLI_changes_schema")
    # Explicit accepted CLI delta overlays the frozen base; unchanged base bytes
    # and metadata cannot silently acquire a new expected identity.
    desired_native = {name: row["sha256"] for name, row in base_native["files"].items()}
    for name, wanted in cli["native_changes"].items():
        need(isinstance(wanted, str) and SHA.fullmatch(wanted), "CLI_native_delta_digest")
        desired_native[name] = wanted
    need(set(native["files"]) == set(desired_native), "native_membership_not_accepted")
    for name, wanted in desired_native.items():
        row = native["files"][name]
        need((row["sha256"] if isinstance(row, dict) else row) == wanted, "stale_or_foreign_native:" + name)
    for key in ("commit", "base_tree"):
        need(native.get(key) == base_native.get(key), "native_donor_identity_changed")
    if not cli["native_changes"]:
        need(binding["native_inventory"] == inputs["native_inventory"]
             and binding["native_root"] == inputs["native_root"], "foreign_unchanged_native")
    need(set(project) == set(original) | set(cli["project_changes"]), "project_membership_not_accepted")
    for name, wanted in original.items():
        need(project[name] == cli["project_changes"].get(name, wanted), "stale_or_foreign_project:" + name)
    for name, wanted in cli["project_changes"].items():
        need(project.get(name) == wanted, "stale_CLI:" + name)
    owner = check_ref(binding["owner_output_acceptance"], "owner_output_acceptance")
    need(owner.get("independent_acceptance") is True and owner.get("source_accepted") is True
         and owner.get("runtime_grant") is False, "owner_receipt_not_independent_source_acceptance")
    need(owner.get("CLI_source_manifest") == binding["CLI_source_manifest"], "stale_owner_acceptance")
    need(binding["candidate_source_acceptance"] == trusted_acceptance, "foreign_acceptance_anchor")
    acceptance = check_ref(trusted_acceptance, "trusted_candidate_source_acceptance")
    need(acceptance.get("schema") == "friday.final-source-acceptance-root-received.v1", "acceptance_schema")
    need(acceptance.get("independent_acceptance") is True and acceptance.get("source_accepted") is True
         and acceptance.get("runtime_grant") is False, "unaccepted_candidate")
    need(acceptance.get("project_manifest") == binding["project_manifest"]
         and acceptance.get("native_inventory") == binding["native_inventory"]
         and acceptance.get("owner_output_acceptance") == binding["owner_output_acceptance"], "stale_final_acceptance")
    need(not any(row.get("AUTHOR_FIXTURE_ONLY") for row in (cli, owner, acceptance)), "author_fixture_not_authority")
    inventory(binding["native_root"], native["files"], require_frozen=True)
    return {"status": "EXACT_ACCEPTED_SOURCE_READY", "binding_sha256": binding["binding_sha256"],
            "project_files": len(project), "native_files": len(desired_native), "runtime_grant": False,
            "full_gate": "NOT_RUN_SEPARATE_EXECUTION_ADMISSION_REQUIRED"}


def normalized_ast(source, replacements):
    tree = ast.parse(source)
    class Normalize(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and node.value in replacements:
                return ast.copy_location(ast.Constant(replacements[node.value]), node)
            return node
    return ast.dump(Normalize().visit(tree), include_attributes=False)


def relocate_checker(source, replacements, expanded=False):
    """Replace exact known absolute string literals only; all other bytes stay."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line.encode("utf-8"))
    data, edits = source.encode("utf-8"), []
    selector_edit = None
    if expanded:
        target = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "test")
        guard = target.body[0]
        need(isinstance(guard, ast.If) and ast.dump(guard.test) == ast.dump(ast.parse("name not in ALLOWED", mode="eval").body),
             "unknown_checker_selector")
        need(ast.get_source_segment(source, guard) == "if name not in ALLOWED:SKIPPED.append(name);return", "selector_body_changed")
        start = offsets[guard.lineno - 1]
        end = offsets[guard.end_lineno - 1] + len(lines[guard.end_lineno - 1].encode("utf-8"))
        selector_edit = (start, end, b"", None)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in replacements:
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            edits.append((start, end, repr(replacements[node.value]).encode("utf-8"), node.value))
    need(edits, "no_known_checker_roots")
    for start, end, replacement, old in sorted(edits + ([selector_edit] if selector_edit else []), reverse=True):
        data = data[:start] + replacement + data[end:]
    moved = data.decode("utf-8")
    if expanded:
        target = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "test")
        target.body.pop(0)
        source_for_compare = ast.unparse(tree)
    else:
        source_for_compare = source
    # Multiple old roots can map to one current root: forward normalization is exact.
    need(normalized_ast(source_for_compare, replacements) == ast.dump(ast.parse(moved), include_attributes=False),
         "relocation_changed_checker_body")
    return moved, [{"old": old, "new": replacements[old]} for _, _, _, old in edits]


def relocate(inputs, binding, destination, trusted_acceptance):
    preflight = source_preflight(inputs, binding, trusted_acceptance)
    dest = Path(destination).absolute()
    need(not dest.exists(), "relocation_output_exists")
    old = Path(inputs["native_fixture_root"])
    legacy = old.parent / "ordinary-cli-tui-onboarding-integration"
    # BASE is a genuine historical comparison fixture, never current SRC.
    # Preserve its original path and hash the exact selected BASE dependencies.
    dest.mkdir(parents=True, mode=0o700)
    records = []
    for key, relative in CHECKERS.items():
        original_path = old / relative
        target_dir = dest / key
        target_dir.mkdir(mode=0o700)
        replacements = {str(old): str(dest), str(old / "candidate"): binding["project_root"],
                        str(old / "hermes"): binding["native_root"],
                        str(legacy / "candidate"): binding["project_root"]}
        source = bytes_at(original_path).decode("utf-8")
        moved, edits = relocate_checker(source, replacements)
        target = target_dir / original_path.name
        target.write_text(moved, encoding="utf-8")
        before, after = classify(original_path), classify(target)
        need(before["definitions"] == after["definitions"] and before["registrations"] == after["registrations"]
             and before["parametrizations"] == after["parametrizations"]
             and before["accepted_control_filter"] == after["accepted_control_filter"], "relocation_collection_changed")
        records.append({"kind": key, "before": ref(original_path), "after": ref(target),
                        "root_edits": edits, "normalized_AST_equal": True,
                        "collection_equal": True, "thresholds_and_bodies_equal": True,
                        "before_collection": before, "after_collection": after,
                        "execution": "NOT_RUN", "independent_relocation_acceptance": "PENDING"})
        expanded, _ = relocate_checker(source, replacements, expanded=True)
        expanded_target = target_dir / ("expanded_" + original_path.name)
        expanded_target.write_text(expanded, encoding="utf-8")
        # Every static call remains; dynamic parametrized names retain their
        # original loops. Execution/coverage still requires a reviewed adapter.
        after_expanded = classify(expanded_target)
        need([r["name_expression"] for r in before["registrations"]] ==
             [r["name_expression"] for r in after_expanded["registrations"]], "expanded_registration_omission")
        records[-1]["expanded"] = {"ref": ref(expanded_target), "all_registration_expressions_retained": True,
             "normalized_body_AST_equal_except_exact_selector": True,
             "selector_delta": "Remove only exact ALLOWED guard; no scenario/threshold/negative change",
             "coverage": "NOT_READY_PENDING_EFFECT_REVIEW_AND_REQUIRED_AUXILIARY_INPUTS",
             "execution": "NOT_RUN"}
    report = {"schema": "friday.known-checker-relocation.v1", "binding_sha256": binding["binding_sha256"],
              "preflight": preflight, "checkers": records, "source_runtime_grant": False,
              "historical_BASE_unchanged": str(legacy / "hermes"),
              "limitation": "30 accepted filtered controls only; full main suite and live journeys remain separate"}
    (dest / "RELOCATION.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def runtime_admission(*args, **kwargs):
    raise Refusal("runtime_requires_genuine_existing_native_grant_exclusive_slot_original_budget;source_receipt_is_not_a_grant")


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("catalog", "preflight", "relocate", "runtime-admission", "coverage"))
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--trusted-acceptance", type=Path,
                        help="Operator-provided exact path/bytes/SHA root-received trust anchor, never author result")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--coverage", type=Path)
    args = parser.parse_args()
    try:
        inputs = input_document(args.inputs)
        if args.phase == "catalog":
            result = collect(inputs)
        elif args.phase == "runtime-admission":
            runtime_admission()
        elif args.phase == "coverage":
            need(args.catalog is not None and args.coverage is not None, "missing_catalog_or_coverage")
            recorded = document(args.catalog)
            need(recorded == collect(inputs), "changed_actual_collection")
            result = coverage_preflight(recorded, document(args.coverage))
        else:
            need(args.binding is not None and args.trusted_acceptance is not None, "missing_final_binding_or_acceptance")
            binding, anchor = document(args.binding), document(args.trusted_acceptance)
            if args.phase == "preflight":
                result = source_preflight(inputs, binding, anchor)
            else:
                result = relocate(inputs, binding, args.output, anchor)
                print(json.dumps({"status": "SOURCE_RELOCATED_NOT_EXECUTED", "checkers": len(result["checkers"])}))
                return 0
        dump(args.output, result)
        print(json.dumps({"status": result.get("status", "STATIC_CATALOG_BUILT"), "runtime_grant": False}))
        return 0
    except (Refusal, KeyError, TypeError, OSError, SyntaxError) as error:
        result = {"status": "NOT_RUN", "cause": str(error), "runtime_grant": False, "full_gate_started": False}
        dump(args.output, result)
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
