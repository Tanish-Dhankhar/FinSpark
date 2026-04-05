# FinSpark Final

FinSpark is an AI orchestrated integration engine with both a Python backend and a Next.js frontend.

## Prerequisites

- Python 3.10+
- Node.js 20+

## How to run

### Backend

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Setup environment variables by copying `.env.example` to `.env` if needed, or ensuring your API keys (e.g., `GEMINI_API_KEY`) are set in `.env`.
5. Run the server:
   ```bash
   uvicorn main:app --reload
   ```
   The backend runs on `http://127.0.0.1:8000`.

### Frontend

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
   The frontend runs on `http://localhost:3000`.
