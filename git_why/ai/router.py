from __future__ import annotations

import os
from importlib.util import find_spec

from git_why.ai.base import AIProvider, ProviderError
from git_why.ai.claude import ClaudeProvider, MISSING_PACKAGE as CLAUDE_MISSING_PACKAGE
from git_why.ai.gemini import GeminiProvider, MISSING_PACKAGE as GEMINI_MISSING_PACKAGE
from git_why.ai.offline import OfflineProvider
from git_why.ai.ollama import OllamaProvider
from git_why.ai.openai_provider import OpenAIProvider, MISSING_PACKAGE as OPENAI_MISSING_PACKAGE
from git_why.ai.openrouter import OpenRouterProvider


VALID_PROVIDERS = ("auto", "offline", "claude", "openai", "gemini", "openrouter", "ollama")


def provider_for(name: str) -> AIProvider:
    normalized = name.lower()
    if normalized not in VALID_PROVIDERS:
        raise ProviderError(
            "Unknown provider. Valid providers: " + ", ".join(VALID_PROVIDERS)
        )
    if normalized == "auto":
        return choose_auto_provider()

    providers: dict[str, AIProvider] = {
        "offline": OfflineProvider(),
        "claude": ClaudeProvider(),
        "openai": OpenAIProvider(),
        "gemini": GeminiProvider(),
        "openrouter": OpenRouterProvider(),
        "ollama": OllamaProvider(),
    }
    provider = providers[normalized]
    if normalized == "offline":
        return provider
    if not provider.is_available():
        raise ProviderError(_unavailable_message(normalized))
    return provider


def choose_auto_provider() -> AIProvider:
    for provider in (
        ClaudeProvider(),
        OpenAIProvider(),
        GeminiProvider(),
        OpenRouterProvider(),
        OllamaProvider(),
    ):
        try:
            if provider.is_available():
                return provider
        except Exception:
            continue
    return OfflineProvider()


def _unavailable_message(name: str) -> str:
    if name == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "Claude provider requires ANTHROPIC_API_KEY."
        if find_spec("anthropic") is None:
            return CLAUDE_MISSING_PACKAGE
        return "Claude provider is not available."
    if name == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            return "OpenAI provider requires OPENAI_API_KEY."
        if find_spec("openai") is None:
            return OPENAI_MISSING_PACKAGE
        return "OpenAI provider is not available."
    if name == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            return "Gemini provider requires GEMINI_API_KEY."
        try:
            has_google_genai = find_spec("google.genai") is not None
        except ModuleNotFoundError:
            has_google_genai = False
        if not has_google_genai:
            return GEMINI_MISSING_PACKAGE
        return "Gemini provider is not available."
    if name == "openrouter":
        return "OpenRouter provider requires OPENROUTER_API_KEY."
    if name == "ollama":
        return "Ollama does not appear to be running. Start it with: ollama serve"
    return "Provider is not available."
