from collections.abc import Iterator
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from app.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@lru_cache
def _client():
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set. Put it in .env (local) or the Space secrets (deploy).")
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


# model name -> index of the thinking option that worked
_thinking_choice: dict[str, int] = {}


def _thinking_options():
    from google.genai import types

    return [
        types.ThinkingConfig(thinking_level=settings.thinking_level),  # Gemini 3.x
        types.ThinkingConfig(thinking_budget=0),                         # Gemini 2.5 Flash / Lite
        None,                                                            # model default
    ]


def _with_thinking_fallback(model: str, call):
    """Run call(thinking_config), falling back if the model rejects that thinking option."""
    options = _thinking_options()
    start = _thinking_choice.get(model, 0)
    last_exc = None
    for i in range(start, len(options)):
        try:
            result = call(options[i])
            _thinking_choice[model] = i
            return result
        except Exception as exc:
            msg = str(exc).lower()
            if "thinking" in msg or "budget" in msg or "level" in msg:
                last_exc = exc
                continue
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
    raise LLMError(f"{type(last_exc).__name__}: {last_exc}") from last_exc


def generate_json(system: str, prompt: str, schema: type[T], temperature: float | None = None,
                  model: str | None = None) -> T:
    """Ask Gemini for output that must match a Pydantic schema (structured output)."""
    from google.genai import types

    model = model or settings.gemini_model

    def call(thinking):
        return _client().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=settings.llm_temperature if temperature is None else temperature,
                response_mime_type="application/json",
                response_schema=schema,
                thinking_config=thinking,
            ),
        )

    response = _with_thinking_fallback(model, call)
    if response.parsed is not None:
        return response.parsed
    try:
        return schema.model_validate_json(response.text or "")
    except Exception as exc:
        raise LLMError(f"Could not parse model output: {exc}") from exc


def stream_text(system: str, prompt: str, model: str | None = None) -> Iterator[str]:
    """Stream plain-text output chunk by chunk."""
    from google.genai import types

    model = model or settings.gemini_model

    def call(thinking):
        stream = _client().models.generate_content_stream(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=settings.llm_temperature,
                thinking_config=thinking,
            ),
        )
        # Pull the first chunk inside the fallback so a rejected thinking option raises here.
        iterator = iter(stream)
        first = next(iterator, None)
        return first, iterator

    first, iterator = _with_thinking_fallback(model, call)
    try:
        if first is not None and first.text:
            yield first.text
        for chunk in iterator:
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
