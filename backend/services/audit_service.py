"""
Audit Service — PostgreSQL-backed
Replaces file-based audit/audit_log.json with the audit_events table.
Interface is 100% backward-compatible with the old file-based version.
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional

from backend.database.connection import get_db_for_client


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
    Emit a structured audit event and persist it to the audit_events table.

    Args:
        client_id:   The client ID (must exist in projects table)
        stage:       Pipeline stage identifier (e.g., 'stage_2_parsing')
        action:      Description of what happened
        agent:       Who/what performed the action
        responsible: Human or system responsible
        input_data:  Raw input string for hashing
        output_data: Raw output string for hashing
        details:     Additional context

    Returns:
        The audit entry dict
    """
    ts = datetime.now(timezone.utc)
    input_hash  = compute_hash(input_data)  if input_data  else None
    output_hash = compute_hash(output_data) if output_data else None

    try:
        with get_db_for_client(client_id) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_events
                        (client_id, timestamp, stage, action, agent, responsible, input_hash, output_hash, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (client_id, ts, stage, action, agent, responsible, input_hash, output_hash, details),
                )
    except Exception as e:
        # Never crash the pipeline because of an audit write failure
        print(f"  [AuditDB] WARNING: failed to write audit event — {e}")

    print(f"  [Log] Audit [{stage}] {action}")

    return {
        "timestamp": ts.isoformat(),
        "stage":     stage,
        "action":    action,
        "agent":     agent,
        "responsible": responsible,
        "input_hash":  input_hash,
        "output_hash": output_hash,
        "details":     details,
    }


def get_audit_log(client_id: str) -> dict:
    """
    Read the full audit log for a client from the database.
    Returns the same shape as the old file-based version: {"entries": [...]}
    """
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, stage, action, agent, responsible,
                       input_hash, output_hash, details
                FROM audit_events
                WHERE client_id = %s
                ORDER BY timestamp ASC
                """,
                (client_id,),
            )
            rows = cur.fetchall()

    entries = [
        {
            "timestamp":   row[0].isoformat() if row[0] else None,
            "stage":       row[1],
            "action":      row[2],
            "agent":       row[3],
            "responsible": row[4],
            "input_hash":  row[5],
            "output_hash": row[6],
            "details":     row[7],
        }
        for row in rows
    ]
    return {"entries": entries}
