from click.testing import CliRunner

from git_why.ai.offline import OfflineProvider
from git_why.ai.base import ProviderError
from git_why.ai.router import choose_auto_provider, provider_for
from git_why.cli import main


ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
]


def _clear_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_router_chooses_offline_when_no_env_vars_exist(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr("git_why.ai.ollama.requests.get", _offline_ollama)

    provider = choose_auto_provider()

    assert provider.name == "offline"


def test_router_detects_anthropic_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr("git_why.ai.claude.find_spec", lambda name: object())

    provider = choose_auto_provider()

    assert provider.name == "claude"


def test_router_detects_openai_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr("git_why.ai.openai_provider.find_spec", lambda name: object())

    provider = choose_auto_provider()

    assert provider.name == "openai"


def test_router_detects_gemini_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr("git_why.ai.gemini._has_google_genai", lambda: True)

    provider = choose_auto_provider()

    assert provider.name == "gemini"


def test_router_detects_openrouter_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")

    provider = choose_auto_provider()

    assert provider.name == "openrouter"


def test_offline_is_always_available():
    assert OfflineProvider().is_available() is True


def test_cli_help_does_not_require_api_keys(monkeypatch):
    _clear_env(monkeypatch)
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--provider" in result.output
    assert "auto" in result.output


def test_explicit_claude_missing_key_is_clean(monkeypatch):
    _clear_env(monkeypatch)

    try:
        provider_for("claude")
    except ProviderError as exc:
        assert "ANTHROPIC_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected ProviderError")


def test_explicit_claude_missing_package_is_clean(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr("git_why.ai.claude.find_spec", lambda name: None)
    monkeypatch.setattr("git_why.ai.router.find_spec", lambda name: None)

    try:
        provider_for("claude")
    except ProviderError as exc:
        assert "pip install git-why[claude]" in str(exc)
    else:
        raise AssertionError("Expected ProviderError")


def test_router_detects_ollama_when_running(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr("git_why.ai.ollama.requests.get", _running_ollama)

    provider = choose_auto_provider()

    assert provider.name == "ollama"


def _offline_ollama(*args, **kwargs):
    raise RuntimeError("network disabled in test")


class _Response:
    ok = True


def _running_ollama(*args, **kwargs):
    return _Response()
