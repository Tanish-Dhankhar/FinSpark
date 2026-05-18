"""
LLM Service — Generation Backend
=================================
Supports two backends, controlled by config.USE_LOCAL_LLM:

  USE_LOCAL_LLM = True  -> Ollama (local)  via OpenAI-compatible API
  USE_LOCAL_LLM = False -> Google Gemini Flash (cloud) via google-genai SDK

The EMBEDDING model (gemini-embedding-2) is NOT handled here.
Embeddings live entirely in vector_service.py and are unaffected by this module.

Key design:
  • call_llm()      — returns raw string
  • call_llm_json() — returns parsed dict (with multi-stage JSON recovery)
  • Signatures are identical regardless of backend; callers need zero changes.
  • Qwen3 nothink: /no_think is prepended to the USER message (not the system
    message). Qwen3 only reads the control token from the user turn. This
    disables chain-of-thought reasoning, making responses 5-10x faster.
"""
import json
import time
import traceback
from typing import Optional

from backend.config import (
    # Local LLM (Ollama)
    USE_LOCAL_LLM,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_TEMPERATURE,
    LOCAL_LLM_MAX_TOKENS,
    LOCAL_LLM_TIMEOUT,
    # Gemini fallback
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS,
)


# -- Lazy singletons ----------------------------------------------------------

_openai_client = None   # OpenAI-compatible client -> Ollama
_gemini_client = None   # google.genai client -> Gemini (fallback only)


def _get_local_client():
    """Lazy-init the OpenAI-compatible client pointed at local Ollama server."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(
            base_url=LOCAL_LLM_BASE_URL,
            api_key="ollama",           # Ollama ignores the key; must be non-empty
            timeout=LOCAL_LLM_TIMEOUT,
        )
    return _openai_client


def _get_gemini_client():
    """Lazy-init the Google Gemini client (fallback / embedding helper)."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        from backend.config import get_google_api_key
        _gemini_client = genai.Client(api_key=get_google_api_key())
    return _gemini_client


# -- Backend implementations --------------------------------------------------

def _call_local(
    prompt: str,
    system_instruction: Optional[str],
    expect_json: bool,
    max_retries: int,
) -> str:
    """Call the local Ollama model via OpenAI-compatible API."""
    from openai import APIConnectionError, APITimeoutError

    client = _get_local_client()

    messages = []
    if system_instruction:
        # System message: clean, no control tokens (Qwen3 ignores /no_think here).
        messages.append({"role": "system", "content": system_instruction})
    # /no_think MUST be on the user turn for Qwen3 to suppress chain-of-thought.
    # Placing it on the system message is silently ignored by the model.
    # We will remove /no_think because extra_body is enough and the explicit token might confuse the JSON parsing on large prompts.
    messages.append({"role": "user", "content": prompt})

    kwargs = dict(
        model=LOCAL_LLM_MODEL,
        messages=messages,
        temperature=LOCAL_LLM_TEMPERATURE,
        max_tokens=LOCAL_LLM_MAX_TOKENS,
        # Definitive nothink: chat_template_kwargs flows directly into the
        # tokenizer's apply_chat_template(enable_thinking=False) call.
        # This is the same parameter as HuggingFace's enable_thinking=False.
        # /no_think in the user message is an additional belt-and-suspenders fallback.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if content:
                # Strip any residual <think>...</think> blocks that leak through
                # even with /no_think (can happen with some Ollama versions).
                import re as _re
                content = _re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                return content
            raise ValueError(f"Empty response from local model (attempt {attempt + 1})")

        except (APIConnectionError, APITimeoutError) as e:
            # Connection errors: Ollama may still be starting up
            if attempt < max_retries - 1:
                wait = min(2 ** attempt * 3, 30)
                print(f"  [wait] Local model connection error (attempt {attempt + 1}/{max_retries}). "
                      f"Is Ollama running? Retrying in {wait}s... [{e}]")
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"Cannot reach local Ollama server at {LOCAL_LLM_BASE_URL}. "
                f"Make sure Ollama is running: 'ollama serve'. Error: {e}"
            ) from e

        except Exception as e:
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in [
                "429", "rate", "overloaded", "unavailable", "503", "500",
                "resource_exhausted", "deadline", "timeout",
            ])
            if is_retryable and attempt < max_retries - 1:
                wait = min(2 ** attempt * 2, 30)
                print(f"  [wait] Retryable error (attempt {attempt + 1}/{max_retries}). "
                      f"Waiting {wait}s... [{e}]")
                time.sleep(wait)
                continue
            print(f"  [ERROR] Local LLM call failed after {attempt + 1} attempts: {e}")
            traceback.print_exc()
            raise


def _call_gemini(
    prompt: str,
    system_instruction: Optional[str],
    expect_json: bool,
    max_retries: int,
    model: Optional[str],
) -> str:
    """Call Google Gemini Flash (fallback backend)."""
    from google.genai import types

    client = _get_gemini_client()
    target_model = model or GEMINI_MODEL

    gen_config = types.GenerateContentConfig(
        temperature=GEMINI_TEMPERATURE,
        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
    )
    if system_instruction:
        gen_config.system_instruction = system_instruction
    if expect_json:
        gen_config.response_mime_type = "application/json"

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=gen_config,
            )
            if response.text:
                return response.text.strip()
            raise ValueError(f"Empty response from Gemini (attempt {attempt + 1})")

        except Exception as e:
            error_str = str(e).lower()
            is_token_overflow = any(kw in error_str for kw in [
                "generation exceeded max tokens", "max_tokens",
                "output tokens limit", "exceeds the maximum",
            ])
            if is_token_overflow:
                raise ValueError(
                    f"Gemini output token overflow — try splitting the request. Error: {e}"
                )
            is_retryable = any(kw in error_str for kw in [
                "429", "rate", "resource_exhausted", "quota",
                "503", "overloaded", "unavailable", "deadline", "500", "internal",
            ])
            if is_retryable and attempt < max_retries - 1:
                wait = min(2 ** attempt * 2, 60)
                print(f"  [wait] Gemini rate limited (attempt {attempt + 1}/{max_retries}). "
                      f"Waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [ERROR] Gemini call failed after {attempt + 1} attempts: {e}")
            traceback.print_exc()
            raise


# -- Public API ---------------------------------------------------------------

from langsmith import traceable


@traceable(run_type="llm")
def call_llm(
    prompt: str,
    system_instruction: Optional[str] = None,
    expect_json: bool = False,
    max_retries: int = 5,
    model: Optional[str] = None,   # only used when USE_LOCAL_LLM=False
) -> str:
    """
    Make a single LLM call — routes to local Ollama or Gemini based on config.

    Args:
        prompt:             User prompt text
        system_instruction: Optional system prompt
        expect_json:        If True, request structured JSON output from the model
        max_retries:        Maximum retry attempts on transient errors
        model:              Override model (Gemini backend only; ignored for local)

    Returns:
        The model's text response (stripped)
    """
    backend = "local (Ollama)" if USE_LOCAL_LLM else "Gemini"
    print(f"  [LLM] call -> {backend}", end="", flush=True)

    if USE_LOCAL_LLM:
        result = _call_local(prompt, system_instruction, expect_json, max_retries)
    else:
        result = _call_gemini(prompt, system_instruction, expect_json, max_retries, model)

    print(f" OK ({len(result)} chars)")
    return result


def call_llm_json(
    prompt: str,
    system_instruction: Optional[str] = None,
    max_retries: int = 5,
) -> dict:
    """
    Make an LLM call and return the response parsed as JSON.

    Uses multi-stage recovery for truncated or malformed responses:
      1. Direct json.loads
      2. Strip markdown fences
      3. json_repair (if installed)
      4. Walk-back partial recovery
      5. Hard failure with diagnostics
    """
    raw = call_llm(
        prompt=prompt,
        system_instruction=system_instruction,
        expect_json=True,
        max_retries=max_retries,
    )
    return _parse_json_response(raw)


# -- JSON Recovery ------------------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response with multi-stage recovery.

    Recovery order:
      1. Direct parse (fast path)
      2. Strip markdown code fences
      3. json_repair (if installed) — handles truncated / malformed JSON
      4. Partial recovery — walk backward to find last complete object
      5. Hard failure with diagnostic context
    """
    if not raw or not raw.strip():
        raise ValueError("LLM returned an empty response.")

    # -- 1. Direct parse ---------------------------------------------------
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # -- 2. Strip markdown code fences ------------------------------------
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

    # -- 3. json_repair ----------------------------------------------------
    try:
        from json_repair import repair_json  # type: ignore
        repaired = repair_json(raw, return_objects=True)
        if isinstance(repaired, (dict, list)):
            print("  [WARN]️  JSON was repaired (response may have been truncated).")
            return repaired if isinstance(repaired, dict) else {"_repaired_list": repaired}
    except ImportError:
        pass

    # -- 4. Walk-back partial recovery -------------------------------------
    for cutoff in range(len(raw), 0, -1):
        candidate = raw[:cutoff].rstrip()
        for closer in ("", "}", "}]}", "}]}\n}"):
            try:
                result = json.loads(candidate + closer)
                if isinstance(result, dict) and result:
                    print(
                        f"  [WARN]️  JSON truncated — recovered partial response "
                        f"({cutoff}/{len(raw)} chars). Some content may be missing."
                    )
                    return result
            except json.JSONDecodeError:
                continue
        if len(raw) - cutoff > 200:
            break

    raise ValueError(
        f"Could not parse JSON from LLM response. "
        f"Response length: {len(raw)} chars. "
        f"First 500 chars:\n{raw[:500]}"
    )
