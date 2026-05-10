# FinSpark — AI Integration Orchestration Engine

FinSpark is an AI-orchestrated integration engine that transforms business requirement documents (BRDs) into production-ready integration configurations using a 7-stage RAG pipeline powered by Gemini.

---

## Prerequisites

- **Python 3.10+**
- **Node.js 20+**
- **A Google API Key** (for Gemini LLM + text-embedding-005)

---

## Project Structure

```
FinSpark_final/
├── backend/              # FastAPI backend (Python)
├── frontend/             # Next.js frontend
├── cloudflared.exe       # Cloudflare tunnel binary (in root)
├── requirements.txt      # Python dependencies
├── .env                  # Your API keys (create this)
└── clients/              # Auto-created: client project data
```

---

## 1. Environment Setup (One-Time)

### Create your `.env` file in the project root:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

> Get your key from [Google AI Studio](https://aistudio.google.com/app/apikey). This key is used for both the Gemini LLM (generation) and the text-embedding-005 model (vector search).

---

## 2. Install Python Dependencies (One-Time)

Open a terminal in the **project root** (where `requirements.txt` is):

```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install all dependencies
pip install -r requirements.txt
```

> **Using `uv` (faster alternative):**
> ```powershell
> uv venv
> .venv\Scripts\Activate.ps1
> uv pip install -r requirements.txt
> ```

---

## Option A — Run Fully on Localhost

Use this if you want to run both the backend and frontend locally without any Cloudflare tunnel.

You need **two separate terminal windows**, both opened in the project root.

### Terminal 1: Start the Backend

```powershell
# Activate the virtual environment (if not already active)
.venv\Scripts\Activate.ps1

# Start the backend on port 8001
python -m uvicorn backend.main:app --port 8001 --reload
```

The backend will be available at: **`http://localhost:8001`**

> On first start, it will warm the vector embeddings cache automatically. You will see `✅ Embeddings cache ready.` in the logs when it's done.

### Terminal 2: Start the Frontend

```powershell
# Navigate to the frontend directory
cd frontend

# Install Node.js dependencies (first time only)
npm install

# Start the Next.js dev server
npm run dev
```

The frontend will be available at: **`http://localhost:3000`**

> The frontend automatically connects to `http://localhost:8001` for the API when running locally. Open your browser at `http://localhost:3000` to use FinSpark.

---

## Option B — Run with Vercel Frontend + Cloudflare Tunnel

Use this to connect the live Vercel-deployed frontend (`https://finspark-frontend.vercel.app/`) to your local backend. You need **two terminal windows**.

### Terminal 1: Start the Backend

```powershell
# Activate the virtual environment
.venv\Scripts\Activate.ps1

# Start the backend on port 8001
python -m uvicorn backend.main:app --port 8001 --reload
```

### Terminal 2: Start the Cloudflare Tunnel

Run this from the **project root** (where `cloudflared.exe` is located):

```powershell
.\cloudflared.exe tunnel --url http://127.0.0.1:8001
```

> **Important:** Copy the `*.trycloudflare.com` URL printed in the output (e.g., `https://abc-xyz.trycloudflare.com`).
>
> Then go to your **Vercel Project → Settings → Environment Variables** and update `NEXT_PUBLIC_API_BASE_URL` to that new URL, then click **Redeploy**.
>
> Every time you restart the tunnel a new URL is generated — you will need to update Vercel each time.

---

## API Reference

Once the backend is running, the interactive API docs are available at:

- **Swagger UI:** `http://localhost:8001/docs`
- **Health check:** `http://localhost:8001/health`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `GOOGLE_API_KEY not found` | Make sure `.env` exists in the project root with `GOOGLE_API_KEY=...` |
| `ModuleNotFoundError: No module named 'backend'` | Run `uvicorn` from the **project root**, not from inside `backend/` |
| `Embeddings cache warmup failed` | Usually a bad API key — check your `GOOGLE_API_KEY` in `.env` |
| `cloudflared.exe` not recognized | Run it as `.\cloudflared.exe` (with the `.\` prefix) from the project root |
| Frontend shows "Failed to fetch" | Make sure the backend is running on port 8001 and CORS is not blocking |
| Port 8001 already in use | Kill the existing process or change the port: `--port 8002` (update `.env` or frontend config accordingly) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python), Uvicorn |
| LLM | Google Gemini (`gemini-3.1-flash-lite-preview`) |
| Embeddings | Google `text-embedding-005` (512-dim MRL) |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Tunnel | Cloudflare Tunnel (`cloudflared`) |