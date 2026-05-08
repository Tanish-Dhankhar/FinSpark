# FinSpark Final

FinSpark is an AI orchestrated integration engine with both a Python backend and a Next.js frontend.

## Prerequisites

-   Python 3.10+ (or [uv](https://github.com/astral-sh/uv) recommended)
-   Node.js 20+

## How to Run (Connected to Vercel Frontend)

Since the frontend is deployed to Vercel at `https://finspark-frontend.vercel.app/`, you only need to run the backend and expose it to the internet using a Cloudflare tunnel so Vercel can communicate with it.

You will need two separate PowerShell windows.

### Terminal 1: The Backend

1.  Open a terminal in the project root directory (where `requirements.txt` is located).
2.  Create and activate a virtual environment (using `uv` is recommended):
    
    ```powershell
    uv venv& .venvScriptsActivate.ps1
    ```
    
3.  Install dependencies:
    
    ```powershell
    uv pip install -r requirements.txt
    ```
    
4.  Setup environment variables by ensuring your API keys (e.g., `GOOGLE_API_KEY`) are set in your `.env` file.
5.  Start the Python server on port 8001:
    
    ```powershell
    python -m uvicorn backend.main:app --port 8001 --reload
    ```
    

### Terminal 2: The Public Tunnel

In a new terminal window at the project root, start the Cloudflare tunnel to expose port 8001:

```powershell
.cloudflared.exe tunnel --url http://127.0.0.1:8001
```

*(Note: Every time you restart the cloudflared tunnel, it generates a fresh new `.trycloudflare.com` URL. You will just need to copy that URL, go to your Vercel Project Settings -> Environment Variables, and update `NEXT_PUBLIC_API_BASE_URL` to the new link, then hit "Redeploy").*