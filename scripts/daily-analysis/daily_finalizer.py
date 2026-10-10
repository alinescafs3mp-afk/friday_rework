#!/usr/bin/env python3
"""Inventory an explicit Git period; never publish, execute source, or accept runtime.

Stdlib only. Output is created exclusively after validation. An existing output
path (including a symlink) is refused. Git reads use immutable full commit IDs.
"""
import argparse
import hashlib
import json
import os
import posixpath
import re
import resource
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

STAGE = "PROVISIONAL_NOT_DAILY_COMPLETE"
MSK = ZoneInfo("Europe/Moscow")
ROOTS = ("analysis/", "docs/", "scripts/", "tests/", "validation/")
HEX = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


class Refusal(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


class Git:
    def __init__(self, repo):
        self.repo = Path(repo).resolve(strict=True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
                        GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        LC_ALL="C")
        self.deadline = time.monotonic() + 890
        self.cache = {}
        self.calls = 0

    def run(self, *args, data=None):
        self.calls += 1
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Refusal("time budget exhausted")
        proc = subprocess.run(["git", "--no-optional-locks", "-C", str(self.repo),
                               *args], input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=self.env,
                              timeout=min(remaining, 60), check=False)
        if proc.returncode:
            # Do not copy local paths or arbitrary Git stderr into public output.
            raise Refusal("Git read failed: " + args[0])
        return proc.stdout

    def commit(self, oid):
        if not HEX.fullmatch(oid):
            raise Refusal("base/end must be full lowercase commit IDs")
        if self.run("cat-file", "-t", oid).strip() != b"commit":
            raise Refusal("base/end must name commit objects")

    def tree(self, oid):
        result = {}
        for raw in self.run("ls-tree", "-r", "-z", oid).split(b"\0"):
            if not raw:
                continue
            header, path = raw.split(b"\t", 1)
            mode, kind, obj = header.decode("ascii").split()
            result[path.decode("utf-8")] = {"mode": mode, "type": kind, "git_blob": obj}
        return result

    def blobs(self, oids):
        missing = sorted(set(oids) - self.cache.keys())
        if not missing:
            return
        data = self.run("cat-file", "--batch", data=("\n".join(missing) + "\n").encode())
        cursor = 0
        for oid in missing:
            eol = data.index(b"\n", cursor)
            header = data[cursor:eol].decode("ascii").split()
            if len(header) != 3 or header[:2] != [oid, "blob"]:
                raise Refusal("expected available blob in batch")
            size = int(header[2]); cursor = eol + 1
            payload = data[cursor:cursor + size]
            if len(payload) != size or data[cursor + size:cursor + size + 1] != b"\n":
                raise Refusal("invalid Git batch framing")
            self.cache[oid] = payload
            cursor += size + 1
        if cursor != len(data):
            raise Refusal("trailing Git batch data")

    def diff(self, before, after):
        flags = ("--raw", "-z", "--no-abbrev", "--no-renames", "--no-ext-diff", "--no-textconv", "--no-relative", "--no-color")
        raw = self.run("diff", *flags, before, after) if before else self.run(
            "diff-tree", "--root", "--no-commit-id", "-r", *flags, after)
        parts = raw.split(b"\0"); rows = []
        for i in range(0, len(parts) - 1, 2):
            fields = parts[i].decode("ascii").split()
            if len(fields) != 5 or not fields[0].startswith(":"):
                raise Refusal("invalid Git raw diff framing")
            oldmode, newmode, oldoid, newoid, status = fields
            row = {"status": status, "path": parts[i + 1].decode("utf-8")}
            for key, mode, oid in (("before", oldmode[1:], oldoid), ("after", newmode, newoid)):
                if mode != "000000":
                    row[key] = {"mode": mode, "type": "commit" if mode == "160000" else "blob",
                                "git_blob": oid}
            rows.append(row)
        return rows


def walk(value, trail=()):
    if isinstance(value, dict):
        yield trail, value
        for key, child in value.items():
            yield from walk(child, trail + (str(key),))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk(child, trail + (str(i),))


def historical_daily_path(obj, trail):
    """These fields bind a report's earlier commit range, not the current tree."""
    return (isinstance(obj, dict)
            and obj.get("schema") == "friday.analysis.daily-period-index.v1"
            and bool(trail)
            and trail[0] in {"ordered_commits", "changed_paths", "net_changed_paths",
                             "logical_blocks", "intermediate_only_paths", "publication_gaps"})


def pointer(trail):
    return "/" + "/".join(s.replace("~", "~0").replace("/", "~1") for s in trail)


def resolve(source, target, link=False):
    if link:
        target = unquote(urlsplit(target).path)
    if not target or target.startswith("/") or "\\" in target:
        return None
    result = posixpath.normpath(target if target.startswith(ROOTS) else
                               posixpath.join(posixpath.dirname(source), target))
    return None if result == ".." or result.startswith("../") else result


def package(path):
    if path.startswith("analysis/"):
        return "/".join(path.split("/")[:3])
    return "product/" + path.split("/", 1)[0]


def directory_prefix(path):
    directory = posixpath.dirname(path)
    return directory + "/" if directory else ""


def verify_public(git, tree, touched):
    def exists(path):
        return path is not None and (path in tree or any(p.startswith(path.rstrip("/") + "/") for p in tree))

    # A payload edit must also check its unchanged enclosing package manifest.
    scope = {p for p in touched if p in tree}
    scope.update(p for p in tree if posixpath.basename(p) == "MANIFEST.json" and
                 any(t.startswith(directory_prefix(p)) for t in touched))
    candidates = {p for p in scope if p.endswith((".json", ".md")) and tree[p]["type"] == "blob"}
    git.blobs(tree[p]["git_blob"] for p in candidates)
    jsons = {}; errors = []; gaps = []; manifests = []; refs = []; links = []; jlinks = []
    def content(path):
        oid = tree[path]["git_blob"]; git.blobs([oid]); return git.cache[oid]

    for p in sorted(candidates):
        if not p.endswith(".json"):
            continue
        try:
            jsons[p] = json.loads(content(p))
        except (ValueError, UnicodeError):
            errors.append({"kind": "INVALID_JSON", "path": p})

    assertions = []
    for p, obj in jsons.items():
        if posixpath.basename(p) != "MANIFEST.json":
            continue
        if isinstance(obj, dict) and isinstance(obj.get("files"), list):
            entries = obj["files"]
        elif isinstance(obj, dict) and obj and all(isinstance(v, dict) and "sha256" in v for v in obj.values()):
            entries = [dict(v, path=k) for k, v in obj.items()]
        else:
            errors.append({"kind": "UNSUPPORTED_MANIFEST_SCHEMA", "path": p}); continue
        seen = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("path", entry.get("file")), str):
                errors.append({"kind": "INVALID_MANIFEST_ENTRY", "path": p, "entry": i}); continue
            target = resolve(p, entry.get("path", entry.get("file")))
            seen.append(target)
            assertions.append({"source": p, "target": target, "expected_sha256": entry.get("sha256"),
                               "expected_bytes": entry.get("bytes"), "kind": "MANIFEST"})
        payloads = {t for t in tree if t.startswith(directory_prefix(p))} - {p}
        unlisted = sorted(payloads - set(seen)); extra = sorted(set(seen) - payloads, key=str)
        row = {"path": p, "entries": len(entries), "unlisted_files": unlisted, "extra_files": extra,
               "duplicate_entries": len(seen) - len(set(seen))}
        manifests.append(row)
        if unlisted or extra or row["duplicate_entries"]:
            errors.append({"kind": "MANIFEST_COVERAGE", **row})

    skipped = 0
    for p, obj in jsons.items():
        if posixpath.basename(p) == "MANIFEST.json":
            continue
        daily_index = (isinstance(obj, dict)
                       and obj.get("schema") == "friday.analysis.daily-period-index.v1")
        if daily_index:
            artifact = obj.get("integrity_artifact")
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
                errors.append({"kind": "INVALID_DAILY_INTEGRITY_REFERENCE", "path": p})
            else:
                assertions.append({"source": p, "json_pointer": "/integrity_artifact",
                                   "target": resolve(p, artifact["path"]),
                                   "expected_sha256": artifact.get("sha256"),
                                   "expected_bytes": artifact.get("bytes"),
                                   "kind": "PUBLIC_REFERENCE"})
        for trail, item in walk(obj):
            if daily_index and trail and trail[0] == "integrity_artifact":
                continue
            if historical_daily_path(obj, trail):
                skipped += 1
                continue
            hkey = next((k for k in ("public_sha256", "published_sha256", "transformed_sha256") if k in item), None)
            if not hkey and "sha256" in item and any(k in item for k in ("path", "public_file", "public_path", "repository_file")):
                hkey = "sha256"
            if not hkey:
                continue
            value = next((item[k] for k in ("repository_file", "public_file", "public_path", "file", "path")
                          if isinstance(item.get(k), str)), None)
            if not value or value.startswith(("/", "<")) or "<" in value:
                skipped += 1; continue
            target = resolve(p, value)
            if hkey == "sha256" and not exists(target) and not any(k in "/".join(trail).lower() for k in ("public", "analysis", "reference")):
                skipped += 1; continue
            nkey = next((k for k in ("public_bytes", "published_bytes", "transformed_bytes", "bytes") if k in item), None)
            assertions.append({"source": p, "json_pointer": pointer(trail), "target": target,
                               "expected_sha256": item[hkey], "expected_bytes": item.get(nkey),
                               "kind": "PUBLIC_REFERENCE"})
    git.blobs(tree[r["target"]]["git_blob"] for r in assertions
              if r["target"] in tree and tree[r["target"]]["type"] == "blob")
    for row in assertions:
        expected = row["expected_sha256"]; size = row["expected_bytes"]; target = row["target"]
        if not isinstance(expected, str) or not HASH.fullmatch(expected) or (size is not None and (type(size) is not int or size < 0)):
            row["status"] = "INVALID_ASSERTION"
        elif target not in tree or tree[target]["type"] != "blob":
            row["status"] = "MISSING"
        else:
            b = content(target); row.update(actual_sha256=digest(b), actual_bytes=len(b))
            row["status"] = "PASS" if digest(b) == expected and (size is None or size == len(b)) else "MISMATCH"
        refs.append(row)
        if row["status"] != "PASS":
            errors.append({**row, "kind": row["kind"] + "_" + row["status"]})
    for p in sorted(candidates):
        if not p.endswith(".md"):
            continue
        try:
            text = content(p).decode("utf-8")
        except UnicodeError:
            errors.append({"kind": "INVALID_MARKDOWN_UTF8", "path": p}); continue
        for match in re.finditer(r"\[[^\]\n]*\]\(([^\)\n]+)\)", text):
            value = match.group(1).split()[0].strip("<>")
            if urlsplit(value).scheme or value.startswith(("#", "//")):
                continue
            target = resolve(p, value, link=True)
            row = {"source": p, "target": target, "status": "PASS" if exists(target) else "MISSING"}
            links.append(row)
            if row["status"] != "PASS":
                gaps.append({"kind": "MARKDOWN_LINK_MISSING", **row})
    for p, obj in jsons.items():
        for trail, item in walk(obj):
            for key, value in item.items():
                if historical_daily_path(obj, trail + (key,)):
                    continue
                if key == "logical_source":
                    # A source-export label names the original source namespace,
                    # not a destination in the publication repository.
                    continue
                for v in value if isinstance(value, list) else [value]:
                    if not isinstance(v, str) or any(c.isspace() for c in v) or not v.startswith(("../", "./", *ROOTS)) or any(c in v for c in "<>*{}"):
                        continue
                    target = resolve(p, v, link=True)
                    row = {"source": p, "json_pointer": pointer(trail + (key,)), "target": target,
                           "status": "PASS" if exists(target) else "MISSING"}
                    jlinks.append(row)
                    if row["status"] != "PASS":
                        gaps.append({"kind": "JSON_LINK_MISSING", **row})
    return {"manifests": manifests, "hash_references": refs, "local_markdown_links": links,
            "local_json_links": jlinks, "findings": errors, "publication_gaps": gaps,
            "json_files_parsed": len(jsons), "provenance_hashes_outside_public_scope_skipped": skipped}


def build(repo, base, end, output):
    output = Path(os.path.abspath(output))
    # Never resolve the final component: a dangling symlink is still a collision.
    if os.path.lexists(output):
        raise Refusal("output already exists")
    parent = output.parent.resolve(strict=True)
    if output.parent != parent:
        raise Refusal("output parent must be canonical, without symlink components")
    git = Git(repo)
    gitdir = Path(git.run("rev-parse", "--absolute-git-dir").decode().strip()).resolve()
    worktree = Path(git.run("rev-parse", "--show-toplevel").decode().strip()).resolve()
    common = Path(git.run("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()).resolve()
    if output.is_relative_to(worktree) or output.is_relative_to(gitdir) or output.is_relative_to(common):
        raise Refusal("output must be outside repository and Git metadata")
    git.commit(base); git.commit(end)
    git.run("merge-base", "--is-ancestor", base, end)
    tree = git.tree(end); base_tree = git.tree(base)
    commits = []; touched = {}; all_changes = []
    for line in git.run("rev-list", "--reverse", "--topo-order", "--parents", base + ".." + end).decode().splitlines():
        oid, *parents = line.split()
        details = git.run("show", "-s", "--no-show-signature", "--encoding=UTF-8", "--format=%cI%x00%s", oid).decode().rstrip("\n").split("\0", 1)
        row = {"commit": oid, "parents": parents, "committed_at": details[0], "subject": details[1], "changed_paths": []}
        for parent_oid in parents or [None]:
            for change in git.diff(parent_oid, oid):
                change["parent_commit"] = parent_oid
                row["changed_paths"].append(change)
                touched.setdefault(change["path"], []).append({"commit": oid, "parent_commit": parent_oid, "status": change["status"]})
                all_changes.append(change)
        commits.append(row)
    net = git.diff(base, end); all_changes.extend(net)
    git.blobs(meta["git_blob"] for row in all_changes for key in ("before", "after")
              if (meta := row.get(key)) and meta["type"] == "blob")
    for row in all_changes:
        for key in ("before", "after"):
            if key in row and row[key]["type"] == "blob":
                data = git.cache[row[key]["git_blob"]]
                row[key].update(sha256=digest(data), bytes=len(data))
    net_status = {r["path"]: r["status"] for r in net}
    paths = []
    for p, refs in sorted(touched.items()):
        row = {"path": p, "status": net_status.get(p, "INTERMEDIATE_ONLY"), "commits": refs,
               "present_at_base": p in base_tree, "present_at_end": p in tree}
        if p in tree:
            row.update(tree[p])
            if tree[p]["type"] == "blob":
                git.blobs([tree[p]["git_blob"]]); data = git.cache[tree[p]["git_blob"]]
                row.update(sha256=digest(data), bytes=len(data))
        paths.append(row)
    checks = verify_public(git, tree, touched)
    if checks["findings"]:
        kinds = sorted({e["kind"] for e in checks["findings"]})
        raise Refusal("public integrity validation failed: " + ", ".join(kinds))
    netpaths = {r["path"] for r in net}
    intermediate = sorted(set(touched) - netpaths)
    blocks = {}
    for row in paths:
        blocks.setdefault(package(row["path"]), []).append(row["path"])
    blockrows = [{"block": block, "paths": members, "file_count": len(members),
                  "commits": [c["commit"] for c in commits if any(r["path"] in members for r in c["changed_paths"])],
                  "historical_outcome_policy": "Literal published records retain their original authority and scope; no execution or acceptance inferred."}
                 for block, members in sorted(blocks.items())]
    counts = {"commits": len(commits), "net_changed_paths": len(net), "touched_paths": len(paths),
              "intermediate_only_paths": len(intermediate), "logical_blocks": len(blockrows),
              **{k: len(checks[k]) for k in ("manifests", "hash_references", "local_markdown_links", "local_json_links")},
              "json_files_parsed": checks["json_files_parsed"], "publication_gaps": len(checks["publication_gaps"])}
    now = datetime.now(MSK).isoformat()
    authority = {"stage": STAGE, "daily_checkpoint_complete": False, "publication_accepted": False,
                 "runtime_grant": False, "product_accepted": False}
    integrity = {"schema": "friday.analysis.daily.coverage-check.v1", "base_commit": base, "end_commit": end,
                 "checked_at_msk": now, **authority, "counts": counts, **checks,
                 "method": "Pinned Git objects only; SHA256, byte counts and path checks. No source import/execution, network, or product checks.",
                 "verdict": "PUBLIC_INTEGRITY_PASS" + ("_WITH_LINK_GAPS" if checks["publication_gaps"] else ""),
                 "exact_commit_chain": True, "commit_touched_paths_equal_net_changed_paths": set(touched) == netpaths,
                 "intermediate_only_paths": intermediate, "block_partition_exact": True,
                 "limits": ["Validation examines touched final files and their enclosing final manifests; historical blobs are hashed, not revalidated as current packages.",
                            "Public hash conventions match the provisional inventory; original/provenance/private assertions are outside scope.",
                            "Daily-index historical range fields are provenance bound by the report manifest, not assertions against this newer cutoff; current report artifact references are still checked.",
                            "Inline Markdown destinations and explicit local JSON paths only; logical_source provenance labels, reference-style Markdown, fragments and external URLs are not validated.",
                            "No semantic status-order inference, secret audit, private-source audit, live checks, or remote verification."]}
    integrity_bytes = encode(integrity)
    index = {"schema": "friday.analysis.daily-period-index.v1", "date_msk": now[:10], "prepared_at_msk": now,
             **authority, "base_commit": base, "end_commit": end,
             "range_semantics": "Base exclusive, end inclusive; all reachable commits in base..end, in topological order. Each parent edge is inventoried; renames are delete/add pairs.",
             "counts": counts, "ordered_commits": commits, "changed_paths": paths, "net_changed_paths": net,
             "changed_paths_semantics": "Union of all touched paths, with net status or INTERMEDIATE_ONLY; net_changed_paths is the base-to-end diff.",
             "intermediate_only_paths": intermediate, "logical_blocks": blockrows,
             "historical_outcomes": "Preserved by exact commit/path/blob references and SHA256, including before/after versions. Never recomputed, promoted to current acceptance, imported, or executed.",
             "publication_gaps": checks["publication_gaps"],
             "integrity_artifact": {"path": "publication-integrity.json", "sha256": digest(integrity_bytes), "bytes": len(integrity_bytes)},
             "remaining_daily_work": ["Reconcile all publishable work through the actual final cutoff using the unchanged previous daily base.",
                                      "Independently review final artifacts and privacy; publish and verify exact remote SHA separately."],
             "coverage_limits": integrity["limits"],
             "reproduction": {"git_environment": {"GIT_OPTIONAL_LOCKS": "0"}, "source": "Immutable local commit objects only", "execution": "NOT_RUN"}}
    payloads = {"daily-period-index.json": encode(index), "publication-integrity.json": integrity_bytes}
    manifest = {"schema": "friday.analysis.daily.v1", "baseline_commit": base, "end_commit": end,
                "date_msk": now[:10], **authority, "manifest_excludes_itself": True,
                "files": [{"path": p, "sha256": digest(b), "bytes": len(b)} for p, b in payloads.items()]}
    payloads["MANIFEST.json"] = encode(manifest)
    # Explicit public path guard; this is intentionally not a full privacy review.
    for data in payloads.values():
        if b"/home/" in data or b".jericho/" in data or re.search(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----", data):
            raise Refusal("public output contains a private-path/key marker")
    output.mkdir(mode=0o700)
    # Exclusive creation; errors leave a visibly incomplete directory that cannot be reused.
    for name, data in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        (output / name).chmod(0o444)
    for entry in manifest["files"]:
        actual = (output / entry["path"]).read_bytes()
        if digest(actual) != entry["sha256"] or len(actual) != entry["bytes"]:
            raise Refusal("output verification failed")
    output.chmod(0o555)
    return {"stage": STAGE, "base_commit": base, "end_commit": end, "counts": counts,
            "git_read_calls": git.calls, "manifest_sha256": digest(payloads["MANIFEST.json"]),
            "runtime_grant": False, "product_accepted": False, "owned_handles": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True, help="full previous daily commit ID, exclusive")
    parser.add_argument("--end", required=True, help="full final source commit ID, inclusive")
    parser.add_argument("--output", required=True, help="new directory outside the repository; parent must exist")
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    try:
        print(json.dumps(build(args.repo, args.base, args.end, args.output), ensure_ascii=False))
    except (Refusal, OSError, ValueError, subprocess.TimeoutExpired, MemoryError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc), "stage": STAGE,
                          "runtime_grant": False, "product_accepted": False}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
