"""
Git notes cache for fetched PR/issue data.

Stores enriched ref metadata in git notes under refs/notes/git-why so that
repeated runs on the same repo are instant and air-gapped environments work
after the first fetch.

Schema per commit:
  { "#847": {"title": "Fix race condition", "body": "When two requests..."} }
"""
from __future__ import annotations

import json
import subprocess

_NOTES_REF = "git-why"


def read_cached_refs(commit_hash: str) -> dict[str, dict]:
    """Return cached ref data for a commit hash, or {} if none exists."""
    try:
        result = subprocess.run(
            ["git", "notes", f"--ref={_NOTES_REF}", "show", commit_hash],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return {}


def write_cached_refs(commit_hash: str, new_refs: dict[str, dict]) -> None:
    """Merge new_refs into the existing git-notes cache for commit_hash."""
    existing = read_cached_refs(commit_hash)
    existing.update(new_refs)
    try:
        subprocess.run(
            [
                "git", "notes", f"--ref={_NOTES_REF}",
                "add", "-f", "-m", json.dumps(existing),
                commit_hash,
            ],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
