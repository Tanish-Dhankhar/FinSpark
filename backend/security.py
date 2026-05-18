"""
FinSpark Security Module — Enterprise Project Isolation

Provides FastAPI dependencies and helpers that enforce strict client-level isolation.
Every endpoint that touches client data must use these guards.

Defense layers:
  1. Input validation  — client_id and filename formats are validated via strict regex
  2. Ownership check   — every request verifies the project exists in the DB
  3. Path confinement  — all filesystem paths are resolved and asserted to stay within
                         the client's own directory tree (prevents traversal attacks)
"""
import re
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Path as FPath
from backend.database.connection import get_admin_db


# ── Constants ─────────────────────────────────────────────────────────────────

# Valid client_id format: exactly "client_" followed by 8 hex chars
_CLIENT_ID_RE = re.compile(r'^client_[a-f0-9]{8}$')

# Valid filename: alphanumerics, dashes, underscores, dots — NO slashes, NO null bytes
_FILENAME_RE = re.compile(r'^[\w\-\.]{1,255}$')

# Allowed config file extensions
_ALLOWED_EXTENSIONS = {'.json', '.yaml', '.yml', '.txt', '.md', '.pdf', '.docx', '.xlsx', '.csv'}


# ── Input Validators — FastAPI Dependency Functions ───────────────────────────
# These functions take path parameters by name (must match the route's path param).
# FastAPI resolves them automatically when used via Depends().

def validate_client_id(client_id: str = FPath(...)) -> str:
    """
    Validates that the client_id matches the strict FinSpark format.
    Raises HTTP 422 for any malformed or suspicious client_id.

    Usage in endpoint:
        client_id: str = Depends(validate_client_id)
    """
    if not _CLIENT_ID_RE.match(client_id):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_client_id",
                "message": "client_id must match pattern client_[8 hex chars] (e.g., client_a1b2c3d4)",
            },
        )
    return client_id


def validate_filename(filename: str = FPath(...)) -> str:
    """
    Validates that a filename parameter is safe for filesystem use:
    - Matches allowlist regex (no slashes, no null bytes, no special chars)
    - Does not contain path traversal sequences (..)
    - Has an allowed extension (if it has one)

    Usage in endpoint:
        filename: str = Depends(validate_filename)
    """
    # Decode any percent-encoding before validation
    try:
        from urllib.parse import unquote
        decoded = unquote(filename)
    except Exception:
        decoded = filename

    if not _FILENAME_RE.match(decoded):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_filename",
                "message": "Filename may only contain alphanumeric characters, dashes, underscores, and dots.",
            },
        )
    # Belt-and-suspenders traversal check on both raw and decoded forms
    for form in (filename, decoded):
        if '..' in form or '/' in form or '\\' in form or '\x00' in form:
            raise HTTPException(
                status_code=422,
                detail={"error": "path_traversal", "message": "Path traversal detected."},
            )

    suffix = Path(decoded).suffix.lower()
    if suffix and suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "forbidden_extension",
                "message": f"File extension '{suffix}' is not allowed.",
            },
        )
    return decoded


# ── Project Ownership Enforcement ─────────────────────────────────────────────

def require_project(client_id: str = Depends(validate_client_id)) -> dict:
    """
    FastAPI dependency — verifies that the client_id refers to an existing project.

    Depends on validate_client_id, so format is pre-validated.
    Raises 404 if the project does not exist in the database.

    Returns the project row dict on success:
        {"client_id": ..., "client_name": ..., "created_at": ...}

    NOTE: We return 404 (not 403) for non-existent projects — returning 403 would
    leak that a project once existed. For single-tenant admin use, 404 is correct.
    """
    # Use admin pool for existence check — the projects table has RLS that filters
    # by app.current_client_id, which isn't set at this guard stage.
    # The actual data queries within each endpoint use get_db_for_client().
    with get_admin_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT client_id, client_name, created_at FROM projects WHERE client_id = %s",
                (client_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "project_not_found",
                "message": f"Project '{client_id}' does not exist.",
            },
        )

    return {"client_id": row[0], "client_name": row[1], "created_at": row[2]}


# ── Filesystem Path Confinement ────────────────────────────────────────────────

def safe_client_path(base_dir: Path, client_id: str, *parts: str) -> Path:
    """
    Build a filesystem path rooted at base_dir/client_id and resolve it,
    then assert that the resolved path stays inside base_dir/client_id.

    This prevents path traversal via:
      - Symlinks pointing outside the directory
      - URL-encoded or double-encoded sequences like %2e%2e
      - Null bytes or unusual unicode

    Args:
        base_dir:  The CLIENTS_DIR root.
        client_id: The validated client_id (must already be validated).
        *parts:    Additional path segments (e.g. "configs", filename).

    Returns:
        The resolved, safe Path object.

    Raises:
        HTTPException 403 if the resolved path escapes the client directory.
    """
    client_root = (base_dir / client_id).resolve()
    candidate = (client_root / Path(*parts)).resolve() if parts else client_root

    # Use os.path.commonpath for a robust containment check
    import os
    try:
        common = os.path.commonpath([str(client_root), str(candidate)])
    except ValueError:
        # Different drives on Windows — always a traversal
        common = ""

    if common != str(client_root):
        raise HTTPException(
            status_code=403,
            detail={"error": "path_traversal", "message": "Access denied: path is outside project directory."},
        )
    return candidate


# ── Cross-Client DB Guard ──────────────────────────────────────────────────────

def assert_client_owns_resource(resource_client_id: Optional[str], requesting_client_id: str) -> None:
    """
    Assert that a resource's client_id matches the requesting client_id.
    Raises 403 if they don't match.

    Use this when a resource is fetched by a non-client_id key (e.g., run_id)
    and you need to verify the fetched record belongs to the requesting client.
    """
    if resource_client_id != requesting_client_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "access_denied",
                "message": "Resource does not belong to this project.",
            },
        )
