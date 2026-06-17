from __future__ import annotations

import os
from importlib.util import find_spec

from git_why.ai.base import AIProvider, ProviderError
from git_why.ai.defaults import DEFAULT_MODELS


MISSING_PACKAGE = (
    "Claude provider requires the anthropic package. "
    "Install it with: pip install git-why[claude]"
)


class ClaudeProvider(AIProvider):
    name = "claude"

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY")) and find_spec("anthropic") is not None

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ProviderError("Claude provider requires ANTHROPIC_API_KEY.")
        if find_spec("anthropic") is None:
            raise ProviderError(MISSING_PACKAGE)

        from anthropic import Anthropic

        try:
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            response = client.messages.create(
                model=model or DEFAULT_MODELS["claude"],
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise ProviderError(f"Claude request failed: {exc}") from exc
        parts = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
