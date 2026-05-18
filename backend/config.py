"""
FinSpark Application Configuration
Central configuration for paths, LLM settings, and pipeline parameters.
"""
import os
from pathlib import Path

# ── Base Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # FinSpark_2/
BACKEND_DIR = PROJECT_ROOT / "backend"
CLIENTS_DIR = PROJECT_ROOT / "clients"
TEMPLATES_DIR = BACKEND_DIR / "templates"
CATALOGS_DIR = BACKEND_DIR / "catalogs"
ADAPTERS_CATALOG_DIR = CATALOGS_DIR / "adapters"
HOOKS_CATALOG_DIR = CATALOGS_DIR / "hooks"
MOCKS_DIR = BACKEND_DIR / "mocks"
SAMPLE_DOCS_DIR = PROJECT_ROOT / "Sample_Documents"

# ── Template ────────────────────────────────────────────────────────────────
CONFIG_TEMPLATE_PATH = TEMPLATES_DIR / "config_v1_template.json"

# ── Catalog Index Paths ─────────────────────────────────────────────────────
ADAPTER_MASTER_INDEX = ADAPTERS_CATALOG_DIR / "master_index.json"
HOOK_MASTER_INDEX = HOOKS_CATALOG_DIR / "master_index.json"

# ── Vector Search (Embeddings Cache) ────────────────────────────────────────
ADAPTER_EMBEDDINGS_CACHE = ADAPTERS_CATALOG_DIR / "embeddings_cache.json"
HOOK_EMBEDDINGS_CACHE    = HOOKS_CATALOG_DIR / "embeddings_cache.json"
VECTOR_TOP_K_ADAPTERS    = 3     # top-3 candidates per service (per-service querying)
VECTOR_TOP_K_HOOKS       = 5     # top-5 hook candidates per integration
VECTOR_SIMILARITY_THRESHOLD = 0.45  # below this → low-confidence warning + fallback
VECTOR_EMBEDDING_DIM     = 512   # MRL truncation: 33% smaller, <1% accuracy loss
GEMINI_EMBEDDING_MODEL   = "models/gemini-embedding-2"

# ── Client Folder Sub-directories ───────────────────────────────────────────
CLIENT_SUBDIRS = [
    "input_documents",
    "configs",
    "simulation_reports",
    "diffs",
    "audit",
]

# ── LLM Settings ────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"  # Kept as fallback only
GEMINI_TEMPERATURE = 0.2
GEMINI_MAX_OUTPUT_TOKENS = 16384  # Enough for complex BRDs with many services (was 8192)

# ── Local LLM — Generation (Ollama + Qwen3-8B) ──────────────────────────────
# Set USE_LOCAL_LLM=True to use local Ollama model for all generation calls.
# Embeddings always use Google (vector_service.py is unaffected by this toggle).
USE_LOCAL_LLM       = True
LOCAL_LLM_BASE_URL  = "http://localhost:11434/v1"  # Ollama OpenAI-compatible endpoint
LOCAL_LLM_MODEL     = "qwen3.5:9b"                  # Confirmed working via `ollama run qwen3.5:9b`
LOCAL_LLM_TEMPERATURE = 0.2                        # Low temp for deterministic JSON output
# IMPORTANT: Keep max_tokens at 4096, NOT 16384.
# Root cause of Stage 2 hang: Qwen3 in think mode consumes ALL 16384 tokens
# on <think> blocks, leaving 0 tokens for the actual JSON response → empty output.
# 4096 is more than enough for any pipeline JSON response.
LOCAL_LLM_MAX_TOKENS  = 4096
LOCAL_LLM_TIMEOUT     = 120                        # Seconds — nothink mode is fast
# Ollama executable path (Windows — may not be in PATH after fresh install)
OLLAMA_PATH = r"C:\Users\happy\AppData\Local\Programs\Ollama\ollama.exe"

# ── Pipeline Settings ───────────────────────────────────────────────────────
MAX_CORRECTION_ITERATIONS = 3
PIPELINE_STAGES = [
    "stage_1_ingestion",
    "stage_2_parsing",
    "stage_3_matching",
    "stage_4_reasoning",
    "stage_5_cleaner",
    "stage_6_review",
    "stage_7_simulation",
]

# ── API Settings ────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

# ── Environment ─────────────────────────────────────────────────────────────
def get_google_api_key() -> str:
    """Load GOOGLE_API_KEY from root .env or environment."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GOOGLE_API_KEY not found in .env or environment variables")
    return key
