#!/usr/bin/env python3
"""Check cumulative release-record completeness and bytes, never runtime truth.

The immutable V2 archive supplies the existing candidate/schema predicates.
This consumer adds the pinned owner delta and separate AC055 worker records.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types

ARCHIVE_NAME = "Friday_rework_Astra_Sol_Directive_V2_2026-10-06"
BASE_SHA256 = "874abefca71903da21e9978462594d0d6da73fe7fa60322e29fb3f9e9fa6eced"
DELTA_SHA256 = "39b992393f03c21976ff86fef444adc320604b1646b5118ee23018ebb050cf6d"
PREDICATES_SHA256 = "e5342817a23fbe7ddfa292b1f36735b6df121078db0fbe4543bab4c67dafa52f"
MANDATORY = frozenset(["AC043", *(f"AC{i:03}" for i in range(53, 59))])
WORKERS = ("Harness", "A0")
MAX_JSON_BYTES = 8 * 1024 * 1024
ROW_FIELDS = frozenset(("check_id", "status", "executor", "started_at_utc",
                        "finished_at_utc", "actions_performed", "observed",
                        "expected_comparison", "evidence", "native_identity",
                        "applicability_reason", "scope_decision_reference", "candidate_sha256"))


def open_directory(path, identities=None):
    """Open every directory component without following a symlink."""
    path = Path(os.path.abspath(path.expanduser()))
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        if identities is not None:
            metadata = os.fstat(fd)
            identities.append((metadata.st_dev, metadata.st_ino))
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                          | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = new
            if identities is not None:
                metadata = os.fstat(fd)
                identities.append((metadata.st_dev, metadata.st_ino))
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_parent(root, parts):
    """Return one parent FD and the identities of its complete directory path."""
    identities = []
    directory = open_directory(root, identities)
    try:
        for part in parts:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                          | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = new
            metadata = os.fstat(directory)
            identities.append((metadata.st_dev, metadata.st_ino))
        return directory, identities
    except BaseException:
        os.close(directory)
        raise


def file_bytes(root, relative, max_bytes=None):
    """Hash/read one regular file through the same contained NOFOLLOW FD."""
    if (not isinstance(relative, str) or not relative or relative in (".", "..")
            or "\\" in relative or any(ord(c) < 32 for c in relative)
            or re.match(r"^[A-Za-z]:", relative)):
        raise ValueError("relative contained path required")
    parts = relative.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("relative contained path required")
    directory, ancestors = open_parent(root, parts[:-1])
    fd = None
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("regular file required")
        if max_bytes is not None and before.st_size > max_bytes:
            raise ValueError("file exceeds read bound")
        digest, size, chunks = hashlib.sha256(), 0, [] if max_bytes is not None else None
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise ValueError("file exceeds read bound")
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        after = os.fstat(fd)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size,
                           s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
        # A leaf stat through the old FD cannot detect a moved parent/root.
        # Reopen the complete current path without following any symlink and
        # compare every directory identity as well as the still-linked leaf.
        current, current_ancestors = open_parent(root, parts[:-1])
        try:
            linked = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if (ancestors != current_ancestors or stamp(before) != stamp(after)
                    or stamp(after) != stamp(linked) or size != after.st_size):
                raise ValueError("file or containing path changed during read")
        finally:
            os.close(current)
        return digest.hexdigest(), size, (after.st_dev, after.st_ino), (
            b"".join(chunks) if chunks is not None else None)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def read_bytes(path):
    return file_bytes(path.parent, path.name, MAX_JSON_BYTES)[3]


def pinned_bytes(path, expected):
    data = read_bytes(path)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("immutable input SHA-256 mismatch: " + path.name)
    return data


def load_predicates(base_root):
    source = pinned_bytes(base_root / "tools/validate_run_record.py", PREDICATES_SHA256)
    module = types.ModuleType("audited_v2_record_predicates")
    module.__file__ = str(base_root / "tools/validate_run_record.py")
    # Exact pinned archive bytes; its guarded CLI is not executed or rewritten.
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def parse_json(data, inherited):
    return json.loads(data, object_pairs_hook=inherited.unique_object,
                      parse_constant=inherited.reject_constant)


def definitions(base_root, product_root, inherited):
    matrix = parse_json(pinned_bytes(base_root / "validation/acceptance_matrix.json",
                                     BASE_SHA256), inherited)
    delta = parse_json(pinned_bytes(product_root / "validation/acceptance-web-admin.json",
                                    DELTA_SHA256), inherited)
    errors = []
    result = inherited.matrix_definitions(matrix, errors)
    if errors:
        raise ValueError("invalid inherited base: " + "; ".join(errors))
    if (set(result) != {f"AC{i:03}" for i in range(1, 53)}
            or delta["base"]["sha256"] != BASE_SHA256
            or delta["worker_parameters"] != {"AC055": list(WORKERS)}):
        raise ValueError("base/delta schema ambiguity")
    for override in delta["overrides"]:
        result[override["id"]] = {**result[override["id"]], **override}
    for row in delta["checks"]:
        if row["id"] in result:
            raise ValueError("duplicate delta definition")
        result[row["id"]] = row
    if any(result[i]["gate"] != "USEFUL" or result[i]["critical"] is not True
           for i in MANDATORY):
        raise ValueError("mandatory owner scope weakened")
    return result


def evidence_check(entry, root, prefix, errors, inherited):
    if not isinstance(entry, dict):
        errors.append(prefix + ": evidence entry is not an object")
        return None
    if set(entry) != {"path", "bytes", "sha256"}:
        errors.append(prefix + ": evidence entry needs exactly path/bytes/sha256")
        return None
    size, expected = entry["bytes"], entry["sha256"]
    if type(size) is not int or size < 0:
        errors.append(prefix + ": evidence bytes must be a nonnegative integer")
        return None
    if not isinstance(expected, str) or not inherited.SHA64.fullmatch(expected):
        errors.append(prefix + ": invalid evidence SHA-256")
        return None
    try:
        digest, observed, identity, _ = file_bytes(root, entry["path"])
        if observed != size:
            errors.append(prefix + ": evidence byte count mismatch")
        if digest != expected:
            errors.append(prefix + ": evidence hash mismatch")
        return identity
    except (OSError, ValueError, RuntimeError, TypeError):
        errors.append(prefix + ": evidence unavailable, altered, escaping or symlinked")
        return None


def validate_row(row, key, required, allowed_na, root, inherited, errors):
    """Retain V2 status, actions, time, evidence and reviewed-exception rules."""
    ident, _worker = key
    prefix = ident + (":" + _worker if _worker else "")
    state = row.get("status")
    if not isinstance(state, str) or state not in inherited.STATUSES:
        errors.append(prefix + ": unsupported status")
        return "INVALID", False, set()
    for field in ("executor", "started_at_utc", "finished_at_utc", "observed",
                  "expected_comparison", "applicability_reason", "scope_decision_reference"):
        if row.get(field) is not None and not isinstance(row[field], str):
            errors.append(prefix + ": " + field + " must be a string or null")
    if "native_identity" in row and not isinstance(row["native_identity"], dict):
        errors.append(prefix + ": native_identity must be an object")
    actions = row.get("actions_performed", [])
    if not isinstance(actions, list) or not all(inherited.nonempty(x) for x in actions):
        errors.append(prefix + ": actions_performed must be a string array")
    evidence = row.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append(prefix + ": evidence must be an array")
        evidence = []
    identities = set()
    for entry in evidence:
        identity = evidence_check(entry, root, prefix, errors, inherited)
        if identity is not None:
            identities.add(identity)
    bound = state == "PASS"
    if state == "PASS":
        for field in ("executor", "observed", "expected_comparison"):
            if not inherited.nonempty(row.get(field)):
                errors.append(prefix + ": missing " + field)
        if not inherited.strings(actions):
            errors.append(prefix + ": actual actions/commands required")
        start = inherited.utc_time(row.get("started_at_utc"))
        end = inherited.utc_time(row.get("finished_at_utc"))
        if start is None or end is None or end < start:
            errors.append(prefix + ": valid ordered UTC start/end required")
        if not evidence:
            errors.append(prefix + ": PASS needs actual evidence files")
    elif state == "NOT_APPLICABLE":
        if ident in MANDATORY:
            errors.append(prefix + ": mandatory owner web/admin scope has no applicability exception")
        elif key in required or ident in allowed_na:
            bound = True
            if ident not in allowed_na:
                errors.append(prefix + ": required check needs an explicit reviewed applicability exception")
            if (not inherited.nonempty(row.get("applicability_reason"))
                    or not inherited.nonempty(row.get("scope_decision_reference")) or not evidence):
                errors.append(prefix + ": applicability reason, scope decision reference and evidence required")
    return state, bound, identities


def failure(target, error):
    return 2, {"record_check": "FAILED", "target": target,
               "declared_target_satisfied": False, "attests_runtime_truth": False,
               "review_required": True, "errors": [str(error)]}


def validate(args):
    try:
        inherited = load_predicates(args.base_root)
        checks = definitions(args.base_root, args.product_root, inherited)
        document = parse_json(read_bytes(args.record), inherited)
        if not isinstance(document, dict) or not isinstance(document.get("records"), list):
            raise ValueError("record object and records array required")
        evidence_root = args.evidence_root or args.record.parent
        fd = open_directory(evidence_root)
        os.close(fd)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, RecursionError) as exc:
        return failure(args.target, "Unreadable or invalid pinned definition/record/root: " + str(exc))
    required_checks = {i for i, row in checks.items() if row["gate"] != "OPTIONAL"
                       and inherited.GATE_ORDER[row["gate"]] <= inherited.GATE_ORDER[args.target]}
    errors = []
    for ident in args.require_optional:
        if ident not in checks or checks[ident]["gate"] != "OPTIONAL":
            errors.append("Not a known optional check: " + ident)
        else:
            required_checks.add(ident)
    allowed_na = set(args.allow_not_applicable)
    if allowed_na - checks.keys():
        errors.append("Unknown NOT_APPLICABLE exception ID")
    if allowed_na & MANDATORY:
        errors.append("Mandatory owner web/admin scope cannot be excepted: "
                      + ", ".join(sorted(allowed_na & MANDATORY)))
    required = {(i, worker) for i in required_checks
                for worker in (WORKERS if i == "AC055" else (None,))}
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        errors.append("Record schema_version must be integer 1")
    if document.get("kind") != "runtime_acceptance_record":
        errors.append("Wrong record kind")
    if document.get("template") is not False:
        errors.append("Unfilled template is not an executed acceptance record")
    if document.get("acceptance_definition") != {
            "base_sha256": BASE_SHA256, "web_admin_sha256": DELTA_SHA256}:
        errors.append("Record acceptance_definition must bind exact cumulative base/delta SHA-256")
    rows, states, bound, evidence_ids = {}, {}, [], {}
    for index, row in enumerate(document["records"]):
        if not isinstance(row, dict):
            errors.append(f"Record row {index + 1}: object required")
            continue
        ident = row.get("check_id")
        if not isinstance(ident, str) or ident not in checks:
            errors.append(f"Record row {index + 1}: known string check_id required")
            continue
        worker = row.get("worker")
        unknown = row.keys() - (ROW_FIELDS | ({"worker"} if ident == "AC055" else set()))
        if unknown:
            errors.append(ident + ": unknown record fields: " + ", ".join(sorted(unknown)))
            continue
        if ident == "AC055":
            if not isinstance(worker, str) or worker not in WORKERS:
                errors.append("AC055: exactly one known worker Harness or A0 required per record")
                continue
        elif "worker" in row:
            errors.append(ident + ": worker discriminator is only supported on AC055")
            continue
        key = (ident, worker)
        if key in rows:
            errors.append("Duplicate record check/worker ID: " + ident + (":" + worker if worker else ""))
            continue
        rows[key] = row
        states[key], is_bound, evidence_ids[key] = validate_row(
            row, key, required, allowed_na, evidence_root, inherited, errors)
        if is_bound:
            bound.append((key, row))
    candidate = document.get("candidate")
    fingerprint = inherited.validate_candidate(candidate, errors) if bound else None
    for key, row in bound:
        value = row.get("candidate_sha256")
        if not isinstance(value, str) or not inherited.SHA64.fullmatch(value):
            errors.append(key[0] + ": candidate_sha256 required for PASS/approved NOT_APPLICABLE")
        elif fingerprint is not None and value != fingerprint:
            errors.append(key[0] + ": candidate_sha256 differs from the current candidate; stale evidence")
    harness, a0 = ("AC055", "Harness"), ("AC055", "A0")
    if states.get(harness) == states.get(a0) == "PASS":
        if (not evidence_ids[harness] - evidence_ids[a0]
                or not evidence_ids[a0] - evidence_ids[harness]):
            errors.append("AC055: each worker needs separate evidence files; shared paths/hardlinks alone cannot pass")
    label = lambda key: key[0] + (":" + key[1] if key[1] else "")
    missing = sorted(label(k) for k in required - rows.keys())
    if missing:
        errors.append("Missing required check records: " + ", ".join(missing))
    unresolved = sorted(label(k) for k in required if states.get(k) not in ("PASS", "NOT_APPLICABLE"))
    satisfied = not errors and not unresolved
    report = {
        "record_check": "VALID" if not errors else "FAILED", "target": args.target,
        "required_count": len(required), "required_check_count": len(required_checks),
        "required_status_counts": dict(sorted(Counter(states.get(k, "MISSING") for k in required).items())),
        "declared_target_satisfied": satisfied, "unresolved_required_checks": unresolved,
        "candidate_sha256": fingerprint,
        "deployment_scope": candidate.get("deployment_scope") if fingerprint else None,
        "acceptance_definition": {"base_sha256": BASE_SHA256, "web_admin_sha256": DELTA_SHA256},
        "attests_runtime_truth": False, "review_required": True,
        "note": "Record completeness, candidate association and referenced bytes only. "
                "Synthetic fixtures do not establish any runtime journey. Astra independently reviews "
                "actual observations, deployment authorization and the seven installed/four web journeys. "
                "Staging records do not establish production readiness.",
        "errors": errors,
    }
    return (0 if satisfied else 1), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--base-root", "--pack-root", type=Path,
                        default=Path(__file__).resolve().parents[2] / ARCHIVE_NAME)
    parser.add_argument("--product-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--target", choices=("FOUNDATION", "USEFUL", "DAILY"), default="USEFUL")
    parser.add_argument("--require-optional", action="append", default=[], metavar="AC_ID")
    parser.add_argument("--allow-not-applicable", action="append", default=[], metavar="AC_ID")
    args = parser.parse_args(argv)
    code, report = validate(args)
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
