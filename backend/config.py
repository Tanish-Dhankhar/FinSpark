"""
FinSpark Application Configuration
Central configuration for paths, LLM settings, and pipeline parameters.
"""
import os
from pathlib import Path

# -- Base Paths ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # FinSpark_finals/
BACKEND_DIR  = PROJECT_ROOT / "backend"
CLIENTS_DIR  = PROJECT_ROOT / "clients"
TEMPLATES_DIR = BACKEND_DIR / "templates"
CATALOGS_DIR  = BACKEND_DIR / "catalogs"
ADAPTERS_CATALOG_DIR = CATALOGS_DIR / "adapters"
HOOKS_CATALOG_DIR    = CATALOGS_DIR / "hooks"
MOCKS_DIR        = BACKEND_DIR / "mocks"
SAMPLE_DOCS_DIR  = PROJECT_ROOT / "Sample_Documents"

# -- Template -----------------------------------------------------------------
CONFIG_TEMPLATE_PATH = TEMPLATES_DIR / "config_v1_template.json"

# -- Catalog Index Paths ------------------------------------------------------
ADAPTER_MASTER_INDEX = ADAPTERS_CATALOG_DIR / "master_index.json"
HOOK_MASTER_INDEX    = HOOKS_CATALOG_DIR    / "master_index.json"

# -- Vector Search (Embeddings Cache) -----------------------------------------
ADAPTER_EMBEDDINGS_CACHE     = ADAPTERS_CATALOG_DIR / "embeddings_cache.json"
HOOK_EMBEDDINGS_CACHE        = HOOKS_CATALOG_DIR    / "embeddings_cache.json"
VECTOR_TOP_K_ADAPTERS        = 3      # top-3 candidates per service
VECTOR_TOP_K_HOOKS           = 5      # top-5 hook candidates per integration
VECTOR_SIMILARITY_THRESHOLD  = 0.45   # below this -> low-confidence warning
VECTOR_EMBEDDING_DIM         = 512    # MRL truncation: 33% smaller, <1% accuracy loss
# Embedding model stays on Google (unchanged)
GEMINI_EMBEDDING_MODEL       = "models/gemini-embedding-2"

# -- Client Folder Sub-directories --------------------------------------------
CLIENT_SUBDIRS = [
    "input_documents",
    "configs",
    "simulation_reports",
    "diffs",
    "audit",
]

# -- LM Studio Local Inference ------------------------------------------------
# The generation LLM is served by LM Studio at the OpenAI-compatible endpoint.
LM_STUDIO_BASE_URL        = "http://127.0.0.1:1234/v1"
LM_STUDIO_API_KEY         = "lm-studio"        # any non-empty string works
LM_STUDIO_MODEL           = "qwen2.5-coder-7b-instruct"
LM_STUDIO_TEMPERATURE     = 0.0                # deterministic — fastest sampling, best JSON
LM_STUDIO_MAX_OUTPUT_TOKENS = 3000             # most calls need <2500; Stage4/S7 capped separately

# Per-call output token caps (tune these to control pipeline speed)
ADAPTER_PICK_MAX_TOKENS     = 300
INTEGRATION_FILL_MAX_TOKENS = 2500
HOOK_FILL_MAX_TOKENS        = 500
STAGE4_MAX_OUTPUT_TOKENS    = 3000
SIMULATION_REPORT_MAX_TOKENS = 2000

# -- Pipeline Settings --------------------------------------------------------
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

# -- API Settings -------------------------------------------------------------
API_HOST     = "0.0.0.0"
API_PORT     = 8000
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

# -- Environment --------------------------------------------------------------
def get_google_api_key() -> str:
    """Load GOOGLE_API_KEY from root .env or environment (used for embeddings only)."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GOOGLE_API_KEY not found in .env or environment variables")
    return key

# -- Backwards-compat aliases (kept so any code referencing old names still works) --
GEMINI_MODEL              = LM_STUDIO_MODEL
GEMINI_TEMPERATURE        = LM_STUDIO_TEMPERATURE
GEMINI_MAX_OUTPUT_TOKENS  = LM_STUDIO_MAX_OUTPUT_TOKENS
