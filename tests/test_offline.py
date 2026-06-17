from git_why.ai.offline import OfflineProvider
from git_why.git_analyzer import CommitInfo, GitAnalysis


def test_offline_provider_is_always_available():
    assert OfflineProvider().is_available() is True


def test_offline_explanation_includes_useful_text():
    analysis = GitAnalysis(
        file_path="src/auth.py",
        line_start=42,
        line_end=42,
        target_code="\u2192     42  return user.is_active",
        commits=[
            CommitInfo(
                hash="abcdef1234567890",
                short_hash="abcdef1234",
                author="Ada",
                date="2026-06-16",
                message="Add active user guard",
                diff="+ return user.is_active",
            )
        ],
        raw_context="context",
    )

    explanation = OfflineProvider().explain("", analysis=analysis)

    assert "Offline explanation" in explanation
    assert "non-AI" in explanation
    assert "src/auth.py:42" in explanation
    assert "abcdef1234" in explanation
    assert "Add active user guard" in explanation
