# FinSpark — Setup & Running Guide

Everything you need to get FinSpark running locally from scratch — **no cloud API keys required.**

> **Prerequisites at a glance:** Python 3.10+, Node.js 20+, PostgreSQL 15+, LM Studio (with Qwen + nomic-embed-text loaded)

---

## Table of Contents

1. [Install LM Studio &amp; Load Models](#1-install-lm-studio--load-models)
2. [Set Up PostgreSQL](#2-set-up-postgresql)
3. [Clone &amp; Configure the Project](#3-clone--configure-the-project)
4. [Install Python Dependencies](#4-install-python-dependencies)
5. [Run Database Migrations](#5-run-database-migrations)
6. [Start the Backend](#6-start-the-backend)
7. [Start the Frontend](#7-start-the-frontend)
8. [Verify Everything Works](#8-verify-everything-works)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Install LM Studio & Load Models

FinSpark uses **LM Studio** to serve both the generation model and the embedding model via an OpenAI-compatible local API.

### 1.1 Download LM Studio

Download from [https://lmstudio.ai](https://lmstudio.ai) and install it.

### 1.2 Load the Generation Model (Qwen)

1. Open LM Studio → click **Search** (top bar)
2. Search for `qwen2.5-coder-7b-instruct`
3. Download the **Q4_K_M** quantization (good balance of speed and quality)
4. Go to **Local Server** tab (left sidebar `↔`)
5. Select `qwen2.5-coder-7b-instruct` from the model dropdown
6. Click **Start Server**

The server will start at `http://127.0.0.1:1234`.

### 1.3 Load the Embedding Model (nomic-embed-text)

LM Studio supports loading a second model alongside the generation model:

1. In LM Studio → **Local Server** tab
2. Click **+ Load Model** (to add alongside Qwen)
3. Search for `text-embedding-nomic-embed-text-v1.5`
4. Download and load it

> **Verify both are loaded:** In the Local Server tab, you should see both models listed under "Loaded Models". The server serves both at `http://127.0.0.1:1234/v1`.

### 1.4 Recommended LM Studio Settings

| Setting        | Value                                               |
| -------------- | --------------------------------------------------- |
| Context Length | 16384                                               |
| GPU Layers     | Max (all layers on GPU if VRAM allows)              |
| Temperature    | 0.2 (set in code — no need to change in LM Studio) |

> **GPU tip:** In LM Studio → model settings → set **GPU Layers** to the maximum your VRAM allows. At 8GB VRAM, Qwen 7B Q4_K_M runs at ~20–30 tok/s. At CPU-only, expect ~3–5 tok/s (pipeline will be slow but functional).

---

## 2. Set Up PostgreSQL

### 2.1 Install PostgreSQL

Download from [https://www.postgresql.org/download](https://www.postgresql.org/download) and install with default settings. Remember the `postgres` superuser password you set during installation.

### 2.2 Create the Database and Users

Open `psql` (the PostgreSQL shell) or use **pgAdmin**:

```sql
-- Connect as postgres superuser
-- Create the application database
CREATE DATABASE finspark_db;

-- Create the superuser role (used only for DDL / migrations)
CREATE USER finspark WITH PASSWORD 'finspark123' SUPERUSER;

-- Create the runtime application role (RLS-enforced, non-superuser)
CREATE USER finspark_app WITH PASSWORD 'finspark_app123';

-- Grant connect and usage on the database
GRANT CONNECT ON DATABASE finspark_db TO finspark_app;
GRANT CONNECT ON DATABASE finspark_db TO finspark;
```

> The `finspark` user (superuser) is used only for running migrations and creating tables. The `finspark_app` user is what the running application uses — it is subject to Row-Level Security and cannot see other tenants' data.

---

## 3. Clone & Configure the Project

### 3.1 Clone the Repository

```powershell
git clone https://github.com/Tanish-Dhankhar/FinSpark.git
cd FinSpark
```

### 3.2 Create the `.env` File

Create a `.env` file in the **project root** (`FinSpark_finals/.env`):

```env
# PostgreSQL — superuser role (used for migrations only)
DATABASE_URL=postgresql://finspark:finspark123@localhost:5432/finspark_db

# PostgreSQL — app role (used by the running backend, RLS enforced)
APP_DATABASE_URL=postgresql://finspark_app:finspark_app123@localhost:5432/finspark_db
```

> **No API keys needed.** LM Studio and PostgreSQL both run locally.

---

## 4. Install Python Dependencies

Open a terminal in the **project root** (where `requirements.txt` is):

```powershell
# Create a virtual environment
python -m venv .venv

# Activate it (PowerShell)
.venv\Scripts\Activate.ps1

# Install all dependencies
pip install -r requirements.txt
```

> **Using `uv` (faster):**
>
> ```powershell
> pip install uv
> uv venv
> .venv\Scripts\Activate.ps1
> uv pip install -r requirements.txt
> ```

Also install the optional `json_repair` package for extra JSON recovery robustness:

```powershell
pip install json_repair
```

---

## 5. Run Database Migrations

With the virtual environment active and PostgreSQL running:

```powershell
# From the project root
python -m backend.database.migrate_existing
```

This creates all 7 tables and sets up Row-Level Security policies:

- `projects` — client project metadata
- `config_versions` — versioned integration configs (JSONB)
- `pipeline_runs` — stage-by-stage pipeline state
- `audit_events` — SHA-256 hashed immutable audit log
- `credentials` — encrypted API key vault
- `simulation_reports` — Stage 7 confidence reports
- `documents` — uploaded BRD metadata

> You should see `✅ All tables created successfully.` when complete.

---

## 6. Start the Backend

Make sure:

- LM Studio is running with both models loaded (port 1234)
- PostgreSQL is running (port 5432)
- Your `.venv` is activated

```powershell
# From the project root
python -m uvicorn backend.main:app --port 8001 --reload
```

On first start, the backend will:

1. Connect to PostgreSQL and verify tables
2. Warm the embedding cache — embeds all 12 adapters + 13 hooks using nomic-embed-text
3. Print `✅ Adapter embeddings: rebuilt 12` and `✅ Hook embeddings: rebuilt 13`

**Expected startup output:**

```
INFO:     Started server process
  🔍 Vector Service: checking embedding cache freshness...
  🔢 Embedding adapter: cibil...
  🔢 Embedding adapter: experian...
  ...
  ✅ Adapter embeddings: rebuilt 12 (...), skipped 0
  ✅ Hook embeddings: rebuilt 13 (...), skipped 0
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

> **Subsequent starts are faster** — the cache uses MD5 hashing to skip unchanged adapters. Only re-embeds files that changed on disk.

The backend API is now live at **`http://localhost:8001`**

- **Swagger docs:** `http://localhost:8001/docs`
- **Health check:** `http://localhost:8001/health`

---

## 7. Start the Frontend

Open a **second terminal** in the project root:

```powershell
# Navigate to the frontend directory
cd frontend

# Install Node.js dependencies (first time only)
npm install

# Start the Next.js development server
npm run dev
```

The frontend will be available at **`http://localhost:3000`**

> The frontend automatically connects to `http://localhost:8001` when running locally.

---

## 8. Verify Everything Works

### 8.1 Quick Connectivity Test

With LM Studio running, run from the project root:

```powershell
python test_lm_studio.py
```

All 5 tests should pass:

```
[PASS]  Plain text generation
[PASS]  JSON object mode
[PASS]  call_llm() wrapper
[PASS]  call_llm_json() wrapper
[PASS]  nomic-embed-text
```

### 8.2 Run a Pipeline End-to-End

1. Open `http://localhost:3000` in your browser
2. Click **New Project** → enter a client name → click Create
3. Upload a BRD document (PDF, DOCX, or TXT) — a sample is in `Sample_Documents/`
4. Click **Run Pipeline**
5. Watch the 7 stages progress in real time
6. At **Stage 6**, review the config + reasoning report → click Approve
7. Stage 7 will run simulation and produce a confidence score

---

## 9. Troubleshooting

| Problem                                            | Fix                                                                                                                                                                              |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Connection refused` to `127.0.0.1:1234`       | LM Studio local server is not started. Go to LM Studio → Local Server tab → Start Server.                                                                                      |
| Embedding cache warmup hangs                       | nomic-embed-text is not loaded in LM Studio. Load it alongside Qwen (see Step 1.3).                                                                                              |
| `ModuleNotFoundError: No module named 'backend'` | Run `uvicorn` from the **project root**, not from inside `backend/`.                                                                                                   |
| `psycopg2.OperationalError`                      | PostgreSQL is not running, or `DATABASE_URL` in `.env` has wrong credentials.                                                                                                |
| Pipeline hangs at Stage 3                          | Qwen model may be slow — check GPU offloading in LM Studio. Also check LM Studio console for errors.                                                                            |
| `test_lm_studio.py` Test 5 fails with wrong dim  | nomic-embed-text model produces a different dimension. Update `VECTOR_EMBEDDING_DIM` in `backend/config.py` to match and delete the embeddings cache files to force rebuild. |
| Frontend shows "Failed to fetch"                   | Make sure backend is running on port 8001 and `NEXT_PUBLIC_API_BASE_URL` is not set to a stale Vercel URL.                                                                     |
| Port 8001 in use                                   | Kill the existing process or use a different port:`--port 8002` (update frontend `.env.local` to match).                                                                     |
| `json_repair` not found warning                  | Run `pip install json_repair` — it's optional but improves JSON recovery for truncated model outputs.                                                                         |

---

## Project Structure Reference

```
FinSpark_finals/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # All constants (model names, paths, thresholds)
│   ├── security.py                # 4-layer security guards
│   ├── pipeline/
│   │   ├── orchestrator.py        # 7-stage state machine
│   │   ├── stage2_parsing.py      # BRD extraction
│   │   ├── stage3_matching.py     # RAG adapter + hook matching
│   │   ├── stage4_reasoning.py    # Reasoning report generation
│   │   ├── stage5_cleaner.py      # Production cleaner
│   │   ├── stage6_review.py       # Human review + correction
│   │   └── stage7_simulation.py   # Mock simulation + confidence scoring
│   ├── services/
│   │   ├── llm_service.py         # Qwen via LM Studio (OpenAI-compatible)
│   │   ├── vector_service.py      # nomic-embed-text RAG engine
│   │   └── project_service.py     # Project CRUD
│   ├── catalogs/
│   │   ├── adapters/              # 12 adapter JSON definitions
│   │   └── hooks/                 # 13 hook JSON definitions
│   └── database/
│       └── migrate_existing.py    # Schema + RLS migration script
├── frontend/                      # Next.js 16 + React 19 + Tailwind CSS 4
├── Sample_Documents/              # Example BRDs to test with
├── requirements.txt               # Python dependencies
├── test_lm_studio.py              # Connectivity smoke test (5 tests)
├── test_local_llm.py              # Alternative LM Studio connectivity test
├── pipeline.png                   # Pipeline architecture diagram
├── .env                           # Your local config (create this — not committed)
└── README.md                      # Project overview
```
