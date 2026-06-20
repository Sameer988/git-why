from __future__ import annotations

from collections import Counter

from git_why.ai.base import AIProvider
from git_why.diff_analyzer import analyze_corpus, build_diff_explanation, is_weak_message


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
        corpus = analyze_corpus(analysis.commits)
        likely_reason = _likely_reason(analysis, corpus)
        diff_insight = build_diff_explanation(corpus)

        timeline = [
            f"- `{commit.short_hash}`: {commit.message}"
            for commit in reversed(analysis.commits[:8])
        ]

        sections = [
            "# Offline explanation",
            "This is a non-AI explanation generated locally from git history. It uses no API key and makes no internet calls.",
            f"## Target\n\n`{target}`",
            "## Likely reason\n\n" + likely_reason,
        ]

        if diff_insight:
            sections.append("## Diff pattern analysis\n\n" + diff_insight)

        sections += [
            "## Evolution timeline\n\n" + ("\n".join(timeline) if timeline else "No timeline is available."),
            (
                "## Gotchas and limits\n\n"
                "- Offline mode infers intent from commit messages, authorship, dates, and diffs.\n"
                "- It cannot know design discussions, issue context, or review comments that are not in git.\n"
                "- Treat this as a grounded starting point, not a final historical record."
            ),
        ]

        return "\n\n".join(sections)


def _target_label(analysis) -> str:
    if analysis.line_start is None or analysis.line_end is None:
        return analysis.file_path
    if analysis.line_start == analysis.line_end:
        return f"{analysis.file_path}:{analysis.line_start}"
    return f"{analysis.file_path}:{analysis.line_start}-{analysis.line_end}"


def _likely_reason(analysis, corpus) -> str:
    if not analysis.commits:
        return "There is not enough local git history to infer why this code exists."

    # ── Message keyword analysis ──────────────────────────────────────────────
    words: Counter = Counter()
    strong_commits = []
    for commit in analysis.commits:
        if not is_weak_message(commit.message):
            strong_commits.append(commit)
        for raw_word in commit.message.lower().replace("-", " ").split():
            word = raw_word.strip(".,:;()[]{}'\"")
            if len(word) >= 4:
                words[word] += 1

    keywords = [w for w, _ in words.most_common(6)]

    # Use the strongest (non-weak) commit as the anchor, falling back to first.
    anchor = strong_commits[0] if strong_commits else analysis.commits[0]

    pieces: list[str] = []

    # ── Diff-signal-first path (weak messages + diff evidence) ───────────────
    if corpus.weak_message_ratio >= 0.6 and corpus.dominant_patterns:
        patterns_text = " and ".join(corpus.dominant_patterns[:2])
        pieces.append(
            f"Commit messages here are mostly terse, "
            f"but the diffs show code that {patterns_text}."
        )
        if strong_commits:
            pieces.append(
                f"The most descriptive commit is `{anchor.short_hash}`: {anchor.message}."
            )

    # ── Message-first path (normal commit messages) ───────────────────────────
    else:
        pieces.append(f"The strongest local signal is `{anchor.short_hash}`: {anchor.message}.")
        if keywords:
            pieces.append(
                "Recurring commit-message terms include "
                + ", ".join(f"`{kw}`" for kw in keywords)
                + ", which may indicate the recurring concerns behind this code."
            )
        # Augment with diff patterns if they add extra context.
        if corpus.dominant_patterns:
            extra = corpus.dominant_patterns[0]
            pieces.append(f"The diffs also suggest code that {extra}.")

    pieces.append(
        "Review the listed diffs for exact behavior changes; "
        "offline mode avoids inventing context that is not present in git."
    )
    return " ".join(pieces)

