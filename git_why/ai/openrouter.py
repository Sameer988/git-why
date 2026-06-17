from __future__ import annotations

import os

import requests

from git_why.ai.base import AIProvider, ProviderError
from git_why.ai.defaults import DEFAULT_MODELS


class OpenRouterProvider(AIProvider):
    name = "openrouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def is_available(self) -> bool:
        return bool(os.getenv("OPENROUTER_API_KEY"))

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        if not os.getenv("OPENROUTER_API_KEY"):
            raise ProviderError("OpenRouter provider requires OPENROUTER_API_KEY.")

        selected_model = model or DEFAULT_MODELS["openrouter"]
        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": selected_model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"OpenRouter request failed: {exc}") from exc
        if response.status_code in {400, 404, 422}:
            raise ProviderError(
                f"OpenRouter rejected model '{selected_model}'. Pass --model with a supported model."
            )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"OpenRouter request failed: {exc}") from exc
        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("OpenRouter returned an unexpected response.") from exc
