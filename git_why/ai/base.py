from __future__ import annotations


class AIProvider:
    name: str

    def is_available(self) -> bool:
        raise NotImplementedError

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        raise NotImplementedError


class ProviderError(Exception):
    pass
