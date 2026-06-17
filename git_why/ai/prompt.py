from __future__ import annotations

from git_why.git_analyzer import GitAnalysis


def _target_label(analysis: GitAnalysis) -> str:
    if analysis.line_start is None or analysis.line_end is None:
        return analysis.file_path
    if analysis.line_start == analysis.line_end:
        return f"{analysis.file_path}:{analysis.line_start}"
    return f"{analysis.file_path}:{analysis.line_start}-{analysis.line_end}"


def build_prompt(analysis: GitAnalysis) -> str:
    commit_sections = []
    for commit in analysis.commits:
        commit_sections.append(
            "\n".join(
                [
                    f"Commit: {commit.hash}",
                    f"Author: {commit.author}",
                    f"Date: {commit.date}",
                    f"Message: {commit.message}",
                    "Diff:",
                    commit.diff,
                ]
            )
        )

    return "\n\n".join(
        [
            "You are a software archaeologist explaining why code exists.",
            "Explain why the target code likely exists, how it evolved, important commits, and gotchas.",
            "Cite commit hashes when making claims. Avoid hallucinating beyond the provided git history.",
            f"Target: {_target_label(analysis)}",
            "Current code:",
            analysis.target_code,
            "Git commits and diffs:",
            "\n\n---\n\n".join(commit_sections) if commit_sections else "No commits found.",
        ]
    )
