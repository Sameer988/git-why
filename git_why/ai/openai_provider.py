from __future__ import annotations

import os
from importlib.util import find_spec

from git_why.ai.base import AIProvider, ProviderError
from git_why.ai.defaults import DEFAULT_MODELS


MISSING_PACKAGE = (
    "OpenAI provider requires the openai package. "
    "Install it with: pip install git-why[openai]"
)


class OpenAIProvider(AIProvider):
    name = "openai"

    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY")) and find_spec("openai") is not None

    def explain(self, prompt: str, model: str | None = None, analysis=None) -> str:
        if not os.getenv("OPENAI_API_KEY"):
            raise ProviderError("OpenAI provider requires OPENAI_API_KEY.")
        if find_spec("openai") is None:
            raise ProviderError(MISSING_PACKAGE)

        from openai import OpenAI

        try:
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            selected_model = model or DEFAULT_MODELS["openai"]
            if hasattr(client, "responses"):
                response = client.responses.create(model=selected_model, input=prompt)
                output_text = getattr(response, "output_text", None)
                if output_text:
                    return output_text
            response = client.chat.completions.create(
                model=selected_model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc
        return response.choices[0].message.content or ""
