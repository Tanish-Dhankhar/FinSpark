"""
test_lm_studio.py
=================
Quick smoke test to verify google/gemma-4-e4b is reachable via LM Studio
and producing valid outputs for FinSpark's two use patterns:

  Test 1 — Plain text response    (basic connectivity + generation)
  Test 2 — JSON response          (response_format json_object mode)
  Test 3 — call_llm() wrapper     (via the actual llm_service used in pipeline)
  Test 4 — call_llm_json() wrapper (full JSON parse + recovery chain)

Run from the repo root:
    python test_lm_studio.py
"""

import json
import sys
import time

BASE_URL = "http://127.0.0.1:1234/v1"
API_KEY  = "lm-studio"

# Always mirrors whatever is active in backend/config.py
from backend.config import LM_STUDIO_MODEL as MODEL

PASS = "[PASS]"
FAIL = "[FAIL]"
SEP  = "-" * 60


def section(title: str):
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Raw OpenAI client: plain text
# ─────────────────────────────────────────────────────────────────────────────
def test_plain_text():
    section("Test 1: Plain text generation (connectivity check)")
    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    t0 = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a concise assistant. Reply in one sentence."},
            {"role": "user",   "content": "What is 2 + 2? Give just the answer."},
        ],
        temperature=0.0,
        max_tokens=64,
    )
    elapsed = time.time() - t0
    content = response.choices[0].message.content
    finish  = response.choices[0].finish_reason

    print(f"  Model      : {response.model}")
    print(f"  Response   : {content!r}")
    print(f"  Finish     : {finish}")
    print(f"  Tokens     : {response.usage.prompt_tokens}in / {response.usage.completion_tokens}out")
    print(f"  Latency    : {elapsed:.2f}s")

    assert content and len(content.strip()) > 0, "Empty response!"
    print(f"\n  {PASS} Plain text works.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Raw OpenAI client: JSON object mode
# ─────────────────────────────────────────────────────────────────────────────
def test_json_mode():
    section("Test 2: JSON schema mode (response_format json_schema)")
    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    t0 = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a JSON-only assistant. Respond with valid JSON only."},
            {"role": "user",   "content": (
                'Return a JSON object with these fields: '
                '"service_name" (string), "category" (string), "confidence" (number between 0 and 1). '
                'Use the values: service_name="CIBIL", category="bureau", confidence=0.95'
            )},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "service_info",
                "strict": False,
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
        temperature=0.0,
        max_tokens=128,
    )
    elapsed = time.time() - t0
    raw = response.choices[0].message.content
    print(f"  Raw output : {raw!r}")
    print(f"  Latency    : {elapsed:.2f}s")

    parsed = json.loads(raw)
    assert "service_name" in parsed, f"Missing 'service_name' key in: {parsed}"
    assert "category"     in parsed, f"Missing 'category' key in: {parsed}"
    assert "confidence"   in parsed, f"Missing 'confidence' key in: {parsed}"

    print(f"  Parsed     : {json.dumps(parsed, indent=4)}")
    print(f"\n  {PASS} JSON schema mode works.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — FinSpark llm_service.call_llm()
# ─────────────────────────────────────────────────────────────────────────────
def test_call_llm_wrapper():
    section("Test 3: llm_service.call_llm() — FinSpark wrapper")
    from backend.services.llm_service import call_llm

    result = call_llm(
        prompt="Explain what an API adapter is in exactly one sentence.",
        system_instruction="You are a concise technical writer.",
        expect_json=False,
        max_retries=2,
    )
    print(f"  Result     : {result!r}")
    assert result and len(result.strip()) > 10, "Response too short or empty!"
    print(f"\n  {PASS} call_llm() works.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — FinSpark llm_service.call_llm_json()  (as Stage 2 & 3 use it)
# ─────────────────────────────────────────────────────────────────────────────
def test_call_llm_json_wrapper():
    section("Test 4: llm_service.call_llm_json() — JSON parse + recovery chain")
    from backend.services.llm_service import call_llm_json

    result = call_llm_json(
        prompt=(
            "Return a JSON object representing a detected integration service with these fields:\n"
            "  service_name (string): name of a payment gateway\n"
            "  category (string): one of [payment, bureau, kyc, banking]\n"
            "  role (string): one of [primary, fallback, mentioned_only]\n"
            "  confidence (number): between 0.0 and 1.0\n\n"
            "Use realistic example values."
        ),
        system_instruction=(
            "You are a JSON API. Respond with a single valid JSON object only. "
            "No markdown, no explanations, no extra text."
        ),
        max_retries=2,
    )
    print(f"  Parsed JSON:\n{json.dumps(result, indent=4)}")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert len(result) > 0, "Empty dict returned!"
    print(f"\n  {PASS} call_llm_json() works.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'=' * 60}")
    print(f"  FinSpark — LM Studio Connection Test")
    print(f"  Model  : {MODEL}")
    print(f"  Server : {BASE_URL}")
    print(f"{'=' * 60}")

    tests = [
        ("Plain text generation",     test_plain_text),
        ("JSON object mode",          test_json_mode),
        ("call_llm() wrapper",        test_call_llm_wrapper),
        ("call_llm_json() wrapper",   test_call_llm_json_wrapper),
    ]

    results = {}
    for name, fn in tests:
        try:
            fn()
            results[name] = True
        except Exception as e:
            print(f"\n  {FAIL} {name}: {e}")
            results[name] = False

    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    all_passed = True
    for name, passed in results.items():
        status = PASS if passed else FAIL
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print(f"{'=' * 60}\n")
    if all_passed:
        print("  All tests passed. FinSpark is ready to use google/gemma-4-e4b.\n")
    else:
        print("  Some tests failed. Check the errors above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
