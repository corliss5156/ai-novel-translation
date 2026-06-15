from __future__ import annotations

import os
from typing import Final, Literal

from openai import OpenAI


ModelName = Literal["gpt-5.4-nano", "gpt-5.4-mini"]

NANO_MODEL: Final[ModelName] = "gpt-5.4-nano"
MINI_MODEL: Final[ModelName] = "gpt-5.4-mini"
WORKFLOW_MODELS: Final[str] = (
    f"glossary:{NANO_MODEL},translator:{MINI_MODEL},editor:{NANO_MODEL}"
)


def _api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is required")
    return api_key


_client = OpenAI(api_key=_api_key())


def get_client() -> OpenAI:
    """Return the shared OpenAI client singleton."""
    return _client


def invoke(prompt: str, model: ModelName) -> str:
    """Generate text with the shared model using the Responses API."""
    response = _client.responses.create(
        model=model,
        reasoning={"effort": "none"},
        input=prompt,
    )
    return response.output_text
