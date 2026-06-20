"""Tests for the PR/issue linker and git notes cache."""
from __future__ import annotations

import json
import subprocess

import pytest

from git_why.linker import (
    LinkedRef,
    RemoteInfo,
    build_url,
    detect_remote,
    enrich_commits,
    extract_refs,
)
from git_why.cache import read_cached_refs, write_cached_refs


# ─── extract_refs ─────────────────────────────────────────────────────────────

def test_extract_refs_hash_only():
    assert extract_refs("fix auth issue #847") == ["#847"]


def test_extract_refs_closing_keyword():
    assert extract_refs("fixes #42 and closes #99") == ["#42", "#99"]


def test_extract_refs_jira():
    assert extract_refs("PROJ-123 rate limiting fix") == ["PROJ-123"]


def test_extract_refs_full_url():
    url = "https://github.com/owner/repo/issues/10"
    assert extract_refs(f"see {url}") == [url]


def test_extract_refs_mixed():
    refs = extract_refs("fix #10, PROJ-42, see https://github.com/a/b/issues/99")
    assert "#10" in refs
    assert "PROJ-42" in refs
    assert "https://github.com/a/b/issues/99" in refs


def test_extract_refs_deduplicates():
    refs = extract_refs("fix #10 and also #10")
    assert refs.count("#10") == 1


def test_extract_refs_empty():
    assert extract_refs("update dependencies") == []


def test_extract_refs_no_jira_lowercase():
    # Jira refs must be uppercase project keys.
    assert extract_refs("proj-123 fix") == []


# ─── build_url ────────────────────────────────────────────────────────────────

def test_build_url_github():
    remote = RemoteInfo("github", "github.com", "myorg", "myrepo")
    assert build_url("#42", remote) == "https://github.com/myorg/myrepo/issues/42"


def test_build_url_gitlab():
    remote = RemoteInfo("gitlab", "gitlab.com", "myorg", "myrepo")
    assert build_url("#42", remote) == "https://gitlab.com/myorg/myrepo/-/issues/42"


def test_build_url_full_url_passthrough():
    url = "https://github.com/a/b/issues/1"
    assert build_url(url, None) == url


def test_build_url_no_remote_hash():
    assert build_url("#42", None) == ""


def test_build_url_jira_no_host(monkeypatch):
    monkeypatch.delenv("JIRA_HOST", raising=False)
    assert build_url("PROJ-123", None) == ""


def test_build_url_jira_with_host(monkeypatch):
    monkeypatch.setenv("JIRA_HOST", "jira.mycompany.com")
    assert build_url("PROJ-123", None) == "https://jira.mycompany.com/browse/PROJ-123"


# ─── enrich_commits ───────────────────────────────────────────────────────────

class _FakeCommit:
    def __init__(self, message: str, full_hash: str = "abc123"):
        self.message = message
        self.full_hash = full_hash
        self.refs = []


def test_enrich_commits_no_refs():
    commits = [_FakeCommit("update dependencies")]
    result = enrich_commits(commits, fetch_refs=False)
    assert commits[0].refs == []
    assert result.rate_limit_warning is None


def test_enrich_commits_url_only_mode(monkeypatch):
    """With fetch_refs=False and a GitHub remote, we get URL-only LinkedRefs."""
    monkeypatch.setattr(
        "git_why.linker.detect_remote",
        lambda: RemoteInfo("github", "github.com", "owner", "repo"),
    )
    commits = [_FakeCommit("fix auth #42")]
    enrich_commits(commits, fetch_refs=False)
    assert len(commits[0].refs) == 1
    ref = commits[0].refs[0]
    assert ref.ref == "#42"
    assert ref.url == "https://github.com/owner/repo/issues/42"
    assert ref.title is None  # no fetch, no title


def test_enrich_commits_deduplicates_refs(monkeypatch):
    """Same ref in two commits is fetched/cached once but attached to both."""
    monkeypatch.setattr(
        "git_why.linker.detect_remote",
        lambda: RemoteInfo("github", "github.com", "owner", "repo"),
    )
    c1 = _FakeCommit("fix #42", full_hash="aaa")
    c2 = _FakeCommit("also fix #42", full_hash="bbb")
    enrich_commits([c1, c2], fetch_refs=False)
    assert len(c1.refs) == 1
    assert len(c2.refs) == 1
    assert c1.refs[0].ref == c2.refs[0].ref == "#42"


def test_enrich_commits_no_remote(monkeypatch):
    """Without a remote, hash refs get no URL but don't crash."""
    monkeypatch.setattr("git_why.linker.detect_remote", lambda: None)
    commits = [_FakeCommit("fix #99")]
    enrich_commits(commits, fetch_refs=False)
    assert len(commits[0].refs) == 1
    assert commits[0].refs[0].url == ""


def test_enrich_commits_cache_hit(monkeypatch, tmp_path):
    """A cached ref is used without making an API call."""
    monkeypatch.setattr(
        "git_why.linker.detect_remote",
        lambda: RemoteInfo("github", "github.com", "owner", "repo"),
    )
    monkeypatch.setattr(
        "git_why.linker.read_cached_refs",
        lambda h: {"#42": {"title": "Fix race condition", "body": "Details here"}},
    )
    fetch_calls = []
    monkeypatch.setattr("git_why.linker._fetch_github", lambda *a, **k: fetch_calls.append(1) or (None, None))

    commits = [_FakeCommit("fix #42", full_hash="abc")]
    result = enrich_commits(commits, fetch_refs=True)

    assert fetch_calls == []  # no API call made
    assert result.refs_from_cache == 1
    ref = commits[0].refs[0]
    assert ref.title == "Fix race condition"
    assert ref.from_cache is True


# ─── cache ────────────────────────────────────────────────────────────────────

def test_read_cached_refs_returns_empty_on_missing(monkeypatch):
    monkeypatch.setattr(
        "git_why.cache.subprocess.run",
        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": ""})(),
    )
    assert read_cached_refs("deadbeef") == {}


def test_read_cached_refs_parses_json(monkeypatch):
    payload = {"#42": {"title": "Fix", "body": "Details"}}
    monkeypatch.setattr(
        "git_why.cache.subprocess.run",
        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": json.dumps(payload)})(),
    )
    assert read_cached_refs("deadbeef") == payload


def test_write_cached_refs_merges_existing(monkeypatch):
    existing = {"#10": {"title": "Old", "body": ""}}
    monkeypatch.setattr(
        "git_why.cache.subprocess.run",
        lambda *a, **k: (
            type("R", (), {"returncode": 0, "stdout": json.dumps(existing)})()
            if "show" in a[0]
            else type("R", (), {"returncode": 0, "stdout": ""})()
        ),
    )
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("R", (), {"returncode": 0, "stdout": ""})()
    monkeypatch.setattr("git_why.cache.subprocess.run", fake_run)

    write_cached_refs("deadbeef", {"#42": {"title": "New", "body": "body"}})
    add_call = next((c for c in calls if "add" in c), None)
    assert add_call is not None
    written = json.loads(add_call[add_call.index("-m") + 1])
    assert "#42" in written
