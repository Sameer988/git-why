from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess


class GitAnalysisError(Exception):
    pass


@dataclass
class CommitInfo:
    hash: str
    short_hash: str
    author: str
    date: str
    message: str
    diff: str
    refs: list = field(default_factory=list)  # list[LinkedRef] — populated by linker


@dataclass
class GitAnalysis:
    file_path: str
    line_start: int | None
    line_end: int | None
    target_code: str
    commits: list[CommitInfo]
    raw_context: str
    context_lines: int = 8
    rate_limit_warning: str | None = None


def run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitAnalysisError("git is not installed or is not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        if not message:
            message = "git command failed."
        raise GitAnalysisError(message) from exc
    return result.stdout


def _is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            sample = f.read(8192)
    except OSError:
        return False
    return b"\x00" in sample


BINARY_PLACEHOLDER = "[binary file - content preview not shown]"


class _BinaryFile(Exception):
    pass


def _read_lines(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise GitAnalysisError(f"File not found: {file_path}")
    if not path.is_file():
        raise GitAnalysisError(f"Target is not a file: {file_path}")
    if _is_binary(path):
        raise _BinaryFile()
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        raise GitAnalysisError(f"Could not read file: {file_path}") from exc


def get_file_content(
    file_path: str,
    line_start: int | None,
    line_end: int | None,
    context: int,
) -> str:
    try:
        lines = _read_lines(file_path)
    except _BinaryFile:
        return BINARY_PLACEHOLDER
    if line_start is None or line_end is None:
        shown = lines[:120]
        suffix = "\n... [truncated]" if len(lines) > 120 else ""
        return "\n".join(f"{idx:>5}  {line}" for idx, line in enumerate(shown, start=1)) + suffix

    if line_start > len(lines):
        raise GitAnalysisError(
            f"Line {line_start} is outside {file_path}, which has {len(lines)} lines."
        )
    if line_end > len(lines):
        raise GitAnalysisError(
            f"Line range {line_start}-{line_end} extends beyond {file_path}, which has {len(lines)} lines."
        )

    capped_end = line_end
    start = max(1, line_start - context)
    end = min(len(lines), capped_end + context)
    formatted = []
    for idx in range(start, end + 1):
        marker = "\u2192 " if line_start <= idx <= capped_end else "  "
        formatted.append(f"{marker} {idx:>5}  {lines[idx - 1]}")
    return "\n".join(formatted)


def read_target_lines(
    file_path: str,
    line_start: int | None,
    line_end: int | None,
    context: int,
) -> tuple[list[str], int, set[int]]:
    """Return raw source lines (no markers) for syntax-highlighted display.

    Returns (lines_to_show, first_line_number, highlighted_line_numbers).
    Kept separate from get_file_content, which produces the plain-text,
    marker-annotated version used in AI prompts and offline explanations.
    """
    try:
        lines = _read_lines(file_path)
    except _BinaryFile:
        return [BINARY_PLACEHOLDER], 1, set()
    if line_start is None or line_end is None:
        shown = lines[:120]
        return shown, 1, set()

    start = max(1, line_start - context)
    end = min(len(lines), line_end + context)
    shown = lines[start - 1 : end]
    highlighted = set(range(line_start, line_end + 1))
    return shown, start, highlighted


def get_blame_hashes(file_path: str, line_start: int | None, line_end: int | None) -> list[str]:
    if line_start is None or line_end is None:
        return []
    output = run_git(["blame", "--porcelain", "-L", f"{line_start},{line_end}", "--", file_path])
    hashes = []
    for line in output.splitlines():
        if not line or line.startswith("\t"):
            continue
        first = line.split(" ", 1)[0]
        if len(first) >= 40 and set(first) != {"0"}:
            hashes.append(first)
    return list(dict.fromkeys(hashes))


def get_log_hashes(file_path: str, depth: int) -> list[str]:
    output = run_git(["log", "--pretty=format:%H", "--follow", "-n", str(depth), "--", file_path])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _metadata_for_commit(commit_hash: str) -> tuple[str, str, str]:
    fmt = "%an%x1f%ad%x1f%s"
    output = run_git(["show", "--no-patch", f"--pretty=format:{fmt}", "--date=short", commit_hash])
    parts = output.strip().split("\x1f", 2)
    if len(parts) != 3:
        return "Unknown", "Unknown", output.strip() or "(no message)"
    return parts[0], parts[1], parts[2]


def get_commit_details(commit_hash: str, file_path: str) -> CommitInfo:
    author, date, message = _metadata_for_commit(commit_hash)
    diff = run_git(["show", "-p", "--unified=3", commit_hash, "--", file_path]).strip()
    if len(diff) > 3500:
        diff = diff[:3500].rstrip() + "\n... [diff truncated]"
    return CommitInfo(
        hash=commit_hash,
        short_hash=commit_hash[:10],
        author=author,
        date=date,
        message=message,
        diff=diff,
    )


def is_binary_file(file_path: str) -> bool:
    path = Path(file_path)
    return path.is_file() and _is_binary(path)


def analyze_target(
    file_path: str,
    line_start: int | None,
    line_end: int | None,
    depth: int,
    context: int,
    fetch_refs: bool = True,
) -> GitAnalysis:
    from git_why.linker import enrich_commits

    target_code = get_file_content(file_path, line_start, line_end, context)
    # git blame depends on real line semantics, which are meaningless for binary
    # content -- and a binary file may have far fewer "lines" than the requested
    # range, which would make git itself error out. git log doesn't depend on
    # line numbers, so commit history is unaffected either way.
    if is_binary_file(file_path):
        blame_hashes: list[str] = []
    else:
        blame_hashes = get_blame_hashes(file_path, line_start, line_end)
    log_hashes = get_log_hashes(file_path, depth)
    commit_hashes = list(dict.fromkeys([*blame_hashes, *log_hashes]))
    commits = [get_commit_details(commit_hash, file_path) for commit_hash in commit_hashes]

    enrich_result = enrich_commits(commits, fetch_refs=fetch_refs)

    raw_context_parts = [
        f"file_path: {file_path}",
        f"line_start: {line_start}",
        f"line_end: {line_end}",
        "",
        "target_code:",
        target_code,
        "",
        "commits:",
    ]
    for commit in commits:
        raw_context_parts.append(
            f"{commit.short_hash} | {commit.author} | {commit.date} | {commit.message}"
        )
    return GitAnalysis(
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        target_code=target_code,
        commits=commits,
        raw_context="\n".join(raw_context_parts),
        context_lines=context,
        rate_limit_warning=enrich_result.rate_limit_warning,
    )
