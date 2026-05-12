"""
LLM Service — Local Inference via LM Studio
Centralized wrapper for the OpenAI-compatible LM Studio server.

Key design decisions:
  - JSON enforcement is done via system-prompt instruction, NOT response_format.
    LM Studio (as of current builds) rejects json_object mode; system-prompt
    enforcement was confirmed to work reliably in testing.
  - 4-tier JSON recovery: direct parse -> strip fences -> json_repair -> partial walk-back.
  - Retry loop with short fixed delays (no exponential backoff — local server
    doesn't rate-limit, so fast retries are correct).
  - Per-call max_tokens override is supported to cap output length per stage.
"""
import json
import time
import traceback
from typing import Optional

from openai import OpenAI, APIConnectionError, APIStatusError
from langsmith import traceable

from backend.config import (
    LM_STUDIO_BASE_URL,
    LM_STUDIO_API_KEY,
    LM_STUDIO_MODEL,
    LM_STUDIO_TEMPERATURE,
    LM_STUDIO_MAX_OUTPUT_TOKENS,
)


# -- Singleton client ---------------------------------------------------------

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Lazy-init the LM Studio OpenAI-compatible client."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=LM_STUDIO_BASE_URL,
            api_key=LM_STUDIO_API_KEY,
        )
    return _client


# -- JSON system-prompt prefix ------------------------------------------------
# Prepended to any system instruction when expect_json=True.
# This is the only reliable JSON enforcement mechanism on LM Studio.
_JSON_PREAMBLE = (
    "IMPORTANT: You MUST respond with valid JSON only. "
    "Do NOT include any markdown code fences (no ``` or ```json). "
    "Do NOT include any explanation before or after the JSON. "
    "Your entire response must be parseable by json.loads().\n\n"
)


# -- Core LLM call ------------------------------------------------------------

@traceable(run_type="llm")
def call_llm(
    prompt: str,
    system_instruction: Optional[str] = None,
    expect_json: bool = False,
    max_retries: int = 3,
    model: Optional[str] = None,
    max_tokens_override: Optional[int] = None,
) -> str:
    """
    Make a single LLM call to the local LM Studio server.

    Args:
        prompt:             The user-turn prompt text.
        system_instruction: Optional system prompt.
        expect_json:        If True, prepend JSON enforcement preamble to system prompt.
        max_retries:        Retry attempts on connection/server errors.
        model:              Override the default model name.
        max_tokens_override: If set, use this instead of LM_STUDIO_MAX_OUTPUT_TOKENS.

    Returns:
        The model's text response (stripped).
    """
    client      = _get_client()
    target_model = model or LM_STUDIO_MODEL
    max_tokens  = max_tokens_override or LM_STUDIO_MAX_OUTPUT_TOKENS

    # Build messages list
    messages = []
    if expect_json:
        # Fuse the JSON preamble with any caller-provided system instruction
        sys_content = _JSON_PREAMBLE + (system_instruction or "")
    else:
        sys_content = system_instruction or ""

    if sys_content.strip():
        messages.append({"role": "system", "content": sys_content})
    messages.append({"role": "user", "content": prompt})

    # Retry loop (short fixed delay — local server, no rate limits)
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=LM_STUDIO_TEMPERATURE,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip()
            else:
                raise ValueError(f"Empty response from model (attempt {attempt + 1})")

        except APIConnectionError as e:
            print(f"  [LLM] Connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise

        except APIStatusError as e:
            print(f"  [LLM] API error {e.status_code} (attempt {attempt + 1}/{max_retries}): {e.message}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise

        except Exception as e:
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in [
                "connection", "timeout", "unavailable", "server error", "500", "503",
            ])
            if is_retryable and attempt < max_retries - 1:
                print(f"  [LLM] Transient error, retrying in 2s (attempt {attempt + 1}): {e}")
                time.sleep(2)
                continue
            print(f"  [LLM] Call failed after {attempt + 1} attempt(s): {e}")
            traceback.print_exc()
            raise


# -- JSON-mode wrapper --------------------------------------------------------

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


# -- JSON recovery pipeline ---------------------------------------------------

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

    # -- 1. Direct parse ------------------------------------------------------
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
        pass  # json_repair not installed -- fall through

    # -- 4. Partial walk-back: salvage last complete JSON object --------------
    for cutoff in range(len(raw), 0, -1):
        candidate = raw[:cutoff].rstrip()
        for closer in ("", "}", "}]}", "}]}\n}"):
            try:
                result = json.loads(candidate + closer)
                if isinstance(result, dict) and result:
                    print(
                        f"  [LLM] JSON truncated at token limit -- recovered partial response "
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
