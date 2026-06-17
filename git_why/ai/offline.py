from __future__ import annotations

from collections import Counter

from git_why.ai.base import AIProvider


class OfflineProvider(AIProvider):
    name = "offline"

    def is_available(self) -> bool:
        return True

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        if analysis is None:
            return (
                "# Offline explanation\n\n"
                "This is a non-AI explanation generated without an API key or internet access.\n\n"
                "No git analysis object was provided."
            )

        target = _target_label(analysis)
        timeline = [
            f"- `{commit.short_hash}`: {commit.message}"
            for commit in reversed(analysis.commits[:8])
        ]
        likely_reason = _likely_reason(analysis)

        return "\n\n".join(
            [
                "# Offline explanation",
                "This is a non-AI explanation generated locally from git history. It uses no API key and makes no internet calls.",
                f"## Target\n\n`{target}`",
                "## Likely reason\n\n" + likely_reason,
                "## Evolution timeline\n\n" + ("\n".join(timeline) if timeline else "No timeline is available."),
                (
                    "## Gotchas and limits\n\n"
                    "- Offline mode infers intent from commit messages, authorship, dates, and diffs.\n"
                    "- It cannot know design discussions, issue context, or review comments that are not in git.\n"
                    "- Treat this as a grounded starting point, not a final historical record."
                ),
            ]
        )


def _target_label(analysis) -> str:
    if analysis.line_start is None or analysis.line_end is None:
        return analysis.file_path
    if analysis.line_start == analysis.line_end:
        return f"{analysis.file_path}:{analysis.line_start}"
    return f"{analysis.file_path}:{analysis.line_start}-{analysis.line_end}"


def _likely_reason(analysis) -> str:
    if not analysis.commits:
        return "There is not enough local git history to infer why this code exists."

    words = Counter()
    for commit in analysis.commits:
        for raw_word in commit.message.lower().replace("-", " ").split():
            word = raw_word.strip(".,:;()[]{}'\"")
            if len(word) >= 4:
                words[word] += 1

    keywords = [word for word, _ in words.most_common(6)]
    first = analysis.commits[0]
    pieces = [
        f"The strongest local signal is `{first.short_hash}`: {first.message}.",
    ]
    if keywords:
        pieces.append(
            "Recurring commit-message terms include "
            + ", ".join(f"`{keyword}`" for keyword in keywords)
            + ", which may indicate the recurring concerns behind this code."
        )
    pieces.append(
        "Review the listed diffs for exact behavior changes; offline mode avoids inventing context that is not present in git."
    )
    return " ".join(pieces)
