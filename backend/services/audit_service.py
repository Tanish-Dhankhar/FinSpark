"""
Audit Service
Structured audit event logging for the pipeline.
Every action emits: timestamp, stage, action, agent, responsible, input_hash, output_hash.
"""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import CLIENTS_DIR


def compute_hash(data: str) -> str:
    """Compute SHA-256 hash of a string."""
    return f"sha256:{hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]}"


def emit_audit_event(
    client_id: str,
    stage: str,
    action: str,
    agent: str = "system",
    responsible: str = "system",
    input_data: Optional[str] = None,
    output_data: Optional[str] = None,
    details: Optional[str] = None,
) -> dict:
    """
    Emit a structured audit event and append it to the client's audit log.
    
    Args:
        client_id: The client folder ID
        stage: Pipeline stage identifier (e.g., 'stage_2_parsing')
        action: Description of what happened
        agent: Who/what performed the action
        responsible: Human or system responsible
        input_data: Raw input string for hashing
        output_data: Raw output string for hashing
        details: Additional context
        
    Returns:
        The audit entry dict
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "action": action,
        "agent": agent,
        "responsible": responsible,
        "input_hash": compute_hash(input_data) if input_data else None,
        "output_hash": compute_hash(output_data) if output_data else None,
        "details": details,
    }

    # Append to audit log file
    audit_dir = CLIENTS_DIR / client_id / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "audit_log.json"

    if audit_file.exists():
        log = json.loads(audit_file.read_text(encoding="utf-8"))
    else:
        log = {"entries": []}

    log["entries"].append(entry)
    audit_file.write_text(json.dumps(log, indent=2), encoding="utf-8")

    print(f"  📋 Audit [{stage}] {action}")
    return entry


def get_audit_log(client_id: str) -> dict:
    """Read the full audit log for a client."""
    audit_file = CLIENTS_DIR / client_id / "audit" / "audit_log.json"
    if audit_file.exists():
        return json.loads(audit_file.read_text(encoding="utf-8"))
    return {"entries": []}
