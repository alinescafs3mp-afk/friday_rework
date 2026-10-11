"""Check exact analysis publication bytes without changing Git whitespace policy.

Single-space empty context lines are necessary unified-diff syntax. Only those
lines, including a terminal run Git diagnoses as blank EOF, may account for a
nonzero ``git diff --check`` result. This check grants
neither publication privacy approval nor product/source/runtime acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def context_markers(data):
    """Return 1-based positions of complete unified-hunk empty context lines."""
    allowed = set()
    remaining = None
    hunks = 0
    for number, line in enumerate(data.split(b"\n"), 1):
        if line.startswith(b"@@ "):
            require(remaining is None or remaining == [0, 0], "unfinished hunk")
            match = re.match(rb"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?: |$)", line)
            require(match is not None, "invalid hunk header")
            remaining = [int(match.group(1) or b"1"), int(match.group(2) or b"1")]
            hunks += 1
            continue
        if remaining is None or remaining == [0, 0]:
            continue
        if line == b"\\ No newline at end of file":
            continue
        require(bool(line) and line[:1] in (b" ", b"+", b"-"), "invalid hunk body")
        if line == b" ":
            allowed.add(number)
        if line[:1] in (b" ", b"-"):
            remaining[0] -= 1
        if line[:1] in (b" ", b"+"):
            remaining[1] -= 1
        require(min(remaining) >= 0, "hunk underflow")
    require(hunks > 0, "no unified hunks")
    require(remaining == [0, 0], "unfinished final hunk")
    return allowed


def strict_text_whitespace(data, allowed_markers):
    """Enforce pinned text bytes independently of Git config/attributes/diff drivers."""
    require(b"\x00" not in data, "binary NUL outside text publication domain")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Refused("publication is not UTF-8 text") from error
    lines = data.split(b"\n")
    if data.endswith(b"\n"):
        lines.pop()
    for number, line in enumerate(lines, 1):
        if line == b" " and number in allowed_markers:
            continue
        require(not line.endswith((b" ", b"\t", b"\r", b"\v", b"\f")), "non-context trailing whitespace at line " + str(number))
    require(not data or not lines or lines[-1] != b"", "new blank line at EOF")


def checked_file(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), "input is not a regular file")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        data = stream.read()
        after = os.fstat(stream.fileno())
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")
    require(all(getattr(before, key) == getattr(after, key) for key in keys), "input changed while read")
    return data


def terminal_context_start(data, allowed_markers):
    """Locate only a terminal physical run of parsed empty context lines."""
    if not data.endswith(b" \n"):
        return None
    lines = data.split(b"\n")[:-1]
    start = len(lines)
    while start > 0 and lines[start-1] == b" ":
        require(start in allowed_markers, "terminal blank is not parsed context")
        start -= 1
    return start + 1


def parse_diagnostics(stdout, returncode, parsed, terminal_starts):
    """Consume exact Git diagnostics; an EOF diagnostic has no source pair."""
    observed = []
    terminal_eof = []
    lines = stdout.decode("ascii").split("\n")
    require(lines[-1] == "", "unterminated whitespace diagnostic")
    lines.pop()
    offset = 0
    while offset < len(lines):
        match = re.fullmatch(r"(.+):(\d+): trailing whitespace\.", lines[offset])
        if match is not None:
            name, number = match.group(1), int(match.group(2))
            require(offset+1 < len(lines), "missing whitespace source line")
            require(name in parsed and number in parsed[name] and lines[offset+1] == "+ ", "whitespace is not a literal empty context marker")
            observed.append({"path": name, "line": number})
            offset += 2
            continue
        match = re.fullmatch(r"(.+):(\d+): new blank line at EOF\.", lines[offset])
        require(match is not None, "non-context whitespace error")
        name, number = match.group(1), int(match.group(2))
        require(name in parsed and terminal_starts.get(name) == number, "EOF diagnostic is not the start of terminal parsed empty context")
        require(not any(item["path"] == name for item in terminal_eof), "duplicate EOF diagnostic")
        terminal_eof.append({"path": name, "line": number})
        offset += 1
    require((returncode == 2) == bool(observed or terminal_eof), "whitespace exit/diagnostic mismatch")
    return observed, terminal_eof


def check(repo, pins_path, pins_sha256, base, end=None, cached=False):
    repo = repo.resolve(strict=True)
    pins = checked_file(pins_path)
    require(hashlib.sha256(pins).hexdigest() == pins_sha256, "pins digest mismatch")
    spec = json.loads(pins)
    require(spec["repository"] == str(repo), "repository mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", base) is not None, "invalid base commit")
    require(spec["base_commit"] == base, "base commit mismatch")
    require(cached != bool(end), "select cached or committed comparison")
    if end:
        require(re.fullmatch(r"[0-9a-f]{40}", end) is not None, "invalid end commit")
    prefix = spec["public_prefix"]
    require(re.fullmatch(r"analysis/\d{4}-\d{2}-\d{2}/[A-Za-z0-9_-]+", prefix) is not None, "invalid public prefix")
    rows = spec["files"]
    require(isinstance(rows, list) and bool(rows), "empty publication")
    expected = {}
    for row in rows:
        name = row["path"]
        require(re.fullmatch(r"[A-Za-z0-9_./-]+", name) is not None, "unsupported filename")
        require(not name.startswith("/") and all(part not in ("", ".", "..") for part in name.split("/")), "unsafe relative path")
        full = prefix + "/" + name
        require(full not in expected, "duplicate publication path")
        require(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None, "invalid file digest")
        require(type(row["bytes"]) is int and row["bytes"] >= 0, "invalid file size")
        expected[full] = row
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}

    def git(arguments, accepted=(0,)):
        result = subprocess.run(["git", "--no-optional-locks", *arguments], cwd=repo, env=env, capture_output=True, timeout=60)
        require(result.returncode in accepted and not result.stderr, "Git command failed: " + arguments[0])
        return result

    comparison = ["--cached", base] if cached else [base, end]
    if cached:
        require(git(["rev-parse", "HEAD"]).stdout.decode().strip() == base, "cached comparison base is not HEAD")
        entries = git(["ls-files", "--stage", "-z", "--", prefix]).stdout.split(b"\0")
    else:
        entries = git(["ls-tree", "-r", "-z", end, "--", prefix]).stdout.split(b"\0")
    modes = {}
    for entry in entries:
        if not entry:
            continue
        metadata, filename = entry.split(b"\t", 1)
        fields = metadata.split()
        require(fields[0] in (b"100644", b"100755"), "publication member is not a regular Git file")
        require((cached and fields[2] == b"0") or (not cached and fields[1] == b"blob"), "invalid Git member stage or kind")
        name = filename.decode("ascii")
        require(name not in modes, "duplicate Git member")
        modes[name] = fields[0].decode()
    require(set(modes) == set(expected), "Git publication inventory differs from exact pins")
    changes = git(["diff", *comparison, "--name-status", "-z", "--no-renames"]).stdout.split(b"\0")
    require(changes[-1] == b"" and (len(changes)-1) % 2 == 0, "invalid Git path inventory")
    actual = {}
    for offset in range(0, len(changes)-1, 2):
        require(changes[offset] == b"A", "publication must add immutable analysis files only")
        name = changes[offset+1].decode("ascii")
        require(name not in actual, "duplicate Git path")
        actual[name] = "A"
    require(set(actual) == set(expected), "changed paths differ from exact publication")
    parsed = {}
    terminal_starts = {}
    for name, row in expected.items():
        object_name = ":" + name if cached else end + ":" + name
        data = git(["show", object_name]).stdout
        require(hashlib.sha256(data).hexdigest() == row["sha256"] and len(data) == row["bytes"], "Git blob pin mismatch")
        if cached:
            require(checked_file(repo/name) == data, "working bytes differ from staged publication")
        if name.endswith(".patch"):
            parsed[name] = context_markers(data)
            # Git parses the same pinned blob, including headers and all hunks.
            result = subprocess.run(["git", "--no-optional-locks", "apply", "--numstat", "-"], cwd=repo, env=env, input=data, capture_output=True, timeout=60)
            require(result.returncode == 0 and not result.stderr, "invalid unified patch")
            terminal_starts[name] = terminal_context_start(data, parsed[name])
        strict_text_whitespace(data, parsed.get(name, set()))
    default = git(["diff", *comparison, "--check"], (0, 2))
    observed, terminal_eof = parse_diagnostics(default.stdout, default.returncode, parsed, terminal_starts)
    nonpatch = sorted(set(expected)-set(parsed))
    if nonpatch:
        strict = git(["diff", *comparison, "--check", "--", *nonpatch])
        require(not strict.stdout, "non-patch whitespace error")
    return {"status": "PASS_EXACT_PUBLICATION_WHITESPACE", "files": len(expected), "patch_files": len(parsed), "strict_nonpatch_files": len(nonpatch), "pinned_text_whitespace_independent_of_Git_policy": True, "UTF8_text_domain_verified": True, "literal_context_markers": observed, "literal_terminal_context_eof": terminal_eof, "default_check_exit_code": default.returncode, "default_check_pass_claimed": default.returncode == 0, "Git_config_changed": False, "public_bytes_changed": False, "privacy_approval": False, "source_acceptance": False, "runtime_grant": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--pins-sha256", required=True)
    parser.add_argument("--base", required=True)
    comparison = parser.add_mutually_exclusive_group(required=True)
    comparison.add_argument("--end")
    comparison.add_argument("--cached", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check(args.repo, args.pins, args.pins_sha256, args.base, args.end, args.cached)))


if __name__ == "__main__":
    main()
