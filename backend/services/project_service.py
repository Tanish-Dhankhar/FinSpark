"""
Project Service
Handles project initialization — folder creation, template injection, listing.
"""
import json
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from backend.config import (
    CLIENTS_DIR,
    CLIENT_SUBDIRS,
    CONFIG_TEMPLATE_PATH,
)
from backend.services.audit_service import emit_audit_event


def generate_client_id() -> str:
    """Generate a unique short client ID like 'client_a8f3bc21'."""
    return f"client_{uuid.uuid4().hex[:8]}"


def create_project(client_name: str) -> dict:
    """
    Initialize a new client project:
    1. Generate unique client_id
    2. Create folder structure
    3. Inject client details into config template → config_v1.json
    4. Create empty .env
    5. Write initial audit entry
    
    Returns:
        Dict with client_id, client_name, created_at, folder_path
    """
    client_id = generate_client_id()
    client_dir = CLIENTS_DIR / client_id
    created_at = datetime.now(timezone.utc).isoformat()

    # 1. Create directory structure
    client_dir.mkdir(parents=True, exist_ok=True)
    for subdir in CLIENT_SUBDIRS:
        (client_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 2. Read template and inject client details
    template = json.loads(CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8"))
    
    config_id = f"config_{uuid.uuid4().hex[:12]}"
    template["metadata"]["config_id"] = config_id
    template["metadata"]["config_version"] = "v1"
    template["metadata"]["created_at"] = created_at
    template["metadata"]["last_updated_at"] = created_at
    template["metadata"]["status"] = "draft"
    template["metadata"]["client"]["client_id"] = client_id
    template["metadata"]["client"]["client_name"] = client_name
    template["metadata"]["pipeline_run"]["run_id"] = f"run_{uuid.uuid4().hex[:8]}"
    template["metadata"]["pipeline_run"]["triggered_by"] = "project_creation"
    template["metadata"]["pipeline_run"]["triggered_at"] = created_at

    # 3. Save as config_v1.json
    config_path = client_dir / "configs" / "config_v1.json"
    config_path.write_text(json.dumps(template, indent=2), encoding="utf-8")

    # 4. Create empty .env with header
    env_path = client_dir / ".env"
    env_content = (
        f"# FinSpark Credential Vault — {client_name} ({client_id})\n"
        f"# Created: {created_at}\n"
        f"# WARNING: Never commit this file to version control.\n"
        f"# Add credentials as KEY=VALUE pairs below.\n\n"
    )
    env_path.write_text(env_content, encoding="utf-8")

    # 5. Audit
    emit_audit_event(
        client_id=client_id,
        stage="project_initialization",
        action=f"Project created for '{client_name}'",
        agent="project_service",
        responsible="user",
        output_data=json.dumps(template),
        details=f"Config template v1 initialized at {config_path}",
    )

    return {
        "client_id": client_id,
        "client_name": client_name,
        "created_at": created_at,
        "folder_path": str(client_dir),
    }


def list_projects() -> List[dict]:
    """List all existing projects by scanning /clients/ folder."""
    projects = []
    if not CLIENTS_DIR.exists():
        return projects

    for folder in sorted(CLIENTS_DIR.iterdir()):
        if not folder.is_dir() or not folder.name.startswith("client_"):
            continue

        # Try to read the latest config to get project info
        config_dir = folder / "configs"
        if not config_dir.exists():
            continue

        config_files = sorted(config_dir.glob("config_v*.json"))
        if not config_files:
            continue

        latest_config_path = config_files[-1]
        try:
            config = json.loads(latest_config_path.read_text(encoding="utf-8"))
            meta = config.get("metadata", {})
            client_info = meta.get("client", {})
            pipeline_info = meta.get("pipeline_run", {})
            integrations = config.get("integrations", [])

            projects.append({
                "client_id": folder.name,
                "client_name": client_info.get("client_name", "Unknown"),
                "created_at": meta.get("created_at", ""),
                "current_config_version": meta.get("config_version", "v1"),
                "pipeline_status": pipeline_info.get("overall_status", "pending"),
                "active_integrations_count": len(integrations),
            })
        except (json.JSONDecodeError, KeyError):
            projects.append({
                "client_id": folder.name,
                "client_name": "Unknown",
                "created_at": "",
                "current_config_version": "v1",
                "pipeline_status": "unknown",
                "active_integrations_count": 0,
            })

    return projects


def get_project_detail(client_id: str) -> Optional[dict]:
    """Get detailed information about a specific project."""
    client_dir = CLIENTS_DIR / client_id
    if not client_dir.exists():
        return None

    config_dir = client_dir / "configs"
    config_files = sorted(config_dir.glob("config_v*.json")) if config_dir.exists() else []
    diff_files = sorted((client_dir / "diffs").glob("*.json")) if (client_dir / "diffs").exists() else []
    sim_files = sorted((client_dir / "simulation_reports").glob("*.json")) if (client_dir / "simulation_reports").exists() else []
    doc_files = list((client_dir / "input_documents").iterdir()) if (client_dir / "input_documents").exists() else []

    # Read latest config
    latest_config = {}
    if config_files:
        latest_config = json.loads(config_files[-1].read_text(encoding="utf-8"))

    meta = latest_config.get("metadata", {})
    client_info = meta.get("client", {})
    pipeline_info = meta.get("pipeline_run", {})
    integrations = latest_config.get("integrations", [])

    return {
        "client_id": client_id,
        "client_name": client_info.get("client_name", "Unknown"),
        "created_at": meta.get("created_at", ""),
        "current_config_version": meta.get("config_version", "v1"),
        "pipeline_status": pipeline_info.get("overall_status", "pending"),
        "current_stage": pipeline_info.get("overall_status", "pending"),
        "active_integrations_count": len(integrations),
        "config_versions": [f.name for f in config_files],
        "diff_files": [f.name for f in diff_files],
        "simulation_reports": [f.name for f in sim_files],
        "input_documents": [f.name for f in doc_files],
        "correction_iterations": pipeline_info.get("correction_iterations", 0),
    }


def get_latest_config_path(client_id: str) -> Optional[Path]:
    """Get the path to the latest config version."""
    config_dir = CLIENTS_DIR / client_id / "configs"
    if not config_dir.exists():
        return None
    config_files = sorted(config_dir.glob("config_v*.json"))
    return config_files[-1] if config_files else None


def get_latest_config(client_id: str) -> Optional[dict]:
    """Read and return the latest config file."""
    path = get_latest_config_path(client_id)
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def get_current_version_number(client_id: str) -> int:
    """Get the current config version number (e.g., 1, 2, 3)."""
    config_dir = CLIENTS_DIR / client_id / "configs"
    if not config_dir.exists():
        return 0
    config_files = sorted(config_dir.glob("config_v*.json"))
    if not config_files:
        return 0
    # Extract version number from filename like config_v3.json → 3
    latest_name = config_files[-1].stem  # config_v3
    try:
        return int(latest_name.split("_v")[1])
    except (IndexError, ValueError):
        return 1


def save_config(client_id: str, config: dict, version: Optional[int] = None) -> Path:
    """
    Save a config file. If version is None, overwrite the latest.
    Otherwise save as config_v{version}.json.
    Also scans for $ENV_VAR references and updates the client .env file.
    """
    config_dir = CLIENTS_DIR / client_id / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)

    if version is None:
        # Overwrite latest
        current = get_current_version_number(client_id)
        version = current if current > 0 else 1

    path = config_dir / f"config_v{version}.json"
    config["metadata"]["config_version"] = f"v{version}"
    config["metadata"]["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Update .env with any $ENV_VAR references found in the config
    _update_client_env(client_id, config)

    return path


def _extract_env_vars(obj) -> set:
    """Recursively scan a dict/list for $ENV_VAR references."""
    import re
    env_vars = set()
    if isinstance(obj, dict):
        for v in obj.values():
            env_vars |= _extract_env_vars(v)
    elif isinstance(obj, list):
        for item in obj:
            env_vars |= _extract_env_vars(item)
    elif isinstance(obj, str):
        # Match patterns like $KARZA_API_KEY, $CIBIL_OAUTH_CLIENT_SECRET
        matches = re.findall(r'\$([A-Z][A-Z0-9_]+)', obj)
        env_vars.update(matches)
    return env_vars


def _update_client_env(client_id: str, config: dict):
    """
    Scan the config for $ENV_VAR references and ensure they
    exist in the client's .env file with empty defaults.
    Preserves any existing values the user has already filled in.
    """
    env_vars = _extract_env_vars(config)
    if not env_vars:
        return

    env_path = CLIENTS_DIR / client_id / ".env"
    client_name = config.get("metadata", {}).get("client", {}).get("client_name", client_id)

    # Parse existing .env to preserve already-set values
    existing = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                existing[key.strip()] = val.strip()

    # Build the new .env content
    lines = [
        f"# FinSpark Credential Vault — {client_name} ({client_id})",
        f"# Auto-generated from config references",
        f"# WARNING: Never commit this file to version control.",
        f"# Fill in your API keys and secrets below.",
        "",
    ]

    # Group by adapter prefix (e.g., KARZA, CIBIL, PERFIOS)
    grouped: dict = {}
    for var in sorted(env_vars):
        parts = var.split("_")
        prefix = parts[0] if len(parts) > 1 else "GENERAL"
        grouped.setdefault(prefix, []).append(var)

    for prefix in sorted(grouped.keys()):
        lines.append(f"# — {prefix}")
        for var in sorted(grouped[prefix]):
            value = existing.get(var, "")
            lines.append(f"{var}={value}")
        lines.append("")

    env_path.write_text("\n".join(lines), encoding="utf-8")

