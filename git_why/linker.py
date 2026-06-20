"""
PR/issue linker for git-why.

Detects the git remote platform (GitHub/GitLab), extracts issue and PR
references from commit messages, builds browsable URLs, optionally fetches
titles and body snippets via API, and caches results in git notes.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

from git_why.cache import read_cached_refs, write_cached_refs

# ─── Limits ───────────────────────────────────────────────────────────────────

# Stay well under GitHub's 60 req/hr unauthenticated and 5000/hr authenticated.
_MAX_UNAUTHED = 50
_MAX_AUTHED = 200

# ─── Ref patterns ─────────────────────────────────────────────────────────────

# #123, closes #123, fixes #123, resolves #123 etc.
_HASH_REF = re.compile(
    r'(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)?\s*#(\d+)',
    re.IGNORECASE,
)
# Jira-style PROJECT-123
_JIRA_REF = re.compile(r'\b([A-Z][A-Z0-9]+-\d+)\b')
# Full GitHub/GitLab URL embedded in message
_URL_REF = re.compile(
    r'(https?://(?:[\w.\-]+\.)?(?:github|gitlab)\.[\w]+/[\w.\-]+/[\w.\-]+'
    r'/(?:issues|pull|merge_requests)/\d+)'
)


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class RemoteInfo:
    platform: str  # "github" | "gitlab" | "unknown"
    host: str      # e.g. "github.com", "gitlab.mycompany.com"
    owner: str
    repo: str


@dataclass
class LinkedRef:
    ref: str                  # "#847", "PROJ-123", or a full URL
    url: str                  # full browsable URL (empty string if none)
    title: str | None         # fetched title, None in URL-only mode
    body_snippet: str | None  # first 300 chars of body
    platform: str             # "github" | "gitlab" | "jira" | "url" | "unknown"
    from_cache: bool = False


@dataclass
class EnrichResult:
    rate_limit_warning: str | None
    refs_fetched: int
    refs_from_cache: int


# ─── Remote detection ─────────────────────────────────────────────────────────

def detect_remote() -> RemoteInfo | None:
    """Parse `git remote get-url origin` to extract platform/owner/repo."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None

    # SSH: git@github.com:owner/repo.git
    m = re.match(r'git@([\w.\-]+):([\w.\-]+)/([\w.\-]+?)(?:\.git)?$', url)
    if m:
        host, owner, repo = m.groups()
        return RemoteInfo(_platform(host), host, owner, repo)

    # HTTPS: https://github.com/owner/repo.git
    m = re.match(r'https?://([\w.\-]+)/([\w.\-]+)/([\w.\-]+?)(?:\.git)?$', url)
    if m:
        host, owner, repo = m.groups()
        return RemoteInfo(_platform(host), host, owner, repo)

    return None


def _platform(host: str) -> str:
    if "github.com" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    return "unknown"


# ─── Token detection ──────────────────────────────────────────────────────────

def _get_token(platform: str) -> str | None:
    """
    Auto-detect auth tokens from environment variables.
    Priority order: explicit git-why override → GitHub CLI → generic GitHub.
    """
    candidates = ["GIT_WHY_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"]
    if platform == "gitlab":
        candidates = ["GIT_WHY_GITLAB_TOKEN", "GITLAB_TOKEN"] + candidates
    for key in candidates:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


# ─── Ref extraction ───────────────────────────────────────────────────────────

def extract_refs(message: str) -> list[str]:
    """Return deduplicated raw ref strings found in a commit message."""
    seen: set[str] = set()
    refs: list[str] = []

    for m in _HASH_REF.finditer(message):
        r = f"#{m.group(1)}"
        if r not in seen:
            refs.append(r)
            seen.add(r)

    for m in _JIRA_REF.finditer(message):
        r = m.group(1)
        if r not in seen:
            refs.append(r)
            seen.add(r)

    for m in _URL_REF.finditer(message):
        r = m.group(1)
        if r not in seen:
            refs.append(r)
            seen.add(r)

    return refs


# ─── URL construction ─────────────────────────────────────────────────────────

def build_url(raw_ref: str, remote: RemoteInfo | None) -> str:
    """Return a browsable URL for raw_ref, or empty string if not resolvable."""
    if raw_ref.startswith("http"):
        return raw_ref

    if raw_ref.startswith("#") and remote:
        number = raw_ref[1:]
        if remote.platform == "github":
            return f"https://github.com/{remote.owner}/{remote.repo}/issues/{number}"
        if remote.platform == "gitlab":
            host = os.environ.get("GITLAB_HOST", remote.host)
            return f"https://{host}/{remote.owner}/{remote.repo}/-/issues/{number}"

    if re.match(r'^[A-Z][A-Z0-9]+-\d+$', raw_ref):
        jira_host = os.environ.get("JIRA_HOST", "").strip()
        if jira_host:
            return f"https://{jira_host}/browse/{raw_ref}"

    return ""


def _ref_platform(raw_ref: str, remote: RemoteInfo | None) -> str:
    if raw_ref.startswith("http"):
        if "github" in raw_ref:
            return "github"
        if "gitlab" in raw_ref:
            return "gitlab"
        return "url"
    if raw_ref.startswith("#"):
        return remote.platform if remote else "unknown"
    return "jira"


# ─── API fetching ─────────────────────────────────────────────────────────────

def _fetch_github(raw_ref: str, remote: RemoteInfo, token: str | None) -> tuple[str | None, str | None]:
    """Fetch (title, body_snippet) from GitHub REST API."""
    try:
        import requests as req
    except ImportError:
        return None, None

    number = raw_ref.lstrip("#")
    url = f"https://api.github.com/repos/{remote.owner}/{remote.repo}/issues/{number}"
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = req.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title") or None
            body = (data.get("body") or "")[:300].strip() or None
            return title, body
    except Exception:
        pass
    return None, None


def _fetch_gitlab(raw_ref: str, remote: RemoteInfo, token: str | None) -> tuple[str | None, str | None]:
    """Fetch (title, body_snippet) from GitLab REST API."""
    try:
        import requests as req
    except ImportError:
        return None, None

    number = raw_ref.lstrip("#")
    host = os.environ.get("GITLAB_HOST", remote.host)
    project = f"{remote.owner}%2F{remote.repo}"
    url = f"https://{host}/api/v4/projects/{project}/issues/{number}"
    headers: dict[str, str] = {}
    if token:
        headers["PRIVATE-TOKEN"] = token
    try:
        resp = req.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title") or None
            body = (data.get("description") or "")[:300].strip() or None
            return title, body
    except Exception:
        pass
    return None, None


# ─── Main enrichment entry point ──────────────────────────────────────────────

def enrich_commits(commits: list, fetch_refs: bool = True) -> EnrichResult:
    """
    Attach LinkedRef objects to each CommitInfo.refs in place.

    - Deduplicates refs across all commits (fetch/cache once, attach everywhere).
    - Checks git notes cache before making any API call.
    - Stops fetching once the per-session limit is reached and falls back to
      URL-only mode for remaining refs.
    - fetch_refs=False forces URL-only mode regardless of token availability.
    """
    remote = detect_remote()
    token = _get_token(remote.platform if remote else "unknown") if remote else None
    max_req = _MAX_AUTHED if token else _MAX_UNAUTHED
    fetch_count = 0
    cache_count = 0
    rate_limited = False

    # Collect unique refs and which commits reference them.
    ref_to_commits: dict[str, list] = {}
    for commit in commits:
        for raw in extract_refs(commit.message):
            ref_to_commits.setdefault(raw, []).append(commit)

    resolved: dict[str, LinkedRef] = {}

    for raw_ref, affected in ref_to_commits.items():
        if raw_ref in resolved:
            continue

        url = build_url(raw_ref, remote)
        platform = _ref_platform(raw_ref, remote)
        title: str | None = None
        body: str | None = None
        from_cache = False

        # Only attempt cache/fetch for numeric refs (#123) on known platforms.
        if raw_ref.startswith("#") and remote and remote.platform in ("github", "gitlab"):
            first_hash = affected[0].full_hash

            # 1. Check git notes cache.
            cached = read_cached_refs(first_hash)
            if raw_ref in cached:
                title = cached[raw_ref].get("title")
                body = cached[raw_ref].get("body") or None
                from_cache = True
                cache_count += 1

            # 2. Fetch from API if enabled and under limit.
            elif fetch_refs and url:
                if fetch_count < max_req:
                    if remote.platform == "github":
                        title, body = _fetch_github(raw_ref, remote, token)
                    else:
                        title, body = _fetch_gitlab(raw_ref, remote, token)
                    fetch_count += 1
                    if title is not None:
                        write_cached_refs(first_hash, {raw_ref: {"title": title, "body": body or ""}})
                else:
                    rate_limited = True

        resolved[raw_ref] = LinkedRef(
            ref=raw_ref,
            url=url,
            title=title,
            body_snippet=body,
            platform=platform,
            from_cache=from_cache,
        )

    # Attach to commits.
    for commit in commits:
        commit.refs = [resolved[r] for r in extract_refs(commit.message) if r in resolved]

    warning: str | None = None
    if rate_limited:
        if token:
            warning = (
                f"Fetched {fetch_count} refs (session limit reached). "
                "Re-run to fetch remaining from cache."
            )
        else:
            warning = (
                f"Fetched {fetch_count}/{_MAX_UNAUTHED} refs (unauthenticated limit). "
                "Set GITHUB_TOKEN for higher limits."
            )

    return EnrichResult(
        rate_limit_warning=warning,
        refs_fetched=fetch_count,
        refs_from_cache=cache_count,
    )
