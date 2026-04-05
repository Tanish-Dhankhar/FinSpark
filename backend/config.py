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

# ── Client Folder Sub-directories ───────────────────────────────────────────
CLIENT_SUBDIRS = [
    "input_documents",
    "configs",
    "simulation_reports",
    "diffs",
    "audit",
]

# ── LLM Settings ────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"  # Gemini 3.1 Flash Lite
GEMINI_TEMPERATURE = 0.2  # Low temperature for structured extraction
GEMINI_MAX_OUTPUT_TOKENS = 65536

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
