from __future__ import annotations

import requests

from git_why.ai.base import AIProvider, ProviderError
from git_why.ai.defaults import DEFAULT_MODELS


class OllamaProvider(AIProvider):
    name = "ollama"
    endpoint = "http://localhost:11434/api/generate"

    def is_available(self) -> bool:
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=1)
            return response.ok
        except requests.RequestException:
            return False

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        if not self.is_available():
            raise ProviderError(
                "Ollama does not appear to be running. Start it with: ollama serve"
            )

        selected_model = model or DEFAULT_MODELS["ollama"]
        try:
            response = requests.post(
                self.endpoint,
                json={"model": selected_model, "prompt": prompt, "stream": False},
                timeout=120,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        if response.status_code == 404:
            raise ProviderError(
                f"Ollama is running, but model '{selected_model}' was not found. "
                f"Install it with: ollama pull {selected_model} or pass --model."
            )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            body = response.text.lower()
            if "not found" in body or "model" in body:
                raise ProviderError(
                    f"Ollama is running, but model '{selected_model}' was not found. "
                    f"Install it with: ollama pull {selected_model} or pass --model."
                ) from exc
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        return response.json().get("response", "")
