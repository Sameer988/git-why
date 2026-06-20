"""
Diff heuristics for git-why's offline explainer.

Analyzes the actual code changes (added/removed lines, co-changed files,
cross-commit patterns) to infer *why* code exists even when commit messages
are useless ("fix", "update", "WIP", etc.).

These signals layer on top of — not replace — commit message analysis.
A bad message + a revealing diff = a useful explanation.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


# ─── Weak message detection ────────────────────────────────────────────────────

_WEAK = re.compile(
    r'^(fix(es|ed)?|update[sd]?|change[sd]?|wip|refactor(ed|ing)?|cleanup|'
    r'clean\s?up|minor|misc|temp|revert|merge|bump|feat|chore|style|'
    r'hotfix|patch|tweak[sd]?|stuff|things?|work|done|test|debug|typo|'
    r'remove[sd]?|add(ed|s)?|more|some|small|quick)\.?$',
    re.IGNORECASE,
)

_STOPWORDS = frozenset({
    "the", "and", "for", "that", "with", "this", "from", "have",
    "been", "will", "when", "were", "also", "into", "some", "more",
    "than", "they", "them", "then", "what", "which", "where", "about",
    "after", "before", "should", "could", "would", "there", "these",
    "those", "such", "just", "only", "very", "much", "most", "over",
    "back", "each", "make", "made", "well", "both", "call", "good",
    "need", "does", "done", "upon", "used", "many", "same", "even",
    "still", "might", "case", "code", "file", "line", "lines", "type",
    "name", "part", "end", "now", "new", "old", "get", "set",
})


def is_weak_message(message: str) -> bool:
    """Return True if a commit message conveys little meaningful intent."""
    stripped = message.strip()
    if len(stripped) < 15:
        return True
    first_word = stripped.split()[0].rstrip(":")
    if _WEAK.match(first_word):
        # Weak first word AND short total message → weak
        return len(stripped) < 40
    return False


# ─── Diff pattern matchers ─────────────────────────────────────────────────────

@dataclass
class _Pattern:
    label: str
    description: str
    regex: re.Pattern
    weight: float = 1.0  # relative importance for the explanation


# Each pattern is matched against *added* lines only (+lines in unified diff).
_ADDED_PATTERNS: list[_Pattern] = [
    _Pattern(
        "null-guard",
        "guards against null/missing values",
        re.compile(r'\b(is\s+None|is\s+not\s+None|if\s+not\s+\w|== None|!= None|'
                   r'isinstance\(.*None|Optional\[|null\s*check|nil\s*check)', re.IGNORECASE),
        weight=1.5,
    ),
    _Pattern(
        "error-handling",
        "adds error handling or defensive programming",
        re.compile(r'\b(try:|except\s|catch\s|rescue\s|raise\s|throw\s|'
                   r'Error\(|Exception\(|ValueError|TypeError|KeyError|'
                   r'RuntimeError|OSError|IOError)', re.IGNORECASE),
        weight=1.5,
    ),
    _Pattern(
        "early-return",
        "short-circuits execution via early return",
        re.compile(r'\breturn\s+(False|None|\[\]|\{\}|\"\"|\'\')|\bbreak\b|\bcontinue\b'),
        weight=1.2,
    ),
    _Pattern(
        "timeout",
        "adds timeout or deadline handling",
        re.compile(r'\btimeout\b|\bdeadline\b|\bmax_wait\b|\bwait_for\b', re.IGNORECASE),
        weight=1.3,
    ),
    _Pattern(
        "retry-resilience",
        "adds retry logic or resilience against transient failures",
        re.compile(r'\bretry\b|\bbackoff\b|\battempts?\b|\bmax_retries\b', re.IGNORECASE),
        weight=1.3,
    ),
    _Pattern(
        "concurrency",
        "adds concurrency control (locks, mutexes, thread safety)",
        re.compile(r'\block\b|\bmutex\b|\bsemaphore\b|\bthread\b|\basync\b|\bawait\b|'
                   r'\batomic\b|\bsynchronized\b', re.IGNORECASE),
        weight=1.4,
    ),
    _Pattern(
        "caching",
        "adds caching or memoization",
        re.compile(r'\bcache\b|\bmemo(ize)?\b|\b_cache\b|\blru_cache\b|\b@cache\b', re.IGNORECASE),
        weight=1.2,
    ),
    _Pattern(
        "logging",
        "adds logging or observability",
        re.compile(r'\b(logger\.|logging\.|log\.|console\.log|print\(|warn\(|'
                   r'debug\(|info\(|error\(|trace\()', re.IGNORECASE),
        weight=0.8,
    ),
    _Pattern(
        "assertion",
        "enforces contracts via assertions",
        re.compile(r'\bassert\b|\bAssertionError\b|\bprecondition\b|\bexpect\(', re.IGNORECASE),
        weight=1.1,
    ),
    _Pattern(
        "deprecation",
        "marks or replaces deprecated behavior",
        re.compile(r'\bdeprecated?\b|\blegacy\b|\bbackward[s]?\s+compat', re.IGNORECASE),
        weight=1.3,
    ),
    _Pattern(
        "rate-limiting",
        "adds rate limiting or throttling",
        re.compile(r'rate.?limit|throttl|quota|too.many.requests|RateLimitError|429', re.IGNORECASE),
        weight=1.4,
    ),
    _Pattern(
        "auth-security",
        "adds authentication or security checks",
        re.compile(r'\bauth(entication|orization|orize|enticate)?\b|\bpermission\b|'
                   r'\btoken\b|\bjwt\b|\bsecret\b|\bsanitize\b|\bescape\b', re.IGNORECASE),
        weight=1.4,
    ),
    _Pattern(
        "validation",
        "validates input or data shape",
        re.compile(r'\bvalidat(e|ion|or)\b|\bschema\b|\bpars(e|ing)\b|\btype.check\b|'
                   r'\bisinstance\b|\bgetattr\b', re.IGNORECASE),
        weight=1.2,
    ),
    _Pattern(
        "off-by-one",
        "adjusts boundary conditions (possible off-by-one fix)",
        re.compile(r'[+\-]\s*1\b|<= |>= |\b(len|count|size|length)\s*[-+]\s*1'),
        weight=1.0,
    ),
    _Pattern(
        "config-flag",
        "adds a feature flag or configuration toggle",
        re.compile(r'\bfeature.?flag\b|\bff\b|\bconfig\b|\benv\b|\bsetting\b|'
                   r'\bos\.environ\b|\bgetenv\b', re.IGNORECASE),
        weight=1.1,
    ),
]

# Patterns matched against *removed* lines (- lines).
_REMOVED_PATTERNS: list[_Pattern] = [
    _Pattern(
        "tech-debt-resolved",
        "resolves a known TODO or technical debt item",
        re.compile(r'\b(TODO|FIXME|HACK|XXX|BUG|TEMP)\b'),
        weight=1.4,
    ),
]

# File-type signals from co-changed files in the same commit.
_COCHANGE_SIGNALS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'test[_s/]|_test\.|spec[_s/]|_spec\.', re.IGNORECASE), "test coverage added"),
    (re.compile(r'docs?/|README|CHANGELOG|\.md$', re.IGNORECASE), "documentation updated alongside"),
    (re.compile(r'migration|schema|\.sql$', re.IGNORECASE), "database schema change"),
    (re.compile(r'requirements|package\.json|Cargo\.toml|go\.mod|pom\.xml', re.IGNORECASE), "dependency change"),
    (re.compile(r'\.ya?ml$|\.toml$|\.json$|config', re.IGNORECASE), "configuration change"),
    (re.compile(r'Dockerfile|docker-compose|\.containerfile', re.IGNORECASE), "infrastructure change"),
]


# ─── Analysis dataclasses ──────────────────────────────────────────────────────

@dataclass
class DiffSignals:
    """Semantic signals extracted from a single commit's diff."""
    commit_short_hash: str
    commit_message: str
    message_is_weak: bool
    matched_patterns: list[str] = field(default_factory=list)     # pattern labels
    pattern_descriptions: list[str] = field(default_factory=list) # human descriptions
    co_changed_files: list[str] = field(default_factory=list)
    co_change_signals: list[str] = field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    total_weight: float = 0.0


@dataclass
class CorpusSignals:
    """Aggregate signals across all commits touching the target."""
    commit_signals: list[DiffSignals] = field(default_factory=list)
    dominant_patterns: list[str] = field(default_factory=list)    # top pattern descriptions
    all_co_change_signals: list[str] = field(default_factory=list)
    weak_message_ratio: float = 0.0
    num_authors: int = 0
    churn: int = 0  # total added + removed lines
    has_any_diff_signal: bool = False


# ─── Core analysis ────────────────────────────────────────────────────────────

def _parse_diff(diff_text: str) -> tuple[list[str], list[str], list[str]]:
    """Split unified diff into (added_lines, removed_lines, file_headers)."""
    added, removed, headers = [], [], []
    for line in diff_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("diff "):
            headers.append(line)
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    return added, removed, headers


def _co_changed_files(diff_text: str) -> list[str]:
    """Extract file paths changed in the same commit."""
    files = []
    for line in diff_text.splitlines():
        m = re.match(r'^diff --git a/(.+) b/(.+)$', line)
        if m:
            files.append(m.group(2))
    return files


def analyze_diff(commit) -> DiffSignals:
    """Extract semantic signals from a single CommitInfo's diff."""
    added, removed, _ = _parse_diff(commit.diff)
    co_files = _co_changed_files(commit.diff)
    message_weak = is_weak_message(commit.message)

    signals = DiffSignals(
        commit_short_hash=commit.short_hash,
        commit_message=commit.message,
        message_is_weak=message_weak,
        co_changed_files=co_files,
        added_lines=len(added),
        removed_lines=len(removed),
    )

    added_text = "\n".join(added)
    removed_text = "\n".join(removed)

    for pattern in _ADDED_PATTERNS:
        if pattern.regex.search(added_text):
            signals.matched_patterns.append(pattern.label)
            signals.pattern_descriptions.append(pattern.description)
            signals.total_weight += pattern.weight

    for pattern in _REMOVED_PATTERNS:
        if pattern.regex.search(removed_text):
            signals.matched_patterns.append(pattern.label)
            signals.pattern_descriptions.append(pattern.description)
            signals.total_weight += pattern.weight

    for regex, label in _COCHANGE_SIGNALS:
        for f in co_files:
            if regex.search(f):
                if label not in signals.co_change_signals:
                    signals.co_change_signals.append(label)

    return signals


def analyze_corpus(commits: list) -> CorpusSignals:
    """Aggregate diff signals across all commits touching the target."""
    corpus = CorpusSignals()

    if not commits:
        return corpus

    all_signals: list[DiffSignals] = []
    pattern_weights: Counter = Counter()
    co_signals: set[str] = set()
    authors: set[str] = set()
    weak_count = 0

    for commit in commits:
        sig = analyze_diff(commit)
        all_signals.append(sig)
        authors.add(commit.author)
        if sig.message_is_weak:
            weak_count += 1
        corpus.churn += sig.added_lines + sig.removed_lines
        for label, desc in zip(sig.matched_patterns, sig.pattern_descriptions):
            pattern_weights[label] += 1
        for cs in sig.co_change_signals:
            co_signals.add(cs)

    corpus.commit_signals = all_signals
    corpus.num_authors = len(authors)
    corpus.weak_message_ratio = weak_count / len(commits)
    corpus.all_co_change_signals = sorted(co_signals)
    corpus.has_any_diff_signal = bool(pattern_weights)

    # Map labels back to descriptions for the top patterns.
    label_to_desc: dict[str, str] = {}
    for sig in all_signals:
        for label, desc in zip(sig.matched_patterns, sig.pattern_descriptions):
            label_to_desc[label] = desc

    top = [label for label, _ in pattern_weights.most_common(4)]
    corpus.dominant_patterns = [label_to_desc[t] for t in top if t in label_to_desc]

    return corpus


# ─── Explanation builder ───────────────────────────────────────────────────────

def build_diff_explanation(corpus: CorpusSignals) -> str | None:
    """
    Build a human-readable explanation from corpus diff signals.
    Returns None if there are no meaningful signals to report.
    """
    if not corpus.has_any_diff_signal and not corpus.all_co_change_signals:
        return None

    parts: list[str] = []

    if corpus.dominant_patterns:
        if len(corpus.dominant_patterns) == 1:
            parts.append(f"The diffs consistently show code that {corpus.dominant_patterns[0]}.")
        else:
            pattern_list = "; ".join(corpus.dominant_patterns[:-1])
            parts.append(
                f"The diffs reveal code that {pattern_list}; "
                f"and {corpus.dominant_patterns[-1]}."
            )

    if corpus.all_co_change_signals:
        cochange = " and ".join(corpus.all_co_change_signals)
        parts.append(f"The same commits also show {cochange}.")

    if corpus.num_authors > 2:
        parts.append(
            f"This code has been touched by {corpus.num_authors} different authors, "
            "suggesting it has been a recurring area of attention."
        )

    if corpus.weak_message_ratio >= 0.6:
        parts.append(
            "Most commit messages here are terse or generic — "
            "the diff patterns above are more reliable than the message keywords."
        )

    return " ".join(parts) if parts else None
