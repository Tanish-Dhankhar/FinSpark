"""
FinSpark Application Configuration
Central configuration for paths, LLM settings, and pipeline parameters.
"""
import os
from pathlib import Path

# ── Base Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # FinSpark_2/
BACKEND_DIR = PROJECT_ROOT / "backend"

if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
    CLIENTS_DIR = Path("/tmp/clients")
else:
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
if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
    ADAPTER_EMBEDDINGS_CACHE = Path("/tmp/adapter_embeddings_cache.json")
    HOOK_EMBEDDINGS_CACHE    = Path("/tmp/hook_embeddings_cache.json")
else:
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
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"  # Gemini 3.1 Flash Lite (generation)
# Note: embedding model is GEMINI_EMBEDDING_MODEL = "text-embedding-005" (see above)
GEMINI_TEMPERATURE = 0.2  # Low temperature for structured extraction
GEMINI_MAX_OUTPUT_TOKENS = 16384  # Enough for complex BRDs with many services (was 8192)

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
