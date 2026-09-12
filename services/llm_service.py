"""Gemini access: single client, bounded concurrency, retries, structured JSON output."""
import hashlib
import json
import re
import threading
from typing import TypeVar

from pydantic import BaseModel, ValidationError

import config
from services.cache_service import llm_cache
from utils.logging import get_logger
from utils.retry import retry

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Gemini call failed after retries (or is not configured)."""


class LLMParseError(LLMError):
    """Gemini responded but the payload could not be parsed into the schema."""


_client = None
_client_lock = threading.Lock()
_semaphore = threading.BoundedSemaphore(max(1, config.GEMINI_MAX_CONCURRENT_REQUESTS))


def is_configured() -> bool:
    return bool(config.GEMINI_API_KEY)


def get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not config.GEMINI_API_KEY:
                    raise LLMError("GEMINI_API_KEY is not set. Add it to your .env file.")
                from google import genai
                from google.genai import types

                _client = genai.Client(
                    api_key=config.GEMINI_API_KEY,
                    http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_SECONDS * 1000),
                )
    return _client


def _status_code(exc: Exception) -> int | None:
    for attr in ("code", "status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(k in msg for k in ("spending cap", "billing", "quota exceeded for", "api key not valid", "permission denied")):
        return False
    code = _status_code(exc)
    if code in (408, 429, 500, 502, 503, 504):
        return True
    return any(k in msg for k in ("resource_exhausted", "unavailable", "timeout", "timed out",
                                  "deadline", "overloaded", "connection reset", "503", "429"))


def _cache_key(model: str, schema_name: str, system: str | None, prompt: str) -> str:
    return hashlib.sha256(f"{model}|{schema_name}|{system or ''}|{prompt}".encode()).hexdigest()


def _extract_json_block(text: str) -> str:
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def _fallback_parse(text: str, schema: type[T]) -> T:
    block = _extract_json_block(text)
    try:
        return schema.model_validate(json.loads(block))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMParseError(f"Could not parse {schema.__name__} from model output: {exc}") from exc


def _call(prompt: str, config_obj):
    client = get_client()
    with _semaphore:
        return retry(
            lambda: client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt, config=config_obj),
            attempts=config.GEMINI_MAX_RETRIES,
            base_delay=config.GEMINI_RETRY_BASE_DELAY,
            retry_on=_is_retryable,
            on_retry=lambda n, e, d: log.warning("Gemini retry %s in %.1fs: %s", n, d, str(e)[:120]),
        )


def generate_structured(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    temperature: float | None = None,
    use_cache: bool = True,
) -> T:
    """Ask Gemini for JSON matching `schema`; returns a validated model instance."""
    from google.genai import types

    key = _cache_key(config.GEMINI_MODEL, schema.__name__, system, prompt)
    if use_cache:
        cached = llm_cache.get(key)
        if cached is not None:
            return schema.model_validate(cached)

    gen_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=config.GEMINI_TEMPERATURE if temperature is None else temperature,
        system_instruction=system,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = _call(prompt, gen_config)
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Gemini request failed: {str(exc)[:300]}") from exc

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        result = parsed
    else:
        text = getattr(response, "text", None) or ""
        if not text.strip():
            raise LLMParseError("Gemini returned an empty response.")
        result = _fallback_parse(text, schema)

    if use_cache:
        llm_cache.set(key, result.model_dump())
    return result


def generate_text(prompt: str, *, system: str | None = None, temperature: float | None = None) -> str:
    from google.genai import types

    gen_config = types.GenerateContentConfig(
        temperature=config.GEMINI_TEMPERATURE if temperature is None else temperature,
        system_instruction=system,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = _call(prompt, gen_config)
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Gemini request failed: {str(exc)[:300]}") from exc
    return (getattr(response, "text", None) or "").strip()
