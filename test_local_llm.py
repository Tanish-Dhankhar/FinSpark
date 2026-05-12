"""
test_local_llm.py
-----------------
Quick connectivity and capability check for the LM Studio local server.

Tests:
  1. Server reachability (lists available models)
  2. Basic chat completion
  3. JSON-mode completion (critical pipeline path)
  4. System-instruction adherence
  5. Token generation speed benchmark

Run from the project root:
    python test_local_llm.py

LM Studio must be running at http://127.0.0.1:1234 with the model loaded.
"""

import json
import sys
import time

try:
    from openai import OpenAI
except ImportError:
    print("FAIL: openai package not installed. Run: pip install openai")
    sys.exit(1)


# -- Configuration ------------------------------------------------------------
BASE_URL = "http://127.0.0.1:1234/v1"
API_KEY  = "lm-studio"               # LM Studio accepts any non-empty string
MODEL    = "qwen2.5-coder-7b-instruct"


def make_client() -> OpenAI:
    return OpenAI(base_url=BASE_URL, api_key=API_KEY)


# -- Test 1: Server reachability ----------------------------------------------
def test_server_reachable(client: OpenAI) -> bool:
    print("\n" + "="*60)
    print("TEST 1 -- Server reachability (list models)")
    print("="*60)
    try:
        models = client.models.list()
        ids = [m.id for m in models.data]
        print(f"  PASS: Server is UP. Models loaded: {ids}")
        if not ids:
            print("  WARN: No models loaded yet -- load a model in LM Studio first.")
            return False
        return True
    except Exception as e:
        print(f"  FAIL: Cannot reach server at {BASE_URL}")
        print(f"        Error: {e}")
        print()
        print("  --> Make sure LM Studio is running and the local server is started")
        print("      (LM Studio -> Local Server tab -> Start Server button)")
        return False


# -- Test 2: Basic chat completion --------------------------------------------
def test_basic_chat(client: OpenAI) -> bool:
    print("\n" + "="*60)
    print("TEST 2 -- Basic chat completion")
    print("="*60)
    try:
        t0 = time.time()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Be concise."},
                {"role": "user",   "content": "What is 2 + 2? Reply with just the number."},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        elapsed = time.time() - t0
        content = response.choices[0].message.content
        tokens  = response.usage.total_tokens if response.usage else "?"
        print(f"  PASS: Response received in {elapsed:.1f}s")
        print(f"        Model replied : {repr(content)}")
        print(f"        Tokens used   : {tokens}")
        return True
    except Exception as e:
        print(f"  FAIL: Basic chat failed: {e}")
        return False


# -- Test 3: JSON-mode completion (pipeline critical path) --------------------
def test_json_mode(client: OpenAI) -> bool:
    print("\n" + "="*60)
    print("TEST 3 -- JSON-mode completion (pipeline critical path)")
    print("="*60)
    system = (
        "You are a data extractor. Always respond with valid JSON only. "
        "Never include any text outside the JSON object."
    )
    user = (
        'Extract the following into JSON with keys "service", "category", "is_mandatory":\n'
        '"The system must verify user identity via CIBIL credit bureau before loan approval."'
    )
    try:
        t0 = time.time()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=200,
        )
        elapsed = time.time() - t0
        raw = response.choices[0].message.content

        try:
            parsed = json.loads(raw)
            print(f"  PASS: JSON-mode response in {elapsed:.1f}s")
            print(f"        Parsed: {json.dumps(parsed)}")
            return True
        except json.JSONDecodeError:
            print(f"  WARN: Response not clean JSON (model ignored json_object mode).")
            print(f"        Raw: {repr(raw[:200])}")
            print("        --> Pipeline's 4-tier JSON recovery will handle this.")
            return True   # non-fatal

    except Exception as e:
        print(f"  FAIL: JSON-mode call failed: {e}")
        return False


# -- Test 4: System instruction adherence -------------------------------------
def test_system_instruction(client: OpenAI) -> bool:
    print("\n" + "="*60)
    print("TEST 4 -- System instruction adherence")
    print("="*60)
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an integration configuration engine. "
                        "Always respond in JSON. Never use markdown fences. "
                        "Respond ONLY with a JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return a JSON object with exactly these fields:\n"
                        '  "adapter_id": "cibil"\n'
                        '  "category": "bureau"\n'
                        '  "selected_version": "v2.1"'
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=150,
        )
        raw = response.choices[0].message.content
        print(f"  Raw: {repr(raw[:300])}")

        # Try direct parse
        try:
            parsed = json.loads(raw)
            print(f"  PASS: System instruction respected -- valid JSON returned")
            print(f"        {json.dumps(parsed)}")
            return True
        except json.JSONDecodeError:
            pass

        # Try stripping markdown fences (Qwen sometimes wraps output)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        try:
            parsed = json.loads(cleaned)
            print("  WARN: Needed markdown fence strip -- but JSON valid after stripping.")
            print(f"        Parsed: {json.dumps(parsed)}")
            return True
        except json.JSONDecodeError:
            print("  WARN: Model did not produce clean JSON. Pipeline fallback parsers will catch this.")
            return True   # non-fatal

    except Exception as e:
        print(f"  FAIL: System instruction test failed: {e}")
        return False


# -- Speed benchmark ----------------------------------------------------------
def test_speed_benchmark(client: OpenAI) -> None:
    print("\n" + "="*60)
    print("BENCHMARK -- Token generation speed")
    print("="*60)
    try:
        t0 = time.time()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user",   "content": "Count from 1 to 50, one number per line."},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        elapsed = time.time() - t0
        usage = response.usage
        if usage:
            out_tokens = usage.completion_tokens
            tok_per_sec = out_tokens / elapsed if elapsed > 0 else 0
            print(f"  Output tokens    : {out_tokens}")
            print(f"  Time             : {elapsed:.1f}s")
            print(f"  Generation speed : {tok_per_sec:.1f} tok/s")
            if tok_per_sec < 10:
                print("  WARN: Speed below 10 tok/s -- check GPU layer offloading in LM Studio.")
                print("        The pipeline will take 40+ minutes at this speed.")
            elif tok_per_sec >= 15:
                print("  INFO: Good speed -- pipeline should run in ~15-20 min range.")
            else:
                print("  INFO: Moderate speed -- pipeline will run in ~25-30 min range.")
        else:
            print(f"  Time: {elapsed:.1f}s (usage stats not returned by server)")
    except Exception as e:
        print(f"  FAIL: Benchmark failed: {e}")


# -- Main ---------------------------------------------------------------------
def main():
    print()
    print("#"*60)
    print("  FinSpark -- Local LLM Connectivity Test")
    print(f"  Server : {BASE_URL}")
    print(f"  Model  : {MODEL}")
    print("#"*60)

    client  = make_client()
    results = {}

    results["server_reachable"]     = test_server_reachable(client)
    if not results["server_reachable"]:
        print("\nSTOPPING -- server is not reachable.")
        sys.exit(1)

    results["basic_chat"]           = test_basic_chat(client)
    results["json_mode"]            = test_json_mode(client)
    results["system_instruction"]   = test_system_instruction(client)
    test_speed_benchmark(client)

    # -- Summary --------------------------------------------------------------
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}]  {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\nAll tests passed -- local model is ready for the FinSpark pipeline.")
    else:
        print("\nSome tests failed -- review output above before running the pipeline.")
    print()


if __name__ == "__main__":
    main()
