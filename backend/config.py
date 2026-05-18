"""
FinSpark Application Configuration
Central configuration for paths, LLM settings, and pipeline parameters.
"""
import os
from pathlib import Path

# ── Base Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # FinSpark_finals/
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

VECTOR_TOP_K_ADAPTERS       = 3     # top-3 candidates per service (per-service querying)
VECTOR_TOP_K_HOOKS          = 5     # top-5 hook candidates per integration
VECTOR_SIMILARITY_THRESHOLD = 0.45  # below this → low-confidence warning + fallback
VECTOR_EMBEDDING_DIM        = 768   # nomic-embed-text produces 768-dim vectors

# ── Client Folder Sub-directories ───────────────────────────────────────────
CLIENT_SUBDIRS = [
    "input_documents",
    "configs",
    "simulation_reports",
    "diffs",
    "audit",
]

# ── LM Studio — Generation (Qwen via LM Studio OpenAI-compatible API) ───────
LM_STUDIO_BASE_URL    = "http://127.0.0.1:1234/v1"
LM_STUDIO_MODEL       = "qwen2.5-coder-7b-instruct"
LM_STUDIO_API_KEY     = "lm-studio"   # LM Studio requires any non-empty key
LM_TEMPERATURE        = 0.2           # Low temperature for structured extraction
LM_MAX_OUTPUT_TOKENS  = 16384         # Enough for complex BRDs with many services

# ── LM Studio — Embeddings (nomic-embed-text via LM Studio) ─────────────────
NOMIC_EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5"
# Note: served at the same LM_STUDIO_BASE_URL above

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

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://finspark:finspark123@localhost:5432/finspark_db"
)
