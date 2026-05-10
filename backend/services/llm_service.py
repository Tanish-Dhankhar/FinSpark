"""
Gemini LLM Service
Centralized wrapper for Google Gemini API calls with rate-limit handling,
structured prompt templating, and JSON response parsing.
"""
import json
import time
import traceback
from typing import Optional
from google import genai
from google.genai import types
from langsmith import traceable
from backend.config import get_google_api_key, GEMINI_MODEL, GEMINI_TEMPERATURE, GEMINI_MAX_OUTPUT_TOKENS


# ── Singleton Client ────────────────────────────────────────────────────────

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Lazy-init the Gemini client."""
    global _client
    if _client is None:
        api_key = get_google_api_key()
        _client = genai.Client(api_key=api_key)
    return _client


# ── Core LLM Call ───────────────────────────────────────────────────────────

@traceable(run_type="llm")
def call_llm(
    prompt: str,
    system_instruction: Optional[str] = None,
    expect_json: bool = False,
    max_retries: int = 5,
    model: Optional[str] = None,
) -> str:
    """
    Make a single LLM call to Gemini with automatic retry on rate limits.
    
    Args:
        prompt: The user prompt text
        system_instruction: Optional system prompt for guiding behavior
        expect_json: If True, instruct model to return valid JSON only
        max_retries: Maximum retry attempts on transient errors
        model: Override the default model
        
    Returns:
        The model's text response (stripped)
    """
    client = _get_client()
    target_model = model or GEMINI_MODEL

    # Build config
    gen_config = types.GenerateContentConfig(
        temperature=GEMINI_TEMPERATURE,
        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
    )
    if system_instruction:
        gen_config.system_instruction = system_instruction
    if expect_json:
        gen_config.response_mime_type = "application/json"

    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=gen_config,
            )
            if response.text:
                return response.text.strip()
            else:
                raise ValueError(f"Empty response from Gemini (attempt {attempt + 1})")
        except Exception as e:
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in [
                "429", "rate", "resource_exhausted", "quota",
                "503", "overloaded", "unavailable", "deadline",
                "500", "internal"
            ])
            # Max-token errors are NOT retryable — the prompt is too large
            is_token_overflow = any(kw in error_str for kw in [
                "generation exceeded max tokens",
                "max_tokens",
                "output tokens limit",
                "exceeds the maximum",
            ])
            if is_token_overflow:
                raise ValueError(
                    f"LLM output token overflow — prompt or response is too large. "
                    f"Try splitting the request into smaller chunks. Error: {e}"
                )
            if is_retryable and attempt < max_retries - 1:
                wait_time = min(2 ** attempt * 2, 60)  # 2, 4, 8, 16, 32, max 60
                print(f"  ⏳ Rate limited (attempt {attempt + 1}/{max_retries}). Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"  ❌ LLM call failed after {attempt + 1} attempts: {e}")
                traceback.print_exc()
                raise


def call_llm_json(
    prompt: str,
    system_instruction: Optional[str] = None,
    max_retries: int = 5,
) -> dict:
    """
    Make an LLM call and parse the response as JSON.
    Falls back to extracting JSON from markdown code blocks if needed.
    
    Returns:
        Parsed JSON as a dict/list
    """
    raw = call_llm(
        prompt=prompt,
        system_instruction=system_instruction,
        expect_json=True,
        max_retries=max_retries,
    )
    return _parse_json_response(raw)


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, handling common formatting issues."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        try:
            return json.loads(raw[start:end].strip())
        except json.JSONDecodeError:
            pass
    
    if "```" in raw:
        start = raw.index("```") + 3
        # Skip language identifier if on same line
        newline = raw.index("\n", start)
        start = newline + 1
        end = raw.index("```", start)
        try:
            return json.loads(raw[start:end].strip())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response. Raw response:\n{raw[:500]}")
