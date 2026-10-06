#!/usr/bin/env python3
"""Observe three public donor repositories; never update or execute their code."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {"hermes": "NousResearch/hermes-agent", "a0": "agent0ai/agent-zero",
                "dsh": "deepseek-ai/deepseek-harness"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_BODY = 1024 * 1024
MAX_LOCK = 128 * 1024
TIMEOUT = 5


class ObservationError(Exception):
    pass


class QueryError(ObservationError):
    def __init__(self, reason, status=None):
        super().__init__(reason)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ObservationError("invalid_commit_identity")
    return value


def read_lock(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_LOCK + 1)
    if len(raw) > MAX_LOCK:
        raise ObservationError("lock_too_large")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw)
        if data["schema_version"] != 1 or not isinstance(data["repositories"], list):
            raise ValueError
        records = data["repositories"]
        if any(not isinstance(r, dict) or not isinstance(r.get("id"), str) for r in records):
            raise ValueError
        if len({r["id"] for r in records}) != len(records):
            raise ValueError
        selected = []
        for identity, repo in REPOSITORIES.items():
            matches = [r for r in records if r["id"] == identity]
            if len(matches) != 1 or matches[0].get("repo") != repo:
                raise ValueError
            record = matches[0]
            branch = record.get("branch")
            if (not isinstance(branch, str) or not branch or len(branch) > 255
                    or any(ord(c) < 33 for c in branch)
                    or any(c in branch for c in "~^:?*[\\") or ".." in branch):
                raise ValueError
            selected.append({"id": identity, "repo": repo, "branch": branch,
                             "commit": sha(record.get("commit"))})
    except (ValueError, KeyError, TypeError, RecursionError, ObservationError) as exc:
        raise ObservationError("invalid_lock:" + digest) from exc
    return selected, digest


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """No credentials, proxy environment, redirects, retries, or response bodies in errors.

    POSIX real-time alarm bounds DNS, TLS and trickling bodies together. Serial
    calls deliberately keep the alarm in the main thread. At most 15 calls/run.
    """
    def __init__(self, timeout=TIMEOUT, max_body=MAX_BODY):
        self.timeout = timeout
        self.max_body = max_body
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, repo, suffix):
        if repo not in REPOSITORIES.values() or not suffix.startswith("/"):
            raise QueryError("invalid_request")
        url = "https://api.github.com/repos/" + repo + suffix
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "Friday-upstream-observer/1",
            "X-GitHub-Api-Version": "2022-11-28"}, method="GET")

        def expired(signum, frame):
            raise QueryError("timeout")

        previous = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, self.timeout)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise QueryError("http_error", response.status)
                body = response.read(self.max_body + 1)
                if len(body) > self.max_body:
                    raise QueryError("body_limit")
                try:
                    result = json.loads(body)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise QueryError("malformed_json") from exc
                if not isinstance(result, dict):
                    raise QueryError("malformed_response")
                return result
        except urllib.error.HTTPError as exc:
            reason = "rate_limited_or_forbidden" if exc.code in (403, 429) else "http_error"
            exc.close()
            raise QueryError(reason, exc.code) from None
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise QueryError("network_error") from None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


def failure(exc):
    result = {"status": "unknown", "error": str(exc), "observed_at": now()}
    if isinstance(exc, QueryError) and exc.status is not None:
        result["http_status"] = exc.status
    return result


def relation(client, pin, observed):
    """Direction is observed upstream HEAD relative to locked pin (base)."""
    base = pin["commit"]
    if observed == base:
        return {"status": "current", "ahead_by": 0, "behind_by": 0}
    # GitHub omits the potentially large file/patch list after page one.
    data = client.get(pin["repo"], f"/compare/{base}...{observed}?per_page=1&page=2")
    status = data.get("status")
    ahead, behind = data.get("ahead_by"), data.get("behind_by")
    if (not isinstance(data.get("base_commit"), dict)
            or data["base_commit"].get("sha") != base
            or type(ahead) is not int or type(behind) is not int
            or ahead < 0 or behind < 0
            or (status, ahead > 0, behind > 0) not in {
                ("ahead", True, False), ("behind", False, True), ("diverged", True, True)}):
        raise ObservationError("invalid_compare_response")
    return {"status": status, "ahead_by": ahead, "behind_by": behind}


def observe(pin, client):
    web = "https://github.com/" + pin["repo"]
    result = dict(pin, pin_url=web + "/commit/" + pin["commit"], observed_at=now())
    cache = {}
    branch_accessible = False
    branch = {"status": "unknown"}
    try:
        response = client.get(pin["repo"], "/commits/" + urllib.parse.quote("refs/heads/" + pin["branch"], safe=""))
        head = sha(response.get("sha"))
        branch_accessible = True
        branch.update(head_sha=head, observed_at=now(), commit_url=web + "/commit/" + head,
                      compare_url=web + "/compare/" + pin["commit"] + "..." + head)
        cache[head] = relation(client, pin, head)
        branch.update(cache[head])
    except ObservationError as exc:
        branch.update(failure(exc))
    result["branch_observation"] = branch
    release = {"status": "unknown"}
    try:
        try:
            data = client.get(pin["repo"], "/releases/latest")
        except QueryError as exc:
            if exc.status == 404 and branch_accessible:
                result["release_observation"] = {"status": "absent", "observed_at": now(),
                    "reason": "latest_release_404_with_public_branch_observed"}
                return result
            raise
        tag, notes, published = data.get("tag_name"), data.get("body"), data.get("published_at")
        if (data.get("draft") is not False or data.get("prerelease") is not False
                or not isinstance(tag, str) or not tag or len(tag) > 255
                or any(ord(c) < 32 for c in tag) or not isinstance(published, str)
                or (notes is not None and not isinstance(notes, str))):
            raise ObservationError("invalid_release_response")
        release.update(tag=tag, published_at=published, observed_at=now(),
                       release_url=web + "/releases/tag/" + urllib.parse.quote(tag, safe=""),
                       notes=notes, notes_are_untrusted=True)
        commit = client.get(pin["repo"], "/commits/" + urllib.parse.quote("refs/tags/" + tag, safe=""))
        head = sha(commit.get("sha"))
        release.update(head_sha=head, commit_url=web + "/commit/" + head,
                       compare_url=web + "/compare/" + pin["commit"] + "..." + head)
        release.update(cache[head] if head in cache else relation(client, pin, head))
    except ObservationError as exc:
        release.update(failure(exc))
    result["release_observation"] = release
    return result


def collect(path, client):
    report = {"schema_version": 1, "started_at": now(), "status": "unknown",
              "lock_sha256": None, "repositories": [], "excluded": ["friday", "legacy_workspace"],
              "direction": "observed_upstream_relative_to_pinned_commit",
              "compatibility": "NOT_ASSESSED", "updates_applied": False}
    try:
        pins, digest = read_lock(path)
        report["lock_sha256"] = digest
        report["repositories"] = [observe(pin, client) for pin in pins]
        statuses = [r[k]["status"] for r in report["repositories"]
                    for k in ("branch_observation", "release_observation")]
        report["status"] = "partial" if "unknown" in statuses else "ok"
        report["changes_observed"] = any(s in {"ahead", "behind", "diverged"} for s in statuses)
    except (ObservationError, OSError) as exc:
        report["error"] = str(exc) if isinstance(exc, ObservationError) else "lock_read_failed"
        if report["error"].startswith("invalid_lock:"):
            report["lock_sha256"] = report["error"].split(":", 1)[1]
            report["error"] = "invalid_lock"
    report["completed_at"] = now()
    return report


def write_report(directory, report):
    """Pin every directory component; only create a new private report, never replace."""
    path = Path(directory)
    if ".." in path.parts:
        raise ObservationError("unsafe_report_directory")
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    private_boundary = False
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            writable = stat.S_IMODE(info.st_mode) & 0o022
            trusted_tmp = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (info.st_uid not in (0, os.getuid())
                    or (writable and not trusted_tmp and not private_boundary)):
                raise ObservationError("unsafe_report_ancestor")
            if info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0:
                private_boundary = True
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ObservationError("report_directory_must_be_owned_mode_0700")
        name = datetime.now(timezone.utc).strftime("upstream-%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex + ".json"
        output = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(output, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return str(path / name)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "sources.lock.json")
    parser.add_argument("--report-dir", type=Path, help="existing private (0700) directory; exclusive new JSON report")
    args = parser.parse_args()
    report = collect(args.lock, Client())
    if args.report_dir:
        try:
            print(write_report(args.report_dir, report))
        except (OSError, ObservationError):
            print("report_write_refused_or_failed; current observation follows", file=sys.stderr)
            print(json.dumps(report, ensure_ascii=True, indent=2))
            return 2
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
