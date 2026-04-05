"""
Credential Service
Handles per-client .env file operations.
Credentials are never logged or stored in config — only env var names are referenced.
"""
import os
from pathlib import Path
from typing import Optional, Dict

from backend.config import CLIENTS_DIR


def read_client_env(client_id: str) -> Dict[str, str]:
    """
    Read all key-value pairs from a client's .env file.
    Returns a dict of VAR_NAME -> value.
    Skips comments and blank lines.
    """
    env_path = CLIENTS_DIR / client_id / ".env"
    if not env_path.exists():
        return {}

    env_vars = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env_vars[key.strip()] = value.strip()
    return env_vars


def resolve_credential(client_id: str, env_var_name: str) -> Optional[str]:
    """
    Resolve a single credential by its environment variable name.
    Never logs the actual value — only the variable name in audit.
    
    Args:
        client_id: The client folder ID
        env_var_name: The environment variable name (e.g., 'CIBIL_API_KEY')
        
    Returns:
        The credential value, or None if not found
    """
    env_vars = read_client_env(client_id)
    return env_vars.get(env_var_name)


def write_credential(client_id: str, env_var_name: str, value: str) -> None:
    """
    Write or update a credential in the client's .env file.
    
    Args:
        client_id: The client folder ID
        env_var_name: The environment variable name
        value: The credential value to store
    """
    env_path = CLIENTS_DIR / client_id / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content
    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    # Check if key already exists — update it
    updated = False
    for i, line in enumerate(existing_lines):
        stripped = line.strip()
        if stripped.startswith(env_var_name + "="):
            existing_lines[i] = f"{env_var_name}={value}"
            updated = True
            break

    if not updated:
        existing_lines.append(f"{env_var_name}={value}")

    env_path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")


def list_credential_vars(client_id: str) -> list:
    """List all credential variable names (NOT values) for a client."""
    env_vars = read_client_env(client_id)
    return list(env_vars.keys())
