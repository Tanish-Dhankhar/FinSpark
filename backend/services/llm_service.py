"""
LLM Service — Local Qwen via LM Studio
Centralized wrapper for the LM Studio generation API (OpenAI-compatible).

Key design decisions:
  - Uses openai Python SDK pointed at LM Studio's local server (http://127.0.0.1:1234/v1).
  - JSON enforcement via response_format={"type": "json_object"} where supported,
    with 4-tier fallback recovery for robustness.
  - Retry loop with short fixed delays for transient connection errors.
  - Per-call max_tokens override supported to cap output length per stage.
"""
import json
import time
import traceback
from typing import Optional

from openai import OpenAI

from backend.config import (
    LM_STUDIO_BASE_URL,
    LM_STUDIO_MODEL,
    LM_STUDIO_API_KEY,
    LM_TEMPERATURE,
    LM_MAX_OUTPUT_TOKENS,
)


# ── Singleton client -----------------------------------------------------------

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Lazy-init the LM Studio OpenAI-compatible client."""
    global _client
    if _client is None:
        _client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key=LM_STUDIO_API_KEY)
    return _client


# ── Core LLM call -------------------------------------------------------------

def call_llm(
    prompt: str,
    system_instruction: Optional[str] = None,
    expect_json: bool = False,
    max_retries: int = 3,
    model: Optional[str] = None,
    max_tokens_override: Optional[int] = None,
) -> str:
    """
    Make a single LLM call to LM Studio (Qwen via OpenAI-compatible API).

    Args:
        prompt:              The user-turn prompt text.
        system_instruction:  Optional system prompt.
        expect_json:         If True, request JSON output via response_format.
        max_retries:         Retry attempts on transient connection errors.
        model:               Optional model override (defaults to LM_STUDIO_MODEL).
        max_tokens_override: If set, use this instead of LM_MAX_OUTPUT_TOKENS.

    Returns:
        The model's text response (stripped).
    """
    client = _get_client()
    max_tokens = max_tokens_override or LM_MAX_OUTPUT_TOKENS

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model or LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": LM_TEMPERATURE,
        "max_tokens": max_tokens,
    }
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip()
            else:
                raise ValueError(f"Empty response from model (attempt {attempt + 1})")

        except Exception as e:
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in [
                "connection", "timeout", "unavailable", "server error",
                "500", "503", "429", "resource_exhausted",
            ])
            if is_retryable and attempt < max_retries - 1:
                wait = 2 * (attempt + 1)  # 2s, 4s, 6s
                print(f"  [LLM] Transient error, retrying in {wait}s (attempt {attempt + 1}): {e}")
                time.sleep(wait)
                continue
            print(f"  [LLM] Call failed after {attempt + 1} attempt(s): {e}")
            traceback.print_exc()
            raise


# ── JSON-mode wrapper ---------------------------------------------------------

def call_llm_json(
    prompt: str,
    system_instruction: Optional[str] = None,
    max_retries: int = 3,
    max_tokens_override: Optional[int] = None,
) -> dict:
    """
    Make an LLM call and parse the response as JSON.
    Uses 4-tier recovery to handle imperfect model outputs.

    Returns:
        Parsed JSON as a dict (or list wrapped in dict under '_repaired_list').
    """
    raw = call_llm(
        prompt=prompt,
        system_instruction=system_instruction,
        expect_json=True,
        max_retries=max_retries,
        max_tokens_override=max_tokens_override,
    )
    return _parse_json_response(raw)


# ── JSON recovery pipeline ----------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """
    Parse JSON from LLM response with 4-tier recovery.

    Recovery order:
      1. Direct json.loads()
      2. Strip markdown code fences (``` or ```json)
      3. json_repair library (handles truncated/malformed JSON)
      4. Partial walk-back: find last syntactically-closed object
      5. Hard failure with diagnostic context
    """
    if not raw or not raw.strip():
        raise ValueError("LLM returned an empty response.")

    # -- 1. Direct parse -------------------------------------------------------
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # -- 2. Strip markdown code fences ----------------------------------------
    for fence in ("```json", "```"):
        if fence in raw:
            try:
                start = raw.index(fence) + len(fence)
                newline = raw.index("\n", start)
                start = newline + 1
                end = raw.index("```", start)
                candidate = raw[start:end].strip()
                return json.loads(candidate)
            except (ValueError, json.JSONDecodeError):
                pass

    # -- 3. json_repair (handles truncated JSON gracefully) -------------------
    try:
        from json_repair import repair_json  # type: ignore
        repaired = repair_json(raw, return_objects=True)
        if isinstance(repaired, (dict, list)):
            print("  [LLM] JSON was repaired (response may have been truncated by token limit).")
            return repaired if isinstance(repaired, dict) else {"_repaired_list": repaired}
    except ImportError:
        pass  # json_repair not installed — fall through

    # -- 4. Partial walk-back: salvage last complete JSON object --------------
    for cutoff in range(len(raw), 0, -1):
        candidate = raw[:cutoff].rstrip()
        for closer in ("", "}", "}]}", "}]}\n}"):
            try:
                result = json.loads(candidate + closer)
                if isinstance(result, dict) and result:
                    print(
                        f"  [LLM] JSON truncated at token limit — recovered partial response "
                        f"({cutoff}/{len(raw)} chars). Some fields may be missing."
                    )
                    return result
            except json.JSONDecodeError:
                continue
        # Only scan the last 200 chars before giving up (avoid O(n^2) on huge strings)
        if len(raw) - cutoff > 200:
            break

    raise ValueError(
        f"Could not parse JSON from LLM response. "
        f"Response may have been truncated ({len(raw)} chars). "
        f"First 500 chars:\n{raw[:500]}"
    )
