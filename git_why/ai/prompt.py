from __future__ import annotations

from git_why.git_analyzer import GitAnalysis


def _target_label(analysis: GitAnalysis) -> str:
    if analysis.line_start is None or analysis.line_end is None:
        return analysis.file_path
    if analysis.line_start == analysis.line_end:
        return f"{analysis.file_path}:{analysis.line_start}"
    return f"{analysis.file_path}:{analysis.line_start}-{analysis.line_end}"


def _refs_section(analysis: GitAnalysis) -> str | None:
    """Build a 'Linked references' block from enriched refs across all commits."""
    seen: set[str] = set()
    lines: list[str] = []
    for commit in analysis.commits:
        for ref in getattr(commit, "refs", []):
            if ref.ref in seen or not ref.title:
                continue
            seen.add(ref.ref)
            lines.append(f"{ref.ref}: {ref.title}")
            if ref.body_snippet:
                snippet = ref.body_snippet.replace("\n", " ").strip()
                lines.append(f"  > {snippet[:300]}")
    return "\n".join(lines) if lines else None


def build_prompt(analysis: GitAnalysis) -> str:
    commit_sections = []
    for commit in analysis.commits:
        section = "\n".join(
            [
                f"Commit: {commit.hash}",
                f"Author: {commit.author}",
                f"Date: {commit.date}",
                f"Message: {commit.message}",
                "Diff:",
                commit.diff,
            ]
        )
        # Append fetched ref context directly under the commit it came from.
        if getattr(commit, "refs", []):
            ref_lines = []
            for ref in commit.refs:
                if ref.title:
                    ref_lines.append(f"  {ref.ref}: {ref.title}")
                    if ref.body_snippet:
                        snippet = ref.body_snippet.replace("\n", " ").strip()
                        ref_lines.append(f"    > {snippet[:200]}")
            if ref_lines:
                section += "\nLinked refs:\n" + "\n".join(ref_lines)
        commit_sections.append(section)

    parts = [
        "You are a software archaeologist explaining why code exists.",
        "Explain why the target code likely exists, how it evolved, important commits, and gotchas.",
        "Cite commit hashes when making claims. Avoid hallucinating beyond the provided git history.",
        "When linked PR/issue references are provided, use them — they often reveal the original intent "
        "that commit messages alone do not capture.",
        f"Target: {_target_label(analysis)}",
        "Current code:",
        analysis.target_code,
        "Git commits and diffs:",
        "\n\n---\n\n".join(commit_sections) if commit_sections else "No commits found.",
    ]

    refs_block = _refs_section(analysis)
    if refs_block:
        parts.append("Linked PR/issue references (fetched from GitHub/GitLab):\n" + refs_block)

    # Add diff pattern signals so the AI can cite them.
    from git_why.diff_analyzer import analyze_corpus, build_diff_explanation
    corpus = analyze_corpus(analysis.commits)
    diff_insight = build_diff_explanation(corpus)
    if diff_insight:
        parts.append(
            "Diff pattern analysis (automated heuristics from the actual code changes):\n"
            + diff_insight
        )

    return "\n\n".join(parts)
