from __future__ import annotations

import os
from importlib.util import find_spec

from git_why.ai.base import AIProvider, ProviderError
from git_why.ai.defaults import DEFAULT_MODELS


MISSING_PACKAGE = (
    "Gemini provider requires the google-genai package. "
    "Install it with: pip install git-why[gemini]"
)


class GeminiProvider(AIProvider):
    name = "gemini"

    def is_available(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY")) and _has_google_genai()

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        if not os.getenv("GEMINI_API_KEY"):
            raise ProviderError("Gemini provider requires GEMINI_API_KEY.")
        if not _has_google_genai():
            raise ProviderError(MISSING_PACKAGE)

        from google import genai

        try:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            response = client.models.generate_content(
                model=model or DEFAULT_MODELS["gemini"],
                contents=prompt,
            )
        except Exception as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc
        return getattr(response, "text", "") or ""


def _has_google_genai() -> bool:
    try:
        return find_spec("google.genai") is not None
    except ModuleNotFoundError:
        return False
