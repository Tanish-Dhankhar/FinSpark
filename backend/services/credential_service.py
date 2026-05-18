"""
Credential Service — PostgreSQL-backed
Replaces per-client .env files with the credentials table.
Interface is 100% backward-compatible with the old .env-based version.
"""
from datetime import datetime, timezone
from typing import Optional, Dict

from backend.database.connection import get_db_for_client


def read_client_env(client_id: str) -> Dict[str, str]:
    """
    Read all key-value pairs for a client from the credentials table.
    Returns a dict of VAR_NAME -> value.
    """
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT var_name, var_value FROM credentials WHERE client_id = %s",
                (client_id,),
            )
            rows = cur.fetchall()
    return {row[0]: row[1] for row in rows}


def resolve_credential(client_id: str, env_var_name: str) -> Optional[str]:
    """
    Resolve a single credential by its variable name.
    Never logs the actual value.

    Args:
        client_id:    The client ID
        env_var_name: The variable name (e.g., 'CIBIL_API_KEY')

    Returns:
        The credential value, or None if not found
    """
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT var_value FROM credentials WHERE client_id = %s AND var_name = %s",
                (client_id, env_var_name),
            )
            row = cur.fetchone()
    return row[0] if row else None


def write_credential(client_id: str, env_var_name: str, value: str) -> None:
    """
    Write or update a credential in the credentials table (UPSERT).

    Args:
        client_id:    The client ID
        env_var_name: The variable name
        value:        The credential value to store
    """
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO credentials (client_id, var_name, var_value, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (client_id, var_name)
                DO UPDATE SET var_value = EXCLUDED.var_value,
                              updated_at = EXCLUDED.updated_at
                """,
                (client_id, env_var_name, value, datetime.now(timezone.utc)),
            )


def write_credentials_bulk(client_id: str, env_vars: Dict[str, str]) -> None:
    """
    Write multiple credentials at once (batch UPSERT).
    Used when scanning config for $ENV_VAR references.

    Args:
        client_id: The client ID
        env_vars:  Dict of VAR_NAME -> value (empty string for placeholders)
    """
    if not env_vars:
        return
    now = datetime.now(timezone.utc)
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            for var_name, var_value in env_vars.items():
                cur.execute(
                    """
                    INSERT INTO credentials (client_id, var_name, var_value, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (client_id, var_name)
                    DO UPDATE SET updated_at = EXCLUDED.updated_at
                    -- Only update timestamp; preserve existing values user may have filled in
                    """,
                    (client_id, var_name, var_value, now),
                )


def list_credential_vars(client_id: str) -> list:
    """List all credential variable names (NOT values) for a client."""
    with get_db_for_client(client_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT var_name FROM credentials WHERE client_id = %s ORDER BY var_name",
                (client_id,),
            )
            rows = cur.fetchall()
    return [row[0] for row in rows]
