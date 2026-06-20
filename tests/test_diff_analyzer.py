"""Tests for the diff heuristics analyzer."""
from __future__ import annotations

from git_why.diff_analyzer import (
    CorpusSignals,
    analyze_corpus,
    analyze_diff,
    build_diff_explanation,
    is_weak_message,
)


# ─── is_weak_message ──────────────────────────────────────────────────────────

def test_weak_message_single_word_fix():
    assert is_weak_message("fix") is True


def test_weak_message_short_with_weak_verb():
    assert is_weak_message("update deps") is True


def test_weak_message_wip():
    assert is_weak_message("WIP") is True


def test_weak_message_descriptive():
    assert is_weak_message("Handle expired session tokens to prevent stale auth") is False


def test_weak_message_medium_length_descriptive():
    assert is_weak_message("Add null check for missing session token") is False


def test_weak_message_chore_short():
    assert is_weak_message("chore") is True


def test_weak_message_chore_long():
    # Long chore message with real content is not weak.
    assert is_weak_message("chore: upgrade all test dependencies to latest stable versions") is False


# ─── Fake commit helper ───────────────────────────────────────────────────────

class _Commit:
    def __init__(self, message: str, diff: str = "", short_hash: str = "abc123"):
        self.message = message
        self.diff = diff
        self.short_hash = short_hash
        self.author = "Test Author"


def _make_diff(added: list[str], removed: list[str] | None = None, files: list[str] | None = None) -> str:
    """Build a minimal unified diff string for testing."""
    lines = []
    for f in (files or ["src/auth.py"]):
        lines.append(f"diff --git a/{f} b/{f}")
        lines.append(f"--- a/{f}")
        lines.append(f"+++ b/{f}")
        lines.append("@@ -1,3 +1,5 @@")
    for line in (removed or []):
        lines.append(f"-{line}")
    for line in added:
        lines.append(f"+{line}")
    return "\n".join(lines)


# ─── analyze_diff — pattern detection ────────────────────────────────────────

def test_detects_null_guard():
    diff = _make_diff(["    if user is None:", "        return False"])
    commit = _Commit("fix", diff)
    sig = analyze_diff(commit)
    assert "null-guard" in sig.matched_patterns
    assert "early-return" in sig.matched_patterns


def test_detects_error_handling():
    diff = _make_diff(["    try:", "        do_thing()", "    except ValueError:"])
    sig = analyze_diff(_Commit("wip", diff))
    assert "error-handling" in sig.matched_patterns


def test_detects_timeout():
    diff = _make_diff(["    response = requests.get(url, timeout=30)"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "timeout" in sig.matched_patterns


def test_detects_tech_debt_resolved():
    diff = _make_diff([], removed=["    # TODO: remove this after migration"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "tech-debt-resolved" in sig.matched_patterns


def test_detects_retry():
    diff = _make_diff(["    for attempt in range(max_retries):"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "retry-resilience" in sig.matched_patterns


def test_detects_concurrency():
    diff = _make_diff(["    with lock:", "        shared_state.update()"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "concurrency" in sig.matched_patterns


def test_detects_caching():
    diff = _make_diff(["    @lru_cache(maxsize=128)", "    def expensive():"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "caching" in sig.matched_patterns


def test_detects_auth():
    diff = _make_diff(["    if not user.token:", "        raise AuthenticationError()"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "auth-security" in sig.matched_patterns


def test_detects_rate_limiting():
    diff = _make_diff(["    if self.rate_limit_exceeded():"])
    sig = analyze_diff(_Commit("update", diff))
    assert "rate-limiting" in sig.matched_patterns


def test_no_false_positives_on_clean_code():
    diff = _make_diff(["    return result * 2", "    total = sum(values)"])
    sig = analyze_diff(_Commit("Add calculation helper", diff))
    assert sig.matched_patterns == []


def test_cochange_detects_test_file():
    diff = _make_diff(["    pass"], files=["src/auth.py", "tests/test_auth.py"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "test coverage added" in sig.co_change_signals


def test_cochange_detects_docs():
    diff = _make_diff(["    pass"], files=["src/auth.py", "docs/authentication.md"])
    sig = analyze_diff(_Commit("fix", diff))
    assert "documentation updated alongside" in sig.co_change_signals


def test_message_weakness_flag():
    sig = analyze_diff(_Commit("fix", _make_diff([])))
    assert sig.message_is_weak is True

    sig2 = analyze_diff(_Commit("Add null check for missing session token", _make_diff([])))
    assert sig2.message_is_weak is False


def test_line_counts():
    diff = _make_diff(["line1", "line2"], removed=["old"])
    sig = analyze_diff(_Commit("fix", diff))
    assert sig.added_lines == 2
    assert sig.removed_lines == 1


# ─── analyze_corpus ───────────────────────────────────────────────────────────

def test_corpus_dominant_patterns():
    null_diff = _make_diff(["    if x is None:", "        return False"])
    commits = [_Commit("fix", null_diff) for _ in range(3)]
    corpus = analyze_corpus(commits)
    assert corpus.has_any_diff_signal is True
    assert any("null" in p.lower() for p in corpus.dominant_patterns)


def test_corpus_weak_message_ratio():
    commits = [
        _Commit("fix", ""),
        _Commit("update", ""),
        _Commit("Add proper null check for expired tokens", ""),
    ]
    corpus = analyze_corpus(commits)
    assert abs(corpus.weak_message_ratio - 2 / 3) < 0.01


def test_corpus_author_count():
    commits = [
        _Commit("fix", ""),
        _Commit("fix", ""),
    ]
    commits[0].author = "Alice"
    commits[1].author = "Bob"
    corpus = analyze_corpus(commits)
    assert corpus.num_authors == 2


def test_corpus_empty_commits():
    corpus = analyze_corpus([])
    assert corpus.has_any_diff_signal is False
    assert corpus.dominant_patterns == []


def test_corpus_churn():
    diff = _make_diff(["a", "b", "c"], removed=["x"])
    corpus = analyze_corpus([_Commit("fix", diff)])
    assert corpus.churn == 4  # 3 added + 1 removed


# ─── build_diff_explanation ───────────────────────────────────────────────────

def test_build_explanation_returns_none_no_signals():
    corpus = CorpusSignals()
    assert build_diff_explanation(corpus) is None


def test_build_explanation_with_patterns():
    null_diff = _make_diff(["    if x is None:", "        return False"])
    corpus = analyze_corpus([_Commit("fix", null_diff)])
    explanation = build_diff_explanation(corpus)
    assert explanation is not None
    assert "null" in explanation.lower() or "guard" in explanation.lower()


def test_build_explanation_mentions_cochange():
    diff = _make_diff(["    pass"], files=["auth.py", "tests/test_auth.py"])
    corpus = analyze_corpus([_Commit("fix", diff)])
    explanation = build_diff_explanation(corpus)
    assert explanation is not None
    assert "test" in explanation.lower()


def test_build_explanation_mentions_weak_message_note():
    null_diff = _make_diff(["    if x is None:", "        return False"])
    commits = [_Commit("fix", null_diff) for _ in range(4)]
    corpus = analyze_corpus(commits)
    explanation = build_diff_explanation(corpus)
    assert explanation is not None
    assert "terse" in explanation.lower() or "generic" in explanation.lower()


def test_build_explanation_multi_pattern_sentence():
    diff = _make_diff([
        "    if token is None:",
        "        return False",
        "    try:",
        "        verify(token)",
        "    except ValueError:",
        "        raise AuthError()",
    ])
    corpus = analyze_corpus([_Commit("fix", diff)])
    explanation = build_diff_explanation(corpus)
    assert explanation is not None
    assert len(explanation) > 30
