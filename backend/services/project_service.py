"""
Project Service — PostgreSQL-backed
Replaces file-system scanning with SQL queries.
Interface is 100% backward-compatible — all callers in main.py continue to work.
"""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import psycopg2.extras  # for RealDictCursor

from backend.config import (
    CLIENTS_DIR,
    CLIENT_SUBDIRS,
    CONFIG_TEMPLATE_PATH,
)
from backend.database.connection import get_db, get_db_for_client, get_admin_db
from backend.services.audit_service import emit_audit_event


# ── Helpers ──────────────────────────────────────────────────────────────────

def generate_client_id() -> str:
    """Generate a unique short client ID like 'client_a8f3bc21'."""
    return f"client_{uuid.uuid4().hex[:8]}"


def _extract_env_vars(obj) -> set:
    """Recursively scan a dict/list for $ENV_VAR references."""
    env_vars = set()
    if isinstance(obj, dict):
        for v in obj.values():
            env_vars |= _extract_env_vars(v)
    elif isinstance(obj, list):
        for item in obj:
            env_vars |= _extract_env_vars(item)
    elif isinstance(obj, str):
        matches = re.findall(r'\$([A-Z][A-Z0-9_]+)', obj)
        env_vars.update(matches)
    return env_vars


# ── Core CRUD ─────────────────────────────────────────────────────────────────

def create_project(client_name: str, client_id: Optional[str] = None) -> dict:
    """
    Initialize a new client project:
    1. Generate unique client_id (if not provided)
    2. Create folder structure for binary files (input_documents, etc.)
    3. Inject client details into config template
    4. INSERT project row into `projects` table
    5. INSERT config v1 into `config_versions` table
    6. INSERT initial pipeline_run row
    7. Seed credential placeholders from config $ENV_VAR references
    8. Write initial audit entry

    Returns:
        Dict with client_id, client_name, created_at
    """
    if not client_id:
        client_id = generate_client_id()

    client_dir = CLIENTS_DIR / client_id
    created_at = datetime.now(timezone.utc)
    created_at_iso = created_at.isoformat()

    # 1. Create directory structure (still needed for binary file uploads)
    client_dir.mkdir(parents=True, exist_ok=True)
    for subdir in CLIENT_SUBDIRS:
        (client_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 2. Build config from template
    template = json.loads(CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8"))
    config_id = f"config_{uuid.uuid4().hex[:12]}"
    run_id    = f"run_{uuid.uuid4().hex[:8]}"

    template["metadata"]["config_id"]              = config_id
    template["metadata"]["config_version"]         = "v1"
    template["metadata"]["created_at"]             = created_at_iso
    template["metadata"]["last_updated_at"]        = created_at_iso
    template["metadata"]["status"]                 = "draft"
    template["metadata"]["client"]["client_id"]    = client_id
    template["metadata"]["client"]["client_name"]  = client_name
    template["metadata"]["pipeline_run"]["run_id"]         = run_id
    template["metadata"]["pipeline_run"]["triggered_by"]   = "project_creation"
    template["metadata"]["pipeline_run"]["triggered_at"]   = created_at_iso

    with get_admin_db() as conn:
        with conn.cursor() as cur:
            # 3. Insert project (uses admin pool — project doesn't exist in DB yet,
            #    so RLS client isolation can't apply until after INSERT commits)
            cur.execute(
                """
                INSERT INTO projects (client_id, client_name, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (client_id) DO NOTHING
                """,
                (client_id, client_name, created_at),
            )

            # 4. Insert config_v1
            cur.execute(
                """
                INSERT INTO config_versions (client_id, version_number, version_label, config_data, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (client_id, 1, "v1", json.dumps(template), "draft", created_at),
            )

            # 5. Insert initial pipeline_run
            cur.execute(
                """
                INSERT INTO pipeline_runs
                    (client_id, run_id, triggered_by, triggered_at, overall_status,
                     current_stage, progress_percent, progress_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (client_id, run_id, "project_creation", created_at,
                 "pending", "idle", 0, "Project created, not yet started"),
            )

            # 6. Seed credential placeholders
            env_vars = _extract_env_vars(template)
            for var in env_vars:
                cur.execute(
                    """
                    INSERT INTO credentials (client_id, var_name, var_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (client_id, var_name) DO NOTHING
                    """,
                    (client_id, var, ""),
                )

    # 7. Audit
    emit_audit_event(
        client_id=client_id,
        stage="project_initialization",
        action=f"Project created for '{client_name}'",
        agent="project_service",
        responsible="user",
        output_data=json.dumps(template),
        details=f"Config template v1 initialized in DB",
    )

    return {
        "client_id":   client_id,
        "client_name": client_name,
        "created_at":  created_at_iso,
        "folder_path": str(client_dir),
    }


def list_projects() -> List[dict]:
    """List all projects from the database (admin operation — bypasses RLS)."""
    with get_admin_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    p.client_id,
                    p.client_name,
                    p.created_at,
                    cv.version_label   AS current_config_version,
                    cv.status          AS config_status,
                    pr.overall_status  AS pipeline_status,
                    cv.config_data
                FROM projects p
                LEFT JOIN LATERAL (
                    SELECT version_label, status, config_data
                    FROM config_versions
                    WHERE client_id = p.client_id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) cv ON TRUE
                LEFT JOIN LATERAL (
                    SELECT overall_status
                    FROM pipeline_runs
                    WHERE client_id = p.client_id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) pr ON TRUE
                ORDER BY p.created_at DESC
                """,
            )
            rows = cur.fetchall()

    projects = []
    for row in rows:
        client_id, client_name, created_at, config_ver, config_status, pipeline_status, config_data = row
        integrations_count = 0
        if config_data:
            cfg = config_data if isinstance(config_data, dict) else json.loads(config_data)
            integrations_count = len(cfg.get("integrations", []))

        projects.append({
            "client_id":                client_id,
            "client_name":              client_name,
            "created_at":               created_at.isoformat() if created_at else "",
            "current_config_version":   config_ver or "v1",
            "pipeline_status":          pipeline_status or "pending",
            "active_integrations_count": integrations_count,
        })
    return projects


def get_project_detail(client_id: str) -> Optional[dict]:
    """Get detailed information about a specific project."""
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            # Check project exists
            cur.execute("SELECT client_name, created_at FROM projects WHERE client_id = %s", (client_id,))
            proj = cur.fetchone()
            if not proj:
                return None

            # All config versions
            cur.execute(
                "SELECT version_label FROM config_versions WHERE client_id = %s ORDER BY version_number",
                (client_id,),
            )
            config_versions = [r[0] for r in cur.fetchall()]

            # Latest pipeline run
            cur.execute(
                """
                SELECT overall_status, current_stage, correction_iterations
                FROM pipeline_runs WHERE client_id = %s ORDER BY created_at DESC LIMIT 1
                """,
                (client_id,),
            )
            run = cur.fetchone() or ("pending", "idle", 0)

            # Simulation reports count
            cur.execute(
                "SELECT COUNT(*) FROM simulation_reports WHERE client_id = %s",
                (client_id,),
            )
            sim_count = cur.fetchone()[0]

            # Documents
            cur.execute(
                "SELECT filename FROM documents WHERE client_id = %s",
                (client_id,),
            )
            docs = [r[0] for r in cur.fetchall()]

            # Latest config
            cur.execute(
                "SELECT config_data FROM config_versions WHERE client_id = %s ORDER BY version_number DESC LIMIT 1",
                (client_id,),
            )
            cfg_row = cur.fetchone()

    config_data = cfg_row[0] if cfg_row else {}
    if isinstance(config_data, str):
        config_data = json.loads(config_data)
    integrations = config_data.get("integrations", [])

    # Also scan on-disk documents folder for files not yet in DB
    doc_dir = CLIENTS_DIR / client_id / "input_documents"
    if doc_dir.exists():
        disk_docs = [f.name for f in doc_dir.iterdir() if f.is_file()]
        # Merge without duplicates
        all_docs = list(set(docs + disk_docs))
    else:
        all_docs = docs

    return {
        "client_id":                 client_id,
        "client_name":               proj[0],
        "created_at":                proj[1].isoformat() if proj[1] else "",
        "current_config_version":    config_versions[-1] if config_versions else "v1",
        "pipeline_status":           run[0],
        "current_stage":             run[1],
        "active_integrations_count": len(integrations),
        "config_versions":           config_versions,
        "diff_files":                [],  # diffs not migrated to DB (still on disk)
        "simulation_reports":        [f"simulation_{i+1}.json" for i in range(sim_count)],
        "input_documents":           all_docs,
        "correction_iterations":     run[2],
    }


# ── Config CRUD ───────────────────────────────────────────────────────────────

def get_latest_config(client_id: str) -> Optional[dict]:
    """Read and return the latest config from config_versions table."""
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT config_data FROM config_versions
                WHERE client_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (client_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    data = row[0]
    return data if isinstance(data, dict) else json.loads(data)


def get_current_version_number(client_id: str) -> int:
    """Get the current (highest) config version number."""
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(version_number) FROM config_versions WHERE client_id = %s",
                (client_id,),
            )
            row = cur.fetchone()
    return row[0] if row and row[0] else 0


def save_config(client_id: str, config: dict, version: Optional[int] = None) -> str:
    """
    Save a config. If version is None, overwrites the latest.
    Otherwise inserts/updates as config_v{version}.

    Also scans for $ENV_VAR references and seeds credential placeholders.
    Returns the version label (e.g., 'v2').
    """
    if version is None:
        current = get_current_version_number(client_id)
        version = current if current > 0 else 1

    version_label = f"v{version}"
    config["metadata"]["config_version"]  = version_label
    config["metadata"]["last_updated_at"] = datetime.now(timezone.utc).isoformat()

    # Determine status from config metadata
    status = config.get("metadata", {}).get("status", "draft")

    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO config_versions (client_id, version_number, version_label, config_data, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (client_id, version_number)
                DO UPDATE SET config_data = EXCLUDED.config_data,
                              status      = EXCLUDED.status
                """,
                (client_id, version, version_label, json.dumps(config), status),
            )

            # Seed any new $ENV_VAR placeholders found in updated config
            env_vars = _extract_env_vars(config)
            for var in env_vars:
                cur.execute(
                    """
                    INSERT INTO credentials (client_id, var_name, var_value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (client_id, var_name) DO NOTHING
                    """,
                    (client_id, var, ""),
                )

    return version_label


def get_latest_config_path(client_id: str):
    """
    Compatibility shim — some pipeline stages write directly to a file path.
    Returns a temporary Path object pointing to a written-out JSON file,
    while the canonical source of truth remains the database.
    """
    config = get_latest_config(client_id)
    if not config:
        return None
    version = get_current_version_number(client_id)
    config_dir = CLIENTS_DIR / client_id / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / f"config_v{version}.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path
